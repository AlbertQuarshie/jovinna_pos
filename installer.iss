; Inno Setup recipe for the Jovinna POS installer.
; Build the app first (pyinstaller JovinnaPOS.spec), then:  ISCC.exe installer.iss
; Output: installer_output\JovinnaPOS_Setup_<version>.exe
;
; Shop data lives in %LOCALAPPDATA%\JovinnaPOS and is NEVER touched by installing, updating or
; uninstalling — so reinstalling or upgrading keeps every product, sale and backup.

#define AppName "Jovinna POS"
#define AppVersion "1.0.0"
#define Publisher "Aeternum Devs"
#define ExeName "JovinnaPOS.exe"

[Setup]
; Never change AppId: it's how Windows knows a new version is an update of this app
AppId={{CACB5155-DF7A-40B7-A3A8-9D8BA412895D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#ExeName}
UninstallDisplayName={#AppName}
SetupIconFile=assets\icon.ico
OutputDir=installer_output
OutputBaseFilename=JovinnaPOS_Setup_{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Close the app automatically if it's open during an update
CloseApplications=yes
; Offer "all users" (needs admin) or "just me" (no admin password needed)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
VersionInfoCompany={#Publisher}
VersionInfoProductName={#AppName}
VersionInfoVersion={#AppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\JovinnaPOS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "Open {#AppName} now"; Flags: nowait postinstall skipifsilent
