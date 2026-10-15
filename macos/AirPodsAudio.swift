import Foundation
import CoreAudio
import AudioToolbox

struct HeadphoneRoute: Equatable {
    var id: AudioDeviceID = 0
    var uid = ""
    var name = ""
    var manufacturer = ""
    var bluetooth = false
    var alive = false
    var outputChannels: UInt32 = 0
    var isAirPods: Bool {
        bluetooth && alive && outputChannels > 0 && !uid.isEmpty &&
        manufacturer.lowercased().contains("apple") && name.lowercased().contains("airpods")
    }
}

enum HeadphoneHardware {
    static func number(_ id: AudioObjectID, _ selector: AudioObjectPropertySelector,
                       scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal) -> UInt32? {
        var address = AudioObjectPropertyAddress(mSelector:selector,mScope:scope,mElement:kAudioObjectPropertyElementMain)
        var value: UInt32 = 0, size = UInt32(MemoryLayout<UInt32>.size)
        guard AudioObjectGetPropertyData(id,&address,0,nil,&size,&value) == noErr else { return nil }
        return value
    }
    static func string(_ id: AudioObjectID, _ selector: AudioObjectPropertySelector) -> String {
        var address = AudioObjectPropertyAddress(mSelector:selector,mScope:kAudioObjectPropertyScopeGlobal,mElement:kAudioObjectPropertyElementMain)
        var value: Unmanaged<CFString>?, size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        guard AudioObjectGetPropertyData(id,&address,0,nil,&size,&value) == noErr,let value=value else { return "" }
        return value.takeRetainedValue() as String
    }
    static func channels(_ id: AudioDeviceID, scope: AudioObjectPropertyScope = kAudioDevicePropertyScopeOutput) -> UInt32 {
        var address = AudioObjectPropertyAddress(mSelector:kAudioDevicePropertyStreamConfiguration,mScope:scope,mElement:kAudioObjectPropertyElementMain)
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(id,&address,0,nil,&size) == noErr,
              size >= MemoryLayout<AudioBufferList>.size, size <= 65536 else { return 0 }
        let memory = UnsafeMutableRawPointer.allocate(byteCount:Int(size),alignment:MemoryLayout<AudioBufferList>.alignment)
        defer { memory.deallocate() }
        guard AudioObjectGetPropertyData(id,&address,0,nil,&size,memory) == noErr else { return 0 }
        return UnsafeMutableAudioBufferListPointer(memory.assumingMemoryBound(to:AudioBufferList.self)).reduce(0) { $0 + $1.mNumberChannels }
    }
    static func current() -> HeadphoneRoute {
        guard let id = number(AudioObjectID(kAudioObjectSystemObject),kAudioHardwarePropertyDefaultOutputDevice), id != 0 else { return HeadphoneRoute() }
        let transport = number(id,kAudioDevicePropertyTransportType)
        return HeadphoneRoute(id:id,uid:string(id,kAudioDevicePropertyDeviceUID),name:string(id,kAudioObjectPropertyName),
            manufacturer:string(id,kAudioObjectPropertyManufacturer),
            bluetooth:transport == kAudioDeviceTransportTypeBluetooth || transport == kAudioDeviceTransportTypeBluetoothLE,
            alive:number(id,kAudioDevicePropertyDeviceIsAlive) == 1,outputChannels:channels(id))
    }
}

// 所有请求带代次：关闭、换输出、睡眠或断连后，旧回复永远不能恢复播放。
final class VoiceGate {
    private let lock = NSLock()
    private var generation: UInt64 = 0
    private var allowed = false
    private var identity = ""
    func update(enabled: Bool, approved: String, route: HeadphoneRoute) {
        lock.lock(); defer { lock.unlock() }
        let next = enabled && !approved.isEmpty && route.isAirPods && approved == route.uid
        let nextIdentity = next ? "\(route.id):\(route.uid)" : ""
        if next != allowed || nextIdentity != identity { generation &+= 1 }
        allowed = next; identity = nextIdentity
    }
    func revoke() { lock.lock(); generation &+= 1; allowed = false; identity = ""; lock.unlock() }
    func ticket() -> UInt64? { lock.lock(); defer { lock.unlock() }; return allowed ? generation : nil }
    func accepts(_ ticket: UInt64) -> Bool {
        // 音频线程不能等 UI；拿不到锁就输出零。
        guard lock.try() else { return false }; defer { lock.unlock() }
        return allowed && generation == ticket
    }
}

