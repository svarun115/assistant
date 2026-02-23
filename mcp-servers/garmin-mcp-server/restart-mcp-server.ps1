$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$serverName = 'garmin'
$windowTitle = 'MCP - Garmin'
$pidFile = Join-Path $scriptDir ".mcp_$serverName.pid"
$commandLineRegex = 'garmin_mcp'
$startCmd = "title $windowTitle & python -m garmin_mcp --http --port 5555"

function TryLoadEnvFromDotenv([string]$filePath) {
  if (-not (Test-Path $filePath)) { return }
  Get-Content $filePath | ForEach-Object {
    $line = $_.Trim()
    if (-not $line) { return }
    if ($line.StartsWith('#')) { return }
    if ($line -notmatch '^[A-Za-z_][A-Za-z0-9_]*=') { return }
    $parts = $line.Split('=', 2)
    $key = $parts[0].Trim()
    $val = $parts[1].Trim()
    if ($val.StartsWith('"') -and $val.EndsWith('"')) { $val = $val.Substring(1, $val.Length - 2) }
    if ($val.StartsWith("'") -and $val.EndsWith("'")) { $val = $val.Substring(1, $val.Length - 2) }
    $existing = [System.Environment]::GetEnvironmentVariable($key, 'Process')
    if (-not $existing) { [System.Environment]::SetEnvironmentVariable($key, $val, 'Process') }
  }
}

Write-Host "Restarting $serverName MCP server..."
Write-Host "Working dir: $scriptDir"
Write-Host "HTTP endpoint: http://127.0.0.1:5555/mcp"

# Load credentials from .env files if not already set
if (-not $env:GARMIN_EMAIL -or -not $env:GARMIN_PASSWORD) {
  TryLoadEnvFromDotenv (Join-Path $scriptDir '.env')
  TryLoadEnvFromDotenv (Join-Path $scriptDir '.env.local')
  TryLoadEnvFromDotenv (Join-Path $scriptDir '.env.development')
}

if (-not $env:GARMIN_EMAIL -or -not $env:GARMIN_PASSWORD) {
  Write-Error "GARMIN_EMAIL and GARMIN_PASSWORD environment variables are required. Set them in Windows environment variables, or create garmin-mcp-server\\.env with GARMIN_EMAIL=... and GARMIN_PASSWORD=..."
  exit 1
}

if (Test-Path $pidFile) {
  $oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($oldPid) {
    Write-Host "Stopping previous instance (PID $oldPid)..."
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
  }
  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match $commandLineRegex } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Starting new instance..."
# Pass credentials to cmd.exe as environment variables
$envVars = @{
  'GARMIN_EMAIL' = $env:GARMIN_EMAIL
  'GARMIN_PASSWORD' = $env:GARMIN_PASSWORD
}
$envStr = ($envVars.GetEnumerator() | ForEach-Object { "set $($_.Key)=$($_.Value) & " }) -join ''
$fullCmd = $envStr + $startCmd
$p = Start-Process -FilePath 'cmd.exe' -WorkingDirectory $scriptDir -ArgumentList @('/k', "`"$fullCmd`"") -PassThru
Set-Content -Path $pidFile -Value $p.Id -Encoding ascii
Write-Host "Started PID $($p.Id)"