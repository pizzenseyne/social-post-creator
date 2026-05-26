@echo off
title Social Post Creator
cd /d "%~dp0"

echo Suppression ancien environnement...
if exist "venv" rmdir /s /q venv

echo Creation environnement virtuel...
py -m venv venv

echo Installation des dependances...
venv\Scripts\pip install fastapi "uvicorn[standard]" anthropic python-dotenv python-multipart httpx "pillow>=11.0.0" --quiet

echo.
echo ============================================
echo   SOCIAL POST CREATOR - PRET !
echo ============================================
echo.
echo Sur ce PC, ouvrez :
echo   http://localhost:8000
echo.
echo Sur votre telephone Android (meme WiFi) :
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "169.254"') do (
    for /f "tokens=1" %%b in ("%%a") do (
        echo   http://%%b:8000
    )
)
echo.
echo Dans Chrome sur Android : menu (3 points) ^> "Ajouter a l'ecran d'accueil"
echo ============================================
echo.

start "" http://localhost:8000
venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
