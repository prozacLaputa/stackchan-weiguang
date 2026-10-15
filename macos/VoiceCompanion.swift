import Foundation
import AppKit
import Combine
import AVFoundation
import Darwin

struct VoiceSoundSettings: Equatable {
    var rate=1.0
    var pitch=0.0
    var autoPlay=true
    static let presets=["原声","舒缓","轻快"]
    var preset: String {
        if abs(rate-1)<0.001 && abs(pitch)<0.001 {return "原声"}
        if abs(rate-0.9)<0.001 && abs(pitch+1)<0.001 {return "舒缓"}
        if abs(rate-1.1)<0.001 && abs(pitch-1)<0.001 {return "轻快"}
        return "自定义"
    }
    mutating func usePreset(_ name: String) {
        switch name {
        case "原声":rate=1;pitch=0
        case "舒缓":rate=0.9;pitch = -1
        case "轻快":rate=1.1;pitch=1
        default:break
        }
    }
    func normalized() -> Self {
        var result=self
        result.rate=rate.isFinite ? min(1.25,max(0.8,rate)) : 1
        result.pitch=pitch.isFinite ? min(2,max(-2,pitch)) : 0
        return result
    }
    static func load(_ preferences: UserDefaults?) -> Self {
        var value=Self()
        if let p=preferences {
            // 旧版 volume 偏好仅用于低音量验收；现在统一跟随耳机系统音量。
            if p.object(forKey:"rate") != nil {value.rate=p.double(forKey:"rate")}
            if p.object(forKey:"pitch") != nil {value.pitch=p.double(forKey:"pitch")}
            if p.object(forKey:"autoPlay") != nil {value.autoPlay=p.bool(forKey:"autoPlay")}
        }
        return value.normalized()
    }
    func save(_ p: UserDefaults?) {
        p?.set(rate,forKey:"rate")
        p?.set(pitch,forKey:"pitch");p?.set(autoPlay,forKey:"autoPlay")
    }
}

struct PendingVoiceReply {
    let samples:[Float]
    let route:HeadphoneRoute
    let ticket:UInt64
    let expires:Date
    func isValid(gate:VoiceGate,route current:HeadphoneRoute,now:Date=Date())->Bool {
        now<expires && route==current && gate.accepts(ticket)
    }
}

