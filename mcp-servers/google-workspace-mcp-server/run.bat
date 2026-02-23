@echo off
REM Google Workspace MCP Server launcher
REM
REM Usage:
REM   run.bat              - stdio mode (default, for Claude Code)
REM   run.bat --http       - HTTP mode on port 3000
REM   run.bat --http 3001  - HTTP mode on custom port

cd /d "%~dp0"

if "%1"=="--http" (
    if "%2"=="" (
        python src/server.py --http
    ) else (
        python src/server.py --http --port %2
    )
) else (
    python src/server.py
)
