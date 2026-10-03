@echo off
cd /d "%~dp0"
py -3 manage.py install %*
set "result=%errorlevel%"
if not defined CODEX_ORCHESTRATION_NO_PAUSE pause
exit /b %result%
