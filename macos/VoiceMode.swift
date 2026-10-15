import Foundation
import SwiftUI
import AppKit

// 本地分句：短促碰撞声不提交；保留320ms句首，停顿约1秒后自动发送。
// 所有音频只在已进入语音模式的内存中，退出即清空。
struct VoiceSentenceDetector {
    enum Event {case began, sentence(VoiceMicrophoneClip), tooLong}
    private var sampleRate=0
    private var partial:[Int16]=[]
    private var preRoll:[Int16]=[]
    private var utterance:[Int16]=[]
    private var candidate=0,quiet=0,voiced=0
    private var noise=0.0015
    private(set) var speaking=false
    private(set) var level:Float=0
    mutating func reset() {self=Self()}
    mutating func feed(_ clip:VoiceMicrophoneClip,replying:Bool)->[Event] {
        guard [8000,16000,24000,32000,44100,48000].contains(clip.sampleRate),clip.pcm.count%2==0,
              clip.pcm.count<=clip.sampleRate*2*2 else {reset();return []}
        if sampleRate != clip.sampleRate {reset();sampleRate=clip.sampleRate}
        let frameSize=sampleRate/50
        var samples=Array(repeating:Int16(0),count:clip.pcm.count/2)
        _=samples.withUnsafeMutableBytes{clip.pcm.copyBytes(to:$0)}
        partial.append(contentsOf:samples)
        var events:[Event]=[],offset=0
        while partial.count-offset>=frameSize {
            let frame=Array(partial[offset..<offset+frameSize]);offset+=frameSize
            let power=frame.reduce(0.0){$0+pow(Double($1)/32768,2)}
            let rms=sqrt(power/Double(frame.count));level=Float(min(1,rms*12))
            // 非说话帧慢速追踪底噪；回复期间提高门槛，避免耳机轻微漏音触发自问自答。
            let threshold=max(replying ? 0.009:0.005,noise*(replying ? 4.0:3.0))
            let active=rms>threshold
            if !speaking {
                if !active {noise=min(0.012,noise*0.97+rms*0.03)}
                preRoll.append(contentsOf:frame)
                if preRoll.count>sampleRate*32/100 {preRoll.removeFirst(preRoll.count-sampleRate*32/100)}
                candidate=active ? candidate+1:0
                if candidate >= (replying ? 14:10) {
                    speaking=true;utterance=preRoll;preRoll=[];voiced=candidate;quiet=0;events.append(.began)
                }
            } else {
                utterance.append(contentsOf:frame)
                if active {voiced+=1;quiet=0} else {quiet+=1}
                if utterance.count>=sampleRate*28 {
                    reset();events.append(.tooLong);return events
                }
                if quiet>=50 {
                    // 末尾保留160ms，去掉多余空白；不把静默填满的窗口发往服务器。
                    let trim=min(utterance.count,frameSize*42)
                    utterance.removeLast(trim)
                    if voiced>=10 {
                        let data=utterance.withUnsafeBytes{Data($0)}
                        events.append(.sentence(VoiceMicrophoneClip(pcm:data,sampleRate:sampleRate)))
                    }
                    utterance=[];speaking=false;quiet=0;voiced=0;candidate=0
                }
            }
        }
        partial.removeFirst(offset)
        return events
    }
}

// UI会话和异步采集共用代次；暂停/退出后，迟到的初始化不能重新开麦。
struct VoiceModeState {
    enum Phase {case off,starting,listening,hearing,waiting,replying,paused,ended}
    private(set) var id=UUID()
    private(set) var phase=Phase.off
    var visible:Bool {phase != .off}
    var running:Bool {visible && phase != .paused && phase != .ended}
    var title:String {
        switch phase {
        case .off:return "语音模式"
        case .starting:return "正在接通"
        case .listening:return "我在听"
        case .hearing:return "你说，我听着"
        case .waiting:return "想一想，马上回来"
        case .replying:return "微光正在说"
        case .paused:return "已暂停"
        case .ended:return "对话已停止"
        }
    }
    mutating func begin()->UUID {id=UUID();phase = .starting;return id}
    func accepts(_ token:UUID)->Bool {running && id==token}
    mutating func set(_ value:Phase) {guard running else {return};phase=value}
    mutating func pause() {id=UUID();phase = .paused}
    mutating func end() {id=UUID();phase = .ended}
    mutating func close() {id=UUID();phase = .off}
}

