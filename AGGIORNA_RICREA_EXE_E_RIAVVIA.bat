@echo off
setlocal EnableExtensions
title PassApp - Aggiornamento, rebuild EXE e riavvio
color 1F
cls

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "VENV_DIR=%SCRIPT_DIR%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "EXE_PATH=%SCRIPT_DIR%\dist\PassAppQt\PassAppQt.exe"
cd /d "%SCRIPT_DIR%"

echo.
echo  ============================================
echo   PASSAPP
echo   Aggiornamento, creazione EXE e riavvio
echo  ============================================
echo.
echo  Attendo la chiusura dell'app...
timeout /t 3 /nobreak >nul
echo.

call :find_python
if errorlevel 1 goto errore

call :check_git
if errorlevel 1 goto errore

call :update_repo
if errorlevel 1 goto errore

call :prepare_venv
if errorlevel 1 goto errore

call :verify_project
if errorlevel 1 goto errore

call :build_exe
if errorlevel 1 goto errore

echo  [OK] Aggiornamento completato.
echo  Riavvio PassApp...
timeout /t 1 /nobreak >nul
start "" "%EXE_PATH%"
exit /b 0

:find_python
set "BASE_PY="
python --version >nul 2>&1
if not errorlevel 1 set "BASE_PY=python"

if not defined BASE_PY (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "BASE_PY=py -3"
)

if not defined BASE_PY (
    echo  [ERRORE] Python non trovato.
    echo  Esegui PREPARA_PC_E_CREA_EXE.bat dopo aver installato Python.
    exit /b 1
)

echo  [OK] Python trovato
%BASE_PY% --version
echo.
exit /b 0

:check_git
git --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRORE] Git non trovato.
    echo  Installa Git e riprova.
    exit /b 1
)

if not exist "%SCRIPT_DIR%\.git" (
    echo  [ERRORE] Repository Git non trovata: %SCRIPT_DIR%\.git
    exit /b 1
)

echo  [OK] Git trovato
git --version
echo.
exit /b 0

:update_repo
for /f "usebackq delims=" %%B in (`git branch --show-current 2^>nul`) do set "BRANCH=%%B"
if not defined BRANCH set "BRANCH=main"

echo  Scaricamento informazioni da GitHub...
git fetch origin
if errorlevel 1 (
    echo  [ERRORE] Impossibile contattare GitHub.
    exit /b 1
)

git status --porcelain --untracked-files=no | findstr /r "." >nul
if not errorlevel 1 (
    echo  [ERRORE] Ci sono modifiche locali ai file dell'app.
    echo  Salvale su GitHub o ripristinale prima di aggiornare automaticamente.
    exit /b 1
)

echo  Applicazione aggiornamenti su branch %BRANCH%...
git pull --ff-only origin %BRANCH%
if errorlevel 1 (
    echo  [ERRORE] Aggiornamento non applicato.
    exit /b 1
)
echo.
exit /b 0

:prepare_venv
set "RECREATE_VENV="
if not exist "%VENV_PY%" set "RECREATE_VENV=1"
if not defined RECREATE_VENV (
    "%VENV_PY%" --version >nul 2>&1
    if errorlevel 1 set "RECREATE_VENV=1"
)

if defined RECREATE_VENV (
    echo  Ambiente .venv non presente o non valido. Ricreo ambiente...
    if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
    %BASE_PY% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  [ERRORE] Creazione ambiente .venv fallita.
        exit /b 1
    )
)

echo  Aggiornamento strumenti base Python...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 exit /b 1

echo  Aggiornamento dipendenze Python...
"%VENV_PY%" -m pip install --upgrade -r "%SCRIPT_DIR%\requirements.txt"
if errorlevel 1 exit /b 1
echo.
exit /b 0

:verify_project
echo  Verifica sintassi e test...
"%VENV_PY%" -m py_compile main.py main_qt.py app_config.py qt_app\app.py qt_app\main_window.py qt_app\updater.py
if errorlevel 1 exit /b 1

"%VENV_PY%" -m pytest
if errorlevel 1 (
    echo  [ERRORE] Test non superati. Aggiornamento interrotto.
    exit /b 1
)
echo.
exit /b 0

:build_exe
if not exist "%SCRIPT_DIR%\data" mkdir "%SCRIPT_DIR%\data"
if not exist "%SCRIPT_DIR%\data\config.json" (
    echo {}>"%SCRIPT_DIR%\data\config.json"
)

echo  Pulizia build Qt precedente...
if exist "%SCRIPT_DIR%\build\PassAppQt" rmdir /s /q "%SCRIPT_DIR%\build\PassAppQt"
if exist "%SCRIPT_DIR%\dist\PassAppQt" rmdir /s /q "%SCRIPT_DIR%\dist\PassAppQt"

echo  Creazione EXE Qt...
"%VENV_PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onedir ^
  --name PassAppQt ^
  --add-data "assets;assets" ^
  --add-data "templates;templates" ^
  --add-data "data\config.json;data" ^
  main.py
if errorlevel 1 exit /b 1

echo  Preparazione cartelle esterne...
if not exist "%SCRIPT_DIR%\dist\PassAppQt\data" mkdir "%SCRIPT_DIR%\dist\PassAppQt\data"
copy /y "%SCRIPT_DIR%\data\config.json" "%SCRIPT_DIR%\dist\PassAppQt\data\config.json" >nul
if exist "%SCRIPT_DIR%\templates" xcopy /e /i /y "%SCRIPT_DIR%\templates" "%SCRIPT_DIR%\dist\PassAppQt\templates" >nul
if not exist "%SCRIPT_DIR%\dist\PassAppQt\documenti" mkdir "%SCRIPT_DIR%\dist\PassAppQt\documenti"
if not exist "%SCRIPT_DIR%\dist\PassAppQt\documenti\segnalazioni_pdf" mkdir "%SCRIPT_DIR%\dist\PassAppQt\documenti\segnalazioni_pdf"
if not exist "%SCRIPT_DIR%\dist\PassAppQt\documenti\fascicoli_segnalazioni" mkdir "%SCRIPT_DIR%\dist\PassAppQt\documenti\fascicoli_segnalazioni"
if not exist "%SCRIPT_DIR%\dist\PassAppQt\documenti\report_mensili" mkdir "%SCRIPT_DIR%\dist\PassAppQt\documenti\report_mensili"
echo.
exit /b 0

:errore
echo.
echo  Aggiornamento interrotto.
echo.
pause
exit /b 1
