@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Build Windows EXE (GUI)
REM Usage: double-click this file, or run in CMD

pushd "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.10+ and check "Add Python to PATH".
  goto :build_error
)

for /f "usebackq delims=" %%V in (`python -c "from modules.config import VERSION; print(VERSION)" 2^>nul`) do set "APP_VERSION=%%V"
if not defined APP_VERSION (
  echo [WARN] Failed to read version from modules/config.py. Fallback to "unknown".
  set "APP_VERSION=unknown"
)

set "APP_NAME=FF14DCT_GUI_v!APP_VERSION!"

echo [1/4] Installing dependencies...
python -m pip install -U pip
if errorlevel 1 goto :build_error
python -m pip install -r requirements.txt
if errorlevel 1 goto :build_error
python -m pip install -U pyinstaller
if errorlevel 1 goto :build_error

echo [2/4] Cleaning old build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist FF14DCT_GUI.spec del /q FF14DCT_GUI.spec
if exist "!APP_NAME!.spec" del /q "!APP_NAME!.spec"

echo [3/4] Building EXE...
python -m PyInstaller --noconfirm --clean --name "!APP_NAME!" --onefile --windowed gui_main.py
if errorlevel 1 goto :build_error

if not exist "dist\!APP_NAME!.exe" (
  echo [ERROR] Build finished but EXE not found: dist\!APP_NAME!.exe
  goto :build_error
)

echo [4/4] Done.
echo Version: !APP_VERSION!
echo Output: dist\!APP_NAME!.exe
popd
pause
exit /b 0

:build_error
echo [ERROR] Build failed.
popd
pause
exit /b 1