// 接通音沿用显式绑定 AirPods 的播放器；完成并排空后才允许开麦。
struct VoiceCallConnection {
    enum Action {case waiting,openMicrophone,cancelled}
    private var token:UUID?
    private var beganAt=0.0
    private var finishedAt:Double?
    mutating func begin(token:UUID,now:Double) {self.token=token;beganAt=now;finishedAt=nil}
    mutating func cancel() {token=nil;finishedAt=nil}
    mutating func poll(token:UUID,valid:Bool,finished:Bool,now:Double)->Action {
        guard self.token==token,valid,now-beganAt<4 else {cancel();return .cancelled}
        guard finished else {return .waiting}
        if finishedAt == nil {finishedAt=now}
        guard now-finishedAt!>=0.2 else {return .waiting}
        cancel();return .openMicrophone
    }
    static func samples()->[Float] {
        let rate=48000,pulse=9600,gap=7680,tail=4800
        var pcm=Array(repeating:Float(0),count:pulse*2+gap+tail)
        for start in [0,pulse+gap] {
            for i in 0..<pulse {
                let envelope=min(1,Double(min(i,pulse-1-i))/480)
                pcm[start+i]=Float(sin(2*Double.pi*440*Double(i)/Double(rate))*0.16*max(0,envelope))
            }
        }
        return pcm
    }
}

// 内容增高和窗口布局变化不当作用户上翻；只有滚动位置变化才改变跟随意图。
struct VoiceCallScroll:Equatable {
    private(set) var followsLatest=true
    private var height:CGFloat = -1
    private var viewport:CGFloat = -1
    mutating func observe(top:CGFloat,height:CGFloat,viewport:CGFloat)->Bool {
        let resized=abs(self.height-height)>0.5 || abs(self.viewport-viewport)>0.5
        self.height=height;self.viewport=viewport
        if resized {return followsLatest}
        followsLatest=top+height<=viewport+24 && top+height>=0
        return false
    }
    mutating func follow() {followsLatest=true}
}

// SwiftUI ScrollView 在部分 macOS 版本不向外传递几何偏好，直接观察其原生裁剪区域。
private struct VoiceCallScrollProbe:NSViewRepresentable {
    var changed:(CGFloat,CGFloat,CGFloat)->Void
    func makeNSView(context:Context)->Probe {let view=Probe();view.changed=changed;return view}
    func updateNSView(_ view:Probe,context:Context) {view.changed=changed;view.scheduleAttach()}
    final class Probe:NSView {
        var changed:((CGFloat,CGFloat,CGFloat)->Void)?
        private weak var observed:NSScrollView?
        private var tokens:[NSObjectProtocol]=[]
        private var last:[CGFloat]=[]
        override func viewDidMoveToWindow() {super.viewDidMoveToWindow();scheduleAttach()}
        override func viewDidMoveToSuperview() {super.viewDidMoveToSuperview();scheduleAttach()}
        func scheduleAttach() {DispatchQueue.main.async { [weak self] in self?.attach()}}
        private func attach() {
            guard window != nil,let scroll=enclosingScrollView,let document=scroll.documentView else {return}
            if observed !== scroll {
                for token in tokens {NotificationCenter.default.removeObserver(token)}
                tokens=[];observed=scroll;last=[]
                scroll.contentView.postsBoundsChangedNotifications=true
                document.postsFrameChangedNotifications=true
                for (name,object) in [(NSView.boundsDidChangeNotification,scroll.contentView),(NSView.frameDidChangeNotification,document)] {
                    tokens.append(NotificationCenter.default.addObserver(forName:name,object:object,queue:.main) { [weak self] _ in
                        DispatchQueue.main.async {self?.sample()}
                    })
                }
            }
            sample()
        }
        private func sample() {
            guard let scroll=observed,let document=scroll.documentView else {return}
            let visible=scroll.documentVisibleRect,height=document.bounds.height,viewport=visible.height
            let top=document.isFlipped ? document.bounds.minY-visible.minY:visible.maxY-document.bounds.maxY
            let reading=[top,height,viewport]
            guard height>0,viewport>0,reading != last else {return}
            last=reading;changed?(top,height,viewport)
        }
        deinit {for token in tokens {NotificationCenter.default.removeObserver(token)}}
    }
}

struct VoiceWaitingBubble:View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body:some View {
        TimelineView(.periodic(from:.now,by:0.25)) {timeline in
            HStack(spacing:5) {
                ForEach(0..<3) {index in
                    Circle().fill(Color.white.opacity(reduceMotion || Int(timeline.date.timeIntervalSince1970*4)%3==index ? 0.8:0.28))
                        .frame(width:5,height:5)
                }
            }.frame(height:18)
        }.accessibilityElement(children:.ignore).accessibilityLabel("微光正在等待回复")
    }
}

