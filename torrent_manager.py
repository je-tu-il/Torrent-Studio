import os
import sys

# Rediriger stdout et stderr si None (cas pythonw sous Windows)
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import time
import json
import logging
import threading
import subprocess
from pathlib import Path
import libtorrent as lt

logger = logging.getLogger("TorrentManager")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def send_windows_notification(title: str, message: str):
    """Envoie une notification native Windows en arrière-plan sans bloquer."""
    ps_code = f"""
    Add-Type -AssemblyName System.Windows.Forms
    $notify = New-Object System.Windows.Forms.NotifyIcon
    $notify.Icon = [System.Drawing.SystemIcons]::Information
    $notify.Visible = $true
    $notify.ShowBalloonTip(5000, '{title}', '{message}', [System.Windows.Forms.ToolTipIcon]::Info)
    Start-Sleep -Seconds 1
    $notify.Dispose()
    """
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-Command", ps_code], creationflags=flags)
    except Exception as e:
        logger.error(f"Erreur envoi notification: {e}")

DEFAULT_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.tracker.cl:1337/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://explodie.org:6969/announce",
    "udp://open.stealth.si:80/announce",
    "http://tracker.openbittorrent.com:80/announce"
]

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

DATA_DIR = APP_DIR / "data"
TORRENTS_STORAGE = DATA_DIR / "torrents"
STATE_FILE = DATA_DIR / "state.json"

DEFAULT_DOWNLOADS_PATH = str(Path.home() / "Downloads")

class TorrentManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.session = None
        self.torrents = {}  # hash -> metadata dict
        self.handles = {}   # hash -> torrent_handle
        self.history = []   # list of past torrents
        self.settings = {
            "default_save_path": DEFAULT_DOWNLOADS_PATH,
            "default_auto_seed": False,  # Par défaut : ne pas seeder comme demandé
            "max_download_rate": 0,      # 0 = illimité
            "max_upload_rate": 0,        # 0 = illimité
            "max_active_downloads": 10,
            "enable_dht": True,
            "close_behavior": "finish_downloads_and_stop"  # finish_downloads_and_stop, keep_seeding_and_stop, always_24_7, stop_immediately
        }
        self.last_heartbeat = time.time()
        self.startup_time = time.time()
        self.client_is_alive = True
        self.has_connected_once = False
        self.disconnect_time = None
        self.was_downloading_background = False
        self.shutdown_triggered = False
        self.running = True
        self._init_storage()
        self._load_state()
        self._init_session()
        self._start_monitor_thread()

    def record_heartbeat(self):
        with self.lock:
            self.last_heartbeat = time.time()
            self.client_is_alive = True
            self.has_connected_once = True
            self.disconnect_time = None

    def record_client_leave(self):
        with self.lock:
            self.client_is_alive = False
            if self.disconnect_time is None:
                self.disconnect_time = time.time()

    def _init_storage(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        TORRENTS_STORAGE.mkdir(parents=True, exist_ok=True)

    def _init_session(self):
        pack_settings = {
            "enable_dht": self.settings.get("enable_dht", True),
            "enable_lsd": True,
            "enable_upnp": True,
            "enable_natpmp": True,
            "dht_bootstrap_nodes": (
                "router.bittorrent.com:6881,"
                "dht.transmissionbt.com:6881,"
                "router.utorrent.com:6881,"
                "dht.libtorrent.org:25401"
            ),
            "alert_mask": (
                lt.alert.category_t.status_notification |
                lt.alert.category_t.error_notification |
                lt.alert.category_t.storage_notification
            ),
            "download_rate_limit": self.settings.get("max_download_rate", 0),
            "upload_rate_limit": self.settings.get("max_upload_rate", 0),
        }
        self.session = lt.session(pack_settings)
        logger.info("Session libtorrent initialisée avec succès.")

        # Re-charger les torrents sauvegardés
        self._restore_saved_torrents()

    def _load_state(self):
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.settings.update(data.get("settings", {}))
                    self.history = data.get("history", [])
                    saved_torrents = data.get("torrents", {})
                    self.torrents = saved_torrents
                logger.info(f"État chargé : {len(self.torrents)} torrents en session, {len(self.history)} dans l'historique.")
            except Exception as e:
                logger.error(f"Erreur chargement state.json: {e}")

    def save_state(self):
        with self.lock:
            data = {
                "settings": self.settings,
                "history": self.history,
                "torrents": self.torrents
            }
            tmp_file = STATE_FILE.with_suffix(".tmp")
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                tmp_file.replace(STATE_FILE)
            except Exception as e:
                logger.error(f"Erreur sauvegarde state.json: {e}")

    def _restore_saved_torrents(self):
        with self.lock:
            for info_hash, meta in list(self.torrents.items()):
                try:
                    save_path = meta.get("save_path", self.settings["default_save_path"])
                    if not os.path.exists(save_path):
                        os.makedirs(save_path, exist_ok=True)

                    params = None
                    torrent_file = meta.get("torrent_file_path")
                    magnet_uri = meta.get("magnet_uri")

                    if torrent_file and os.path.exists(torrent_file):
                        with open(torrent_file, "rb") as f:
                            torrent_bytes = f.read()
                        ti = lt.torrent_info(torrent_bytes)
                        params = lt.add_torrent_params()
                        params.ti = ti
                    elif magnet_uri:
                        params = lt.parse_magnet_uri(magnet_uri)

                    if params:
                        params.save_path = save_path
                        handle = self.session.add_torrent(params)
                        self.handles[info_hash] = handle

                        # Appliquer la priorité
                        self._apply_priority(handle, meta.get("priority", "normal"))

                        # Appliquer l'état de pause / seed
                        if meta.get("user_paused", False):
                            handle.pause()
                        elif meta.get("is_finished", False) and not meta.get("seed_enabled", False):
                            handle.pause()
                        else:
                            handle.resume()

                        logger.info(f"Torrent restauré : {meta.get('name', info_hash)}")
                except Exception as e:
                    logger.error(f"Échec restauration torrent {info_hash}: {e}")

    def _apply_priority(self, handle, priority_str):
        prio_map = {
            "low": 50,
            "normal": 100,
            "high": 180,
            "max": 255
        }
        val = prio_map.get(priority_str.lower(), 100)
        try:
            handle.set_priority(val)
        except Exception:
            pass

    def add_magnet(self, uri: str, save_path: str = None, priority: str = "normal", auto_seed: bool = None) -> dict:
        with self.lock:
            if not save_path:
                save_path = self.settings["default_save_path"]
            if auto_seed is None:
                auto_seed = self.settings["default_auto_seed"]

            os.makedirs(save_path, exist_ok=True)
            params = lt.parse_magnet_uri(uri)
            params.save_path = save_path

            # Ajouter trackers recommandés pour booster la recherche
            for tr in DEFAULT_TRACKERS:
                try:
                    params.trackers.append(tr)
                except Exception:
                    pass

            handle = self.session.add_torrent(params)
            info_hash = str(handle.info_hash())

            # Nom initial déduit ou temporaire
            name = params.name or f"Magnet_{info_hash[:10]}"

            meta = {
                "hash": info_hash,
                "name": name,
                "save_path": save_path,
                "priority": priority,
                "auto_seed": auto_seed,
                "seed_enabled": auto_seed,  # Détermine si le seed sera actif
                "user_paused": False,
                "is_finished": False,
                "magnet_uri": uri,
                "torrent_file_path": None,
                "date_added": time.strftime("%Y-%m-%d %H:%M:%S"),
                "date_finished": None,
                "total_downloaded": 0,
                "total_uploaded": 0
            }

            self.torrents[info_hash] = meta
            self.handles[info_hash] = handle
            self._apply_priority(handle, priority)
            self.save_state()
            logger.info(f"Magnet ajouté : {name} ({info_hash})")
            return meta

    def add_torrent_file(self, file_bytes: bytes, original_filename: str = "", save_path: str = None, priority: str = "normal", auto_seed: bool = None) -> dict:
        with self.lock:
            if not save_path:
                save_path = self.settings["default_save_path"]
            if auto_seed is None:
                auto_seed = self.settings["default_auto_seed"]

            os.makedirs(save_path, exist_ok=True)
            ti = lt.torrent_info(file_bytes)
            info_hash = str(ti.info_hash())

            # Sauvegarde physique du fichier .torrent pour persistance
            torrent_path = str(TORRENTS_STORAGE / f"{info_hash}.torrent")
            with open(torrent_path, "wb") as f:
                f.write(file_bytes)

            params = lt.add_torrent_params()
            params.ti = ti
            params.save_path = save_path

            for tr in DEFAULT_TRACKERS:
                try:
                    params.trackers.append(tr)
                except Exception:
                    pass

            handle = self.session.add_torrent(params)
            name = ti.name() or original_filename or f"Torrent_{info_hash[:10]}"

            meta = {
                "hash": info_hash,
                "name": name,
                "save_path": save_path,
                "priority": priority,
                "auto_seed": auto_seed,
                "seed_enabled": auto_seed,
                "user_paused": False,
                "is_finished": False,
                "magnet_uri": lt.make_magnet_uri(ti),
                "torrent_file_path": torrent_path,
                "date_added": time.strftime("%Y-%m-%d %H:%M:%S"),
                "date_finished": None,
                "total_downloaded": 0,
                "total_uploaded": 0
            }

            self.torrents[info_hash] = meta
            self.handles[info_hash] = handle
            self._apply_priority(handle, priority)
            self.save_state()
            logger.info(f"Fichier .torrent ajouté : {name} ({info_hash})")
            return meta

    def pause_torrent(self, info_hash: str) -> bool:
        with self.lock:
            handle = self.handles.get(info_hash)
            meta = self.torrents.get(info_hash)
            if not handle or not meta:
                return False
            meta["user_paused"] = True
            handle.pause()
            self.save_state()
            return True

    def resume_torrent(self, info_hash: str) -> bool:
        with self.lock:
            handle = self.handles.get(info_hash)
            meta = self.torrents.get(info_hash)
            if not handle or not meta:
                return False
            meta["user_paused"] = False
            # Si le torrent est terminé mais que son seed_enabled est faux,
            # reprendre le torrent réactive également le seed ou l'utilisateur veut le forcer
            if meta.get("is_finished", False):
                meta["seed_enabled"] = True
            handle.resume()
            self.save_state()
            return True

    def toggle_seed(self, info_hash: str, enable: bool = None) -> bool:
        """
        Active ou désactive spécifiquement le seeding pour ce torrent.
        Permet de désélectionner un torrent à la seed et de le réactiver plus tard.
        """
        with self.lock:
            handle = self.handles.get(info_hash)
            meta = self.torrents.get(info_hash)
            if not meta:
                return False

            if enable is None:
                new_state = not meta.get("seed_enabled", False)
            else:
                new_state = bool(enable)

            meta["seed_enabled"] = new_state
            logger.info(f"Toggle seed pour {meta['name']} -> {new_state}")

            if handle and handle.is_valid():
                st = handle.status()
                # Si le torrent est déjà terminé (100%) ou en train de seeder
                if st.progress >= 0.9999 or st.is_finished or st.is_seeding:
                    if not new_state:
                        # Stopper immédiatement le seed
                        handle.pause()
                    else:
                        # Réactiver le seed
                        meta["user_paused"] = False
                        handle.resume()

            self.save_state()
            return new_state

    def set_priority(self, info_hash: str, priority_str: str) -> bool:
        with self.lock:
            handle = self.handles.get(info_hash)
            meta = self.torrents.get(info_hash)
            if not meta:
                return False
            meta["priority"] = priority_str
            if handle and handle.is_valid():
                self._apply_priority(handle, priority_str)
            self.save_state()
            return True

    def delete_torrent(self, info_hash: str, delete_files: bool = False) -> bool:
        with self.lock:
            handle = self.handles.get(info_hash)
            meta = self.torrents.get(info_hash, {})

            # Enregistrer dans l'historique avant suppression
            self._archive_to_history(info_hash, meta, status_label="Supprimé")

            if handle and handle.is_valid():
                try:
                    if delete_files:
                        self.session.remove_torrent(handle, lt.session.delete_files)
                    else:
                        self.session.remove_torrent(handle)
                except Exception as e:
                    logger.error(f"Erreur remove_torrent: {e}")

            if info_hash in self.handles:
                del self.handles[info_hash]
            if info_hash in self.torrents:
                # Supprimer le fichier .torrent stocké si présent
                fpath = meta.get("torrent_file_path")
                if fpath and os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
                del self.torrents[info_hash]

            self.save_state()
            logger.info(f"Torrent supprimé : {meta.get('name', info_hash)} (delete_files={delete_files})")
            return True

    def _archive_to_history(self, info_hash: str, meta: dict, status_label: str = "Terminé"):
        # Éviter les doublons stricts dans l'historique
        existing = next((item for item in self.history if item.get("hash") == info_hash), None)
        total_dl = meta.get("total_downloaded", 0)
        total_ul = meta.get("total_uploaded", 0)
        ratio = round(total_ul / max(1, total_dl), 2)

        record = {
            "hash": info_hash,
            "name": meta.get("name", "Inconnu"),
            "size": meta.get("total_size", 0),
            "date_added": meta.get("date_added", time.strftime("%Y-%m-%d %H:%M:%S")),
            "date_finished": meta.get("date_finished") or time.strftime("%Y-%m-%d %H:%M:%S"),
            "downloaded": total_dl,
            "uploaded": total_ul,
            "ratio": ratio,
            "status": status_label,
            "magnet_uri": meta.get("magnet_uri")
        }

        if existing:
            self.history.remove(existing)
        self.history.insert(0, record)
        # Limiter l'historique aux 200 derniers torrents
        self.history = self.history[:200]

    def clear_history(self):
        with self.lock:
            self.history.clear()
            self.save_state()

    def delete_history_item(self, info_hash: str):
        with self.lock:
            self.history = [h for h in self.history if h.get("hash") != info_hash]
            self.save_state()

    def create_torrent_file(self, source_path: str, trackers: list = None, piece_size_kb: int = 0, comment: str = "", seed_after: bool = False) -> dict:
        """
        Génère un fichier .torrent à partir d'un fichier ou dossier local.
        """
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Le chemin source n'existe pas : {source_path}")

        source_path = os.path.abspath(source_path)
        is_dir = os.path.isdir(source_path)
        parent_dir = os.path.dirname(source_path)
        basename = os.path.basename(source_path)

        # Utilisation de list_files ou add_files
        fs = lt.file_storage()
        lt.add_files(fs, source_path)

        piece_size_bytes = piece_size_kb * 1024 if piece_size_kb > 0 else 0
        t = lt.create_torrent(fs, piece_size_bytes)

        if not trackers:
            trackers = DEFAULT_TRACKERS

        tier = 0
        for tr in trackers:
            tr = tr.strip()
            if tr:
                t.add_tracker(tr, tier)
                tier += 1

        if comment:
            t.set_comment(comment)
        t.set_creator("Torrent Studio Mini")

        # Calculer les hachages de pièces
        lt.set_piece_hashes(t, parent_dir)
        torrent_entry = t.generate()
        torrent_bytes = lt.bencode(torrent_entry)

        ti = lt.torrent_info(torrent_bytes)
        info_hash = str(ti.info_hash())

        # Enregistrer le .torrent généré
        output_filename = f"{basename}.torrent"
        output_path = str(TORRENTS_STORAGE / output_filename)
        with open(output_path, "wb") as f:
            f.write(torrent_bytes)

        res = {
            "name": basename,
            "hash": info_hash,
            "size": ti.total_size(),
            "pieces": ti.num_pieces(),
            "piece_length": ti.piece_length(),
            "torrent_file_path": output_path,
            "output_filename": output_filename
        }

        # Si l'utilisateur a choisi de seeder directement après création
        if seed_after:
            params = lt.add_torrent_params()
            params.ti = ti
            params.save_path = parent_dir
            params.flags |= lt.torrent_flags.seed_mode

            handle = self.session.add_torrent(params)
            self.handles[info_hash] = handle

            meta = {
                "hash": info_hash,
                "name": basename,
                "save_path": parent_dir,
                "priority": "normal",
                "auto_seed": True,
                "seed_enabled": True,
                "user_paused": False,
                "is_finished": True,
                "magnet_uri": lt.make_magnet_uri(ti),
                "torrent_file_path": output_path,
                "date_added": time.strftime("%Y-%m-%d %H:%M:%S"),
                "date_finished": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_downloaded": ti.total_size(),
                "total_uploaded": 0
            }
            self.torrents[info_hash] = meta
            self.save_state()

        return res

    def get_all_torrents(self) -> list:
        with self.lock:
            result = []
            for info_hash, meta in self.torrents.items():
                handle = self.handles.get(info_hash)
                data = dict(meta)

                if not handle or not handle.is_valid():
                    data.update({
                        "progress": 1.0 if meta.get("is_finished") else 0.0,
                        "download_rate": 0,
                        "upload_rate": 0,
                        "num_seeds": 0,
                        "num_peers": 0,
                        "eta_seconds": 0 if meta.get("is_finished") else None,
                        "state": "paused",
                        "state_label": "En pause",
                        "total_size": meta.get("total_size", 0),
                        "total_done": meta.get("total_size", 0) if meta.get("is_finished") else 0
                    })
                    result.append(data)
                    continue

                st = handle.status()

                # Mise à jour du nom dès réception des métadonnées
                if handle.has_metadata():
                    ti = handle.torrent_file()
                    if ti and ti.name():
                        data["name"] = ti.name()
                        meta["name"] = ti.name()
                        data["total_size"] = ti.total_size()
                        meta["total_size"] = ti.total_size()

                total_size = st.total_wanted or st.total or meta.get("total_size", 0)
                total_done = st.total_done
                progress = round(st.progress, 4)
                dl_rate = st.download_rate
                up_rate = st.upload_rate

                meta["total_size"] = total_size
                meta["total_downloaded"] = st.all_time_download
                meta["total_uploaded"] = st.all_time_upload

                # Calcul ETA (temps estimé)
                eta_seconds = None
                if progress >= 0.9999 or st.is_finished:
                    eta_seconds = 0
                elif dl_rate > 1024:
                    remaining = max(0, total_size - total_done)
                    eta_seconds = int(remaining / dl_rate)

                # Détermination de l'état
                user_paused = meta.get("user_paused", False)
                seed_enabled = meta.get("seed_enabled", False)
                is_finished = progress >= 0.9999 or st.is_finished

                if is_finished and not meta.get("is_finished"):
                    meta["is_finished"] = True
                    meta["date_finished"] = time.strftime("%Y-%m-%d %H:%M:%S")

                state_code = "downloading"
                state_label = "Téléchargement"

                if user_paused:
                    state_code = "paused"
                    state_label = "En pause"
                elif not handle.has_metadata():
                    state_code = "metadata"
                    state_label = "Récupération infos…"
                elif is_finished:
                    if seed_enabled and not user_paused:
                        state_code = "seeding"
                        state_label = "Partage (Seeding)"
                    else:
                        state_code = "finished"
                        state_label = "Terminé (Seed désactivé)"
                elif int(st.state) == 1 or int(st.state) == 7:  # checking
                    state_code = "checking"
                    state_label = "Vérification…"
                elif dl_rate == 0 and st.num_seeds == 0:
                    state_code = "stalled"
                    state_label = "En attente de sources"

                data.update({
                    "progress": progress,
                    "download_rate": dl_rate,
                    "upload_rate": up_rate,
                    "num_seeds": st.num_seeds,
                    "num_complete": max(0, st.num_complete),
                    "num_peers": st.num_peers,
                    "num_incomplete": max(0, st.num_incomplete),
                    "eta_seconds": eta_seconds,
                    "total_size": total_size,
                    "total_done": total_done,
                    "total_downloaded": st.all_time_download,
                    "total_uploaded": st.all_time_upload,
                    "state": state_code,
                    "state_label": state_label
                })
                result.append(data)

            return result

    def get_global_stats(self) -> dict:
        torrents = self.get_all_torrents()
        total_dl_rate = sum(t["download_rate"] for t in torrents)
        total_ul_rate = sum(t["upload_rate"] for t in torrents)
        active_dl = sum(1 for t in torrents if t["state"] in ("downloading", "metadata", "stalled"))
        active_seed = sum(1 for t in torrents if t["state"] == "seeding")
        completed = sum(1 for t in torrents if t["progress"] >= 0.9999)

        return {
            "total_download_rate": total_dl_rate,
            "total_upload_rate": total_ul_rate,
            "active_downloads": active_dl,
            "active_seeds": active_seed,
            "completed_count": completed,
            "total_count": len(torrents),
            "dht_nodes": self.session.status().dht_nodes if self.session else 0
        }

    def update_settings(self, new_settings: dict) -> dict:
        with self.lock:
            for k in ["default_save_path", "default_auto_seed", "max_download_rate", "max_upload_rate", "max_active_downloads", "close_behavior"]:
                if k in new_settings:
                    self.settings[k] = new_settings[k]

            # Mettre à jour les limites session
            if "max_download_rate" in new_settings or "max_upload_rate" in new_settings:
                sett = {
                    "download_rate_limit": int(self.settings.get("max_download_rate", 0)),
                    "upload_rate_limit": int(self.settings.get("max_upload_rate", 0))
                }
                self.session.apply_settings(sett)

            self.save_state()
            return self.settings

    def _start_monitor_thread(self):
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()

    def _monitor_loop(self):
        """
        Boucle de fond : vérifie les complétions, applique les arrêts de seed si requis,
        traite les alertes libtorrent, gère le cycle de vie quand l'interface est fermée,
        et persiste l'état.
        """
        last_save = time.time()

        while self.running:
            try:
                # 1. Traiter les alertes libtorrent
                if self.session:
                    alerts = self.session.pop_alerts()
                    for alert in alerts:
                        what = alert.what()
                        if what == "torrent_finished_alert":
                            h = alert.handle
                            info_hash = str(h.info_hash())
                            with self.lock:
                                meta = self.torrents.get(info_hash)
                                if meta:
                                    meta["is_finished"] = True
                                    meta["date_finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
                                    # Vérifier la règle de seed
                                    if not meta.get("auto_seed", False) or not meta.get("seed_enabled", False):
                                        meta["seed_enabled"] = False
                                        h.pause()
                                        logger.info(f"Torrent {meta['name']} terminé -> Seed stoppé automatiquement.")
                                    else:
                                        logger.info(f"Torrent {meta['name']} terminé -> Seed actif.")
                                    self._archive_to_history(info_hash, meta, status_label="Terminé")

                # 2. Vérification périodique de tous les torrents
                with self.lock:
                    for info_hash, meta in list(self.torrents.items()):
                        h = self.handles.get(info_hash)
                        if h and h.is_valid():
                            st = h.status()
                            # Nom si metadata enfin dispo
                            if h.has_metadata():
                                ti = h.torrent_file()
                                if ti and ti.name() and meta.get("name", "").startswith("Magnet_"):
                                    meta["name"] = ti.name()
                                    meta["total_size"] = ti.total_size()

                            # Détection de fin de téléchargement
                            if (st.progress >= 0.9999 or st.is_finished) and not meta.get("is_finished", False):
                                meta["is_finished"] = True
                                meta["date_finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
                                if not meta.get("auto_seed", False) or not meta.get("seed_enabled", False):
                                    meta["seed_enabled"] = False
                                    h.pause()
                                    logger.info(f"Torrent {meta['name']} complété -> Seed coupé (auto_seed=False).")
                                self._archive_to_history(info_hash, meta, status_label="Terminé")

                            # Si seed désactivé sur un torrent terminé, s'assurer qu'il reste en pause
                            if meta.get("is_finished", False) and not meta.get("seed_enabled", False):
                                if not st.paused:
                                    h.pause()

                # 3. Vérification du comportement à la fermeture de la page
                now = time.time()
                if self.has_connected_once and not self.shutdown_triggered:
                    # Tolérance de 60 secondes sans heartbeat avant de considérer la déconnexion
                    client_active = (now - self.last_heartbeat) < 60
                    self.client_is_alive = client_active

                    if client_active:
                        self.disconnect_time = None
                    else:
                        if self.disconnect_time is None:
                            self.disconnect_time = now

                        disconnected_duration = now - self.disconnect_time
                        # Attendre 45 secondes de déconnexion confirmée (soit au moins 105s sans heartbeat)
                        if disconnected_duration >= 45:
                            behavior = self.settings.get("close_behavior", "finish_downloads_and_stop")
                            torrents = self.get_all_torrents()
                            active_dl = sum(1 for t in torrents if t["state"] in ("downloading", "metadata", "stalled"))
                            active_seed = sum(1 for t in torrents if t["state"] == "seeding")

                            if behavior == "always_24_7":
                                # Le serveur reste toujours actif 24/24 sur le PC
                                pass
                            elif behavior == "finish_downloads_and_stop":
                                if active_dl > 0:
                                    self.was_downloading_background = True
                                else:
                                    self.shutdown_triggered = True
                                    if self.was_downloading_background:
                                        logger.info("Téléchargements terminés en tâche de fond. Arrêt du serveur avec notification.")
                                        send_windows_notification("Torrent Studio Pro", "Tous vos téléchargements sont terminés ! Le serveur s'est arrêté.")
                                    else:
                                        logger.info("Page fermée et aucun téléchargement actif. Arrêt du serveur.")
                                    self.shutdown()
                                    threading.Thread(target=lambda: (time.sleep(1.2), os._exit(0)), daemon=True).start()
                            elif behavior == "keep_seeding_and_stop":
                                if active_dl > 0 or active_seed > 0:
                                    self.was_downloading_background = True
                                else:
                                    self.shutdown_triggered = True
                                    if self.was_downloading_background:
                                        logger.info("Téléchargements et seeds terminés. Arrêt du serveur avec notification.")
                                        send_windows_notification("Torrent Studio Pro", "Téléchargements et partages terminés ! Le serveur s'est arrêté.")
                                    else:
                                        logger.info("Page fermée et aucun seed/téléchargement actif. Arrêt du serveur.")
                                    self.shutdown()
                                    threading.Thread(target=lambda: (time.sleep(1.2), os._exit(0)), daemon=True).start()
                            elif behavior == "stop_immediately":
                                self.shutdown_triggered = True
                                logger.info("Page fermée (mode arrêt immédiat après confirmation). Arrêt du serveur.")
                                self.shutdown()
                                threading.Thread(target=lambda: (time.sleep(1.2), os._exit(0)), daemon=True).start()

                # 4. Sauvegarde automatique toutes les 8 secondes
                if time.time() - last_save > 8:
                    self.save_state()
                    last_save = time.time()

            except Exception as e:
                logger.error(f"Erreur dans _monitor_loop: {e}")

            time.sleep(0.5)

    def shutdown(self):
        self.running = False
        self.save_state()
        logger.info("TorrentManager arrêté proprement.")
