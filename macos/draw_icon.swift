// 微光原生矢量图标：沿用机器人宽眼距、无瞳孔与小微笑。
// 只生成项目图标资产，不读取或控制桌面。
import AppKit
import Foundation
let output=URL(fileURLWithPath:CommandLine.arguments[1],isDirectory:true)
try FileManager.default.createDirectory(at:output,withIntermediateDirectories:true)
func drawIcon(_ size:Int)->Data {
 let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:size,pixelsHigh:size,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
 let ctx=NSGraphicsContext(bitmapImageRep:rep)!
 NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=ctx
 let cg=ctx.cgContext;cg.scaleBy(x:CGFloat(size)/1024,y:CGFloat(size)/1024)
 let bounds=NSRect(x:64,y:64,width:896,height:896)
 let shape=NSBezierPath(roundedRect:bounds,xRadius:202,yRadius:202)
 NSGraphicsContext.saveGraphicsState()
 let shadow=NSShadow();shadow.shadowColor=NSColor.black.withAlphaComponent(0.24);shadow.shadowBlurRadius=28;shadow.shadowOffset=NSSize(width:0,height:-10);shadow.set()
 NSColor.black.setFill();shape.fill()
 NSGraphicsContext.restoreGraphicsState()
 // 白框向黑色底面外侧延伸，在深色 Dock 上也能看清轮廓。
 let border=NSBezierPath(roundedRect:bounds.insetBy(dx:-8,dy:-8),xRadius:210,yRadius:210)
 NSColor.white.setStroke();border.lineWidth=16;border.stroke()
 let ink=NSColor.white
 // 两枚圆端线条，留出呼吸感；小尺寸也不画瞳孔、像素格或拟真五官。
 ink.setFill()
 for x in [CGFloat(286),CGFloat(614)] {
  NSBezierPath(roundedRect:NSRect(x:x,y:529,width:124,height:38),xRadius:19,yRadius:19).fill()
 }
 let smile=NSBezierPath();smile.move(to:NSPoint(x:463,y:425))
 smile.curve(to:NSPoint(x:561,y:425),controlPoint1:NSPoint(x:489,y:400),controlPoint2:NSPoint(x:535,y:400))
 ink.setStroke();smile.lineWidth=18;smile.lineCapStyle = .round;smile.stroke()
 // 下方一束微光，帮助在 Dock 小尺寸中辨认。
 let light=NSBezierPath(roundedRect:NSRect(x:466,y:167,width:92,height:10),xRadius:5,yRadius:5)
 NSColor.white.withAlphaComponent(0.5).setFill();light.fill()
 NSGraphicsContext.restoreGraphicsState()
 return rep.representation(using:.png,properties:[:])!
}
for points in [16,32,128,256,512] {
 for scale in [1,2] {
  let name="icon_\(points)x\(points)"+(scale==2 ? "@2x" : "")+".png"
  try drawIcon(points*scale).write(to:output.appendingPathComponent(name))
 }
}
