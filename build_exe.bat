@echo off
setlocal

set APP_NAME=TubeCutCalculator
set APP_VERSION=v0.1.0

echo Building %APP_NAME% %APP_VERSION%

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set PYTHON_CMD=py -3.13
) else (
    set PYTHON_CMD=python
)

if not exist .venv (
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 exit /b 1
)

call .venv\Scripts\activate.bat
if errorlevel 1 exit /b 1

python -m pip install --upgrade pip
if errorlevel 1 exit /b 1

python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

powershell -NoProfile -ExecutionPolicy Bypass -Command "$date=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); Set-Content -Encoding UTF8 version.txt @('TubeCutCalculator v0.1.0','Build date: ' + $date,'Description: Interface, drag-and-drop, file queue. Geometry analysis is not implemented.')"
if errorlevel 1 exit /b 1

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onefile ^
  --name TubeCutCalculator ^
  --add-data "version.txt;." ^
  --collect-all PySide6 ^
  main.py
if errorlevel 1 exit /b 1

copy /Y version.txt dist\version.txt >nul
if errorlevel 1 exit /b 1

echo.
echo Done: dist\TubeCutCalculator.exe
echo Version file: dist\version.txt
endlocal
