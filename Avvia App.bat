@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
    exit /b %errorlevel%
)

python --version >nul 2>&1
if %errorlevel% equ 0 (
    python main.py
    exit /b %errorlevel%
)

py -3 --version >nul 2>&1
if %errorlevel% equ 0 (
    py -3 main.py
    exit /b %errorlevel%
)

echo [ERRORE] Python non trovato.
echo Esegui SETUP_PYTHON_E_INSTALLA.bat e riprova.
pause
exit /b 1
