$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$serverName = 'splitwise'
$windowTitle = 'MCP - Splitwise'
$pidFile = Join-Path $scriptDir ".mcp_$serverName.pid"
$commandLineRegex = 'splitwise-mcp-server|dist\\index\.js|src\\index\.ts'
$port = 2222
$startCmd = "npm run build & title $windowTitle & node dist\\index.js --http --port $port"

function StopProcessesOnPort([int]$p) {
  $pids = @()

  # Preferred: Get-NetTCPConnection (available on most Windows installs)
  try {
    $pids = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction Stop |
      Select-Object -ExpandProperty OwningProcess -Unique
  } catch {
    # Fallback: netstat parsing
    $lines = netstat -ano -p tcp | Select-String ":$p\s"
    foreach ($line in $lines) {
      $tokens = ($line.ToString() -split '\s+') | Where-Object { $_ }
      if ($tokens.Count -gt 0) {
        $pidToken = $tokens[-1]
        if ($pidToken -match '^\d+$') { $pids += [int]$pidToken }
      }
    }
    $pids = $pids | Select-Object -Unique
  }

  foreach ($pid in $pids) {
    if ($pid -and $pid -ne 0 -and $pid -ne $PID) {
      try {
        Write-Host "Stopping process on port $p (PID $pid)..."
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
      } catch { }
    }
  }
}

Write-Host "Restarting $serverName MCP server..."
Write-Host "Working dir: $scriptDir"
Write-Host "HTTP endpoint: http://127.0.0.1:$port/mcp"

# Make sure the port is free (handles cases where the old Node process survived)
StopProcessesOnPort -p $port

if (Test-Path $pidFile) {
  $oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($oldPid) {
    Write-Host "Stopping previous instance (PID $oldPid)..."
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
  }
  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -and
    $_.CommandLine -match $commandLineRegex -and
    $_.ProcessId -ne $PID -and
    $_.CommandLine -notmatch 'restart-mcp-server\.ps1'
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Starting new instance..."
$p = Start-Process -FilePath 'cmd.exe' -WorkingDirectory $scriptDir -ArgumentList @('/k', "`"$startCmd`"") -PassThru
Set-Content -Path $pidFile -Value $p.Id -Encoding ascii
Write-Host "Started PID $($p.Id)"