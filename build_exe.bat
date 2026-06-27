@echo off
setlocal

set APP_NAME=TubeCutCalculator
set APP_VERSION=v0.5.5
set ENV_NAME=TubeCutCalculator

echo Building %APP_NAME% %APP_VERSION%

set BUILD_COMMIT=manual-build
for /f "usebackq delims=" %%i in (`git rev-parse --short^=12 HEAD 2^>nul`) do set BUILD_COMMIT=%%i

where conda >nul 2>nul
if errorlevel 1 (
    echo Conda or Miniforge is required for %APP_NAME% %APP_VERSION%.
    echo Install Miniforge, then run build_exe.bat again.
    exit /b 1
)

where mamba >nul 2>nul
if errorlevel 1 (
    set CONDA_CMD=conda
) else (
    set CONDA_CMD=mamba
)

conda env list | findstr /R /C:"^%ENV_NAME% " >nul
if errorlevel 1 (
    echo Creating conda environment %ENV_NAME%...
    call %CONDA_CMD% env create -f environment.yml
    if errorlevel 1 exit /b 1
) else (
    echo Updating conda environment %ENV_NAME%...
    call %CONDA_CMD% env update -n %ENV_NAME% -f environment.yml --prune
    if errorlevel 1 exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$date=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); @('from __future__ import annotations','','APP_BUILD_COMMIT = \"' + $env:BUILD_COMMIT + '\"','APP_BUILD_DATE = \"' + $date + '\"','CALC_CORE_REVISION = \"round-iges-fallback-v2\"') | Set-Content -Encoding UTF8 app_build.py; @('TubeCutCalculator v0.5.5','Build date: ' + $date,'Build commit: ' + $env:BUILD_COMMIT,'Calc core: round-iges-fallback-v2','Description: Verifies packaged build identity and improves round IGES diagnostics.') | Set-Content -Encoding UTF8 version.txt"
if errorlevel 1 exit /b 1

echo Generated build identity:
type app_build.py

call %CONDA_CMD% run -n %ENV_NAME% python -c "from app_info import APP_BUILD_COMMIT, CALC_CORE_REVISION; print('Build identity:', APP_BUILD_COMMIT, CALC_CORE_REVISION); raise SystemExit(1 if APP_BUILD_COMMIT in ('', 'local', 'unknown') else 0)"
if errorlevel 1 exit /b 1

call %CONDA_CMD% run -n %ENV_NAME% python -m PyInstaller --noconfirm --clean TubeCutCalculator.spec
if errorlevel 1 exit /b 1

if not exist dist (
    echo Build output directory was not created.
    exit /b 1
)

if not exist dist\TubeCutCalculator.exe (
    if exist dist\TubeCutCalculator\TubeCutCalculator.exe (
        copy /Y dist\TubeCutCalculator\TubeCutCalculator.exe dist\TubeCutCalculator.exe >nul
        if errorlevel 1 exit /b 1
    )
)

if not exist dist\TubeCutCalculator.exe (
    echo EXE was not found in dist.
    dir /S dist
    exit /b 1
)

copy /Y version.txt dist\version.txt >nul
if errorlevel 1 exit /b 1

echo.
echo Build output:
dir /S dist

echo.
echo Done: dist\TubeCutCalculator.exe
echo Version file: dist\version.txt
endlocal
