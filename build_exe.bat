@echo off
cd /d "%~dp0"

echo ========================================
echo    Building Clipboard Monitor
echo ========================================

python -m pip install --upgrade pip pyinstaller cryptography pyperclip --quiet

python -m PyInstaller --onefile --windowed ^
  --hidden-import=cryptography ^
  --hidden-import=cryptography.fernet ^
  --hidden-import=pyperclip ^
  --add-data "config.json;." ^
  --name "clipboard_monitor" ^
  --icon NONE ^
  clipboard_monitor.py

echo.
echo Build finished! EXE is in dist\clipboard_monitor.exe
echo.
pause
