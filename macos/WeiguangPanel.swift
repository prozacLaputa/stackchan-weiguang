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
        if d.motion_state == "unavailable" {return reason(d.motion_reason)+"。请先保留记录排查；反复摸头或切换开关不会重试。"}
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
    var pending_tasks:[PendingTask]?
    var diagnostics_ok:Bool?
    var companion:Companion?, companion_at:Double?, companion_error:String?
    var note:DeskNote?=nil, note_at:Double?=nil, note_error:String?=nil
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
    func companionFresh(at now:Double = Date().timeIntervalSince1970)->Bool {
        guard connected(),let b=bridge,b.companion != nil,b.companion_error == nil,let stamp=b.companion_at else{return false}
        return now-stamp >= 0 && now-stamp < 8
    }
}
struct RecoveryReply:Decodable {var ok:Bool;var outcome:String;var state:PanelState?}
struct ControlReply:Decodable {var ok:Bool;var error:String?;var device:Device?;var device_at:Double?;var companion:Companion?;var companion_at:Double?;var note:DeskNote?=nil;var note_at:Double?=nil}
struct DiagnosticReply:Decodable {var ok:Bool;var path:String?;var events:Int?}
struct OpenTaskReply:Decodable {var ok:Bool;var error:String?;var thread_id:String?}

let accent=Color(red:0.45,green:0.85,blue:0.80)
let quiet=Color.white.opacity(0.5)

