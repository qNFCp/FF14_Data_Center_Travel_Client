@echo off
setlocal

REM Build Windows EXE (GUI)
REM Usage: double-click this file, or run in CMD

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.10+ and check "Add Python to PATH".
  pause
  exit /b 1
)

echo [1/4] Installing dependencies...
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -U pyinstaller

echo [2/4] Cleaning old build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist FF14DCT_GUI.spec del /q FF14DCT_GUI.spec

echo [3/4] Building EXE...
python -m PyInstaller --noconfirm --clean --name FF14DCT_GUI --onefile --windowed gui_main.py

echo [4/4] Done.
echo Output: dist\FF14DCT_GUI.exe
pause
