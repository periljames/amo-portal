param(
  [Parameter(Mandatory=$true)][ValidateSet('Backend','Frontend')][string]$Service,
  [ValidateSet('Dev','Shared')][string]$FrontendMode = 'Dev'
)
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $workspaceRoot
$runtimeDir = Join-Path $workspaceRoot '.artifacts/portal-runtime'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
Start-Transcript -Path (Join-Path $runtimeDir "$($Service.ToLower()).log") -Append | Out-Null
$Host.UI.RawUI.WindowTitle = "AMO Portal $Service - $(if($Service -eq 'Backend'){'8080 / 8090'}else{'5173 / '+$FrontendMode})"
# The job releases all descendants when this visible console closes.
Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
public static class PortalConsoleLifetime {
 [StructLayout(LayoutKind.Sequential)] struct Basic { public long a,b; public uint flags; public UIntPtr min,max; public uint count; public UIntPtr affinity; public uint priority,scheduling; }
 [StructLayout(LayoutKind.Sequential)] struct Io { public ulong a,b,c,d,e,f; }
 [StructLayout(LayoutKind.Sequential)] struct Limits { public Basic basic; public Io io; public UIntPtr process,job,peakProcess,peakJob; }
 [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr attributes,string name);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int type,ref Limits info,uint size);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
 static IntPtr handle;
 public static void OwnConsole() {
  handle=CreateJobObject(IntPtr.Zero,null);
  var limits=new Limits(); limits.basic.flags=0x2000;
  if(handle==IntPtr.Zero || !SetInformationJobObject(handle,9,ref limits,(uint)Marshal.SizeOf(typeof(Limits))) || !AssignProcessToJobObject(handle,Process.GetCurrentProcess().Handle))
   throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
 }
}
'@
[PortalConsoleLifetime]::OwnConsole()
$runtimeDir = Join-Path $workspaceRoot '.artifacts/portal-runtime'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$ownerFile = Join-Path $runtimeDir "$($Service.ToLower()).json"
@{pid=$PID; startedTicks=(Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks; workspace=$workspaceRoot; service=$Service} | ConvertTo-Json | Set-Content -LiteralPath $ownerFile -Encoding utf8
Write-Host "AMO Portal $Service is owned by this visible window (PID $PID)." -ForegroundColor Cyan
Write-Host 'Ctrl+C stops the foreground service. Closing this window stops all its children.'
Write-Host "Stop both: & '$PSScriptRoot\Stop-Portal.ps1'"
try {
 if($Service -eq 'Backend') {
  & (Join-Path $workspaceRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'dev_runtime.py') --env-file .env.development --no-frontend --no-reload 2>&1 | Tee-Object -FilePath (Join-Path $runtimeDir 'backend-service.log')
 } else {
  Set-Location -LiteralPath (Join-Path $workspaceRoot 'frontend')
  if($FrontendMode -eq 'Shared') {
   if(-not (Test-Path -LiteralPath 'dist/index.html')){ throw 'No built frontend. Run npm --prefix frontend run build first, then start Shared mode.' }
   # Serve an immutable release copy: Vite empties dist while building.
   $releasesRoot = Join-Path $runtimeDir 'frontend-releases'
   New-Item -ItemType Directory -Path $releasesRoot -Force | Out-Null
   $previousRelease = Get-ChildItem -LiteralPath $releasesRoot -Directory | Where-Object { $_.Name -match '^release-[0-9]+$' } | Sort-Object Name -Descending | Select-Object -First 1
   $releaseRoot = Join-Path $releasesRoot ("release-" + [DateTime]::UtcNow.Ticks)
   New-Item -ItemType Directory -Path $releaseRoot | Out-Null
   Get-ChildItem -LiteralPath 'dist' -Force | Copy-Item -Destination $releaseRoot -Recurse -Force
   # Old tabs may still request immutable chunks from the previous release.
   if($previousRelease -and (Test-Path -LiteralPath (Join-Path $previousRelease.FullName 'assets'))) {
    Get-ChildItem -LiteralPath (Join-Path $previousRelease.FullName 'assets') -Force | Copy-Item -Destination (Join-Path $releaseRoot 'assets') -Recurse -Force
   }
   @{pid=$PID; startedTicks=(Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks; workspace=$workspaceRoot; service=$Service; release=$releaseRoot} | ConvertTo-Json | Set-Content -LiteralPath $ownerFile -Encoding utf8
   Write-Host "Serving verified release: $releaseRoot" -ForegroundColor Cyan
   Write-Host 'Rebuild dist and restart this frontend to publish source changes.'
   & npm.cmd run preview -- --host 0.0.0.0 --port 5173 --strictPort --outDir $releaseRoot
  } else { & npm.cmd run dev -- --host 0.0.0.0 --port 5173 --strictPort }
 }
} finally {
 if(Test-Path -LiteralPath $ownerFile){ Remove-Item -LiteralPath $ownerFile }
 Write-Host 'Foreground command stopped. Close this window to release every remaining child.' -ForegroundColor Yellow
}
