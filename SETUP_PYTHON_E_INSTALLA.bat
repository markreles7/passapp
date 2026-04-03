@echo off
title PassApp Suite Ufficio Servizi - Setup Python
color 1F
cls

echo.
echo  ============================================
echo   PASSAPP SUITE UFFICIO SERVIZI
echo   Verifica e installazione Python
echo  ============================================
echo.

echo  [1/3] Controllo Python in corso...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
    echo.
    echo  [OK] Python e' gia' installato: %PYVER%
    echo.
    goto :installa_app
)

py --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('py --version 2^>^&1') do set PYVER=%%v
    echo.
    echo  [OK] Python e' gia' installato: %PYVER%
    echo.
    goto :installa_app
)

echo  [!] Python non trovato sul PC.
echo.
echo  [2/3] Download Python 3.12 in corso...
echo        Attendere qualche secondo.
echo.

set INSTALLER=%TEMP%\python_installer.exe
set URL=https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe

powershell -Command "try { (New-Object Net.WebClient).DownloadFile('%URL%', '%INSTALLER%'); Write-Host 'Download completato.' } catch { Write-Host ('ERRORE: ' + $_.Exception.Message); exit 1 }"

if %errorlevel% neq 0 (
    echo.
    echo  [ERRORE] Impossibile scaricare Python.
    echo  Scaricalo manualmente da:
    echo  https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo.
echo  [OK] Download completato.
echo.
echo  [3/3] Avvio installazione Python...
echo.
echo  IMPORTANTE:
echo  Nella schermata che si apre, abilita "Add Python to PATH"
echo  e poi clicca "Install Now".
echo.
pause

start /wait "" "%INSTALLER%"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo  [ATTENZIONE] Python non sembra ancora disponibile.
        echo  Riapri il prompt e riesegui INSTALLA.bat.
        echo.
        pause
        exit /b 1
    )
)

echo.
echo  [OK] Python installato correttamente.
echo.

del "%INSTALLER%" >nul 2>&1

:installa_app
echo  ============================================
echo   Installazione suite in corso...
echo  ============================================
echo.

call "%~dp0INSTALLA.bat"
