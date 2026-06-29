@echo off
:: Ce fichier lance l'app en arriere-plan au demarrage de Windows
:: Pour l'activer : Win+R -> shell:startup -> copier ce fichier ici

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    py -m venv venv
    venv\Scripts\pip install fastapi "uvicorn[standard]" python-dotenv httpx --quiet
)

start /min "" venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000
timeout /t 3 /nobreak >nul
start "" http://localhost:8000
