import Foundation
import CoreGraphics

// 使用音频输出的可用性作为信号，不把连接状态冒充入耳传感器。
// 首次启动只建立基线；短暂掉线、开关变化和唤醒不补发问候。
struct VoiceGreetingTrigger {
    var lastAttempt:TimeInterval=0
    private var wasAvailable:Bool?
    private var awaySince:TimeInterval?
    private var candidateSince:TimeInterval?
    static let minimumAway:TimeInterval=10
    static let settle:TimeInterval=3
    init(lastAttempt:TimeInterval=0) {self.lastAttempt=lastAttempt}

    mutating func reset(available:Bool,now:TimeInterval) {
        wasAvailable=available;awaySince=available ? nil:now;candidateSince=nil
    }
    mutating func poll(available:Bool,permitted:Bool,occupied:Bool,cooldown:TimeInterval,now:TimeInterval)->Bool {
        guard permitted,wasAvailable != nil else {reset(available:available,now:now);return false}
        if !available {
            if wasAvailable != false {awaySince=now}
            wasAvailable=false;candidateSince=nil;return false
        }
        if wasAvailable == false {
            candidateSince=now-(awaySince ?? now)>=Self.minimumAway ? now:nil
            wasAvailable=true;awaySince=nil
        }
        guard let candidate=candidateSince,now-candidate>=Self.settle else {return false}
        candidateSince=nil // 冷却中或忙碌时直接跳过，不延迟到别的时刻开口。
        guard !occupied,now-lastAttempt>=cooldown else {return false}
        lastAttempt=now;return true
    }
}

enum VoiceGreetingLines {
    static let lines=[
        "你终于来啦，等你好久了。",
        "欢迎回来，微光已经就位。",
        "好啦，现在是我们的专属频道。",
        "你一回来，这里就热闹起来了。",
        "欢迎上线，今天也一起慢慢来。",
        "微光待命，随时听你安排。",
        "回来啦，先把今天过得轻松一点。",
        "接收到你啦，今天也有我陪着。"
    ]
    static func next(after previous:Int)->Int {
        lines.indices.filter{$0 != previous}.randomElement() ?? 0
    }
    static func next(excluding:Set<Int>)->Int {
        lines.indices.filter{!excluding.contains($0)}.randomElement() ?? 0
    }
    static func prompt(_ index:Int)->String {
        "我刚戴上耳机，请像贴心小助手，用一句话向我打招呼，不要提问，不要调用工具。只说这句：\(lines[index])"
    }
}

struct PreparedVoiceGreeting {
    let index:Int
    let samples:[Float]
    let rate:Double
    let pitch:Double
    let created:Date
    func usable(rate:Double,pitch:Double,now:Date)->Bool {
        self.rate==rate && self.pitch==pitch && now.timeIntervalSince(created)>=0 && now.timeIntervalSince(created)<6*3600 &&
        !samples.isEmpty && samples.count<=48000*10 && samples.allSatisfy{$0.isFinite && abs($0)<=1}
    }
}

struct VoiceGreetingBank {
    private(set) var clips:[PreparedVoiceGreeting]=[]
    mutating func prune(rate:Double,pitch:Double,now:Date) {
        // 样本在插入时验证一次，轮询只核对元数据。
        clips.removeAll{$0.rate != rate || $0.pitch != pitch || now.timeIntervalSince($0.created)<0 || now.timeIntervalSince($0.created)>=6*3600}
    }
    @discardableResult mutating func insert(_ clip:PreparedVoiceGreeting,now:Date)->Bool {
        guard clip.usable(rate:clip.rate,pitch:clip.pitch,now:now),!clips.contains(where:{$0.index==clip.index}),clips.count<2 else {return false}
        clips.append(clip);return true
    }
    mutating func take(after last:Int,rate:Double,pitch:Double,now:Date)->PreparedVoiceGreeting? {
        prune(rate:rate,pitch:pitch,now:now)
        guard let index=clips.firstIndex(where:{$0.index != last}) else {return nil}
        return clips.remove(at:index)
    }
    mutating func clear() {clips=[]}
}

