import Foundation
import SwiftUI
import CryptoKit

struct RecapTask:Codable,Identifiable {var id:String;var title:String;var kind:String}
struct WorkRecapState:Codable {var token:UInt32;var partial:Bool;var rows:[RecapTask];var waiting:Int;var completed:Int}
struct MusicState:Codable {var source:String;var player:String;var key:String;var title:String;var artist:String;var playing:Bool;var elapsed:Int;var duration:Int}
struct DeskExtrasState:Codable {var settings:[String:Bool];var recap:WorkRecapState;var music:MusicState?;var music_error:String;var supported:Bool?;var last_result:String}

extension PanelModel {
    var extras:DeskExtrasState? {state?.fresh == true ? state?.bridge?.desk_extras:nil}
    func desk(_ operation:String,target:String="-",key:String="",enabled:Bool=false) {
        guard !busy,state?.fresh == true else{return}
        var data:[String:Any]=["action":"desk","operation":operation]
        if operation=="configure" {data["key"]=key;data["enabled"]=enabled}
        else {data["target"]=target;data["token"]=extras?.recap.token ?? 0}
        busy=true
        run([root.appendingPathComponent("app/control.py").path],input:try? JSONSerialization.data(withJSONObject:data)){[weak self] response in
            guard let self=self else{return};self.busy=false
            var result="failed"
            if case .success(let bytes)=response,let value=try? JSONSerialization.jsonObject(with:bytes) as? [String:Any] {result=value["result"] as? String ?? "failed"}
            self.success=["ok","sent","opened"].contains(result)
            self.message=["ok":"已更新。","sent":"已发送控制请求，等待播放器状态更新。","opened":"已请求在 Codex 打开会话。","headphones":"请先让 AirPods 成为 Mac 的声音输出。","stale":"内容已变化，请刷新后重试。","locked":"请先解锁 Mac。"] [result] ?? "暂时未能完成，请检查连接后重试。"
            self.refresh()
        }
    }
}

struct DeskExtrasView:View {
    @ObservedObject var model:PanelModel
    private let accent=Color(red:0.48,green:0.80,blue:0.80)
    private var musicHint:String {
        switch model.extras?.music_error {
        case "missing_helper":return "需要安装 media-control 才能读取歌曲。"
        case "no_player":return "在 QQ 音乐或网易云音乐播放一首歌。"
        case "off":return "开启后读取正在播放的歌名和进度。"
        default:return "等待播放器信息；锁屏时暂停读取。"
        }
    }
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            HStack {Image(systemName:"sparkles").foregroundColor(accent);Text("桌边陪伴").font(.system(size:15,weight:.semibold));Spacer()}
            Toggle("回来后的工作接力",isOn:Binding(get:{model.extras?.settings["recap"] ?? true},set:{model.desk("configure",key:"recap",enabled:$0)})).disabled(model.busy || model.extras == nil)
            if let recap=model.extras?.recap,!recap.rows.isEmpty,model.state?.pendingFresh==true {
                HStack {
                    Text("\(recap.completed) 个新结果 · \(recap.waiting) 个待回应").foregroundColor(accent)
                    Spacer();Button("收起"){model.desk("dismiss")}.disabled(model.busy)
                }.font(.system(size:12))
                ForEach(recap.rows) {task in
                    HStack {
                        Image(systemName:task.kind=="wait" ? "bubble.left":"checkmark.circle").foregroundColor(task.kind=="wait" ? .orange:accent)
                        Text(task.title).font(.system(size:12)).lineLimit(1)
                        Spacer();Button("打开"){model.desk("open",target:task.id)}.disabled(model.busy)
                    }
                }
                if recap.partial {Text("包含恢复连接后的状态对比，中间过程可能不完整。").font(.system(size:11)).foregroundColor(.secondary)}
            } else {Text("离开至少半分钟后回来，汇总新结果和当前待回应；不自动打开会话。").font(.system(size:11)).foregroundColor(.secondary)}
            Divider().opacity(0.25)
            Toggle("音乐陪伴",isOn:Binding(get:{model.extras?.settings["music"] ?? false},set:{model.desk("configure",key:"music",enabled:$0)})).disabled(model.busy || model.extras == nil)
            if let music=model.extras?.music {
                HStack(alignment:.center,spacing:14) {
                    Image(systemName:music.playing ? "music.note":"pause.circle").font(.system(size:26,weight:.light)).foregroundColor(accent).frame(width:38)
                    VStack(alignment:.leading,spacing:5){Text(music.title).font(.system(size:15,weight:.medium)).lineLimit(1);Text([music.artist,music.player].filter{ !$0.isEmpty }.joined(separator:" · ")).font(.system(size:11)).foregroundColor(.secondary).lineLimit(1)}
                    Spacer()
                    Button {model.desk("previous",target:music.key)} label:{Image(systemName:"backward.end.fill")}.accessibilityLabel("上一首")
                    Button {model.desk("toggle",target:music.key)} label:{Image(systemName:music.playing ? "pause.fill":"play.fill")}.accessibilityLabel(music.playing ? "暂停音乐":"播放音乐")
                    Button {model.desk("next",target:music.key)} label:{Image(systemName:"forward.end.fill")}.accessibilityLabel("下一首")
                }.disabled(model.busy)
                if music.duration>0 {ProgressView(value:Double(music.elapsed),total:Double(music.duration)).tint(accent)}
                Text("只读取歌名和进度；播放操作需 AirPods，声音仍由原播放器负责。").font(.system(size:11)).foregroundColor(.secondary)
            } else {Text(musicHint).font(.system(size:11)).foregroundColor(.secondary)}
            if model.extras?.supported == false {Text("机器人需连接 USB 更新后显示新入口。").font(.system(size:11)).foregroundColor(.orange)}
        }.toggleStyle(.switch).font(.system(size:13))
    }
}

