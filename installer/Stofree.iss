; ============================================================================================
; Stofree - Windows Disk Space Analyzer :: Inno Setup 7 installer script
;
; Build (from the project root, after the ONEDIR build exists in dist\Stofree):
;     "C:\Program Files\Inno Setup 7\ISCC.exe" installer\Stofree.iss
; or simply run  scripts\build_windows.ps1  which does everything in order.
;
; Output: installer-output\Stofree-Setup.exe (unless overridden on the command line).
;
; Requires Inno Setup 7 (uses [Setup] SetupArchitecture, new in 7.0). ASCII only: Inno Setup 7
; refuses to compile .iss/.isl files containing bytes that are invalid in their code page.
; ============================================================================================

; Version: scripts\build_windows.ps1 passes /DAppVersion=<APP_VERSION from constants.py>.
; The fallback below is only used when this file is compiled by hand.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName        "Stofree"
#define AppExeName     "Stofree.exe"
#define AppDescription "Windows Disk Space Analyzer"
#define AppPublisher   "Shanuka B. Herath"
#define DeveloperCredit "Developed by Shanuka B. Herath - Software Developer"

[Setup]
; Stable identity of this application for upgrades and the uninstaller. NEVER change it.
AppId={{2391ED91-82CF-4363-8AB9-A8C6818AD439}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppComments={#DeveloperCredit}
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}

; ---- 64-bit only (PySide6 is 64-bit). Inno Setup 7: build a native 64-bit installer.
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

; ---- Location and permissions
; Default: C:\Program Files\Stofree (all users; needs administrator rights, so Windows shows a UAC
; prompt). With the "dialog" override Setup first asks "for all users or only for me": choosing
; "only for me" needs no elevation and {autopf} becomes %LOCALAPPDATA%\Programs. The user can still
; change the folder on the Select Destination Location page either way.
DefaultDirName={autopf}\{#AppName}
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no

; ---- Wizard pages: Welcome, Licence, Destination, Ready, Progress (always), Finished
DisableWelcomePage=no
DisableDirPage=no
DisableReadyPage=no
DisableFinishedPage=no
LicenseFile=TERMS_AND_CONDITIONS.txt

; ---- Branding (images are generated from logo.png by tools\make_installer_images.py)
SetupIconFile=..\assets\branding\stofree.ico
WizardStyle=modern
WizardImageFile=assets\wizard_large_164x314.png,assets\wizard_large_246x459.png,assets\wizard_large_328x604.png
WizardSmallImageFile=assets\wizard_small_58.png,assets\wizard_small_87.png,assets\wizard_small_116.png

; ---- Output
OutputDir=..\installer-output
OutputBaseFilename=Stofree-Setup
Compression=lzma2/ultra64
SolidCompression=yes

; ---- Version resource of Stofree-Setup.exe
VersionInfoVersion={#AppVersion}.0
VersionInfoProductVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup - {#AppDescription}
VersionInfoCompany={#AppPublisher}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install [name/ver] - {#AppDescription} - on your computer.%n%n{#DeveloperCredit}.%n%nStofree only reads file names, sizes and folder structure. It never deletes, moves or changes your files.%n%nIt is recommended that you close all other applications before continuing.
BeveledLabel={#DeveloperCredit}

[Tasks]
; No "unchecked" flag -> the desktop shortcut is ticked by default.
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; The complete PyInstaller ONEDIR output (Stofree.exe + _internal\ with Python, Qt, assets...),
; not just the exe.
Source: "..\dist\Stofree\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; WorkingDir = the install folder; the shortcuts start the installed Stofree.exe directly.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Comment: "{#AppDescription}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Comment: "{#AppDescription}"; Tasks: desktopicon

[Run]
; "Launch Stofree" checkbox on the last page (ticked by default).
; runasoriginaluser: Stofree starts with the normal user's rights, NOT elevated, even though
; Setup itself ran as administrator. Stofree never needs elevation.
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
// The uninstaller removes only the files Setup installed. User data is never deleted silently:
//  * exported reports live wherever the user saved them and are never touched;
//  * settings and logs live in %LOCALAPPDATA%\Stofree - the user is asked, default answer NO.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  DataDir := ExpandConstant('{localappdata}\{#AppName}');
  if (not DirExists(DataDir)) or UninstallSilent then
    Exit;
  if SuppressibleMsgBox(
       'Stofree has been removed.' + #13#10 + #13#10 +
       'Your Stofree settings and log files are still stored in:' + #13#10 +
       DataDir + #13#10 + #13#10 +
       'Do you also want to delete them?' + #13#10 + #13#10 +
       'Choose No to keep them (they will be reused if you reinstall). ' +
       'Reports you exported are saved elsewhere and will NOT be deleted either way.',
       mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
  begin
    if not DelTree(DataDir, True, True, True) then
      SuppressibleMsgBox('Some files in ' + DataDir + ' could not be deleted. ' +
        'You can remove that folder manually.', mbError, MB_OK, IDOK);
  end;
end;
