#include <Arduino.h>
#include <M5Unified.h>
#include <Si12T.h>
#include <math.h>
#include "ui_state.h"
#include "touch_gesture.h"
#include "quiet_motion.h"
#include "face_expression.h"
#include "standby_state.h"
#include "sync_state.h"
#include "ble_transport.h"
#include "device_settings.h"
#include "remote_settings.h"
#include "touch_startup.h"
#include "task_hint.h"
#include "progress_marquee.h"
#include "daily_pet.h"
#include "desk_companion.h"
#include "rest_ritual.h"
#include "cat_skin.h"
#include "desktop_actions.h"
#include "focus_dial.h"
#include "focus_waiting.h"
#include "focus_summary.h"
#include "sticky_note.h"

UiState ui;
SyncState syncState;
BleTransport ble;
DeviceSettings settings;
struct TouchIo {
 bool read(uint8_t addr,uint8_t reg,uint8_t* data,int size){return M5.In_I2C.readRegister(addr,reg,data,size,100000);}
 bool write(uint8_t addr,uint8_t reg,uint8_t value){return M5.In_I2C.writeRegister8(addr,reg,value,100000);}
 void wait(int ms){delay(ms);}
 bool reinitialize(){auto driver=M5.Display.panel()->getTouch();return driver&&driver->init();}
};
TouchIo touchIo;
TouchStartupResult touchStartup;
int settingsPage=0;
bool settingsOpen=false,settingsDirty=false,settingsSaveFailed=false,pressedInSettings=false,pressedSettingsEntry=false;
SettingHit pressedSetting=SettingHit::none;
uint32_t settingsChangedAt=0;
FaceAnimator faceAnimator;
CatPetting cat;
DailyAnimator daily;
RestRitual restRitual;
DeskCompanion companion;
FocusSummary focusSummary;bool focusSummarySaveFailed=false;uint32_t focusSummarySavedAt=0;
void tickFocus(uint32_t now);
void saveFocusSummary(bool force=false){
 uint32_t now=millis();
 if(!focusSummary.dirty||(!force&&uint32_t(now-focusSummarySavedAt)<60000))return;
 focusSummarySavedAt=now;uint32_t words[8];focusSummary.encode(words);
 Preferences prefs;bool ok=prefs.begin("weiguang_focus",false);
 if(ok){ok=prefs.putBytes("summary",words,sizeof(words))==sizeof(words);prefs.end();}
 focusSummarySaveFailed=!ok;if(ok)focusSummary.dirty=false;
}
String focusSummaryText(){
 if(!focusSummary.ready)return "今日专注 · 等待日期同步";
 uint32_t seconds=focusSummary.seconds();
 String duration=seconds>0&&seconds<60?"不足 1 分钟":String(seconds/60)+" 分钟";
 return String("今日 ")+focusSummary.rounds()+" 轮 · "+duration;
}
StickyNote stickyNote;StickyNotePress stickyPress;bool noteSaveFailed=false;
bool noteVisible(){
 if(!stickyNote.active())return false;
 if(syncState.live())for(const auto& task:ui.tasks)if(task.state=="needs_input")return false;
 return true;
}
bool persistNote(const StickyNote& next){
 auto bytes=next.encode();Preferences prefs;bool ok=prefs.begin("weiguang_note",false);
 if(ok){ok=prefs.putBytes("note",bytes.data(),bytes.size())==bytes.size();prefs.end();}
 noteSaveFailed=!ok;if(ok)stickyNote=next;return ok;
}
DesktopAction desktopAction;
bool focusOpen=false,pressedInFocus=false,pressedFocusEntry=false;
int focusMinutes=25;FocusHit pressedFocus=FocusHit::none;
FocusTimer::Phase pressedFocusPhase=FocusTimer::off;FocusCycle::Stage pressedFocusStage=FocusCycle::work;
FocusPresentation focusPresentation;bool pressedFocusControls=false,pressedHomeFocus=false;uint32_t handledFocusCompletion=0,handledStageCompletion=0;
FocusWaitingPress focusWaitingPress;bool focusActionFeedback=false;
WaitingPress waitingPress;
const Task* waitingTask(){
 if(!syncState.live()||ui.tasks.empty()||ui.tasks[ui.currentIndex].state!="needs_input")return nullptr;
 return &ui.tasks[ui.currentIndex];
}
void observeDesktopPresses(){
 waitingPress.observe(waitingTask(),desktopAction.armed&&!ui.details&&!settingsOpen&&!focusOpen);
 focusWaitingPress.observe(focusWaitingTarget(ui.tasks,syncState.live(),ui.currentIndex).task,
  desktopAction.armed&&focusOpen&&pressedFocusPhase==companion.focus.phase&&pressedFocusStage==companion.focus.stage);
}
uint32_t localWakeAt=0;bool localWake=false;
StandbyState standby;
WakeTouchGate wakeTouch;
int displayBrightness=StandbyState::awakeBrightness;
QuietMotion motion;
TouchGesture gesture;Hit pressedHit=Hit::none;bool pressedInList=false,pressedInRows=false;
M5Canvas canvas(&M5.Display);
M5Canvas taskCache(&M5.Display);
std::vector<std::string> titleSources;
std::vector<std::vector<std::string>> titleLines;
TitlePlayback titlePlayback;
ProgressMarquee homeProgress,listProgress;
std::vector<std::string> progressSources;
std::vector<int> progressWidths;
int lastProgressIndex=-1,lastProgressOffset=0;
int lastTitleIndex=-1,lastTitleOffset=0;
float readingOffset=-1;
bool cacheDirty=true,cacheReady=false,fullRedraw=true,lastWasDetails=false,canvasInPsram=false;
int lastDrawOffset=0,touchX=0,touchY=0;
uint32_t touchFeedbackAt=0;bool touchFeedback=false;
Si12T head(SI12T_Type_Low,SI12T_Sensitivity_Level_3);
String line;
bool connected=false,overflow=false,charging=false,clockReady=false,headReady=false;
int battery=-1,headRaw=-1,headHits=0;
uint32_t lastPacket=0,lastFrame=0,clockSeconds=0,clockTick=0,lastBattery=0,lastHead=0,lastPet=0;
bool pet=false;
const uint16_t BG=0x0000,MUTED=0x7BCF,FACE_INK=0xEF7D,ACCENT=0x5EBF;
String field(const String&s,int&p){int e=s.indexOf('\t',p);if(e<0)e=s.length();String v=s.substring(p,e);p=e+1;return v;}
bool number(const String&s){if(!s.length())return false;for(unsigned i=0;i<s.length();i++)if(s[i]<'0'||s[i]>'9')return false;return true;}
bool known(const String&s){return s=="running"||s=="done"||s=="interrupted"||s=="unknown"||s=="needs_input";}
void text(const String&s,int x,int y,uint16_t color=FACE_INK,const lgfx::IFont*font=&fonts::efontCN_16){canvas.setFont(font);canvas.setTextColor(color,BG);canvas.setCursor(x,y);canvas.print(s);}
String label(const std::string&s){return s=="needs_input"?"待你回应":s=="running"?"进行中":s=="done"?"本轮结束":s=="interrupted"?"已中断":"状态未知";}
uint16_t color(const std::string&s){return s=="needs_input"?0xFD6B:s=="running"?ACCENT:s=="done"?0x77D5:0xECAF;}
void centered(const String&s,int y,uint16_t c=FACE_INK){canvas.setFont(&fonts::efontCN_16);text(s,(canvas.width()-canvas.textWidth(s))/2,y,c);}
void backButton(bool pressed=false,bool compact=false){
 uint16_t ink=pressed?FACE_INK:ACCENT;
 canvas.drawRoundRect(12,28,compact?84:120,36,6,pressed?ACCENT:0x3186);
 int x=compact?27:45;canvas.drawLine(x,40,x-6,46,ink);canvas.drawLine(x-6,46,x,52,ink);text("返回",x+12,38,ink);
}
bool dailyEligible(uint32_t now){
 if(restRitual.active(now))return false;
 if(companion.welcome(now)||companion.focus.finished(now))return false;
 if(ui.details||settingsOpen||focusOpen||standby.resting()||gesture.active||M5.Touch.getCount()>0||cat.content(now)||headRaw>0||motion.active()||ui.celebrating||(pet&&uint32_t(now-lastPet)<2600))return false;
 if(syncState.live())for(const auto& t:ui.tasks)if(t.state=="needs_input")return false;
 return true;
}
DailyContext dailyContext(uint32_t now){
 if(companion.focus.working())return DailyContext::working;
 if(syncState.live())for(const auto& task:ui.tasks)if(task.state=="running")return DailyContext::working;
 return cat.affectionate(now)?DailyContext::affectionate:DailyContext::idle;
}
void applySettings(){
 standby.configure(settings.brightness(),settings.idleMs(),millis());
 motion.configure(settings.petMotion,settings.waitMotion,settings.doneMotion,settings.focusMotion);
 daily.configure(settings.daily,millis());
 companion.configureGreeting(settings.greeting);
 cat.setAffection(settings.affection);
 fullRedraw=true;
}
bool saveSettings(){
 if(!settingsDirty)return !settingsSaveFailed;
 Preferences prefs;bool ok=prefs.begin("weiguang_ui",false);
 if(ok){ok=prefs.putUInt("prefs",settings.packed())==4;prefs.end();}
 settingsDirty=false;settingsSaveFailed=!ok;fullRedraw=true;
 Serial.printf("SETTINGS\tsaved=%d\n",ok);return ok;
}
void settingsChanged(){settingsDirty=true;settingsSaveFailed=false;settingsChangedAt=millis();applySettings();}
void inspectSettings(){Serial.printf("SETTINGS\tlight=%d\trest=%d\tpet=%d\twait_motion=%d\tdone_motion=%d\tdirty=%d\tsave_error=%d\n",settings.light,settings.rest,settings.petMotion,settings.waitMotion,settings.doneMotion,settingsDirty,settingsSaveFailed);}
void cropped(const String&s,int x,int y,int width,const lgfx::IFont*font){
 canvas.setFont(font);String out;
 for(unsigned i=0;i<s.length();){uint8_t c=s[i];unsigned n=c<0x80?1:c<0xE0?2:c<0xF0?3:4;String next=s.substring(i,i+n);i+=n;
  if(canvas.textWidth(out+next+(i<s.length()?"…":""))>width){out+="…";break;}out+=next;}
 text(out,x,y,FACE_INK,font);
}
void prepareTaskTitles(){
 bool titlesChanged=titleSources.size()!=ui.tasks.size();
 bool progressChanged=progressSources.size()!=ui.tasks.size();
 if(!titlesChanged)for(int i=0;i<int(ui.tasks.size());i++)if(titleSources[i]!=ui.tasks[i].title){titlesChanged=true;break;}
 if(!progressChanged)for(int i=0;i<int(ui.tasks.size());i++)if(progressSources[i]!=ui.tasks[i].progressHint){progressChanged=true;break;}
 if(!titlesChanged&&!progressChanged)return;
 canvas.setFont(&fonts::efontCN_16);
 if(titlesChanged){
  titleSources.clear();titleLines.clear();
  for(const auto& t:ui.tasks){
   titleSources.push_back(t.title);
   titleLines.push_back(wrapTaskTitle(t.title,canvas.width()-54,[](const std::string& s){return canvas.textWidth(s.c_str());}));
  }
 }
 if(progressChanged){
  progressSources.clear();progressWidths.clear();
  for(const auto& t:ui.tasks){progressSources.push_back(t.progressHint);progressWidths.push_back(canvas.textWidth(t.progressHint.c_str()));}
 }
}
void drawTaskRow(M5Canvas& target,int i,int x,int y,int width){
 const auto& t=ui.tasks[i];uint16_t c=syncState.live()?color(t.state):MUTED;
 target.setFont(&fonts::efontCN_16);target.fillCircle(x+7,y+14,3,c);
 target.setTextColor(FACE_INK,BG);
 for(int l=0;l<std::min(2,int(titleLines[i].size()));l++){
  target.setCursor(x+20,y+TaskRow::titleTop+l*TaskRow::lineHeight);target.print(titleLines[i][l].c_str());
 }
 String status=syncState.live()?label(t.state):syncState.linked?"状态暂不可读":"离线快照";
 std::string reason=taskHint(t,syncState.live());
 bool unread=syncState.live()&&ui.unread.contains(t.id);
 int suffixWidth=unread?target.textWidth(" · 新"):0;
 if(!reason.empty())status=fitTaskHint(reason,width-26-suffixWidth,[&](const std::string& s){return target.textWidth(s.c_str());}).c_str();
 if(unread)status+=" · 新";
 target.setTextColor(c,BG);target.setCursor(x+20,y+TaskRow::statusTop);target.print(status);
 target.drawFastHLine(x+4,y+TaskRow::height-4,width-14,0x2104);
}
void rebuildTaskCache(){
 if(!cacheDirty)return;
 prepareTaskTitles();
 cacheDirty=false;cacheReady=false;
 int w=canvas.width()-26,h=int(ui.tasks.size())*TaskRow::height;
 if(!h)return;
 if(taskCache.width()!=w||taskCache.height()!=h){
  taskCache.deleteSprite();taskCache.setPsram(true);taskCache.setColorDepth(16);
  if(!taskCache.createSprite(w,h))return;
 }
 taskCache.setTextWrap(false,false);taskCache.fillScreen(BG);taskCache.setFont(&fonts::efontCN_16);
 for(int i=0;i<int(ui.tasks.size());i++)drawTaskRow(taskCache,i,0,i*TaskRow::height,w);
 cacheReady=true;
}
ListLayout listLayout(){return {canvas.width(),canvas.height()};}
void statusBar(){
 int w=canvas.width();char stamp[6]="--:--";
 if(clockReady)snprintf(stamp,sizeof(stamp),"%02u:%02u",(unsigned)(clockSeconds/3600),(unsigned)(clockSeconds/60%60));
 text(stamp,12,7,MUTED);String link=syncState.title();canvas.setFont(&fonts::efontCN_16);text(link,(w-canvas.textWidth(link))/2,7,syncState.live()?ACCENT:MUTED);
 String power=battery>=0?String(battery)+"%":"--%";canvas.setFont(&fonts::efontCN_16);int x=w-12-canvas.textWidth(power);
 text(power,x,7,battery>=0&&battery<=20?0xFD20:MUTED);
 int bx=x-24;canvas.drawRoundRect(bx,10,18,10,2,MUTED);canvas.fillRect(bx+18,13,2,4,MUTED);
 if(battery>=0)canvas.fillRect(bx+2,12,14*battery/100,6,charging?0x77D5:MUTED);
 if(charging){
  // 直接画闪电，避免字体缺少符号；只在电源芯片确认正在充电时显示。
  int bolt=bx-13;
  canvas.fillTriangle(bolt+8,6,bolt,14,bolt+5,14,0x77D5);
  canvas.fillTriangle(bolt+5,11,bolt+10,11,bolt+2,20,0x77D5);
 }
}
FaceMood selectedFace(uint32_t now){
 bool shy=pet&&uint32_t(now-lastPet)<2600;
 if(cat.content(now))return FaceMood::content;
 if(standby.resting()&&!shy)return FaceMood::rest;
 bool waiting=!ui.tasks.empty()&&ui.tasks[ui.currentIndex].state=="needs_input";
 auto base=selectFace(syncState.live(),shy,waiting,ui.celebrating,ui.tasks.empty()?"idle":ui.tasks[ui.currentIndex].mood);
 if(shy||(syncState.live()&&(waiting||ui.celebrating)))return base;
 if(companion.welcome(now)||companion.focus.finished(now))return FaceMood::joy;
 if(base==FaceMood::idle&&daily.kind==DailyKind::none&&dailyContext(now)==DailyContext::affectionate&&cat.softBlink(now))return FaceMood::content;
 if(base==FaceMood::idle&&companion.focus.working())return FaceMood::focus;
 return base;
}
void drawFace(uint32_t now){
 int w=canvas.width(),h=canvas.height();int faceBottom=h-74;
 int cx=w/2,cy=(32+faceBottom)/2;
 // 保持已认可的无瞳孔五官、宽眼距和小微笑；用相同轮廓平滑变化。
 auto animation=daily.frame(faceAnimator.update(selectedFace(now),now),now);
 FacePose p=restRitual.frame(animation.pose,now);cx+=int(lroundf(animation.x));cy+=int(lroundf(animation.y));
 int gap=w*70/320,breathing=int(2*sin(now/(standby.resting()?2200.0:1100.0)));
 uint32_t blinkPhase=now%4900;float open=1;
 if(!standby.resting()&&!restRitual.active(now)&&daily.kind!=DailyKind::blink&&blinkPhase>4680)open=fabs((int)blinkPhase-4790)/110.0;
 if(settings.skin==1){drawCatSkin(canvas,p,cx,cy,open,breathing,now,FACE_INK);return;}
 for(int side=-1;side<=1;side+=2){
  int x=cx+side*gap,y=cy-12+breathing+int(lroundf(side<0?p.leftLift:p.rightLift));
  int radius=std::max(1,int(lroundf(p.eyeWidth)));
  for(int dx=-radius;dx<=radius;dx++){
   float u=dx/float(radius),outline=sqrtf(std::max(0.0f,1-u*u));
   int ry=std::max(1,int(lroundf(p.eyeHeight*open*outline)));
   int center=y+int(lroundf(p.eyeCurve*(u*u-.55f)));
   canvas.drawFastVLine(x+dx,center-ry,ry*2+1,FACE_INK);
  }
  if(p.brow>.05f){
   int brow=y-21,extent=int(8*p.brow),tilt=side>0?int(3*p.brow):0;
   canvas.drawLine(x-extent,brow+tilt,x+extent,brow-tilt,FACE_INK);
  }
 }
 int my=cy+24+breathing,mw=std::max(1,int(lroundf(p.mouthWidth)));
 if(p.mouthOpen>1.5f){
  int height=std::max(2,int(lroundf(p.mouthOpen)));
  canvas.drawEllipse(cx,my+2,mw,height,FACE_INK);canvas.drawEllipse(cx,my+2,std::max(1,mw-1),height-1,FACE_INK);
 }else for(int x=-mw;x<=mw;x++)canvas.fillCircle(cx+x,my+int(lroundf(p.mouthCurve*(1-x*x/float(mw*mw)))),2,FACE_INK);
 if(p.cheek>.05f){
  uint16_t pink=canvas.color565(int(247*p.cheek),int(165*p.cheek),int(158*p.cheek));
  for(int side=-1;side<=1;side+=2)for(int j=-1;j<=1;j++){
   int x=cx+side*(w*105/320)+j*6;canvas.drawLine(x-2,my-5,x+2,my+3,pink);canvas.drawLine(x-1,my-5,x+3,my+3,pink);
  }
 }
 if(p.dots>.05f)for(int i=0;i<3;i++){
  float glow=p.dots*(.35f+.65f*((now/500)%3==unsigned(i)));
  canvas.fillCircle(cx+(i-1)*10,cy-39,2,canvas.color565(int(120*glow),int(175*glow),int(185*glow)));
 }
}

