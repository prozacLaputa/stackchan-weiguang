import Foundation
import AppKit
import AVFoundation
import CoreAudio
import AudioToolbox
import SwiftUI

// 只接受这副 AirPods 的双工 UID，或系统实际使用的 Bluetooth :input/:output 配对。
// 不按显示名称猜测，不读取或切换默认麦克风。
enum VoiceMicrophoneHardware {
    static func pairKey(_ uid:String)->String? {
        let parts=uid.split(separator:":",omittingEmptySubsequences:false)
        guard parts.count==2,["input","output"].contains(String(parts[1])),
              parts[0].range(of:"^[0-9a-fA-F]{2}(-[0-9a-fA-F]{2}){5}$",options:.regularExpression) != nil else {return nil}
        return parts[0].lowercased()
    }
    static func matches(_ input:String,_ output:String)->Bool {
        if !input.isEmpty && input==output {return true}
        guard input.hasSuffix(":input"),output.hasSuffix(":output"),let key=pairKey(input) else {return false}
        return key==pairKey(output)
    }
    static func input(for route:HeadphoneRoute)->AudioDeviceID? {
        guard route.isAirPods,HeadphoneHardware.current()==route else {return nil}
        var address=AudioObjectPropertyAddress(mSelector:kAudioHardwarePropertyDevices,mScope:kAudioObjectPropertyScopeGlobal,mElement:kAudioObjectPropertyElementMain)
        var size:UInt32=0
        guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject),&address,0,nil,&size)==noErr,size>0,size<=4096,size%4==0 else {return nil}
        var ids=Array(repeating:AudioDeviceID(0),count:Int(size)/4)
        guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject),&address,0,nil,&size,&ids)==noErr else {return nil}
        let candidates=ids.filter {valid($0,for:route)}
        return candidates.count==1 ? candidates[0]:nil
    }
    static func valid(_ id:AudioDeviceID,for route:HeadphoneRoute)->Bool {
        let transport=HeadphoneHardware.number(id,kAudioDevicePropertyTransportType)
        return matches(HeadphoneHardware.string(id,kAudioDevicePropertyDeviceUID),route.uid) &&
            HeadphoneHardware.number(id,kAudioDevicePropertyDeviceIsAlive)==1 &&
            (transport==kAudioDeviceTransportTypeBluetooth || transport==kAudioDeviceTransportTypeBluetoothLE) &&
            HeadphoneHardware.string(id,kAudioObjectPropertyManufacturer).lowercased().contains("apple") &&
            HeadphoneHardware.channels(id,scope:kAudioDevicePropertyScopeInput)>0
    }
}

// 按下、松手、迟到的初始化回调都带同一代次；松手不会让迟到的录音重新开始。
struct VoiceHoldState {
    enum Phase {case idle,starting,recording,sending}
    private(set) var id=UUID()
    private(set) var phase=Phase.idle
    var active:Bool {phase != .idle}
    var holding:Bool {phase == .starting || phase == .recording}
    mutating func begin()->UUID {id=UUID();phase = .starting;return id}
    mutating func started(_ token:UUID)->Bool {
        guard token==id,phase == .starting else {return false};phase = .recording;return true
    }
    mutating func release()->Bool {
        guard phase == .recording else {cancel();return false};phase = .sending;return true
    }
    mutating func cancel() {id=UUID();phase = .idle}
    func accepts(_ token:UUID)->Bool {active && token==id}
}

struct VoiceMicrophoneClip {
    let pcm:Data
    let sampleRate:Int
    var seconds:Double {Double(pcm.count)/Double(sampleRate*2)}
}

// 独立录音许可在松手/失焦/路由变化时同步撤销，音频回调不等待主线程。
final class VoiceCapturePermit {
    private let lock=NSLock()
    private var permitted=true
    func revoke() {lock.lock();permitted=false;lock.unlock()}
    var allows:Bool {guard lock.try() else {return false};defer{lock.unlock()};return permitted}
}

