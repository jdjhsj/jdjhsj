@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Paie Maroc
echo Lancement du logiciel de paie...
echo.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m paie_maroc web --ouvrir
    goto fin
)
where python >nul 2>nul
if %errorlevel%==0 (
    python -m paie_maroc web --ouvrir
    goto fin
)
echo Python n'est pas installe sur cet ordinateur.
echo Telechargez-le sur https://www.python.org/downloads/
echo et cochez la case "Add Python to PATH" pendant l'installation.
:fin
echo.
pause
