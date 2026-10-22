param([ValidateSet('All','Backend','Frontend')][string]$Service = 'All')
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimeDir = Join-Path $workspaceRoot '.artifacts/portal-runtime'
$selectedServices = if($Service -eq 'All'){@('backend','frontend')}else{@($Service.ToLower())}
foreach($serviceName in $selectedServices){
 $ownerFile = Join-Path $runtimeDir "$serviceName.json"
 if(-not (Test-Path -LiteralPath $ownerFile)){ continue }
 $owner = Get-Content -LiteralPath $ownerFile -Raw | ConvertFrom-Json
 $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($owner.pid)" -ErrorAction SilentlyContinue
 if($process){
  $started = (Get-Process -Id $owner.pid).StartTime.ToUniversalTime()
  $recorded = if($owner.startedTicks){ [DateTime]::new([long]$owner.startedTicks, [DateTimeKind]::Utc) } elseif($owner.started -is [DateTime]){ $owner.started.ToUniversalTime() } else { [DateTimeOffset]::Parse([string]$owner.started).UtcDateTime }
  if($owner.workspace -ne $workspaceRoot -or [Math]::Abs(($started-$recorded).TotalSeconds) -gt 1 -or $process.CommandLine -notlike '*Run-PortalService.ps1*'){
   throw "Refusing to stop PID $($owner.pid): it no longer matches the recorded portal console."
  }
  taskkill.exe /PID $owner.pid /T /F 2>&1 | Out-Null
  Write-Host "Stopped $serviceName console PID $($owner.pid) and its process tree."
 }
 Remove-Item -LiteralPath $ownerFile -ErrorAction SilentlyContinue
}
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in @(5173,8080,8090) } | Select-Object LocalPort,OwningProcess | Format-Table
