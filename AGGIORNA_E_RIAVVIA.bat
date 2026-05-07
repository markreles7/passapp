@echo off
setlocal EnableExtensions
title PassApp Suite Ufficio Servizi - Aggiornamento
color 1F
cls

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
cd /d "%SCRIPT_DIR%"

echo.
echo  ============================================
echo   PASSAPP SUITE UFFICIO SERVIZI
echo   Aggiornamento da GitHub
echo  ============================================
echo.
echo  Attendo la chiusura dell'app...
timeout /t 2 /nobreak >nul
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRORE] Git non trovato. Installa Git e riprova.
    goto errore
)

for /f "usebackq delims=" %%B in (`git branch --show-current 2^>nul`) do set "BRANCH=%%B"
if not defined BRANCH set "BRANCH=main"

echo  Scaricamento informazioni da GitHub...
git fetch origin
if errorlevel 1 (
    echo  [ERRORE] Impossibile contattare GitHub.
    goto errore
)

echo  Applicazione aggiornamenti su branch %BRANCH%...
git pull --ff-only origin %BRANCH%
if errorlevel 1 (
    echo  [ERRORE] Aggiornamento non applicato.
    echo  Controlla che non ci siano modifiche locali ai file dell'app.
    goto errore
)
echo.

set "BASE_PY="
python --version >nul 2>&1
if not errorlevel 1 set "BASE_PY=python"

if not defined BASE_PY (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "BASE_PY=py -3"
)

if not defined BASE_PY (
    echo  [ERRORE] Python non trovato.
    goto errore
)

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
        goto errore
    )
)

set "PY_RUN="%VENV_PY%""

echo  Aggiornamento strumenti base Python...
%PY_RUN% -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo  [ERRORE] Aggiornamento pip/setuptools/wheel fallito.
    goto errore
)
echo.

echo  Aggiornamento dipendenze Python...
%PY_RUN% -m pip install --upgrade -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (
    echo  [ERRORE] Aggiornamento dipendenze fallito.
    goto errore
)
echo.

echo  [OK] Aggiornamento completato.
echo  Riavvio PassApp...
timeout /t 1 /nobreak >nul
start "" "%SCRIPT_DIR%Avvia App Qt.bat"
exit /b 0

:errore
echo.
echo  Aggiornamento interrotto.
echo.
pause
exit /b 1
