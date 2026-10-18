@echo off
rem Stops the NEXUS engine running in the background.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\nexus.ps1" -Stop
timeout /t 2 >nul
