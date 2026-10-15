import Foundation

enum VoiceTurnState:String {
    case waiting,replying,ready,completed,failed,cancelled
    var label:String {
        switch self {
        case .waiting:return "等待回复"
        case .replying:return "正在回复"
        case .ready:return "已收到 · 未播放"
        case .completed:return "已完成"
        case .failed:return "未完成"
        case .cancelled:return "已停止"
        }
    }
    var terminal:Bool {self == .completed || self == .failed || self == .cancelled}
}

struct VoiceTurn:Identifiable,Equatable {
    let id:UUID
    var user:String
    var voice=false
    var transcribed=false
    var reply=""
    var state=VoiceTurnState.waiting
    var detail=""
    var lastSequence=0
    var waitingForText:Bool {reply.isEmpty && (state == .waiting || state == .replying)}
}

struct VoiceConversation:Equatable {
    private(set) var turns:[VoiceTurn]=[]
    private(set) var callTurns:[VoiceTurn]=[]
    private(set) var callActive=false
    // 最近对话仍只保留10轮；显式通话另存本次完整记录，只在内存中，退出清除。
    mutating func beginCall() {if !callActive {callTurns=[];callActive=true}}
    mutating func endCall() {callActive=false;callTurns=[]}
    private mutating func update(_ id:UUID,_ edit:(inout VoiceTurn)->Void) {
        if let i=turns.firstIndex(where:{$0.id==id}) {edit(&turns[i])}
        if let i=callTurns.firstIndex(where:{$0.id==id}) {edit(&callTurns[i])}
    }
    mutating func begin(id:UUID,text:String,voice:Bool=false) {
        guard !turns.contains(where:{$0.id==id}),!callTurns.contains(where:{$0.id==id}) else {return}
        let turn=VoiceTurn(id:id,user:String(text.prefix(120)),voice:voice)
        turns.append(turn)
        if callActive {callTurns.append(turn)}
        if turns.count>10 {turns.removeFirst(turns.count-10)}
    }
    mutating func transcribe(id:UUID,text:String) {
        guard !text.isEmpty,text.count<=2000 else {return}
        update(id) {turn in
            guard turn.voice,!turn.transcribed,!turn.state.terminal else {return}
            turn.user=text;turn.transcribed=true
        }
    }
    mutating func append(id:UUID,sequence:Int,text:String) {
        guard !text.isEmpty,text.count<=2000,sequence<=64 else {return}
        update(id) {turn in
            guard !turn.state.terminal,sequence>turn.lastSequence,
                  turn.reply.count+text.count+(turn.reply.isEmpty ? 0:1)<=6000 else {return}
            turn.reply += (turn.reply.isEmpty ? "":"\n") + text
            turn.lastSequence=sequence;turn.state = .replying
        }
    }
    mutating func finish(id:UUID,state:VoiceTurnState,detail:String="") {
        update(id) {turn in
            guard !turn.state.terminal || (turn.state == .cancelled && state == .failed) else {return}
            turn.state=state;turn.detail=detail
        }
    }
    mutating func clear() {turns=[];callTurns=[]}
    mutating func finishCommand(id:UUID,outcome:VoiceCommandOutcome) {
        update(id) {turn in
            guard !turn.state.terminal else{return}
            turn.reply=outcome.message;turn.state=outcome.ok ? .completed:.failed
        }
    }
}

enum VoiceWorkerEvent {
    case subtitle(sequence:Int,text:String)
    case transcript(String)
    case localCommand(VoiceLocalCommand)
    case result([String:Any])
}

struct VoiceEventLines {
    private var buffer=Data()
    private var bytes=0
    mutating func append(_ part:Data)throws->[VoiceWorkerEvent] {
        bytes+=part.count
        guard bytes<=262144 else {throw NSError(domain:"voice-events",code:1)}
        buffer.append(part)
        var events:[VoiceWorkerEvent]=[]
        while let end=buffer.firstIndex(of:10) {
            let line=Data(buffer[..<end]);buffer.removeSubrange(...end)
            guard line.count<=32768 else {throw NSError(domain:"voice-events",code:2)}
            if line.isEmpty {continue}
            guard let value=try JSONSerialization.jsonObject(with:line) as? [String:Any] else {throw NSError(domain:"voice-events",code:3)}
            if value["event"] as? String == "subtitle" {
                guard let sequence=value["sequence"] as? Int,(1...64).contains(sequence),
                      let text=value["text"] as? String,!text.isEmpty,text.count<=2000 else {throw NSError(domain:"voice-events",code:4)}
                events.append(.subtitle(sequence:sequence,text:text))
            } else if value["event"] as? String == "transcript" {
                guard let text=value["text"] as? String,!text.isEmpty,text.count<=2000 else {throw NSError(domain:"voice-events",code:6)}
                events.append(.transcript(text))
            } else if value["event"] as? String == "local_command" {
                events.append(.localCommand(try VoiceLocalCommand.decode(value["command"])))
            } else if value["event"] == nil,value["ok"] is Bool {events.append(.result(value))}
        }
        guard buffer.count<=32768 else {throw NSError(domain:"voice-events",code:2)}
        return events
    }
    func finish()throws {
        guard buffer.isEmpty else {throw NSError(domain:"voice-events",code:5)}
    }
}

