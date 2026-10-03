@echo off
setlocal
set "ROOT=%~dp0.."
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 was not found.
  echo Install it from https://jrsoftware.org/isinfo.php, then run this script again.
  exit /b 2
)
if not exist "%ROOT%\dist\worthlesstask\worthlesstask.exe" (
  echo Missing dist\worthlesstask\worthlesstask.exe.
  echo Build the portable folder first:  node tools\build-portable.cjs
  exit /b 3
)
"%ISCC%" "%~dp0worthlesstask.iss"
if errorlevel 1 exit /b %errorlevel%
echo Installer written to dist\worthlesstask-Setup-3.1.0.exe
