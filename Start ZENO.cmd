@echo off
rem Double-click to open ZENO as an app. First run installs and builds it.
title ZENO
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\nexus.ps1" %*
if errorlevel 1 pause
