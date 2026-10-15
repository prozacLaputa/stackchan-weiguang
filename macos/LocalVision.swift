import Foundation
import Vision
import ImageIO
import AppKit
import SwiftUI

// No network, image files, photo library or Mac-camera APIs in this worker.
func localVisionAnalyzer() {
    while let line=readLine() {
        autoreleasepool {
            var reply:[String:Any]=["ok":false]
            if line.utf8.count<=90000,let data=Data(base64Encoded:line),data.count<=65536,
               let source=CGImageSourceCreateWithData(data as CFData,nil),
               let image=CGImageSourceCreateImageAtIndex(source,0,nil),image.width==320,image.height==240 {
                do {
                    let face=VNDetectFaceRectanglesRequest()
                    let hand=VNDetectHumanHandPoseRequest();hand.maximumHandCount=1
                    try VNImageRequestHandler(cgImage:image,orientation:.up).perform([face,hand])
                    let faces=(face.results ?? []).filter{$0.confidence>=0.6 && $0.boundingBox.width>=0.09}
                    reply=["ok":true,"faces":faces.count]
                    if faces.count==1 {
                        let box=faces[0].boundingBox
                        reply["face"]=[Double(box.midX),Double(box.midY)]
                    }
                    if let observation=hand.results?.first {
                        let points=try observation.recognizedPoints(.all)
                        let pairs:[(VNHumanHandPoseObservation.JointName,VNHumanHandPoseObservation.JointName)] = [(.indexTip,.indexPIP),(.middleTip,.middlePIP),(.ringTip,.ringPIP),(.littleTip,.littlePIP)]
                        if let wrist=points[.wrist],wrist.confidence>=0.4 {
                            let extended=pairs.filter {tip,pip in
                                guard let t=points[tip],let p=points[pip],t.confidence>=0.4,p.confidence>=0.4 else{return false}
                                return hypot(t.location.x-wrist.location.x,t.location.y-wrist.location.y)>hypot(p.location.x-wrist.location.x,p.location.y-wrist.location.y)*1.2
                            }.count
                            if extended>=3 {reply["hand"]=[Double(wrist.location.x),Double(wrist.location.y)]}
                        }
                    }
                } catch {reply=["ok":false]}
            }
            let bytes=(try? JSONSerialization.data(withJSONObject:reply)) ?? Data("{}".utf8)
            FileHandle.standardOutput.write(bytes);FileHandle.standardOutput.write(Data([10]))
        }
    }
}

final class LocalVision:ObservableObject {
    @Published var running=false
    @Published var status="用 Chan 看见你，安静地回应。"
    @Published var detail="Mac 本地识别 · 不产生模型调用费"
    private var process:Process?
    private var generation=UUID()
    private var observers:[NSObjectProtocol]=[]
    init() {
        for name in [NSWorkspace.willSleepNotification,NSWorkspace.screensDidSleepNotification,NSWorkspace.sessionDidResignActiveNotification] {
            observers.append(NSWorkspace.shared.notificationCenter.addObserver(forName:name,object:nil,queue:.main){[weak self] _ in self?.stop("Mac 已休息，视觉互动已关闭。")})
        }
    }
    func start() {
        guard !running,process==nil else{return}
        let root=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Weiguang")
        guard let data=try? Data(contentsOf:root.appendingPathComponent("voice-runtime.json")),
              let config=try? JSONSerialization.jsonObject(with:data) as? [String:String],let python=config["python"],let voiceWorker=config["worker"] else {status="本地组件未就绪，请更新控制台。";return}
        let worker=URL(fileURLWithPath:voiceWorker).deletingLastPathComponent().appendingPathComponent("vision_camera.py")
        let child=Process();let output=Pipe()
        child.executableURL=URL(fileURLWithPath:python)
        child.arguments=[worker.path,"--analyzer",Bundle.main.executableURL!.path]
        child.standardOutput=output;child.standardError=FileHandle.nullDevice;child.standardInput=FileHandle.nullDevice
        let ticket=UUID();generation=ticket
        do {try child.run()} catch {status="本地视觉组件启动失败。";return}
        process=child;running=true;status="正在连接 Chan 摄像头…";detail="USB 画面 · 蓝牙继续同步任务"
        DispatchQueue.global(qos:.utility).async { [weak self] in
            var pending=Data()
            while true {
                let data=output.fileHandleForReading.availableData
                if data.isEmpty {break};pending.append(data)
                if pending.count>8192 {child.terminate();break}
                while let end=pending.firstIndex(of:10) {
                    let line=pending.subdata(in:0..<end);pending.removeSubrange(0...end)
                    guard let value=try? JSONSerialization.jsonObject(with:line) as? [String:Any] else{continue}
                    DispatchQueue.main.async {
                        guard let self=self,self.generation==ticket else{return}
                        if let message=value["message"] as? String {self.status=message}
                        if let fps=value["fps"] as? Double {self.detail=String(format:"本地识别 · %.1f 帧/秒 · 画面不保存",fps)}
                    }
                }
            }
            child.waitUntilExit()
            DispatchQueue.main.async {
                guard let self=self,self.generation==ticket else{return}
                self.process=nil;self.running=false;self.detail="Mac 本地识别 · 不产生模型调用费"
                if self.status.hasPrefix("正在") {self.status="连接已结束，可重新开启。"}
            }
        }
    }
    func stop(_ message:String="视觉互动已关闭，摄像头已停止采集。") {
        guard let child=process else{return}
        generation=UUID();running=false;status=message;detail="Mac 本地识别 · 不产生模型调用费"
        child.terminate()
        // Keep ownership until the graceful stop completes, prevent competing serial clients.
        DispatchQueue.global().async {[weak self] in
            child.waitUntilExit()
            DispatchQueue.main.async {if self?.process === child {self?.process=nil}}
        }
    }
}

struct LocalVisionCard:View {
    @ObservedObject var vision:LocalVision
    let connected:Bool
    var body:some View {
        VStack(alignment:.leading,spacing:13) {
            HStack {
                Image(systemName:vision.running ? "eye":"eye.slash").font(.system(size:19)).foregroundColor(accent)
                VStack(alignment:.leading,spacing:3) {Text("看见你").font(.system(size:15,weight:.semibold));Text("视觉互动 · 试用").font(.system(size:10)).foregroundColor(quiet)}
                Spacer()
                Button(vision.running ? "关闭互动":"开启互动") {if vision.running {vision.stop()} else {vision.start()}}
                    .buttonStyle(PanelActionStyle(prominent:!vision.running)).disabled(!vision.running && !connected)
            }
            Text(vision.status).font(.system(size:12)).fixedSize(horizontal:false,vertical:true)
            Text(vision.detail).font(.system(size:11)).foregroundColor(quiet)
            if !vision.running {
                HStack(spacing:16) {Label("见面微笑",systemImage:"face.smiling");Label("视线跟随",systemImage:"eyes");Label("挥手回应",systemImage:"hand.wave")}.font(.system(size:11)).foregroundColor(accent)
                Text("接上 USB 数据线，保持蓝牙任务同步。一次只和画面中的一个人互动；不识别人名。静音、只变表情；任务提醒和摸头优先。锁屏或关闭控制台后停止。")
                    .font(.system(size:11)).foregroundColor(quiet).fixedSize(horizontal:false,vertical:true)
            }
        }
    }
}
