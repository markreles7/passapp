@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "EXE_PATH=%SCRIPT_DIR%\dist\PassAppQt\PassAppQt.exe"

if exist "%EXE_PATH%" (
    start "" "%EXE_PATH%"
    exit /b 0
)

echo.
echo  EXE non trovato.
echo  Avvio la preparazione del PC e la creazione dell'EXE.
echo.
call "%SCRIPT_DIR%\PREPARA_PC_E_CREA_EXE.bat"
if errorlevel 1 exit /b 1

if exist "%EXE_PATH%" (
    start "" "%EXE_PATH%"
    exit /b 0
)

echo.
echo  [ERRORE] EXE ancora non trovato: %EXE_PATH%
pause
exit /b 1
