import SwiftUI
import AppKit

struct VoiceSettingsView:View {
    @ObservedObject var voice:VoiceCompanion
    @Environment(\.presentationMode) var presentation
    @State private var page=0
    var editingBlocked:Bool {(voice.busy && !voice.preparingGreeting) || voice.microphoneState.active}
    func binding<Value>(_ key:WritableKeyPath<VoiceSoundSettings,Value>)->Binding<Value> {
        Binding(get:{voice.sound[keyPath:key]},set:{new in voice.changeSound{$0[keyPath:key]=new}})
    }
    func section<Content:View>(@ViewBuilder content:()->Content)->some View {
        VStack(alignment:.leading,spacing:17,content:content).padding(18).frame(maxWidth:.infinity,alignment:.leading)
            .background(Color.white.opacity(0.04),in:RoundedRectangle(cornerRadius:16))
            .overlay(RoundedRectangle(cornerRadius:16).stroke(Color.white.opacity(0.06)))
    }
    func hint(_ text:String)->some View {Text(text).font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)}
    var body:some View {
        VStack(alignment:.leading,spacing:0) {
            HStack {
                VStack(alignment:.leading,spacing:6) {Text("声音设置").font(.system(size:24,weight:.medium));Label("仅 AirPods · 音量跟随耳机",systemImage:"airpodspro").font(.system(size:11)).foregroundColor(quiet)}
                Spacer()
                Button("完成"){presentation.wrappedValue.dismiss()}.buttonStyle(PanelActionStyle())
            }.padding(.bottom,20)
            PanelToggleRow(title:"语音陪伴",detail:voice.routeText,value:Binding(get:{voice.enabled},set:{voice.setEnabled($0)})).padding(.bottom,20)
            PanelChoices(labels:["声音","自动提醒","快捷操作"],selection:$page,name:"声音设置分类").padding(.bottom,16)
            ScrollView {
                VStack(alignment:.leading,spacing:14) {
                    if page==0 {soundSections}
                    else if page==1 {automaticSections}
                    else {shortcutSections}
                }.padding(.bottom,16)
            }.id(page)
            Divider().overlay(Color.white.opacity(0.04))
            HStack {
                Label("更改即时保存",systemImage:"checkmark.circle").font(.system(size:11)).foregroundColor(quiet)
                Spacer()
                if voice.busy && !voice.preparingGreeting {Button("立即停止"){voice.stopByUser()}}
                else if page==0 {Button("试听当前设置"){voice.request(demo:true)}.buttonStyle(PanelActionStyle(prominent:true)).disabled(!voice.ready)}
            }.padding(.top,14)
            if !voice.message.isEmpty {hint(voice.message).lineLimit(2).padding(.top,8)}
        }.padding(24).frame(width:540,height:720).background(Color(red:0.055,green:0.065,blue:0.075))
            .foregroundColor(.white).preferredColorScheme(.dark).accentColor(accent).buttonStyle(PanelActionStyle())
    }
    private var soundSections:some View {
        Group {
            section {
                PanelSectionHeading(title:"湾湾小何v2",detail:"已确认的原厂音色",icon:"waveform")
                PanelFold("关于原厂音色",summary:"云端角色",icon:"info.circle") {
                    hint("音色随 StackChan World 的原账号、已绑定角色设置。控制台尚未接入账号授权，不能直接切换云端说话人；App 中更换后，这里的确认名称不会自动更新。")
                }
            }
            section {
                PanelSectionHeading(title:"播放风格",detail:"原声边收边播，调整语速或音调会先收完整句。",icon:"slider.horizontal.3")
                PanelChoices(labels:VoiceSoundSettings.presets + (voice.sound.preset=="自定义" ? ["自定义"]:[]),selection:Binding(get:{VoiceSoundSettings.presets.firstIndex(of:voice.sound.preset) ?? VoiceSoundSettings.presets.count},set:{i in if i<VoiceSoundSettings.presets.count {voice.changeSound{$0.usePreset(VoiceSoundSettings.presets[i])}}}),name:"声音风格").disabled(editingBlocked)
                PanelFold("精细调整",summary:"\(String(format:"%.2f×",voice.sound.rate)) · \(voice.sound.pitch==0 ? "原调":String(format:"%+.1f 半音",voice.sound.pitch))") {
                    HStack {Text("语速");Spacer();Text(String(format:"%.2f×",voice.sound.rate)).monospacedDigit().foregroundColor(accent)}.font(.system(size:12))
                    Slider(value:binding(\.rate),in:0.8...1.25,step:0.05).accessibilityLabel("语速").disabled(editingBlocked)
                    HStack {Text("音调");Spacer();Text(voice.sound.pitch==0 ? "原调":String(format:"%+.1f 半音",voice.sound.pitch)).monospacedDigit().foregroundColor(accent)}.font(.system(size:12))
                    Slider(value:binding(\.pitch),in: -2...2,step:0.5).accessibilityLabel("音调").disabled(editingBlocked)
                    hint("舒缓稍慢、稍低；轻快稍快、稍高。这里仅处理本地播放，不更换原厂角色。")
                    Button("恢复声音默认"){voice.restoreSound()}.disabled(editingBlocked)
                }
                Divider().overlay(Color.white.opacity(0.04))
                PanelToggleRow(title:"回复自动播放",detail:"关闭后手动播放，回复保留 60 秒。",value:binding(\.autoPlay))
            }
            section {
                PanelFold("输出保护",summary:"只走已绑定 AirPods",icon:"lock.shield") {
                    hint("断连或切换输出立即停止，重连不补播。机器人与 Mac 扬声器都不会外放；只有主动进入语音时才开麦。")
                    if voice.route.isAirPods && voice.approved != voice.route.uid {Button("使用这副 AirPods"){voice.adoptCurrent()}}
                }
            }
        }
    }
    private var automaticSections:some View {
        Group {
            section {
                PanelSectionHeading(title:"欢迎回来",detail:"连接耳机，听到一句熟悉的问候。",icon:"hand.wave")
                PanelToggleRow(title:"耳机连接时问候",value:Binding(get:{voice.greetingEnabled},set:{voice.setGreetingEnabled($0)}))
                if voice.greetingEnabled {hint(voice.greetingStatus)}
                PanelFold("问候偏好",summary:"间隔至少 \(voice.greetingMinutes) 分钟",icon:"clock") {
                    Text("防重复间隔").font(.system(size:12))
                    PanelChoices(labels:["1 分钟","5 分钟","15 分钟"],selection:Binding(get:{[1,5,15].firstIndex(of:voice.greetingMinutes) ?? 1},set:{voice.setGreetingMinutes([1,5,15][$0])}),name:"问候间隔").disabled(!voice.greetingEnabled)
                    hint("文案随机轮换，提前静音准备 2 句，输出稳定 3 秒后播放；没准备好则跳过。耳机需离开输出至少 10 秒，只识别输出变化，不直接识别入耳。")
                    Button("听一句问候"){voice.request(greetingPreview:true)}.disabled(!voice.ready || editingBlocked)
                }
            }
            section {
                PanelSectionHeading(title:"任务完成",detail:"完成一轮，轻轻提醒你。",icon:"checkmark.bubble")
                PanelToggleRow(title:"任务完成时语音提醒",detail:"聊天或打字时不打扰，不补播旧提醒。",value:Binding(get:{voice.taskNoticeEnabled},set:{voice.setTaskNoticeEnabled($0)}))
                PanelFold("提醒说明",summary:"合并播报 · 只读任务名",icon:"info.circle") {
                    hint("例如「界面优化这一轮完成了，可以看看结果」。接连完成会合成一句，整句核对不符则静音跳过。默认关闭，需要控制台运行、语音开启且已绑定 AirPods 为实际输出。")
                    hint("仅将任务名交给原厂语音服务；该服务收费规则尚未确认。")
                }
            }
        }
    }
    private var shortcutSections:some View {
        Group {
            section {
                PanelSectionHeading(title:"随时开口",detail:"用一个快捷键呼出独立语音浮窗。",icon:"keyboard")
                HStack(spacing:8) {ForEach(["⌃ Control","⌥ Option","Space"],id:\.self) {key in Text(key).font(.system(size:12,weight:.medium,design:.monospaced)).padding(.horizontal,12).padding(.vertical,10).background(Color.white.opacity(0.06),in:RoundedRectangle(cornerRadius:8))}}
                PanelToggleRow(title:"全局快捷键",value:Binding(get:{voice.hotkeyEnabled},set:{voice.setHotkeyEnabled($0)}))
                hint(voice.hotkeyStatus)
                hint("再次按快捷键、Esc 或点结束，关闭浮窗和麦克风。切到其他应用时浮窗仍可见。")
            }
            section {
                PanelSectionHeading(title:"语音操作",detail:"只在主动进入语音模式后识别。",icon:"waveform.circle")
                PanelToggleRow(title:"语音操作番茄钟和便签",value:Binding(get:{voice.commandsEnabled},set:{voice.setCommandsEnabled($0)}))
                VStack(alignment:.leading,spacing:12) {
                    Label("开始 25 分钟番茄钟",systemImage:"timer")
                    Label("暂停番茄钟",systemImage:"pause")
                    Label("记个便签：下班带充电器",systemImage:"note.text")
                }.font(.system(size:12)).foregroundColor(quiet)
                hint("识别到操作后，以机器人回执显示结果；普通文字聊天不会执行指令。")
            }
        }
    }
}

