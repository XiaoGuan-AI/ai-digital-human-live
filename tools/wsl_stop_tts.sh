#!/bin/bash
# 停掉 WSL 里的 edge-tts 服务（供 stop-stage.cmd 调用）
n=0
for p in $(pgrep -f edge_tts_server 2>/dev/null); do
  kill -9 "$p" 2>/dev/null && n=$((n+1))
done
echo "killed $n"