struct VoiceCallHistoryView:View {
    let turns:[VoiceTurn]
    @State private var scroll=VoiceCallScroll()
    var body:some View {
        GeometryReader { _ in
            ScrollViewReader {proxy in
                ScrollView {
                    VStack(alignment:.leading,spacing:22) {
                        ForEach(turns) {turn in
                            VStack(alignment:.leading,spacing:12) {
                                HStack(alignment:.top) {
                                    Spacer(minLength:54)
                                    Text(verbatim:turn.user).font(.system(size:14)).lineSpacing(4).textSelection(.enabled)
                                        .foregroundColor(Color(red:0.05,green:0.16,blue:0.15))
                                        .padding(.horizontal,14).padding(.vertical,10)
                                        .background(Color(red:0.57,green:0.85,blue:0.78),in:RoundedRectangle(cornerRadius:14))
                                        .fixedSize(horizontal:false,vertical:true)
                                        .accessibilityLabel("你：\(turn.user)")
                                }
                                HStack(alignment:.top) {
                                    VStack(alignment:.leading,spacing:7) {
                                        Group {
                                            if turn.waitingForText {VoiceWaitingBubble()}
                                            else if !turn.reply.isEmpty {
                                                Text(verbatim:turn.reply).font(.system(size:14)).lineSpacing(4).textSelection(.enabled)
                                            } else {
                                                Text(turn.state == .cancelled ? "已停止":turn.state == .failed ? "这次没有收到回复":"本次回复没有字幕")
                                                    .font(.system(size:12)).foregroundColor(.white.opacity(0.5))
                                            }
                                        }.padding(.horizontal,14).padding(.vertical,11)
                                            .background(.white.opacity(0.075),in:RoundedRectangle(cornerRadius:14))
                                        if turn.state == .failed || turn.state == .cancelled {
                                            Text(turn.detail.isEmpty ? turn.state.label:turn.detail)
                                                .font(.system(size:11)).foregroundColor(.white.opacity(0.45)).padding(.leading,4)
                                        }
                                    }.foregroundColor(.white.opacity(0.9)).fixedSize(horizontal:false,vertical:true)
                                    Spacer(minLength:54)
                                }
                            }.id(turn.id)
                        }
                        Color.clear.frame(height:1).id("call-bottom")
                    }.padding(.vertical,12).padding(.horizontal,4)
                        .background(VoiceCallScrollProbe {top,height,visible in
                            if scroll.observe(top:top,height:height,viewport:visible) {proxy.scrollTo("call-bottom",anchor:.bottom)}
                        })
                }
                    .onChange(of:turns.last) {_ in
                        if scroll.followsLatest {proxy.scrollTo("call-bottom",anchor:.bottom)}
                    }
                    .overlay(alignment:.bottomTrailing) {
                        if !scroll.followsLatest {
                            Button {scroll.follow();proxy.scrollTo("call-bottom",anchor:.bottom)} label:{Image(systemName:"arrow.down").frame(width:30,height:30)}
                                .buttonStyle(.plain).background(Color(white:0.2),in:Circle()).padding(6)
                                .help("回到最新消息").accessibilityLabel("回到最新消息")
                        }
                    }
            }
        }
    }
}

