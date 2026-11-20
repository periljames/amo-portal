param([ValidateSet('Dev','Shared')][string]$FrontendMode = 'Shared', [ValidateSet('All','Backend','Frontend')][string]$Service = 'All', [switch]$Visible)
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$selectedPorts = switch($Service){ 'Backend' {@(8080,8090)} 'Frontend' {@(5173)} default {@(5173,8080,8090)} }
$occupiedPorts = @(foreach($port in $selectedPorts){
 $probe = [System.Net.Sockets.TcpClient]::new()
 try {
  $connection = $probe.ConnectAsync('127.0.0.1', $port)
  if($connection.Wait(500) -and $probe.Connected){ $port }
 } catch {} finally { $probe.Dispose() }
})
if($occupiedPorts.Count){
 Write-Host "Portal ports already accepting connections: $($occupiedPorts -join ', ')"
 Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in $occupiedPorts } | Select-Object LocalPort,OwningProcess | Format-Table | Out-Host
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
 if($serviceName -eq 'Frontend') {
  $frontendReady = $false
  $readyDeadline = [DateTime]::UtcNow.AddSeconds(120)
  while([DateTime]::UtcNow -lt $readyDeadline) {
   if($console.HasExited){ throw "Frontend startup failed. See .artifacts/portal-runtime/frontend.log." }
   $readyProbe = [System.Net.Sockets.TcpClient]::new()
   try {
    $readyConnection = $readyProbe.ConnectAsync('127.0.0.1', 5173)
    if($readyConnection.Wait(500) -and $readyProbe.Connected){ $frontendReady = $true; break }
   } catch {} finally { $readyProbe.Dispose() }
   Start-Sleep -Milliseconds 250
  }
  if(-not $frontendReady){ throw 'Frontend did not begin listening within 120 seconds. Inspect .artifacts/portal-runtime/frontend.log.' }
 }
 Write-Host "$serviceName owner PID: $($console.Id)"
}
Write-Host 'Logs: .artifacts/portal-runtime. Stop both with: .\scripts\Stop-Portal.ps1'
