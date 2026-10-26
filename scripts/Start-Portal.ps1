param([ValidateSet('Dev','Shared')][string]$FrontendMode = 'Shared', [ValidateSet('All','Backend','Frontend')][string]$Service = 'All', [switch]$Visible)
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$selectedPorts = switch($Service){ 'Backend' {@(8080,8090)} 'Frontend' {@(5173)} default {@(5173,8080,8090)} }
$occupied = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in $selectedPorts }
if($occupied){
 $occupied | Select-Object LocalPort,OwningProcess | Format-Table | Out-Host
 throw 'Portal ports are already in use. Run scripts/Stop-Portal.ps1 or stop the owner in its terminal first.'
}
$shellPath = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if(-not $shellPath){ $shellPath = (Get-Command powershell.exe).Source }
$serviceScript = Join-Path $PSScriptRoot 'Run-PortalService.ps1'
$selectedServices = if($Service -eq 'All'){@('Backend','Frontend')}else{@($Service)}
foreach($serviceName in $selectedServices){
 $arguments = @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$serviceScript+'"'),'-Service',$serviceName,'-FrontendMode',$FrontendMode)
 $windowStyle = if($Visible){ 'Normal' }else{ 'Hidden' }
 $console = Start-Process -FilePath $shellPath -WorkingDirectory $workspaceRoot -ArgumentList $arguments -WindowStyle $windowStyle -PassThru
 Write-Host "$serviceName owner PID: $($console.Id)"
}
Write-Host 'Logs: .artifacts/portal-runtime. Stop both with: .\scripts\Stop-Portal.ps1'
