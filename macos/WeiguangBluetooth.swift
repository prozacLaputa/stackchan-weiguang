import Foundation
import CoreBluetooth
import CryptoKit

func emit(_ value:[String:Any]) { if let data=try? JSONSerialization.data(withJSONObject:value){
 FileHandle.standardOutput.write(data+Data([10]))
 if let i=CommandLine.arguments.firstIndex(of:"--report"),i+1<CommandLine.arguments.count{try? data.write(to:URL(fileURLWithPath:CommandLine.arguments[i+1]),options:.atomic)}
} }
func fail(_ code:String)->Never {emit(["event":"error","code":code]);exit(2)}
extension Data {
 init?(hex:String){guard hex.count%2==0 else{return nil};var data=Data();var i=hex.startIndex;while i<hex.endIndex{let end=hex.index(i,offsetBy:2);guard let byte=UInt8(hex[i..<end],radix:16) else{return nil};data.append(byte);i=end};self=data}
 func hex()->String{map{String(format:"%02x",$0)}.joined()}
}
struct Wire {
 let send:SymmetricKey,receive:SymmetricKey
 var sent:UInt32=0,received:UInt32=0
 init(key:Data,challenge:Data){
  let base=SymmetricKey(data:key)
  send=SymmetricKey(data:Data(HMAC<SHA256>.authenticationCode(for:challenge+Data("M".utf8),using:base)))
  receive=SymmetricKey(data:Data(HMAC<SHA256>.authenticationCode(for:challenge+Data("R".utf8),using:base)))
 }
 static func sequence(_ n:UInt32)->Data{Data([UInt8((n>>24)&255),UInt8((n>>16)&255),UInt8((n>>8)&255),UInt8(n&255)])}
 mutating func seal(_ plain:Data)throws->Data{
  guard plain.count<=4096,sent<UInt32.max else{throw NSError(domain:"wire",code:1)};sent+=1
  let length=plain.count+20,seq=Self.sequence(sent)
  let header=Data([87,71,1,UInt8(length>>8),UInt8(length&255)])+seq
  let box=try AES.GCM.seal(plain,using:send,nonce:AES.GCM.Nonce(data:Data(repeating:0,count:8)+seq),authenticating:header)
  return header+box.ciphertext+box.tag
 }
 mutating func open(_ frame:Data)throws->Data{
  let bytes=[UInt8](frame);guard bytes.count>=25,bytes[0...2]==[87,71,1],Int(bytes[3])*256+Int(bytes[4])==bytes.count-5 else{throw NSError(domain:"wire",code:2)}
  let seq=bytes[5..<9].reduce(UInt32(0)){$0<<8|UInt32($1)};guard seq>received else{throw NSError(domain:"wire",code:3)}
  let box=try AES.GCM.SealedBox(nonce:AES.GCM.Nonce(data:Data(repeating:0,count:8)+Self.sequence(seq)),ciphertext:frame.subdata(in:9..<frame.count-16),tag:frame.suffix(16))
  let plain=try AES.GCM.open(box,using:receive,authenticating:frame.prefix(9));received=seq;return plain
 }
}
let args=CommandLine.arguments
func option(_ key:String)->String?{guard let i=args.firstIndex(of:key),i+1<args.count else{return nil};return args[i+1]}
if args.contains("--self-test"){
 let key=Data(repeating:7,count:32),nonce=Data(repeating:3,count:16);var wire=Wire(key:key,challenge:nonce)
 let frame=try wire.seal(Data("PING".utf8));assert(frame.count==29)
 let derived=SymmetricKey(data:Data(HMAC<SHA256>.authenticationCode(for:nonce+Data("M".utf8),using:SymmetricKey(data:key))))
 let box=try AES.GCM.SealedBox(nonce:AES.GCM.Nonce(data:Data(repeating:0,count:8)+Wire.sequence(1)),ciphertext:frame.subdata(in:9..<13),tag:frame.suffix(16))
 let opened=try AES.GCM.open(box,using:derived,authenticating:frame.prefix(9));guard opened==Data("PING".utf8) else{fail("self_test_failed")}
 emit(["event":"self_test","ok":true,"fixture":frame.hex()]);exit(0)
}

