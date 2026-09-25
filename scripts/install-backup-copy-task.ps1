$ErrorActionPreference = 'Stop'
$taskName = 'AMO-Postgres-Backup-Copy'
$repoRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
$scriptPath = Join-Path $PSScriptRoot 'backup_private_vm.py'
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument ('"' + $scriptPath + '"')
$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At '00:10'),
    (New-ScheduledTaskTrigger -Daily -At '06:10'),
    (New-ScheduledTaskTrigger -Daily -At '12:10'),
    (New-ScheduledTaskTrigger -Daily -At '18:10'),
    (New-ScheduledTaskTrigger -AtLogOn)
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw 'Backup task already exists; inspect it before replacing it.'
}
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description 'Copy and verify AMO VM database backup to the Windows user profile using a restricted SSH key'
# Interactive token: runs while this Windows account is logged in. For a fully
# unattended host, install under a dedicated service account with appropriate
# key/directory ACLs and a non-interactive logon policy.
