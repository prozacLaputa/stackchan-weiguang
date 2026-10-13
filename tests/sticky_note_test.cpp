#include "sticky_note.h"
#include <cassert>
#include <iostream>
int main(){
 StickyNote note,next;
 for(const auto& invalid: {std::string(""),std::string("  "),std::string("x\ny"),std::string("🐱"),std::string("a\xe2\x80\xae" "b"),std::string("\xc0\x80"),std::string("\xed\xa0\x80"),std::string(33,'a')})assert(!StickyNote::validText(invalid));
 assert(StickyNote::validText("下班记得带充电器，今晚 7 点见！"));
 std::string longNote;for(int i=0;i<32;i++)longNote+="中";assert(StickyNote::validText(longNote));assert(!StickyNote::validText(longNote+"中"));
 assert(!*note.update(0,"set","下班带充电器",next));assert(note.state=="empty");note=next;assert(note.active()&&note.revision==1);
 assert(std::string(note.update(0,"done","",next))=="conflict");assert(note.active());
 assert(!*note.update(1,"set",note.text,next)&&next.revision==1);
 auto encoded=note.encode();StickyNote restored;assert(restored.load(encoded)&&restored.text==note.text&&restored.revision==1);
 encoded[10]^=1;assert(!restored.load(encoded)&&restored.active());
 assert(!*note.update(1,"done","",next));note=next;assert(!note.active()&&note.state=="done"&&note.text=="下班带充电器"&&note.revision==2);
 assert(restored.load(note.encode())&&restored.state=="done");
 assert(!*note.update(2,"restore","",next));note=next;assert(note.active()&&note.revision==3);
 std::string decoded;assert(StickyNote::unhex(StickyNote::hex(note.text),decoded)&&decoded==note.text);
 for(auto invalid:{"a","gg","","00\t00"})assert(!StickyNote::unhex(invalid,decoded));
 StickyNotePress press;TouchGesture g;
 auto start=[&](){press.begin(note,true,150,190);g.begin(150,190,100,false);};
 start();g.release(150,190,1050);assert(press.release(note,true,g,150,190,1050));
 start();g.release(150,190,500);assert(!press.release(note,true,g,150,190,500));
 start();g.move(170,190);g.release(150,190,1100);assert(!press.release(note,true,g,150,190,1100));
 start();g.release(310,190,1100);assert(!press.release(note,true,g,310,190,1100));
 start();g.release(150,190,5000);assert(!press.release(note,true,g,150,190,5000));
 // 待回应覆盖纸条，即使随后消失，也不能继续沿用原按压。
 start();press.observe(note,false);press.observe(note,true);g.release(150,190,1100);assert(!press.release(note,true,g,150,190,1100));
 start();assert(!*note.update(note.revision,"set","新的便签",next));g.release(150,190,1100);assert(!press.release(next,true,g,150,190,1100));
 press.begin(note,true,150,100);assert(!press.captured);
 note.revision=UINT32_MAX;assert(std::string(note.update(UINT32_MAX,"done","",next))=="invalid");
 std::cout<<"Note text, revision conflicts, persistence, undo and long-press cancellation passed\n";
}