final class PanelModel:ObservableObject {
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
    var noteAvailable:Bool {available && device?.firmware=="0.46" && state?.noteFresh()==true}
    var noteConflict:Bool {noteDirty && noteBaseRevision != note?.revision}
    var noteStatus:String {
        if let version=device?.firmware,version != "0.46"{return "连接 USB 更新后可用"}
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
    var focusAvailable:Bool {available && ["0.34","0.35","0.36","0.37","0.38","0.39","0.40","0.41","0.42","0.43","0.44","0.45","0.46"].contains(device?.firmware ?? "") && state?.companionFresh() == true}
    var companionSettingsAvailable:Bool {available && device?.daily != nil && device?.away_rest != nil && device?.greeting != nil && device?.affection != nil}
    var focusRunning:Bool {companion?.focus_state == "running"}
    var focusPaused:Bool {companion?.focus_state == "paused"}
    var focusActive:Bool {focusRunning || focusPaused}
    var focusNextAvailable:Bool {focusAvailable && companion?.resting == true && companion?.focus_state == "done"}
    var focusPauseAvailable:Bool {focusAvailable && ["0.40","0.41","0.42","0.43","0.44","0.45","0.46"].contains(device?.firmware ?? "")}
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
            else{self.state=nil;self.message="无法读取本机服务，请检查安装是否完整。";self.success=false}
        }
    }
    func issue(_ request:[String:Any],saving:Bool){
        let focus=request["action"] as? String == "focus"
        guard !busy else{return};busy=true;message=focus ? "等待机器人确认计时…" : saving ? "等待机器人保存…" : "正在检查连接与设备…";success=true
        let input=try? JSONSerialization.data(withJSONObject:request)
        run([root.appendingPathComponent("app/control.py").path],input:input){[weak self] result in
            guard let self=self else{return};self.busy=false
            if case .success(let data)=result,let reply=try? JSONDecoder().decode(ControlReply.self,from:data) {
                self.success=reply.ok
                if reply.ok {
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
struct PanelView:View {
    @ObservedObject var model:PanelModel
    func card<Content:View>(@ViewBuilder _ content:()->Content)->some View {
        VStack(alignment:.leading,spacing:14,content:content).padding(20).frame(maxWidth:.infinity,alignment:.leading)
            .background(RoundedRectangle(cornerRadius:18).fill(Color.white.opacity(0.045)))
            .overlay(RoundedRectangle(cornerRadius:18).stroke(Color.white.opacity(0.07)))
    }
    func diagnostic(_ name:String,_ value:String,_ ok:Bool)->some View {
        HStack{Circle().fill(ok ? accent : Color.orange.opacity(0.9)).frame(width:6,height:6);Text(name).foregroundColor(quiet);Spacer();Text(value)}.font(.system(size:12))
    }
    var body:some View {
        let live=model.available
        let d=model.device
        ScrollView { VStack(alignment:.leading,spacing:18){
            HStack(spacing:20){
                PetFace()
                VStack(alignment:.leading,spacing:8){Text("微光").font(.system(size:29,weight:.medium));Text("你的工位小伙伴").font(.system(size:12)).foregroundColor(quiet)}
                Spacer()
                VStack(alignment:.trailing,spacing:8){HStack(spacing:6){Circle().fill(model.state?.connected() == true ? accent:Color.orange).frame(width:6,height:6);Text(model.connectionTitle).font(.system(size:12))};Text("静音运行").font(.system(size:11)).foregroundColor(quiet)}
            }.padding(.bottom,4)
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
                    else {Button("开始专注"){model.focus("start")}.disabled(!model.focusAvailable || model.busy)}
                }
                Text(["0.44","0.45","0.46"].contains(model.device?.firmware ?? "") ? "专注到时自动休息 5 分钟，休息结束点下一轮。两段均可暂停；结束取消整个循环。机器人重启只清除当前计时。" : "静音计时，关闭控制台或短暂断连仍会继续；机器人重启后清除。").font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)
            }
            card {
                HStack{Text("今日专注").font(.system(size:14,weight:.semibold));Spacer();Text("设备记录").font(.system(size:11)).foregroundColor(quiet)}
                Text(model.focusSummaryTitle).font(.system(size:26,weight:.light,design:.rounded)).monospacedDigit().foregroundColor(model.state?.companionFresh() == true ? accent:quiet)
                Text(model.companion?.summary_save_error == 1 ? "记录尚未保存，设备正在重试。" : "完成一轮才计数，提前结束也保留已专注的时间。暂停与休息不计入；按 Mac 本地日期换日。").font(.system(size:11)).foregroundColor(model.companion?.summary_save_error == 1 ? .orange:quiet).fixedSize(horizontal:false,vertical:true)
            }
            card {
                HStack{Text("桌面便签").font(.system(size:14,weight:.semibold));Spacer();Text(model.noteStatus).font(.system(size:11)).foregroundColor(quiet)}
                TextField("例如：下班记得带充电器",text:Binding(get:{model.noteDraft},set:{model.editNote($0)})).textFieldStyle(.roundedBorder).disabled(model.busy)
                HStack {
                    Text("\(model.noteDraft.unicodeScalars.count) / 32 字 · 中文、英文、数字和常用标点").font(.system(size:11)).foregroundColor(model.noteDraft.isEmpty || PanelModel.validNote(model.noteDraft) ? quiet:.orange)
                    Spacer()
                    if model.note?.state=="active" {Button("收起"){model.sendNote("done")}.disabled(!model.noteAvailable || model.busy)}
                    if model.note?.state=="done" && !model.noteDirty {Button("重新贴上"){model.sendNote("restore")}.disabled(!model.noteAvailable || model.busy)}
                    if model.noteDirty {Button("重读便签"){model.discardNote()}.disabled(!model.noteAvailable || model.busy)}
                    Button(model.noteConflict ? "覆盖为这条" : "贴到机器人"){model.sendNote("set")}.disabled(!model.noteAvailable || model.busy || !PanelModel.validNote(model.noteDraft))
                }
                if model.noteConflict,let current=model.note {Text("机器人当前\(current.state=="done" ? "已收起":"显示")：\(current.text.isEmpty ? "没有便签":current.text)").font(.system(size:12)).foregroundColor(.orange).fixedSize(horizontal:false,vertical:true)}
                Text(model.noteMessage.isEmpty ? "一张小纸条，长按约一秒后松手划掉；任务待回应时优先显示提醒。保存后，断开 Mac 或重启机器人仍保留。" : model.noteMessage).font(.system(size:11)).foregroundColor(model.noteSuccess ? quiet:.orange).fixedSize(horizontal:false,vertical:true)
            }
            card {
                HStack{Text("摸头与动作").font(.system(size:14,weight:.semibold));Spacer();Text(live ? "设备回传" : "等待连接").font(.system(size:11)).foregroundColor(quiet)}
                Text(PetStatus.title(d,live:live)).font(.system(size:15,weight:.medium)).foregroundColor(live && d?.motion_state != "unavailable" && d?.motion_state != "sensor" ? accent:.orange)
                Text(PetStatus.latest(d,live:live)).font(.system(size:12)).fixedSize(horizontal:false,vertical:true)
                Text(PetStatus.detail(d,live:live)).font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)
                DisclosureGroup("为什么有时只害羞、不点头？") {
                    Text("摸头需持续约 0.12 秒；一直按着只触发一次，抬手约 0.4 秒才能再次触发。两次点头开始至少间隔 5 秒。\n\n触屏时让开；舵机位置、负载或回执异常时停止驱动，无法卸力时请求断电。这些是自定义固件的限制，不代表已确认硬件损坏。\n\n状态约每 2 秒回传；最近一次记录保留到下一次摸头或机器人重启。查看状态不会触发动作。")
                        .font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true).padding(.top,6)
                }.font(.system(size:11)).tint(quiet)
            }
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
            card {
                HStack{Text("日常设置").font(.system(size:14,weight:.semibold));Spacer();if !model.dirty.isEmpty{Text("尚未保存").font(.system(size:11)).foregroundColor(.orange)}}
                Text(model.settingsHint).font(.system(size:11)).foregroundColor(model.dirty.isEmpty ? quiet : .orange)
                HStack{Text("外观皮肤");Spacer();Picker("外观皮肤",selection:Binding(get:{model.skin},set:{model.skin=$0;model.edited("skin")})){Text("默认").tag(0);Text("猫系").tag(1)}.labelsHidden().frame(width:210)}.disabled(d?.skin == nil)
                Text(d?.skin == nil ? "连接 v0.37 或更新固件后，可切换默认与猫系外观。" : "只改变脸的外观，任务提醒和摸头互动照常。").font(.system(size:11)).foregroundColor(quiet)
                HStack{Text("屏幕亮度");Spacer();Picker("屏幕亮度",selection:Binding(get:{model.light},set:{model.light=$0;model.edited("light")})){ForEach(0..<4){i in Text(["柔和","标准","明亮","很亮"][i]).tag(i)}}.labelsHidden().frame(width:210)}
                HStack{Text("空闲后休息");Spacer();Picker("空闲后休息",selection:Binding(get:{model.rest},set:{model.rest=$0;model.edited("rest")})){ForEach(0..<5){i in Text(["1 分钟","3 分钟","5 分钟","10 分钟","保持常亮"][i]).tag(i)}}.labelsHidden().frame(width:210)}
                HStack{VStack(alignment:.leading,spacing:4){Text("摸头时轻轻点头");Text("关闭后仍会害羞，也能唤醒").font(.system(size:11)).foregroundColor(quiet)};Spacer();Toggle("摸头时轻轻点头",isOn:Binding(get:{model.pet},set:{model.pet=$0;model.edited("pet")})).labelsHidden().toggleStyle(.switch)}
                Divider().overlay(Color.white.opacity(0.1))
                HStack{Text("任务提醒动作").font(.system(size:12,weight:.semibold));Spacer();Text("可单独开启").font(.system(size:11)).foregroundColor(quiet)}
                HStack{Text("待你回应时轻点头");Spacer();Toggle("待你回应时轻点头",isOn:Binding(get:{model.waitMotion},set:{model.waitMotion=$0;model.edited("wait_motion")})).labelsHidden().toggleStyle(.switch)}.disabled(d?.wait_motion == nil)
                HStack{Text("任务完成时轻点头");Spacer();Toggle("任务完成时轻点头",isOn:Binding(get:{model.doneMotion},set:{model.doneMotion=$0;model.edited("done_motion")})).labelsHidden().toggleStyle(.switch)}.disabled(d?.done_motion == nil)
                HStack{Text("番茄钟到时轻点头");Spacer();Toggle("番茄钟到时轻点头",isOn:Binding(get:{model.focusMotion},set:{model.focusMotion=$0;model.edited("focus_motion")})).labelsHidden().toggleStyle(.switch)}.disabled(d?.focus_motion == nil)
                Text(d == nil ? "等待设备回传提醒设置" : d?.wait_motion == nil ? "更新到 v0.25 后可设置提醒动作" : "三项独立设置；开启后轻点头一次，触摸时避让，间隔至少 20 秒。开关本身不会触发动作。").font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)
                Divider().overlay(Color.white.opacity(0.1))
                HStack{Text("陪伴设置").font(.system(size:12,weight:.semibold));Spacer();Text("只改变屏幕反应").font(.system(size:11)).foregroundColor(quiet)}
                Group {
                    HStack{Text("日常表情频率");Spacer();Picker("日常表情频率",selection:Binding(get:{model.daily},set:{model.daily=$0;model.edited("daily")})){Text("低调").tag(0);Text("自然").tag(1);Text("活泼").tag(2)}.labelsHidden().frame(width:210)}
                    Text(["连续空闲约 3–5 分钟后，偶尔张望、微笑或打哈欠","连续空闲约 45–90 秒后，自然地变换小表情","连续空闲约 20–40 秒后，多一些小表情"][model.daily]).font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)
                    HStack{Text("锁屏后休息");Spacer();Toggle("锁屏后休息",isOn:Binding(get:{model.awayRest},set:{model.awayRest=$0;model.edited("away_rest")})).labelsHidden().toggleStyle(.switch)}
                    HStack{Text("回来迎接");Spacer();Toggle("回来迎接",isOn:Binding(get:{model.greeting},set:{model.greeting=$0;model.edited("greeting")})).labelsHidden().toggleStyle(.switch)}
                    HStack{Text("摸头后亲昵");Spacer();Toggle("摸头后亲昵",isOn:Binding(get:{model.affection},set:{model.affection=$0;model.edited("affection")})).labelsHidden().toggleStyle(.switch)}
                }.disabled(!model.companionSettingsAvailable)
                Text(model.companionSettingsAvailable ? "任务提醒优先。关闭亲昵后，直接摸头的表情与动作设置仍然保留。" : "连接 v0.35 或更新固件后，可调整陪伴设置。").font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)
                HStack{Text(live ? "更改后保存到机器人" : model.state?.bridge?.device_supported == false ? "请先更新机器人固件" : "设备状态更新后可调整").font(.system(size:11)).foregroundColor(quiet);Spacer();Button("采用机器人设置"){model.discard()}.disabled(model.dirty.isEmpty);Button("保存设置"){model.save()}.buttonStyle(.borderedProminent).tint(accent).disabled(model.dirty.isEmpty)}
            }.disabled(!live || model.busy)
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
            HStack(alignment:.top,spacing:8){if model.busy{ProgressView().controlSize(.small)};Text(model.message.isEmpty ? "机器人独立供电即可，日常设置通过蓝牙传递。" : model.message).font(.system(size:11)).foregroundColor(model.success ? quiet:Color.orange).fixedSize(horizontal:false,vertical:true);Spacer()}.frame(minHeight:28)
        }.padding(28) }.frame(width:620,height:780).background(Color(red:0.055,green:0.065,blue:0.075)).foregroundColor(.white).preferredColorScheme(.dark)
    }
}

