@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
    exit /b %errorlevel%
)

python -c "import PySide6" >nul 2>&1
if %errorlevel% equ 0 (
    python main.py
    exit /b %errorlevel%
)

py -3 -c "import PySide6" >nul 2>&1
if %errorlevel% equ 0 (
    py -3 main.py
    exit /b %errorlevel%
)

echo [ERRORE] PySide6 non trovato.
echo Usa l'ambiente virtuale del progetto oppure installa le dipendenze da requirements.txt.
pause
exit /b 1
