import SwiftUI
import AppKit
import Foundation

struct PendingTask:Codable,Identifiable {
    var id:String, title:String, reason:String
    var codexURL:URL? {
        guard let uuid=UUID(uuidString:id),id.count==36 else{return nil}
        return URL(string:"codex://threads/\(uuid.uuidString.lowercased())?hostId=local")
    }
}
struct Device: Codable {
    var firmware:String, page:String
    var wait_motion:Int?, done_motion:Int?, focus_motion:Int?
    var daily:Int?, away_rest:Int?, greeting:Int?, affection:Int?, skin:Int?
    var motion_fault_id:Int?, motion_recoverable:Int?
    var motion_state:String?, motion_reason:String?, pet_result:String?, pet_reason:String?
    var pet_cooldown_ms:Int?, head_sensor:Int?, pet_event:Int?, pet_age:Int?, head_down:Int?
    var battery:Int, charging:Int, resting:Int, brightness:Int, light:Int, rest:Int, pet:Int, save_error:Int, uptime:Int, sync_age:Int
    var preferences:[String:Int] {
        var result=["light":light,"rest":rest,"pet":pet]
        if let value=wait_motion{result["wait_motion"]=value}
        if let value=done_motion{result["done_motion"]=value}
        if let value=daily{result["daily"]=value}
        if let value=away_rest{result["away_rest"]=value}
        if let value=greeting{result["greeting"]=value}
        if let value=affection{result["affection"]=value}
        if let value=skin{result["skin"]=value}
        if let value=focus_motion{result["focus_motion"]=value}
        return result
    }
}
// 只解释机器人回传值；不把“开关打开”等同于电机已就绪。
struct PetStatus {
    static func reason(_ code:String?)->String {
        switch code ?? "none" {
        case "none":return ""
        case "settling":return "已感应到接触，正在确认是否持续摸头"
        case "cooldown":return "距上次点头开始不足 5 秒，本次不补做"
        case "screen-touch":return "触屏操作优先，已让开"
        case "busy","already-moving":return "当时已有动作，本次不排队"
        case "release-required":return "需要先抬手约 0.4 秒，再重新摸头"
        case "too-short":return "接触时间太短，未达到约 0.12 秒的动作门槛"
        case "preference":return "机器人保存的摸头动作开关已关闭"
        case "disabled":return "动作驱动已手动停用"
        case "head-read":return "头顶触摸传感器暂时读不到"
        case "position-limit":return "当前姿态没有足够的安全点头空间"
        case "load-high":return "舵机回传负载超过设定阈值"
        case "pet-follow-error":return "实测位置没有跟上动作目标"
        case "not-reached":return "在允许时间内未到达目标位置"
        case "timeout":return "动作运行超时"
        case "position-range","feedback-range":return "实测位置超出允许范围"
        case "position-read":return "未能读取有效的舵机位置"
        case "release-ack":return "未确认卸力成功，已请求切断舵机供电"
        case "torque-read":return "舵机驱动状态读数异常"
        case "command-ack","pet-command-ack","return-ack":return "动作命令未收到正常回执"
        case "bus-init":return "舵机通信初始化未成功"
        case "power-init":return "舵机电源初始化未成功"
        case "torque-release":return "启动时未确认舵机已卸力"
        case "calibration":return "本机校准或角度限位数据不可用"
        case "not-initialized":return "动作驱动尚未初始化"
        default:return "设备返回了未知原因，请保留记录排查"
        }
    }
    static func title(_ d:Device?,live:Bool)->String {
        guard live,let d=d else{return "当前不可判断 · 等待新回传"}
        guard let state=d.motion_state else{return "此固件尚无动作反馈"}
        switch state {
        case "ready":return "可响应摸头"
        case "moving":return "正在动作"
        case "checking":return "正在检查动作模块"
        case "cooldown":return "冷却中 · 约 \(((d.pet_cooldown_ms ?? 0)+999)/1000) 秒"
        case "disabled":return "点头已关闭"
        case "unavailable":return "动作暂不可用"
        case "screen":return "正在操作屏幕 · 暂不点头"
        case "release":return "等待抬手后再次触摸"
        case "sensor":return "头顶传感器暂不可读取"
        default:return "状态未知"
        }
    }
    static func latest(_ d:Device?,live:Bool)->String {
        guard let d=d,d.motion_state != nil else{return "等待设备提供摸头记录"}
        guard (d.pet_event ?? 0)>0 else{return live ? "本次开机尚未记录到摸头" : "上次回传时尚无摸头记录"}
        let label:[String:String]=["detected":"已感应，正在确认","moving":"已触发点头","completed":"已完成一次点头","skipped":"已感应，本次未点头","stopped":"点头已中止","failed":"动作异常，已停用"]
        let ago=d.pet_age ?? 0
        let stamp=live ? (ago<60 ? "\(ago) 秒前" : ago<3600 ? "\(ago/60) 分钟前" : "\(ago/3600) 小时前") : "上次记录"
        return "\(stamp) · \(label[d.pet_result ?? "none"] ?? "尚无动作结果")"
    }
    static func detail(_ d:Device?,live:Bool)->String {
        guard live,let d=d else{return "连接恢复后再判断当前能否动作。"}
        if d.motion_state == "checking" {return "请移开手，让头部保持静止。检查过程不会点头。"}
        if d.motion_state == "unavailable" {
            return reason(d.motion_reason)+(d.motion_recoverable == 1 ? "。可尝试恢复动作；故障记录会保留。" : "。当前异常需保留记录并重启检查；切换开关不会重试。")
        }
        if d.motion_state == "sensor" {return "头顶读数不可用，暂不触发动作；这不代表电机故障。"}
        let why=reason(d.pet_reason)
        return why.isEmpty ? "动作开关控制是否允许点头；下方规则决定何时执行。" : "最近一次："+why+"。"
    }
}
struct Companion:Codable {
    var presence:String, focus_state:String
    var remaining:Int, total:Int, welcome:Int
    var stage:String?=nil, focus_total:Int?=nil, round:Int?=nil
    var today_day:Int?=nil, today_seconds:Int?=nil, today_rounds:Int?=nil, summary_save_error:Int?=nil
    var resting:Bool {stage == "rest"}
    var chosenSeconds:Int {focus_total ?? total}
    func seconds(at now:Double,received:Double)->Int {focus_state == "running" ? max(0,remaining-Int(max(0,now-received))) : remaining}
}
struct DeskNote:Codable {var revision:Int;var state:String;var text:String;var save_error:Int}
struct BridgeState: Codable {
    var connection:String, data_source:String
    var transport:String?, error:String?, device_error:String?
    var tasks:Int, running:Int, needs_input:Int
    var ack_ms:Double?, device_at:Double?, device_supported:Bool?, device:Device?
    var desk_extras:DeskExtrasState?=nil
    var pending_tasks:[PendingTask]?
    var diagnostics_ok:Bool?
    var companion:Companion?, companion_at:Double?, companion_error:String?
    var note:DeskNote?=nil, note_at:Double?=nil, note_error:String?=nil
    var pid:Int?=nil, last_good_at:Double?=nil, completion_events:[VoiceTaskCompletion]?=nil
}
struct PanelState: Codable {
    var installed:Bool
    var paused:Bool?, loaded:Bool?, fresh:Bool?, bridge:BridgeState?
    func connected(at now:Double = Date().timeIntervalSince1970)->Bool {
        installed && paused != true && fresh == true && bridge?.connection == "connected"
    }
    func deviceFresh(at now:Double = Date().timeIntervalSince1970)->Bool {
        guard connected(), let b=bridge, b.device != nil, b.device_error == nil, let stamp=b.device_at else{return false}
        return now-stamp >= 0 && now-stamp < 25
    }
    func noteFresh(at now:Double = Date().timeIntervalSince1970)->Bool {
        guard connected(),let b=bridge,b.note != nil,b.note_error == nil,let stamp=b.note_at else{return false}
        return now-stamp>=0 && now-stamp<8
    }
    var pendingFresh:Bool {installed && paused != true && fresh == true && bridge?.data_source == "ok"}
    var taskVoiceSnapshot:VoiceTaskSnapshot? {
        guard pendingFresh,let b=bridge,let pid=b.pid,let stamp=b.last_good_at,let events=b.completion_events else {return nil}
        return VoiceTaskSnapshot(pid:pid,at:stamp,events:events)
    }
    func companionFresh(at now:Double = Date().timeIntervalSince1970)->Bool {
        guard connected(),let b=bridge,b.companion != nil,b.companion_error == nil,let stamp=b.companion_at else{return false}
        return now-stamp >= 0 && now-stamp < 8
    }
}
struct RecoveryReply:Decodable {var ok:Bool;var outcome:String;var state:PanelState?}
struct ControlReply:Decodable {var motion_result:String?=nil;var ok:Bool;var error:String?;var device:Device?;var device_at:Double?;var companion:Companion?;var companion_at:Double?;var note:DeskNote?=nil;var note_at:Double?=nil}
struct DiagnosticReply:Decodable {var ok:Bool;var path:String?;var events:Int?}
struct OpenTaskReply:Decodable {var ok:Bool;var error:String?;var thread_id:String?}

let accent=Color(red:0.45,green:0.85,blue:0.80)
let quiet=Color.white.opacity(0.5)