private struct VoiceHistoryBottom:PreferenceKey {
    static var defaultValue:CGFloat=0
    static func reduce(value:inout CGFloat,nextValue:()->CGFloat) {value=nextValue()}
}

struct VoiceConversationView:View {
    let history:VoiceConversation
    var clear:()->Void
    @State private var followsLatest=true
    private var height:CGFloat {history.turns.count<2 ? 190:300}
    func stateColor(_ state:VoiceTurnState)->Color {
        switch state {
        case .failed:return Color.orange
        case .waiting,.replying:return accent
        default:return quiet
        }
    }
    func placeholder(_ turn:VoiceTurn)->String {
        switch turn.state {
        case .waiting:return "正在等 Chan 回复…"
        case .replying:return "正在接收字幕…"
        case .ready,.completed:return "本次回复没有附带字幕。"
        case .failed,.cancelled:return "还没收到回复文字。"
        }
    }
    var body:some View {
        VStack(alignment:.leading,spacing:10) {
            HStack {
                Text("最近对话").font(.system(size:12,weight:.medium))
                Text("最多 10 轮 · 退出后清除").font(.system(size:10)).foregroundColor(quiet)
                Spacer()
                Button("清空"){clear()}.buttonStyle(.borderless).font(.system(size:11)).disabled(history.turns.isEmpty)
                    .help("只清空本次对话记录，不中断正在播放的声音")
            }
            if history.turns.isEmpty {
                HStack(spacing:12) {
                    Image(systemName:"text.bubble").font(.system(size:21)).foregroundColor(quiet)
                    VStack(alignment:.leading,spacing:5) {
                        Text("聊过的话，留在这里").font(.system(size:13))
                        Text("回车发送，回复逐句出现。").font(.system(size:11)).foregroundColor(quiet)
                    }
                    Spacer()
                }.padding(18).frame(maxWidth:.infinity,alignment:.leading)
                    .background(RoundedRectangle(cornerRadius:12).fill(Color.white.opacity(0.025)))
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment:.leading,spacing:18) {
                            ForEach(history.turns) {turn in
                                VStack(alignment:.leading,spacing:12) {
                                    HStack {
                                        Spacer(minLength:42)
                                        Text(verbatim:turn.user).font(.system(size:13)).lineSpacing(4).textSelection(.enabled)
                                            .padding(.horizontal,13).padding(.vertical,10)
                                            .background(RoundedRectangle(cornerRadius:13).fill(accent.opacity(0.12)))
                                            .accessibilityLabel("你：\(turn.user)")
                                    }
                                    VStack(alignment:.leading,spacing:7) {
                                        HStack(spacing:6) {
                                            Text("Chan").font(.system(size:11,weight:.semibold))
                                            Circle().fill(stateColor(turn.state)).frame(width:4,height:4)
                                            Text(turn.state.label).font(.system(size:10)).foregroundColor(stateColor(turn.state))
                                        }
                                        Text(verbatim:turn.reply.isEmpty ? placeholder(turn):turn.reply)
                                            .font(.system(size:13)).lineSpacing(5).textSelection(.enabled)
                                            .foregroundColor(turn.reply.isEmpty ? quiet:Color.white.opacity(0.92))
                                            .fixedSize(horizontal:false,vertical:true)
                                        if !turn.detail.isEmpty {
                                            Text(verbatim:turn.detail).font(.system(size:11)).foregroundColor(stateColor(turn.state))
                                                .fixedSize(horizontal:false,vertical:true)
                                        }
                                    }.padding(.trailing,30)
                                }.id(turn.id)
                            }
                            Color.clear.frame(height:1).id("voice-bottom")
                                .background(GeometryReader {geometry in
                                    Color.clear.preference(key:VoiceHistoryBottom.self,value:geometry.frame(in:.named("voice-history")).maxY)
                                })
                        }.padding(14)
                    }.coordinateSpace(name:"voice-history").frame(height:height)
                        .background(RoundedRectangle(cornerRadius:12).fill(Color.black.opacity(0.18)))
                        .onPreferenceChange(VoiceHistoryBottom.self){bottom in followsLatest=bottom<=height+28 && bottom>=0}
                        .onAppear {proxy.scrollTo("voice-bottom",anchor:.bottom)}
                        .onChange(of:history.turns.last?.id) {_ in followsLatest=true;proxy.scrollTo("voice-bottom",anchor:.bottom)}
                        .onChange(of:history.turns.last) {_ in if followsLatest {proxy.scrollTo("voice-bottom",anchor:.bottom)}}
                        .overlay(alignment:.bottomTrailing) {
                            if !followsLatest {
                                Button {followsLatest=true;proxy.scrollTo("voice-bottom",anchor:.bottom)} label:{Label("最新",systemImage:"arrow.down")}
                                    .font(.system(size:11)).padding(9)
                            }
                        }
                }
            }
        }
    }
}

