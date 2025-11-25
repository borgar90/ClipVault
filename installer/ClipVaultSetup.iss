#define MyAppName "ClipVault"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Borgar Flaen Stensrud"
#define MyAppURL "https://borgar-stensrud.no/"
#define MyAppExeName "ClipVault.exe"

[Setup]
AppId={{A0C8F2C1-1E3F-4C18-9E0E-123456789ABC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\ClipVault
DefaultGroupName=ClipVault
OutputBaseFilename=ClipVaultSetup
Compression=lzma
SolidCompression=yes
LicenseFile=license.txt
InfoBeforeFile=info_before.txt
InfoAfterFile=info_after.txt
DisableDirPage=no
DisableProgramGroupPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Start ClipVault when Windows starts"; \
  GroupDescription: "Additional options:"; Flags: unchecked

[Files]
[Files]
; Copy everything PyInstaller produced for ClipVault
Source: "..\dist\ClipVault\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\icon.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\logo.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ClipVault"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\ClipVault"; Filename: "{app}\{#MyAppExeName}"

[Registry]
; Per‑user autostart entry, only if the user checked the task
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#MyAppName}"; \
  ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch ClipVault"; \
  Flags: nowait postinstall skipifsilent