struct VoiceModeView:View {
    @ObservedObject var voice:VoiceCompanion
    var compact=false
    var onEnd:(()->Void)?
    func endCall() {if let onEnd=onEnd {onEnd()} else {voice.exitVoiceMode()}}
    var phase:VoiceModeState.Phase {voice.voiceMode.phase}
    var inactive:Bool {phase == .off || phase == .paused || phase == .ended}
    var accent:Color {inactive ? .gray:Color(red:0.47,green:0.84,blue:0.79)}
    var microphoneAction:String {phase == .off ? "开始":phase == .ended ? "重试":inactive ? "继续":"暂停"}
    var statusNote:String {phase == .off ? (voice.message.isEmpty ? voice.routeText:voice.message):voice.voiceModeNote}
    var body:some View {
        VStack(spacing:0) {
            HStack(spacing:12) {
                face.frame(width:54,height:54)
                VStack(alignment:.leading,spacing:5) {
                    Text("微光").font(.system(size:17,weight:.medium)).foregroundColor(.white)
                    Text(phase == .off ? "尚未接通":voice.voiceMode.title).font(.system(size:12)).foregroundColor(accent)
                }
                Spacer()
                Label("仅 AirPods",systemImage:"airpodspro").font(.system(size:11)).foregroundColor(.white.opacity(0.4))
            }.padding(.bottom,16)
            Rectangle().fill(.white.opacity(0.055)).frame(height:1)
            if voice.conversation.callTurns.isEmpty {
                VStack(spacing:12) {
                    Spacer()
                    Image(systemName:phase == .starting ? "phone.arrow.up.right":"waveform").font(.system(size:26,weight:.light)).foregroundColor(accent.opacity(0.65))
                    Text(phase == .starting ? "嘟，嘟…":inactive ? "聊天记录会显示在这里":"开口说话就好")
                        .font(.system(size:14)).foregroundColor(.white.opacity(0.4))
                    if voice.commandsEnabled && !inactive && phase != .starting {
                        Text("也可以说：开始25分钟番茄钟").font(.system(size:11)).foregroundColor(.white.opacity(0.3))
                    }
                    Spacer()
                }.frame(maxWidth:.infinity)
            } else {VoiceCallHistoryView(turns:voice.conversation.callTurns).padding(.vertical,8)}
            if inactive && !statusNote.isEmpty {
                Text(statusNote).font(.system(size:12)).foregroundColor(.white.opacity(0.55))
                    .multilineTextAlignment(.center).fixedSize(horizontal:false,vertical:true).padding(.vertical,12)
            }
            HStack(spacing:36) {
                callControl(microphoneAction,systemImage:inactive ? "mic.fill":"mic.slash.fill",
                            foreground:.white.opacity(0.9),background:.white.opacity(0.09),
                            hint:inactive ? "打开麦克风，继续聊天":"暂停回复并关闭麦克风") {
                                if phase == .off {voice.startVoiceMode()} else {voice.toggleVoiceModePause()}
                            }.disabled(inactive && !voice.ready)
                callControl("结束",systemImage:"phone.down.fill",
                            foreground:Color(red:1,green:0.64,blue:0.63),background:Color(red:0.27,green:0.12,blue:0.13),
                            hint:"结束语音并关闭麦克风（Esc）") {endCall()}
            }.padding(.top,14)
            if compact {Text("⌃⌥空格 / Esc 结束").font(.system(size:10)).foregroundColor(.white.opacity(0.25)).padding(.top,12)}
        }.padding(compact ? 18:22).frame(width:compact ? 400:480,height:compact ? 520:640)
            .background(Color(red:0.04,green:0.055,blue:0.065)).preferredColorScheme(.dark)
            .onExitCommand{endCall()}
    }
    private var face:some View {
        ZStack {
            RoundedRectangle(cornerRadius:19).fill(accent.opacity(0.08))
                .scaleEffect(1+CGFloat(voice.voiceModeLevel)*0.08).animation(.easeOut(duration:0.14),value:voice.voiceModeLevel)
            VStack(spacing:9) {
                HStack(spacing:13) {
                    Capsule().fill(accent).frame(width:9,height:inactive ? 2:3)
                    Capsule().fill(accent).frame(width:9,height:inactive ? 2:3)
                }
                SmileShape().stroke(accent,style:StrokeStyle(lineWidth:1.8,lineCap:.round)).frame(width:12,height:4)
            }
        }.accessibilityHidden(true)
    }
    private func callControl(_ title:String,systemImage:String,foreground:Color,background:Color,
                             hint:String,action:@escaping ()->Void)->some View {
        Button(action:action) {
            VStack(spacing:9) {
                Image(systemName:systemImage).font(.system(size:20,weight:.medium))
                    .foregroundColor(foreground).frame(width:54,height:54).background(background,in:Circle())
                Text(title).font(.system(size:11)).foregroundColor(.white.opacity(0.55))
            }.frame(width:64).contentShape(Rectangle())
        }.buttonStyle(.plain).help(hint).accessibilityLabel(title).accessibilityHint(hint)
    }
    struct SmileShape:Shape {
        func path(in rect:CGRect)->Path {var p=Path();p.move(to:CGPoint(x:0,y:1));p.addQuadCurve(to:CGPoint(x:rect.width,y:1),control:CGPoint(x:rect.midX,y:rect.height*1.7));return p}
    }
}

