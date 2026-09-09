#define MyAppName "Radar de Inversión"
#define MyAppVersion "1.3.3"
#define MyAppExeName "InvestmentIntelligenceRadar.exe"
#define SimExeName "RadarSimulationLab.exe"
[Setup]
AppId={{44C4B1FA-5DC9-42E1-AE16-93AB0F9EA76A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\Investment Intelligence Radar
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=Radar_de_Inversion_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupIconFile=..\assets\radar.ico
[Files]
Source: "..\dist\InvestmentIntelligenceRadar.exe"; DestDir: "{app}"; Flags: ignoreversion restartreplace
Source: "..\dist\RadarSimulationLab.exe"; DestDir: "{app}"; Flags: ignoreversion restartreplace
Source: "..\dist\RadarWorker.exe"; DestDir: "{app}"; Flags: ignoreversion restartreplace
Source: "..\dist\RadarUpdater.exe"; DestDir: "{app}"; Flags: ignoreversion restartreplace
Source: "..\version.json"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{autodesktop}\Radar de Inversión"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Radar de Inversión - Simulation Lab"; Filename: "{app}\{#SimExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{userprograms}\Radar de Inversión"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{userprograms}\Radar de Inversión - Simulation Lab"; Filename: "{app}\{#SimExeName}"; IconFilename: "{app}\{#MyAppExeName}"
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Radar de Inversión"; Flags: nowait postinstall skipifsilent