final class PanelModel:ObservableObject {
    var onTaskSnapshot:((VoiceTaskSnapshot?)->Void)?
    @Published var state:PanelState?
    @Published var busy=false
    @Published var loading=false
    @Published var light=1
    @Published var rest=1
    @Published var pet=true
    @Published var waitMotion=false
    @Published var doneMotion=false
    @Published var focusMotion=true
    @Published var skin=0
    @Published var daily=1
    @Published var awayRest=true
    @Published var greeting=true
    @Published var affection=true
    @Published var dirty:Set<String>=[]
    @Published var message=""
    @Published var success=true
    @Published var openingThreadID:String?
    @Published var exporting=false
    @Published var diagnosticURL:URL?
    @Published var diagnosticMessage=""
    @Published var noteDraft=""
    @Published var noteDirty=false
    @Published var noteBaseRevision:Int?=nil
    @Published var noteMessage=""
    @Published var noteSuccess=true
    @Published var focusMinutes=25
    let root=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Weiguang")
    var timer:Timer?
    var available:Bool {state?.deviceFresh() == true}
    var device:Device? {state?.bridge?.device}
    var companion:Companion? {state?.bridge?.companion}
    var note:DeskNote? {state?.bridge?.note}
    var noteAvailable:Bool {available && ["0.46","0.47","0.48"].contains(device?.firmware ?? "") && state?.noteFresh()==true}
    var noteConflict:Bool {noteDirty && noteBaseRevision != note?.revision}
    var noteStatus:String {
        if let version=device?.firmware,!["0.46","0.47","0.48"].contains(version){return "连接 USB 更新后可用"}
        guard noteAvailable,let n=note else{return "等待机器人同步 · 草稿可继续编辑"}
        if n.save_error==1{return "上次保存失败，原便签仍保留"}
        return n.state=="active" ? "已贴在机器人上" : n.state=="done" ? "已收起 · 可以重新贴上" : "还没有便签"
    }
    static func validNote(_ value:String)->Bool {
        let scalars=value.unicodeScalars
        guard !scalars.isEmpty && scalars.count<=32 else{return false}
        var visible=false
        for scalar in scalars {
            let c=scalar.value
            guard (0x20...0x7e).contains(c) || (0xa0...0x24f).contains(c) || (0x2010...0x2027).contains(c) || (0x3000...0x303f).contains(c) || (0x4e00...0x9fff).contains(c) || (0xff01...0xff60).contains(c) else{return false}
            visible = visible || ![0x20,0xa0,0x3000].contains(c)
        }
        return visible
    }
    func editNote(_ value:String){if !noteDirty{noteBaseRevision=note?.revision};noteDraft=value;noteDirty=true;noteMessage=""}
    func acceptNote(){
        guard state?.noteFresh()==true,let current=note else{return}
        if !noteDirty{noteDraft=current.text;noteBaseRevision=current.revision}
    }
    func discardNote(){guard noteAvailable else{return};noteDirty=false;acceptNote();noteMessage="已读取机器人当前便签。";noteSuccess=true}
    func sendNote(_ operation:String){
        guard noteAvailable,!busy,let current=note else{return}
        if operation=="set" && !Self.validNote(noteDraft){return}
        var request:[String:Any]=["action":"note","operation":operation,"expected_revision":current.revision]
        let sentText=noteDraft
        if operation=="set"{request["text"]=sentText}
        busy=true;noteMessage="正在保存到机器人…";noteSuccess=true
        let input=try? JSONSerialization.data(withJSONObject:request)
        run([root.appendingPathComponent("app/control.py").path],input:input){[weak self] result in
            guard let self=self else{return};self.busy=false
            if case .success(let data)=result,let reply=try? JSONDecoder().decode(ControlReply.self,from:data){
                self.noteSuccess=reply.ok
                if reply.ok{
                    if operation=="set" && self.noteDraft==sentText{self.noteDirty=false}
                    self.acceptReply(reply)
                    self.noteMessage=operation=="done" ? "已收起，随时可以重新贴上。" : "机器人已确认保存。"
                }else{self.noteMessage=reply.error=="conflict" ? "便签刚被更新，草稿已保留。看过最新状态后再贴上。" : reply.error=="save_failed" ? "保存失败，原便签仍保留。" : Self.errorText(reply.error ?? "unknown")}
            }else{self.noteSuccess=false;self.noteMessage="没有收到确认，草稿已保留；请先查看同步后的状态。"}
            self.refresh()
        }
    }
    var focusAvailable:Bool {available && ["0.34","0.35","0.36","0.37","0.38","0.39","0.40","0.41","0.42","0.43","0.44","0.45","0.46","0.47","0.48"].contains(device?.firmware ?? "") && state?.companionFresh() == true}
    var companionSettingsAvailable:Bool {available && device?.daily != nil && device?.away_rest != nil && device?.greeting != nil && device?.affection != nil}
    var focusRunning:Bool {companion?.focus_state == "running"}
    var focusPaused:Bool {companion?.focus_state == "paused"}
    var focusActive:Bool {focusRunning || focusPaused}
    var focusNextAvailable:Bool {focusAvailable && companion?.resting == true && companion?.focus_state == "done"}
    var focusPauseAvailable:Bool {focusAvailable && ["0.40","0.41","0.42","0.43","0.44","0.45","0.46","0.47","0.48"].contains(device?.firmware ?? "")}
    var focusSummaryTitle:String {
        guard state?.companionFresh() == true,let c=companion else{return "等待机器人同步"}
        guard let day=c.today_day else{return "更新固件后可记录"}
        if day==0{return "等待日期同步"}
        let date=Date(timeIntervalSince1970:Double(day)*86400)
        let formatter=DateFormatter();formatter.timeZone=TimeZone(secondsFromGMT:0);formatter.dateFormat="yyyy-MM-dd"
        let local=DateFormatter();local.dateFormat="yyyy-MM-dd"
        guard formatter.string(from:date)==local.string(from:Date()) else{return "等待今日记录同步"}
        let seconds=c.today_seconds ?? 0
        let duration=seconds>0 && seconds<60 ? "不足 1 分钟" : seconds>=3600 ? "\(seconds/3600) 小时 \(seconds%3600/60) 分钟" : "\(seconds/60) 分钟"
        return "\(c.today_rounds ?? 0) 轮 · \(duration)"
    }
    var focusTitle:String {
        guard state?.companionFresh() == true,let c=companion else{return "等待机器人同步"}
        if c.focus_state=="done"{return c.resting ? "休息结束 · 可以开始下一轮" : "专注结束 · 歇一会儿"}
        if c.focus_state != "running" && c.focus_state != "paused"{return "准备好，再开始"}
        let seconds=c.seconds(at:Date().timeIntervalSince1970,received:state?.bridge?.companion_at ?? 0)
        let stage=c.stage == nil ? "" : "第 \(c.round ?? 1) 轮 · \(c.resting ? "休息" : "专注") · "
        return seconds>0 ? stage + String(format:"%02d:%02d",seconds/60,seconds%60) + (focusPaused ? " · 已暂停" : "") : "等待设备确认结束"
    }
    var presenceTitle:String {
        guard state?.companionFresh() == true else{return "Mac 状态待同步"}
        switch companion?.presence {
        case "away":return "Mac 已锁屏或切出当前用户"
        case "awake":return "Mac 已解锁"
        default:return "Mac 状态暂不可读"
        }
    }
    func focus(_ operation:String){
        guard focusAvailable else{return}
        var request:[String:Any]=["action":"focus","operation":operation]
        if operation=="start"{request["minutes"]=focusMinutes}
        issue(request,saving:false)
    }
    var connectionTitle:String {
        guard let s=state else{return "正在读取状态"}
        if !s.installed{return "尚未安装"};if s.paused == true{return "同步已暂停"}
        if s.fresh != true{return "同步服务未就绪"}
        if s.bridge?.connection != "connected"{return "正在等待机器人"}
        if s.bridge?.data_source != "ok"{return "任务数据暂不可读取"}
        return s.bridge?.transport == "ble" ? "蓝牙同步正常" : "USB 同步正常"
    }
    var recoveryTitle:String {state?.paused == true ? "恢复同步" : state?.fresh != true ? "启动同步" : "重新连接"}
    var pending:[PendingTask] {state?.pendingFresh == true ? Array((state?.bridge?.pending_tasks ?? []).filter{$0.codexURL != nil}.prefix(8)) : []}

    func openPending(_ task:PendingTask){
        guard openingThreadID == nil,state?.pendingFresh == true,let url=task.codexURL else{return}
        openingThreadID=task.id
        run([root.appendingPathComponent("app/task_actions.py").path,task.id]){[weak self] result in
            guard let self=self else{return}
            guard case .success(let data)=result,
                  let reply=try? JSONDecoder().decode(OpenTaskReply.self,from:data),reply.ok,reply.thread_id==task.id else{
                self.openingThreadID=nil;self.success=false
                self.message="该任务可能已回应或状态已变化，请等待列表刷新后重试。";self.refresh();return
            }
            guard let app=NSWorkspace.shared.urlForApplication(toOpen:url) else{
                self.openingThreadID=nil;self.success=false;self.message="未找到能打开此会话的 Codex 应用，请先安装或打开 Codex。";return
            }
            let configuration=NSWorkspace.OpenConfiguration();configuration.activates=true
            NSWorkspace.shared.open([url],withApplicationAt:app,configuration:configuration){_,error in
                DispatchQueue.main.async {
                    self.openingThreadID=nil;self.success=error == nil
                    self.message=error == nil ? "已在 Codex 打开会话，请在那里回应。" : "打开会话失败，请在 Codex 中查找该任务。"
                }
            }
        }
    }
    static func diagnosticFile(_ path:String,root:URL)->URL? {
        let url=URL(fileURLWithPath:path).standardizedFileURL
        guard url.deletingLastPathComponent().path==root.appendingPathComponent("diagnostics").standardizedFileURL.path,
              url.pathExtension=="zip",url.lastPathComponent.hasPrefix("微光-诊断-") else{return nil}
        return url
    }
    func exportDiagnostics(){
        guard !exporting,state?.installed == true else{return}
        exporting=true;diagnosticMessage="正在整理本机诊断…"
        run([root.appendingPathComponent("app/service.py").path,"diagnostics"]){[weak self] result in
            guard let self=self else{return};self.exporting=false
            if case .success(let data)=result,let reply=try? JSONDecoder().decode(DiagnosticReply.self,from:data),
               reply.ok,let path=reply.path,let url=Self.diagnosticFile(path,root:self.root),
               FileManager.default.fileExists(atPath:url.path) {
                self.diagnosticURL=url
                self.diagnosticMessage="已导出到本机 · \(reply.events ?? 0) 条记录 · 未上传"
            }else{
                self.diagnosticMessage="导出失败，请检查本机磁盘空间和微光安装目录。"
            }
        }
    }
    func start(){refresh();timer=Timer.scheduledTimer(withTimeInterval:2,repeats:true){[weak self] _ in self?.refresh()}}
    // 子进程只读取本机状态或连接私有 Unix socket，不建立第二条蓝牙连接。
    func run(_ args:[String],input:Data?=nil,completion:@escaping(Result<Data,Error>)->Void){
        let root=self.root
        DispatchQueue.global(qos:.userInitiated).async {
            do {
                let process=Process();process.executableURL=root.appendingPathComponent(".venv/bin/python");process.arguments=args
                let output=Pipe(),errors=Pipe(),stdin=Pipe();process.standardOutput=output;process.standardError=errors;process.standardInput=stdin
                try process.run()
                if let input=input{try stdin.fileHandleForWriting.write(contentsOf:input)}
                try? stdin.fileHandleForWriting.close()
                let data=output.fileHandleForReading.readDataToEndOfFile();process.waitUntilExit()
                guard process.terminationStatus==0 else{throw NSError(domain:"panel",code:Int(process.terminationStatus))}
                DispatchQueue.main.async{completion(.success(data))}
            } catch {DispatchQueue.main.async{completion(.failure(error))}}
        }
    }
    var draftValues:[String:Int] {["light":light,"rest":rest,"pet":pet ? 1:0,"wait_motion":waitMotion ? 1:0,"done_motion":doneMotion ? 1:0,"focus_motion":focusMotion ? 1:0,"daily":daily,"away_rest":awayRest ? 1:0,"greeting":greeting ? 1:0,"affection":affection ? 1:0,"skin":skin]}
    var settingsHint:String {
        if !available{return "连接后自动同步机器人设置"}
        if device?.save_error == 1{return "机器人保存失败 · 设置尚未持久保存"}
        return dirty.isEmpty ? "两端已同步 · 设置保存在机器人" : "有未保存的修改 · 其余设置持续同步"
    }
    func edited(_ key:String){
        if device?.save_error == 0 && draftValues[key]==device?.preferences[key]{dirty.remove(key)}else{dirty.insert(key)}
    }
    func acceptDevice(_ d:Device){
        // 未编辑项跟随机器人；草稿与设备已经相同则无需再次保存。
        for (key,value) in d.preferences where d.save_error == 0 && dirty.contains(key) && draftValues[key]==value{dirty.remove(key)}
        if !dirty.contains("light"){light=d.light}
        if !dirty.contains("rest"){rest=d.rest}
        if !dirty.contains("pet"){pet=d.pet != 0}
        if !dirty.contains("wait_motion"){waitMotion=d.wait_motion == 1}
        if !dirty.contains("done_motion"){doneMotion=d.done_motion == 1}
        if !dirty.contains("focus_motion"),let v=d.focus_motion{focusMotion=v==1}
        if !dirty.contains("daily"),let v=d.daily{daily=v}
        if !dirty.contains("away_rest"),let v=d.away_rest{awayRest=v==1}
        if !dirty.contains("greeting"),let v=d.greeting{greeting=v==1}
        if !dirty.contains("affection"),let v=d.affection{affection=v==1}
        if !dirty.contains("skin"),let v=d.skin{skin=v}
    }
    func accept(_ incoming:PanelState){
        var next=incoming
        // status 子进程可能早于保存回执启动，禁止旧快照把新设置短暂改回去。
        if next.connected(),let latest=state?.bridge,let current=latest.device_at,
           let received=next.bridge?.device_at,received<current {
            next.bridge?.device=latest.device;next.bridge?.device_at=current
            next.bridge?.device_error=latest.device_error;next.bridge?.device_supported=latest.device_supported
        }
        if next.connected(),let latest=state?.bridge,let current=latest.companion_at,
           let received=next.bridge?.companion_at,received<current {
            next.bridge?.companion=latest.companion;next.bridge?.companion_at=current;next.bridge?.companion_error=latest.companion_error
        }
        if next.connected(),let latest=state?.bridge,let current=latest.note_at,let received=next.bridge?.note_at,received<current {
            next.bridge?.note=latest.note;next.bridge?.note_at=current;next.bridge?.note_error=latest.note_error
        }
        state=next
        onTaskSnapshot?(next.taskVoiceSnapshot)
        acceptNote()
        if next.companionFresh(),let c=next.bridge?.companion,(c.focus_state=="running" || c.focus_state=="paused" || c.focus_state=="done"),[15,25,45].contains(c.chosenSeconds/60){focusMinutes=c.chosenSeconds/60}
        if next.deviceFresh(),let d=next.bridge?.device {acceptDevice(d)}
        if message==Self.recoveryText("synced") && !next.deviceFresh(){
            message=next.paused == true ? "同步已暂停；需要时点“恢复同步”。" : "连接状态已变化，等待机器人新回执。"
        }
    }
    func acceptReply(_ reply:ControlReply){
        if let n=reply.note,let stamp=reply.note_at,stamp >= (state?.bridge?.note_at ?? 0){
            state?.bridge?.note=n;state?.bridge?.note_at=stamp;state?.bridge?.note_error=nil;acceptNote()
        }
        if let c=reply.companion,let stamp=reply.companion_at,stamp >= (state?.bridge?.companion_at ?? 0) {
            state?.bridge?.companion=c;state?.bridge?.companion_at=stamp;state?.bridge?.companion_error=nil
            if (c.focus_state=="running" || c.focus_state=="paused" || c.focus_state=="done"),[15,25,45].contains(c.chosenSeconds/60){focusMinutes=c.chosenSeconds/60}
        }
        guard let d=reply.device,let stamp=reply.device_at else{return}
        if let current=state?.bridge?.device_at,stamp<current{return}
        state?.bridge?.device=d;state?.bridge?.device_at=stamp
        state?.bridge?.device_error=nil;state?.bridge?.device_supported=true
        acceptDevice(d)
    }

