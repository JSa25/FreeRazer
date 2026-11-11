# Builds dist\FreeRazer.exe and dist\FreeRazerSetup.exe (+ .sha256) for the version in freerazer.pyw.
#   powershell -ExecutionPolicy Bypass -File build.ps1
# Needs: Python 3.13 with hidapi, pystray, pillow, pyinstaller; Inno Setup 6 (winget install JRSoftware.InnoSetup).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$version = [regex]::Match((Get-Content freerazer.pyw -Raw), "APP_VERSION = '([\d.]+)'").Groups[1].Value
if (-not $version) { throw 'APP_VERSION not found in freerazer.pyw' }
"Building FreeRazer $version"

# the Python to build with: $env:PYTHON if set (the GitHub release workflow sets it), else the py launcher's 3.13
$py, $pyArgs = if ($env:PYTHON) { $env:PYTHON, @() } else { 'py', @('-3.13') }
& $py @pyArgs razer_switch.py test
if ($LASTEXITCODE) { throw 'self-check failed' }

# Only modules proven unused (none load in a run that uses every feature). Do NOT exclude bz2, lzma, decimal,
# PIL.ImageFont or PIL._imagingft: the tray icon and the drawing code need them.
$exclude = 'numpy PIL._avif PIL._webp PIL._imagingcms PIL.ImageCms PIL.AvifImagePlugin PIL.WebPImagePlugin _ssl ssl ' +
           '_hashlib hashlib _pydecimal pydoc pydoc_data pyexpat xml xmlrpc unittest email http urllib sqlite3 ' +
           'multiprocessing asyncio'
$excludeArgs = $exclude.Split(' ') | ForEach-Object { '--exclude-module', $_ }
$icon = Join-Path $PSScriptRoot 'icon.ico'  # absolute: PyInstaller resolves relative paths from --specpath
$db = Join-Path $PSScriptRoot 'devices.json'  # the mouse database the exe starts with
& $py @pyArgs -m PyInstaller --onefile --windowed --name 'FreeRazer' --icon $icon --add-data "$icon;." --add-data "$db;." `
    --paths $PSScriptRoot --hidden-import razer_switch --hidden-import pystray._win32 @excludeArgs `
    --distpath dist --workpath build --specpath build --noconfirm --clean freerazer.pyw
if ($LASTEXITCODE) { throw 'PyInstaller failed' }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw 'Inno Setup 6 not found (winget install JRSoftware.InnoSetup)' }
& $iscc /Q "/DAppVersion=$version" freerazer.iss
if ($LASTEXITCODE) { throw 'Inno Setup failed' }

# the updater checks the download against this before running it
$hash = (Get-FileHash dist\FreeRazerSetup.exe -Algorithm SHA256).Hash.ToLower()
Set-Content dist\FreeRazerSetup.exe.sha256 "$hash  FreeRazerSetup.exe" -Encoding ascii -NoNewline
"Built dist\FreeRazerSetup.exe ($version)  sha256 $hash"
