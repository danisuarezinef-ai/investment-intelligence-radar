@echo off
set "APP=%~dp0"
set "DATABASE_URL=sqlite:///%APP:\=/%radar.db"
start "" "%APP%runtime\pythonw.exe" "%APP%radar_desktop.py"