final class HeadphoneWatcher {
    let queue = DispatchQueue(label:"weiguang.voice.route")
    var registrations: [(AudioObjectID,AudioObjectPropertyAddress,AudioObjectPropertyListenerBlock)] = []
    var registrationErrors: [String:Int] = [:]
    var device: AudioDeviceID = 0
    var healthy: Bool { device != 0 && registrations.count == 5 }
    let changed: () -> Void
    init(changed: @escaping () -> Void) {
        self.changed = changed
        for selector in [kAudioHardwarePropertyDefaultOutputDevice,kAudioHardwarePropertyDevices,kAudioHardwarePropertyServiceRestarted] {
            add(AudioObjectID(kAudioObjectSystemObject),selector)
        }
    }
    func add(_ id: AudioObjectID, _ selector: AudioObjectPropertySelector) {
        var address = AudioObjectPropertyAddress(mSelector:selector,mScope:kAudioObjectPropertyScopeGlobal,mElement:kAudioObjectPropertyElementMain)
        let callback: AudioObjectPropertyListenerBlock = { [weak self] _,_ in self?.changed() }
        let status=AudioObjectAddPropertyListenerBlock(id,&address,queue,callback)
        if status == noErr { registrations.append((id,address,callback)) }
        else { registrationErrors[String(selector)]=Int(status) }
    }
    func observe(_ id: AudioDeviceID) {
        guard id != device else { return }
        for (object,var address,callback) in registrations where object != AudioObjectID(kAudioObjectSystemObject) {
            AudioObjectRemovePropertyListenerBlock(object,&address,queue,callback)
        }
        registrations.removeAll { $0.0 != AudioObjectID(kAudioObjectSystemObject) }
        device = id
        if id != 0 { add(id,kAudioDevicePropertyDeviceIsAlive); add(id,kAudioDevicePropertyDeviceUID) }
    }
    deinit { for (object,var address,callback) in registrations { AudioObjectRemovePropertyListenerBlock(object,&address,queue,callback) } }
}

// 管道读取可能把一个Float拆开；只向播放器交付完整、有限、有界的样本。
struct VoicePCMChunks {
    private var carry=Data()
    private(set) var bytes=0
    mutating func append(_ data:Data)throws->[Float] {
        guard bytes+data.count<=48000*60*4 else {throw NSError(domain:"voice-stream",code:1)}
        bytes+=data.count;carry.append(data)
        let count=carry.count/4
        var samples=Array(repeating:Float(0),count:count)
        if count>0 {_=samples.withUnsafeMutableBytes{carry.copyBytes(to:$0,count:count*4)};carry.removeFirst(count*4)}
        guard samples.allSatisfy({$0.isFinite && abs($0)<=1}) else {throw NSError(domain:"voice-stream",code:2)}
        return samples
    }
    func finish(allowEmpty:Bool=false)throws {
        guard (bytes>0 || allowEmpty),carry.isEmpty else {throw NSError(domain:"voice-stream",code:3)}
    }
}

