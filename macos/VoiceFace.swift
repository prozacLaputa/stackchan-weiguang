import Foundation
import Darwin

// Samples are measured in the real render callback, never from incoming network audio.
// Owned by HeadphonePCMPlayer's existing lock; no allocation or I/O on the audio thread.
struct VoiceMouthMeter {
    private var energy:Float=0
    private var frames=0
    mutating func add(_ sample:Float) {energy += sample*sample;frames += 1}
    mutating func take()->Int? {
        defer {energy=0;frames=0}
        guard frames>0 else {return nil}
        let rms=sqrt(energy/Float(frames))
        if rms<0.008 {return 0}
        if rms<0.04 {return 1}
        if rms<0.11 {return 2}
        return 3
    }
}

// One latest value, no per-frame queue. A blocked/restarted bridge cannot replay old speech.
final class VoiceFaceRelay {
    private let lock=NSLock()
    private var level:Int?=nil
    private var changed=ProcessInfo.processInfo.systemUptime
    private var timer:DispatchSourceTimer?
    private var sentActive=false
    private let path:String
    init(root:URL) {path=root.appendingPathComponent("runtime/control.sock").path}
    func start() {
        guard timer == nil else {return}
        let source=DispatchSource.makeTimerSource(queue:DispatchQueue(label:"weiguang.voice.face",qos:.utility))
        source.schedule(deadline:.now(),repeating:.milliseconds(150))
        source.setEventHandler {[weak self] in self?.flush()}
        timer=source;source.resume()
    }
    func update(_ next:Int?) {
        lock.lock();level=next;changed=ProcessInfo.processInfo.systemUptime;lock.unlock()
    }
    private func flush() {
        lock.lock();let next=level;let age=ProcessInfo.processInfo.systemUptime-changed;lock.unlock()
        let current=(age>=0 && age<0.45) ? next:nil
        guard current != nil || sentActive else {return}
        let payload:[String:Any] = ["action":"voice","level":current ?? -1,"at":Date().timeIntervalSince1970]
        guard var data=try? JSONSerialization.data(withJSONObject:payload) else {return}
        data.append(10)
        let fd=socket(AF_UNIX,SOCK_STREAM,0)
        guard fd>=0 else {return};defer {Darwin.close(fd)}
        var timeout=timeval(tv_sec:0,tv_usec:120000),one:Int32=1
        setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,socklen_t(MemoryLayout.size(ofValue:timeout)))
        setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,socklen_t(MemoryLayout.size(ofValue:timeout)))
        setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&one,socklen_t(MemoryLayout.size(ofValue:one)))
        var address=sockaddr_un();address.sun_family=sa_family_t(AF_UNIX)
        let bytes=Array(path.utf8)+[0]
        guard bytes.count<=MemoryLayout.size(ofValue:address.sun_path) else {return}
        withUnsafeMutableBytes(of:&address.sun_path) {$0.copyBytes(from:bytes)}
        address.sun_len=UInt8(MemoryLayout<sockaddr_un>.size)
        let connected=withUnsafePointer(to:&address) {
            $0.withMemoryRebound(to:sockaddr.self,capacity:1) {Darwin.connect(fd,$0,socklen_t(MemoryLayout<sockaddr_un>.size))}
        }
        guard connected==0 else {return}
        let count=data.withUnsafeBytes {Darwin.send(fd,$0.baseAddress,data.count,0)}
        guard count==data.count else {return}
        var response=[UInt8](repeating:0,count:128)
        let received=Darwin.recv(fd,&response,response.count,0)
        guard received>0,let value=try? JSONSerialization.jsonObject(with:Data(response.prefix(received))) as? [String:Any],value["ok"] as? Bool == true else {return}
        sentActive=current != nil
    }
    deinit {timer?.cancel()} // The robot's 600ms lease is also required for process crashes.
}

func voiceFaceSelfTest() {
    var meter=VoiceMouthMeter()
    precondition(meter.take()==nil)
    for (value,expected):(Float,Int) in [(0,0),(0.02,1),(0.08,2),(0.3,3)] {
        for _ in 0..<480 {meter.add(value)}
        precondition(meter.take()==expected && meter.take()==nil)
    }
}
