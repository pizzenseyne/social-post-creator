@echo off
title Pizz'en Seyne - Food Cost
cd /d "%~dp0"

:: Création du venv si absent
if not exist "venv\Scripts\python.exe" (
    echo Creation de l'environnement...
    py -m venv venv
)

:: Mise a jour des dependances a chaque lancement (rapide si deja installe)
echo Verification des dependances...
venv\Scripts\pip install -r requirements.txt --quiet

echo.
echo ============================================
echo   PIZZ'EN SEYNE - FOOD COST - PRET !
echo ============================================
echo.
echo Sur ce PC :        http://localhost:8000
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "169.254"') do (
    for /f "tokens=1" %%b in ("%%a") do (
        echo Sur telephone :    http://%%b:8000
    )
)
echo ============================================
echo.

start "" http://localhost:8000
venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000
