; Inno Setup script for FreeRazer. Build with build.ps1 (it passes /DAppVersion from freerazer.pyw).
; Per-user install (no admin), upgrades in place, and is what the in-app updater runs silently.

#ifndef AppVersion
  #error Run build.ps1, which passes /DAppVersion
#endif

[Setup]
; Fixed forever: Windows uses it to recognise upgrades and the Installed apps entry
AppId={{ED2EAA2A-8EF3-4980-9ACF-10D6B468085E}
AppName=FreeRazer
AppVersion={#AppVersion}
AppVerName=FreeRazer {#AppVersion}
AppPublisher=FreeRazer contributors
AppPublisherURL=https://github.com/JSa25/freerazer
AppSupportURL=https://github.com/JSa25/freerazer/issues
DefaultDirName={localappdata}\Programs\FreeRazer
DisableDirPage=yes
; the app was called Mouse Profiles before; upgrades move it to the FreeRazer folder instead of reusing the old one
UsePreviousAppDir=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=FreeRazerSetup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\FreeRazer.exe
UninstallDisplayName=FreeRazer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; the app holds this mutex (the second is the old Mouse Profiles name); Setup and Uninstall ask you to close it first
AppMutex=FreeRazerSingleInstance,MouseProfilesSingleInstance
CloseApplications=yes

[InstallDelete]
; leftovers from when the app was called Mouse Profiles
Type: filesandordirs; Name: "{localappdata}\Programs\Mouse Profiles"
Type: files; Name: "{userprograms}\Mouse Profiles.lnk"

[Files]
Source: "dist\FreeRazer.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\FreeRazer"; Filename: "{app}\FreeRazer.exe"

[Run]
; normal install: offer to open it at the end
Filename: "{app}\FreeRazer.exe"; Description: "Open FreeRazer"; Flags: nowait postinstall skipifsilent
; silent install (the in-app updater): reopen it in the tray and say it updated
Filename: "{app}\FreeRazer.exe"; Parameters: "--tray --updated"; Flags: nowait; Check: WizardSilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // the app's own leftovers: its start-with-Windows entry and, if you say so, your profiles
  // (a silent uninstall can't ask, so it keeps them)
  if CurUninstallStep = usUninstall then
  begin
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'FreeRazer');
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Mouse Profiles');
    if (not UninstallSilent) and (MsgBox('Also delete your FreeRazer profiles?' + #13#10 +
        'Choose No to keep them for a reinstall.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      DelTree(ExpandConstant('{userappdata}\FreeRazer'), True, True, True);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // older versions were installed by install.ps1 with their own Installed apps entry; drop it so there is only one
  if CurStep = ssPostInstall then
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseProfiles');
end;
