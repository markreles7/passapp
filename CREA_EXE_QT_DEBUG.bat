@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo [1/3] Pulizia build debug Qt precedente...
if exist "build\PassAppQtDebug" rmdir /s /q "build\PassAppQtDebug"
if exist "dist\PassAppQtDebug" rmdir /s /q "dist\PassAppQtDebug"

echo [2/3] Creazione EXE Qt con console debug...
"%PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --name PassAppQtDebug ^
  --add-data "assets;assets" ^
  --add-data "data\config.json;data" ^
  main_qt.py
if errorlevel 1 goto errore

echo [3/3] Preparazione configurazione esterna...
if not exist "dist\PassAppQtDebug\data" mkdir "dist\PassAppQtDebug\data"
if exist "data\config.json" copy /y "data\config.json" "dist\PassAppQtDebug\data\config.json" >nul

echo.
echo Build debug completata:
echo dist\PassAppQtDebug\PassAppQtDebug.exe
echo.
"dist\PassAppQtDebug\PassAppQtDebug.exe"
pause
exit /b 0

:errore
echo.
echo [ERRORE] Build debug Qt non completata.
pause
exit /b 1
