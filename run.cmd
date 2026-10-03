@echo off
REM Start the worthlesstask dashboard. This is the main entry point.
REM The packaged build is preferred; without it the source tree is used.
setlocal
cd /d "%~dp0"

set "APP=%~dp0outputs\worthlesstask.exe"
if not exist "%APP%" set "APP=%~dp0dist\worthlesstask\worthlesstask.exe"
if exist "%APP%" (
  start "" "%APP%" %*
  echo worthlesstask started from "%APP%"
  echo The dashboard opens in your browser automatically.
  goto :eof
)

where python >nul 2>nul
if errorlevel 1 (
  echo Neither the packaged build nor python was found.
  echo Expected the build at: %APP%
  exit /b 1
)

echo Packaged build not found, running from source.
python -m worthlesstask web --open %*
endlocal
