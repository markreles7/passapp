@echo off
setlocal EnableExtensions
title PassApp - Preparazione PC e creazione EXE
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
echo   Preparazione PC, aggiornamento e build EXE
echo  ============================================
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

call :create_shortcut

echo.
echo  ============================================
echo   [OK] Preparazione completata.
echo.
echo   EXE creato:
echo   %EXE_PATH%
echo.
echo   Per avviare PassApp usa:
echo   AVVIA_PASSAPP.bat
echo  ============================================
echo.
pause
exit /b 0

:find_python
set "BASE_PY="
python --version >nul 2>&1
if not errorlevel 1 set "BASE_PY=python"

if not defined BASE_PY (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "BASE_PY=py -3"
)

if defined BASE_PY (
    echo  [OK] Python trovato
    %BASE_PY% --version
    echo.
    exit /b 0
)

echo  [ERRORE] Python non trovato.
echo.
echo  Installa Python da:
echo  https://www.python.org/downloads/
echo.
echo  Durante l'installazione abilita:
echo  Add python.exe to PATH
echo.
exit /b 1

:check_git
git --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRORE] Git non trovato.
    echo.
    echo  Installa Git da:
    echo  https://git-scm.com/download/win
    echo.
    exit /b 1
)

if not exist "%SCRIPT_DIR%\.git" (
    echo  [ERRORE] Questa cartella non sembra una repository Git.
    echo  Copia o clona la repository completa di PassApp e riprova.
    echo.
    exit /b 1
)

echo  [OK] Git trovato
git --version
echo.
exit /b 0

:update_repo
for /f "usebackq delims=" %%B in (`git branch --show-current 2^>nul`) do set "BRANCH=%%B"
if not defined BRANCH set "BRANCH=main"

echo  Scaricamento aggiornamenti da GitHub...
git fetch origin
if errorlevel 1 (
    echo  [ERRORE] Impossibile contattare GitHub.
    exit /b 1
)

git status --porcelain --untracked-files=no | findstr /r "." >nul
if not errorlevel 1 (
    echo  [ERRORE] Ci sono modifiche locali ai file dell'app.
    echo  Salvale o ripristinale prima di aggiornare e ricreare l'EXE.
    exit /b 1
)

echo  Applicazione aggiornamenti su branch %BRANCH%...
git pull --ff-only origin %BRANCH%
if errorlevel 1 (
    echo  [ERRORE] Aggiornamento Git non applicato.
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
    echo  Creazione ambiente virtuale .venv...
    if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
    %BASE_PY% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  [ERRORE] Creazione ambiente virtuale fallita.
        exit /b 1
    )
) else (
    echo  [OK] Ambiente virtuale gia presente
)
echo.

echo  Aggiornamento strumenti Python...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo  [ERRORE] Aggiornamento pip/setuptools/wheel fallito.
    exit /b 1
)
echo.

echo  Installazione requirements...
"%VENV_PY%" -m pip install --upgrade -r "%SCRIPT_DIR%\requirements.txt"
if errorlevel 1 (
    echo  [ERRORE] Installazione requirements fallita.
    exit /b 1
)
echo.
exit /b 0

:verify_project
echo  Verifica import principali...
"%VENV_PY%" -c "import PySide6, openpyxl, PIL, reportlab; print('Import OK')"
if errorlevel 1 (
    echo  [ERRORE] Verifica librerie fallita.
    exit /b 1
)

echo  Verifica sintassi...
"%VENV_PY%" -m py_compile main.py main_qt.py app_config.py qt_app\app.py qt_app\main_window.py qt_app\updater.py
if errorlevel 1 exit /b 1

echo  Esecuzione test...
"%VENV_PY%" -m pytest
if errorlevel 1 (
    echo  [ERRORE] Test non superati. Build interrotta.
    exit /b 1
)
echo.
exit /b 0

:build_exe
if not exist "%SCRIPT_DIR%\data" mkdir "%SCRIPT_DIR%\data"
if not exist "%SCRIPT_DIR%\data\config.json" (
    echo {}>"%SCRIPT_DIR%\data\config.json"
)

echo  Pulizia build precedente...
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
if errorlevel 1 (
    echo  [ERRORE] Build EXE non completata.
    exit /b 1
)

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

:create_shortcut
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\PassApp.bat"
if not exist "%DESKTOP%" exit /b 0

echo  Creazione collegamento sul Desktop...
(
    echo @echo off
    echo call "%SCRIPT_DIR%\AVVIA_PASSAPP.bat"
) > "%SHORTCUT%"

if errorlevel 1 (
    echo  [AVVISO] Collegamento Desktop non creato.
) else (
    echo  [OK] Collegamento creato: %SHORTCUT%
)
echo.
exit /b 0

:errore
echo.
echo  ============================================
echo   [ERRORE] Procedura interrotta.
echo  ============================================
echo.
pause
exit /b 1
