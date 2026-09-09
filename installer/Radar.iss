#define MyAppName "Radar de Inversión"
#define MyAppVersion "1.5.13"
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
[InstallDelete]
; Purge every desktop shortcut name emitted by previous releases from both
; per-user and common desktop locations. 1.5.12 only cleaned {autodesktop},
; which can leave a legacy shortcut in the other Windows desktop scope.
Type: files; Name: "{userdesktop}\Investment Intelligence Radar.lnk"
Type: files; Name: "{commondesktop}\Investment Intelligence Radar.lnk"
Type: files; Name: "{userdesktop}\Radar de Inversión.lnk"
Type: files; Name: "{commondesktop}\Radar de Inversión.lnk"
Type: files; Name: "{userdesktop}\Radar de Inversión - Simulation Lab.lnk"
Type: files; Name: "{commondesktop}\Radar de Inversión - Simulation Lab.lnk"
Type: files; Name: "{userdesktop}\Radar de InversiÃ³n.lnk"
Type: files; Name: "{commondesktop}\Radar de InversiÃ³n.lnk"
Type: files; Name: "{userdesktop}\Radar de InversiÃƒÂ³n.lnk"
Type: files; Name: "{commondesktop}\Radar de InversiÃƒÂ³n.lnk"
Type: files; Name: "{userdesktop}\Radar de InversiÃ³n - Simulation Lab.lnk"
Type: files; Name: "{commondesktop}\Radar de InversiÃ³n - Simulation Lab.lnk"
Type: files; Name: "{userdesktop}\Radar de InversiÃƒÂ³n - Simulation Lab.lnk"
Type: files; Name: "{commondesktop}\Radar de InversiÃƒÂ³n - Simulation Lab.lnk"
[Icons]
; Exactly one desktop shortcut. Simulation Lab stays available from the Start menu.
Name: "{userdesktop}\Radar de Inversión"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{userprograms}\Radar de Inversión"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{userprograms}\Radar de Inversión - Simulation Lab"; Filename: "{app}\{#SimExeName}"; IconFilename: "{app}\{#MyAppExeName}"
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Radar de Inversión"; Flags: nowait postinstall skipifsilent
