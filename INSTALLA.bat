@echo off
setlocal EnableExtensions
title PassApp Suite Ufficio Servizi - Installazione Qt
color 1F
cls

echo.
echo  ============================================
echo   PASSAPP SUITE UFFICIO SERVIZI
echo   Procedura guidata installazione Qt
echo  ============================================
echo.
echo  Questa procedura installa tutti i requisiti
echo  per usare la nuova versione Qt dell'app.
echo.
echo  Nota:
echo  - I percorsi delle cartelle si impostano
echo    dalla pagina Configurazione dell'app.
echo  - Per gli aggiornamenti automatici serve Git.
echo.
pause
echo.

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "PY_CMD="

python --version >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"

if not defined PY_CMD (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    echo  [ERRORE] Python non trovato sul PC.
    echo.
    echo  Installa Python da:
    echo  https://www.python.org/downloads/
    echo.
    echo  Durante l'installazione seleziona:
    echo  Add python.exe to PATH
    echo.
    pause
    exit /b 1
)

echo  [OK] Python trovato
%PY_CMD% --version
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo  [AVVISO] Git non trovato.
    echo.
    echo  L'app potra funzionare, ma gli aggiornamenti
    echo  automatici da GitHub non saranno disponibili.
    echo.
    echo  Installa Git da:
    echo  https://git-scm.com/download/win
    echo.
    choice /C SN /M "Vuoi continuare comunque senza Git"
    if errorlevel 2 exit /b 1
) else (
    echo  [OK] Git trovato
    git --version
)
echo.

if exist "%VENV_PY%" (
    "%VENV_PY%" --version >nul 2>&1
    if errorlevel 1 (
        echo  [AVVISO] Ambiente .venv presente ma non valido.
        choice /C SN /M "Vuoi ricreare l'ambiente .venv"
        if errorlevel 2 exit /b 1
        rmdir /s /q "%VENV_DIR%"
    ) else (
        echo  [OK] Ambiente virtuale gia presente
    )
)

if not exist "%VENV_PY%" (
    echo  Creazione ambiente virtuale .venv...
    %PY_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  [ERRORE] Creazione ambiente virtuale fallita.
        pause
        exit /b 1
    )
)
echo.

echo  Aggiornamento strumenti base Python...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo  [ERRORE] Aggiornamento pip/setuptools/wheel fallito.
    pause
    exit /b 1
)
echo.

echo  Installazione requisiti Qt e librerie applicative...
"%VENV_PY%" -m pip install --upgrade -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (
    echo  [ERRORE] Installazione requisiti fallita.
    pause
    exit /b 1
)
echo.

echo  Verifica import librerie principali...
"%VENV_PY%" -c "import PySide6, qtawesome, openpyxl, PIL; print('PySide6 OK')"
if errorlevel 1 (
    echo  [ERRORE] Verifica Qt fallita.
    pause
    exit /b 1
)
echo.

set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\PassApp Suite Ufficio Servizi Qt.bat"

echo  Creazione collegamento sul Desktop...
(
    echo @echo off
    echo cd /d "%SCRIPT_DIR%"
    echo call "%SCRIPT_DIR%Avvia App Qt.bat"
) > "%SHORTCUT%"
if errorlevel 1 (
    echo  [AVVISO] Non e stato possibile creare il collegamento sul Desktop.
) else (
    echo  [OK] Collegamento creato:
    echo       %SHORTCUT%
)
echo.

echo  ============================================
echo   Installazione completata.
echo.
echo   Avvia l'app dal collegamento sul Desktop
echo   oppure da Avvia App Qt.bat.
echo.
echo   I percorsi delle cartelle si impostano da:
echo   Configurazione ^> Salva configurazione
echo  ============================================
echo.
pause
exit /b 0
