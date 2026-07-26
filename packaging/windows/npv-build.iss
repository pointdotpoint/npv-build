#define MyAppName "NPV Build"
#define MyAppPublisher "NPV Build maintainers"
#define MyAppExeName "npv-build.exe"

#ifndef MyAppVersion
  #error MyAppVersion must be passed to ISCC
#endif
#ifndef SourceDir
  #error SourceDir must be passed to ISCC
#endif
#ifndef OutputDir
  #error OutputDir must be passed to ISCC
#endif

[Setup]
AppId={{EB45405B-405C-4A89-BCE7-455E77F56E7A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\NPV Build
DefaultGroupName=NPV Build
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=npv-build-{#MyAppVersion}-windows-x86_64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Icons]
Name: "{autoprograms}\NPV Build"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\NPV Build"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch NPV Build"; Flags: nowait postinstall skipifsilent
