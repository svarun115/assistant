@echo off
REM Run OAuth2 authentication flow for all Google Workspace APIs
REM Creates a single token.json with combined scopes

cd /d "%~dp0"
python src/auth.py
pause
