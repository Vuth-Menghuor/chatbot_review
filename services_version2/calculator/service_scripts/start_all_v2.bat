@echo off
REM Batch file wrapper to run start_all_v2.ps1 with execution policy bypass
REM This allows running the PowerShell script without digitally signing it

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -NoProfile -File "start_all_v2.ps1" %*
pause
