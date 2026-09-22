@echo off
cd /d "%~dp0"

:: Lancer le serveur en arriere-plan sans fenetre de commande persistante (le serveur ouvre lui-meme un seul onglet)
where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw app.py
    exit
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    start "" /b python app.py
    exit
)

echo [ERREUR] Python n'est pas installe ou n'est pas dans le PATH.
pause
