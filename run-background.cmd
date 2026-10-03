@echo off
REM Start the worthlesstask dashboard without keeping a console window around.
REM Same entry point as run.cmd, detached. Stop it with the Stop button in the
REM panel, or: taskkill /IM worthlesstask.exe /F
setlocal
cd /d "%~dp0"

set "APP=%~dp0outputs\worthlesstask.exe"
if not exist "%APP%" set "APP=%~dp0dist\worthlesstask\worthlesstask.exe"
if exist "%APP%" (
  start "" /b "%APP%" %*
  echo Started in the background from "%APP%"
  echo Dashboard: http://127.0.0.1:8787
  goto :eof
)

set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"

if not defined PYW (
  echo Packaged build not found and pythonw.exe is not on PATH.
  echo Run it in the foreground instead:  run.cmd
  exit /b 1
)

start "" /b "%PYW%" -m worthlesstask web --open %*
echo Started in the background from source.
echo The dashboard opens in your browser automatically.
endlocal
