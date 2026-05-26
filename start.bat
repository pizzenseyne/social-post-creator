@echo off
chcp 65001 > nul
title Social Post Creator

echo ============================================
echo        Social Post Creator - Demarrage
echo ============================================
echo.

:: Vérifier si Python est installé
python --version > nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH.
    echo Telechargez Python sur https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Créer le fichier .env s'il n'existe pas
if not exist ".env" (
    echo [INFO] Création du fichier .env à partir de .env.example...
    copy .env.example .env > nul
    echo [!] IMPORTANT: Editez le fichier .env et ajoutez votre cle API Anthropic.
    echo     Fichier .env cree - ouvrez-le et remplacez "sk-ant-..." par votre vraie cle.
    echo.
    notepad .env
    echo.
)

:: Installer les dépendances si nécessaire
if not exist "venv" (
    echo [INFO] Création de l'environnement virtuel...
    python -m venv venv
    echo [INFO] Installation des dépendances...
    call venv\Scripts\activate.bat
    pip install -r requirements.txt --quiet
    echo [OK] Dépendances installées.
) else (
    call venv\Scripts\activate.bat
)

echo.
echo [OK] Démarrage du serveur...
echo.
echo  Ouvrez votre navigateur sur : http://localhost:8000
echo  Appuyez sur Ctrl+C pour arrêter le serveur.
echo.

:: Ouvrir le navigateur après 2 secondes
start "" /b cmd /c "timeout /t 2 > nul && start http://localhost:8000"

:: Démarrer FastAPI
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