final class HeadphonePCMPlayer {
    let gate: VoiceGate
    let ticket: UInt64
    let route: HeadphoneRoute
    private var samples: [Float]
    let gain: Float
    private let lock = NSLock()
    private var cursor = 0
    private var rendered = 0
    private var mouthMeter=VoiceMouthMeter()
    private var active = true
    private var inputFinished:Bool
    private var underruns=0
    private var unit: AudioUnit?
    private(set) var boundCorrectly = false
    init(gate: VoiceGate, ticket: UInt64, route: HeadphoneRoute, samples: [Float], gain: Float,streaming:Bool=false) {
        self.gate=gate;self.ticket=ticket;self.route=route;self.samples=samples;self.gain=gain.isFinite ? min(1,max(0,gain)):0
        inputFinished = !streaming
        if streaming {self.samples.reserveCapacity(48000*60)}
    }
    var finished: Bool { lock.lock(); defer {lock.unlock()}; return (inputFinished && cursor >= samples.count) || !active }
    var renderedFrames: Int { lock.lock(); defer {lock.unlock()}; return rendered }
    var underrunCount:Int {lock.lock();defer{lock.unlock()};return underruns}
    func mouthLevel()->Int? {
        guard gate.accepts(ticket) else {return nil}
        lock.lock();defer{lock.unlock()}
        let level=mouthMeter.take()
        return active ? level:nil
    }
    func append(_ more:[Float])->Bool {
        guard gate.accepts(ticket),more.allSatisfy({$0.isFinite && abs($0)<=1}) else {return false}
        lock.lock();defer{lock.unlock()}
        guard active,!inputFinished,samples.count+more.count<=48000*60 else {return false}
        samples.append(contentsOf:more);return true
    }
    func finishInput() {lock.lock();inputFinished=true;lock.unlock()}
    func check(_ status: OSStatus) throws { if status != noErr { throw NSError(domain:"headphone-audio",code:Int(status)) } }
    func start() throws {
        guard gate.accepts(ticket),route.isAirPods,HeadphoneHardware.current() == route,
              samples.count > 0,samples.count <= 48000 * 60,samples.allSatisfy({$0.isFinite && abs($0) <= 1}) else { throw NSError(domain:"headphone-route",code:1) }
        var description=AudioComponentDescription(componentType:kAudioUnitType_Output,componentSubType:kAudioUnitSubType_HALOutput,componentManufacturer:kAudioUnitManufacturer_Apple,componentFlags:0,componentFlagsMask:0)
        guard let component=AudioComponentFindNext(nil,&description) else {throw NSError(domain:"headphone-audio",code:2)}
        try check(AudioComponentInstanceNew(component,&unit))
        guard let unit=unit else {throw NSError(domain:"headphone-audio",code:3)}
        do {
            var off: UInt32=0,on: UInt32=1,id=route.id
            try check(AudioUnitSetProperty(unit,kAudioOutputUnitProperty_EnableIO,kAudioUnitScope_Input,1,&off,4))
            try check(AudioUnitSetProperty(unit,kAudioOutputUnitProperty_EnableIO,kAudioUnitScope_Output,0,&on,4))
            try check(AudioUnitSetProperty(unit,kAudioOutputUnitProperty_CurrentDevice,kAudioUnitScope_Global,0,&id,4))
            var confirmed: AudioDeviceID=0,size: UInt32=4
            try check(AudioUnitGetProperty(unit,kAudioOutputUnitProperty_CurrentDevice,kAudioUnitScope_Global,0,&confirmed,&size))
            guard confirmed == route.id else {throw NSError(domain:"headphone-route",code:4)}
            boundCorrectly=true
            var format=AudioStreamBasicDescription(mSampleRate:48000,mFormatID:kAudioFormatLinearPCM,mFormatFlags:kAudioFormatFlagsNativeFloatPacked,mBytesPerPacket:8,mFramesPerPacket:1,mBytesPerFrame:8,mChannelsPerFrame:2,mBitsPerChannel:32,mReserved:0)
            try check(AudioUnitSetProperty(unit,kAudioUnitProperty_StreamFormat,kAudioUnitScope_Input,0,&format,UInt32(MemoryLayout.size(ofValue:format))))
            var callback=AURenderCallbackStruct(inputProc:{ ref,_,_,_,frames,data in
                guard let data=data else {return noErr}
                let player=Unmanaged<HeadphonePCMPlayer>.fromOpaque(ref).takeUnretainedValue()
                player.render(frames:frames,data:data)
                return noErr
            },inputProcRefCon:Unmanaged.passUnretained(self).toOpaque())
            try check(AudioUnitSetProperty(unit,kAudioUnitProperty_SetRenderCallback,kAudioUnitScope_Input,0,&callback,UInt32(MemoryLayout.size(ofValue:callback))))
            try check(AudioUnitInitialize(unit))
            guard gate.accepts(ticket),HeadphoneHardware.current() == route else {throw NSError(domain:"headphone-route",code:5)}
            try check(AudioOutputUnitStart(unit))
        } catch { stop(); throw error }
    }
    func render(frames: UInt32, data: UnsafeMutablePointer<AudioBufferList>) {
        let buffers=UnsafeMutableAudioBufferListPointer(data)
        for buffer in buffers {if let ptr=buffer.mData {memset(ptr,0,Int(buffer.mDataByteSize))}}
        guard gate.accepts(ticket),lock.try() else {return}
        defer {lock.unlock()}
        guard active,buffers.count == 1,buffers[0].mNumberChannels == 2,
              buffers[0].mDataByteSize >= frames * 8,let ptr=buffers[0].mData?.assumingMemoryBound(to:Float.self) else {return}
        let count=min(Int(frames),samples.count-cursor)
        if count<Int(frames) && !inputFinished {underruns+=1}
        for i in 0..<count {
            // 约5ms的淡入淡出，避免播放首尾的突发声。
            let remaining=(inputFinished || count<Int(frames)) ? samples.count-1-cursor-i : Int.max
            let fade=min(1,Float(min(cursor+i,remaining))/240)
            let value=samples[cursor+i]*gain*max(0,fade)
            ptr[i*2]=value;ptr[i*2+1]=value
            mouthMeter.add(value)
        }
        cursor += count; rendered += count
    }
    func stop() {
        lock.lock();active=false;lock.unlock()
        if let unit=unit {AudioOutputUnitStop(unit);AudioUnitUninitialize(unit);AudioComponentInstanceDispose(unit);self.unit=nil}
    }
    deinit {stop()}
}

