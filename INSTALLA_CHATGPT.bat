@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALLA_CHATGPT.ps1"
if errorlevel 1 (
    echo.
    echo Aggiornamento non completato. Leggi il messaggio sopra.
    pause
    exit /b 1
)
