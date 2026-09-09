#define MyAppName "Radar de Inversión"
#define MyAppVersion "1.5.10"
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
; Radar owns background/hidden processes that may keep its one-file executables locked.
; Stop only Radar processes before files are replaced instead of asking the user to
; ignore a partial upgrade. The updater uses the same controlled shutdown policy.
CloseApplications=no
RestartApplications=no
SetupIconFile=..\assets\radar.ico
[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{cmd}'), '/C taskkill /F /IM InvestmentIntelligenceRadar.exe >nul 2>&1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{cmd}'), '/C taskkill /F /IM RadarSimulationLab.exe >nul 2>&1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{cmd}'), '/C taskkill /F /IM RadarWorker.exe >nul 2>&1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{cmd}'), '/C taskkill /F /IM RadarUpdater.exe >nul 2>&1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1200);
  Result := '';
end;
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
