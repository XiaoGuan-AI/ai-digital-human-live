@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

rem ============================================================
rem  Stop the whole ai-digital-human-live stack (safe: only our own processes)
rem    [1] end live session   [2] bridge   [3] OmniVoice   [4] stage window
rem  Does NOT touch unrelated python/edge processes.
rem ============================================================

echo [1/4] ending live session (stops billing) ...
curl -s --noproxy "*" -X POST "http://127.0.0.1:8795/api/live/stop" >nul 2>&1

echo [2/4] stopping bridge :8795 ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'src\.main' -and $_.CommandLine -match '8795' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>nul

echo [3/4] stopping OmniVoice TTS :9877 ...
wsl -d Ubuntu-24.04 bash -lc "pkill -f omnivoice-demo" 2>nul

echo [4/4] closing stage window (this profile only) ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { $_.CommandLine -match 'edge-profile' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>nul

echo.
echo Done. Ports 8795 / 9877 / 9334 should be free.
echo Credits: Vidu bills only while a session is live; check balance in the console.
endlocal
