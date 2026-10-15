import AppKit
import Carbon

// 系统只分发这一组快捷键；不安装全键盘监听，也不申请辅助功能或输入监控。
final class VoiceHotkey {
    private var reference:EventHotKeyRef?
    private var handler:EventHandlerRef?
    private var held=false
    private let action:()->Void
    init(action:@escaping()->Void){self.action=action}
    func register()->Bool {
        unregister()
        var types=[EventTypeSpec(eventClass:OSType(kEventClassKeyboard),eventKind:UInt32(kEventHotKeyPressed)),
                   EventTypeSpec(eventClass:OSType(kEventClassKeyboard),eventKind:UInt32(kEventHotKeyReleased))]
        let callback:EventHandlerUPP = { _,event,context in
            guard let event=event,let context=context else{return OSStatus(eventNotHandledErr)}
            var key=EventHotKeyID()
            guard GetEventParameter(event,EventParamName(kEventParamDirectObject),EventParamType(typeEventHotKeyID),nil,MemoryLayout<EventHotKeyID>.size,nil,&key)==noErr,
                  key.signature==0x57475643,key.id==1 else{return OSStatus(eventNotHandledErr)}
            let owner=Unmanaged<VoiceHotkey>.fromOpaque(context).takeUnretainedValue()
            owner.handle(pressed:GetEventKind(event)==UInt32(kEventHotKeyPressed))
            return noErr
        }
        let installed=InstallEventHandler(GetApplicationEventTarget(),callback,types.count,&types,Unmanaged.passUnretained(self).toOpaque(),&handler)
        guard installed==noErr else {unregister();return false}
        let registered=RegisterEventHotKey(UInt32(kVK_Space),UInt32(controlKey|optionKey),EventHotKeyID(signature:0x57475643,id:1),GetApplicationEventTarget(),0,&reference)
        guard registered==noErr else {unregister();return false}
        return true
    }
    func handle(pressed:Bool) {
        if !pressed {held=false;return}
        guard !held else{return};held=true;action()
    }
    func unregister() {
        if let reference=reference {UnregisterEventHotKey(reference)}
        if let handler=handler {RemoveEventHandler(handler)}
        reference=nil;handler=nil;held=false
    }
    deinit {unregister()}
}

func voiceHotkeySelfTest() {
    var count=0;let key=VoiceHotkey{count+=1}
    key.handle(pressed:true);key.handle(pressed:true);precondition(count==1)
    key.handle(pressed:false);key.handle(pressed:true);precondition(count==2)
    key.unregister();key.handle(pressed:true);precondition(count==3)
    print("voice shortcut: held-key repeat suppression and reset passed (not registered)")
}
