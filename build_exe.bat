@echo off
setlocal

set APP_NAME=TubeCutCalculator
set APP_VERSION=v0.2.0
set ENV_NAME=TubeCutCalculator

echo Building %APP_NAME% %APP_VERSION%

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
    %CONDA_CMD% env create -f environment.yml
    if errorlevel 1 exit /b 1
) else (
    echo Updating conda environment %ENV_NAME%...
    %CONDA_CMD% env update -n %ENV_NAME% -f environment.yml --prune
    if errorlevel 1 exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$date=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); Set-Content -Encoding UTF8 version.txt @('TubeCutCalculator v0.2.0','Build date: ' + $date,'Description: STEP/IGES import, 3D viewer, drag-and-drop, file queue. Geometry analysis is not implemented.')"
if errorlevel 1 exit /b 1

conda run -n %ENV_NAME% python -m PyInstaller --noconfirm --clean TubeCutCalculator.spec
if errorlevel 1 exit /b 1

copy /Y version.txt dist\version.txt >nul
if errorlevel 1 exit /b 1

echo.
echo Done: dist\TubeCutCalculator.exe
echo Version file: dist\version.txt
endlocal