final class AppDelegate:NSObject,NSApplicationDelegate {
    var window:NSWindow?
    let model=PanelModel()
    func applicationDidFinishLaunching(_ notification:Notification){
        let view=PanelView(model:model)
        let hosting=NSHostingView(rootView:view)
        let window=NSWindow(contentRect:NSRect(x:0,y:0,width:620,height:780),styleMask:[.titled,.closable,.miniaturizable],backing:.buffered,defer:false)
        if let url=Bundle.main.url(forResource:"Weiguang",withExtension:"icns"),let icon=NSImage(contentsOf:url){NSApp.applicationIconImage=icon}
        window.title="微光控制台";window.titlebarAppearsTransparent=true;window.backgroundColor=NSColor(calibratedRed:0.055,green:0.065,blue:0.075,alpha:1);window.contentView=hosting;window.center();window.setFrameAutosaveName("WeiguangPanel");self.window=window
        window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true);model.start()
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool{true}
}
@main struct Main {
    static func main(){
        if CommandLine.arguments.contains("--self-test") {
            let d=Device(firmware:"0.25",page:"home",battery:100,charging:0,resting:0,brightness:70,light:1,rest:1,pet:1,save_error:0,uptime:1,sync_age:1)
            let b=BridgeState(connection:"connected",data_source:"ok",transport:"ble",tasks:8,running:1,needs_input:0,device_at:Date().timeIntervalSince1970,device_supported:true,device:d)
            var s=PanelState(installed:true,paused:false,loaded:true,fresh:true,bridge:b)
            precondition(s.deviceFresh());s.paused=true;precondition(!s.deviceFresh());s.paused=false;s.fresh=false;precondition(!s.deviceFresh());s.fresh=true;s.bridge?.device_at=Date().timeIntervalSince1970-30;precondition(!s.deviceFresh());s.bridge?.device_at=Date().timeIntervalSince1970+30;precondition(!s.deviceFresh())
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
            let task=PendingTask(id:"00000000-0000-0000-0046-000000000001",title:"提问",reason:"待答：提醒方式")
            precondition(task.codexURL?.absoluteString == "codex://threads/00000000-0000-0000-0046-000000000001?hostId=local")
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
