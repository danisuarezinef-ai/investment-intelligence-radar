; Investment Intelligence Radar — candidate installer definition
; Build only in verified release pipeline. PAPER only.
#define MyAppName "Radar de inversión"
#define MyAppVersion "0.1.0-rc1"
#define MyAppExeName "RadarDeInversion.exe"
[Setup]
AppId={{B87B56A7-48CF-47E0-94AA-21F63A1DB8C1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\Radar de inversion
DefaultGroupName=Radar de inversion
OutputBaseFilename=Radar-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\updater\*"; DestDir: "{app}\updater"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\Radar de inversion"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Radar de inversion"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Radar de inversion"; Flags: nowait postinstall skipifsilent
