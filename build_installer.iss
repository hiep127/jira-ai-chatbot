#define AppName      "Jira AI"
#define AppVersion   "1.0"
#define AppPublisher "LGE"
#define AppExeName   "Jira AI.exe"
#define SourceDir    "dist\JiraAgent"
#define OutputDir    "installer_output"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppId={{A3F2C1D4-7B6E-4F8A-9C2D-1E5B8F3A7D90}
PrivilegesRequired=admin
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=no
OutputDir={#OutputDir}
OutputBaseFilename=Jira_AI_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#SourceDir}\{#AppExeName}
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoCompany={#AppPublisher}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Recursively bundle everything flet pack produced
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{group}\{#AppName}";       Filename: "{app}\{#AppExeName}"
; Start Menu uninstall entry
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
; Desktop shortcut
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
; Optional "Launch Jira AI now" checkbox shown on the final wizard page
Filename: "{app}\{#AppExeName}"; \
    Description: "Launch {#AppName} now"; \
    Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  GhFound: Boolean;
begin
  Result := True;
  GhFound := Exec('cmd.exe', '/c gh --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
             and (ResultCode = 0);
  if not GhFound then
  begin
    if MsgBox(
      'GitHub CLI (gh) was not detected on this machine.' + #13#10#13#10 +
      'Jira AI requires GitHub CLI to authenticate with GitHub Copilot.' + #13#10 +
      'Download and install it from: https://cli.github.com' + #13#10 +
      'Then run: gh auth login' + #13#10#13#10 +
      'You can install gh after setup. Continue anyway?',
      mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;
