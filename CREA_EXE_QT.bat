@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo [1/4] Verifica dipendenze e test...
"%PYTHON%" -m py_compile main_qt.py app_config.py qt_app\app.py qt_app\main_window.py
if errorlevel 1 goto errore

"%PYTHON%" -m unittest discover -s tests
if errorlevel 1 goto errore

echo [2/4] Pulizia build Qt precedente...
if exist "build\PassAppQt" rmdir /s /q "build\PassAppQt"
if exist "dist\PassAppQt" rmdir /s /q "dist\PassAppQt"

echo [3/4] Creazione EXE Qt...
"%PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onedir ^
  --name PassAppQt ^
  --add-data "assets;assets" ^
  --add-data "data\config.json;data" ^
  main_qt.py
if errorlevel 1 goto errore

echo [4/4] Preparazione cartelle esterne...
if not exist "dist\PassAppQt\data" mkdir "dist\PassAppQt\data"
if exist "data\config.json" copy /y "data\config.json" "dist\PassAppQt\data\config.json" >nul
if not exist "dist\PassAppQt\documenti" mkdir "dist\PassAppQt\documenti"
if not exist "dist\PassAppQt\documenti\segnalazioni_pdf" mkdir "dist\PassAppQt\documenti\segnalazioni_pdf"
if not exist "dist\PassAppQt\documenti\fascicoli_segnalazioni" mkdir "dist\PassAppQt\documenti\fascicoli_segnalazioni"
if not exist "dist\PassAppQt\documenti\report_mensili" mkdir "dist\PassAppQt\documenti\report_mensili"

echo.
echo Build completata:
echo dist\PassAppQt\PassAppQt.exe
echo.
pause
exit /b 0

:errore
echo.
echo [ERRORE] Build Qt non completata.
pause
exit /b 1
