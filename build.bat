@echo off
cd /d "%~dp0"
echo ===================================================
echo     Compilation de Torrent Studio en .exe standalone
echo ===================================================

pyinstaller --noconfirm --clean --onefile --noconsole ^
    --name "TorrentStudio" ^
    --icon "web\favicon.ico" ^
    --add-data "web;web" ^
    --collect-all libtorrent ^
    --collect-all uvicorn ^
    --collect-all fastapi ^
    --collect-all starlette ^
    --hidden-import "uvicorn.logging" ^
    --hidden-import "uvicorn.loops" ^
    --hidden-import "uvicorn.loops.auto" ^
    --hidden-import "uvicorn.protocols" ^
    --hidden-import "uvicorn.protocols.http" ^
    --hidden-import "uvicorn.protocols.http.auto" ^
    --hidden-import "uvicorn.lifespan" ^
    --hidden-import "uvicorn.lifespan.on" ^
    app.py

if %errorlevel% equ 0 (
    echo.
    echo ===================================================
    echo  SUCCES ! L'executable est pret dans dist\TorrentStudio.exe
    echo ===================================================
) else (
    echo.
    echo [ERREUR] La compilation a rencontre un probleme.
)
