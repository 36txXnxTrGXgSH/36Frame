; Installateur de 36Frame (Inno Setup 6). Lance par compiler.ps1.
;
; Sans droits d'administrateur : l'application va dans %LOCALAPPDATA%\Programs\36Frame.
; Il declare 36Frame aupres de Windows comme visionneuse d'images (menu « Ouvrir avec »
; et page « Applications par defaut »). Windows 10/11 interdit a un programme de se
; mettre lui-meme par defaut : c'est l'utilisateur qui valide, en un clic, a la fin.

#ifndef Version
  #define Version "0.2.0"
#endif

[Setup]
AppId={{9B1E7C3A-36F4-4A8E-B236-36F7A3E0F136}
AppName=36Frame
AppVersion={#Version}
AppPublisher=36txXnxTrGXgSH
AppPublisherURL=https://github.com/36txXnxTrGXgSH/36Frame
AppSupportURL=https://github.com/36txXnxTrGXgSH/36Frame/issues
AppComments=Liseuse d'images inspiree de Picasa
DefaultDirName={autopf}\36Frame
DefaultGroupName=36Frame
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=dist
OutputBaseFilename=36Frame-Setup-{#Version}
SetupIconFile=assets\36frame.ico
UninstallDisplayIcon={app}\36Frame.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Creer un raccourci sur le bureau"; Flags: unchecked

[Files]
Source: "dist\36Frame\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\36Frame"; Filename: "{app}\36Frame.exe"
Name: "{autodesktop}\36Frame"; Filename: "{app}\36Frame.exe"; Tasks: bureau

[Registry]
; Type de fichier « Image 36Frame »
Root: HKA; Subkey: "Software\Classes\36Frame.Image"; ValueType: string; ValueName: ""; ValueData: "Image 36Frame"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\36Frame.Image\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\36Frame.exe,0"
Root: HKA; Subkey: "Software\Classes\36Frame.Image\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\36Frame.exe"" ""%1"""
; Entree « Applications\36Frame.exe » (liste « Ouvrir avec »)
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "36Frame"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\36Frame.exe"" ""%1"""
; Capacites : 36Frame apparait dans Parametres > Applications > Applications par defaut
Root: HKA; Subkey: "Software\36Frame"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\36Frame\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "36Frame"
Root: HKA; Subkey: "Software\36Frame\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Liseuse d'images inspiree de Picasa"
Root: HKA; Subkey: "Software\36Frame\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\36Frame.exe,0"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "36Frame"; ValueData: "Software\36Frame\Capabilities"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.jpg\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".jpg"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jpg"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".jpeg"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jpeg"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.jpe\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".jpe"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jpe"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.jfif\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".jfif"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jfif"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.png\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".png"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".png"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.webp\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".webp"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".webp"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.avif\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".avif"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".avif"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.bmp\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".bmp"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".bmp"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.dib\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".dib"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".dib"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.tif\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".tif"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".tif"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.tiff\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".tiff"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".tiff"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.gif\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".gif"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".gif"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.ico\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".ico"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ico"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.cur\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".cur"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".cur"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.icns\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".icns"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".icns"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.tga\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".tga"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".tga"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.psd\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".psd"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".psd"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.dds\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".dds"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".dds"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.jp2\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".jp2"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jp2"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.pcx\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".pcx"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pcx"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.ppm\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".ppm"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ppm"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.pgm\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".pgm"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pgm"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.pbm\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".pbm"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pbm"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.xbm\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".xbm"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".xbm"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.xpm\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".xpm"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".xpm"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.wbmp\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".wbmp"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wbmp"; ValueData: "36Frame.Image"
Root: HKA; Subkey: "Software\Classes\.svg\OpenWithProgids"; ValueType: string; ValueName: "36Frame.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\36Frame.exe\SupportedTypes"; ValueType: string; ValueName: ".svg"; ValueData: ""
Root: HKA; Subkey: "Software\36Frame\Capabilities\FileAssociations"; ValueType: string; ValueName: ".svg"; ValueData: "36Frame.Image"

[Run]
Filename: "ms-settings:defaultapps?registeredAppUser=36Frame"; Description: "Choisir 36Frame comme visionneuse par defaut (Parametres Windows)"; Flags: shellexec postinstall skipifsilent nowait
Filename: "{app}\36Frame.exe"; Description: "Lancer 36Frame"; Flags: nowait postinstall skipifsilent unchecked

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM 36Frame.exe"; Flags: runhidden; RunOnceId: "fermer"