    func refresh(){
        guard !loading else{return};loading=true
        run([root.appendingPathComponent("app/service.py").path,"status","--json"]){[weak self] result in
            guard let self=self else{return};self.loading=false
            if case .success(let data)=result,let next=try? JSONDecoder().decode(PanelState.self,from:data){self.accept(next)}
            else{self.state=nil;self.onTaskSnapshot?(nil);self.message="无法读取本机服务，请检查安装是否完整。";self.success=false}
        }
    }
    var canRecoverMotion:Bool {
        available && device?.motion_state == "unavailable" && device?.motion_recoverable == 1 && (device?.motion_fault_id ?? 0)>0
    }
    func recoverMotion(){
        guard canRecoverMotion,let id=device?.motion_fault_id else{return}
        issue(["action":"motion_recover","fault_id":id],saving:false)
    }
    static func motionRecoveryText(_ result:String)->String {
        switch result {
        case "recovered":return "动作已恢复，等 5 秒后可再次摸头。计时和设置保持不变，故障记录已保留。"
        case "already-ready":return "动作已经可用，无需重复恢复。"
        case "release-required","not-still":return "请移开手，让头部停稳后再点恢复；本次没有解除保护。"
        case "cooldown":return "请稍等约 10 秒再试，避免连续检查。"
        case "stale-fault":return "设备状态已变化，请等待最新状态后再试。"
        case "check-timeout":return "检查未能及时完成，仍保持停用；请稍后再试。"
        case "diagnostic-save-failed":return "故障记录未能保存，本次未恢复动作。请检查本机存储后再试。"
        case "requires-reset":return "这类异常需要保留记录并重启检查，不能直接解除保护。"
        case "connection-lost":return "连接已变化，检查已停止；不会在重连后补做。"
        case "busy":return "设备正忙，请等当前动作或检查结束。"
        default:return "检查未通过："+PetStatus.reason(result)+"。仍保持停用。"
        }
    }
    func issue(_ request:[String:Any],saving:Bool){
        let motionRecovery=request["action"] as? String == "motion_recover"
        let focus=request["action"] as? String == "focus"
        guard !busy else{return};busy=true;message=motionRecovery ? "正在保存故障并检查电机，请移开手…" : focus ? "等待机器人确认计时…" : saving ? "等待机器人保存…" : "正在检查连接与设备…";success=true
        let input=try? JSONSerialization.data(withJSONObject:request)
        run([root.appendingPathComponent("app/control.py").path],input:input){[weak self] result in
            guard let self=self else{return};self.busy=false
            if case .success(let data)=result,let reply=try? JSONDecoder().decode(ControlReply.self,from:data) {
                self.success=reply.ok
                if motionRecovery,let result=reply.motion_result {
                    self.message=Self.motionRecoveryText(result)
                }else if reply.ok {
                    if saving{self.dirty.removeAll()}
                    self.acceptReply(reply)
                    self.message=focus ? (["start":"机器人已开始专注计时。","stop":"已结束专注计时。","pause":"计时已暂停。","resume":"计时已继续。"][request["operation"] as? String ?? ""] ?? "计时已更新。") : saving ? "机器人已确认保存，重启后保留。" : "机器人已回复；下方显示各环节检查结果。"
                }else{self.message=Self.errorText(reply.error ?? "unknown")}
            }else{self.success=false;self.message="未收到确认，请刷新后检查设备当前状态。"}
            self.refresh()
        }
    }
    static func errorText(_ code:String)->String {
        switch code {
        case "firmware_update_required":return "机器人固件较旧，需要通过 USB 更新后才能使用控制台。"
        case "save_failed":return "设备保存失败，设置可能已临时生效，请重新读取并重试保存。"
        case "confirmation_timeout":return "未收到设备确认，请刷新后检查；修改不会在下次连接时补发。"
        case "busy":return "设备正在处理其他请求，请稍后重试。"
        case "invalid", "invalid_request":return "设置值无效，未发送修改。"
        default:return "设备或同步服务暂不可用，请确认机器人开机、蓝牙开启且同步未暂停。"
        }
    }
    func recover(){
        guard !busy,state?.installed == true else{return}
        let resume=state?.paused == true
        busy=true;success=true;message=resume ? "正在恢复同步，等待机器人确认…" : "正在重新连接，等待机器人确认…"
        var args=[root.appendingPathComponent("app/service.py").path,"recover","--json"]
        if resume{args.append("--resume")}
        run(args){[weak self] result in
            guard let self=self else{return};self.busy=false
            if case .success(let data)=result,let reply=try? JSONDecoder().decode(RecoveryReply.self,from:data){
                self.success=reply.ok
                if let state=reply.state{self.accept(state)}
                self.message=Self.recoveryText(reply.outcome)
            }else{self.success=false;self.message="恢复操作未完成，请检查安装和当前连接状态。"}
            self.refresh()
        }
    }
    static func recoveryText(_ outcome:String)->String {
        switch outcome {
        case "synced":return "同步已恢复，机器人已确认收到当前任务。"
        case "paused":return "同步仍已暂停；需要时点“恢复同步”。"
        case "waiting_device":return "后台已启动，暂未收到机器人回复。请确认机器人开机、距离合适且 Mac 蓝牙可用。"
        case "data_unavailable":return "机器人已连接，但 Codex 任务数据暂不可读取；请打开 Codex 后再检查。"
        case "firmware_update_required":return "任务连接已恢复，设备状态功能需要更新机器人固件。"
        case "busy":return "已有恢复操作正在进行，请等待它结束。"
        case "not_installed":return "尚未安装微光，请先运行安装入口。"
        default:return "同步服务尚未恢复，请查看运行日志或重新安装微光。"
        }
    }
    func save(){
        var changes=[String:Int]()
        if dirty.contains("light"){changes["light"]=light};if dirty.contains("rest"){changes["rest"]=rest};if dirty.contains("pet"){changes["pet"]=pet ? 1:0}
        if dirty.contains("wait_motion"){changes["wait_motion"]=waitMotion ? 1:0}
        if dirty.contains("done_motion"){changes["done_motion"]=doneMotion ? 1:0}
        for key in ["daily","away_rest","greeting","affection","skin","focus_motion"] where dirty.contains(key){changes[key]=draftValues[key]}
        guard !changes.isEmpty,available else{return}
        issue(["action":"configure","changes":changes],saving:true)
    }
    func discard(){dirty.removeAll();if let s=state{accept(s)};message="已恢复设备当前设置。";success=true}
}

struct PetFace:View {
    var body:some View {
        ZStack {
            RoundedRectangle(cornerRadius:21).fill(accent.opacity(0.09))
            HStack(spacing:30){Capsule().frame(width:14,height:6);Capsule().frame(width:14,height:6)}.offset(y:-8)
            Path{p in p.move(to:CGPoint(x:43,y:49));p.addQuadCurve(to:CGPoint(x:65,y:49),control:CGPoint(x:54,y:58))}.stroke(style:StrokeStyle(lineWidth:3,lineCap:.round))
        }.foregroundColor(accent).frame(width:108,height:80)
    }
}

