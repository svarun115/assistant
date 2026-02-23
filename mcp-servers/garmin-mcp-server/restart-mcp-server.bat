@echo off
setlocal EnableExtensions

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart-mcp-server.ps1"
if errorlevel 1 (
  echo Failed to restart Garmin MCP server.
  pause
  exit /b 1
)

exit /b 0
