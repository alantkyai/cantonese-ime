; Build with tools/build_release.py. All executable inputs are local, pinned.
#ifndef PayloadRoot
  #error PayloadRoot is required
#endif
#ifndef OutputRoot
  #error OutputRoot is required
#endif
#ifndef ManifestSha256
  #error ManifestSha256 is required
#endif
#ifndef ReleaseVersion
  #error ReleaseVersion is required
#endif

[Setup]
AppId={{3EE61D80-37D3-4CF1-B203-9A26F0E5DA80}
AppName=Cantonese IME
AppVersion={#ReleaseVersion}
AppVerName=Cantonese IME {#ReleaseVersion}
AppPublisher=Cantonese IME
VersionInfoVersion={#ReleaseVersion}.0
VersionInfoProductName=Cantonese IME
VersionInfoDescription=Cantonese IME Installer
DefaultDirName={commonpf64}\CantoneseIME
DisableDirPage=yes
UsePreviousAppDir=no
DefaultGroupName=Cantonese IME
DisableProgramGroupPage=yes
PrivilegesRequired=admin
SetupArchitecture=x64
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
OutputDir={#OutputRoot}
OutputBaseFilename=CantoneseIME-{#ReleaseVersion}-windows-x64-setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=no
RestartApplications=no
RestartIfNeededByRun=no
UninstallDisplayName=Cantonese IME
UninstallDisplayIcon={app}\native\CantoneseMachineRegistration.exe,0
InfoBeforeFile={#PayloadRoot}\RELEASE_NOTICES.txt
InfoAfterFile={#PayloadRoot}\GETTING_STARTED.txt
#ifdef SetupIconFile
SetupIconFile={#SetupIconFile}
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start Cantonese IME automatically when I sign in"; Flags: checkedonce

[Files]
Source: "{#PayloadRoot}\*"; DestDir: "{app}"; Excludes: "__pycache__\*"; Flags: ignoreversion recursesubdirs createallsubdirs uninsrestartdelete
; Bootstrap before copying product files. This interpreter is temporary and
; is never registered globally or added to PATH.
Source: "{#PayloadRoot}\runtime\python\*"; DestDir: "{tmp}\prereq\python"; Flags: dontcopy
Source: "{#PayloadRoot}\installer\lifecycle.py"; DestDir: "{tmp}\prereq"; Flags: dontcopy
Source: "{#PayloadRoot}\package-manifest.json"; DestDir: "{tmp}\prereq"; Flags: dontcopy

[Icons]
Name: "{group}\Enable Cantonese IME"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: "-B ""{app}\installer\lifecycle.py"" finish-user --install-root ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\native\CantoneseMachineRegistration.exe"; IconIndex: 0
Name: "{group}\Stop Cantonese IME"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: "-B ""{app}\installer\lifecycle.py"" stop-user --install-root ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\native\CantoneseMachineRegistration.exe"; IconIndex: 0
Name: "{group}\Cantonese IME Settings"; Filename: "{app}\native\CantoneseImeSettings.exe"; WorkingDir: "{app}"
Name: "{group}\Getting started"; Filename: "{app}\GETTING_STARTED.txt"
Name: "{group}\Third-party notices"; Filename: "{app}\data\THIRD_PARTY_NOTICES.md"

[UninstallDelete]
Type: files; Name: "{app}\machine-registration.plan"
Type: files; Name: "{app}\installation.json"
Type: files; Name: "{app}\installer-machine-*.jsonl"
Type: files; Name: "{app}\native\CantoneseIME.previous-*.dll"
Type: files; Name: "{app}\native\CantoneseIME.failed-*.dll"
Type: files; Name: "{app}\native\CantoneseMachineRegistration.previous-*.exe"
Type: files; Name: "{app}\native\CantoneseMachineRegistration.failed-*.exe"
; Learning, user dictionaries, and user logs are outside {app} and retained.

[Code]
var
  PrerequisitesReady: Boolean;
  UserPrepared: Boolean;
  UserPreparationAttempted: Boolean;
  MachinePrepared: Boolean;
  MachineCommitted: Boolean;
  UserActivated: Boolean;

function Quote(const Value: String): String;
begin
  Result := '"' + Value + '"';
end;

function BootstrapPython: String;
begin
  Result := ExpandConstant('{tmp}\prereq\python\python.exe');
end;

function BootstrapScript: String;
begin
  Result := ExpandConstant('{tmp}\prereq\lifecycle.py');
end;

function RootArgument: String;
begin
  Result := ' --install-root ' + Quote(ExpandConstant('{app}'));
end;

function MachineReceipt: String;
begin
  Result := ExpandConstant('{tmp}\release-machine.json');
end;

procedure ExtractPrerequisites;
begin
  if PrerequisitesReady then Exit;
  ExtractTemporaryFiles('{tmp}\prereq\python\*');
  ExtractTemporaryFiles('{tmp}\prereq\lifecycle.py');
  ExtractTemporaryFiles('{tmp}\prereq\package-manifest.json');
  PrerequisitesReady := True;
end;

function MachineCommand(const Action, Extra: String): Boolean;
var
  Code: Integer;
begin
  Code := -1;
  Result := ExecAndLogOutput(BootstrapPython,
    '-B ' + Quote(BootstrapScript) + ' ' + Action + RootArgument + Extra,
    ExpandConstant('{tmp}'), SW_SHOWNORMAL, ewWaitUntilTerminated, Code, nil);
  if Result then
    Log('Machine lifecycle ' + Action + ' completed with exit code ' + IntToStr(Code))
  else
    Log('Machine lifecycle ' + Action + ' could not launch: Win32 error ' + IntToStr(Code) + ': ' + SysErrorMessage(Code));
  Result := Result and (Code = 0);
end;

function UserCommand(const Action, Extra: String): Boolean;
var
  Code: Integer;
begin
  Code := -1;
  Result := ExecAsOriginalUser(BootstrapPython,
    '-B ' + Quote(BootstrapScript) + ' ' + Action + RootArgument + Extra,
    ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, Code);
  if Result then
    Log('Original-user lifecycle ' + Action + ' completed with exit code ' + IntToStr(Code))
  else
    Log('Original-user lifecycle ' + Action + ' could not launch: Win32 error ' + IntToStr(Code) + ': ' + SysErrorMessage(Code));
  Result := Result and (Code = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  ExtractPrerequisites;
  if not UserPrepared then begin
    UserPreparationAttempted := True;
    if not UserCommand('prepare-user', '') then begin
      Result := 'Cantonese IME could not safely prepare your user account. Start Setup normally (not Run as administrator), and stop Cantonese IME in other Windows sessions before retrying. Your personal learning is unchanged. See the Setup log and %LOCALAPPDATA%\CantoneseIME\Installer.';
      Exit;
    end;
    UserPrepared := True;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then begin
    if not MachineCommand('prepare-machine',
      ' --receipt ' + Quote(MachineReceipt) +
      ' --next-manifest ' + Quote(ExpandConstant('{tmp}\prereq\package-manifest.json')) +
      ' --manifest-sha256 {#ManifestSha256}') then
      RaiseException('The existing installation could not be safely backed up. Stop Cantonese IME in other Windows sessions and retry. No application has been closed.');
    MachinePrepared := True;
  end;
  if CurStep = ssPostInstall then begin
    if not MachineCommand('install-machine',
      ' --receipt ' + Quote(MachineReceipt) + ' --manifest-sha256 {#ManifestSha256}') then
      RaiseException('Windows input profile registration failed. Setup will restore the previous package. See the Setup log and retained protected update backup.');
    MachineCommitted := True;
    if WizardIsTaskSelected('startup') then
      UserActivated := UserCommand('finish-user', '')
    else
      UserActivated := UserCommand('finish-user', ' --no-startup');
    if not UserActivated then begin
      Log('Machine package installed; original-user activation needs attention.');
      if not WizardSilent then
        MsgBox('Cantonese IME files are installed, but activation for your Windows account needs attention. Run Enable Cantonese IME from the Start menu as your ordinary user. The engine was not started as administrator.', mbError, MB_OK);
    end;
  end;
end;

procedure DeinitializeSetup;
begin
  if PrerequisitesReady and not MachineCommitted then begin
    if MachinePrepared or FileExists(MachineReceipt) then
      if not MachineCommand('rollback-machine', ' --receipt ' + Quote(MachineReceipt)) then
        MsgBox('The previous package could not be fully restored. Keep the protected CantoneseIME-Updates backup and inspect the Setup log before retrying.', mbError, MB_OK);
    if UserPreparationAttempted then
      if not UserCommand('restore-user', '') then
        Log('The previous user broker needs to be started from its normal-user shortcut.');
  end;
end;

function GetCustomSetupExitCode: Integer;
begin
  Result := 0;
  if MachinePrepared and not MachineCommitted then
    Result := 11
  else if MachineCommitted and not UserActivated then
    Result := 10;
end;

function InitializeUninstall: Boolean;
begin
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Code: Integer;
  Python, Script, Params: String;
begin
  if CurUninstallStep = usUninstall then begin
    Python := ExpandConstant('{app}\runtime\python\python.exe');
    Script := ExpandConstant('{app}\installer\lifecycle.py');
    Params := '-B ' + Quote(Script) + ' uninstall-machine' + RootArgument;
    Code := -1;
    if not ExecAndLogOutput(Python, Params, ExpandConstant('{app}'), SW_SHOWNORMAL, ewWaitUntilTerminated, Code, nil) or (Code <> 0) then
      RaiseException('Cantonese IME could not be safely removed. Stop it from your ordinary user account, sign out other users, and retry. Your personal learning has been retained.');
  end;
end;
