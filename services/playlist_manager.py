"""
services/playlist_manager.py — Gestor modular de Playlists de YouTube.

Permite administrar una playlist de YouTube directamente desde el Controller:
- Mantiene intacto el orden manual que ya tenía la playlist en YouTube.
- Identifica cuáles son los videos nuevos / agregados por el usuario (con permisos de borrado y administración, especialmente al final de la playlist).
- Permite agregar nuevos videos, borrar videos propios y cambiarles manualmente su posición exacta en YouTube en 1 sola llamada (ACTION_MOVE_VIDEO_BEFORE / ACTION_REMOVE_VIDEO / ACTION_ADD_VIDEO).
- Soporta inicio de sesión de Google (cookies de sesión SAPISIDHASH o ventana interactiva) y YouTube Data API v3 (API Key + OAuth 2.0 Bearer Token).
"""

import hashlib
import http.cookiejar
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests

from services.browser_cookie_detector import get_youtube_cookiefile

logger = logging.getLogger("playlist_manager")

ORIGIN = "https://www.youtube.com"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

CONFIG_DIR = Path.home() / ".config" / "youtube-stream-controller"
PLAYLIST_COOKIE_FILE = CONFIG_DIR / "youtube_playlist_cookies.txt"


def extract_playlist_id(raw: str) -> str:
    """Extrae el ID limpio de una playlist desde una URL de YouTube o un ID directo."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", raw)
    if m:
        return m.group(1)
    return raw


def extract_video_id(raw: str) -> str:
    """Extrae el ID de 11 caracteres de un video de YouTube desde cualquier URL o ID directo."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if re.match(r"^[A-Za-z0-9_-]{11}$", raw):
        return raw
    patterns = [
        r"[?&]v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
        r"youtube\.com/live/([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, raw)
        if m:
            return m.group(1)
    return ""


def format_duration(seconds: int) -> str:
    """Formatea segundos en M:SS o H:MM:SS."""
    seconds = max(0, int(seconds or 0))
    if seconds == 0:
        return ""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def parse_iso8601_seconds(duration_str: str) -> int:
    """Convierte PT#H#M#S de YouTube Data API v3 a segundos."""
    if not duration_str:
        return 0
    m = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", duration_str)
    if not m:
        return 0
    h, mins, secs = m.groups()
    return (int(h or 0) * 3600) + (int(mins or 0) * 60) + int(secs or 0)


def _run_qt_google_login_dialog() -> Optional[str]:
    """
    Ejecuta la ventana gráfica de inicio de sesión de Google/YouTube y guarda
    las cookies de sesión en PLAYLIST_COOKIE_FILE.
    """
    try:
        from PyQt5.QtCore import QUrl, QTimer
        from PyQt5.QtWidgets import (
            QApplication,
            QDialog,
            QVBoxLayout,
            QHBoxLayout,
            QLabel,
            QPushButton,
        )
        from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile
    except ImportError:
        logger.warning("PyQt5 / PyQtWebEngine no disponible para login interactivo.")
        return None

    sys.argv.extend(["--disable-gpu", "--disable-gpu-compositing", "--disable-dev-shm-usage"])
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("youtube-stream-controller")

    captured_cookies = {}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cookie_path = PLAYLIST_COOKIE_FILE

    dlg = QDialog()
    dlg.setWindowTitle("Iniciar sesión en Google / YouTube — Gestor de Playlist")
    dlg.resize(540, 680)

    layout = QVBoxLayout(dlg)
    info = QLabel(
        "Iniciá sesión con la cuenta de Google que tenga acceso a la playlist.\n"
        "La ventana se cerrará automáticamente al detectar la sesión de YouTube."
    )
    info.setWordWrap(True)
    layout.addWidget(info)

    profile = QWebEngineProfile("youtube-playlist-editor", dlg)
    view = QWebEngineView(dlg)
    page = QWebEnginePage(profile, view)
    view.setPage(page)
    layout.addWidget(view, stretch=1)

    btn_row = QHBoxLayout()
    btn_done = QPushButton("Ya inicié sesión / Continuar")
    btn_cancel = QPushButton("Cancelar")
    btn_done.clicked.connect(dlg.accept)
    btn_cancel.clicked.connect(dlg.reject)
    btn_row.addStretch()
    btn_row.addWidget(btn_done)
    btn_row.addWidget(btn_cancel)
    layout.addLayout(btn_row)

    def _on_cookie_added(cookie):
        try:
            domain = cookie.domain()
            name = bytes(cookie.name()).decode("utf-8", errors="ignore")
            value = bytes(cookie.value()).decode("utf-8", errors="ignore")
            if not domain or not name or not value:
                return
            if "youtube.com" in domain or "google.com" in domain:
                path = cookie.path() or "/"
                secure = cookie.isSecure()
                exp_dt = cookie.expirationDate()
                expires = int(exp_dt.toSecsSinceEpoch()) if exp_dt.isValid() else 0
                captured_cookies[(domain, path, name)] = (domain, path, secure, expires, name, value)

                yt_names = {
                    nm for (dom, _, nm) in captured_cookies.keys() if "youtube.com" in dom
                }
                if {"SAPISID", "SID"} <= yt_names or "__Secure-3PAPISID" in yt_names:
                    lines = ["# Netscape HTTP Cookie File"]
                    for dom, pth, sec, exp, nm, val in captured_cookies.values():
                        sub = "TRUE" if dom.startswith(".") else "FALSE"
                        sec_s = "TRUE" if sec else "FALSE"
                        lines.append(f"{dom}\t{sub}\t{pth}\t{sec_s}\t{exp}\t{nm}\t{val}")
                    cookie_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    os.chmod(cookie_path, 0o600)
        except Exception:
            pass

    profile.cookieStore().cookieAdded.connect(_on_cookie_added)
    view.load(
        QUrl("https://accounts.google.com/ServiceLogin?service=youtube&continue=https://www.youtube.com/")
    )

    def _check_auto_close():
        if cookie_path.is_file() and cookie_path.stat().st_size > 200:
            url_str = view.url().toString()
            if "youtube.com" in url_str and "accounts.google.com" not in url_str:
                dlg.accept()

    timer = QTimer(dlg)
    timer.timeout.connect(_check_auto_close)
    timer.start(800)

    if dlg.exec_() == QDialog.Accepted and cookie_path.is_file():
        return str(cookie_path)
    return None


def launch_interactive_google_login() -> Optional[str]:
    """
    Lanza la ventana de inicio de sesión de Google en un subproceso dedicado
    para que funcione de forma segura tanto desde hilos de Flask como desde CLI.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "services.playlist_manager", "--login-dialog"],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode == 0 and PLAYLIST_COOKIE_FILE.is_file():
            return str(PLAYLIST_COOKIE_FILE)
    except Exception as e:
        logger.warning(f"Fallo al abrir subproceso de login: {e}")
    return None


class YouTubeInnerTubePlaylistClient:
    """
    Cliente autenticado por sesión de Google/YouTube (SAPISIDHASH) que permite
    leer, agregar, borrar y mover videos en una playlist de YouTube manteniendo
    su orden manual exacto.
    """

    def __init__(self, cookie_file: str, api_key: str = ""):
        self.cookie_file = cookie_file
        self.api_key = api_key
        self.cj = http.cookiejar.MozillaCookieJar(cookie_file)
        self.cj.load(ignore_discard=True, ignore_expires=True)
        self.sapisid = self._find_sapisid()
        if not self.sapisid:
            raise ValueError(
                f"El archivo de cookies '{cookie_file}' no contiene una sesión activa de YouTube (SAPISID)."
            )
        self.session = requests.Session()
        self.session.cookies = self.cj

    def _find_sapisid(self) -> str:
        for c in self.cj:
            if "youtube.com" in c.domain and c.name in ("SAPISID", "__Secure-3PAPISID") and c.value:
                return c.value
        return ""

    def _headers(self, playlist_id: str) -> dict:
        ts = int(time.time())
        raw = f"{ts} {self.sapisid} {ORIGIN}"
        sapisidhash = f"{ts}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()}"
        return {
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": f"https://www.youtube.com/playlist?list={playlist_id}",
            "Authorization": f"SAPISIDHASH {sapisidhash} SAPISID1PHASH {sapisidhash} SAPISID3PHASH {sapisidhash}",
            "X-Origin": ORIGIN,
            "X-Goog-AuthUser": "0",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _context() -> dict:
        return {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20250312.04.00",
                "hl": "es",
                "gl": "AR",
            }
        }

    @staticmethod
    def _find_key_recursive(obj, target_key: str):
        if isinstance(obj, dict):
            if target_key in obj:
                yield obj[target_key]
            for v in obj.values():
                yield from YouTubeInnerTubePlaylistClient._find_key_recursive(v, target_key)
        elif isinstance(obj, list):
            for item in obj:
                yield from YouTubeInnerTubePlaylistClient._find_key_recursive(item, target_key)

    def fetch_playlist_details(self, playlist_id: str) -> dict:
        """
        Obtiene todos los videos de la playlist respetando el orden manual exacto de YouTube,
        identificando cuáles fueron agregados por el usuario actual (canDelete / canMove).
        """
        items = []
        seen_set_ids = set()
        seen_tokens = set()
        playlist_title = ""
        is_owner_editable = False
        can_reorder_playlist = False

        payload = {"context": self._context(), "browseId": f"VL{playlist_id}"}

        while True:
            resp = self.session.post(
                f"{ORIGIN}/youtubei/v1/browse?prettyPrint=false",
                headers=self._headers(playlist_id),
                json=payload,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

            if not playlist_title:
                for hdr in self._find_key_recursive(data, "playlistHeaderRenderer"):
                    playlist_title = hdr.get("title", {}).get("simpleText", "")
                    if playlist_title:
                        break
                if not playlist_title:
                    for meta in self._find_key_recursive(data, "playlistMetadataRenderer"):
                        playlist_title = meta.get("title", "")
                        if playlist_title:
                            break

            for plv in self._find_key_recursive(data, "playlistVideoListRenderer"):
                if plv.get("isEditable"):
                    is_owner_editable = True
                if plv.get("canReorder"):
                    can_reorder_playlist = True

            page_renderers = list(self._find_key_recursive(data, "playlistVideoRenderer"))
            for r in page_renderers:
                vid = r.get("videoId", "")
                set_vid = r.get("setVideoId", "")
                key = set_vid or f"{vid}_{len(items)}"
                if key in seen_set_ids:
                    continue
                seen_set_ids.add(key)

                title_runs = r.get("title", {}).get("runs", [])
                title = (
                    title_runs[0].get("text", "")
                    if title_runs
                    else r.get("title", {}).get("simpleText", "Sin título")
                )
                channel_runs = r.get("shortBylineText", {}).get("runs", [])
                channel = channel_runs[0].get("text", "") if channel_runs else ""
                duration_sec = int(r.get("lengthSeconds") or 0)

                # Verificar si este video tiene acción de borrado/movimiento habilitada para el usuario actual
                item_edit_actions = set()
                for pe in self._find_key_recursive(r.get("menu", {}), "playlistEditEndpoint"):
                    if pe.get("playlistId") == playlist_id:
                        for act in pe.get("actions", []):
                            if act.get("action"):
                                item_edit_actions.add(act["action"])

                can_delete = is_owner_editable or ("ACTION_REMOVE_VIDEO" in item_edit_actions)
                can_move = bool(set_vid) and (
                    is_owner_editable
                    or can_reorder_playlist
                    or ("ACTION_MOVE_VIDEO_BEFORE" in item_edit_actions)
                    or ("ACTION_MOVE_VIDEO_AFTER" in item_edit_actions)
                )

                pos = len(items)
                items.append({
                    "position": pos,
                    "index": pos + 1,
                    "videoId": vid,
                    "setVideoId": set_vid,
                    "title": title,
                    "channel": channel,
                    "duration": format_duration(duration_sec),
                    "durationSeconds": duration_sec,
                    "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg" if vid else "",
                    "canDelete": can_delete,
                    "canMove": can_move,
                })

            next_token = None
            for cc in self._find_key_recursive(data, "continuationCommand"):
                tok = cc.get("token")
                if tok and tok not in seen_tokens:
                    seen_tokens.add(tok)
                    next_token = tok
                    break

            if not next_token or not page_renderers:
                break
            payload = {"context": self._context(), "continuation": next_token}

        return {
            "playlistId": playlist_id,
            "title": playlist_title or playlist_id,
            "total": len(items),
            "isOwner": is_owner_editable,
            "canReorder": can_reorder_playlist,
            "editableCount": sum(1 for x in items if x["canDelete"]),
            "items": items,
        }

    def fetch_playlist_items(self, playlist_id: str) -> list[dict]:
        return self.fetch_playlist_details(playlist_id)["items"]

    def _edit_playlist(self, playlist_id: str, actions: list[dict]) -> dict:
        payload = {
            "context": self._context(),
            "playlistId": playlist_id,
            "actions": actions,
            "params": "CAFAAQ%3D%3D",
        }
        resp = self.session.post(
            f"{ORIGIN}/youtubei/v1/browse/edit_playlist?prettyPrint=false",
            headers=self._headers(playlist_id),
            json=payload,
            timeout=20,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Error HTTP {resp.status_code} en YouTube: {resp.text[:300]}")
        data = resp.json()
        status = data.get("status", "STATUS_SUCCEEDED")
        if status != "STATUS_SUCCEEDED" and "playlistEditResults" not in data and "actions" not in data:
            raise RuntimeError(f"YouTube rechazó la modificación de la playlist ({status}).")
        return data

    def add_video(self, playlist_id: str, video_id: str) -> dict:
        """Agrega un video al final de la playlist en YouTube."""
        vid = extract_video_id(video_id)
        if not vid:
            raise ValueError("URL o ID de video de YouTube inválido.")
        self._edit_playlist(
            playlist_id,
            [{"action": "ACTION_ADD_VIDEO", "addedVideoId": vid}],
        )
        return {"success": True, "videoId": vid}

    def remove_video(self, playlist_id: str, set_video_id: str, video_id: str = "") -> dict:
        """Elimina un video específico de la playlist en YouTube usando su setVideoId."""
        if not set_video_id:
            raise ValueError("Falta setVideoId para poder borrar el video de la playlist.")
        action = {
            "action": "ACTION_REMOVE_VIDEO",
            "setVideoId": set_video_id,
        }
        if video_id:
            action["removedVideoId"] = video_id
        self._edit_playlist(playlist_id, [action])
        return {"success": True, "setVideoId": set_video_id}

    def move_video(
        self,
        playlist_id: str,
        set_video_id: str,
        new_position: int,
        current_items: Optional[list[dict]] = None,
    ) -> dict:
        """
        Mueve un único video (`set_video_id`) a la posición manual `new_position` (0-indexada)
        en 1 sola petición a YouTube, manteniendo intacto el orden del resto de la playlist.
        """
        if not set_video_id:
            raise ValueError("Falta setVideoId para mover el video.")

        items = current_items if current_items is not None else self.fetch_playlist_items(playlist_id)
        remaining = [it for it in items if it.get("setVideoId") != set_video_id]
        if len(remaining) == len(items):
            raise ValueError("No se encontró el video indicado dentro de la playlist.")

        target_idx = max(0, min(int(new_position), len(remaining)))

        if target_idx < len(remaining):
            successor_set_id = remaining[target_idx]["setVideoId"]
            action = {
                "action": "ACTION_MOVE_VIDEO_BEFORE",
                "setVideoId": set_video_id,
                "movedSetVideoIdSuccessor": successor_set_id,
            }
        else:
            # En YouTube InnerTube, ACTION_MOVE_VIDEO_BEFORE sin movedSetVideoIdSuccessor mueve al final
            action = {
                "action": "ACTION_MOVE_VIDEO_BEFORE",
                "setVideoId": set_video_id,
            }

        self._edit_playlist(playlist_id, [action])
        return {
            "success": True,
            "setVideoId": set_video_id,
            "newPosition": target_idx,
            "newIndex": target_idx + 1,
        }


class YouTubePlaylistManager:
    """
    Servicio centralizado para gestionar la playlist de YouTube desde las rutas Flask
    del Controller o desde la interfaz de línea de comandos.
    """

    def __init__(self, load_config_fn=None, save_config_fn=None):
        self._load_config = load_config_fn
        self._save_config = save_config_fn
        self._cached_details = {}
        self._client = None
        self._client_cookie_path = ""
        self._client_cookie_mtime = 0.0

    def _get_config(self) -> dict:
        if callable(self._load_config):
            try:
                return self._load_config() or {}
            except Exception:
                return {}
        return {}

    def resolve_cookie_file(self, force_scan: bool = False) -> Optional[str]:
        """Devuelve la ruta al archivo de cookies de YouTube con sesión activa (SAPISID)."""
        if not force_scan and self._client_cookie_path and os.path.isfile(self._client_cookie_path):
            return self._client_cookie_path

        candidates = []
        if PLAYLIST_COOKIE_FILE.is_file():
            candidates.append(str(PLAYLIST_COOKIE_FILE))
        default_std = CONFIG_DIR / "youtube_cookies.txt"
        if default_std.is_file():
            candidates.append(str(default_std))

        for path in candidates:
            try:
                client = YouTubeInnerTubePlaylistClient(path)
                if client.sapisid:
                    self._client_cookie_path = path
                    return path
            except Exception:
                continue

        # Escanear navegadores si aún no hay archivo válido en disco
        scanned = get_youtube_cookiefile(force_refresh=True)
        if scanned:
            try:
                client = YouTubeInnerTubePlaylistClient(scanned)
                if client.sapisid:
                    self._client_cookie_path = scanned
                    return scanned
            except Exception:
                pass
        return None

    def get_auth_status(self) -> dict:
        cookie_file = self.resolve_cookie_file()
        cfg = self._get_config()
        has_api_key = bool(cfg.get("youtube_api_key"))
        return {
            "authenticated": bool(cookie_file),
            "cookieFile": os.path.basename(cookie_file) if cookie_file else "",
            "hasApiKey": has_api_key,
            "playlistId": cfg.get("playlist_id", ""),
        }

    def get_client(self, cookie_file: Optional[str] = None) -> YouTubeInnerTubePlaylistClient:
        cfile = cookie_file or self.resolve_cookie_file()
        if not cfile:
            raise PermissionError(
                "No se encontró una sesión activa de Google/YouTube. "
                "Haz clic en 'Iniciar sesión de Google' para vincular la cuenta con acceso a la playlist."
            )
        mtime = os.path.getmtime(cfile) if os.path.isfile(cfile) else 0.0
        if self._client and self._client_cookie_path == cfile and self._client_cookie_mtime == mtime:
            return self._client
        cfg = self._get_config()
        self._client = YouTubeInnerTubePlaylistClient(cfile, api_key=cfg.get("youtube_api_key", ""))
        self._client_cookie_path = cfile
        self._client_cookie_mtime = mtime
        return self._client

    def get_playlist(self, playlist_id: str = "", force_refresh: bool = True) -> dict:
        cfg = self._get_config()
        pid = extract_playlist_id(playlist_id or cfg.get("playlist_id", ""))
        if not pid:
            raise ValueError("No se especificó un ID o URL de playlist.")

        if not force_refresh and pid in self._cached_details:
            return self._cached_details[pid]

        client = self.get_client()
        details = client.fetch_playlist_details(pid)
        self._cached_details[pid] = details
        return details

    @staticmethod
    def _reindex_details(details: dict) -> dict:
        items = details.get("items", [])
        for idx, it in enumerate(items):
            it["position"] = idx
            it["index"] = idx + 1
        details["total"] = len(items)
        details["editableCount"] = sum(1 for x in items if x.get("canDelete"))
        return details

    def add_video(self, playlist_id: str, video_url_or_id: str) -> dict:
        cfg = self._get_config()
        pid = extract_playlist_id(playlist_id or cfg.get("playlist_id", ""))
        if not pid:
            raise ValueError("No se especificó un ID o URL de playlist.")

        client = self.get_client()
        res = client.add_video(pid, video_url_or_id)
        # Esperar brevemente a que la réplica de lectura de YouTube refleje el nuevo video y su setVideoId
        time.sleep(1.2)
        details = client.fetch_playlist_details(pid)
        self._cached_details[pid] = details
        return {**res, "playlist": details}

    def remove_video(self, playlist_id: str, set_video_id: str, video_id: str = "") -> dict:
        cfg = self._get_config()
        pid = extract_playlist_id(playlist_id or cfg.get("playlist_id", ""))
        if not pid:
            raise ValueError("No se especificó un ID o URL de playlist.")

        client = self.get_client()
        res = client.remove_video(pid, set_video_id, video_id=video_id)
        cached = self._cached_details.get(pid)
        if cached and cached.get("items"):
            cached["items"] = [it for it in cached["items"] if it.get("setVideoId") != set_video_id]
            details = self._reindex_details(cached)
        else:
            time.sleep(1.2)
            details = client.fetch_playlist_details(pid)
            self._cached_details[pid] = details
        return {**res, "playlist": details}

    def move_video(self, playlist_id: str, set_video_id: str, new_position: int) -> dict:
        cfg = self._get_config()
        pid = extract_playlist_id(playlist_id or cfg.get("playlist_id", ""))
        if not pid:
            raise ValueError("No se especificó un ID o URL de playlist.")

        client = self.get_client()
        cached = self._cached_details.get(pid)
        if not cached or not cached.get("items"):
            cached = client.fetch_playlist_details(pid)
            self._cached_details[pid] = cached

        current_items = cached["items"]
        res = client.move_video(pid, set_video_id, new_position, current_items=current_items)

        # Actualizar orden en memoria inmediatamente para evitar el desfase de réplica de lectura de YouTube
        moving_item = next((it for it in current_items if it.get("setVideoId") == set_video_id), None)
        if moving_item:
            remaining = [it for it in current_items if it.get("setVideoId") != set_video_id]
            target_idx = res["newPosition"]
            remaining.insert(target_idx, moving_item)
            cached["items"] = remaining
            self._reindex_details(cached)

        return {**res, "playlist": cached}


if __name__ == "__main__":
    if "--login-dialog" in sys.argv:
        res = _run_qt_google_login_dialog()
        sys.exit(0 if res else 1)
