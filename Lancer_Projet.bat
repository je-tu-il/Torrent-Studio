@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "APP_TITLE=Torrent"
title %APP_TITLE%

echo ========================================================
echo   %APP_TITLE%
echo ========================================================
echo.
REM --- 1. VERIFICATION SI VENV EXISTE DEJA ---
if exist "%~dp0venv\Scripts\python.exe" (
    set "PY_BIN=%~dp0venv\Scripts\python.exe"
    echo [*] Environnement virtuel [venv] detecte.
    echo [*] Lancement automatique direct en cours...
    echo.
    choice /c od /t 2 /d d /n /m "Appuyez sur [O] pour les Options (lancement dans 2s)... "
    if errorlevel 2 goto AUTO_RUN
    if errorlevel 1 goto OPTIONS_MENU
)

REM --- 2. VERIFICATION DE PYTHON SYSTEME ---
python --version >nul 2>&1
if errorlevel 1 (
    echo ========================================================
    echo   [ERREUR] Python introuvable sur votre systeme
    echo ========================================================
    echo Aucun interpreteur Python detecte dans le PATH.
    echo.
    echo Ouverture du Microsoft Store pour installer Python...
    start ms-windows-store://search/?query=Python
    echo.
    pause
    exit /b 1
)

REM --- 3. CHOIX INITIAL DE L'ENVIRONNEMENT ---
echo Choisissez l'environnement d'execution Python :
echo   [1] Environnement virtuel local (venv) [Recommande - Isole]
echo   [2] Python actuel du systeme
echo.
set "CHOIX=1"
set /p "CHOIX=Votre choix (1 ou 2, defaut: 1) : "
echo.
if "%CHOIX:~0,1%"=="2" goto USE_SYSTEM_PYTHON

:USE_VENV
echo [*] Creation de l'environnement virtuel venv...
python -m venv venv
if not exist "%~dp0venv\Scripts\python.exe" (
    echo [!] Echec creation venv, bascule sur Python systeme.
    goto USE_SYSTEM_PYTHON
)
set "PY_BIN=%~dp0venv\Scripts\python.exe"
goto INSTALL_MODULES

:USE_SYSTEM_PYTHON
set "PY_BIN=python"

:INSTALL_MODULES
if exist "%~dp0requirements.txt" (
    echo [*] Verification et installation des modules requis...
    "%PY_BIN%" -m pip install -q --disable-pip-version-check --no-warn-script-location -r "%~dp0requirements.txt"
)
goto AUTO_RUN

:OPTIONS_MENU
cls
echo ========================================================
echo   OPTIONS - %APP_TITLE%
echo ========================================================
echo.
echo   [1] Supprimer l'environnement virtuel (venv)
echo   [2] Reinitialiser l'application (vider cache, logs)
echo   [3] Mettre a jour / Retelecharger depuis GitHub
echo   [4] Lancer avec le Python systeme (sans venv)
echo   [5] Desinstaller les modules Python du projet
echo   [6] Retour au lancement normal
echo.
set "OPT=6"
set /p "OPT=Votre choix [1-6, defaut: 6] : "
echo.
if "%OPT%"=="1" goto OPT_DEL_VENV
if "%OPT%"=="2" goto OPT_RESET
if "%OPT%"=="3" goto OPT_GIT
if "%OPT%"=="4" goto OPT_RUN_SYS
if "%OPT%"=="5" goto OPT_UNINSTALL
goto AUTO_RUN

:OPT_DEL_VENV
echo [*] Suppression du dossier venv en cours...
if exist "%~dp0venv" (
    rmdir /s /q "%~dp0venv"
    echo [OK] Environnement venv supprime.
) else (
    echo [*] Aucun dossier venv present.
)
echo.
pause
exit /b 0

:OPT_RESET
echo [*] Reinitialisation de l'application...
if exist "%~dp0cache" rmdir /s /q "%~dp0cache" 2>nul
if exist "%~dp0__pycache__" rmdir /s /q "%~dp0__pycache__" 2>nul
if exist "%~dp0.cache" rmdir /s /q "%~dp0.cache" 2>nul
del /q "%~dp0*.pyc" 2>nul
del /q "%~dp0*.log" 2>nul
echo [OK] Cache et donnees temporaires nettoyes.
echo.
pause
goto AUTO_RUN

:OPT_GIT
echo [*] Verification de Git...
where git >nul 2>&1
if errorlevel 1 (
    echo [ATTENTION] Git n'est pas installe ou pas detecte dans le PATH.
    echo Ouverture du site officiel pour installer Git...
    start https://git-scm.com/download/win
    echo.
    pause
    goto OPTIONS_MENU
)
echo [*] Synchronisation avec GitHub...
git pull
if errorlevel 1 (
    echo [INFO] La synchronisation necessite une connexion GitHub.
    echo Ouverture de la page de connexion GitHub...
    start https://github.com/login
    echo.
) else (
    echo [OK] Depot mis a jour avec succes.
)
echo.
pause
goto OPTIONS_MENU

:OPT_RUN_SYS
set "PY_BIN=python"
goto AUTO_RUN

:OPT_UNINSTALL
echo [*] Desinstallation des modules Python du projet...
if exist "%~dp0requirements.txt" (
    "%PY_BIN%" -m pip uninstall -y -q --disable-pip-version-check -r "%~dp0requirements.txt"
    echo [OK] Modules desinstalles.
) else (
    echo [*] Aucun fichier requirements.txt trouve.
)
echo.
pause
goto OPTIONS_MENU

:AUTO_RUN
echo [*] Ouverture automatique du navigateur : http://localhost:5050...
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:5050"
echo [*] Demarrage de app.py...
"%PY_BIN%" "%~dp0app.py"
if errorlevel 1 (
    echo.
    echo [!] Le programme s'est arrete avec une erreur (Code: %errorlevel%).
    pause
    exit /b %errorlevel%
)
exit /b 0
