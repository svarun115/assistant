$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$serverName = 'googleplaces'
$windowTitle = 'MCP - Google Places'
$pidFile = Join-Path $scriptDir ".mcp_$serverName.pid"
$commandLineRegex = 'googleplaces-mcp-server|dist\\index\.js|src\\index\.ts'
$port = 1111
$startCmd = "npm run build & title $windowTitle & node dist\\index.js --http --port $port"

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
Write-Host "HTTP endpoint: http://127.0.0.1:1111/mcp"

if (-not $env:GOOGLE_PLACES_API_KEY) {
  TryLoadEnvFromDotenv (Join-Path $scriptDir '.env')
  TryLoadEnvFromDotenv (Join-Path $scriptDir '.env.local')
  TryLoadEnvFromDotenv (Join-Path $scriptDir '.env.development')
}

if (-not $env:GOOGLE_PLACES_API_KEY) {
  Write-Error "GOOGLE_PLACES_API_KEY environment variable is required. Set it in Windows environment variables, or create googleplaces-mcp-server\\.env with GOOGLE_PLACES_API_KEY=..."
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