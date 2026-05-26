# Social Post Creator - Installateur automatique
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Social Post Creator - Installation" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Chercher Python dans les emplacements courants
$pythonPaths = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    "C:\Python312\python.exe",
    "C:\Python311\python.exe",
    "C:\Python310\python.exe",
    "$env:USERPROFILE\miniconda3\python.exe",
    "$env:USERPROFILE\anaconda3\python.exe"
)

$pythonExe = $null
foreach ($path in $pythonPaths) {
    if (Test-Path $path) {
        $pythonExe = $path
        break
    }
}

# Si Python non trouvé, le télécharger
if (-not $pythonExe) {
    Write-Host "[INFO] Python non detecte. Telechargement en cours..." -ForegroundColor Yellow
    Write-Host "       (Cela peut prendre 1-2 minutes)" -ForegroundColor Gray

    $installer = "$env:TEMP\python_installer.exe"
    $url = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($url, $installer)

        Write-Host "[INFO] Installation de Python 3.12 (silencieuse)..." -ForegroundColor Yellow
        $proc = Start-Process $installer -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1" -Wait -PassThru

        if ($proc.ExitCode -ne 0) {
            throw "Echec installation Python (code $($proc.ExitCode))"
        }

        # Mettre à jour le PATH de la session
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + $env:PATH

        $pythonExe = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
        if (-not (Test-Path $pythonExe)) {
            $pythonExe = (Get-Command python -ErrorAction SilentlyContinue)?.Source
        }

        Write-Host "[OK] Python installe avec succes !" -ForegroundColor Green
        Remove-Item $installer -ErrorAction SilentlyContinue

    } catch {
        Write-Host ""
        Write-Host "[ERREUR] Impossible d'installer Python automatiquement." -ForegroundColor Red
        Write-Host ""
        Write-Host "Installez Python manuellement :" -ForegroundColor Yellow
        Write-Host "1. Allez sur https://www.python.org/downloads/" -ForegroundColor White
        Write-Host "2. Cliquez 'Download Python 3.12'" -ForegroundColor White
        Write-Host "3. Cochez 'Add Python to PATH' avant d'installer" -ForegroundColor White
        Write-Host "4. Relancez ce script apres l'installation" -ForegroundColor White
        Write-Host ""
        Start-Process "https://www.python.org/downloads/"
        Read-Host "Appuyez sur Entree pour fermer"
        exit 1
    }
}

Write-Host "[OK] Python trouve : $pythonExe" -ForegroundColor Green
& $pythonExe --version

Write-Host ""
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Créer venv si nécessaire
if (-not (Test-Path "venv")) {
    Write-Host "[INFO] Creation de l'environnement virtuel..." -ForegroundColor Yellow
    & $pythonExe -m venv venv
}

$pip = "venv\Scripts\pip.exe"
$uvicorn = "venv\Scripts\uvicorn.exe"

# Installer les dépendances
Write-Host "[INFO] Installation des dependances..." -ForegroundColor Yellow
& $pip install -r requirements.txt --quiet --no-warn-script-location
Write-Host "[OK] Dependances installees !" -ForegroundColor Green

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Serveur demarre sur http://localhost:8000" -ForegroundColor Green
Write-Host "  Appuyez sur Ctrl+C pour arreter" -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

# Ouvrir le navigateur
Start-Process "http://localhost:8000"

# Démarrer le serveur
& $uvicorn main:app --host 0.0.0.0 --port 8000 --reload
