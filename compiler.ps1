# Fabrique dist\36Frame-Setup-<version>.exe : l'installateur a lancer.
#
#   powershell -ExecutionPolicy Bypass -File compiler.ps1
#
# Prerequis (deja en place sur ce PC) :
#   - .venv avec les dependances et PyInstaller   (.venv\Scripts\pip install pyinstaller)
#   - Inno Setup 6                                (winget install JRSoftware.InnoSetup)
#
# 1. PyInstaller (36frame.spec) -> dist\36Frame\  (dossier et non exe unique : demarrage instantane,
#    important pour une visionneuse qu'on ouvre d'un double-clic sur une photo) ;
# 2. Inno Setup  -> dist\36Frame-Setup-<version>.exe, sans droits d'administrateur,
#    qui declare 36Frame comme visionneuse d'images aupres de Windows.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

$version = (& $py -c "import frame36; print(frame36.__version__)").Trim()
Write-Host "== 36Frame $version ==" -ForegroundColor Cyan

Write-Host "== Icone ==" -ForegroundColor Cyan
& $py outils\fabriquer_icone.py
if ($LASTEXITCODE -ne 0) { throw "Icone : echec." }

Write-Host "== Compilation (PyInstaller, version installee) ==" -ForegroundColor Cyan
# 36frame.spec retire ce que 36Frame n'utilise jamais (OpenGL logiciel, chiffrement reseau,
# traductions etrangeres...) : programme plus leger, demarrage plus rapide.
$env:MODE = "dossier"; $env:NOM = "36Frame"
& $py -m PyInstaller --noconfirm --clean --distpath dist --workpath build\travail 36frame.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller a echoue." }
Write-Host "== Installateur (Inno Setup) ==" -ForegroundColor Cyan
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup introuvable : winget install JRSoftware.InnoSetup" }
& $iscc /Q "/DVersion=$version" installateur.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup a echoue." }

Write-Host "== Version portable (exe unique) ==" -ForegroundColor Cyan
# Un seul fichier, sans installation. Le nom contient "Portable" : l'appli range alors
# ses reglages et ses miniatures dans "36Frame-donnees" a cote de l'exe.
# Il se decompresse a chaque lancement : pratique, mais plus lent pour ouvrir une image.
$env:MODE = "unique"; $env:NOM = "36Frame-Portable"
& $py -m PyInstaller --noconfirm --clean --distpath Portable --workpath build\travail-portable 36frame.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller (portable) a echoue." }

Write-Host "== Version portable rapide (dossier, en .zip) ==" -ForegroundColor Cyan
# Meme programme que la version installee, sans installation : aussi rapide qu'elle.
$env:MODE = "dossier"; $env:NOM = "36Frame-Portable"
& $py -m PyInstaller --noconfirm --clean --distpath build\portable-dossier --workpath build\travail-portable-dossier 36frame.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller (portable dossier) a echoue." }
$zip = Join-Path $PSScriptRoot "Portable\36Frame-Portable-rapide.zip"
if (Test-Path $zip) { [IO.File]::Delete($zip) }
Copy-Item THIRD_PARTY_NOTICES.md "build\portable-dossier\36Frame-Portable\" -Force
Compress-Archive -Path "build\portable-dossier\36Frame-Portable" -DestinationPath $zip -CompressionLevel Optimal
Remove-Item Env:MODE, Env:NOM
$setup = Join-Path $PSScriptRoot "dist\36Frame-Setup-$version.exe"
$taille = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host ("== Termine : dist\36Frame-Setup-$version.exe (" + $taille + " Mo) ==") -ForegroundColor Green
