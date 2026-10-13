#!/bin/sh
weiguang_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$weiguang_dir/weiguang" panel