enum VoiceSession {
    static func isAwake()->Bool {
        // 与现有MacPresence的保守会话判定一致，不读取其他会话内容。
        guard let state=CGSessionCopyCurrentDictionary() as? [String:Any] else {return false}
        return state["kCGSSessionOnConsoleKey"] as? Bool == true &&
            state["kCGSessionLoginDoneKey"] as? Bool == true &&
            state["CGSSessionScreenIsLocked"] as? Bool != true
    }
}

func voiceGreetingSelfTest() {
    var trigger=VoiceGreetingTrigger()
    var now:TimeInterval=10_000
    func tick(_ available:Bool,_ permitted:Bool=true,_ occupied:Bool=false,_ advance:TimeInterval=0)->Bool {
        now+=advance
        return trigger.poll(available:available,permitted:permitted,occupied:occupied,cooldown:60,now:now)
    }
    precondition(!tick(true)) // 启动时已连接，不欢迎一次。
    precondition(!tick(true,true,false,30))
    precondition(!tick(false))
    precondition(!tick(true,true,false,2)) // 短暂重连。
    precondition(!tick(true,true,false,3))
    precondition(!tick(false))
    precondition(!tick(true,true,false,10))
    precondition(!tick(true,true,false,2.9))
    precondition(tick(true,true,false,0.2)) // 稳定满3秒，仅一次。
    let attempt=trigger.lastAttempt
    precondition(!tick(true,true,false,30))
    precondition(!tick(false))
    precondition(!tick(true,true,false,10))
    precondition(!tick(true,true,false,3)) // 冷却中丢弃。
    precondition(!tick(true,true,false,60)) // 不在冷却结束后补播。
    precondition(trigger.lastAttempt==attempt)
    precondition(!tick(false))
    precondition(!tick(true,true,false,10))
    precondition(!tick(true,true,true,3)) // 正在对话，不插话。
    precondition(!tick(true,true,false,10))
    precondition(!tick(false))
    precondition(!tick(true,true,false,10))
    precondition(!tick(true,false,false,1)) // 关闭、锁屏或睡眠取消候选。
    precondition(!tick(true,true,false,30))
    precondition(!tick(false))
    precondition(!tick(true,true,false,10))
    precondition(tick(true,true,false,3))
    var restarted=VoiceGreetingTrigger(lastAttempt:trigger.lastAttempt)
    precondition(!restarted.poll(available:false,permitted:true,occupied:false,cooldown:60,now:now))
    precondition(!restarted.poll(available:true,permitted:true,occupied:false,cooldown:60,now:now+10))
    precondition(!restarted.poll(available:true,permitted:true,occupied:false,cooldown:60,now:now+13))
    for index in VoiceGreetingLines.lines.indices {
        precondition(VoiceGreetingLines.next(after:index) != index)
        precondition(VoiceGreetingLines.prompt(index).count<=120)
    }
    var bank=VoiceGreetingBank();let date=Date()
    bank.insert(PreparedVoiceGreeting(index:0,samples:[0],rate:1,pitch:0,created:date),now:date)
    bank.insert(PreparedVoiceGreeting(index:1,samples:[0.1],rate:1,pitch:0,created:date),now:date)
    precondition(bank.take(after:0,rate:1,pitch:0,now:date)?.index==1)
    precondition(bank.take(after:1,rate:1,pitch:0,now:date)?.index==0)
    precondition(bank.take(after:0,rate:1,pitch:0,now:date)==nil)
    precondition(!bank.insert(PreparedVoiceGreeting(index:2,samples:[.nan],rate:1,pitch:0,created:date),now:date))
    precondition(bank.clips.isEmpty)
    bank.insert(PreparedVoiceGreeting(index:2,samples:[0],rate:1,pitch:0,created:date),now:date)
    precondition(bank.take(after:0,rate:0.9,pitch:0,now:date)==nil) // 改风格后不能播放旧加工音频。
    bank.insert(PreparedVoiceGreeting(index:2,samples:[0],rate:1,pitch:0,created:date),now:date)
    precondition(bank.take(after:0,rate:1,pitch:0,now:date.addingTimeInterval(6*3600))==nil)
}
