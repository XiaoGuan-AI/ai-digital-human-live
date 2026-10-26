@echo off
rem TTS launcher (runs inside WSL, but kept as a file so cmd quoting stays simple)
cd /d %~dp0..
set "PYTHONPATH="
set "PYTHONHOME="
wsl -d Ubuntu-24.04 bash -lc "cd /mnt/d/Projects/ai-digital-human-live && exec /root/livetalking/LiveTalking/.venv-lt/bin/python tools/edge_tts_server.py --port 18780"