final class VoiceCompanion: ObservableObject {
    var onLocalCommand:((VoiceLocalCommand,@escaping(VoiceCommandOutcome)->Void)->Void)?
    var onHotkeyChanged:(()->Void)?
    var onPresentVoiceMode:(()->Void)?
    func presentVoiceMode() {onPresentVoiceMode?()}
    @Published private(set) var commandsEnabled=true
    @Published private(set) var hotkeyEnabled=true
    @Published var hotkeyStatus="⌃⌥空格 · 开始或结束语音"
    @Published private(set) var enabled=false
    @Published private(set) var route=HeadphoneRoute()
    @Published private(set) var approved=""
    @Published private(set) var busy=false
    @Published private(set) var message=""
    @Published var draft=""
    @Published private(set) var conversation=VoiceConversation()
    func clearConversation() {conversation.clear()}
    private var submittedDraft:String?
    @Published private(set) var sound=VoiceSoundSettings()
    @Published private(set) var pending:PendingVoiceReply?
    @Published private(set) var greetingEnabled=false
    @Published private(set) var taskNoticeEnabled=false
    private var taskNoticeTrigger=VoiceTaskNoticeTrigger()
    private var activeTaskNotice=false
    @Published private(set) var greetingMinutes=1
    @Published private(set) var greetingStatus="等待下一次耳机连接"
    @Published private(set) var preparingGreeting=false
    @Published private(set) var greetingReadyCount=0
    @Published private(set) var microphoneState=VoiceHoldState()
    @Published private(set) var microphoneSeconds=0.0
    @Published private(set) var microphoneLevel:Float=0
    @Published private(set) var microphonePermission=AVCaptureDevice.authorizationStatus(for:.audio)
    private var microphone:AirPodsMicrophone?
    private var microphoneBegan=Date.distantPast
    private let microphoneQueue=DispatchQueue(label:"weiguang.voice.microphone",qos:.userInitiated)
    private var appTokens:[NSObjectProtocol]=[]
    var canHoldMicrophone:Bool {!voiceMode.visible && ready && (!busy || preparingGreeting) && !microphoneState.active}
    @Published private(set) var voiceMode=VoiceModeState()
    @Published private(set) var voiceModeLevel:Float=0
    @Published private(set) var voiceModeNote=""
    private var voiceModeMicrophone:AirPodsMicrophone?
    private var voiceModeTone:HeadphonePCMPlayer?
    private var voiceModeConnection=VoiceCallConnection()
    private let voiceModeGate=VoiceGate()
    private var sentenceDetector=VoiceSentenceDetector()
    private var voiceModeLastInput=Date.distantPast
    private var voiceModeLastRecorded:VoiceModeState.Phase?
    private var voiceModeTurns=0,voiceModeInterruptions=0
    private var voiceModeErrorCode:Int?
    let gate=VoiceGate()
    let root=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Weiguang")
    let preferences: UserDefaults?
    var watcher: HeadphoneWatcher?
    var timer: Timer?
    var tokens: [NSObjectProtocol]=[]
    lazy var faceRelay=VoiceFaceRelay(root:root)
    var player: HeadphonePCMPlayer?
    var process: Process?
    var requestID=UUID()
    var deadline=Date.distantPast
    var audioEndedAt: Date?
    var streamWaiting:[Float]=[]
    var requestBegan=Date.distantPast
    var greetingTrigger=VoiceGreetingTrigger()
    var greetingLine = -1
    var activeGreeting=false
    var sessionInteractive=true
    var greetingBank=VoiceGreetingBank()
    var nextGreetingPreparation=Date.distantPast
    var greetingPreparationAttempts=2
    private(set) var lastResult: [String:Any]=[:]
    func recordResult() {
        guard preferences != nil,lastResult["greeting_preparation"] as? Bool != true else {return} // 静音备句和离线测试不覆盖真实播放记录。
        let allowed:Set<String>=["started","played","cancelled","error","error_code","stage","request_started_at","greeting","greeting_preparation","automatic_greeting","prepared_greeting","local_command","command_confirmed","task_notice","notice_text_verified","streaming","first_playback_seconds","receive_complete_seconds","first_audio_seconds","input_ready_seconds","connected_seconds","input_upload_seconds","upload_interval_ms","input_guard_ms","stt_seconds","tts_start_seconds","audio_packets","tts_started","tts_stopped","stt_received","missing_audio_packets","concealed_audio_packets","subtitle_events","rendered_frames","stream_underruns","pcm_frames","bound_device_verified","partial_audio_started","microphone_opened"]
        var safe=lastResult.filter{allowed.contains($0.key)}
        safe["updated_at"]=Date().timeIntervalSince1970
        guard let data=try? JSONSerialization.data(withJSONObject:safe,options:[.sortedKeys]) else {return}
        let file=root.appendingPathComponent("runtime/voice-last.json")
        try? data.write(to:file,options:.atomic)
        try? FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:file.path)
        if lastResult["error"] != nil {
            let failure=root.appendingPathComponent("runtime/voice-last-failure.json")
            try? data.write(to:failure,options:.atomic)
            try? FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:failure.path)
        }
    }
    var headphonesAvailable:Bool {route.isAirPods && !approved.isEmpty && route.uid == approved && watcher?.healthy == true}
    var ready: Bool { enabled && headphonesAvailable && sessionInteractive && VoiceSession.isAwake() }
    var hasWork:Bool {busy || pending != nil || microphoneState.active || voiceMode.running}
    var hasForegroundWork:Bool {(busy && !preparingGreeting) || pending != nil || microphoneState.active || voiceMode.visible}
    var soundSummary:String {"\(sound.preset) · 跟随耳机音量 · \(String(format:"%.2g",sound.rate))×"}
    var routeText: String {
        if !enabled {return "语音已关闭"}
        if !sessionInteractive || !VoiceSession.isAwake() {return "Mac 已休息，语音保持静音"}
        if !route.isAirPods {return "等待 AirPods 成为声音输出"}
        if approved != route.uid {return "请确认使用这副 AirPods"}
        if watcher?.healthy != true {return "输出监测未就绪，保持静音"}
        return busy ? "仅 AirPods · \(route.name)" : "AirPods 可播放 · \(route.name)"
    }
    init(persist: Bool=true) {
        preferences=persist ? UserDefaults(suiteName:"io.github.prozaclaputa.weiguang.voice") : nil
        enabled=preferences?.bool(forKey:"enabled") ?? false
        approved=preferences?.string(forKey:"approvedUID") ?? ""
        sound=VoiceSoundSettings.load(preferences)
        greetingEnabled=preferences?.bool(forKey:"greetingEnabled") ?? false
        taskNoticeEnabled=preferences?.bool(forKey:"taskNoticeEnabled") ?? false
        commandsEnabled=preferences?.object(forKey:"commandsEnabled") as? Bool ?? true
        hotkeyEnabled=preferences?.object(forKey:"hotkeyEnabled") as? Bool ?? true
        let minutes=preferences?.integer(forKey:"greetingMinutes") ?? 1
        greetingMinutes=[1,5,15].contains(minutes) ? minutes:1
        greetingLine=preferences?.object(forKey:"greetingLine") as? Int ?? -1
        let now=Date().timeIntervalSince1970,saved=preferences?.double(forKey:"greetingAttemptAt") ?? 0
        greetingTrigger=VoiceGreetingTrigger(lastAttempt:saved.isFinite && saved>=0 ? min(saved,now):0)
    }
    func start() {
        signal(SIGPIPE,SIG_IGN) // 取消正在写入的语音 pipe 只产生 EPIPE，不终止控制台。
        faceRelay.start()
        guard timer == nil else {return}
        refreshRoute()
        watcher=HeadphoneWatcher { [weak self] in
            self?.gate.revoke();self?.voiceModeGate.revoke()
            DispatchQueue.main.async {
                guard let self=self else {return}
                self.taskNoticeTrigger.reset()
                if self.hasWork {self.cancel("输出变化，已停止；旧回复不会补播。")}
                self.refreshRoute()
            }
        }
        watcher?.observe(route.id)
        refreshRoute()
        resetGreetingBaseline()
        let timer=Timer(timeInterval:0.15,repeats:true) { [weak self] _ in self?.tick() }
        self.timer=timer;RunLoop.main.add(timer,forMode:.common)
        for event in [NSApplication.didResignActiveNotification,NSWindow.didResignKeyNotification] {
            appTokens.append(NotificationCenter.default.addObserver(forName:event,object:nil,queue:.main) { [weak self] _ in
                guard let self=self,self.microphoneState.active else {return}
                self.cancelMicrophone("已取消录音，没有发送。")
            })
        }
        for event in [NSWorkspace.willSleepNotification,NSWorkspace.screensDidSleepNotification,NSWorkspace.sessionDidResignActiveNotification] {
            tokens.append(NSWorkspace.shared.notificationCenter.addObserver(forName:event,object:nil,queue:.main) { [weak self] _ in
                guard let self=self else {return}
                self.sessionInteractive=false;self.gate.revoke();self.voiceModeGate.revoke();self.resetGreetingBaseline();self.taskNoticeTrigger.reset()
                if self.hasWork {self.cancel("Mac 已休息，语音已停止。")}
            })
        }
        for event in [NSWorkspace.didWakeNotification,NSWorkspace.screensDidWakeNotification,NSWorkspace.sessionDidBecomeActiveNotification] {
            tokens.append(NSWorkspace.shared.notificationCenter.addObserver(forName:event,object:nil,queue:.main) { [weak self] _ in
                guard let self=self else {return}
                self.sessionInteractive=true;self.refreshRoute();self.resetGreetingBaseline();self.taskNoticeTrigger.reset()
            })
        }
    }
    func refreshRoute() {
        let current=HeadphoneHardware.current()
        if current != route {
            taskNoticeTrigger.reset()
            if hasWork {cancel("输出变化，已停止；旧回复不会补播。")}
            route=current;watcher?.observe(current.id)
        }
        gate.update(enabled:enabled && watcher?.healthy == true && sessionInteractive && VoiceSession.isAwake(),approved:approved,route:route)
    }
    func tick() {
        refreshRoute()
        tickVoiceMode()
        faceRelay.update(ready ? player?.mouthLevel():nil)
        if microphoneState.phase == .recording,let microphone=microphone {
            let meter=microphone.meter();microphoneSeconds=meter.seconds;microphoneLevel=meter.level
            if Date().timeIntervalSince(microphoneBegan)>=30 {cancelMicrophone("已到 30 秒上限，录音已取消，请分句说。")}
            else if meter.failed || !microphone.allowed || !VoiceMicrophoneHardware.valid(microphone.inputID,for:route) {
                cancelMicrophone("AirPods 麦克风中断，录音已丢弃，请重新按住。")
            }
        }
        if hasWork && !ready {cancel("AirPods 输出不可用，已停止。")}
        if let pending=pending,!pending.isValid(gate:gate,route:route) {cancel("待播放回复已清除，请重新发送。")}
        if busy && Date()>deadline {cancel("本次等待超时，未继续播放。")}
        if busy && !preparingGreeting && player == nil && process != nil {
            let seconds=Int(Date().timeIntervalSince(requestBegan))
            if seconds>=8 {message="仍在等待语音 · 已等 \(seconds) 秒 · 可点「立即停止」"}
        }
        if let player=player,player.finished {
            // 给AU转换器与耳机设备缓冲短暂排空时间；路由失效仍会立即取消。
            if audioEndedAt == nil {audioEndedAt=Date()}
            if Date().timeIntervalSince(audioEndedAt!)>0.4 {
                lastResult["rendered_frames"]=player.renderedFrames
                lastResult["stream_underruns"]=player.underrunCount
                lastResult["bound_device_verified"]=player.boundCorrectly
                if activeGreeting {greetingStatus="已打过招呼 · \(DateFormatter.localizedString(from:Date(),dateStyle:.none,timeStyle:.short))"}
                player.stop();self.player=nil;busy=false;activeGreeting=false;activeTaskNotice=false;message="播放结束 · \(soundSummary)";lastResult["played"]=true
                recordResult()
                conversation.finish(id:requestID,state:.completed)
                if voiceMode.running && !sentenceDetector.speaking {voiceMode.set(.listening)}
            }
        }
        greetingBank.prune(rate:sound.rate,pitch:sound.pitch,now:Date())
        if greetingReadyCount != greetingBank.clips.count {greetingReadyCount=greetingBank.clips.count}
        if let notice=taskNoticeTrigger.take(eligible:canAnnounceTask,now:Date().timeIntervalSince1970) {request(taskNotice:notice)}
        if greetingTrigger.poll(available:headphonesAvailable,permitted:enabled && greetingEnabled && sessionInteractive && VoiceSession.isAwake(),occupied:hasForegroundWork,cooldown:Double(greetingMinutes*60),now:Date().timeIntervalSince1970) {
            preferences?.set(greetingTrigger.lastAttempt,forKey:"greetingAttemptAt")
            request(greeting:true)
        }
        if greetingEnabled && ready && !hasWork && !voiceMode.visible && !taskNoticeTrigger.hasPending && greetingReadyCount<2 && greetingPreparationAttempts>0 && Date()>=nextGreetingPreparation {
            request(greetingPreparation:true)
        }
    }
    func adoptCurrent() {
        refreshRoute();guard route.isAirPods else {message="请先连接 AirPods 并选为声音输出。";return}
        cancel("");approved=route.uid;preferences?.set(approved,forKey:"approvedUID");refreshRoute()
        resetGreetingBaseline()
        message="已绑定这副 AirPods；更换耳机需要重新确认。"
    }
    func setEnabled(_ value: Bool) {
        taskNoticeTrigger.reset()
        enabled=value;preferences?.set(value,forKey:"enabled")
        if !value {cancel("语音已关闭。")}
        refreshRoute()
        if value && approved.isEmpty && route.isAirPods {adoptCurrent()}
        resetGreetingBaseline()
    }
    func resetGreetingBaseline() {greetingTrigger.reset(available:headphonesAvailable,now:Date().timeIntervalSince1970)}
    private var canAnnounceTask:Bool {taskNoticeEnabled && ready && !hasForegroundWork && draft.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty}
    func acceptTaskSnapshot(_ snapshot:VoiceTaskSnapshot?) {
        taskNoticeTrigger.observe(snapshot,eligible:canAnnounceTask,now:Date().timeIntervalSince1970)
    }
    func setTaskNoticeEnabled(_ value:Bool) {
        taskNoticeEnabled=value;preferences?.set(value,forKey:"taskNoticeEnabled")
        taskNoticeTrigger.reset()
        if !value && activeTaskNotice {cancel("任务完成语音提醒已关闭。")}
    }
    func setCommandsEnabled(_ value:Bool) {
        commandsEnabled=value;preferences?.set(value,forKey:"commandsEnabled")
        if voiceMode.running && busy {interruptVoiceMode()}
    }
    func setHotkeyEnabled(_ value:Bool) {
        hotkeyEnabled=value;preferences?.set(value,forKey:"hotkeyEnabled");onHotkeyChanged?()
    }
    func setGreetingEnabled(_ value:Bool) {
        greetingEnabled=value;preferences?.set(value,forKey:"greetingEnabled")
        if !value && (activeGreeting || preparingGreeting) {cancel("自动问候已关闭。")}
        if !value {greetingBank.clear();greetingReadyCount=0}
        if value {nextGreetingPreparation=Date();greetingPreparationAttempts=2}
        greetingStatus=value ? "等待下一次耳机连接":"问候已关闭"
        resetGreetingBaseline()
    }
    func setGreetingMinutes(_ minutes:Int) {
        guard [1,5,15].contains(minutes) else {return}
        greetingMinutes=minutes;preferences?.set(minutes,forKey:"greetingMinutes");resetGreetingBaseline()
    }
    func changeSound(_ edit:(inout VoiceSoundSettings)->Void) {
        var next=sound;edit(&next);next=next.normalized()
        guard next != sound else {return}
        if hasWork {cancel("声音设置已更新；请重新发送。")}
        if next.rate != sound.rate || next.pitch != sound.pitch {greetingBank.clear();greetingReadyCount=0;nextGreetingPreparation=Date();greetingPreparationAttempts=2}
        sound=next;sound.save(preferences)
        resetGreetingBaseline()
    }
    func restoreSound() {
        // 保留总开关和已确认耳机；音量始终交给系统和耳机控制。
        changeSound {$0=VoiceSoundSettings()}
        message="已恢复原声、正常语速和自动播放；音量跟随耳机。"
    }
    func cancel(_ reason: String,failed:Bool=false,preserveVoiceMode:Bool=false) {
        taskNoticeTrigger.reset();activeTaskNotice=false
        if voiceMode.visible && !preserveVoiceMode {
            stopVoiceModeMicrophone();voiceMode.end();voiceModeNote=reason;recordVoiceMode()
        }
        cancelMicrophone("")
        faceRelay.update(nil)
        conversation.finish(id:requestID,state:failed ? .failed:.cancelled,detail:reason)
        if activeGreeting {greetingStatus="这次问候已取消，不会补播"}
        if let submittedDraft=submittedDraft,draft.isEmpty {draft=submittedDraft}
        submittedDraft=nil
        gate.revoke();requestID=UUID()
        if let process=process,process.isRunning {process.terminate()}
        process=nil;player?.stop();player=nil;pending=nil;busy=false;audioEndedAt=nil;activeGreeting=false;preparingGreeting=false;streamWaiting=[]
        resetGreetingBaseline()
        if !reason.isEmpty {message=reason}
        if lastResult["started"] as? Bool == true && lastResult["played"] as? Bool != true {lastResult["cancelled"]=true}
        if !lastResult.isEmpty {recordResult()}
    }
    func stopByUser() {greetingPreparationAttempts=0;cancel("已停止，旧回复不会补播。")}
    func play(_ reply:PendingVoiceReply,gain:Float,streaming:Bool=false) {
        refreshRoute()
        guard ready,reply.isValid(gate:gate,route:route) else {cancel("回复已过期，未播放。");return}
        do {
            let p=HeadphonePCMPlayer(gate:gate,ticket:reply.ticket,route:reply.route,samples:reply.samples,gain:gain,streaming:streaming)
            try p.start();player=p;busy=true;audioEndedAt=nil
            deadline=activeTaskNotice ? min(deadline,Date().addingTimeInterval(15)):Date().addingTimeInterval(65)
            conversation.finish(id:requestID,state:.replying)
            if voiceMode.running {voiceMode.set(.replying)}
            if streaming {lastResult["first_playback_seconds"]=Date().timeIntervalSince(requestBegan)}
            message=streaming ? String(format:"正在边收边播 · %.1f 秒开始 · 仅 AirPods",Date().timeIntervalSince(requestBegan)):"仅 AirPods 播放 · 跟随耳机音量"
            recordResult()
        } catch {cancel("耳机输出无法确认，已拒绝播放。",failed:true);lastResult["error"]="audio_start_rejected"}
    }
    func receiveSubtitle(_ text:String,sequence:Int,id:UUID,ticket:UInt64,selected:HeadphoneRoute) {
        guard requestID==id,gate.accepts(ticket),ready,route==selected else {return}
        conversation.append(id:id,sequence:sequence,text:text)
    }
    func receiveStream(_ samples:[Float],id:UUID,ticket:UInt64,selected:HeadphoneRoute) {
        guard requestID==id else {return}
        refreshRoute()
        guard requestID==id,ready,route==selected,gate.accepts(ticket) else {cancel("输出已变化，语音已停止。");return}
        if let player=player {
            if !player.append(samples) {cancel("音频分片无效，已停止。",failed:true);lastResult["error"]="stream_chunk_rejected"}
        } else {
            streamWaiting.append(contentsOf:samples)
            // 先备180ms，避免每个网络包的抖动都变成可听见的停顿。
            if streamWaiting.count>=8640 {
                let initial=streamWaiting;streamWaiting=[]
                play(PendingVoiceReply(samples:initial,route:selected,ticket:ticket,expires:Date().addingTimeInterval(60)),gain:1,streaming:true)
            }
        }
    }
    func playPending() {
        guard !busy,let reply=pending else {return}
        pending=nil;lastResult["manual_play"]=true;play(reply,gain:1)
    }
    @discardableResult func playPreparedGreeting(automatic:Bool)->Bool {
        guard !hasForegroundWork else {return false}
        greetingBank.prune(rate:sound.rate,pitch:sound.pitch,now:Date())
        guard greetingBank.clips.contains(where:{$0.index != greetingLine}) else {return false}
        if preparingGreeting {cancel("")}
        refreshRoute()
        guard ready,let ticket=gate.ticket(),let clip=greetingBank.take(after:greetingLine,rate:sound.rate,pitch:sound.pitch,now:Date()) else {return false}
        greetingReadyCount=greetingBank.clips.count
        greetingLine=clip.index;preferences?.set(greetingLine,forKey:"greetingLine")
        activeGreeting=automatic
        let gain:Float=1
        lastResult=["started":true,"played":false,"greeting":true,"automatic_greeting":automatic,"prepared_greeting":true,"gain":gain,"microphone_opened":false]
        if automatic {greetingStatus="正在问候…"}
        resetGreetingBaseline()
        play(PendingVoiceReply(samples:clip.samples,route:route,ticket:ticket,expires:Date().addingTimeInterval(10)),gain:gain)
        return true
    }
    func startVoiceMode() {
        guard !voiceMode.running else {return}
        refreshRoute()
        guard ready else {message="请先开启语音并确认 AirPods 输出。";return}
        microphonePermission=AVCaptureDevice.authorizationStatus(for:.audio)
        guard microphonePermission == .authorized else {requestMicrophoneAccess();return}
        let playTone=voiceMode.phase != .paused
        cancel("",preserveVoiceMode:true);stopVoiceModeMicrophone();refreshRoute()
        guard ready else {return}
        let token=voiceMode.begin(),selected=route
        conversation.beginCall()
        voiceModeLevel=0;sentenceDetector.reset()
        voiceModeTurns=0;voiceModeInterruptions=0;voiceModeErrorCode=nil;voiceModeLastRecorded=nil;recordVoiceMode()
        voiceModeNote="";resetGreetingBaseline()
        if playTone {
            guard let ticket=gate.ticket() else {cancel("耳机输出暂不可用，请重试。");return}
            do {
                let tone=HeadphonePCMPlayer(gate:gate,ticket:ticket,route:selected,samples:VoiceCallConnection.samples(),gain:1)
                try tone.start();voiceModeTone=tone
                voiceModeConnection.begin(token:token,now:Date().timeIntervalSince1970)
            } catch {cancel("未能接通 AirPods，请重新连接后重试。",failed:true)}
        } else {openVoiceModeMicrophone(token:token,selected:selected)}
    }
    private func openVoiceModeMicrophone(token:UUID,selected:HeadphoneRoute) {
        guard voiceMode.accepts(token),ready,route==selected else {cancel("AirPods 输出变化，语音模式已停止。");return}
        voiceModeGate.update(enabled:true,approved:approved,route:selected)
        guard let ticket=voiceModeGate.ticket() else {cancel("麦克风许可失效，请重试。");return}
        let recorder=AirPodsMicrophone(route:selected,gate:voiceModeGate,ticket:ticket)
        voiceModeMicrophone=recorder;voiceModeLastInput=Date()
        microphoneQueue.async { [weak self] in
            do {
                try recorder.start()
                DispatchQueue.main.async {
                    guard let self=self,self.voiceMode.accepts(token) else {recorder.permit.revoke();return}
                    guard self.ready,self.route==selected else {self.cancel("AirPods 输出变化，语音模式已停止。");return}
                    self.voiceMode.set(.listening);self.voiceModeLastInput=Date();self.recordVoiceMode()
                }
            } catch {
                DispatchQueue.main.async {
                    guard let self=self,self.voiceMode.accepts(token) else {return}
                    self.voiceModeErrorCode=(error as NSError).code
                    self.cancel("暂时无法打开 AirPods 麦克风，请点重试。",failed:true)
                }
            }
        }
    }
    private func stopVoiceModeMicrophone() {
        voiceModeConnection.cancel();voiceModeTone?.stop();voiceModeTone=nil
        voiceModeGate.revoke()
        if let microphone=voiceModeMicrophone {microphone.permit.revoke();microphoneQueue.async {_=microphone.stop(keep:false)}}
        voiceModeMicrophone=nil;sentenceDetector.reset();voiceModeLevel=0
    }
    func exitVoiceMode() {
        guard voiceMode.visible else {return}
        cancel("语音模式已结束，麦克风已关闭。")
        conversation.endCall()
        voiceMode.close();voiceModeNote="";resetGreetingBaseline();recordVoiceMode()
    }
    func toggleVoiceModePause() {
        if voiceMode.phase == .paused || voiceMode.phase == .ended {startVoiceMode();return}
        guard voiceMode.running else {return}
        cancel("",preserveVoiceMode:true);stopVoiceModeMicrophone();voiceMode.pause()
        voiceModeNote="麦克风已关闭，点继续再聊天";recordVoiceMode()
    }
    func interruptVoiceMode() {
        guard voiceMode.running else {return}
        voiceModeInterruptions+=1
        cancel("",preserveVoiceMode:true);refreshRoute();sentenceDetector.reset()
        voiceMode.set(.listening);voiceModeNote="我在听，你接着说"
    }
    private func recordVoiceMode() {
        guard preferences != nil,voiceModeLastRecorded != voiceMode.phase else {return}
        voiceModeLastRecorded=voiceMode.phase
        var safe:[String:Any]=["phase":String(describing:voiceMode.phase),"microphone_active":voiceModeMicrophone != nil && voiceMode.running && voiceMode.phase != .starting,
            "turns":voiceModeTurns,"interruptions":voiceModeInterruptions,"updated_at":Date().timeIntervalSince1970]
        if let code=voiceModeErrorCode {safe["capture_error_code"]=code}
        let path=root.appendingPathComponent("runtime/voice-mode-last.json")
        if let data=try? JSONSerialization.data(withJSONObject:safe,options:[.sortedKeys]) {
            try? data.write(to:path,options:.atomic)
            try? FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:path.path)
        }
    }
    private func tickVoiceMode() {
        defer {recordVoiceMode()}
        if let tone=voiceModeTone {
            let valid=voiceMode.phase == .starting && ready && tone.route==route && gate.accepts(tone.ticket)
            switch voiceModeConnection.poll(token:voiceMode.id,valid:valid,finished:tone.finished,now:Date().timeIntervalSince1970) {
            case .waiting:break
            case .openMicrophone:
                tone.stop();voiceModeTone=nil
                openVoiceModeMicrophone(token:voiceMode.id,selected:tone.route)
            case .cancelled:cancel("接通已中断，请确认 AirPods 后重试。")
            }
            return
        }
        guard voiceMode.running,voiceMode.phase != .starting,let microphone=voiceModeMicrophone else {return}
        guard ready,microphone.allowed,VoiceMicrophoneHardware.valid(microphone.inputID,for:route),!microphone.meter().failed else {
            cancel("AirPods 麦克风或输出中断，语音模式已停止。");return
        }
        guard let chunk=microphone.drain() else {
            if Date().timeIntervalSince(voiceModeLastInput)>3 {cancel("麦克风没有返回声音，语音模式已停止。")}
            return
        }
        voiceModeLastInput=Date()
        guard chunk.seconds<=2 else {cancel("录音处理停顿，已关闭麦克风，请点继续重试。");return}
        let events=sentenceDetector.feed(chunk,replying:player != nil)
        voiceModeLevel=sentenceDetector.level
        for event in events {
            guard voiceMode.running else {break}
            switch event {
            case .began:
                if busy || pending != nil {voiceModeInterruptions+=1;cancel("",preserveVoiceMode:true);refreshRoute()}
                voiceMode.set(.hearing);voiceModeNote="正在听你说，停顿约一秒后发送"
            case let .sentence(clip):
                voiceModeTurns+=1
                voiceMode.set(.waiting);voiceModeNote="已经说完也可以直接接着补充"
                request(microphoneClip:clip,fromVoiceMode:true)
            case .tooLong:
                toggleVoiceModePause();voiceModeNote="这句话超过28秒，已暂停且没有发送；点继续后分句说"
            }
        }
    }
    func requestMicrophoneAccess() {
        microphonePermission=AVCaptureDevice.authorizationStatus(for:.audio)
        if microphonePermission == .notDetermined {
            message="请允许麦克风访问；允许后再按住说话，不会自动录音。"
            AVCaptureDevice.requestAccess(for:.audio) { [weak self] granted in
                DispatchQueue.main.async {
                    self?.microphonePermission=AVCaptureDevice.authorizationStatus(for:.audio)
                    self?.message=granted ? "麦克风已允许，按住说话才开始录音。":"麦克风未允许，仍可打字聊天。"
                }
            }
        } else if microphonePermission != .authorized {
            message="请在系统设置 → 隐私与安全性 → 麦克风，允许微光控制台。"
        }
    }
    func beginMicrophone() {
        guard NSApp.isActive,canHoldMicrophone else {return}
        microphonePermission=AVCaptureDevice.authorizationStatus(for:.audio)
        guard microphonePermission == .authorized else {requestMicrophoneAccess();return}
        if preparingGreeting {cancel("")}
        pending=nil;refreshRoute()
        guard ready,let ticket=gate.ticket() else {return}
        let token=microphoneState.begin(),selected=route
        let recorder=AirPodsMicrophone(route:selected,gate:gate,ticket:ticket)
        microphone=recorder;microphoneSeconds=0;microphoneLevel=0;microphoneBegan=Date()
        resetGreetingBaseline();message="正在打开 AirPods 麦克风…"
        microphoneQueue.async { [weak self] in
            do {
                try recorder.start()
                DispatchQueue.main.async {
                    guard let self=self,self.microphoneState.started(token) else {recorder.permit.revoke();return}
                    self.message="正在听 · 松开发送 · 移出按钮或 Esc 取消"
                }
            } catch {
                DispatchQueue.main.async {
                    guard let self=self,self.microphoneState.accepts(token) else {return}
                    self.cancelMicrophone("未能打开已绑定的 AirPods 麦克风，请重新按住；不会改用电脑麦克风。")
                }
            }
        }
    }
    func cancelMicrophone(_ reason:String) {
        let wasActive=microphoneState.active
        microphoneState.cancel();microphoneLevel=0;microphoneSeconds=0
        if let recorder=microphone {recorder.permit.revoke();microphoneQueue.async {_=recorder.stop(keep:false)}}
        microphone=nil
        if wasActive {resetGreetingBaseline();if !reason.isEmpty {message=reason}}
    }
    func endMicrophone(send:Bool) {
        guard microphoneState.holding else {return}
        let token=microphoneState.id
        guard send,microphoneState.release(),let recorder=microphone else {cancelMicrophone("已取消录音，没有发送。");return}
        recorder.permit.revoke();microphone=nil;microphoneLevel=0;message="录音已结束，正在发送…"
        let selected=route
        microphoneQueue.async { [weak self] in
            let clip=recorder.stop(keep:true)
            // 先释放 Bluetooth 通话输入，让设备恢复播放；期间断连/取消会撤销 token。
            DispatchQueue.main.asyncAfter(deadline:.now()+0.6) {
                guard let self=self,self.microphoneState.accepts(token) else {return}
                self.refreshRoute()
                guard self.microphoneState.accepts(token),self.ready,self.route==selected else {self.cancelMicrophone("输出已变化，录音已丢弃。");return}
                guard let clip=clip else {self.cancelMicrophone("录音太短或中断了，请按住至少半秒再说话。");return}
                self.microphoneState.cancel();self.microphoneSeconds=0
                self.request(microphoneClip:clip)
            }
        }
    }
    func request(demo: Bool=false, silenceOnly: Bool=false,greeting:Bool=false,greetingPreview:Bool=false,greetingPreparation:Bool=false,microphoneClip:VoiceMicrophoneClip?=nil,fromVoiceMode:Bool=false,taskNotice:VoiceTaskNotice?=nil) {
        if taskNotice != nil && !canAnnounceTask {return}
        guard !voiceMode.visible || (fromVoiceMode && voiceMode.running) else {return}
        if greeting {
            guard greetingEnabled else {return}
            greetingPreparationAttempts=2;nextGreetingPreparation=Date()
            if !playPreparedGreeting(automatic:true) {greetingStatus="问候还未就绪，这次跳过，不延迟补播"}
            return
        }
        if greetingPreview && playPreparedGreeting(automatic:false) {return}
        if !greetingPreparation && preparingGreeting {cancel("")}
        refreshRoute()
        guard !busy,!microphoneState.active,ready,let ticket=gate.ticket() else {message="保持静音：请开启语音并确认 AirPods 输出。";return}
        if greetingPreparation && (!greetingEnabled || hasWork) {return}
        let greetingMode=greetingPreview || greetingPreparation
        var selectedGreetingLine = -1
        let text:String
        if greetingMode {
            selectedGreetingLine=VoiceGreetingLines.next(excluding:Set(greetingBank.clips.map{$0.index}+[greetingLine]))
            text=VoiceGreetingLines.prompt(selectedGreetingLine)
        } else if let notice=taskNotice {text=notice.prompt}
        else if let clip=microphoneClip {text=String(format:"语音消息 · %.1f 秒",clip.seconds)}
        else {text=demo ? "你好，请用一句很短的话跟我打招呼，不要调用工具。" : draft.trimmingCharacters(in:.whitespacesAndNewlines)}
        guard !text.isEmpty,text.count<=120 else {message="输入 1–120 字后发送。";return}
        if !greetingPreparation {resetGreetingBaseline()}
        pending=nil
        var options=sound
        if fromVoiceMode || taskNotice != nil {options.autoPlay=true} // 各自独立开关，不改文字聊天的播放偏好。
        let shouldStream = taskNotice == nil && !greetingPreparation && (greetingMode || demo || options.autoPlay) && options.rate==1 && options.pitch==0
        let gain:Float=1 // 不额外衰减；聊天、试听与问候均跟随耳机系统音量。
        let id=UUID();requestID=id;busy=true;deadline=Date().addingTimeInterval(taskNotice == nil ? 105:30);audioEndedAt=nil
        requestBegan=Date();streamWaiting=[]
        activeGreeting=greeting
        activeTaskNotice=taskNotice != nil
        preparingGreeting=greetingPreparation
        if greetingPreparation {nextGreetingPreparation=Date().addingTimeInterval(60);greetingPreparationAttempts-=1}
        if greeting {greetingStatus="正在准备问候…"}
        lastResult=["started":true,"played":false,"demo":demo,"gain":gain,"microphone_opened":microphoneClip != nil,"auto_play":options.autoPlay,"greeting":greetingMode,"automatic_greeting":greeting,"greeting_preparation":greetingPreparation]
        lastResult["request_started_at"]=requestBegan.timeIntervalSince1970
        lastResult["task_notice"]=taskNotice != nil
        recordResult()
        let selected=route
        if silenceOnly {
            do {
                let p=HeadphonePCMPlayer(gate:gate,ticket:ticket,route:selected,samples:Array(repeating:0,count:48000),gain:0)
                try p.start();player=p;message="无声设备绑定测试";lastResult["silence_only"]=true
            } catch {busy=false;message="耳机绑定测试失败，保持静音。";lastResult["error"]="audio_binding_failed"}
            return
        }
        message=taskNotice != nil ? "正在准备任务完成提醒…":greetingPreparation ? "静音准备问候，不会现在播放…":greetingMode ? "正在用原厂声音准备一句问候…":"正在等待原厂回复…"
        let greetingIndex=selectedGreetingLine
        let chat = !demo && !greetingMode && taskNotice == nil
        if chat {conversation.begin(id:id,text:text,voice:microphoneClip != nil)}
        do {
            let data=try Data(contentsOf:root.appendingPathComponent("voice-runtime.json"))
            guard let settings=try JSONSerialization.jsonObject(with:data) as? [String:String],
                  let python=settings["python"],let worker=settings["worker"],let ffmpeg=settings["ffmpeg"],let opus=settings["libopus"],
                  [python,worker,ffmpeg,opus].allSatisfy({FileManager.default.fileExists(atPath:$0)}) else {throw NSError(domain:"voice-runtime",code:1)}
            let child=Process();child.executableURL=URL(fileURLWithPath:python);child.arguments=[worker]
            let output=Pipe(),input=Pipe(),errors=Pipe();child.standardInput=input;child.standardOutput=output;child.standardError=errors
            process=child
            try child.run()
            var payload:[String:Any]=["ffmpeg":ffmpeg,"libopus":opus,"rate":options.rate,"pitch":options.pitch,"stream":shouldStream,"subtitle_events":chat]
            if let clip=microphoneClip {
                payload["audio_pcm16"]=clip.pcm.base64EncodedString();payload["sample_rate"]=clip.sampleRate
                payload["transcript_events"]=true
                payload["local_commands"]=fromVoiceMode && commandsEnabled
            } else {payload["text"]=text}
            if let notice=taskNotice {payload["expected_speech"]=notice.line}
            let request=try JSONSerialization.data(withJSONObject:payload)
            // 麦克风包可大于 pipe 容量；后台写入，停止按钮和路由保护仍可及时处理。
            DispatchQueue.global(qos:.userInitiated).async {
                defer {try? input.fileHandleForWriting.close()}
                try? input.fileHandleForWriting.write(contentsOf:request)
            }
            if chat && microphoneClip == nil {
                submittedDraft=draft;draft=""
            }
            let eventReader=VoiceWorkerEventReader(handle:errors.fileHandleForReading,onSubtitle:{ [weak self] sequence,text in
                guard chat else {return}
                DispatchQueue.main.async {self?.receiveSubtitle(text,sequence:sequence,id:id,ticket:ticket,selected:selected)}
            },onTranscript:{ [weak self] text in
                guard microphoneClip != nil else {return}
                DispatchQueue.main.async {
                    guard let self=self,self.requestID==id,self.gate.accepts(ticket),self.ready,self.route==selected else {return}
                    self.conversation.transcribe(id:id,text:text)
                }
            })
            DispatchQueue.global(qos:.userInitiated).async { [weak self] in
                // worker限制原始45秒、调速后60秒；诊断不含回复正文。
                var pcm=Data(),chunks=VoicePCMChunks(),validStream=true
                do {
                    while true {
                        let part=output.fileHandleForReading.availableData
                        if part.isEmpty {break}
                        let samples=try chunks.append(part)
                        pcm.append(part)
                        if greetingMode && pcm.count>48000*10*4 {throw NSError(domain:"voice-greeting-length",code:1)}
                        if taskNotice != nil && pcm.count>48000*12*4 {throw NSError(domain:"voice-task-notice-length",code:1)}
                        if shouldStream && !samples.isEmpty {
                            DispatchQueue.main.async {self?.receiveStream(samples,id:id,ticket:ticket,selected:selected)}
                        }
                    }
                    try chunks.finish(allowEmpty:fromVoiceMode) // 本地指令只返回回执事件，没有语音PCM。
                } catch {validStream=false;if child.isRunning {child.terminate()}}
                let eventResult=eventReader.wait()
                child.waitUntilExit()
                let completePCM=pcm,validPCM=validStream
                DispatchQueue.main.async {
                    guard let self=self,self.requestID==id else {return}
                    self.process=nil;self.refreshRoute()
                    guard self.requestID==id,self.gate.accepts(ticket),self.ready else {self.cancel("回复已过期，未播放。");return}
                    let result=eventResult.result
                    if let command=eventResult.command {
                        guard fromVoiceMode,self.commandsEnabled,self.voiceMode.running,
                              child.terminationStatus==0,eventResult.valid,validPCM,completePCM.isEmpty,
                              result["ok"] as? Bool == true,result["local_command"] as? Bool == true,
                              result["streaming"] as? Bool == false,let perform=self.onLocalCommand else {
                            self.cancel("指令未通过检查，没有执行。",failed:true);return
                        }
                        self.message="正在等待机器人确认…";self.voiceModeNote=self.message
                        self.conversation.append(id:id,sequence:1,text:self.message)
                        perform(command){[weak self] outcome in
                            guard let self=self,self.requestID==id else{return}
                            self.busy=false;self.submittedDraft=nil
                            self.message=outcome.message;self.voiceModeNote=outcome.message
                            self.conversation.finishCommand(id:id,outcome:outcome)
                            self.lastResult["local_command"]=true;self.lastResult["command_confirmed"]=outcome.ok
                            self.recordResult()
                            if self.voiceMode.running {self.voiceMode.set(.listening)}
                        }
                        return
                    }
                    if !result.isEmpty {
                        for key in ["error_code","stage","audio_packets","pcm_frames","elapsed_seconds","packet_gaps","voice_id_observed","playback_rate","playback_pitch","first_audio_seconds","input_ready_seconds","connected_seconds","input_upload_seconds","upload_interval_ms","input_guard_ms","stt_seconds","tts_start_seconds","streaming","stt_received","tts_started","tts_stopped","missing_audio_packets","concealed_audio_packets","subtitle_events"] {self.lastResult[key]=result[key]}
                    }
                    let noticeVerified=taskNotice == nil || VoiceTaskNotice.acceptsWorkerReply(result)
                    if taskNotice != nil {self.lastResult["notice_text_verified"]=noticeVerified}
                    guard child.terminationStatus==0,validPCM,eventResult.valid,noticeVerified,!completePCM.isEmpty,result["ok"] as? Bool == true else {
                        let partial=self.player != nil
                        let code=self.lastResult["error_code"] as? String
                        let reason:String
                        switch code {
                        case "notice_text_mismatch":reason="原厂返回的文字与任务提醒不一致，已静音跳过。"
                        case "recognition_timeout":reason="原厂未确认收到这句话，已结束等待。"
                        case "first_audio_timeout":reason="原厂已开始处理，但语音迟迟未返回，已结束等待。"
                        case "service_closed_without_reply":reason="原厂提前结束了会话，已停止等待。"
                        case "service_error":reason="原厂服务返回异常，已停止等待。"
                        case "previous_session_busy":reason="上一条语音连接还未退出，请稍后重试。"
                        case "audio_stalled":reason="语音传输停滞，已停止播放。"
                        case "audio_packet_gap":reason="语音丢包较多，已停止。"
                        case "reply_incomplete" where !partial:reason="原厂暂未返回完整语音。"
                        default:reason=taskNotice != nil ? "任务提醒未通过完整核对，已静音跳过。":partial ? "语音传输中断，已停止播放。":"语音请求未完成。"
                        }
                        self.cancel(reason + (taskNotice != nil ? "":fromVoiceMode ? "点重试后可以继续聊。":microphoneClip != nil ? "请重新按住说话。":chat ? "原文已恢复，可回车重试。":"可以稍后重试。"),failed:true)
                        self.lastResult["error"]="factory_reply_failed";self.lastResult["partial_audio_started"]=partial
                        self.recordResult()
                        if greetingPreparation {self.greetingStatus=self.greetingPreparationAttempts>0 ? "问候准备未完成，稍后静音重试":"问候暂未就绪，下次新连接时再准备"};return
                    }
                    self.lastResult["receive_complete_seconds"]=Date().timeIntervalSince(self.requestBegan)
                    self.recordResult()
                    self.submittedDraft=nil
                    if shouldStream {
                        if let player=self.player {player.finishInput()}
                        else {
                            let short=self.streamWaiting;self.streamWaiting=[]
                            self.play(PendingVoiceReply(samples:short,route:selected,ticket:ticket,expires:Date().addingTimeInterval(60)),gain:gain)
                        }
                        if greetingPreview {self.greetingLine=greetingIndex;self.preferences?.set(greetingIndex,forKey:"greetingLine")}
                        return
                    }
                    var samples=Array(repeating:Float(0),count:completePCM.count/4)
                    _=samples.withUnsafeMutableBytes {completePCM.copyBytes(to:$0)}
                    if greetingMode && samples.count>48000*10 {self.cancel("问候过长，已跳过。");self.lastResult["error"]="greeting_too_long";return}
                    if greetingPreparation {
                        guard self.greetingBank.insert(PreparedVoiceGreeting(index:greetingIndex,samples:samples,rate:options.rate,pitch:options.pitch,created:Date()),now:Date()) else {
                            self.busy=false;self.preparingGreeting=false;self.message="问候音频未通过检查，保持静音。"
                            self.lastResult["error"]="greeting_audio_rejected";return
                        }
                        self.greetingReadyCount=self.greetingBank.clips.count;self.busy=false;self.preparingGreeting=false
                        self.greetingPreparationAttempts=2
                        self.nextGreetingPreparation=Date().addingTimeInterval(2)
                        self.greetingStatus="\(self.greetingReadyCount) 句已准备好，下次连接直接问候"
                        self.message="问候已静音准备好，仅在下次连接时播放。";return
                    }
                    if greetingPreview {self.greetingLine=greetingIndex;self.preferences?.set(greetingIndex,forKey:"greetingLine")}
                    let reply=PendingVoiceReply(samples:samples,route:selected,ticket:ticket,expires:Date().addingTimeInterval(60))
                    if greetingMode || demo || options.autoPlay {self.play(reply,gain:gain)}
                    else {
                        self.busy=false;self.pending=reply;self.lastResult["awaiting_manual_play"]=true
                        self.conversation.finish(id:id,state:.ready)
                        self.message="回复已就绪，点播放才出声 · 仅保留 60 秒。"
                    }
                }
            }
        } catch {cancel("语音接入尚未配置或启动失败，保持静音。",failed:true);lastResult["error"]="runtime_unavailable"}
    }
    func stop() {
        cancel("");timer?.invalidate();timer=nil;watcher=nil
        greetingBank.clear();greetingReadyCount=0;conversation.clear();draft=""
        for token in tokens {NSWorkspace.shared.notificationCenter.removeObserver(token)};tokens=[]
        for token in appTokens {NotificationCenter.default.removeObserver(token)};appTokens=[]
    }
    func voiceModeCancellationSelfTest() {
        precondition(preferences == nil)
        let fake=HeadphoneRoute(id:7,uid:"test",name:"AirPods",manufacturer:"Apple",bluetooth:true,alive:true,outputChannels:2)
        let session=voiceMode.begin()
        voiceModeGate.update(enabled:true,approved:fake.uid,route:fake)
        gate.update(enabled:true,approved:fake.uid,route:fake)
        let micTicket=voiceModeGate.ticket()!,outputTicket=gate.ticket()!,oldRequest=requestID
        cancel("",preserveVoiceMode:true)
        precondition(voiceMode.accepts(session) && voiceModeGate.accepts(micTicket))
        precondition(!gate.accepts(outputTicket) && requestID != oldRequest)
        exitVoiceMode()
        precondition(!voiceMode.visible && !voiceModeGate.accepts(micTicket) && !hasWork)
        _=voiceMode.begin();cancel("模拟断连")
        precondition(voiceMode.phase == .ended && !voiceMode.running && !hasWork)
        voiceMode.close()
        let ringing=voiceMode.begin();conversation.beginCall()
        voiceModeConnection.begin(token:ringing,now:0)
        voiceModeTone=HeadphonePCMPlayer(gate:gate,ticket:outputTicket,route:fake,samples:VoiceCallConnection.samples(),gain:1)
        exitVoiceMode()
        precondition(voiceModeTone == nil && !conversation.callActive)
        precondition(voiceModeConnection.poll(token:ringing,valid:true,finished:true,now:1) == .cancelled)
    }
    func lastCancellationCheck() {
        lastResult["cancelled_and_not_resumed"] = !hasWork && player == nil && process == nil
    }
}

