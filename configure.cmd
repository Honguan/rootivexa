@echo off
cd /d "%~dp0"
start /wait "" notepad.exe "%~dp0settings.json"
echo Save settings.json, then run install.cmd to apply changes.
if not defined CODEX_ORCHESTRATION_NO_PAUSE pause
