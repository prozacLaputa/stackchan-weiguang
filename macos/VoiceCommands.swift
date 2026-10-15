import Foundation

enum VoiceLocalCommand:Equatable {
    case focus(String,Int?), note(String), help(String)
    static func decode(_ raw:Any?)throws->Self {
        guard let value=raw as? [String:Any],let kind=value["kind"] as? String else {throw VoiceCommandError("指令格式无效。")}
        let keys=Set(value.keys)
        if kind=="note",keys==["kind","text"],let text=value["text"] as? String,PanelModel.validNote(text) {return .note(text)}
        if kind=="help",keys==["kind","code"],let code=value["code"] as? String,["note_length","focus_duration"].contains(code) {return .help(code)}
        if kind=="focus",let op=value["operation"] as? String {
            if op=="start",keys==["kind","operation","minutes"],let minutes=value["minutes"] as? Int,[15,25,45].contains(minutes) {return .focus(op,minutes)}
            if ["pause","resume","stop"].contains(op),keys==["kind","operation"] {return .focus(op,nil)}
        }
        throw VoiceCommandError("这条指令暂不支持。")
    }
}
struct VoiceCommandError:Error {let message:String;init(_ text:String){message=text}}
struct VoiceCommandOutcome {let ok:Bool;let message:String}

extension PanelModel {
    func voiceCommandRequest(_ command:VoiceLocalCommand)throws->[String:Any] {
        if case let .help(code)=command {
            throw VoiceCommandError(code=="note_length" ? "便签最多32字，请缩短后再说。":"目前支持15、25或45分钟；这次没有开始计时。")
        }
        guard !busy else {throw VoiceCommandError("机器人正在处理上一条操作，请稍后再说。")}
        switch command {
        case let .note(text):
            guard noteAvailable,let current=note else {throw VoiceCommandError("便签状态还没同步，请稍后再说。")}
            guard !noteDirty else {throw VoiceCommandError("控制台有未保存的便签草稿，请先保存或取消。")}
            guard Self.validNote(text) else {throw VoiceCommandError("便签最多32字，请缩短后再说。")}
            return ["action":"note","operation":"set","text":text,"expected_revision":current.revision]
        case let .focus(op,minutes):
            guard focusAvailable else {throw VoiceCommandError("机器人尚未连接或计时状态未同步，这次没有操作。")}
            if op=="start" {
                guard !focusActive else {throw VoiceCommandError("已经有一轮计时，先结束当前番茄钟再开始新的。")}
                guard let minutes=minutes,[15,25,45].contains(minutes) else {throw VoiceCommandError("目前支持15、25或45分钟。")}
                return ["action":"focus","operation":"start","minutes":minutes]
            }
            if op=="pause" && !focusRunning {throw VoiceCommandError("当前没有正在运行的番茄钟。")}
            if op=="resume" && !focusPaused {throw VoiceCommandError("当前没有暂停的番茄钟。")}
            if op=="stop" && companion?.focus_state=="off" {throw VoiceCommandError("当前没有需要结束的番茄钟。")}
            guard ["pause","resume","stop"].contains(op) else {throw VoiceCommandError("这条操作暂不支持。")}
            return ["action":"focus","operation":op]
        case .help:throw VoiceCommandError("这条指令暂不支持。")
        }
    }
    static func confirmedVoiceCommand(_ request:[String:Any],reply:ControlReply,sentAt:Double,now:Double)->Bool {
        guard reply.ok else {return false}
        if request["action"] as? String == "note" {
            guard let note=reply.note,let stamp=reply.note_at,stamp.isFinite,stamp>=sentAt-0.5,stamp<=now+1 else {return false}
            return note.state=="active" && note.save_error==0 && note.text==request["text"] as? String && note.revision >= (request["expected_revision"] as? Int ?? Int.max)
        }
        guard let clock=reply.companion,let stamp=reply.companion_at,stamp.isFinite,stamp>=sentAt-0.5,stamp<=now+1 else {return false}
        switch request["operation"] as? String {
        case "start":return clock.focus_state=="running" && !clock.resting && clock.remaining>0 && clock.chosenSeconds==(request["minutes"] as? Int ?? 0)*60
        case "pause":return clock.focus_state=="paused"
        case "resume":return clock.focus_state=="running"
        case "stop":return clock.focus_state=="off"
        default:return false
        }
    }
    func executeVoiceCommand(_ command:VoiceLocalCommand,
                             transport:(([String:Any],@escaping(Result<Data,Error>)->Void)->Void)?=nil,
                             completion:@escaping(VoiceCommandOutcome)->Void) {
        let request:[String:Any]
        do {request=try voiceCommandRequest(command)}
        catch {completion(VoiceCommandOutcome(ok:false,message:(error as? VoiceCommandError)?.message ?? "这次没有执行操作。"));return}
        busy=true;let began=Date().timeIntervalSince1970
        let handle:(Result<Data,Error>)->Void = { [weak self] result in
            guard let self=self else{return};self.busy=false
            var outcome=VoiceCommandOutcome(ok:false,message:"还没有收到机器人确认，请查看设备状态；不会自动重复操作。")
            if case let .success(data)=result,let reply=try? JSONDecoder().decode(ControlReply.self,from:data) {
                if Self.confirmedVoiceCommand(request,reply:reply,sentAt:began,now:Date().timeIntervalSince1970) {
                    self.acceptReply(reply)
                    let message:String
                    switch command {
                    case let .note(text):message="已贴好便签：\(text)"
                    case let .focus("start",minutes):message="已开始\(minutes ?? 25)分钟番茄钟。"
                    case .focus("pause",_):message="番茄钟已暂停。"
                    case .focus("resume",_):message="番茄钟已继续。"
                    default:message="番茄钟已结束。"
                    }
                    outcome=VoiceCommandOutcome(ok:true,message:message)
                } else if !reply.ok {outcome=VoiceCommandOutcome(ok:false,message:reply.error=="conflict" ? "便签刚被修改，这次没有覆盖，请看过最新内容再说。":Self.errorText(reply.error ?? "unknown"))}
            }
            self.message=outcome.message;self.success=outcome.ok
            completion(outcome)
            if transport == nil {self.refresh()}
        }
        if let transport=transport {transport(request,handle)}
        else {run([root.appendingPathComponent("app/control.py").path],input:try? JSONSerialization.data(withJSONObject:request),completion:handle)}
    }
}

