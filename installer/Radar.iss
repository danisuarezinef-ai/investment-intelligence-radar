#define MyAppName "Investment Intelligence Radar"
#define MyAppVersion "1.0.0"
#define MyAppExeName "InvestmentIntelligenceRadar.exe"
[Setup]
AppId={{44C4B1FA-5DC9-42E1-AE16-93AB0F9EA76A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\Investment Intelligence Radar
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=Investment_Intelligence_Radar_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
[Files]
Source: "..\dist\InvestmentIntelligenceRadar.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\RadarWorker.exe"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{autodesktop}\Investment Intelligence Radar"; Filename: "{app}\{#MyAppExeName}"
Name: "{userprograms}\Investment Intelligence Radar"; Filename: "{app}\{#MyAppExeName}"
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Investment Intelligence Radar"; Flags: nowait postinstall skipifsilent
