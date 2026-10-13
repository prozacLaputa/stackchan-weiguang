#pragma once
#include <string>
#include <vector>
#include <stdint.h>

struct Task { std::string id,state,title,doneKey,waitKey,mood,waitReason,resultHint,progressHint; };
enum class NoticeKind { none,waiting,done };
struct NoticeEvents {
    NoticeKind kind=NoticeKind::none;
    int completed=0;
    std::string completedId;
    std::vector<std::string> completedIds;
};
class NoticeTracker {
    struct Seen { std::string id,done,waiting; };
    std::vector<Seen> seen;
public:
    NoticeEvents observe(const std::vector<Task>& tasks,bool live){
        NoticeEvents event;
        for(const auto& t:tasks){
            auto it=seen.begin();for(;it!=seen.end()&&it->id!=t.id;++it){}
            if(it==seen.end()){
                // 首次看见的任务只建立基线，避免旧任务、启动与重连补播。
                if(seen.size()>=48)seen.erase(seen.begin());
                seen.push_back({t.id,t.doneKey,t.waitKey});continue;
            }
            if(!t.doneKey.empty()&&t.doneKey!=it->done){
                if(live){event.completed++;event.completedId=t.id;event.completedIds.push_back(t.id);if(event.kind==NoticeKind::none)event.kind=NoticeKind::done;}
                it->done=t.doneKey;
            }
            if(!t.waitKey.empty()&&t.waitKey!=it->waiting){
                if(live)event.kind=NoticeKind::waiting;
                it->waiting=t.waitKey;
            }
        }
        return event;
    }
};