func voiceSettingsSelfTest() {
    var value=VoiceSoundSettings()
    precondition(value.preset=="原声" && value.autoPlay)
    value.usePreset("舒缓");precondition(value.rate==0.9 && value.pitch == -1)
    value.usePreset("轻快");precondition(value.rate==1.1 && value.pitch==1)
    value.rate=1.25;precondition(value.preset=="自定义")
    let bad=VoiceSoundSettings(rate:99,pitch: -99).normalized()
    precondition(bad.rate==1.25 && bad.pitch == -2)
    // 独立测试域，不写真实音量、开关或耳机绑定。
    let name="io.github.prozaclaputa.weiguang.voice-test.\(UUID())",p=UserDefaults(suiteName:name)!
    defer {p.removePersistentDomain(forName:name)}
    p.set(5,forKey:"volume");p.set("test-only",forKey:"approvedUID")
    var saved=VoiceSoundSettings.load(p);precondition(saved==VoiceSoundSettings()) // 旧5%偏好不再衰减播放。
    saved.rate=0.85;saved.pitch=0.5;saved.autoPlay=false;saved.save(p)
    precondition(VoiceSoundSettings.load(p)==saved && p.string(forKey:"approvedUID")=="test-only")
    let gate=VoiceGate(),route=HeadphoneRoute(id:7,uid:"test-only",name:"AirPods",manufacturer:"Apple",bluetooth:true,alive:true,outputChannels:2)
    gate.update(enabled:true,approved:route.uid,route:route)
    let ticket=gate.ticket()!,now=Date()
    let reply=PendingVoiceReply(samples:[0],route:route,ticket:ticket,expires:now.addingTimeInterval(60))
    precondition(reply.isValid(gate:gate,route:route,now:now))
    precondition(!reply.isValid(gate:gate,route:route,now:now.addingTimeInterval(61)))
    precondition(!reply.isValid(gate:gate,route:HeadphoneRoute(),now:now))
    gate.revoke();gate.update(enabled:true,approved:route.uid,route:route)
    precondition(!reply.isValid(gate:gate,route:route,now:now))
    let voice=VoiceCompanion(persist:false)
    precondition(!voice.greetingEnabled && voice.greetingMinutes==1 && !voice.taskNoticeEnabled)
    voice.draft="尚未发送的内容"
    voice.setTaskNoticeEnabled(true);precondition(voice.taskNoticeEnabled && !voice.enabled)
    voice.request(taskNotice:VoiceTaskNotice(events:[])) // 总开关关闭时不启动服务、不清草稿、不进入聊天。
    precondition(!voice.busy && voice.draft=="尚未发送的内容" && voice.conversation.turns.isEmpty)
    voice.setTaskNoticeEnabled(false)
    voice.setGreetingEnabled(true);voice.setGreetingMinutes(15)
    voice.setGreetingMinutes(2);precondition(voice.greetingMinutes==15)
    voice.changeSound{$0=saved};precondition(!voice.sound.autoPlay)
    voice.restoreSound();precondition(voice.sound.preset=="原声" && voice.sound.autoPlay && !voice.enabled)
    precondition(voice.greetingEnabled && voice.greetingMinutes==15 && !voice.taskNoticeEnabled)
    voice.stop()
}
