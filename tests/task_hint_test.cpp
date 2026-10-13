#include <cassert>
#include "task_hint.h"
#include "ui_state.h"
int main(){
    Task task={"one","needs_input","任务","","q","idle","待答：选择提醒方式"};
    assert(validTaskHint(task.waitReason));
    assert(waitingHint(task,true)==task.waitReason);
    assert(waitingHint(task,false).empty());
    task.state="done";assert(waitingHint(task,true).empty());task.state="needs_input";
    assert(!validTaskHint(std::string(129,'a')));
    assert(!validTaskHint("bad\ncommand")&&!validTaskHint("bad\tfield"));
    assert(!validTaskHint(std::string("a\0b",3)));
    assert(!validTaskHint("\xc0\xaf")&&!validTaskHint("\xed\xa0\x80")&&!validTaskHint("\xf4\x90\x80\x80"));
    assert(!validTaskHint("\xe4\xb8")&&validTaskHint("😀"));
    auto width=[](const std::string&s){return int(s.size());};
    assert(fitTaskHint("短提示",9,width)=="短提示");
    assert(fitTaskHint("待答：选择提醒方式",12,width)=="待答：…");
    assert(fitTaskHint("很长",2,width).empty());
    UiState ui;ui.update({task},100);auto serial=ui.noticeSerial;
    task.waitReason="待答：剩余第二项";ui.update({task},200);
    assert(ui.tasks[0].waitReason==task.waitReason&&ui.noticeSerial==serial);
    task.state="running";task.waitReason.clear();ui.update({task},300);
    assert(waitingHint(ui.tasks[0],true).empty());
    task.resultHint="摘录：改动已完成，测试未通过";
    assert(taskHint(task,true).empty());
    task.state="done";
    assert(taskHint(task,true)==task.resultHint&&taskHint(task,false).empty());
    task.state="needs_input";task.waitReason="待答：确认范围";
    assert(taskHint(task,true)==task.waitReason);
    // 摘录刷新不会额外产生完成提醒。
    task.state="done";task.doneKey="completion";ui.update({task},400);serial=ui.noticeSerial;
    task.resultHint="摘录：验证尚未完成";ui.update({task},500);assert(ui.noticeSerial==serial);
    // 同一任务的进展更新不会产生完成提醒、改变列表位置或缩小脸部。
    task.state="running";task.doneKey="";task.waitReason="";task.resultHint="";
    task.progressHint="进展：正在编译固件";
    assert(taskHint(task,true)==task.progressHint&&taskHint(task,false).empty());
    Task second=task;second.id="two";second.progressHint="进展：检查设置保存";
    ui.update({task,second,task,second},600);ui.open(600);ui.scroll.offset=86;
    serial=ui.noticeSerial;auto offset=ui.scroll.offset;
    task.progressHint="进展：测试未通过，继续排查";
    ui.update({task,second,task,second},700);
    assert(ui.noticeSerial==serial&&ui.scroll.offset==offset);
    assert(taskHint(ui.tasks[0],true)==task.progressHint);
    task.state="needs_input";task.waitReason="待答：确认范围";
    assert(taskHint(task,true)==task.waitReason);
    task.state="done";task.resultHint="摘录：完成修改";
    assert(taskHint(task,true)==task.resultHint);
    task.state="interrupted";assert(taskHint(task,true).empty());
}