func voiceGateSelfTest() {
    let route=HeadphoneRoute(id:7,uid:"test-airpods",name:"AirPods Pro",manufacturer:"Apple Inc.",bluetooth:true,alive:true,outputChannels:2)
    let gate=VoiceGate()
    gate.update(enabled:false,approved:route.uid,route:route);precondition(gate.ticket()==nil)
    gate.update(enabled:true,approved:route.uid,route:route);let ticket=gate.ticket()!;precondition(gate.accepts(ticket))
    var speaker=route;speaker.bluetooth=false
    gate.update(enabled:true,approved:route.uid,route:speaker);precondition(!gate.accepts(ticket))
    gate.update(enabled:true,approved:route.uid,route:route);precondition(!gate.accepts(ticket))
    let next=gate.ticket()!;gate.revoke();gate.update(enabled:true,approved:route.uid,route:route);precondition(!gate.accepts(next))
    var fake=route;fake.manufacturer="Other";precondition(!fake.isAirPods)
    fake=route;fake.alive=false;gate.update(enabled:true,approved:route.uid,route:fake);precondition(gate.ticket()==nil)
    gate.update(enabled:true,approved:"different",route:route);precondition(gate.ticket()==nil)
    // 真实render函数：开关关闭／失效代次后的非零样本不能进入音频缓冲。
    gate.update(enabled:true,approved:route.uid,route:route)
    let renderTicket=gate.ticket()!
    let player=HeadphonePCMPlayer(gate:gate,ticket:renderTicket,route:route,samples:Array(repeating:0.5,count:960),gain:1)
    let memory=UnsafeMutablePointer<Float>.allocate(capacity:960);defer{memory.deallocate()}
    var buffer=AudioBufferList(mNumberBuffers:1,mBuffers:AudioBuffer(mNumberChannels:2,mDataByteSize:3840,mData:memory))
    player.render(frames:480,data:&buffer);precondition((0..<960).contains{memory[$0]>0});precondition(memory[600]==0.5);precondition(player.mouthLevel()==3 && player.mouthLevel()==nil) // 淡入后原样输出，不能仍被旧20%上限衰减。
    gate.revoke();precondition(player.mouthLevel()==nil);player.render(frames:480,data:&buffer);precondition((0..<960).allSatisfy{memory[$0]==0})
    // 流式缓冲耗尽只输出零，不提前结束或重放；新分片仍受同一代次约束。
    gate.update(enabled:true,approved:route.uid,route:route)
    let stream=HeadphonePCMPlayer(gate:gate,ticket:gate.ticket()!,route:route,samples:Array(repeating:0.25,count:480),gain:1,streaming:true)
    stream.render(frames:480,data:&buffer);precondition(memory[600]==0.25 && !stream.finished)
    stream.render(frames:480,data:&buffer);precondition((0..<960).allSatisfy{memory[$0]==0} && !stream.finished);_ = stream.mouthLevel();precondition(stream.mouthLevel()==nil)
    precondition(stream.append(Array(repeating:0.5,count:960)))
    stream.render(frames:480,data:&buffer);precondition(memory[600]==0.5)
    precondition(!stream.append([.nan]))
    stream.finishInput();precondition(!stream.append([0.1]))
    stream.render(frames:480,data:&buffer);precondition(stream.finished)
    let late=HeadphonePCMPlayer(gate:gate,ticket:gate.ticket()!,route:route,samples:[0.5],gain:1,streaming:true)
    gate.revoke();precondition(!late.append([0.5]));late.render(frames:480,data:&buffer)
    precondition((0..<960).allSatisfy{memory[$0]==0})
    var chunks=VoicePCMChunks(),values:[Float]=[0.25,-0.5]
    let encoded=values.withUnsafeBytes{Data($0)}
    precondition(try! chunks.append(encoded.prefix(3)).isEmpty)
    precondition(try! chunks.append(encoded.dropFirst(3))==values);try! chunks.finish()
    var truncated=VoicePCMChunks();_=try! truncated.append(encoded.prefix(3))
    do {try truncated.finish();preconditionFailure("truncated PCM accepted")}catch{}
    do {try truncated.finish(allowEmpty:true);preconditionFailure("command accepted truncated PCM")}catch{}
    let empty=VoicePCMChunks();try! empty.finish(allowEmpty:true)
    do {try empty.finish();preconditionFailure("empty chat audio accepted")}catch{}
    var invalid=VoicePCMChunks(),bad=Float.nan
    do {_=try invalid.append(withUnsafeBytes(of:&bad){Data($0)});preconditionFailure("invalid PCM accepted")}catch{}
}
