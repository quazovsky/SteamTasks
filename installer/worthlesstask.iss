; worthlesstask installer
; Build with Inno Setup 6: ISCC.exe installer\worthlesstask.iss
;
; The install directory stays read-only for a standard user. All mutable data -
; library, icons, logs, worker executables, session record - is written by the app
; under %LOCALAPPDATA%\worthlesstask (see worthlesstask\paths.py), so nothing here needs
; write access. That is what keeps a Program Files install safe to keep.
#define MyAppName "worthlesstask"
#define MyAppVersion "3.1.0"
#define MyAppPublisher "worthlesstask"
#define MyAppExeName "worthlesstask.exe"

[Setup]
AppId={{B2E950C8-52F3-4B0E-9E75-310D9E4A7C01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\worthlesstask
DefaultGroupName=worthlesstask
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
SetupIconFile=..\assets\worthlesstask.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist
OutputBaseFilename=worthlesstask-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
ChangesAssociations=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startup"; Description: "Start worthlesstask when I sign in"; GroupDescription: "Additional options:"; Flags: unchecked

[Files]
; The whole portable folder: the program plus one worker executable per game.
Source: "..\dist\worthlesstask\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\worthlesstask"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\worthlesstask.ico"; WorkingDir: "{app}"
Name: "{autodesktop}\worthlesstask"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\worthlesstask.ico"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\worthlesstask"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\worthlesstask.ico"; WorkingDir: "{app}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch worthlesstask"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\*.writing"
Type: files; Name: "{app}\*.bak"