final class AirPodsMicrophone {
    let route:HeadphoneRoute
    let gate:VoiceGate
    let ticket:UInt64
    let permit=VoiceCapturePermit()
    private let lock=NSLock()
    private var unit:AudioUnit?
    private var samples:UnsafeMutablePointer<Int16>?
    private var scratch:UnsafeMutablePointer<Int16>?
    private var capacity=0,count=0,rate=0
    private var failed=false,peak:Float=0
    private let chunkCapacity=8192
    private(set) var inputID:AudioDeviceID=0
    init(route:HeadphoneRoute,gate:VoiceGate,ticket:UInt64) {self.route=route;self.gate=gate;self.ticket=ticket}
    func check(_ status:OSStatus)throws {if status != noErr {throw NSError(domain:"airpods-microphone",code:Int(status))}}
    var allowed:Bool {permit.allows && gate.accepts(ticket)}
    func start()throws {
        guard AVCaptureDevice.authorizationStatus(for:.audio) == .authorized,allowed,
              let id=VoiceMicrophoneHardware.input(for:route) else {throw NSError(domain:"airpods-microphone-binding",code:1)}
        inputID=id
        var description=AudioComponentDescription(componentType:kAudioUnitType_Output,componentSubType:kAudioUnitSubType_HALOutput,componentManufacturer:kAudioUnitManufacturer_Apple,componentFlags:0,componentFlagsMask:0)
        guard let component=AudioComponentFindNext(nil,&description) else {throw NSError(domain:"airpods-microphone",code:2)}
        try check(AudioComponentInstanceNew(component,&unit))
        guard let unit=unit else {throw NSError(domain:"airpods-microphone",code:3)}
        do {
            var on:UInt32=1,off:UInt32=0,selected=id
            try check(AudioUnitSetProperty(unit,kAudioOutputUnitProperty_EnableIO,kAudioUnitScope_Input,1,&on,4))
            try check(AudioUnitSetProperty(unit,kAudioOutputUnitProperty_EnableIO,kAudioUnitScope_Output,0,&off,4))
            try check(AudioUnitSetProperty(unit,kAudioOutputUnitProperty_CurrentDevice,kAudioUnitScope_Global,0,&selected,4))
            var confirmed:AudioDeviceID=0,size:UInt32=4
            try check(AudioUnitGetProperty(unit,kAudioOutputUnitProperty_CurrentDevice,kAudioUnitScope_Global,0,&confirmed,&size))
            guard confirmed==id,allowed else {throw NSError(domain:"airpods-microphone-binding",code:4)}
            var hardware=AudioStreamBasicDescription();size=UInt32(MemoryLayout.size(ofValue:hardware))
            try check(AudioUnitGetProperty(unit,kAudioUnitProperty_StreamFormat,kAudioUnitScope_Input,1,&hardware,&size))
            guard [8000.0,16000,24000,32000,44100,48000].contains(hardware.mSampleRate) else {throw NSError(domain:"airpods-microphone-format",code:5)}
            rate=Int(hardware.mSampleRate);capacity=rate*30
            samples = .allocate(capacity:capacity);scratch = .allocate(capacity:chunkCapacity)
            var format=AudioStreamBasicDescription(mSampleRate:hardware.mSampleRate,mFormatID:kAudioFormatLinearPCM,mFormatFlags:kAudioFormatFlagIsSignedInteger|kAudioFormatFlagIsPacked,mBytesPerPacket:2,mFramesPerPacket:1,mBytesPerFrame:2,mChannelsPerFrame:1,mBitsPerChannel:16,mReserved:0)
            try check(AudioUnitSetProperty(unit,kAudioUnitProperty_StreamFormat,kAudioUnitScope_Output,1,&format,UInt32(MemoryLayout.size(ofValue:format))))
            var callback=AURenderCallbackStruct(inputProc:{ref,flags,time,_,frames,_ in
                Unmanaged<AirPodsMicrophone>.fromOpaque(ref).takeUnretainedValue().receive(flags:flags,time:time,frames:frames)
            },inputProcRefCon:Unmanaged.passUnretained(self).toOpaque())
            try check(AudioUnitSetProperty(unit,kAudioOutputUnitProperty_SetInputCallback,kAudioUnitScope_Global,0,&callback,UInt32(MemoryLayout.size(ofValue:callback))))
            try check(AudioUnitInitialize(unit))
            guard allowed,HeadphoneHardware.current()==route,VoiceMicrophoneHardware.valid(id,for:route) else {throw NSError(domain:"airpods-microphone-binding",code:6)}
            try check(AudioOutputUnitStart(unit))
        } catch {_=stop(keep:false);throw error}
    }
    private func receive(flags:UnsafeMutablePointer<AudioUnitRenderActionFlags>,time:UnsafePointer<AudioTimeStamp>,frames:UInt32)->OSStatus {
        guard allowed,let unit=unit,let scratch=scratch,Int(frames)<=chunkCapacity else {return noErr}
        var list=AudioBufferList(mNumberBuffers:1,mBuffers:AudioBuffer(mNumberChannels:1,mDataByteSize:frames*2,mData:scratch))
        let status=AudioUnitRender(unit,flags,time,1,frames,&list)
        guard lock.try() else {return noErr};defer{lock.unlock()}
        guard allowed else {return noErr}
        guard status==noErr,list.mBuffers.mDataByteSize==frames*2,let samples=samples,count+Int(frames)<=capacity else {failed=true;return noErr}
        samples.advanced(by:count).update(from:scratch,count:Int(frames));count+=Int(frames)
        for i in 0..<Int(frames) {peak=max(peak,Float(abs(Int(scratch[i])))/32768)}
        return noErr
    }
    func meter()->(seconds:Double,level:Float,failed:Bool) {
        lock.lock();defer{lock.unlock()}
        let value=(Double(count)/Double(max(1,rate)),peak,failed);peak=0;return value
    }
    // 连续语音只取尚未消费的一小段；采集继续，内存不会累计整场对话。
    func drain()->VoiceMicrophoneClip? {
        lock.lock();defer{lock.unlock()}
        guard !failed,count>0,rate>0,let samples=samples else {return nil}
        let clip=VoiceMicrophoneClip(pcm:Data(bytes:samples,count:count*2),sampleRate:rate)
        count=0;return clip
    }
    // 只在串行录音工作队列中调用；先停设备，再把持有期间的有限数据交回主线程。
    func stop(keep:Bool)->VoiceMicrophoneClip? {
        permit.revoke()
        if let unit=unit {AudioOutputUnitStop(unit);AudioUnitUninitialize(unit);AudioComponentInstanceDispose(unit);self.unit=nil}
        lock.lock();defer{lock.unlock()}
        defer {samples?.deallocate();samples=nil;scratch?.deallocate();scratch=nil;count=0}
        guard keep,!failed,rate>0,count>=rate/3,count<=capacity,let samples=samples else {return nil}
        return VoiceMicrophoneClip(pcm:Data(bytes:samples,count:count*2),sampleRate:rate)
    }
    deinit {_=stop(keep:false)}
}