func voiceModeSelfTest() {
    var call=VoiceCallConnection();let callToken=UUID()
    call.begin(token:callToken,now:0)
    precondition(call.poll(token:callToken,valid:true,finished:false,now:0.5) == .waiting)
    precondition(call.poll(token:callToken,valid:true,finished:true,now:0.8) == .waiting)
    precondition(call.poll(token:callToken,valid:true,finished:true,now:1.1) == .openMicrophone)
    precondition(call.poll(token:callToken,valid:true,finished:true,now:1.3) == .cancelled) // 最多开麦一次。
    call.begin(token:callToken,now:0);call.cancel()
    precondition(call.poll(token:callToken,valid:true,finished:true,now:1) == .cancelled)
    call.begin(token:callToken,now:0)
    precondition(call.poll(token:UUID(),valid:true,finished:true,now:1) == .cancelled)
    call.begin(token:callToken,now:0)
    precondition(call.poll(token:callToken,valid:false,finished:true,now:1) == .cancelled)
    call.begin(token:callToken,now:0)
    precondition(call.poll(token:callToken,valid:true,finished:false,now:4) == .cancelled)
    let tone=VoiceCallConnection.samples()
    precondition(tone.count==31680 && tone.allSatisfy{$0.isFinite && abs($0)<=0.16})
    precondition(tone[0..<9600].contains{abs($0)>0.1} && tone[17280..<26880].contains{abs($0)>0.1})
    precondition(tone[9600..<17280].allSatisfy{$0==0} && tone[26880...].allSatisfy{$0==0})
    var scroll=VoiceCallScroll()
    precondition(scroll.observe(top:0,height:800,viewport:400))
    _=scroll.observe(top:-400,height:800,viewport:400);precondition(scroll.followsLatest)
    _=scroll.observe(top:-200,height:800,viewport:400);precondition(!scroll.followsLatest)
    precondition(!scroll.observe(top:-200,height:900,viewport:400) && !scroll.followsLatest)
    scroll.follow();precondition(scroll.observe(top:-200,height:1000,viewport:400))
    func pcm(_ amplitude:Int16,_ ms:Int,rate:Int=16000)->VoiceMicrophoneClip {
        let values=(0..<(rate*ms/1000)).map {i in i%2==0 ? amplitude : -amplitude}
        return VoiceMicrophoneClip(pcm:values.withUnsafeBytes{Data($0)},sampleRate:rate)
    }
    var detector=VoiceSentenceDetector()
    for _ in 0..<200 {precondition(detector.feed(pcm(20,150),replying:false).isEmpty)} // 长时间安静不发送。
    precondition(detector.feed(pcm(9000,80),replying:false).isEmpty) // 单次敲击不构成句子。
    precondition(detector.feed(pcm(0,500),replying:false).isEmpty)
    let began=detector.feed(pcm(3500,300),replying:false)
    precondition(began.contains{if case .began=$0{return true};return false})
    precondition(detector.feed(pcm(0,600),replying:false).isEmpty) // 思考时短停顿不断句。
    precondition(detector.feed(pcm(3500,300),replying:false).isEmpty)
    let complete=detector.feed(pcm(0,1100),replying:false)
    guard case let .sentence(clip)=complete.last! else {preconditionFailure()}
    precondition(clip.seconds>1 && clip.seconds<2 && !detector.speaking)
    precondition(detector.feed(pcm(0,1200),replying:false).isEmpty) // 同一句不重发。
    let interrupt=detector.feed(pcm(3500,320),replying:true)
    precondition(interrupt.contains{if case .began=$0{return true};return false})
    detector.reset();precondition(detector.feed(pcm(0,1200),replying:false).isEmpty) // 取消清除半句话。
    for rate in [8000,16000,24000,32000,44100,48000] {
        detector.reset();_=detector.feed(pcm(3500,400,rate:rate),replying:false)
        let done=detector.feed(pcm(0,1200,rate:rate),replying:false)
        precondition(done.contains{if case .sentence=$0{return true};return false})
    }
    detector.reset();var limit=false
    for _ in 0..<29 {limit = detector.feed(pcm(3500,1000),replying:false).contains{if case .tooLong=$0{return true};return false} || limit}
    precondition(limit)
    var mode=VoiceModeState();precondition(!mode.visible)
    let first=mode.begin();precondition(mode.accepts(first));mode.pause();precondition(!mode.accepts(first) && !mode.running)
    let second=mode.begin();mode.set(.replying);precondition(mode.accepts(second));mode.end();precondition(!mode.accepts(second))
    mode.close();precondition(!mode.visible)
    VoiceCompanion(persist:false).voiceModeCancellationSelfTest()
    print("voice mode speech, call cue, cancellation, history scroll and late-callback checks passed")
}
