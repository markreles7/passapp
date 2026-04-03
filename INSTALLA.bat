@echo off
title PassApp Suite Ufficio Servizi - Installazione
color 1F
cls

echo.
echo  ============================================
echo   PASSAPP SUITE UFFICIO SERVIZI
echo   Installazione
echo  ============================================
echo.

set "PY_CMD="
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=python"
) else (
    py -3 --version >nul 2>&1
    if %errorlevel% equ 0 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    echo  [ERRORE] Python non trovato sul PC.
    echo.
    echo  Esegui prima SETUP_PYTHON_E_INSTALLA.bat
    echo  oppure installa Python da:
    echo  https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo  [OK] Python trovato
echo.
echo  Installazione librerie necessarie...
echo.

%PY_CMD% -m pip install openpyxl pillow xlrd --quiet --upgrade
if %errorlevel% neq 0 (
    echo  [ERRORE] Installazione librerie fallita.
    pause
    exit /b 1
)

echo  [OK] Librerie installate
echo.

set SCRIPT_DIR=%~dp0
set DESKTOP=%USERPROFILE%\Desktop
set SHORTCUT=%DESKTOP%\PassApp Suite Ufficio Servizi.bat

echo @echo off > "%SHORTCUT%"
echo cd /d "%SCRIPT_DIR%" >> "%SHORTCUT%"
echo %PY_CMD% "%SCRIPT_DIR%main.py" >> "%SHORTCUT%"

echo  [OK] Collegamento creato sul Desktop
echo.
echo  ============================================
echo   Installazione completata.
echo   Usa il collegamento sul Desktop oppure
echo   Avvia App.bat per aprire la suite.
echo  ============================================
echo.
pause
