#define MyAppName "Radar de Inversión"
#define MyAppVersion "1.5.28"
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
; Wildcard purge is intentional: old builds created both correctly encoded and mojibake names.
Type: files; Name: "{userdesktop}\Radar de Invers*.lnk"
Type: files; Name: "{commondesktop}\Radar de Invers*.lnk"
Type: files; Name: "{userdesktop}\Investment Intelligence Radar*.lnk"
Type: files; Name: "{commondesktop}\Investment Intelligence Radar*.lnk"
[Icons]
; Exactly one desktop shortcut. Simulation Lab remains in Start Menu only.
Name: "{userdesktop}\Radar de Inversión"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{userprograms}\Radar de Inversión"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{userprograms}\Radar de Inversión - Simulation Lab"; Filename: "{app}\{#SimExeName}"; IconFilename: "{app}\{#MyAppExeName}"
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Radar de Inversión"; Flags: nowait postinstall skipifsilent