// 控制台通用控件；只管理视觉和点击反馈，不改变保存或设备交互规则。
struct PanelActionStyle:ButtonStyle {
    var prominent=false
    @Environment(\.isEnabled) private var enabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var hovering=false
    func makeBody(configuration:Configuration)->some View {
        configuration.label.font(.system(size:12,weight:.medium))
            .padding(.horizontal,14).padding(.vertical,9)
            .foregroundColor(prominent ? Color(red:0.04,green:0.12,blue:0.13):Color.white.opacity(0.87))
            .background(RoundedRectangle(cornerRadius:10).fill(prominent ? accent:Color.white.opacity(hovering ? 0.10:0.055)))
            .overlay(RoundedRectangle(cornerRadius:10).stroke(prominent ? accent.opacity(0.3):Color.white.opacity(hovering ? 0.15:0.07)))
            .opacity(enabled ? 1:0.35).scaleEffect(configuration.isPressed && !reduceMotion ? 0.98:1)
            .animation(reduceMotion ? nil:.easeOut(duration:0.12),value:configuration.isPressed)
            .onHover {hovering=$0}
    }
}
struct PanelOptionStyle:ButtonStyle {
    var selected:Bool
    @Environment(\.isEnabled) private var enabled
    @State private var hovering=false
    func makeBody(configuration:Configuration)->some View {
        configuration.label.foregroundColor(selected ? accent:Color.white.opacity(0.65))
            .background(RoundedRectangle(cornerRadius:10).fill(selected ? accent.opacity(0.10):Color.white.opacity(hovering ? 0.06:0.025)))
            .overlay(RoundedRectangle(cornerRadius:10).stroke(selected ? accent.opacity(0.55):Color.white.opacity(hovering ? 0.14:0.06)))
            .opacity(enabled ? (configuration.isPressed ? 0.72:1):0.35)
            .onHover {hovering=$0}
    }
}
struct PanelChoices:View {
    let labels:[String]
    @Binding var selection:Int
    var name:String
    var body:some View {
        HStack(spacing:7) {
            ForEach(labels.indices,id:\.self) {i in
                Button {selection=i} label:{Text(labels[i]).font(.system(size:12,weight:selection==i ? .semibold:.regular)).frame(maxWidth:.infinity,minHeight:34)}
                    .buttonStyle(PanelOptionStyle(selected:selection==i))
                    .accessibilityLabel("\(name)：\(labels[i])").accessibilityValue(selection==i ? "已选中":"未选中")
            }
        }
    }
}
struct PanelSectionHeading:View {
    let title:String
    let detail:String
    let icon:String
    var body:some View {
        HStack(spacing:11) {
            Image(systemName:icon).font(.system(size:15,weight:.medium)).foregroundColor(accent)
                .frame(width:34,height:34).background(accent.opacity(0.08),in:RoundedRectangle(cornerRadius:11))
            VStack(alignment:.leading,spacing:4) {
                Text(title).font(.system(size:14,weight:.semibold))
                if !detail.isEmpty {Text(detail).font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)}
            }
            Spacer(minLength:0)
        }
    }
}
struct PanelToggleRow:View {
    let title:String
    var detail:String=""
    @Binding var value:Bool
    var body:some View {
        Toggle(isOn:$value) {
            VStack(alignment:.leading,spacing:5) {
                Text(title).font(.system(size:13))
                if !detail.isEmpty {Text(detail).font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)}
            }.padding(.trailing,18).frame(maxWidth:.infinity,alignment:.leading)
        }.toggleStyle(SwitchToggleStyle(tint:accent)).padding(.vertical,3)
            .accessibilityLabel(title)
    }
}
struct PanelFold<Content:View>:View {
    let title:String
    let summary:String
    var icon:String="slider.horizontal.3"
    let content:Content
    @State private var expanded=false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    init(_ title:String,summary:String="",icon:String="slider.horizontal.3",@ViewBuilder content:()->Content) {
        self.title=title;self.summary=summary;self.icon=icon;self.content=content()
    }
    var body:some View {
        VStack(alignment:.leading,spacing:0) {
            Button {withAnimation(reduceMotion ? nil:.easeInOut(duration:0.18)){expanded.toggle()}} label:{
                HStack(spacing:10) {
                    Image(systemName:icon).font(.system(size:13)).foregroundColor(accent.opacity(0.8)).frame(width:20)
                    Text(title).font(.system(size:13,weight:.medium)).foregroundColor(.white.opacity(0.9))
                    Spacer()
                    if !expanded {Text(summary).font(.system(size:11)).foregroundColor(quiet).lineLimit(1)}
                    Image(systemName:"chevron.right").font(.system(size:10,weight:.semibold)).foregroundColor(quiet).rotationEffect(.degrees(expanded ? 90:0))
                }.padding(.vertical,7).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityLabel(title).accessibilityValue(expanded ? "已展开":"已收起")
            if expanded {
                VStack(alignment:.leading,spacing:16) {content}.padding(.top,15).padding(.bottom,4)
                    .transition(.opacity)
            }
        }
    }
}
struct PanelFacePreview:View {
    let cat:Bool
    var body:some View {
        GeometryReader {g in
            let w=g.size.width,h=g.size.height
            Path {p in
                for side:CGFloat in [-1,1] {
                    let x=w/2+side*w*0.23,y=h*0.48
                    if cat {
                        p.move(to:CGPoint(x:x-8,y:y));p.addQuadCurve(to:CGPoint(x:x+8,y:y),control:CGPoint(x:x,y:y-5))
                        p.move(to:CGPoint(x:x-10,y:y-14));p.addLine(to:CGPoint(x:x-2,y:y-23));p.addLine(to:CGPoint(x:x+7,y:y-14))
                    } else {
                        p.move(to:CGPoint(x:x-6,y:y));p.addLine(to:CGPoint(x:x+6,y:y))
                    }
                }
                p.move(to:CGPoint(x:w/2-7,y:h*0.72));p.addQuadCurve(to:CGPoint(x:w/2+7,y:h*0.72),control:CGPoint(x:w/2,y:h*0.86))
            }.stroke(accent.opacity(0.92),style:StrokeStyle(lineWidth:cat ? 2.2:3.5,lineCap:.round,lineJoin:.round))
        }.accessibilityHidden(true)
    }
}

enum PanelPage:String,CaseIterable,Identifiable {
    case work,chat,robot,connection
    var id:String {rawValue}
    var title:String {switch self {case .work:return "工作台";case .chat:return "对话";case .robot:return "机器人";case .connection:return "连接"}}
    var icon:String {switch self {case .work:return "square.grid.2x2";case .chat:return "bubble.left.and.bubble.right";case .robot:return "face.smiling";case .connection:return "antenna.radiowaves.left.and.right"}}
}
struct PanelView:View {
    @ObservedObject var model:PanelModel
    @ObservedObject var voice:VoiceCompanion
    @ObservedObject var vision:LocalVision
    @AppStorage("controlPanelPage") private var storedPage=PanelPage.work.rawValue
    var page:PanelPage {PanelPage(rawValue:storedPage) ?? .work}
    var live:Bool {model.available}
    var d:Device? {model.device}
    func card<Content:View>(@ViewBuilder _ content:()->Content)->some View {
        VStack(alignment:.leading,spacing:14,content:content).padding(18).frame(maxWidth:.infinity,alignment:.leading)
            .background(RoundedRectangle(cornerRadius:18).fill(Color.white.opacity(0.045)))
            .overlay(RoundedRectangle(cornerRadius:18).stroke(Color.white.opacity(0.07)))
    }
    func diagnostic(_ name:String,_ value:String,_ ok:Bool)->some View {
        HStack{Circle().fill(ok ? accent : Color.orange.opacity(0.9)).frame(width:6,height:6);Text(name).foregroundColor(quiet);Spacer();Text(value)}.font(.system(size:12))
    }
    var body:some View {
        VStack(spacing:0) {
            header.padding(.horizontal,24).padding(.top,20).padding(.bottom,18)
            HStack(spacing:4) {
                ForEach(PanelPage.allCases) {item in
                    Button {storedPage=item.rawValue} label:{
                        HStack(spacing:7) {
                            Image(systemName:item.icon).font(.system(size:12))
                            Text(item.title).font(.system(size:13,weight:page == item ? .semibold:.regular))
                            if item == .robot && !model.dirty.isEmpty {Circle().fill(Color.orange).frame(width:5,height:5)}
                            if item == .work && !model.pending.isEmpty {Text("\(model.pending.count)").font(.system(size:10,weight:.semibold)).foregroundColor(.orange)}
                        }.frame(maxWidth:.infinity).padding(.vertical,10)
                            .foregroundColor(page == item ? accent:quiet)
                            .background(RoundedRectangle(cornerRadius:10).fill(page == item ? accent.opacity(0.10):.clear))
                    }.buttonStyle(.plain).accessibilityLabel(item.title).accessibilityValue(page == item ? "已选中":"未选中")
                }
            }.padding(4).background(Color.white.opacity(0.025),in:RoundedRectangle(cornerRadius:13)).padding(.horizontal,24)
            ScrollView {
                VStack(alignment:.leading,spacing:14) {
                    switch page {
                    case .work:pendingCard;card {DeskExtrasView(model:model)};focusCard;noteCard
                    case .chat:card {VoiceCardView(voice:voice)}
                    case .robot:card {LocalVisionCard(vision:vision,connected:model.state?.connected()==true && model.state?.bridge?.transport=="ble")};petCard;settingsCard
                    case .connection:deviceCard;connectionCard
                    }
                }.frame(maxWidth:.infinity,alignment:.topLeading).padding(24).padding(.top,-6)
            }.id(page)
            if model.busy || !model.message.isEmpty || !model.dirty.isEmpty {footer}
        }.frame(width:620,height:780).background(Color(red:0.055,green:0.065,blue:0.075)).foregroundColor(.white).preferredColorScheme(.dark).accentColor(accent).buttonStyle(PanelActionStyle())
    }
    private var header:some View {
        HStack(spacing:14) {
            PetFace().scaleEffect(0.55).frame(width:60,height:44)
            VStack(alignment:.leading,spacing:5) {
                HStack(alignment:.firstTextBaseline,spacing:8) {Text("微光").font(.system(size:24,weight:.medium));Text("控制台").font(.system(size:11)).foregroundColor(quiet)}
                HStack(spacing:8) {
                    Text("机器人静音").font(.system(size:11)).foregroundColor(quiet)
                    if model.focusActive {
                        Button {storedPage=PanelPage.work.rawValue} label:{Label(model.focusPaused ? "计时已暂停":"专注中",systemImage:"timer").font(.system(size:10)).foregroundColor(accent)}.buttonStyle(.plain)
                    }
                }
            }
            Spacer()
            VStack(alignment:.trailing,spacing:7) {
                Button {storedPage=PanelPage.connection.rawValue} label:{
                    HStack(spacing:5) {Circle().fill(model.state?.connected() == true && model.state?.bridge?.data_source == "ok" ? accent:.orange).frame(width:5,height:5);Text(model.connectionTitle).font(.system(size:11)).foregroundColor(.white.opacity(0.8))}
                }.buttonStyle(.plain).help("查看连接状态")
                HStack(spacing:5) {
                    if live,let d=d,d.battery>=0 {
                        Image(systemName:d.charging == 1 ? "battery.100.bolt":"battery.\(d.battery > 87 ? 100:d.battery > 62 ? 75:d.battery > 37 ? 50:d.battery > 12 ? 25:0)").font(.system(size:12))
                        Text("\(d.battery)%").font(.system(size:11)).monospacedDigit()
                        if d.charging == 1 {Text("充电中").font(.system(size:10))}
                    } else {Text("等待设备状态").font(.system(size:10))}
                }.foregroundColor(quiet)
            }
        }
    }
    private var footer:some View {
        VStack(spacing:0) {
            Rectangle().fill(Color.white.opacity(0.06)).frame(height:1)
            HStack(spacing:12) {
                if model.busy {ProgressView().controlSize(.small)}
                else {Image(systemName:model.dirty.isEmpty ? (model.success ? "checkmark.circle":"exclamationmark.circle") : "circle.lefthalf.filled").foregroundColor(model.dirty.isEmpty && model.success ? accent:.orange)}
                VStack(alignment:.leading,spacing:3) {
                    if !model.dirty.isEmpty {Text("\(model.dirty.count) 项设置待保存").font(.system(size:12,weight:.medium))}
                    Text(model.busy || model.dirty.isEmpty ? model.message : (model.success ? "保存后应用到机器人。":model.message))
                        .font(.system(size:11)).foregroundColor(model.success ? quiet:.orange).lineLimit(2)
                }
                Spacer(minLength:4)
                if !model.dirty.isEmpty {
                    if page == .robot {
                        Button("撤销"){model.discard()}.buttonStyle(.plain).font(.system(size:12)).foregroundColor(quiet).padding(.horizontal,6).disabled(model.busy)
                        Button("保存设置"){model.save()}.buttonStyle(PanelActionStyle(prominent:true)).disabled(!live || model.busy)
                    } else {
                        Button("查看更改"){storedPage=PanelPage.robot.rawValue}.buttonStyle(PanelActionStyle())
                    }
                } else if !model.busy {
                    Button {model.message=""} label:{Image(systemName:"xmark").font(.system(size:10,weight:.medium)).frame(width:26,height:26)}
                        .buttonStyle(.plain).foregroundColor(quiet).accessibilityLabel("收起状态提示")
                }
            }.padding(.horizontal,24).padding(.vertical,14)
        }.background(Color(red:0.065,green:0.08,blue:0.09))
    }
    private var deviceCard:some View {
        card {
            HStack(alignment:.firstTextBaseline){Text("设备状态").font(.system(size:14,weight:.semibold));Spacer();Text(live ? "刚刚同步" : d == nil ? "等待设备回传" : "上次记录 · 当前不可用").font(.system(size:11)).foregroundColor(live ? accent:Color.orange)}
            HStack(alignment:.firstTextBaseline,spacing:30){
                VStack(alignment:.leading,spacing:7){Text("电量").font(.system(size:11)).foregroundColor(quiet);HStack(alignment:.firstTextBaseline,spacing:5){Text(d.map{$0.battery<0 ? "—":"\($0.battery)%"} ?? "—").font(.system(size:28,weight:.light,design:.rounded));if d?.charging == 1{Image(systemName:"bolt.fill").foregroundColor(accent)}}}
                Spacer()
                VStack(alignment:.leading,spacing:7){Text("充电状态").font(.system(size:11)).foregroundColor(quiet);Text(d.map{$0.charging == 1 ? "正在充电":"未在充电"} ?? "—").font(.system(size:14))}
                Spacer()
                VStack(alignment:.leading,spacing:7){Text("机器人").font(.system(size:11)).foregroundColor(quiet);Text(d.map{$0.resting == 1 ? "正在休息":"醒着"} ?? "—").font(.system(size:14))}
                Spacer()
                VStack(alignment:.leading,spacing:7){Text("固件").font(.system(size:11)).foregroundColor(quiet);Text(d.map{"v\($0.firmware)"} ?? "—").font(.system(size:14,design:.monospaced))}
            }.opacity(live ? 1:0.45)
        }
    }
    private var focusCard:some View {
        card {
            HStack{Text("番茄钟").font(.system(size:14,weight:.semibold));Spacer();Text(model.presenceTitle).font(.system(size:11)).foregroundColor(quiet)}
            Text(model.focusTitle).font(.system(size:model.focusActive ? 28:17,weight:.light,design:.rounded)).monospacedDigit().foregroundColor(model.focusAvailable ? accent:quiet)
            HStack(spacing:14){
                Picker("时长",selection:$model.focusMinutes){Text("15 分钟").tag(15);Text("25 分钟").tag(25);Text("45 分钟").tag(45)}.labelsHidden().pickerStyle(.segmented).frame(maxWidth:300).disabled(model.focusActive || model.focusNextAvailable || model.busy)
                Spacer()
                if model.focusActive {
                    if model.focusPauseAvailable {Button(model.focusPaused ? "继续":"暂停"){model.focus(model.focusPaused ? "resume":"pause")}.disabled(model.busy)}
                    Button("结束"){model.focus("stop")}.disabled(!model.focusAvailable || model.busy)
                }
                else if model.focusNextAvailable {
                    Button("下一轮"){model.focus("next")}.disabled(model.busy)
                    Button("结束"){model.focus("stop")}.disabled(model.busy)
                }
                else {Button("开始专注"){model.focus("start")}.buttonStyle(PanelActionStyle(prominent:true)).disabled(!model.focusAvailable || model.busy)}
            }
            DisclosureGroup("计时说明") {
                Text(["0.44","0.45","0.46","0.47","0.48"].contains(model.device?.firmware ?? "") ? "专注到时自动休息 5 分钟，休息结束点下一轮。两段均可暂停；结束取消整个循环。机器人重启只清除当前计时。" : "静音计时，关闭控制台或短暂断连仍会继续；机器人重启后清除。").font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)
                Text("今日专注按 Mac 的本地日期累计；完成一轮才计入轮数，提前结束也累计已专注的时间，暂停和休息时间不计入。").font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true).padding(.top,6)
            }.font(.system(size:11)).tint(quiet)
            Divider().overlay(Color.white.opacity(0.07))
            HStack {
                Text("今日专注").font(.system(size:12)).foregroundColor(quiet)
                Spacer()
                Text(model.focusSummaryTitle).font(.system(size:16,weight:.medium,design:.rounded)).monospacedDigit()
                    .foregroundColor(model.state?.companionFresh() == true ? accent:quiet)
            }
            if model.companion?.summary_save_error == 1 {
                Text("专注记录尚未保存，设备正在重试。").font(.system(size:11)).foregroundColor(.orange)
            }
        }
    }
    private var noteCard:some View {
        card {
            HStack{Text("桌面便签").font(.system(size:14,weight:.semibold));Spacer();Text(model.noteStatus).font(.system(size:11)).foregroundColor(quiet)}
            TextField("例如：下班记得带充电器",text:Binding(get:{model.noteDraft},set:{model.editNote($0)})).textFieldStyle(.roundedBorder).disabled(model.busy)
            HStack {
                Text("\(model.noteDraft.unicodeScalars.count) / 32 字 · 中文、英文、数字和常用标点").font(.system(size:11)).foregroundColor(model.noteDraft.isEmpty || PanelModel.validNote(model.noteDraft) ? quiet:.orange)
                Spacer()
                if model.note?.state=="active" {Button("收起"){model.sendNote("done")}.disabled(!model.noteAvailable || model.busy)}
                if model.note?.state=="done" && !model.noteDirty {Button("重新贴上"){model.sendNote("restore")}.disabled(!model.noteAvailable || model.busy)}
                if model.noteDirty {Button("重读便签"){model.discardNote()}.disabled(!model.noteAvailable || model.busy)}
                Button(model.noteConflict ? "覆盖为这条" : "贴到机器人"){model.sendNote("set")}.buttonStyle(PanelActionStyle(prominent:true)).disabled(!model.noteAvailable || model.busy || !PanelModel.validNote(model.noteDraft))
            }
            if model.noteConflict,let current=model.note {Text("机器人当前\(current.state=="done" ? "已收起":"显示")：\(current.text.isEmpty ? "没有便签":current.text)").font(.system(size:12)).foregroundColor(.orange).fixedSize(horizontal:false,vertical:true)}
            Text(model.noteMessage.isEmpty ? "最多32字，保存后断开 Mac 也会保留。" : model.noteMessage).font(.system(size:11)).foregroundColor(model.noteSuccess ? quiet:.orange).fixedSize(horizontal:false,vertical:true)
        }
    }
    private var petCard:some View {
        card {
            if live && (d?.motion_state == "unavailable" || d?.motion_state == "checking") {
                HStack(spacing:14) {
                    VStack(alignment:.leading,spacing:5) {
                        Text(PetStatus.title(d,live:live)).font(.system(size:14,weight:.semibold)).foregroundColor(.orange)
                        Text(PetStatus.detail(d,live:live)).font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)
                    }
                    Spacer(minLength:0)
                    if d?.motion_recoverable == 1 || d?.motion_state == "checking" {
                        Button(model.busy || d?.motion_state == "checking" ? "检查中…" : "恢复动作"){model.recoverMotion()}
                            .buttonStyle(.bordered).disabled(model.busy || !model.canRecoverMotion)
                    }
                }
                Text("通过蓝牙检查，不重启、不试点头；恢复前先保存故障记录。").font(.system(size:10)).foregroundColor(quiet)
                Divider()
            }
            PanelFold("摸头与动作状态",summary:PetStatus.title(d,live:live),icon:"hand.raised") {
                Text(PetStatus.title(d,live:live)).font(.system(size:15,weight:.medium)).foregroundColor(live && d?.motion_state != "unavailable" && d?.motion_state != "sensor" ? accent:.orange)
                Text(PetStatus.latest(d,live:live)).font(.system(size:12)).fixedSize(horizontal:false,vertical:true)
                Text(PetStatus.detail(d,live:live)).font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)
                DisclosureGroup("为什么有时只害羞、不点头？") {
                    Text("摸头需持续约 0.12 秒；一直按着只触发一次，抬手约 0.4 秒才能再次触发。两次点头开始至少间隔 5 秒。\n\n触屏时让开；舵机位置、负载或回执异常时停止驱动，无法卸力时请求断电。这些是自定义固件的限制，不代表已确认硬件损坏。\n\n状态约每 2 秒回传；最近一次记录保留到下一次摸头或机器人重启。查看状态不会触发动作。")
                        .font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true).padding(.top,6)
                }.font(.system(size:11)).tint(quiet)
            }.font(.system(size:12)).tint(quiet)
        }
    }
    private var pendingCard:some View {
        card {
            HStack{Text("待你回应").font(.system(size:14,weight:.semibold));Spacer();Text("\(model.pending.count) 项").font(.system(size:11)).foregroundColor(quiet)}
            if model.pending.isEmpty {
                Text(model.state?.pendingFresh == true ? "当前 Top 8 中没有待回应的会话" : "等待同步服务更新任务状态").font(.system(size:12)).foregroundColor(quiet)
            }
            ForEach(model.pending){task in
                HStack(alignment:.center,spacing:16){
                    VStack(alignment:.leading,spacing:5){
                        Text(task.title).font(.system(size:13,weight:.medium)).lineLimit(2)
                        Text(task.reason).font(.system(size:11)).foregroundColor(.orange).lineLimit(2)
                    }
                    Spacer(minLength:0)
                    Button(model.openingThreadID == task.id ? "正在打开…" : "在 Codex 打开"){model.openPending(task)}.disabled(model.openingThreadID != nil)
                }
            }
        }
    }
    private func preference(_ key:String,_ value:Binding<Int>)->Binding<Int> {
        Binding(get:{value.wrappedValue},set:{value.wrappedValue=$0;model.edited(key)})
    }
    private func preference(_ key:String,_ value:Binding<Bool>)->Binding<Bool> {
        Binding(get:{value.wrappedValue},set:{value.wrappedValue=$0;model.edited(key)})
    }
    private func skinChoice(_ value:Int,_ title:String,_ subtitle:String)->some View {
        Button {model.skin=value;model.edited("skin")} label:{
            HStack(spacing:16) {
                PanelFacePreview(cat:value==1).frame(width:84,height:64)
                VStack(alignment:.leading,spacing:5) {Text(title).font(.system(size:14,weight:.medium));Text(subtitle).font(.system(size:11)).foregroundColor(quiet)}
                Spacer(minLength:0)
                Image(systemName:model.skin==value ? "checkmark.circle.fill":"circle").font(.system(size:15)).opacity(model.skin==value ? 1:0.35)
            }.padding(13).frame(maxWidth:.infinity)
        }.buttonStyle(PanelOptionStyle(selected:model.skin==value))
            .accessibilityLabel("外观皮肤：\(title)").accessibilityValue(model.skin==value ? "已选中":"未选中")
            .disabled(d?.skin == nil)
    }
    private var settingsCard:some View {
        VStack(alignment:.leading,spacing:14) {
            HStack(spacing:6) {
                Circle().fill(!model.dirty.isEmpty ? Color.orange:live ? accent:quiet).frame(width:5,height:5)
                Text(model.settingsHint).font(.system(size:11)).foregroundColor(!model.dirty.isEmpty ? .orange:quiet)
            }.padding(.horizontal,3)
            card {
                PanelSectionHeading(title:"它的模样",detail:"选一个喜欢的表情，保存后应用。",icon:"face.smiling")
                HStack(spacing:10) {skinChoice(0,"默认","极简线条");skinChoice(1,"猫系","小耳朵 · 弯弯眼")}
                Divider().overlay(Color.white.opacity(0.04))
                HStack {Text("屏幕亮度").font(.system(size:12));Spacer();Image(systemName:"sun.max").font(.system(size:12)).foregroundColor(quiet)}
                PanelChoices(labels:["柔和","标准","明亮","很亮"],selection:preference("light",$model.light),name:"屏幕亮度")
                Text("这里只预览外观选择，亮度仍以机器人屏幕为准。").font(.system(size:10)).foregroundColor(quiet)
            }
            card {
                PanelSectionHeading(title:"相处方式",detail:"安静陪伴，按你的节奏。",icon:"sparkle")
                PanelToggleRow(title:"摸头时轻轻点头",detail:"关闭后仍会害羞，也能唤醒。",value:preference("pet",$model.pet))
                Divider().overlay(Color.white.opacity(0.04))
                PanelFold("休息与日常",summary:["1 分钟后休息","3 分钟后休息","5 分钟后休息","10 分钟后休息","保持清醒"][model.rest],icon:"moon") {
                    Text("空闲多久后休息").font(.system(size:12))
                    PanelChoices(labels:["1 分钟","3 分钟","5 分钟","10 分钟","不休息"],selection:preference("rest",$model.rest),name:"空闲后休息")
                    Text("休息时闭眼，屏幕亮度保持不变。").font(.system(size:11)).foregroundColor(quiet)
                    Group {
                        Text("日常表情").font(.system(size:12))
                        PanelChoices(labels:["低调","自然","活泼"],selection:preference("daily",$model.daily),name:"日常表情频率")
                        Text(["空闲约 3–5 分钟后，偶尔变换小表情。","空闲约 45–90 秒后，自然地变换小表情。","空闲约 20–40 秒后，多一些小表情。"][model.daily]).font(.system(size:11)).foregroundColor(quiet)
                        PanelToggleRow(title:"锁屏后休息",value:preference("away_rest",$model.awayRest))
                        PanelToggleRow(title:"回来迎接",value:preference("greeting",$model.greeting))
                        PanelToggleRow(title:"摸头后亲昵",detail:"关闭后，直接摸头的表情和动作仍然保留。",value:preference("affection",$model.affection))
                    }.disabled(!model.companionSettingsAvailable)
                    if !model.companionSettingsAvailable {Text("连接 v0.35 或更新固件后可调整日常陪伴。").font(.system(size:11)).foregroundColor(.orange)}
                }
                Divider().overlay(Color.white.opacity(0.04))
                PanelFold("提醒动作",summary:"\([model.waitMotion,model.doneMotion,model.focusMotion].filter{$0}.count) 项已开启",icon:"bell") {
                    PanelToggleRow(title:"待你回应时轻点头",value:preference("wait_motion",$model.waitMotion)).disabled(d?.wait_motion == nil)
                    PanelToggleRow(title:"任务完成时轻点头",value:preference("done_motion",$model.doneMotion)).disabled(d?.done_motion == nil)
                    PanelToggleRow(title:"番茄钟到时轻点头",value:preference("focus_motion",$model.focusMotion)).disabled(d?.focus_motion == nil)
                    Text(d?.wait_motion == nil ? "连接支持提醒动作的新固件后可调整。":"开启后轻点头一次；触摸时避让，两次至少间隔 20 秒。设置开关本身不触发动作。").font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)
                }
            }
        }.disabled(!live || model.busy)
    }
    private var connectionCard:some View {
        card {
            HStack{Text("同步检查").font(.system(size:14,weight:.semibold));Spacer();Button(model.busy ? "正在检查…":"立即检查"){model.issue(["action":"inspect"],saving:false)}.disabled(model.busy)}
            HStack{Text("连接异常时可在这里恢复").font(.system(size:11)).foregroundColor(quiet);Spacer();Button(model.recoveryTitle){model.recover()}.disabled(model.busy || model.state?.installed != true)}
            diagnostic("Mac 同步服务",model.state?.paused == true ? "已暂停" : model.state?.fresh == true ? "运行中":"未就绪",model.state?.fresh == true && model.state?.paused != true)
            diagnostic("机器人连接",model.state?.connected() == true ? model.state?.bridge?.transport == "ble" ? "蓝牙已连接":"USB 已连接":"等待连接",model.state?.connected() == true)
            diagnostic("Codex 任务数据",model.state?.fresh == true && model.state?.bridge?.data_source == "ok" ? "可读取":"暂不可读取",model.state?.fresh == true && model.state?.bridge?.data_source == "ok")
            diagnostic("设备状态回传",live ? "正常":"等待新状态",live)
            if let b=model.state?.bridge,model.state?.fresh == true{Text("\(b.tasks) 项任务   ·   \(b.running) 项运行   ·   \(b.needs_input) 项待回应").font(.system(size:11)).foregroundColor(quiet)}
            Divider().overlay(Color.white.opacity(0.1))
            HStack(alignment:.center){
                VStack(alignment:.leading,spacing:5){
                    Text(model.state?.paused == true ? "暂停期间不采集异常" : model.state?.fresh != true ? "等待服务恢复留档" : model.state?.bridge?.diagnostics_ok == true ? "异常自动留档已开启" : model.state?.bridge?.diagnostics_ok == false ? "异常留档暂不可写入" : "当前版本尚未回传留档状态").font(.system(size:12))
                    Text("最多约 384 KiB · 不含聊天正文和密钥").font(.system(size:11)).foregroundColor(quiet)
                }
                Spacer()
                Button(model.exporting ? "正在导出…":"导出诊断"){model.exportDiagnostics()}.disabled(model.exporting || model.state?.installed != true)
            }
            if !model.diagnosticMessage.isEmpty {
                HStack(alignment:.top){Text(model.diagnosticMessage).font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true);Spacer();if let url=model.diagnosticURL{Button("在 Finder 显示"){NSWorkspace.shared.activateFileViewerSelecting([url])}}}
            }

        }
    }
}

