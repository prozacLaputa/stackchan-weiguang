#!/bin/sh
weiguang_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$weiguang_dir/weiguang" resume
weiguang_result=$?
printf "\n按回车关闭此窗口…"
read -r weiguang_answer
exit "$weiguang_result"