// 无 UI 的本机播放器控制入口；只接收固定动作、限定来源和本次曲目身份。
func musicControl() {
    func reply(_ result:String){print("{\"result\":\"\(result)\"}")}
    let args=CommandLine.arguments
    guard args.count==5,["toggle","next","previous"].contains(args[2]),["com.tencent.QQMusicMac","com.netease.163music"].contains(args[3]),args[4].count==16 else {reply("failed");return}
    let paths=["/opt/homebrew/bin/media-control","/usr/local/bin/media-control"]
    guard let binary=paths.first(where:{FileManager.default.isExecutableFile(atPath:$0)}) else {reply("failed");return}
    func run(_ arguments:[String])->Data? {
        let process=Process(),output=Pipe();process.executableURL=URL(fileURLWithPath:binary);process.arguments=arguments
        process.standardOutput=output;process.standardError=FileHandle.nullDevice
        do {
            try process.run()
            let finished=DispatchSemaphore(value:0);process.terminationHandler={_ in finished.signal()}
            if process.isRunning && finished.wait(timeout:.now()+1.3) == .timedOut {process.terminate();return nil}
            guard process.terminationStatus==0 else{return nil}
            return output.fileHandleForReading.readDataToEndOfFile()
        } catch {return nil}
    }
    guard HeadphoneHardware.current().isAirPods else {reply("headphones");return}
    guard let raw=run(["get","--no-artwork"]),raw.count<32768,
          let metadata=try? JSONSerialization.jsonObject(with:raw) as? [String:Any],metadata["bundleIdentifier"] as? String==args[3] else {reply("stale");return}
    guard let pid=metadata["processIdentifier"] as? Int,pid>0,
          NSRunningApplication(processIdentifier:pid_t(pid))?.bundleIdentifier==args[3] else {reply("stale");return}
    let text=["bundleIdentifier","title","artist","album","duration"].map{key->String in
        if let s=metadata[key] as? String{return s};if let n=metadata[key] as? NSNumber{return n.stringValue};return ""
    }.joined(separator:"\n")
    let hash=SHA256.hash(data:Data(text.utf8)).map{String(format:"%02x",$0)}.joined()
    guard String(hash.prefix(16))==args[4] else {reply("stale");return}
    guard HeadphoneHardware.current().isAirPods else {reply("headphones");return}
    let command=["toggle":"toggle-play-pause","next":"next-track","previous":"previous-track"][args[2]]!
    reply(run([command]) == nil ? "failed":"sent")
}
