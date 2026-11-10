# Marks Synapse's leftover driver file for deletion at the next restart (run elevated).
$log = Join-Path $PSScriptRoot 'delete_on_reboot.log'
Add-Type -Namespace W -Name K -MemberDefinition '[DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] public static extern bool MoveFileEx(string a, string b, int f);'
$f = 'C:\Windows\System32\drivers\RzDev_00e5.sys'
$ok = [W.K]::MoveFileEx($f, $null, 4)  # 4 = MOVEFILE_DELAY_UNTIL_REBOOT
"$f marked for deletion at restart: $ok (error $([Runtime.InteropServices.Marshal]::GetLastWin32Error()))" | Set-Content $log