void notePaper(int w){
 const int x=12,y=142,width=w-24,height=90,fold=17;
 const int right=x+width-1,bottom=y+height-1;
 // 偏暖的纸张渐变，固定的细微纸纹不会随重绘闪动。
 canvas.fillRoundRect(x+2,y+4,width,height,3,0x18C2);
 canvas.fillRoundRect(x+1,y+2,width,height,3,0x3164);
 for(int row=0;row<height;row++){
  int cut=row>=height-fold?row-(height-fold)+1:0;
  int inset=row==0||row==height-1?2:row==1||row==height-2?1:0;
  uint16_t shade=canvas.color565(250-row*13/height,232-row*27/height,162-row*43/height);
  canvas.drawFastHLine(x+inset,y+row,width-inset-std::max(inset,cut),shade);
 }
 canvas.drawFastHLine(x+3,y+1,width-6,canvas.color565(255,240,182));
 for(int row=9;row<height-8;row+=9)for(int col=7+(row%5);col<width-23;col+=19)
  canvas.drawPixel(x+col,y+row,canvas.color565(248-row*13/height,229-row*27/height,158-row*43/height));
 // 右下角卷起，纸背略亮，折痕只用一条细线。
 canvas.fillTriangle(right-fold,bottom-fold,right,bottom-fold,right-fold,bottom,canvas.color565(255,239,182));
 canvas.drawLine(right-fold,bottom-fold,right-fold,bottom,canvas.color565(206,169,85));
 canvas.drawLine(right-fold,bottom-fold,right,bottom-fold,canvas.color565(240,207,124));
}
void home(uint32_t now){
 int w=canvas.width(),h=canvas.height();drawFace(now);
 canvas.drawRoundRect(228,28,80,34,7,0x3186);
 text(companion.focus.phase==FocusTimer::running?(companion.focus.resting()?"休息中":"专注中"):companion.focus.phase==FocusTimer::paused?"已暂停":companion.focus.phase==FocusTimer::done?"下一轮":"番茄钟",244,37,ACCENT);
 int active=0,waiting=0;for(const auto&t:ui.tasks){if(t.state=="running")active++;if(t.state=="needs_input")waiting++;}
 String summary=!connected?(syncState.ever?"同步已中断":"等待 Mac 同步"):!syncState.available?"任务数据暂不可读":String("进行中 ")+active+"  ·  任务 "+ui.tasks.size();
 uint16_t summaryColor=syncState.live()?ACCENT:MUTED;
 if(syncState.live()&&waiting){
  uint16_t amber=0xFD6B;
  canvas.drawRoundRect(12,142,w-24,94,9,amber);
  canvas.fillCircle(28,159,3,amber);
  text(String("待回应 ")+waiting+" · 长按打开 Codex",40,151,amber);
  if(!ui.tasks.empty())cropped(ui.tasks[ui.currentIndex].title.c_str(),26,176,w-52,&fonts::efontCN_16);
  String hint="按住约 1 秒即可打开";
  if(!ui.tasks.empty()&&!ui.tasks[ui.currentIndex].waitReason.empty())hint=fitTaskHint(ui.tasks[ui.currentIndex].waitReason,w-52,[](const std::string& str){return canvas.textWidth(str.c_str());}).c_str();
  if(waitingPress.captured&&gesture.active){
   uint32_t held=now-gesture.startAt;
   hint=waitingPress.fired?(*desktopAction.feedback(now)?desktopAction.feedback(now):"已发送打开请求"):waitingPress.canceled?"已取消 · 松手重试":"继续按住，打开 Codex";
   if(!waitingPress.canceled)canvas.fillRoundRect(26,226,int((w-52)*std::min(1.0f,held/900.0f)),3,1,amber);
  }else if(desktopAction.feedback(now)[0])hint=desktopAction.feedback(now);
  text(hint,26,202,amber);return;
 }else if(noteVisible()){
  notePaper(w);
  const uint16_t ink=canvas.color565(72,51,26),muted=canvas.color565(117,83,37);
  auto paperText=[&](const String& s,int x,int y,uint16_t color){
   canvas.setFont(&fonts::efontCN_16);canvas.setTextColor(color);canvas.setCursor(x,y);canvas.print(s);
  };
  paperText("便签",26,151,muted);
  String cue=noteSaveFailed?"保存失败 · 再试一次":"长按划掉";
  if(stickyPress.captured&&gesture.active){
   uint32_t held=now-gesture.startAt;
   bool valid=stickyPress.matches(stickyNote,noteVisible())&&gesture.maxTravel<=8&&gesture.axis==Axis::pending&&held<=4000;
   cue=!valid?"已取消":held>=900?"松手划掉":"继续按住…";
   if(valid)canvas.fillRoundRect(26,224,int((w-70)*std::min(1.0f,held/900.0f)),2,1,muted);
  }
  paperText(cue,w-26-canvas.textWidth(cue),151,noteSaveFailed?canvas.color565(142,53,29):muted);
  canvas.setFont(&fonts::efontCN_16);String row;int y=176;
  const auto& body=stickyNote.text;
  for(size_t i=0;i<body.size();){
   uint8_t first=body[i];int n=first<0x80?1:first<0xe0?2:3;String glyph=String(body.substr(i,n).c_str());i+=n;
   if(canvas.textWidth(row+glyph)>w-52){paperText(row,26,y,ink);row="";y+=23;}
   row+=glyph;
  }
  paperText(row,26,y,ink);return;
 }else if(syncState.live()&&ui.celebrating){
  summary=String("本轮结束 · ")+ui.completedCount+" 项";summaryColor=0x77D5;
  canvas.drawRoundRect(50,h-70,w-100,26,7,summaryColor);
 }else if(companion.focus.finished(now)){
  summary=companion.focus.phase==FocusTimer::done?"休息结束 · 可开始下一轮":"专注结束 · 休息五分钟";summaryColor=0x77D5;
 }else if(companion.welcome(now)){
  summary="回来啦";summaryColor=ACCENT;
 }else if(settings.awayRest&&companion.away(now)&&standby.resting()){
  summary="离席休息";summaryColor=MUTED;
 }else if(companion.focus.active()){
  auto left=companion.focus.remaining(now);char countdown[40];snprintf(countdown,sizeof(countdown),"%s %02u:%02u · 进行中 %d",companion.focus.resting()?"休息":"专注",unsigned(left/60),unsigned(left%60),active);
  summary=companion.focus.phase==FocusTimer::paused?String(companion.focus.resting()?"休息已暂停 · ":"专注已暂停 · ")+left/60+" 分钟":String(countdown);summaryColor=ACCENT;
 }
 centered(summary,h-64,summaryColor);
 if(ui.tasks.empty())centered(connected?"暂无任务":"等待 Mac 连接",h-40,MUTED);
 else{
  String name=ui.tasks[ui.currentIndex].title.c_str();int left=16,available=w-32;canvas.setFont(&fonts::efontCN_16);
  int width=canvas.textWidth(name),offset=0;
  if(width>available){int cycle=width-available+80;offset=std::min(width-available,std::max(0,(int)((now-ui.currentSince)/60%cycle)-40));}
  canvas.setClipRect(left,h-41,available,20);text(name,left-offset,h-41);canvas.clearClipRect();
 }
 String hint="轻点查看任务";
 if(!ui.tasks.empty())hint=(syncState.live()?label(ui.tasks[ui.currentIndex].state):syncState.linked?"状态未知":"离线快照")+" · "+"轻点查看";
 if(syncState.live()&&waiting)hint="回 Codex 回应 · 轻点查看";
 if(syncState.live()&&ui.unread.count())hint=String("新完成 ")+ui.unread.count()+" 项 · 轻点查看";
 std::string reason=ui.tasks.empty()?"":taskHint(ui.tasks[ui.currentIndex],syncState.live());
 if(!reason.empty())hint=fitTaskHint(reason,w-32,[](const std::string& s){return canvas.textWidth(s.c_str());}).c_str();
 if(standby.resting())hint="休息中 · 轻触唤醒";
 if(!syncState.live()){
  if(syncState.goodSeconds>=0){char stamp[24];snprintf(stamp,sizeof(stamp),"上次同步 %02d:%02d",syncState.goodSeconds/3600,syncState.goodSeconds/60%60);hint=stamp;if(syncState.age(now)>=86400)hint+=" · 超过一天";}
  else hint="尚未收到有效任务数据";
 }
 if(desktopAction.feedback(now)[0]){hint=desktopAction.feedback(now);reason="";}
 if(homeProgress.index>=0&&!ui.tasks.empty()&&homeProgress.index==ui.currentIndex&&syncState.live()&&!standby.resting()&&ui.tasks[ui.currentIndex].state=="running"&&homeProgress.key==ui.tasks[ui.currentIndex].id+"\n"+ui.tasks[ui.currentIndex].progressHint){
  canvas.setClipRect(16,h-19,w-32,18);
  text(ui.tasks[ui.currentIndex].progressHint.c_str(),16-homeProgress.offset,h-19,ACCENT);
  canvas.clearClipRect();
 }else centered(hint,h-19,!reason.empty()&&!standby.resting()?(waiting?0xFD6B:!ui.tasks.empty()&&ui.tasks[ui.currentIndex].state=="running"?ACCENT:0x77D5):syncState.live()&&ui.unread.count()&&!standby.resting()?0x77D5:MUTED);
}
void details(uint32_t now,bool header){
 int w=canvas.width(),h=canvas.height();
 if(header){
  bool pressed=gesture.active&&pressedHit==Hit::back&&gesture.maxTravel<=8&&gesture.axis==Axis::pending;
  backButton(pressed,true);
  canvas.drawRoundRect(108,28,96,36,6,0x3186);text("番茄钟",132,38,ACCENT);
  canvas.drawRoundRect(208,28,100,36,6,0x3186);text("设置",242,38,ACCENT);
 }
 auto layout=listLayout();int offset=int(lroundf(ui.scroll.visualOffset()));
 canvas.setClipRect(12,layout.rowsTop(),w-26,layout.viewportHeight());
 if(cacheReady)taskCache.pushSprite(&canvas,12,layout.rowsTop()-offset);
 else for(int i=0;i<int(ui.tasks.size());i++){
  int y=layout.rowsTop()+i*layout.rowHeight()-offset;
  if(y+layout.rowHeight()<=layout.rowsTop())continue;
  if(y>=layout.rowsBottom())break;
  drawTaskRow(canvas,i,12,y,w-26);
 }
 canvas.clearClipRect();
 int focus=titlePlayback.index;
 if(focus>=0&&focus<int(titleLines.size())){
  int top=layout.rowsTop()+focus*layout.rowHeight()-offset+TaskRow::titleTop;
  int clipTop=std::max(top,layout.rowsTop()),clipBottom=std::min(top+TaskRow::titleHeight,layout.rowsBottom());
  if(clipBottom>clipTop){
   canvas.setClipRect(32,clipTop,w-54,clipBottom-clipTop);canvas.fillRect(32,top,w-54,TaskRow::titleHeight,BG);
   for(int l=0;l<int(titleLines[focus].size());l++)text(titleLines[focus][l].c_str(),32,top+l*TaskRow::lineHeight-titlePlayback.offset);
   canvas.clearClipRect();
  }
 }
 int progress=listProgress.index;
 if(progress>=0&&progress<int(ui.tasks.size())&&syncState.live()&&!standby.resting()&&rowFullyVisible(progress,ui.scroll.visualOffset(),layout.rowHeight(),layout.viewportHeight())&&ui.tasks[progress].state=="running"&&listProgress.key==ui.tasks[progress].id+"\n"+ui.tasks[progress].progressHint){
  int y=layout.rowsTop()+progress*layout.rowHeight()-offset+TaskRow::statusTop;
  // 只覆盖状态行，保留标题、分隔线和滚动条；不重建任务缓存。
  canvas.setClipRect(32,y,w-52,18);canvas.fillRect(32,y,w-52,18,BG);
  text(ui.tasks[progress].progressHint.c_str(),32-listProgress.offset,y,ACCENT);
  canvas.clearClipRect();
 }
 if(ui.tasks.empty())centered("暂无任务",h/2,MUTED);
 if(ui.scroll.maximum()>0){
  int track=layout.viewportHeight(),thumb=std::max(18,track*track/(int(ui.tasks.size())*layout.rowHeight()));
  int y=layout.rowsTop()+int((track-thumb)*ui.scroll.offset/ui.scroll.maximum());
  canvas.fillRoundRect(w-8,layout.rowsTop(),3,track,1,0x2104);
  canvas.fillRoundRect(w-8,y,3,thumb,1,ui.scroll.held?ACCENT:MUTED);
 }
 if(touchFeedback&&(gesture.active||uint32_t(now-touchFeedbackAt)<140)&&touchY>=layout.rowsTop()){
  canvas.setClipRect(0,layout.rowsTop(),w,layout.viewportHeight());
  canvas.drawCircle(touchX,touchY,gesture.active?8:10,gesture.axis==Axis::vertical?ACCENT:0x39C7);
  canvas.clearClipRect();
 }
}
void drawSettings(){
 backButton();canvas.drawRoundRect(208,28,100,36,7,0x3186);
 const char* sections[]={"日常","提醒","陪伴","亲昵","外观"};text(sections[settingsPage],153,38,MUTED);text(String(sections[SettingsLayout::nextPage(settingsPage)])+" >",226,38,ACCENT);
 if(settingsPage==4){
  text("外观皮肤",16,90);canvas.drawRoundRect(164,76,144,44,7,ACCENT);
  String value=String(settings.skinLabel())+" >";canvas.setFont(&fonts::efontCN_16);text(value,236-canvas.textWidth(value)/2,90,ACCENT);
  centered("默认脸 / 猫系脸",148,MUTED);centered("只换外观 · 互动照常",178,MUTED);
 }else if(settingsPage==2||settingsPage==3){
  const char* names[]={"表情频率","锁屏休息","回来迎接"};
  int rows=settingsPage==2?3:1;
  for(int row=0;row<rows;row++){
   int y=76+row*48;bool on=settingsPage==3?settings.affection:row==1?settings.awayRest:settings.greeting;
   text(settingsPage==3?"摸头后亲昵":names[row],16,y+14);
   String value=settingsPage==2&&row==0?String(settings.dailyLabel())+" >":on?"开启":"关闭";
   auto ink=settingsPage==2&&row==0?ACCENT:on?ACCENT:MUTED;
   canvas.drawRoundRect(164,y,144,44,7,ink==MUTED?0x3186:ACCENT);canvas.setFont(&fonts::efontCN_16);text(value,236-canvas.textWidth(value)/2,y+14,ink);
  }
  if(settingsPage==3){centered("摸完后 · 偶尔眯眼回应",145,MUTED);centered("直接摸头的表情仍保留",172,MUTED);centered("只改变表情 · 不增加动作",199,MUTED);}
 }else if(settingsPage==1){
  const char* labels[]={"待你回应","任务完成"};
  for(int row=0;row<2;row++){
   int y=76+row*48;bool on=row==0?settings.waitMotion:settings.doneMotion;
   text(labels[row],16,y+14);canvas.drawRoundRect(164,y,144,44,7,on?ACCENT:0x3186);text(on?"轻点头":"仅屏幕",212,y+14,on?ACCENT:MUTED);
  }
  centered("单次小动作 · 间隔至少20秒",185,MUTED);
 }else{
 const char* names[]={"屏幕亮度","空闲休息","摸头动作"};
 for(int row=0;row<3;row++){
  int y=76+row*48;text(names[row],16,y+14);canvas.drawFastHLine(16,y+46,292,0x2104);
  if(row<2){
   for(int x:{164,264}){canvas.drawRoundRect(x,y,44,44,7,0x3186);canvas.drawFastHLine(x+15,y+22,14,ACCENT);if(x==264)canvas.drawFastVLine(x+22,y+15,14,ACCENT);}
   String value=row==0?settings.lightLabel():settings.restLabel();canvas.setFont(&fonts::efontCN_16);text(value,236-canvas.textWidth(value)/2,y+14,ACCENT);
  }else{canvas.drawRoundRect(164,y,144,44,7,settings.petMotion?ACCENT:0x3186);text(settings.petMotion?"开启":"关闭",220,y+14,settings.petMotion?ACCENT:MUTED);}
 }
 }
 centered(settingsSaveFailed?"保存失败 · 返回时重试":settingsDirty?"正在保存…":"自动保存 · 重启后保留",223,settingsSaveFailed?0xFD20:MUTED);
}
void drawFocus(uint32_t now){
 auto& timer=companion.focus;bool started=timer.phase!=FocusTimer::off;
 bool controls=focusPresentation.controls(now,started);
 auto waiting=focusWaitingTarget(ui.tasks,syncState.live(),ui.currentIndex);
 bool card=started&&controls&&waiting.task;
 uint32_t left=timer.active()?timer.remaining(now):timer.phase==FocusTimer::done?0:focusMinutes*60;
 if(started)FocusDial::ring(canvas,FocusDial::remainingRatio(timer.total,timer.used(now)),controls,timer.phase==FocusTimer::paused,card,timer.resting());
 FocusDial::digits(canvas,left,started?(controls?(card?110:108):120):108,!started||controls,timer.phase==FocusTimer::done);
 if(timer.resting())centered(timer.phase==FocusTimer::done?"休息结束":"休息",controls?148:57,0x8559);
 if(!controls){if(waiting.task)canvas.fillCircle(250,42,4,0xFD6B);return;}
 if(!started){
  centered(focusSummarySaveFailed?"专注记录保存失败":focusSummaryText(),3,focusSummarySaveFailed?0xFD6B:MUTED);
  const int choices[]={15,25,45};
  for(int i=0;i<3;i++){
   int x=12+i*102;bool chosen=focusMinutes==choices[i];
   canvas.drawRoundRect(x,24,92,40,7,chosen?ACCENT:0x3186);
   text(String(choices[i])+" 分钟",x+18,36,chosen?ACCENT:MUTED);
  }
  canvas.drawRoundRect(12,146,296,32,7,0x3186);text("到时轻点头",28,154,MUTED);text(settings.focusMotion?"开启":"关闭",258,154,settings.focusMotion?ACCENT:MUTED);
 }else if(card){
  const uint16_t amber=0xFD6B;canvas.drawRoundRect(12,3,296,37,7,0x6244);
  const char* feedback=focusActionFeedback?desktopAction.feedback(now):"";
  if(gesture.active&&focusWaitingPress.captured){
   uint32_t held=now-gesture.startAt;
   centered(focusWaitingPress.fired?(*feedback?feedback:"已发送打开请求"):focusWaitingPress.canceled?"已取消 · 松手重试":"继续按住…",13,amber);
   if(!focusWaitingPress.canceled)canvas.fillRect(24,35,int(272*std::min(1.0f,held/900.0f)),2,amber);
  }else if(*feedback)centered(feedback,13,amber);
  else{
   canvas.fillCircle(25,21,3,amber);text(String("待回应 ")+waiting.count,35,13,amber);
   cropped(waiting.task->title.c_str(),112,13,110,&fonts::efontCN_16);
   text(desktopAction.armed?"长按打开":"同步中…",232,13,amber);
  }
 }else{
  const char* feedback=focusActionFeedback?desktopAction.feedback(now):"";
  centered(*feedback?String(feedback):focusSummaryText(),16,*feedback?0xFD6B:MUTED);
 }
 const int x[]={12,108,212};const int width[]={88,96,96};
 const char* primary=timer.phase==FocusTimer::running?"暂停":timer.phase==FocusTimer::paused?"继续":timer.phase==FocusTimer::done?"下一轮":"开始";
 const char* labels[]={"退出",primary,"结束"};
 for(int i=0;i<3;i++){
  canvas.drawRoundRect(x[i],186,width[i],48,8,i==1?ACCENT:0x3186);
  canvas.setFont(&fonts::efontCN_16);text(labels[i],x[i]+(width[i]-canvas.textWidth(labels[i]))/2,202,i==1?ACCENT:MUTED);
 }
}
void openFocus(uint32_t now){focusOpen=true;settingsOpen=false;ui.details=false;focusActionFeedback=false;focusWaitingPress.reset();focusPresentation.hide();standby.wake(now);daily.cancel(now);fullRedraw=true;}
void focusTap(FocusHit hit,uint32_t now){
 auto phaseBefore=companion.focus.phase;auto stageBefore=companion.focus.stage;
 tickFocus(now);auto& timer=companion.focus;focusPresentation.reveal(now);
 if(hit==FocusHit::primary&&(phaseBefore!=timer.phase||stageBefore!=timer.stage)){fullRedraw=true;return;}
 if(hit==FocusHit::back){focusOpen=false;ui.returnHome(now);}
 else if(hit==FocusHit::stop)timer.stop();
 else if(hit==FocusHit::motion&&timer.phase==FocusTimer::off){settings.focusMotion=!settings.focusMotion;settingsChanged();}
 else if(hit==FocusHit::primary){
  if(timer.phase==FocusTimer::running)timer.pause(now);
  else if(timer.phase==FocusTimer::paused)timer.resume(now);
  else if(timer.phase==FocusTimer::done){if(timer.next(now))focusPresentation.hide();}
  else {timer.start(focusMinutes*60,now);focusPresentation.hide();}
 }else if(!timer.active()){
  if(hit==FocusHit::shorter)focusMinutes=15;
  if(hit==FocusHit::normal)focusMinutes=25;
  if(hit==FocusHit::longer)focusMinutes=45;
 }
 saveFocusSummary(true);standby.wake(now);daily.cancel(now);fullRedraw=true;
}
uint32_t frameDrawUs=0,framePushUs=0;
void render(){
 uint32_t start=micros();bool full=fullRedraw||settingsOpen||focusOpen||!ui.details||!lastWasDetails;
 if(ui.details&&!settingsOpen&&!focusOpen)rebuildTaskCache();
 if(full){canvas.fillScreen(BG);if(!focusOpen)statusBar();}
 else canvas.fillRect(0,listLayout().rowsTop(),canvas.width(),listLayout().viewportHeight(),BG);
 if(focusOpen)drawFocus(millis());else if(settingsOpen)drawSettings();else if(ui.details)details(millis(),full);else home(millis());
 uint32_t drawn=micros();
 if(!full)M5.Display.setClipRect(0,listLayout().rowsTop(),canvas.width(),listLayout().viewportHeight());
 canvas.pushSprite(0,0);M5.Display.clearClipRect();
 frameDrawUs=drawn-start;framePushUs=micros()-drawn;
 fullRedraw=false;lastWasDetails=ui.details;lastDrawOffset=int(lroundf(ui.scroll.visualOffset()));
 lastTitleIndex=titlePlayback.index;lastTitleOffset=titlePlayback.offset;
 lastProgressIndex=listProgress.index;lastProgressOffset=listProgress.offset;
}
// 显式诊断：用真实任务跑固定的列表渲染基准，结束后恢复原界面及位置。
void benchmark(){
 bool wasDetails=ui.details;float wasOffset=ui.scroll.offset,wasStretch=ui.scroll.stretch;ui.details=true;ui.scroll.stretch=0;fullRedraw=true;
 uint32_t draw=0,push=0,worst=0;
 for(int i=0;i<25;i++){
  ui.scroll.offset=ui.scroll.maximum()*i/24;render();
  if(i){draw+=frameDrawUs;push+=framePushUs;worst=std::max(worst,frameDrawUs+framePushUs);}delay(1);
 }
 ui.details=wasDetails;ui.scroll.offset=wasOffset;ui.scroll.stretch=wasStretch;fullRedraw=true;render();
 Serial.printf("PERF\t24\t%u\t%u\t%u\t%d\t%d\n",unsigned(draw/24),unsigned(push/24),unsigned(worst),cacheReady,canvasInPsram);
}
// 诊断只读当前屏幕和 UI 状态；不改变真实任务状态。
void snapshot(){
 render();int w=canvas.width(),h=canvas.height();Serial.printf("FRAME\t%d\t%d\n",w,h);
 uint8_t row[640];
 for(int y=0;y<h;y++){for(int x=0;x<w;x++){uint16_t c=canvas.readPixel(x,y);row[2*x]=c>>8;row[2*x+1]=c&255;}Serial.write(row,w*2);}
}
void inspect(){Serial.printf("UI\t%s\t%d\t%d\t%d\t%d\t%d\n",ui.details?"list":"home",(int)ui.scroll.offset,(int)ui.tasks.size(),headReady,headRaw,headHits);}
void inspectStandby(){Serial.printf("STANDBY\t%s\tbrightness=%d\tidle_ms=%u\tconnected=%d\n",standby.resting()?"rest":"awake",displayBrightness,unsigned(standby.idleFor(millis())),connected);}
void inspectProximityStandby(){
 uint8_t control=0xFF;
 bool readOk=M5.In_I2C.readRegister(0x23,0x81,&control,1,100000);
 Serial.printf("PROX\tstandby=%d\tread_ok=%d\tcontrol=%u\n",readOk&&(control&3)==0,readOk,unsigned(control));
}
void reply(const String& message,SyncTransport via){if(via==SyncTransport::ble)ble.reply(message+"\n");else Serial.println(message);}
void deviceReport(const String& seq,SyncTransport via){
 String page=focusOpen?"focus":settingsOpen?"settings":ui.details?"list":"home";
 String report="DEVICE\t"+seq+"\t0.46\t"+String(battery)+"\t"+String(charging?1:0)+"\t"+page;
 report+="\t"+String(standby.resting()?1:0)+"\t"+String(displayBrightness);
 report+="\t"+String(settings.light)+"\t"+String(settings.rest)+"\t"+String(settings.petMotion?1:0);
 report+="\t"+String(settingsSaveFailed?1:0)+"\t"+String(millis()/1000)+"\t"+String(syncState.age(millis()));
 report+="\t"+String(settings.waitMotion?1:0)+"\t"+String(settings.doneMotion?1:0);
 uint32_t now=millis();
 report+="\t"+String(motion.petState(now))+"\t"+motion.faultReason()+"\t"+String(motion.cooldown(now));
 report+="\t"+String(motion.feedback.sensorOK?1:0)+"\t"+String(motion.feedback.event)+"\t"+String(motion.feedback.age(now));
 report+="\t"+String(motion.feedback.result)+"\t"+motion.feedback.reason+"\t"+String(motion.feedback.held()?1:0);
 report+="\t"+String(settings.daily)+"\t"+String(settings.awayRest?1:0)+"\t"+String(settings.greeting?1:0)+"\t"+String(settings.affection?1:0)+"\t"+String(settings.skin)+"\t"+String(settings.focusMotion?1:0);
 reply(report,via);
}
void tickFocus(uint32_t now){
 auto& timer=companion.focus;focusSummary.sample(now,timer);timer.tick(now);
 if(handledStageCompletion!=timer.completions){
  handledStageCompletion=timer.completions;saveFocusSummary(true);standby.wake(now);daily.cancel(now);fullRedraw=true;focusPresentation.hide();
 }
 if(handledFocusCompletion!=timer.focusCompletions){
  handledFocusCompletion=timer.focusCompletions;
  // 仅专注结束沿用原独立动作；休息结束只更新屏幕，迟到事件也不补播。
  if(uint32_t(now-timer.lastFocusEnd)<5000)motion.requestFocus(now,headRaw!=0,gesture.active||M5.Touch.getCount()>0);
 }
}
void companionReport(const String& seq,SyncTransport via){
 uint32_t now=millis();
 tickFocus(now);
 reply("COMPANION\t"+seq+"\t"+companion.presence(now)+"\t"+companion.focus.name()+"\t"+String(companion.focus.remaining(now))+"\t"+String(companion.focus.total)+"\t"+String(companion.welcome(now)?1:0)+"\t"+companion.focus.stageName()+"\t"+String(companion.focus.focusTotal)+"\t"+String(companion.focus.round)+"\t"+String(focusSummary.day())+"\t"+String(focusSummary.seconds())+"\t"+String(focusSummary.rounds())+"\t"+String(focusSummarySaveFailed?1:0),via);
}
void receive(SyncTransport via=SyncTransport::usb){
 int p=0;String kind=field(line,p);
 if(kind=="TOUCH_INFO"&&via==SyncTransport::usb){
  Serial.printf("TOUCH\tready=%d\trecovered=%d\tcount=%d\n",touchControllerReady(touchIo),touchStartup.recovered,M5.Touch.getCount());return;
 }
 if(kind=="PING"){reply("READY\t"+ble.deviceId,via);return;}
 if(kind=="SYNC_INFO"){
  reply(String("SYNC\t")+(connected?"connected":"waiting")+"\t"+(syncState.transport==SyncTransport::ble?"ble":"usb")+"\t"+(syncState.available?"ok":"unavailable")+"\tage="+syncState.age(millis()),via);return;
 }
 if(kind=="DEVICE_INFO"||kind=="DEVICE_SET"){
  String seq=field(line,p);
  if(!number(seq)||seq.length()>10){reply("ERROR\trequest",via);return;}
  if(kind=="DEVICE_INFO"){
   if(p<int(line.length())){reply("DEVICE_ERROR\t"+seq+"\tinvalid",via);return;}
  }else{
   String light=field(line,p),rest=field(line,p),petMotion=field(line,p),waiting="-",done="-",frequency="-",away="-",greeting="-",affection="-",skin="-",focusMotion="-";auto next=settings;
   if(p<int(line.length())){waiting=field(line,p);done=field(line,p);}
   if(p<int(line.length())){frequency=field(line,p);away=field(line,p);greeting=field(line,p);affection=field(line,p);}
   if(p<int(line.length()))skin=field(line,p);
   if(p<int(line.length()))focusMotion=field(line,p);
   if(p<int(line.length())||!patchDeviceSettings(next,light.c_str(),rest.c_str(),petMotion.c_str(),waiting.c_str(),done.c_str(),frequency.c_str(),away.c_str(),greeting.c_str(),affection.c_str(),skin.c_str(),focusMotion.c_str())){reply("DEVICE_ERROR\t"+seq+"\tinvalid",via);return;}
   if(next.packed()!=settings.packed()||settingsSaveFailed){settings=next;settingsChanged();}
   // 设置页尚未保存的触屏改动也一并保存；只在真实存储成功后确认。
   if(!saveSettings()){reply("DEVICE_ERROR\t"+seq+"\tsave_failed",via);return;}
  }
  deviceReport(seq,via);return;
 }
 if(kind=="ACTION_GET"||kind=="ACTION_RESULT"){
  String seq=field(line,p),argument=field(line,p);uint32_t now=millis();
  if(!number(seq)||seq.length()>10){reply("ERROR\trequest",via);return;}
  bool owner=syncState.live()&&syncState.transport==via;
  desktopAction.tick(now);
  if(kind=="ACTION_GET"){
   if(p<int(line.length())||(argument!="arm"&&argument!="poll")){reply("ERROR\trequest",via);return;}
   if(argument=="arm"&&owner){desktopAction.reset();desktopAction.armed=true;}
   if(owner&&desktopAction.available(now)){
    desktopAction.queued=false;
    reply("ACTION\t"+seq+"\t"+String(desktopAction.serial)+"\t"+desktopAction.thread.c_str(),via);
   }else reply("ACTION\t"+seq+"\t0\t-",via);
  }else{
   String outcome=field(line,p);
   if(p<int(line.length())||!number(argument)||argument.length()>10||strtoull(argument.c_str(),nullptr,10)>UINT32_MAX||!(outcome=="opened"||outcome=="stale"||outcome=="locked"||outcome=="failed")){reply("ERROR\trequest",via);return;}
   if(owner&&desktopAction.finish(uint32_t(strtoull(argument.c_str(),nullptr,10)),outcome.c_str(),now))fullRedraw=true;
   reply("ACTION_ACK\t"+seq,via);
  }
  return;
 }
 if(kind=="NOTE_INFO"||kind=="NOTE_SET"){
  String seq=field(line,p);
  if(!number(seq)||seq.length()>10){reply("ERROR\trequest",via);return;}
  if(kind=="NOTE_SET"){
   String expected=field(line,p),action=field(line,p),encoded=field(line,p);std::string body;
   if(p<int(line.length())||!number(expected)||expected.length()>10||strtoull(expected.c_str(),nullptr,10)>UINT32_MAX||!StickyNote::unhex(encoded.c_str(),body)){reply("NOTE_ERROR\t"+seq+"\tinvalid",via);return;}
   StickyNote next;const char* error=stickyNote.update(uint32_t(strtoull(expected.c_str(),nullptr,10)),action.c_str(),body,next);
   if(*error){reply("NOTE_ERROR\t"+seq+"\t"+error,via);return;}
   if((next.revision!=stickyNote.revision||noteSaveFailed)&&!persistNote(next)){reply("NOTE_ERROR\t"+seq+"\tsave_failed",via);return;}
   stickyPress.observe(stickyNote,noteVisible());fullRedraw=true;
  }else if(p<int(line.length())){reply("NOTE_ERROR\t"+seq+"\tinvalid",via);return;}
  reply("NOTE\t"+seq+"\t"+String(stickyNote.revision)+"\t"+stickyNote.state.c_str()+"\t"+StickyNote::hex(stickyNote.text).c_str()+"\t"+String(noteSaveFailed?1:0),via);return;
 }
 if(kind=="COMPANION_INFO"||kind=="COMPANION_SET"||kind=="FOCUS_SET"){
  String seq=field(line,p);uint32_t now=millis();
  if(!number(seq)||seq.length()>10){reply("ERROR\trequest",via);return;}
  tickFocus(now);
  bool valid=true;
  if(kind=="COMPANION_SET"){
   String state=field(line,p),token=field(line,p),date="";
   if(p<int(line.length()))date=field(line,p);
   bool validDate=date.length()==0||(number(date)&&date.length()<=10&&strtoull(date.c_str(),nullptr,10)>=946684800ULL&&strtoull(date.c_str(),nullptr,10)<=4102444799ULL);
   valid=validDate&&(state=="awake"||state=="away"||state=="unknown")&&number(token)&&token.length()<=10&&strtoull(token.c_str(),nullptr,10)<=UINT32_MAX&&p>=int(line.length());
   if(valid&&date.length()){focusSummary.sync(uint32_t(strtoull(date.c_str(),nullptr,10)),now,companion.focus);}
   if(valid&&companion.accept(state.c_str(),uint32_t(strtoull(token.c_str(),nullptr,10)),now)){standby.wake(now);daily.cancel(now);fullRedraw=true;}
  }else if(kind=="FOCUS_SET"){
   String action=field(line,p),minutes=field(line,p);
   valid=number(minutes)&&minutes.length()<=2&&p>=int(line.length())&&((action=="start"&&minutes.toInt()>=1&&minutes.toInt()<=90)||((action=="stop"||action=="pause"||action=="resume"||action=="next")&&minutes=="0"));
   if(valid){
    if(action=="start"&&companion.focus.active()){reply("COMPANION_ERROR\t"+seq+"\tbusy",via);return;}
    if(action=="start"){focusMinutes=minutes.toInt();companion.focus.start(minutes.toInt()*60,now);focusPresentation.hide();}
    else if(action=="stop")companion.focus.stop();
    else if(action=="next"){if(!companion.focus.next(now)){reply("COMPANION_ERROR\t"+seq+"\tbusy",via);return;}focusPresentation.hide();}
    else if(action=="pause"&&!companion.focus.pause(now)){reply("COMPANION_ERROR\t"+seq+"\tbusy",via);return;}
    else if(action=="resume"&&!companion.focus.resume(now)){reply("COMPANION_ERROR\t"+seq+"\tbusy",via);return;}
    standby.wake(now);daily.cancel(now);fullRedraw=true;
   }
  }else valid=p>=int(line.length());
  if(!valid){reply("COMPANION_ERROR\t"+seq+"\tinvalid",via);return;}
  saveFocusSummary(kind=="FOCUS_SET");companionReport(seq,via);return;
 }
 if(via==SyncTransport::ble&&kind!="SC5"&&kind!="SC6"&&kind!="SC7"&&kind!="SC8"){reply("ERROR\tcommand",via);return;}
 if(kind=="BIND_BLE"){
  String key=field(line,p);if(p<int(line.length())||!ble.provision(key)){Serial.println("BIND\terror");return;}
  Serial.println("BIND\tok\t"+ble.deviceId);return;
 }
 if(kind=="SHOT"){snapshot();return;}
 if(kind=="INFO"){inspect();return;}
 // 显式 USB 验收入口；BLE 白名单在上方已拒绝这些命令。
 if(kind=="CAT_INFO"){Serial.printf("CAT\t%s\t%s\n",faceName(selectedFace(millis())),DailyAnimator::name(daily.kind));return;}
 if(kind=="CAT_DEMO"&&dailyEligible(millis())){cat.preview(millis());daily.cancel(millis());standby.wake(millis());fullRedraw=true;return;}
 if(kind=="IDLE_DEMO"){
  String choice=field(line,p);if(p<int(line.length())||!dailyEligible(millis()))return;
  DailyKind next=choice=="look"?DailyKind::look:choice=="grin"?DailyKind::grin:choice=="yawn"?DailyKind::yawn:DailyKind::none;
  if(next!=DailyKind::none){daily.kind=next;daily.since=millis();fullRedraw=true;}return;
 }
 if(kind=="PROGRESS_INFO"){Serial.printf("PROGRESS\thome_index=%d\thome_offset=%d\thome_travel=%d\tlist_index=%d\tlist_offset=%d\tlist_travel=%d\n",homeProgress.index,homeProgress.offset,homeProgress.travel,listProgress.index,listProgress.offset,listProgress.travel);return;}
 if(kind=="ACTION_INFO"){Serial.printf("ACTION_STATE\tarmed=%d\tqueued=%d\tinflight=%d\tserial=%u\n",desktopAction.armed,desktopAction.queued,desktopAction.inFlight,unsigned(desktopAction.serial));return;}
 if(kind=="READING_INFO"){Serial.printf("READING\tunread=%d\tfocus=%d\ttitle_offset=%d\n",ui.unread.count(),titlePlayback.index,titlePlayback.offset);return;}
 // 仅 USB 显式诊断可以定位列表；不增加任何触屏选任务或翻页操作。
 if(kind=="FOCUS_VIEW"){openFocus(millis());reply("FOCUS_VIEW\tok",via);return;}
 if(kind=="FOCUS_CONTROLS"&&focusOpen){focusPresentation.reveal(millis());fullRedraw=true;reply("FOCUS_CONTROLS\tok",via);return;}
 if(kind=="LIST_VIEW"){
  String offset=field(line,p);if(!number(offset)||offset.length()>4||p<int(line.length()))return;
  daily.cancel(millis());focusOpen=false;settingsOpen=false;ui.open(millis());ui.scroll.offset=ui.scroll.clamp(offset.toInt());standby.wake(millis());fullRedraw=true;inspect();return;
 }
 if(kind=="HOME_VIEW"){daily.cancel(millis());focusOpen=false;settingsOpen=false;ui.returnHome(millis());fullRedraw=true;inspect();return;}
 if(kind=="STANDBY_INFO"){inspectStandby();return;}
 if(kind=="FACE_INFO"){Serial.printf("FACE\t%s\n",faceName(selectedFace(millis())));return;}
 if(kind=="RITUAL_INFO"){Serial.printf("RITUAL\t%s\t%u\n",restRitual.name(millis()),unsigned(millis()-restRitual.since));return;}
 if(kind=="RITUAL_PREVIEW"&&line=="RITUAL_PREVIEW\twake"&&!standby.resting()&&dailyEligible(millis())){
  restRitual.previewWake(poseFor(FaceMood::rest),millis());daily.cancel(millis());fullRedraw=true;return;
 }
 if(kind=="MOTION_INFO"){motion.inspect();return;}
 if(kind=="PROX_INFO"){inspectProximityStandby();return;}
 if(kind=="SETTINGS_INFO"){inspectSettings();return;}
 if(kind=="SETTINGS_OPEN"){focusOpen=false;daily.cancel(millis());settingsPage=0;settingsOpen=true;ui.scroll.end(millis());standby.wake(millis());fullRedraw=true;return;}
 if(kind=="SETTINGS_PAGE"){
  String page=field(line,p);if(page.length()!=1||!number(page)||page.toInt()>4||p<int(line.length())||!settingsOpen)return;
  settingsPage=page.toInt();fullRedraw=true;return;
 }
 if(kind=="SETTINGS_CLOSE"){settingsOpen=false;ui.details=true;fullRedraw=true;return;}
 if(kind=="SETTINGS_SET"){
  String l=field(line,p),r=field(line,p),m=field(line,p);
  if(p<int(line.length())||l.length()!=1||r.length()!=1||m.length()!=1||!number(l)||!number(r)||!number(m)||!settings.set(l.toInt(),r.toInt(),m.toInt())){Serial.println("SETTINGS\terror");return;}
  settingsChanged();saveSettings();inspectSettings();return;
 }
 if(kind=="PET_DEMO"){
  if(!gesture.active&&motion.requestPet(millis())){standby.wake(millis());pet=true;lastPet=millis();fullRedraw=true;}
  else Serial.println("MOTION\tskipped\tpet-guard");
  return;
 }
 if(kind=="MOTION_OFF"){motion.disable();return;}
 if(kind=="MOTION_ON"){motion.enabled=true;motion.inspect();return;}
 if(kind=="NUDGE_WAIT"||kind=="NUDGE_DONE"){
  Serial.println("MOTION\tskipped\tnotice-motion-disabled");return;
 }
 if(kind=="BENCH"){benchmark();return;}
 if(kind=="TIME"){
  String v=field(line,p);if(number(v)&&v.length()<=5&&v.toInt()<86400){if(!clockReady||clockSeconds/60!=uint32_t(v.toInt())/60)fullRedraw=true;clockSeconds=v.toInt();clockTick=millis();clockReady=true;}return;
 }
 if(kind!="SC2"&&kind!="SC3"&&kind!="SC4"&&kind!="SC5"&&kind!="SC6"&&kind!="SC7"&&kind!="SC8")return;
 String seq=field(line,p),nStr=field(line,p);if(!number(seq)||!number(nStr))return;int n=nStr.toInt();if(n>8)return;
 bool dataOk=true,baseline=false;int goodSeconds=clockReady?int(clockSeconds):-1;uint32_t age=0,newClock=clockSeconds;
 if(kind=="SC5"||(kind=="SC6"||kind=="SC7"||kind=="SC8")){
  String available=field(line,p),stamp=field(line,p),good=field(line,p),elapsed=field(line,p),base=field(line,p);
  if((available!="ok"&&available!="unavailable")||!number(stamp)||stamp.length()>5||stamp.toInt()>=86400||(good!="-"&&(!number(good)||good.length()>5||good.toInt()>=86400))||!number(elapsed)||elapsed.length()>7||elapsed.toInt()>604800||(base!="0"&&base!="1"))return;
  dataOk=available=="ok";newClock=stamp.toInt();goodSeconds=good=="-"?-1:good.toInt();age=elapsed.toInt();baseline=base=="1";
 }
 if(via==SyncTransport::usb&&connected&&syncState.transport==SyncTransport::ble&&uint32_t(millis()-lastPacket)<15000){reply("BUSY\t"+seq,via);return;}
 std::vector<Task> next;
 for(int i=0;i<n;i++){
  if(p>=int(line.length()))return;
  String id=field(line,p),state=field(line,p),name=field(line,p);
  if(id.length()!=36||!known(state)||!name.length()||name.length()>240)return;
  String doneKey,waitKey,mood="idle",reason,resultHint,progressHint;
  if(kind=="SC3"||kind=="SC4"||kind=="SC5"||(kind=="SC6"||kind=="SC7"||kind=="SC8")){
   if(p>=int(line.length()))return;doneKey=field(line,p);
   if(p>=int(line.length()))return;waitKey=field(line,p);
   if(doneKey=="-")doneKey="";if(waitKey=="-")waitKey="";
   if(doneKey.length()>16||waitKey.length()>16)return;
  }
  if(kind=="SC4"||kind=="SC5"||(kind=="SC6"||kind=="SC7"||kind=="SC8")){
   if(p>=int(line.length()))return;mood=field(line,p);
   if(!knownExpression(mood.c_str()))return;
  }
  if((kind=="SC6"||kind=="SC7"||kind=="SC8")){
   if(p>=int(line.length()))return;reason=field(line,p);
   if(reason=="-")reason="";
   if(!validTaskHint(std::string(reason.c_str(),reason.length())))return;
   if((kind=="SC7"||kind=="SC8")&&state=="done"&&dataOk)resultHint=reason;
   if(kind=="SC8"&&state=="running"&&dataOk)progressHint=reason;
   if(state!="needs_input"||!dataOk)reason="";
  }
  next.push_back({id.c_str(),state.c_str(),name.c_str(),doneKey.c_str(),waitKey.c_str(),mood.c_str(),reason.c_str(),resultHint.c_str(),progressHint.c_str()});
 }
 if(p<int(line.length()))return;
 if(!dataOk&&next.empty()){next=ui.tasks;for(auto& task:next){task.state="unknown";task.mood="idle";task.doneKey="";task.waitKey="";task.waitReason="";task.resultHint="";task.progressHint="";}}
 bool changed=next.size()!=ui.tasks.size()||!connected||syncState.available!=dataOk||syncState.transport!=via;
 if(!changed)for(int i=0;i<int(next.size());i++)if(next[i].id!=ui.tasks[i].id||next[i].state!=ui.tasks[i].state||next[i].title!=ui.tasks[i].title||next[i].waitReason!=ui.tasks[i].waitReason||next[i].resultHint!=ui.tasks[i].resultHint||next[i].progressHint!=ui.tasks[i].progressHint){changed=true;break;}
 uint32_t beforeNotice=ui.noticeSerial;
 uint32_t beforeUnread=ui.unread.revision;
 bool live=syncState.live()&&syncState.transport==via&&!baseline&&dataOk;
 if(!live)desktopAction.reset();
 standby.observe(ui.tasks,next,connected&&syncState.available==dataOk&&!baseline,millis());
 ui.update(next,millis(),live);connected=true;lastPacket=millis();
 syncState.accept(lastPacket,via,dataOk,goodSeconds,age);
 observeDesktopPresses();
 if(kind=="SC5"||(kind=="SC6"||kind=="SC7"||kind=="SC8")){if(!clockReady||clockSeconds/60!=newClock/60)fullRedraw=true;clockSeconds=newClock;clockTick=lastPacket;clockReady=true;}
 if(!dataOk)ui.celebrating=false;
 if(ui.noticeSerial!=beforeNotice){
  daily.cancel(millis());
  standby.wake(millis());
  fullRedraw=true;
  Serial.printf("NOTICE\t%s\tcompleted=%d\n",ui.latestNotice.kind==NoticeKind::waiting?"waiting":"done",ui.latestNotice.completed);
  // 仅此刻的新事件有资格触发，开关变化和重连不补播；触摸时丢弃，不排队。
  if(!focusOpen)motion.request(settings.notificationMotion(ui.latestNotice),millis(),headRaw!=0,gesture.active||M5.Touch.getCount()>0);
 }
 if(changed||beforeUnread!=ui.unread.revision){cacheDirty=true;fullRedraw=true;}
 reply("ACK\t"+seq,via);
}
void setup(){
 auto cfg=M5.config();cfg.internal_spk=false;cfg.internal_mic=false;cfg.external_spk=0;cfg.external_speaker_value=0;cfg.external_display_value=0;cfg.internal_imu=false;cfg.internal_rtc=false;
 M5.begin(cfg);M5.Speaker.setVolume(0);M5.Speaker.end();M5.Mic.end();
 daily.seed=esp_random();if(!daily.seed)daily.seed=7;
 // 使用连续触点坐标；防抖由我们自己的 4px 起滑与点击规则负责。
 M5.Touch.setFlickThresh(0);
 Serial.setRxBufferSize(4096);Serial.begin(115200);
 touchStartup=initializeTouchController(touchIo);
 Serial.printf("TOUCH\tready=%d\trecovered=%d\n",touchStartup.ready,touchStartup.recovered);
 Preferences notes;if(notes.begin("weiguang_note",true)){
  size_t size=notes.getBytesLength("note");if(size){if(size>=13&&size<=109){std::string bytes(size,'\0');if(notes.getBytes("note",&bytes[0],size)!=size||!stickyNote.load(bytes))noteSaveFailed=true;}else noteSaveFailed=true;}notes.end();
 }
 Preferences stats;if(stats.begin("weiguang_focus",true)){uint32_t words[8];if(stats.getBytesLength("summary")==sizeof(words)&&stats.getBytes("summary",words,sizeof(words))==sizeof(words)){if(!focusSummary.load(words))focusSummarySaveFailed=true;}stats.end();}
 Preferences prefs;if(prefs.begin("weiguang_ui",true)){settings.load(prefs.getUInt("prefs",settings.packed()));prefs.end();}
 standby.configure(settings.brightness(),settings.idleMs(),millis());standby.begin(millis());displayBrightness=settings.brightness();
 M5.Display.setRotation(1);M5.Display.setBrightness(displayBrightness);
 daily.seed=esp_random()|1u;
 uint8_t probe=0;headReady=head.readRegister(SI12T_CTRL1_ADDR,&probe,1);
 if(headReady){head.begin();headReady=head.SI12T_Read_Sensitivity()==0x33;}
 Serial.printf("HEAD\t%d\n",headReady);
 motion.begin();
 motion.configure(settings.petMotion,settings.waitMotion,settings.doneMotion,settings.focusMotion);
 daily.configure(settings.daily,millis());
 companion.configureGreeting(settings.greeting);
 cat.setAffection(settings.affection);
 // 旧固件可能在软重启后留下接近通道开启；明确置为待机，不再采样或触发互动。
 bool proximityStopped=M5.In_I2C.writeRegister8(0x23,0x81,0,100000);
 Serial.printf("PROX\tstop_ok=%d\n",proximityStopped);inspectProximityStandby();
 // 活动帧缓冲优先使用片内 RAM，避免每帧在慢速 PSRAM 逐像素绘制。
 canvas.setPsram(false);canvas.setColorDepth(16);
 if(!canvas.createSprite(M5.Display.width(),M5.Display.height())){
  canvas.setPsram(true);canvasInPsram=true;
  if(!canvas.createSprite(M5.Display.width(),M5.Display.height())){M5.Display.fillScreen(BG);M5.Display.print("Display buffer error");return;}
 }
 canvas.setTextWrap(false,false);ui.scroll.rowHeight=listLayout().rowHeight();ui.scroll.viewportHeight=listLayout().viewportHeight();render();ble.begin();
}
void loop(){
 std::string wireless;
 if(ble.poll(wireless)){String saved=line;line=String(wireless.c_str());receive(SyncTransport::ble);line=saved;}
 while(Serial.available()){char c=Serial.read();if(c=='\n'){if(!overflow)receive();line="";overflow=false;}else if(c!='\r'){if(line.length()<4096)line+=c;else overflow=true;}}
 M5.update();uint32_t now=millis();bool wasCelebrating=ui.celebrating;ui.tick(now);
 desktopAction.tick(now);
 if(syncState.expire(now)){desktopAction.reset();connected=false;standby.wake(now);cacheDirty=true;fullRedraw=true;}
 tickFocus(now);observeDesktopPresses();
 if(wasCelebrating!=ui.celebrating)fullRedraw=true;
 stickyPress.observe(stickyNote,noteVisible());
 if(M5.Touch.getCount()){
  auto t=M5.Touch.getDetail();
  if(t.wasPressed()){wakeTouch.begin(standby,now);fullRedraw=true;}
  if(wakeTouch.consumed){
   standby.wake(now);
   if(t.wasReleased())wakeTouch.end();
  }else{
  if(t.wasPressed()){
   daily.cancel(now);cat.cancel();
   pressedInFocus=focusOpen;pressedFocusPhase=companion.focus.phase;pressedFocusStage=companion.focus.stage;
   pressedFocusControls=focusPresentation.controls(now,companion.focus.phase!=FocusTimer::off);
   pressedFocus=FocusLayout::hit(t.x,t.y,companion.focus.phase!=FocusTimer::off);
   bool waitingActionReady=desktopAction.armed&&!desktopAction.inFlight&&!(focusActionFeedback&&*desktopAction.feedback(now));
   focusWaitingPress.begin(focusWaitingTarget(ui.tasks,syncState.live(),ui.currentIndex),pressedInFocus&&pressedFocusControls,companion.focus.phase!=FocusTimer::off,waitingActionReady,t.x,t.y);
   if(pressedInFocus&&pressedFocusControls)focusPresentation.reveal(now);
   stickyPress.begin(stickyNote,!ui.details&&!settingsOpen&&!focusOpen&&noteVisible(),t.x,t.y);
   pressedHomeFocus=!ui.details&&!settingsOpen&&!focusOpen&&homeFocusEntry(t.x,t.y);
   waitingPress.begin(waitingTask(),!ui.details&&!settingsOpen&&!focusOpen&&desktopAction.armed&&!desktopAction.inFlight,waitingRegion,t.x,t.y);
   pressedInSettings=settingsOpen;pressedSetting=SettingsLayout::hit(t.x,t.y,settingsPage);
   pressedInList=ui.details&&!settingsOpen&&!focusOpen;pressedHit=listLayout().hit(t.x,t.y);
   pressedFocusEntry=pressedInList&&FocusLayout::entry(t.x,t.y);
   pressedSettingsEntry=pressedInList&&SettingsLayout::entry(t.x,t.y);
   pressedInRows=pressedInList&&listLayout().inRows(t.x,t.y);
   gesture.begin(t.x,t.y,now,pressedInRows);
   if(pressedInList)ui.scroll.begin(now);
   touchFeedback=true;touchFeedbackAt=now;touchX=t.x;touchY=t.y;
   if(pressedHit==Hit::back)fullRedraw=true;
  }
  if(gesture.active&&t.isPressed()&&!t.wasReleased()){
   int dy=gesture.move(t.x,t.y);if(pressedInRows)ui.scroll.drag(dy,now);
   touchX=t.x;touchY=t.y;touchFeedbackAt=now;
   if(pressedInFocus&&pressedFocusControls)focusPresentation.reveal(now);
   if(pressedInFocus&&focusOpen){
    if(focusWaitingPress.poll(focusWaitingTarget(ui.tasks,syncState.live(),ui.currentIndex),desktopAction.armed&&!desktopAction.inFlight,
      pressedFocusPhase==companion.focus.phase&&pressedFocusStage==companion.focus.stage,gesture,t.x,t.y,now)){
     focusActionFeedback=desktopAction.request(focusWaitingPress.id,now)||focusActionFeedback;fullRedraw=true;
    }
   }else if(waitingPress.poll(waitingTask(),!ui.details&&!settingsOpen&&!focusOpen&&desktopAction.armed&&!desktopAction.inFlight,gesture,t.x,t.y,now)){
    desktopAction.request(waitingPress.id,now);fullRedraw=true;
   }
  }
  if(t.wasReleased()){
   auto action=gesture.release(t.x,t.y,now);
   touchFeedbackAt=now;
   if(pressedInFocus&&focusOpen){
    if(focusWaitingPress.captured){
     focusPresentation.reveal(now);fullRedraw=true;
    }else if(action.tap){
     if(!pressedFocusControls||pressedFocusPhase!=companion.focus.phase||pressedFocusStage!=companion.focus.stage){focusPresentation.reveal(now);fullRedraw=true;}
     else if(pressedFocus==FocusLayout::hit(t.x,t.y,companion.focus.phase!=FocusTimer::off))focusTap(pressedFocus,now);
    }
   }
   else if(pressedInSettings&&settingsOpen){
    if(action.tap&&pressedSetting==SettingsLayout::hit(t.x,t.y,settingsPage)){
     if(pressedSetting==SettingHit::back){
      if(settingsSaveFailed)settingsDirty=true;
      if(saveSettings()){settingsOpen=false;ui.details=true;fullRedraw=true;}
     }else if(pressedSetting==SettingHit::section){settingsPage=SettingsLayout::nextPage(settingsPage);fullRedraw=true;}
     else if(SettingsLayout::change(settings,pressedSetting))settingsChanged();
    }
   }
   else if(!pressedInList&&!ui.details&&!settingsOpen&&!focusOpen){
    if(stickyPress.captured){
     if(stickyPress.release(stickyNote,noteVisible(),gesture,t.x,t.y,now)){
      StickyNote next;if(!*stickyNote.update(stickyPress.revision,"done","",next))persistNote(next);
      fullRedraw=true;
     }else if(action.tap&&!stickyPress.canceled){ui.open(now);fullRedraw=true;}
    }else if(waitingPress.fired){
     fullRedraw=true;
    }else if(action.tap&&pressedHomeFocus&&homeFocusEntry(t.x,t.y))openFocus(now);
    else if(action.tap){ui.open(now);fullRedraw=true;}
   }
   else if(pressedInList&&ui.details){
    if(pressedInRows)ui.scroll.drag(action.dragY,now);
    ui.scroll.end(now);
    if(action.tap&&pressedFocusEntry&&FocusLayout::entry(t.x,t.y))openFocus(now);
    else if(action.tap&&pressedSettingsEntry&&SettingsLayout::entry(t.x,t.y)){settingsPage=0;settingsOpen=true;fullRedraw=true;}
    else if(action.tap&&pressedHit==listLayout().hit(t.x,t.y)){
     if(pressedHit==Hit::back){ui.returnHome(now);fullRedraw=true;}
    }
   }
   if(pressedHit==Hit::back)fullRedraw=true;
   waitingPress.reset();stickyPress.captured=false;focusWaitingPress.reset();inspect();
  }
  }
 }
 if(headReady&&now-lastHead>=50){
  lastHead=now;uint8_t raw=0;
  if(head.readRegister(SI12T_OUTPUT1_ADDR,&raw,1)){
   int next=raw&0x3F;if(next>0){lastPet=now;pet=true;if(headRaw<=0){headHits++;Serial.printf("PET\t%d\n",headHits);}}
   headRaw=next;
  }else headRaw=-1;
 }
 bool screenTouch=gesture.active||M5.Touch.getCount()>0;
 if(screenTouch||headRaw>0){localWake=true;localWakeAt=now;companion.dismissWelcome();}
 cat.update(headReady?headRaw:-1,screenTouch,now);
 // 反馈观察同一套去抖与避让门槛，不新增动作或重试。
 if(motion.feedback.update(headReady?headRaw:-1,screenTouch,motion.active(),now)){
  pet=true;lastPet=now;fullRedraw=true;
  Serial.printf("PET\thead\t%u\n",unsigned(now));
  motion.requestPet(now,true);
 }
 if(motion.isPetting()){pet=true;lastPet=now;}
 motion.tick(now,headRaw>0,screenTouch);
 if(settingsDirty&&!screenTouch&&!motion.active()&&uint32_t(now-settingsChangedAt)>=1200)saveSettings();
 if(clockReady){uint32_t elapsed=(now-clockTick)/1000,next=(clockSeconds+elapsed)%86400;if(next/60!=clockSeconds/60)fullRedraw=true;clockSeconds=next;clockTick+=elapsed*1000;}
 if(lastBattery==0||now-lastBattery>=10000){lastBattery=now;int before=battery;bool wasCharging=charging;battery=M5.Power.getBatteryLevel();if(battery<0||battery>100)battery=-1;charging=M5.Power.isCharging()==m5::Power_Class::is_charging;if(before!=battery||wasCharging!=charging)fullRedraw=true;Serial.printf("POWER\t%d\t%d\n",battery,charging?1:0);}
 bool wasResting=standby.resting();
 if(!screenTouch&&!motion.active())saveFocusSummary();
 bool waiting=false;if(syncState.live())for(const auto&t:ui.tasks)waiting|=t.state=="needs_input";
 bool interaction=screenTouch||cat.content(now)||headRaw>0||motion.active()||ui.celebrating||(pet&&uint32_t(now-lastPet)<2600);
 if(!focusOpen&&settings.awayRest&&companion.away(now)&&!waiting&&!interaction&&!companion.focus.finished(now)&&!(localWake&&uint32_t(now-localWakeAt)<10000))standby.settle(now);
 else standby.tick(now,syncState.live(),ui.tasks,interaction||focusOpen||companion.welcome(now)||companion.focus.phase==FocusTimer::running||companion.focus.finished(now)||(settings.awayRest&&companion.away(now)&&localWake&&uint32_t(now-localWakeAt)<10000));
 bool ritualBlocked=waiting||ui.celebrating||companion.welcome(now)||companion.focus.finished(now)||ui.details||settingsOpen||focusOpen||screenTouch;
 restRitual.update(standby.resting(),headRaw>0,ritualBlocked,faceAnimator.pose(now),now);
 daily.tick(now,dailyEligible(now),dailyContext(now));
 if(wasResting!=standby.resting()){fullRedraw=true;inspectStandby();}
 int nextBrightness=int(lroundf(standby.brightness(now)));
 if(nextBrightness!=displayBrightness){displayBrightness=nextBrightness;M5.Display.setBrightness(displayBrightness);}
 if(cacheDirty)prepareTaskTitles();
 bool reading=ui.details&&!settingsOpen&&!focusOpen&&!standby.resting()&&!screenTouch&&!ui.scroll.held&&!ui.scroll.moving();
 float offset=ui.scroll.visualOffset();
 if(std::fabs(readingOffset-offset)>.01f)reading=false;
 readingOffset=offset;
 uint32_t beforeUnread=ui.unread.revision;
 ui.unread.readVisible(ui.tasks,offset,ui.scroll.rowHeight,ui.scroll.viewportHeight,now,reading&&syncState.live());
 if(beforeUnread!=ui.unread.revision){cacheDirty=true;fullRedraw=true;}
 int focus=-1;
 if(reading)for(int i=0;i<int(titleLines.size());i++)if(titleLines[i].size()>2&&rowFullyVisible(i,offset,ui.scroll.rowHeight,ui.scroll.viewportHeight)){focus=i;break;}
 titlePlayback.tick(focus>=0?ui.tasks[focus].id+"\n"+ui.tasks[focus].title:"",focus,focus>=0?int(titleLines[focus].size()):0,now,reading);
 int homeFocus=-1,progressFocus=-1;
 bool progressAllowed=syncState.live()&&!settingsOpen&&!focusOpen&&!standby.resting()&&!screenTouch;
 if(progressAllowed&&!ui.details&&!ui.tasks.empty()&&ui.tasks[ui.currentIndex].state=="running"&&!ui.tasks[ui.currentIndex].progressHint.empty())homeFocus=ui.currentIndex;
 if(progressAllowed&&reading)for(int i=0;i<int(ui.tasks.size());i++){
  if(ui.tasks[i].state=="running"&&progressWidths[i]>canvas.width()-52&&rowFullyVisible(i,offset,ui.scroll.rowHeight,ui.scroll.viewportHeight)){progressFocus=i;break;}
 }
 homeProgress.tick(homeFocus>=0?ui.tasks[homeFocus].id+"\n"+ui.tasks[homeFocus].progressHint:"",homeFocus,homeFocus>=0?progressWidths[homeFocus]:0,canvas.width()-32,now,homeFocus>=0);
 listProgress.tick(progressFocus>=0?ui.tasks[progressFocus].id+"\n"+ui.tasks[progressFocus].progressHint:"",progressFocus,progressFocus>=0?progressWidths[progressFocus]:0,canvas.width()-52,now,progressFocus>=0);
 if(touchFeedback&&!gesture.active&&uint32_t(now-touchFeedbackAt)>=140){touchFeedback=false;fullRedraw=true;}
 bool feedbackFrame=touchFeedback;
 bool needsFrame=focusOpen||!ui.details||fullRedraw||cacheDirty||feedbackFrame||lastDrawOffset!=int(lroundf(ui.scroll.visualOffset()))||lastTitleIndex!=titlePlayback.index||lastTitleOffset!=titlePlayback.offset||lastProgressIndex!=listProgress.index||lastProgressOffset!=listProgress.offset;
 if(needsFrame&&now-lastFrame>=(ui.details?16:standby.resting()&&!restRitual.active(now)?160:65)&&canvas.width()){lastFrame=now;render();}delay(1);
}