// 与PCM管道并行读取。正文只送到主线程内存，不交给诊断记录函数。
final class VoiceWorkerEventReader {
    private let group=DispatchGroup()
    private var result:[String:Any]=[:]
    private var command:VoiceLocalCommand?
    private var valid=true
    init(handle:FileHandle,onSubtitle:@escaping (Int,String)->Void,onTranscript:@escaping (String)->Void={_ in}) {
        group.enter()
        DispatchQueue.global(qos:.userInitiated).async { [self] in
            defer {group.leave();try? handle.close()}
            var lines=VoiceEventLines()
            while true {
                let part=handle.availableData
                if part.isEmpty {break}
                guard valid else {continue} // 出错仍排空管道，避免子进程阻塞。
                do {
                    for event in try lines.append(part) {
                        switch event {
                        case let .subtitle(sequence,text):onSubtitle(sequence,text)
                        case let .result(value):result=value
                        case let .transcript(text):onTranscript(text)
                        case let .localCommand(value):
                            guard command == nil else {throw VoiceCommandError("重复指令，未执行。")}
                            command=value
                        }
                    }
                } catch {valid=false}
            }
            do {try lines.finish()} catch {valid=false}
        }
    }
    func wait()->(result:[String:Any],valid:Bool,command:VoiceLocalCommand?) {
        group.wait() // 所有字幕已入队，再发布最终状态。
        return (result,valid && !result.isEmpty,command)
    }
}

func voiceConversationSelfTest() {
    var history=VoiceConversation();let id=UUID()
    history.begin(id:id,text:"你好")
    history.append(id:id,sequence:1,text:"你好呀。")
    precondition(history.turns[0].state == .replying)
    history.append(id:id,sequence:1,text:"不应重复")
    precondition(history.turns[0].reply=="你好呀。")
    history.append(id:id,sequence:2,text:"你好呀。") // 相同文字的不同句子可以合法重复。
    precondition(history.turns[0].reply=="你好呀。\n你好呀。")
    history.finish(id:id,state:.cancelled)
    history.append(id:id,sequence:3,text:"取消后的迟到字幕")
    precondition(history.turns[0].lastSequence==2)
    history.finish(id:id,state:.failed,detail:"连接中断")
    precondition(history.turns[0].state == .failed && !history.turns[0].reply.isEmpty)
    history.clear();history.append(id:id,sequence:4,text:"清空后不复活")
    precondition(history.turns.isEmpty)
    for _ in 0..<12 {history.begin(id:UUID(),text:"固定测试")}
    precondition(history.turns.count==10)
    let completed=history.turns.last!.id
    history.finish(id:completed,state:.completed);history.finish(id:completed,state:.cancelled)
    precondition(history.turns.last!.state == .completed)

    let mic=UUID();history.begin(id:mic,text:"语音消息",voice:true)
    history.transcribe(id:mic,text:"识别结果");precondition(history.turns.last!.user=="识别结果")
    history.transcribe(id:mic,text:"迟到重复");precondition(history.turns.last!.user=="识别结果")
    history.finish(id:mic,state:.cancelled);history.transcribe(id:mic,text:"取消后不更新")
    history.clear();history.transcribe(id:mic,text:"清空后不复活");precondition(history.turns.isEmpty)
    history.begin(id:UUID(),text:"通话前的文字聊天")
    history.beginCall();precondition(history.callTurns.isEmpty)
    let firstCall=UUID();history.begin(id:firstCall,text:"语音消息",voice:true)
    precondition(history.callTurns.last!.waitingForText)
    history.transcribe(id:firstCall,text:"第一句")
    history.append(id:firstCall,sequence:1,text:"第一句回复")
    precondition(!history.callTurns.last!.waitingForText && history.callTurns.last!.user=="第一句")
    for _ in 0..<14 {history.begin(id:UUID(),text:"本次通话",voice:true)}
    precondition(history.turns.count==10 && history.callTurns.count==15)
    history.beginCall();precondition(history.callTurns.count==15) // 暂停后重进不清除。
    history.finish(id:firstCall,state:.completed)
    precondition(history.callTurns.first!.state == .completed) // 超过最近10轮仍能更新。
    let waiting=history.callTurns.last!.id
    history.finish(id:waiting,state:.failed,detail:"连接中断")
    precondition(!history.callTurns.last!.waitingForText)
    history.endCall();history.append(id:firstCall,sequence:2,text:"退出后的迟到内容")
    precondition(history.callTurns.isEmpty && history.turns.count==10)
    history.beginCall();precondition(history.callTurns.isEmpty)
    history.endCall()
    var transcriptLines=VoiceEventLines()
    let transcript=try! transcriptLines.append(Data("{\"event\":\"transcript\",\"text\":\"你好\"}\n".utf8))
    precondition(transcript.count==1)
    if case let .transcript(text)=transcript[0] {precondition(text=="你好")} else {preconditionFailure()}
    let raw=Data("{\"event\":\"subtitle\",\"sequence\":1,\"text\":\"你好，Chan。\"}\n{\"ok\":true}\n".utf8)
    var lines=VoiceEventLines(),events:[VoiceWorkerEvent]=[]
    for byte in raw {events+=try! lines.append(Data([byte]))} // 中文UTF8被拆开仍可还原。
    try! lines.finish();precondition(events.count==2)
    if case let .subtitle(sequence,text)=events[0] {precondition(sequence==1 && text=="你好，Chan。")} else {preconditionFailure()}
    var large=VoiceEventLines()
    do {_=try large.append(Data(repeating:65,count:32769));preconditionFailure()} catch {}
    var truncated=VoiceEventLines();_=try! truncated.append(Data("{\"ok\":true}".utf8))
    do {try truncated.finish();preconditionFailure()} catch {}
    let pipe=Pipe(),reader=VoiceWorkerEventReader(handle:pipe.fileHandleForReading,onSubtitle:{_,_ in})
    pipe.fileHandleForWriting.write(raw);try! pipe.fileHandleForWriting.close()
    let result=reader.wait();precondition(result.valid && result.result["ok"] as? Bool == true)
}