final class Client:NSObject,CBCentralManagerDelegate,CBPeripheralDelegate {
 let service=CBUUID(string:"45860001-3a86-4a23-b79b-9ce13700c681")
 let rxID=CBUUID(string:"45860002-3a86-4a23-b79b-9ce13700c681"),txID=CBUUID(string:"45860003-3a86-4a23-b79b-9ce13700c681"),infoID=CBUUID(string:"45860004-3a86-4a23-b79b-9ce13700c681")
 var manager:CBCentralManager!,peer:CBPeripheral?,rx:CBCharacteristic?,tx:CBCharacteristic?,info:CBCharacteristic?
 var wire:Wire?,incoming=Data(),outgoing=Data(),offset=0,awaiting=false,ready=false,subscribed=false
 var pending=[Data](),progress=Date(),timer:Timer?
 let probe:Bool,device:String,key:Data
 init(device:String,key:Data,probe:Bool){
  self.device=device;self.key=key;self.probe=probe;super.init()
  manager=CBCentralManager(delegate:self,queue:.main,options:[CBCentralManagerOptionShowPowerAlertKey:false])
  timer=Timer.scheduledTimer(withTimeInterval:1,repeats:true){[weak self] _ in
   guard let self=self else{return};if (!self.ready||self.awaiting)&&Date().timeIntervalSince(self.progress)>15{fail(self.ready ? "ble_reply_timeout":"ble_connect_timeout")}
  }
 }
 func centralManagerDidUpdateState(_ central:CBCentralManager){
  switch central.state {
  case .poweredOn:if probe{emit(["event":"available"]);exit(0)};manager.scanForPeripherals(withServices:[service],options:[CBCentralManagerScanOptionAllowDuplicatesKey:false])
  case .unauthorized:fail("bluetooth_permission_denied")
  case .poweredOff:fail("bluetooth_powered_off")
  case .unsupported:fail("bluetooth_unsupported")
  default:break
  }
 }
 func centralManager(_ central:CBCentralManager,didDiscover peripheral:CBPeripheral,advertisementData:[String:Any],rssi:NSNumber){
  guard peer==nil else{return}
  let name=(advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? peripheral.name ?? ""
  guard name=="Weiguang-"+device.suffix(4) else{return}
  manager.stopScan();peer=peripheral;peripheral.delegate=self;manager.connect(peripheral);progress=Date()
 }
 func centralManager(_ central:CBCentralManager,didConnect peripheral:CBPeripheral){progress=Date();peripheral.discoverServices([service])}
 func centralManager(_ central:CBCentralManager,didFailToConnect peripheral:CBPeripheral,error:Error?){fail("ble_connect_failed")}
 func centralManager(_ central:CBCentralManager,didDisconnectPeripheral peripheral:CBPeripheral,error:Error?){fail("ble_disconnected")}
 func peripheral(_ peripheral:CBPeripheral,didDiscoverServices error:Error?){guard error==nil,let target=peripheral.services?.first(where:{$0.uuid==service}) else{fail("ble_service_missing")};peripheral.discoverCharacteristics([rxID,txID,infoID],for:target)}
 func peripheral(_ peripheral:CBPeripheral,didDiscoverCharacteristicsFor service:CBService,error:Error?){
  guard error==nil else{fail("ble_characteristics_failed")}
  for c in service.characteristics ?? []{if c.uuid==rxID{rx=c};if c.uuid==txID{tx=c};if c.uuid==infoID{info=c}}
  guard rx != nil,let tx=tx,info != nil else{fail("ble_characteristic_missing")};peripheral.setNotifyValue(true,for:tx)
 }
 func peripheral(_ peripheral:CBPeripheral,didUpdateNotificationStateFor characteristic:CBCharacteristic,error:Error?){
  guard error==nil,characteristic.isNotifying,let info=info else{fail("ble_notifications_failed")};subscribed=true;peripheral.readValue(for:info)
 }
 func peripheral(_ peripheral:CBPeripheral,didUpdateValueFor characteristic:CBCharacteristic,error:Error?){
  guard error==nil,let data=characteristic.value else{fail("ble_read_failed")}
  if characteristic.uuid==infoID{
   let parts=String(data:data,encoding:.utf8)?.split(separator:"\t").map(String.init) ?? []
   guard parts.count==3,parts[0]=="WG1",parts[1]==device,let nonce=Data(hex:parts[2]),nonce.count==16 else{fail("ble_identity_mismatch")}
   wire=Wire(key:key,challenge:nonce);send(Data("PING".utf8));return
  }
  guard characteristic.uuid==txID else{return}
  incoming.append(data);guard incoming.count<=4121 else{fail("ble_frame_too_large")}
  while incoming.count>=5{
   let header=[UInt8](incoming.prefix(5)),length=Int(header[3])*256+Int(header[4])+5
   guard header[0...2]==[87,71,1],length>=25,length<=4121 else{fail("ble_frame_invalid")}
   if incoming.count<length{return};let frame=Data(incoming.prefix(length));incoming=Data(incoming.dropFirst(length))
   do{
    guard wire != nil else{fail("ble_session_missing")};let plain=try wire!.open(frame);awaiting=false;progress=Date()
    if !ready{guard String(data:plain,encoding:.utf8)=="READY\t"+device+"\n" else{fail("ble_auth_failed")};ready=true;emit(["event":"ready","device":device])}
    else{emit(["event":"reply","data":plain.base64EncodedString()])}
    pump()
   }catch{fail("ble_auth_failed")}
  }
 }
 func enqueue(_ data:Data){guard pending.count<4,data.count<=4096 else{fail("ble_queue_full")};pending.append(data);pump()}
 func pump(){if ready && !awaiting && !pending.isEmpty{send(pending.removeFirst())}}
 func send(_ data:Data){
  do{guard wire != nil else{fail("ble_not_ready")};outgoing=try wire!.seal(data);offset=0;awaiting=true;progress=Date();writeChunk()}catch{fail("ble_encrypt_failed")}
 }
 func writeChunk(){
  guard let peer=peer,let rx=rx,offset<outgoing.count else{return}
  let n=min(180,peer.maximumWriteValueLength(for:.withResponse),outgoing.count-offset)
  let chunk=outgoing.subdata(in:offset..<offset+n);offset+=n;peer.writeValue(chunk,for:rx,type:.withResponse)
 }
 func peripheral(_ peripheral:CBPeripheral,didWriteValueFor characteristic:CBCharacteristic,error:Error?){guard error==nil else{fail("ble_write_failed")};progress=Date();writeChunk()}
}
let isProbe=args.contains("--probe")
let device=option("--device") ?? ""
var secret=Data()
if !isProbe{
 guard let path=option("--key-file"),let text=try? String(contentsOfFile:path,encoding:.utf8),let data=Data(hex:text.trimmingCharacters(in:.whitespacesAndNewlines)),data.count==32,device.count==12 else{fail("ble_binding_missing")};secret=data
}
let client=Client(device:device,key:secret,probe:isProbe)
if !isProbe{DispatchQueue.global().async{while let line=readLine(){
 guard let bytes=line.data(using:.utf8),let json=(try? JSONSerialization.jsonObject(with:bytes)) as? [String:Any],let encoded=json["data"] as? String,let data=Data(base64Encoded:encoded) else{fail("ble_input_invalid")}
 DispatchQueue.main.async{client.enqueue(data)}
};exit(0)}}
RunLoop.main.run()
