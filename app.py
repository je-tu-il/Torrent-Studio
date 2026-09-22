import os
import sys
from pathlib import Path

# Résolution des chemins pour mode script ou exécutable standalone
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = APP_DIR

WEB_DIR = BUNDLE_DIR / "web"
DATA_DIR = APP_DIR / "data"
LOG_FILE = DATA_DIR / "app.log"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Rediriger stdout et stderr vers app.log pour tracer les erreurs même sans console
if sys.stdout is None:
    try:
        sys.stdout = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    except Exception:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    try:
        sys.stderr = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    except Exception:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

def log_msg(msg):
    try:
        import time
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

import socket
import webbrowser
import threading
import asyncio
import subprocess
import string
from typing import Optional, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from torrent_manager import TorrentManager, TORRENTS_STORAGE

def open_browser_window(url: str):
    """Ouvre l'URL dans le navigateur par défaut de manière garantie sous Windows."""
    try:
        os.startfile(url)
    except Exception:
        try:
            webbrowser.open(url)
        except Exception:
            pass

def check_single_instance(port=5050):
    """
    Vérifie si une instance tourne déjà sur ce port.
    Si oui, ouvre le navigateur sur la session active et quitte immédiatement.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.6)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        open_browser_window(f"http://127.0.0.1:{port}")
        sys.exit(0)
    except (ConnectionRefusedError, OSError, socket.timeout):
        pass
    finally:
        s.close()

app = FastAPI(title="Torrent Studio Mini", version="2.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tm = TorrentManager()

# Models
class MagnetRequest(BaseModel):
    magnet: str
    save_path: Optional[str] = None
    priority: Optional[str] = "normal"
    auto_seed: Optional[bool] = None

class ActionRequest(BaseModel):
    hash: str
    action: str  # pause, resume, toggle_seed, set_priority, delete
    seed_enabled: Optional[bool] = None
    priority: Optional[str] = None
    delete_files: Optional[bool] = False

class CreateTorrentRequest(BaseModel):
    source_path: str
    trackers: Optional[List[str]] = None
    piece_size_kb: Optional[int] = 0
    comment: Optional[str] = ""
    seed_after: Optional[bool] = False

class SettingsRequest(BaseModel):
    default_save_path: Optional[str] = None
    default_auto_seed: Optional[bool] = None
    max_download_rate: Optional[int] = None
    max_upload_rate: Optional[int] = None
    max_active_downloads: Optional[int] = None
    close_behavior: Optional[str] = None

# Routes

@app.get("/favicon.ico")
async def get_favicon_ico():
    favicon_path = WEB_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/favicon.png")
async def get_favicon_png():
    favicon_path = WEB_DIR / "favicon.png"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/favicon.svg")
async def get_favicon_svg():
    favicon_path = WEB_DIR / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/api/heartbeat")
async def client_heartbeat():
    tm.record_heartbeat()
    return {"status": "ok"}

@app.post("/api/leave")
async def client_leave():
    tm.record_client_leave()
    return {"status": "ok"}

@app.get("/api/torrents")
async def get_torrents():
    tm.record_heartbeat()
    return {
        "torrents": tm.get_all_torrents(),
        "stats": tm.get_global_stats()
    }

@app.post("/api/torrents/add-magnet")
async def add_magnet(req: MagnetRequest):
    uri = req.magnet.strip()
    if not uri or not uri.startswith("magnet:"):
        raise HTTPException(status_code=400, detail="Lien magnet invalide.")
    try:
        meta = tm.add_magnet(
            uri=uri,
            save_path=req.save_path,
            priority=req.priority or "normal",
            auto_seed=req.auto_seed
        )
        return {"success": True, "torrent": meta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Échec de l'ajout du magnet : {str(e)}")

@app.post("/api/torrents/add-file")
async def add_torrent_file(
    file: UploadFile = File(...),
    save_path: Optional[str] = Form(None),
    priority: Optional[str] = Form("normal"),
    auto_seed: Optional[bool] = Form(None)
):
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Fichier .torrent vide.")
        meta = tm.add_torrent_file(
            file_bytes=content,
            original_filename=file.filename,
            save_path=save_path,
            priority=priority,
            auto_seed=auto_seed
        )
        return {"success": True, "torrent": meta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Échec de l'ajout du fichier .torrent : {str(e)}")

@app.post("/api/torrents/action")
async def torrent_action(req: ActionRequest):
    h = req.hash
    act = req.action.lower()

    if act == "pause":
        ok = tm.pause_torrent(h)
    elif act == "resume":
        ok = tm.resume_torrent(h)
    elif act == "toggle_seed":
        ok = tm.toggle_seed(h, req.seed_enabled)
        return {"success": True, "seed_enabled": ok}
    elif act == "set_priority":
        if not req.priority:
            raise HTTPException(status_code=400, detail="Priorité manquante.")
        ok = tm.set_priority(h, req.priority)
    elif act == "delete":
        ok = tm.delete_torrent(h, delete_files=bool(req.delete_files))
    else:
        raise HTTPException(status_code=400, detail=f"Action inconnue : {act}")

    return {"success": ok}

@app.post("/api/torrents/create")
async def create_torrent(req: CreateTorrentRequest):
    if not req.source_path or not os.path.exists(req.source_path):
        raise HTTPException(status_code=400, detail="Le chemin source spécifié est introuvable sur le disque.")
    try:
        res = tm.create_torrent_file(
            source_path=req.source_path,
            trackers=req.trackers,
            piece_size_kb=req.piece_size_kb or 0,
            comment=req.comment or "",
            seed_after=bool(req.seed_after)
        )
        return {"success": True, "created": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur création .torrent : {str(e)}")

@app.get("/api/torrents/download-torrent/{info_hash}")
async def download_created_torrent(info_hash: str):
    file_path = TORRENTS_STORAGE / f"{info_hash}.torrent"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fichier .torrent introuvable.")
    meta = tm.torrents.get(info_hash, {})
    filename = f"{meta.get('name', info_hash)}.torrent"
    return FileResponse(path=file_path, filename=filename, media_type="application/x-bittorrent")

@app.get("/api/history")
async def get_history():
    return tm.history

@app.delete("/api/history")
async def delete_history(hash: Optional[str] = Query(None)):
    if hash:
        tm.delete_history_item(hash)
    else:
        tm.clear_history()
    return {"success": True}

@app.get("/api/settings")
async def get_settings():
    return tm.settings

@app.post("/api/settings")
async def update_settings(req: SettingsRequest):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    saved = tm.update_settings(updates)
    return {"success": True, "settings": saved}

def _open_folder_dialog():
    """Ouvre un dialogue de sélection de dossier natif Windows au premier plan sans bloquer le serveur."""
    ps_code = """
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Sélectionnez le dossier de téléchargement'
    $dialog.ShowNewFolderButton = $true
    $form = New-Object System.Windows.Forms.Form
    $form.TopMost = $true
    $form.StartPosition = 'Manual'
    $form.Location = New-Object System.Drawing.Point(-2000, -2000)
    $form.Show()
    $result = $dialog.ShowDialog($form)
    $form.Dispose()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        [Console]::WriteLine($dialog.SelectedPath)
    }
    """
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=flags,
            timeout=120
        )
        out = proc.stdout.strip()
        if out:
            return out
    except Exception as e:
        log_msg(f"Erreur PowerShell folder dialog: {e}")

    # Secours Tkinter si PowerShell échoue
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title="Sélectionnez un dossier")
        root.destroy()
        return folder
    except Exception:
        return ""

def _open_file_dialog():
    """Ouvre un dialogue de sélection de fichier natif Windows au premier plan."""
    ps_code = """
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = 'Sélectionnez un fichier'
    $dialog.Filter = 'Tous les fichiers (*.*)|*.*'
    $form = New-Object System.Windows.Forms.Form
    $form.TopMost = $true
    $form.StartPosition = 'Manual'
    $form.Location = New-Object System.Drawing.Point(-2000, -2000)
    $form.Show()
    $result = $dialog.ShowDialog($form)
    $form.Dispose()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        [Console]::WriteLine($dialog.FileName)
    }
    """
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=flags,
            timeout=120
        )
        out = proc.stdout.strip()
        if out:
            return out
    except Exception as e:
        log_msg(f"Erreur PowerShell file dialog: {e}")

    # Secours Tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        file_selected = filedialog.askopenfilename(title="Sélectionnez un fichier")
        root.destroy()
        return file_selected
    except Exception:
        return ""

@app.get("/api/quick-folders")
def get_quick_folders():
    """Renvoie les dossiers fréquemment utilisés et les disques du PC pour un choix en 1 clic."""
    folders = []
    
    # Downloads
    dl = Path.home() / "Downloads"
    if dl.exists():
        folders.append({"name": "Téléchargements", "path": str(dl), "icon": "download"})
        
    # Desktop
    dt = Path.home() / "Desktop"
    if dt.exists():
        folders.append({"name": "Bureau", "path": str(dt), "icon": "desktop"})
        
    # Videos
    vid = Path.home() / "Videos"
    if vid.exists():
        folders.append({"name": "Vidéos", "path": str(vid), "icon": "video"})
        
    # Project downloads folder
    proj_dl = APP_DIR / "downloads"
    proj_dl.mkdir(parents=True, exist_ok=True)
    folders.append({"name": "Dossier Projet", "path": str(proj_dl), "icon": "folder"})
    
    # Available Windows Drives
    for d in string.ascii_uppercase:
        drive_path = f"{d}:\\"
        if os.path.exists(drive_path):
            folders.append({"name": f"Disque {d}:", "path": drive_path, "icon": "drive"})
            
    return {"folders": folders}

@app.get("/api/browse-folder")
def browse_folder():
    """Ouvre la boîte de dialogue native Windows pour choisir un dossier."""
    try:
        path = _open_folder_dialog()
        return {"path": path.replace("/", "\\") if path else ""}
    except Exception as e:
        return {"path": "", "error": str(e)}

@app.get("/api/browse-file")
def browse_file():
    """Ouvre la boîte de dialogue native Windows pour choisir un fichier."""
    try:
        path = _open_file_dialog()
        return {"path": path.replace("/", "\\") if path else ""}
    except Exception as e:
        return {"path": "", "error": str(e)}

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Fichier web/index.html introuvable</h1>", status_code=404)
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.on_event("shutdown")
def shutdown_event():
    tm.shutdown()

def start_server(host="127.0.0.1", port=5050, open_browser=True):
    log_msg(f"Vérification de l'instance sur port {port}...")
    check_single_instance(port)
    log_msg("Port libre, initialisation du serveur...")

    if open_browser:
        def _open():
            import time
            time.sleep(0.8)
            url = f"http://{host}:{port}"
            log_msg(f"Ouverture du navigateur sur {url}...")
            open_browser_window(url)
        threading.Thread(target=_open, daemon=True).start()

    log_msg("Lancement de uvicorn.run...")
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    import traceback
    try:
        log_msg("=== Lancement du processus principal ===")
        start_server()
    except Exception as e:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"CRASH FATAL: {e}\n")
            traceback.print_exc(file=f)
