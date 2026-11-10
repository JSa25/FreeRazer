# Publishes the built installer as a GitHub Release; installed copies pick it up within a day.
#   powershell -ExecutionPolicy Bypass -File release.ps1 -Notes "What changed"
# Run build.ps1 first. Bump APP_VERSION in freerazer.pyw for every release, or nobody gets the update.
param([Parameter(Mandatory)][string]$Notes)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$version = [regex]::Match((Get-Content freerazer.pyw -Raw), "APP_VERSION = '([\d.]+)'").Groups[1].Value
foreach ($f in 'dist\FreeRazerSetup.exe', 'dist\FreeRazerSetup.exe.sha256') {
    if (-not (Test-Path $f)) { throw "$f missing: run build.ps1 first" }
}
$hash = (Get-FileHash dist\FreeRazerSetup.exe -Algorithm SHA256).Hash.ToLower()
if ((Get-Content dist\FreeRazerSetup.exe.sha256 -Raw).Split(' ')[0] -ne $hash) { throw 'checksum file is stale: rebuild' }

git push origin HEAD
gh release create "v$version" dist\FreeRazerSetup.exe dist\FreeRazerSetup.exe.sha256 `
    --title "FreeRazer $version" --notes $Notes
