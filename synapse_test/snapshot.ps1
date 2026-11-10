# Records everything an installer could add, so a later run can be compared and leftovers listed exactly.
#   powershell -ExecutionPolicy Bypass -File snapshot.ps1 -Out before.json
param([Parameter(Mandatory)][string]$Out)
$ErrorActionPreference = 'SilentlyContinue'

$uninstallKeys = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
                 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
                 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
$folders = "$env:ProgramFiles", "${env:ProgramFiles(x86)}", "$env:ProgramData", "$env:APPDATA", "$env:LOCALAPPDATA",
           "$env:LOCALAPPDATA\Programs", "$env:PUBLIC\Desktop", "$env:USERPROFILE\Desktop",
           "$env:APPDATA\Microsoft\Windows\Start Menu\Programs", "$env:ProgramData\Microsoft\Windows\Start Menu\Programs",
           "$env:SystemRoot\System32\drivers"
$runKeys = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run', 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run',
           'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run'

$snap = [ordered]@{
    apps      = @(Get-ItemProperty $uninstallKeys | ? DisplayName | % { "$($_.DisplayName) | $($_.PSChildName)" } | Sort-Object -Unique)
    services  = @(Get-Service | % { "$($_.Name) | $($_.DisplayName)" } | Sort-Object)
    drivers   = @(Get-CimInstance Win32_SystemDriver | % { "$($_.Name) | $($_.PathName)" } | Sort-Object)
    pnpdrv    = @(pnputil /enum-drivers | Select-String 'Published Name|Original Name|Provider Name' | % { $_.Line.Trim() })
    tasks     = @(Get-ScheduledTask | % { "$($_.TaskPath)$($_.TaskName)" } | Sort-Object)
    run       = @($runKeys | % { $k = $_; (Get-ItemProperty $k).PSObject.Properties | ? Name -notlike 'PS*' | % { "$k | $($_.Name)" } } | Sort-Object)
    folders   = @($folders | % { $f = $_; Get-ChildItem $f -Force | % { "$f\$($_.Name)" } } | Sort-Object)
    hklmsoft  = @(Get-ChildItem 'HKLM:\SOFTWARE', 'HKLM:\SOFTWARE\WOW6432Node', 'HKCU:\Software' | % { $_.Name } | Sort-Object)
    firewall  = @(Get-NetFirewallRule | ? DisplayName -match 'razer' | % { $_.DisplayName } | Sort-Object)
    processes = @(Get-Process | ? Name -match 'razer|rz' | % Name | Sort-Object -Unique)
}
$snap | ConvertTo-Json -Depth 3 | Set-Content -Encoding utf8 $Out
"saved ${Out}: " + (($snap.Keys | % { "$_ $($snap[$_].Count)" }) -join ', ')