struct VoiceCardView:View {
    @ObservedObject var voice:VoiceCompanion
    @State private var settingsOpen=false
    @FocusState private var inputFocused:Bool
    @State private var refocusAfterReply=false
    var waitingForReply:Bool {voice.busy && !voice.preparingGreeting}
    var canSend:Bool {
        voice.ready && !voice.voiceMode.visible && !voice.microphoneState.active && (!voice.busy || voice.preparingGreeting) &&
        !voice.draft.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty && voice.draft.count<=120
    }
    func send() {
        guard canSend else {return}
        voice.request()
        if waitingForReply {refocusAfterReply=true;inputFocused=false}
    }
    func restoreInputFocus() {
        guard refocusAfterReply,!waitingForReply else {return}
        refocusAfterReply=false
        // 等输入框重新启用；不抢其他应用、设置页或另一个输入框的焦点。
        DispatchQueue.main.async {
            guard !settingsOpen,!waitingForReply,NSApp.isActive else {return}
            if let editor=NSApp.keyWindow?.firstResponder as? NSTextView,editor.isFieldEditor,!inputFocused {return}
            inputFocused=true
        }
    }
    var body:some View {
        VStack(alignment:.leading,spacing:14){
            HStack{Text("语音陪伴").font(.system(size:14,weight:.semibold));Spacer();Button{settingsOpen=true}label:{Label("声音设置",systemImage:"slider.horizontal.3")};Toggle("语音陪伴",isOn:Binding(get:{voice.enabled},set:{voice.setEnabled($0)})).labelsHidden().toggleStyle(.switch)}
            HStack{Image(systemName:"airpodspro");Text(voice.routeText).font(.system(size:12));Spacer();if voice.route.isAirPods && voice.approved != voice.route.uid {Button("使用这副 AirPods"){voice.adoptCurrent()}}}
            HStack{Text("湾湾小何v2 · \(voice.soundSummary)");Spacer();Text(voice.sound.autoPlay ? "回复自动播放":"点按播放回复")}.font(.system(size:11)).foregroundColor(quiet)
            VoiceConversationView(history:voice.conversation,clear:voice.clearConversation)
            TextField("打字给 Chan，回车发送（最多 120 字）",text:$voice.draft)
                .textFieldStyle(.roundedBorder)
                .focused($inputFocused)
                .onSubmit {send()}
                .disabled((voice.busy && !voice.preparingGreeting) || voice.microphoneState.active)
            HStack(spacing:12) {
                Button {inputFocused=false;voice.presentVoiceMode()} label:{Label("进入语音模式",systemImage:"waveform").padding(.vertical,6)}
                    .buttonStyle(PanelActionStyle(prominent:true)).disabled(!voice.ready)
                Text(voice.hotkeyEnabled ? "⌃⌥空格 · 呼出／结束":"直接开口，自然接话").font(.system(size:11)).foregroundColor(quiet)
                Spacer()
            }
            HStack {
                Text("仅 AirPods · 机器人静音").font(.system(size:11)).foregroundColor(quiet)
                Spacer()
                if voice.busy && !voice.preparingGreeting {Button("立即停止"){voice.stopByUser()}}
                else {
                    if voice.preparingGreeting {Button("停止准备"){voice.stopByUser()}}
                    if voice.pending != nil {
                        Button("丢弃"){voice.cancel("已丢弃这条回复。")}
                        Button("播放回复"){voice.playPending()}.disabled(!voice.ready)
                    }
                    Button("发送"){send()}.buttonStyle(PanelActionStyle(prominent:true)).disabled(!canSend)
                }
            }
            if !voice.message.isEmpty {Text(voice.message).font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)}
        }.onDisappear {voice.cancelMicrophone("")}
            .onChange(of:settingsOpen) {opened in if opened {voice.cancelMicrophone("已取消录音，没有发送。")}}
            .onChange(of:waitingForReply) {waiting in if !waiting {restoreInputFocus()}}
            .sheet(isPresented:$settingsOpen){VoiceSettingsView(voice:voice)}
    }
}
