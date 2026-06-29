@echo off
title Pizz'en Seyne - Food Cost
cd /d "%~dp0"

:: Installation initiale si venv absent
if not exist "venv\Scripts\python.exe" (
    echo Installation en cours, patientez...
    py -m venv venv
    venv\Scripts\pip install fastapi "uvicorn[standard]" python-dotenv python-multipart httpx --quiet
    echo Installation terminee !
)

echo.
echo ============================================
echo   PIZZ'EN SEYNE - FOOD COST - PRET !
echo ============================================
echo.
echo Sur ce PC :        http://localhost:8000/foodcost
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "169.254"') do (
    for /f "tokens=1" %%b in ("%%a") do (
        echo Sur telephone :    http://%%b:8000/foodcost
    )
)
echo ============================================
echo.

start "" http://localhost:8000/foodcost
venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000
