@echo off
rem Double-click to open NEXUS as an app. First run installs and builds it.
title NEXUS
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\nexus.ps1" %*
if errorlevel 1 pause