func voiceCommandsSelfTest() {
    precondition((try? VoiceLocalCommand.decode(["kind":"focus","operation":"start","minutes":25])) == .focus("start",25))
    for bad:[String:Any] in [["kind":"shell","command":"test"],["kind":"focus","operation":"start","minutes":5],
                            ["kind":"note","text":String(repeating:"长",count:33)],["kind":"note","text":"便签","extra":true]] {
        precondition((try? VoiceLocalCommand.decode(bad))==nil)
    }
    let stamp=Date().timeIntervalSince1970
    let device=Device(firmware:"0.47",page:"home",battery:100,charging:0,resting:0,brightness:70,light:1,rest:1,pet:1,save_error:0,uptime:1,sync_age:1)
    let clock=Companion(presence:"awake",focus_state:"off",remaining:0,total:0,welcome:0,stage:"focus",focus_total:1500,round:0)
    let bridge=BridgeState(connection:"connected",data_source:"ok",tasks:0,running:0,needs_input:0,device_at:stamp,device:device,companion:clock,companion_at:stamp,note:DeskNote(revision:1,state:"active",text:"原便签",save_error:0),note_at:stamp)
    let model=PanelModel();model.accept(PanelState(installed:true,paused:false,fresh:true,bridge:bridge))
    var calls=0;var outcome:VoiceCommandOutcome?
    model.executeVoiceCommand(.focus("pause",nil),transport:{_,_ in calls+=1}){outcome=$0}
    precondition(calls==0 && outcome?.ok==false)
    model.executeVoiceCommand(.focus("start",25),transport:{request,done in
        calls+=1;precondition(request["minutes"] as? Int==25)
        let reply=ControlReply(ok:true,companion:Companion(presence:"awake",focus_state:"running",remaining:1500,total:1500,welcome:0),companion_at:Date().timeIntervalSince1970)
        // 模拟设备真实格式回执；没有确认之前不发成功消息。
        let data=try! JSONSerialization.data(withJSONObject:["ok":true,"companion":["presence":"awake","focus_state":"running","remaining":1500,"total":1500,"welcome":0],"companion_at":reply.companion_at!])
        done(.success(data))
    }){outcome=$0}
    precondition(calls==1 && outcome?.ok==true && model.focusRunning)
    precondition((try? model.voiceCommandRequest(.focus("start",25)))==nil)
    model.editNote("未保存")
    precondition((try? model.voiceCommandRequest(.note("新便签")))==nil && model.noteDraft=="未保存")
    let request:[String:Any]=["action":"focus","operation":"pause"]
    precondition(!PanelModel.confirmedVoiceCommand(request,reply:ControlReply(ok:true,companion:clock,companion_at:stamp),sentAt:stamp,now:stamp))
    precondition(!PanelModel.confirmedVoiceCommand(request,reply:ControlReply(ok:true,companion:clock,companion_at:stamp-10),sentAt:stamp,now:stamp))
    model.state?.bridge?.connection="waiting_ble"
    precondition((try? model.voiceCommandRequest(.focus("pause",nil)))==nil)
    print("voice commands: allowlist, device acknowledgement, state guards and draft preservation passed")
}