final class VoiceFloatingPanel:NSPanel {
    override var canBecomeKey:Bool {true}
    override var canBecomeMain:Bool {false}
    override func cancelOperation(_ sender:Any?) {performClose(sender)}
}

final class AppDelegate:NSObject,NSApplicationDelegate,NSWindowDelegate {
    var window:NSWindow?
    var voicePanel:VoiceFloatingPanel?
    var statusItem:NSStatusItem?
    var hotkey:VoiceHotkey?
    let model=PanelModel()
    let voice=VoiceCompanion()
    let vision=LocalVision()
    func applicationDidFinishLaunching(_ notification:Notification){
        model.onTaskSnapshot = { [weak voice] snapshot in voice?.acceptTaskSnapshot(snapshot) }
        voice.onLocalCommand = { [weak model] command,completion in
            guard let model=model else {completion(VoiceCommandOutcome(ok:false,message:"控制台暂不可用。"));return}
            model.executeVoiceCommand(command,completion:completion)
        }
        voice.onHotkeyChanged = { [weak self] in self?.configureHotkey() }
        voice.onPresentVoiceMode = { [weak self] in self?.openVoicePanel() }
        let view=PanelView(model:model,voice:voice,vision:vision)
        let hosting=NSHostingView(rootView:view)
        let window=NSWindow(contentRect:NSRect(x:0,y:0,width:620,height:780),styleMask:[.titled,.closable,.miniaturizable],backing:.buffered,defer:false)
        if let url=Bundle.main.url(forResource:"Weiguang",withExtension:"icns"),let icon=NSImage(contentsOf:url){NSApp.applicationIconImage=icon}
        window.title="微光控制台";window.titlebarAppearsTransparent=true;window.backgroundColor=NSColor(calibratedRed:0.055,green:0.065,blue:0.075,alpha:1);window.contentView=hosting;window.center();window.setFrameAutosaveName("WeiguangPanel");self.window=window
        window.delegate=self;window.isReleasedWhenClosed=false
        installMenus();configureHotkey()
        window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true);model.start();voice.start()
    }
    func configureHotkey() {
        hotkey?.unregister();hotkey=nil
        guard voice.hotkeyEnabled else {voice.hotkeyStatus="快捷键已关闭；可从菜单栏打开语音。";return}
        let key=VoiceHotkey { [weak self] in self?.toggleVoice() }
        hotkey=key
        voice.hotkeyStatus=key.register() ? "⌃⌥空格 · 呼出或关闭语音浮窗" : "⌃⌥空格注册失败，可能已被占用；可用菜单栏入口。"
    }
    func installMenus() {
        let main=NSMenu(),root=NSMenuItem();main.addItem(root)
        let application=NSMenu();root.submenu=application
        let about=NSMenuItem(title:"关于微光控制台",action:#selector(showAbout),keyEquivalent:"");about.target=self;application.addItem(about)
        application.addItem(.separator())
        let show=NSMenuItem(title:"显示控制台",action:#selector(showPanel),keyEquivalent:"0");show.target=self;application.addItem(show)
        let voiceEntry=NSMenuItem(title:"开始／结束语音",action:#selector(toggleVoice),keyEquivalent:"");voiceEntry.target=self;application.addItem(voiceEntry)
        application.addItem(.separator())
        application.addItem(NSMenuItem(title:"隐藏微光控制台",action:#selector(NSApplication.hide(_:)),keyEquivalent:"h"))
        application.addItem(.separator())
        let quit=NSMenuItem(title:"退出微光",action:#selector(quitApp),keyEquivalent:"q");quit.target=self;application.addItem(quit)
        let editRoot=NSMenuItem(title:"编辑",action:nil,keyEquivalent:"");main.addItem(editRoot)
        let edit=NSMenu(title:"编辑");editRoot.submenu=edit
        for (title,action,key) in [("撤销","undo:","z"),("剪切","cut:","x"),("复制","copy:","c"),("粘贴","paste:","v"),("全选","selectAll:","a")] {
            edit.addItem(NSMenuItem(title:title,action:NSSelectorFromString(action),keyEquivalent:key))
        }
        let windowRoot=NSMenuItem(title:"窗口",action:nil,keyEquivalent:"");main.addItem(windowRoot)
        let windows=NSMenu(title:"窗口");windowRoot.submenu=windows
        windows.addItem(NSMenuItem(title:"最小化",action:#selector(NSWindow.performMiniaturize(_:)),keyEquivalent:"m"))
        windows.addItem(NSMenuItem(title:"关闭窗口",action:#selector(NSWindow.performClose(_:)),keyEquivalent:"w"))
        NSApp.windowsMenu=windows
        NSApp.mainMenu=main
        let item=NSStatusBar.system.statusItem(withLength:NSStatusItem.squareLength)
        item.button?.image=NSImage(systemSymbolName:"waveform",accessibilityDescription:"微光")
        item.button?.image?.isTemplate=true;item.button?.toolTip="微光 · ⌃⌥空格开始或结束语音"
        let menu=NSMenu()
        for (title,selector) in [("打开微光控制台",#selector(showPanel)),("开始／结束语音",#selector(toggleVoice))] {
            let entry=NSMenuItem(title:title,action:selector,keyEquivalent:"");entry.target=self;menu.addItem(entry)
        }
        menu.addItem(.separator())
        let exit=NSMenuItem(title:"退出微光",action:#selector(quitApp),keyEquivalent:"");exit.target=self;menu.addItem(exit)
        item.menu=menu;statusItem=item
    }
    @objc func showAbout(){NSApp.orderFrontStandardAboutPanel(options:[.applicationName:"微光控制台",.credits:NSAttributedString(string:"Chan 的桌面伙伴\n关闭窗口后仍可从菜单栏打开；退出控制台不停止机器人任务同步。")])}
    @objc func showPanel(){window?.deminiaturize(nil);window?.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true)}
    func openVoicePanel() {
        if voicePanel == nil {
            let panel=VoiceFloatingPanel(contentRect:NSRect(x:0,y:0,width:400,height:520),
                styleMask:[.titled,.closable,.nonactivatingPanel],backing:.buffered,defer:false)
            panel.title="微光语音";panel.titleVisibility = .hidden;panel.titlebarAppearsTransparent=true
            panel.backgroundColor=NSColor(calibratedRed:0.04,green:0.055,blue:0.065,alpha:1)
            panel.isReleasedWhenClosed=false;panel.delegate=self
            panel.level = .floating;panel.hidesOnDeactivate=false;panel.isFloatingPanel=true
            panel.collectionBehavior=[.canJoinAllSpaces,.fullScreenAuxiliary]
            panel.becomesKeyOnlyIfNeeded=false;panel.isMovableByWindowBackground=true;panel.worksWhenModal=true
            panel.contentView=NSHostingView(rootView:VoiceModeView(voice:voice,compact:true,onEnd:{[weak self] in self?.closeVoicePanel()}))
            panel.setFrameAutosaveName("WeiguangVoicePanel")
            if !panel.setFrameUsingName("WeiguangVoicePanel"),let screen=NSScreen.screens.first(where:{$0.frame.contains(NSEvent.mouseLocation)}) ?? NSScreen.main {
                let frame=screen.visibleFrame
                panel.setFrameTopLeftPoint(NSPoint(x:frame.maxX-panel.frame.width-24,y:frame.maxY-48))
            }
            voicePanel=panel
        }
        // 先让独立窗口可见，再沿用现有耳机／权限保护进入语音；不把控制台一起带出。
        window?.orderOut(nil)
        voicePanel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps:true)
        if !voice.voiceMode.visible {voice.startVoiceMode()}
    }
    func closeVoicePanel() {
        voice.exitVoiceMode()
        voicePanel?.orderOut(nil)
    }
    @objc func toggleVoice() {
        if voicePanel?.isVisible == true || voice.voiceMode.visible {closeVoicePanel()}
        else {openVoicePanel()}
    }
    @objc func quitApp(){NSApp.terminate(nil)}
    func windowShouldClose(_ sender:NSWindow)->Bool {
        if sender === voicePanel {closeVoicePanel();return false}
        closeVoicePanel();voice.cancel("控制台已收起，麦克风已关闭；可从菜单栏或快捷键再次打开。")
        vision.stop("控制台已收起，视觉互动已关闭。");sender.orderOut(nil);return false
    }
    func applicationShouldHandleReopen(_ sender:NSApplication,hasVisibleWindows flag:Bool)->Bool{showPanel();return true}
    func applicationWillTerminate(_ notification:Notification){hotkey?.unregister();voice.stop();vision.stop()}
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool{false}
}
@main struct Main {
    static func main(){
        if CommandLine.arguments.contains("--music-output") {print(HeadphoneHardware.current().isAirPods ? "airpods":"protected");return}
        if CommandLine.arguments.contains("--music-control") {musicControl();return}
        if CommandLine.arguments.contains("--vision-analyze") {localVisionAnalyzer();return}
        if CommandLine.arguments.contains("--voice-inspect") {
            let r=HeadphoneHardware.current()
            let result:[String:Any]=["is_airpods":r.isAirPods,"name":r.name,"manufacturer":r.manufacturer,"bluetooth":r.bluetooth,"alive":r.alive,"output_channels":r.outputChannels]
            print(String(data:try! JSONSerialization.data(withJSONObject:result,options:[.sortedKeys]),encoding:.utf8)!);return
        }
        if CommandLine.arguments.contains("--voice-self-test") {voiceGateSelfTest();voiceSettingsSelfTest();voiceGreetingSelfTest();voiceTaskNoticeSelfTest();voiceConversationSelfTest();voiceFaceSelfTest();voiceMicrophoneSelfTest();voiceModeSelfTest();voiceCommandsSelfTest();voiceHotkeySelfTest();print("voice gate, render, settings, greeting and conversation tests passed");return}
        if CommandLine.arguments.contains("--voice-demo") || CommandLine.arguments.contains("--voice-silence-test") || CommandLine.arguments.contains("--voice-cancel-test") {
            let voice=VoiceCompanion(persist:false);voice.start();voice.adoptCurrent();voice.setEnabled(true)
            let cancelTest=CommandLine.arguments.contains("--voice-cancel-test")
            voice.request(demo:true,silenceOnly:!CommandLine.arguments.contains("--voice-demo"))
            if cancelTest {
                let until=Date().addingTimeInterval(0.2)
                while Date()<until {RunLoop.current.run(until:Date().addingTimeInterval(0.02))}
                voice.setEnabled(false);voice.setEnabled(true)
                voice.lastCancellationCheck()
            }
            let until=Date().addingTimeInterval(95)
            while voice.busy && Date()<until {RunLoop.current.run(until:Date().addingTimeInterval(0.05))}
            var result=voice.lastResult;result["message"]=voice.message
            result["route_is_airpods"]=voice.route.isAirPods;result["watcher_healthy"]=voice.watcher?.healthy ?? false
            result["listener_errors"]=voice.watcher?.registrationErrors ?? [:]
            result["listener_count"]=voice.watcher?.registrations.count ?? 0
            voice.stop();print(String(data:try! JSONSerialization.data(withJSONObject:result,options:[.sortedKeys]),encoding:.utf8)!);return
        }
        if CommandLine.arguments.contains("--self-test") {
            let d=Device(firmware:"0.25",page:"home",battery:100,charging:0,resting:0,brightness:70,light:1,rest:1,pet:1,save_error:0,uptime:1,sync_age:1)
            let b=BridgeState(connection:"connected",data_source:"ok",transport:"ble",tasks:8,running:1,needs_input:0,device_at:Date().timeIntervalSince1970,device_supported:true,device:d)
            var s=PanelState(installed:true,paused:false,loaded:true,fresh:true,bridge:b)
            precondition(s.deviceFresh());s.paused=true;precondition(!s.deviceFresh());s.paused=false;s.fresh=false;precondition(!s.deviceFresh());s.fresh=true;s.bridge?.device_at=Date().timeIntervalSince1970-30;precondition(!s.deviceFresh());s.bridge?.device_at=Date().timeIntervalSince1970+30;precondition(!s.deviceFresh())
            // Python status JSON -> 面板 -> 语音观察器；缺字段的旧桥接保持兼容且不播报。
            precondition(s.taskVoiceSnapshot == nil)
            let noticeJSON=Data("{\"installed\":true,\"paused\":false,\"fresh\":true,\"bridge\":{\"connection\":\"waiting_ble\",\"data_source\":\"ok\",\"tasks\":1,\"running\":0,\"needs_input\":0,\"pid\":123,\"last_good_at\":100,\"completion_events\":[{\"id\":\"00000000-0000-4000-8000-000000000001\",\"title\":\"测试任务\",\"key\":\"aaaaaaaaaaaaaaaa\",\"completed_at\":99}]}}".utf8)
            var noticeState=try! JSONDecoder().decode(PanelState.self,from:noticeJSON)
            let noticeModel=PanelModel();var receivedSnapshot:VoiceTaskSnapshot?
            noticeModel.onTaskSnapshot={receivedSnapshot=$0};noticeModel.accept(noticeState)
            precondition(receivedSnapshot?.events.first?.title=="测试任务" && receivedSnapshot?.pid==123)
            noticeState.paused=true;noticeModel.accept(noticeState);precondition(receivedSnapshot == nil)
            noticeState.paused=false;noticeState.bridge?.data_source="unavailable"
            noticeModel.accept(noticeState);precondition(receivedSnapshot == nil)
            let model=PanelModel();var device=d;device.wait_motion=1;device.done_motion=0
            model.acceptDevice(device);precondition(model.waitMotion && !model.doneMotion)
            model.waitMotion=false;model.edited("wait_motion");model.acceptDevice(device);precondition(!model.waitMotion)
            model.dirty.removeAll();device.wait_motion=nil;model.acceptDevice(device);precondition(!model.waitMotion)
            model.state=s;model.state?.paused=true;precondition(model.recoveryTitle=="恢复同步")
            model.state?.paused=false;model.state?.fresh=false;precondition(model.recoveryTitle=="启动同步")
            model.state?.fresh=true;precondition(model.recoveryTitle=="重新连接")
            model.message=PanelModel.recoveryText("synced");s.paused=true;model.accept(s)
            precondition(model.message != PanelModel.recoveryText("synced"))
            let data=Data("{\"ok\":false,\"outcome\":\"waiting_device\"}".utf8)
            precondition((try! JSONDecoder().decode(RecoveryReply.self,from:data)).ok == false)
            // 两端编辑同一份偏好：保留未保存草稿，接收其余字段，拒绝旧回执。
            var synced=s;synced.paused=false;synced.fresh=true
            synced.bridge?.device=device;synced.bridge?.device_at=Date().timeIntervalSince1970-2
            let linked=PanelModel();linked.accept(synced)
            linked.light=3;linked.edited("light");precondition(linked.dirty==["light"])
            var robot=device;robot.rest=2;robot.pet=0;robot.light=0;robot.wait_motion=1;robot.done_motion=1
            var newer=synced;newer.bridge?.device=robot;newer.bridge?.device_at=Date().timeIntervalSince1970-1
            linked.accept(newer)
            precondition(linked.light==3 && linked.rest==2 && !linked.pet && linked.waitMotion && linked.doneMotion)
            precondition(linked.dirty==["light"])
            linked.accept(synced);precondition(linked.rest==2 && !linked.pet) // 旧状态不能倒退。
            linked.light=0;linked.edited("light");precondition(linked.dirty.isEmpty)
            linked.rest=4;linked.edited("rest");robot.rest=4
            linked.acceptReply(ControlReply(ok:true,device:robot,device_at:Date().timeIntervalSince1970))
            precondition(linked.dirty.isEmpty && linked.rest==4)
            linked.accept(newer);precondition(linked.rest==4)
            linked.light=2;linked.edited("light");linked.discard();precondition(linked.light==0 && linked.dirty.isEmpty)
            linked.light=2;linked.edited("light");robot.light=2;robot.save_error=1
            linked.acceptDevice(robot);precondition(linked.dirty.contains("light")) // 保存失败不能丢失可重试草稿。
            let task=PendingTask(id:"00000000-0000-4000-8000-000000000001",title:"提问",reason:"待答：提醒方式")
            precondition(task.codexURL?.absoluteString == "codex://threads/00000000-0000-4000-8000-000000000001?hostId=local")
            precondition(PendingTask(id:"https://example.com",title:"",reason:"").codexURL == nil)
            linked.state?.bridge?.pending_tasks=[task];linked.state?.fresh=true;linked.state?.paused=false
            linked.state?.bridge?.data_source="ok";linked.state?.bridge?.connection="waiting_ble"
            precondition(linked.pending.count==1) // 查会话不要求机器人在线。
            linked.state?.bridge?.data_source="unavailable";precondition(linked.pending.isEmpty)
            linked.state?.bridge?.data_source="ok";linked.state?.fresh=false;precondition(linked.pending.isEmpty)
            var petDevice=d;petDevice.firmware="0.30";petDevice.motion_state="ready";petDevice.motion_reason="none"
            petDevice.pet_event=0
            precondition(PetStatus.title(petDevice,live:true)=="可响应摸头")
            precondition(PetStatus.latest(petDevice,live:true).contains("尚未记录"))
            petDevice.motion_state="cooldown";petDevice.pet_cooldown_ms=1250
            petDevice.pet_event=1;petDevice.pet_age=3;petDevice.pet_result="skipped";petDevice.pet_reason="cooldown"
            precondition(PetStatus.title(petDevice,live:true).contains("2 秒"))
            precondition(PetStatus.latest(petDevice,live:true).contains("本次未点头"))
            precondition(PetStatus.detail(petDevice,live:true).contains("不足 5 秒"))
            petDevice.motion_state="unavailable";petDevice.motion_reason="load-high"
            precondition(PetStatus.detail(petDevice,live:true).contains("负载"))
            precondition(PetStatus.title(petDevice,live:false).contains("不可判断"))
            precondition(PetStatus.latest(petDevice,live:false).contains("上次记录"))
            precondition(PetStatus.title(d,live:true).contains("尚无动作反馈"))
            var recoveryState=synced;petDevice.motion_state="unavailable";petDevice.firmware="0.48";petDevice.motion_recoverable=1;petDevice.motion_fault_id=123
            recoveryState.bridge?.device=petDevice;recoveryState.bridge?.device_at=Date().timeIntervalSince1970
            let recovering=PanelModel();recovering.accept(recoveryState);precondition(recovering.canRecoverMotion)
            recoveryState.bridge?.device_at=Date().timeIntervalSince1970-60;let staleRecovery=PanelModel();staleRecovery.accept(recoveryState);precondition(!staleRecovery.canRecoverMotion)
            petDevice.motion_state="checking";precondition(PetStatus.title(petDevice,live:true).contains("正在检查"))
            precondition(PanelModel.motionRecoveryText("recovered").contains("故障记录已保留"))
            precondition(PanelModel.motionRecoveryText("load-high").contains("仍保持停用"))
            let exportRoot=URL(fileURLWithPath:"/tmp/Weiguang")
            precondition(PanelModel.diagnosticFile("/tmp/Weiguang/diagnostics/微光-诊断-20261010-test.zip",root:exportRoot) != nil)
            precondition(PanelModel.diagnosticFile("/tmp/Weiguang/diagnostics/../../other.zip",root:exportRoot) == nil)
            precondition(PanelModel.diagnosticFile("/tmp/Weiguang/diagnostics/key.txt",root:exportRoot) == nil)
            let clock=Date().timeIntervalSince1970
            let companion=Companion(presence:"awake",focus_state:"running",remaining:1500,total:1500,welcome:0)
            precondition(companion.seconds(at:clock+3,received:clock)==1497)
            precondition(companion.seconds(at:clock+2000,received:clock)==0)
            var focusState=synced;focusState.bridge?.device?.firmware="0.34"
            focusState.bridge?.device_at=clock;focusState.bridge?.companion=companion;focusState.bridge?.companion_at=clock
            let focused=PanelModel();focused.accept(focusState);precondition(focused.focusAvailable && focused.focusRunning)
            precondition(!focusState.companionFresh(at:clock+8));focusState.paused=true;precondition(!focusState.companionFresh());focusState.paused=false
            let pausedClock=Companion(presence:"awake",focus_state:"paused",remaining:900,total:1500,welcome:0)
            precondition(pausedClock.seconds(at:clock+100,received:clock)==900)
            var pausedState=focusState;pausedState.bridge?.device?.firmware="0.40"
            pausedState.bridge?.companion=pausedClock
            let pausedPanel=PanelModel();pausedPanel.accept(pausedState)
            precondition(pausedPanel.focusPaused && pausedPanel.focusActive && pausedPanel.focusPauseAvailable)
            precondition(pausedPanel.focusTitle.contains("15:00") && pausedPanel.focusTitle.contains("已暂停"))
            let stopped=Companion(presence:"awake",focus_state:"off",remaining:0,total:0,welcome:0)
            focused.acceptReply(ControlReply(ok:true,companion:stopped,companion_at:clock+1))
            focused.accept(focusState);precondition(focused.companion?.focus_state=="off")
            focused.acceptReply(ControlReply(ok:true,companion:companion,companion_at:clock));precondition(!focused.focusRunning)
            focusState.bridge?.companion=Companion(presence:"awake",focus_state:"running",remaining:880,total:900,welcome:0)
            let reopened=PanelModel();reopened.accept(focusState);precondition(reopened.focusMinutes==15)
            for version in ["0.41","0.42","0.43","0.44"] {
                var supported=pausedState;supported.bridge?.device?.firmware=version
                let checked=PanelModel();checked.accept(supported)
                precondition(checked.focusAvailable && checked.focusPauseAvailable)
            }
            var restState=pausedState;restState.bridge?.device?.firmware="0.44"
            let restClock=Companion(presence:"awake",focus_state:"paused",remaining:123,total:300,welcome:0,stage:"rest",focus_total:900,round:2)
            restState.bridge?.companion=restClock
            let restPanel=PanelModel();restPanel.accept(restState)
            precondition(restPanel.focusAvailable && restPanel.focusPaused && restPanel.focusMinutes==15)
            precondition(restPanel.focusTitle.contains("休息") && restPanel.focusTitle.contains("第 2 轮") && !restPanel.focusNextAvailable)
            let finishedRest=Companion(presence:"awake",focus_state:"done",remaining:0,total:300,welcome:0,stage:"rest",focus_total:900,round:2)
            restPanel.acceptReply(ControlReply(ok:true,companion:finishedRest,companion_at:Date().timeIntervalSince1970))
            precondition(restPanel.focusNextAvailable && !restPanel.focusActive && restPanel.focusTitle.contains("休息结束"))
            let encoded=try! JSONEncoder().encode(restClock)
            precondition((try! JSONDecoder().decode(Companion.self,from:encoded)).stage=="rest")
            var summaryState=restState;summaryState.bridge?.device?.firmware="0.45"
            var summaryClock=finishedRest
            let calendar=Calendar.current
            let start=calendar.startOfDay(for:Date())
            let day=Int((start.timeIntervalSince1970+Double(TimeZone.current.secondsFromGMT(for:start)))/86400)
            summaryClock.today_day=day;summaryClock.today_seconds=3020;summaryClock.today_rounds=2;summaryClock.summary_save_error=0
            summaryState.bridge?.companion=summaryClock;summaryState.bridge?.companion_at=Date().timeIntervalSince1970
            let summaryModel=PanelModel();summaryModel.accept(summaryState)
            precondition(summaryModel.focusAvailable && summaryModel.focusSummaryTitle=="2 轮 · 50 分钟")
            summaryClock.today_seconds=20;summaryState.bridge?.companion=summaryClock;summaryModel.accept(summaryState)
            precondition(summaryModel.focusSummaryTitle=="2 轮 · 不足 1 分钟")
            summaryClock.today_day=day-1;summaryState.bridge?.companion=summaryClock;summaryModel.accept(summaryState)
            precondition(summaryModel.focusSummaryTitle=="等待今日记录同步")
            var noteState=summaryState;noteState.bridge?.device?.firmware="0.46"
            noteState.bridge?.note=DeskNote(revision:1,state:"active",text:"下班带充电器",save_error:0);noteState.bridge?.note_at=Date().timeIntervalSince1970
            let noteModel=PanelModel();noteModel.accept(noteState)
            precondition(noteModel.noteAvailable && noteModel.noteDraft=="下班带充电器")
            noteModel.editNote("买牛奶")
            noteState.bridge?.note=DeskNote(revision:2,state:"done",text:"下班带充电器",save_error:0)
            noteModel.accept(noteState);precondition(noteModel.noteConflict && noteModel.noteDraft=="买牛奶")
            noteModel.discardNote();precondition(!noteModel.noteDirty && noteModel.noteDraft=="下班带充电器")
            precondition(PanelModel.validNote("今晚 7 点记得带伞！") && PanelModel.validNote(String(repeating:"中",count:32)))
            for invalid in ["", "   ", "🐱", "a\nb", "a\u{202E}b", String(repeating:"中",count:33)]{precondition(!PanelModel.validNote(invalid))}
            precondition(!noteState.noteFresh(at:Date().timeIntervalSince1970+10))
            var companionDevice=device;companionDevice.wait_motion=0;companionDevice.done_motion=0;companionDevice.firmware="0.35";companionDevice.daily=1;companionDevice.away_rest=1;companionDevice.greeting=1;companionDevice.affection=1
            var companionSettings=synced;companionSettings.bridge?.device=companionDevice;companionSettings.bridge?.device_at=Date().timeIntervalSince1970
            let preferences=PanelModel();preferences.accept(companionSettings);precondition(preferences.companionSettingsAvailable)
            preferences.daily=2;preferences.edited("daily");precondition(preferences.dirty==["daily"])
            companionDevice.greeting=0;companionDevice.away_rest=0;companionDevice.affection=0
            preferences.acceptDevice(companionDevice);precondition(preferences.daily==2 && !preferences.greeting && !preferences.awayRest && !preferences.affection)
            precondition(preferences.dirty==["daily"])
            companionDevice.daily=2;preferences.acceptDevice(companionDevice);precondition(preferences.dirty.isEmpty)
            precondition(companionDevice.preferences.count==9)
            var skinDevice=companionDevice;skinDevice.firmware="0.37";skinDevice.skin=1
            var skinState=companionSettings;skinState.bridge?.device=skinDevice
            let skins=PanelModel();skins.accept(skinState);precondition(skins.skin==1 && skinDevice.preferences.count==10)
            skins.skin=0;skins.edited("skin");precondition(skins.dirty==["skin"])
            skinDevice.light=3;skins.acceptDevice(skinDevice);precondition(skins.skin==0 && skins.light==3 && skins.dirty==["skin"])
            skinDevice.skin=0;skins.acceptDevice(skinDevice);precondition(skins.dirty.isEmpty)
            skins.skin=1;skins.edited("skin");skins.discard();precondition(skins.dirty.isEmpty && skins.skin==1)
            var timerDevice=skinDevice;timerDevice.firmware="0.41";timerDevice.focus_motion=1
            let timerModel=PanelModel();timerModel.acceptDevice(timerDevice)
            precondition(timerModel.focusMotion && timerDevice.preferences.count==11)
            timerModel.focusMotion=false;timerModel.edited("focus_motion");precondition(timerModel.dirty==["focus_motion"])
            timerModel.acceptDevice(timerDevice);precondition(!timerModel.focusMotion)
            timerDevice.focus_motion=0;timerModel.acceptDevice(timerDevice);precondition(timerModel.dirty.isEmpty)

            preferences.state?.bridge?.device=device;precondition(!preferences.companionSettingsAvailable)
            print("Panel freshness, bidirectional settings, draft preservation, pending navigation and recovery checks passed");return
        }
        let app=NSApplication.shared;app.setActivationPolicy(.regular);let delegate=AppDelegate();app.delegate=delegate;app.run()
    }
}
