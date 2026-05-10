@echo off
echo ========================================
echo    Building Stealth Clipboard Monitor
echo ========================================

pip install pyinstaller cryptography pyperclip --quiet

pyinstaller --onefile --noconsole ^
  --hidden-import=cryptography ^
  --hidden-import=pyperclip ^
  --add-data "config.json;." ^
  --name "clipboard_monitor" ^
  --icon NONE ^
  clipboard_monitor.py

echo.
echo Build finished! EXE is in dist\clipboard_monitor.exe
echo.
pause
