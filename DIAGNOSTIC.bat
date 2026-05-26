@echo off
chcp 65001 > nul
title Diagnostic

echo ===== DIAGNOSTIC =====
echo.

echo Test Python :
python --version
python3 --version
py --version

echo.
echo Test winget :
winget --version

echo.
echo Test PowerShell :
powershell -Command "Write-Host 'PowerShell OK'"

echo.
echo ===== FIN =====
pause