// NSView 的按下/拖动/松开事件不使用阻塞式 tracking loop；安全计时器仍可运行。
struct VoiceHoldButton:NSViewRepresentable {
    var enabled:Bool
    var recording:Bool
    var begin:()->Void
    var end:(Bool)->Void
    func makeNSView(context:Context)->HoldView {HoldView()}
    func updateNSView(_ view:HoldView,context:Context) {
        view.enabled=enabled;view.recording=recording;view.begin=begin;view.end=end;view.needsDisplay=true
        view.setAccessibilityLabel(recording ? "正在录音，松开发送，Escape 取消":"按住说话，松开发送")
        view.setAccessibilityEnabled(enabled)
    }
    final class HoldView:NSView {
        var enabled=false,recording=false,holding=false
        var begin:(()->Void)?
        var end:((Bool)->Void)?
        override var acceptsFirstResponder:Bool {true}
        override init(frame:NSRect) {super.init(frame:frame);setAccessibilityElement(true);setAccessibilityRole(.button)}
        required init?(coder:NSCoder) {fatalError()}
        override func draw(_ dirtyRect:NSRect) {
            let color=recording ? NSColor.systemOrange:NSColor.controlAccentColor
            color.withAlphaComponent(enabled ? 0.20:0.07).setFill();NSBezierPath(roundedRect:bounds,xRadius:9,yRadius:9).fill()
            color.withAlphaComponent(enabled ? 0.8:0.25).setStroke();let border=NSBezierPath(roundedRect:bounds.insetBy(dx:0.5,dy:0.5),xRadius:9,yRadius:9);border.lineWidth=1;border.stroke()
            let title=recording ? "●  松开发送":"按住说话"
            let attrs:[NSAttributedString.Key:Any]=[.font:NSFont.systemFont(ofSize:12,weight:.semibold),.foregroundColor:enabled ? NSColor.labelColor:NSColor.disabledControlTextColor]
            let size=(title as NSString).size(withAttributes:attrs)
            (title as NSString).draw(at:NSPoint(x:(bounds.width-size.width)/2,y:(bounds.height-size.height)/2),withAttributes:attrs)
        }
        override func mouseDown(with event:NSEvent) {guard enabled,!holding else {return};window?.makeFirstResponder(self);holding=true;begin?()}
        override func mouseDragged(with event:NSEvent) {if holding && !bounds.contains(convert(event.locationInWindow,from:nil)) {holding=false;end?(false)}}
        override func mouseUp(with event:NSEvent) {guard holding else {return};holding=false;end?(bounds.contains(convert(event.locationInWindow,from:nil)))}
        override func keyDown(with event:NSEvent) {
            if event.keyCode==53 {holding=false;end?(false)}
            else if event.keyCode==49 && !event.isARepeat && enabled && !holding {holding=true;begin?()}
            else {super.keyDown(with:event)}
        }
        override func keyUp(with event:NSEvent) {if event.keyCode==49 && holding {holding=false;end?(true)} else {super.keyUp(with:event)}}
        override func resignFirstResponder()->Bool {if holding {holding=false;end?(false)};return super.resignFirstResponder()}
    }
}

func voiceMicrophoneSelfTest() {
    precondition(VoiceMicrophoneHardware.matches("AA-BB-CC-DD-EE-FF:input","aa-bb-cc-dd-ee-ff:output"))
    for uid in ["AA-BB-CC-DD-EE-00:input","AirPods:input","BuiltInMicrophoneDevice", "AA-BB-CC-DD-EE-FF:output"] {
        precondition(!VoiceMicrophoneHardware.matches(uid,"aa-bb-cc-dd-ee-ff:output"))
    }
    precondition(!VoiceMicrophoneHardware.matches("",""))
    var hold=VoiceHoldState();let old=hold.begin();precondition(hold.started(old));precondition(hold.release())
    precondition(hold.phase == .sending);hold.cancel();precondition(!hold.accepts(old))
    let late=hold.begin();precondition(!hold.release());precondition(!hold.started(late)) // 初始化期间已松手，不迟到录音。
    let latest=hold.begin();precondition(!hold.started(old));precondition(hold.started(latest));hold.cancel();precondition(!hold.release())
    let permit=VoiceCapturePermit();precondition(permit.allows);permit.revoke();precondition(!permit.allows)
    print("microphone pairing, hold/release/cancel lifecycle tests passed (no microphone opened)")
}
