# Removes what today's Synapse 4 install left behind after Razer's own uninstaller ran (run elevated).
$log = Join-Path $PSScriptRoot 'remove_leftovers.log'
"started $(Get-Date)" | Set-Content $log
sc.exe stop RzDev_00e5 2>&1 | Add-Content $log
sc.exe delete RzDev_00e5 2>&1 | Add-Content $log
$files = 'C:\Windows\System32\drivers\RzDev_00e5.sys',
         'C:\Windows\Installer\Razer\Installer2\DownloadCache\Razer_App_Engine_4.0.896.exe',
         'C:\Windows\Installer\Razer\Installer2\DownloadCache\Razer_App_Engine_4.0.896.exe.etag',
         'C:\Windows\Installer\Razer\Installer2\DownloadCache\Razer_Synapse_4.0.896.exe',
         'C:\Windows\Installer\Razer\Installer2\DownloadCache\Razer_Synapse_4.0.896.exe.etag'
foreach ($f in $files) {
    try { Remove-Item -LiteralPath $f -Force -ErrorAction Stop; "removed $f" | Add-Content $log }
    catch { "FAILED $f : $($_.Exception.Message)" | Add-Content $log }
}
"done $(Get-Date)" | Add-Content $log
