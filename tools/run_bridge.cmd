@echo off
rem Bridge launcher: clears PYTHONPATH/PYTHONHOME properly (quoted set form),
rem otherwise Hermes' site-packages leaks in and pydantic/websockets break.
cd /d %~dp0..
set "PYTHONPATH="
set "PYTHONHOME="
if not exist logs mkdir logs
.venv\Scripts\python.exe -u -m src.main
