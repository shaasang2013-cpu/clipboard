@echo off
cd /d "%~dp0"

echo Building Clipboard Monitor...
python -m pip install --upgrade pip pyinstaller cryptography pyperclip

python -m PyInstaller --onefile --windowed --name clipboard_monitor clipboard_monitor.py

echo Build complete! Check dist\ folder
pause
