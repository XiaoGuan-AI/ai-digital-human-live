@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

rem ============================================================
rem  Cyber-Xiaoya full stack launcher (TianGong / Vidu S2 + OmniVoice)
rem    [1] WSL venv bind-mount   [2] OmniVoice TTS :9877
rem    [3] local bridge :8795     [4] stage page (Edge app + CDP)
rem    [5] cost guard (billing starts only when stage page connects)
rem  Usage: start-vidu.cmd [budget_minutes]
rem ============================================================

set "BUDGET=%~1"
if "%BUDGET%"=="" set "BUDGET=25"

echo [1/5] WSL venv bind-mount ...
wsl -d Ubuntu-24.04 bash -lc "mountpoint -q /mnt/d/Projects/ai-digital-human-live/omnivoice-venv || mount --bind /root/omnivoice-venv /mnt/d/Projects/ai-digital-human-live/omnivoice-venv" 2>nul
wsl -d Ubuntu-24.04 bash -lc "test -x /mnt/d/Projects/ai-digital-human-live/omnivoice-venv/bin/python" 2>nul
if errorlevel 1 (
  echo   ERROR: OmniVoice venv not reachable. Rebuild:
  echo     wsl -d Ubuntu-24.04 bash -lc "uv venv /root/omnivoice-venv --python 3.12"
  echo   then reinstall torch + omnivoice-src ^(see docs\PROJECT-LAYOUT.md^)
  pause
  exit /b 1
)

echo [2/5] OmniVoice TTS on :9877 ...
".venv\Scripts\python.exe" tools\wait_port.py 9877 1 2>nul
if not errorlevel 1 (
  echo   already running, skip
) else (
  wsl -d Ubuntu-24.04 bash -lc "cd /mnt/d/Projects/ai-digital-human-live && export HF_HUB_OFFLINE=1 && nohup /root/omnivoice-venv/bin/omnivoice-demo --model /mnt/d/Projects/ai-digital-human-live/models/OmniVoice --ip 0.0.0.0 --port 9877 --no-asr > logs/omnivoice.log 2>&1 &" 2>nul
  echo   waiting for weights to load (about 20s) ...
  ".venv\Scripts\python.exe" tools\wait_port.py 9877 120 2>nul
  if errorlevel 1 (
    echo   ERROR: 9877 not up. See logs\omnivoice.log in WSL.
    pause
    exit /b 1
  )
)

echo [3/5] bridge on :8795 ...
".venv\Scripts\python.exe" tools\wait_port.py 8795 1 2>nul
if not errorlevel 1 (
  echo   already running, skip
) else (
  start "cx-bridge" /min cmd /c ".venv\Scripts\python.exe -m src.main --port 8795 > logs\bridge.log 2>&1"
  ".venv\Scripts\python.exe" tools\wait_port.py 8795 60 2>nul
  if errorlevel 1 (
    echo   ERROR: bridge failed, see logs\bridge.log
    pause
    exit /b 1
  )
)
curl -s --noproxy "*" -X POST "http://127.0.0.1:8795/api/settings/reload" >nul 2>&1

echo [4/5] stage page (Edge app window + CDP :9334) ...
tasklist /fi "imagename eq msedge.exe" 2>nul | find /i "msedge.exe" >nul
start msedge --remote-debugging-port=9334 --user-data-dir="%CD%\.edge-profile" --no-first-run --no-default-browser-check --app="http://127.0.0.1:8795/stage"

echo.
echo   BILLING: Vidu S2 = 1 credit/sec = about 0.031 CNY/sec
echo            budget %BUDGET% min = about %BUDGET% * 1.875 CNY
echo   Nothing is billed until the stage page connects (phase=live).
echo   Do NOT refresh the stage page - it reconnects and re-bills.
echo.
echo [5/5] cost guard: budget %BUDGET% minutes (Ctrl+C stops guard + session)
".venv\Scripts\python.exe" -u tools\cost_guard.py --budget-min %BUDGET%

endlocal
