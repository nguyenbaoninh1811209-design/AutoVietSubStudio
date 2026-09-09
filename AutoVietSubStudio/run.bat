@echo off
setlocal
cd /d %~dp0
py -m app.main
if errorlevel 1 pause
