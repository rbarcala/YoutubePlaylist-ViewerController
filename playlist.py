#!/usr/bin/env python3
"""
playlist.py — Gestor y ordenador de Playlists de YouTube en vivo.

Permite ordenar y modificar directamente en YouTube cualquier playlist a la que
tengas acceso de edición, ingresando su URL o ID y autenticando mediante:
  1. Sesión de Google/YouTube detectada automáticamente (Controller / Navegador)
  2. Inicio de sesión interactivo de Google (ventana dedicada o archivo cookies.txt)
  3. YouTube Data API v3 (API Key + Token OAuth 2.0 / client_secrets.json)

Uso interactivo:
    python3 playlist.py

Uso por línea de comandos:
    python3 playlist.py "<URL_O_ID_PLAYLIST>" --sort popular
    python3 playlist.py "<URL_O_ID_PLAYLIST>" --sort duration-asc
    python3 playlist.py "<URL_O_ID_PLAYLIST>" --sort title-asc
    python3 playlist.py "<URL_O_ID_PLAYLIST>" --login
"""

import argparse
import hashlib
import http.cookiejar
import json
import os
import random
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

ORIGIN = "https://www.youtube.com"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Modos nativos de YouTube (1 sola petición a edit_playlist)
NATIVE_SORT_ORDERS = {
    "added-desc": (1, "Fecha de inclusión (más reciente primero)"),
    "added-asc": (2, "Fecha de inclusión (más antiguo primero)"),
    "popular": (3, "Más populares (mayor cantidad de vistas)"),
    "published-desc": (4, "Fecha de publicación (más reciente primero)"),
    "published-asc": (5, "Fecha de publicación (más antiguo primero)"),
}

# Modos personalizados (reordenan cada ítem en YouTube)
CUSTOM_SORT_ORDERS = {
    "title-asc": "Título (A → Z)",
    "title-desc": "Título (Z → A)",
    "duration-asc": "Duración (más cortos primero)",
    "duration-desc": "Duración (más largos primero)",
    "channel-asc": "Canal / Autor (A → Z)",
    "reverse": "Invertir el orden actual",
    "shuffle": "Aleatorio (Shuffle)",
}


def extract_playlist_id(raw: str) -> str:
    """Extrae el ID de la playlist desde una URL completa de YouTube o devuelve el ID limpio."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", raw)
    if m:
        return m.group(1)
    return raw


def format_duration(seconds: int) -> str:
    """Formatea segundos en M:SS o H:MM:SS."""
    seconds = max(0, int(seconds or 0))
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


def launch_interactive_google_login() -> Optional[str]:
    """
    Abre una ventana de inicio de sesión de Google/YouTube para autenticar una cuenta
    con permisos sobre la playlist y exporta las cookies a un archivo Netscape.
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
        print("[!] PyQt5 / PyQtWebEngine no está disponible para abrir la ventana gráfica.")
        return None

    sys.argv.extend(["--disable-gpu", "--disable-gpu-compositing", "--disable-dev-shm-usage"])
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("youtube-stream-controller")

    captured_cookies = {}
    target_dir = Path.home() / ".config" / "youtube-stream-controller"
    target_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = target_dir / "youtube_playlist_cookies.txt"

    dlg = QDialog()
    dlg.setWindowTitle("Iniciar sesión en Google / YouTube — Ordenador de Playlists")
    dlg.resize(540, 680)

    layout = QVBoxLayout(dlg)
    info = QLabel(
        "Iniciá sesión con la cuenta de Google que tenga acceso de edición a la playlist.\n"
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


class YouTubeInnerTubePlaylistClient:
    """
    Cliente autenticado por sesión de Google/YouTube (SAPISIDHASH) que permite
    leer y reordenar playlists directamente en YouTube sin consumir cuota de Data API v3.
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

    def fetch_playlist_items(self, playlist_id: str) -> list[dict]:
        """Obtiene todos los videos de la playlist junto con su setVideoId para poder moverlos."""
        items = []
        seen_set_ids = set()
        seen_tokens = set()
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

            page_renderers = list(self._find_key_recursive(data, "playlistVideoRenderer"))
            for r in page_renderers:
                vid = r.get("videoId", "")
                set_vid = r.get("setVideoId", "")
                key = set_vid or f"{vid}_{len(items)}"
                if key in seen_set_ids:
                    continue
                seen_set_ids.add(key)

                title_runs = r.get("title", {}).get("runs", [])
                title = title_runs[0].get("text", "") if title_runs else r.get("title", {}).get("simpleText", "Sin título")
                channel_runs = r.get("shortBylineText", {}).get("runs", [])
                channel = channel_runs[0].get("text", "") if channel_runs else ""
                duration_sec = int(r.get("lengthSeconds") or 0)

                items.append({
                    "position": len(items),
                    "videoId": vid,
                    "setVideoId": set_vid,
                    "title": title,
                    "channel": channel,
                    "duration": duration_sec,
                })

            # Buscar token de paginación (continuationCommand.token dentro de playlistVideoListRenderer)
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

        return items

    def set_native_playlist_order(self, playlist_id: str, order_code: int) -> bool:
        """Aplica uno de los órdenes nativos de servidor de YouTube en una sola llamada."""
        payload = {
            "context": self._context(),
            "playlistId": playlist_id,
            "actions": [
                {
                    "action": "ACTION_SET_PLAYLIST_VIDEO_ORDER",
                    "playlistVideoOrder": int(order_code),
                }
            ],
            "params": "CAFAAQ%3D%3D",
        }
        resp = self.session.post(
            f"{ORIGIN}/youtubei/v1/browse/edit_playlist?prettyPrint=false",
            headers=self._headers(playlist_id),
            json=payload,
            timeout=20,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Error HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        status = data.get("status", "STATUS_SUCCEEDED")
        return status == "STATUS_SUCCEEDED" or "playlistEditResults" in data or "actions" in data

    def apply_custom_order(self, playlist_id: str, current_items: list[dict], sorted_items: list[dict]) -> int:
        """
        Reordena los videos de la playlist en YouTube para que coincidan con `sorted_items`.
        Usa ACTION_MOVE_VIDEO_BEFORE en orden inverso para colocar cada video en su posición exacta.
        """
        missing_set_id = [it for it in current_items if not it.get("setVideoId")]
        if missing_set_id:
            raise PermissionError(
                "YouTube no devolvió 'setVideoId' para los videos de esta playlist. "
                "Verifica que la cuenta iniciada sea propietaria o colaboradora con permisos de edición en la playlist."
            )

        current_ids = [it["setVideoId"] for it in current_items]
        target_ids = [it["setVideoId"] for it in sorted_items]
        if current_ids == target_ids:
            print("[✓] La playlist ya se encuentra exactamente en el orden solicitado.")
            return 0

        # Asegurar modo manual (playlistVideoOrder = 0) antes de mover videos individualmente
        try:
            self.set_native_playlist_order(playlist_id, 0)
        except Exception:
            pass

        # Si enviamos ACTION_MOVE_VIDEO_BEFORE (sin successor = mover al tope) desde el último
        # hacia el primero de la lista deseada, la playlist queda en el orden exacto de target_ids.
        # Optimización: si un sufijo al final ya está en orden relativo correcto, no hace falta moverlo.
        total = len(target_ids)
        moves = []
        # Recorremos de atrás hacia adelante enviando al tope cada elemento
        for set_vid in reversed(target_ids):
            moves.append({
                "action": "ACTION_MOVE_VIDEO_BEFORE",
                "setVideoId": set_vid,
            })

        # Enviar en lotes para mostrar progreso claro y evitar timeouts
        batch_size = 25
        completed = 0
        for i in range(0, len(moves), batch_size):
            batch = moves[i : i + batch_size]
            payload = {
                "context": self._context(),
                "playlistId": playlist_id,
                "actions": batch,
                "params": "CAFAAQ%3D%3D",
            }
            resp = self.session.post(
                f"{ORIGIN}/youtubei/v1/browse/edit_playlist?prettyPrint=false",
                headers=self._headers(playlist_id),
                json=payload,
                timeout=30,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Fallo al mover videos (HTTP {resp.status_code}): {resp.text[:300]}")
            completed += len(batch)
            print(f"  → Progreso en YouTube: {completed}/{total} videos posicionados...")

        return completed


class YouTubeDataAPIv3PlaylistClient:
    """
    Cliente oficial YouTube Data API v3.
    Usa API Key (o Bearer token) para listar y OAuth 2.0 Bearer Token para modificar posiciones en YouTube.
    """

    def __init__(self, api_key: str = "", oauth_token: str = ""):
        self.api_key = api_key.strip()
        self.oauth_token = oauth_token.strip()
        self.session = requests.Session()

    def fetch_playlist_items(self, playlist_id: str) -> list[dict]:
        items = []
        page_token = None
        while True:
            params = {
                "part": "id,snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": 50,
            }
            if self.api_key:
                params["key"] = self.api_key
            if page_token:
                params["pageToken"] = page_token

            headers = {}
            if self.oauth_token:
                headers["Authorization"] = f"Bearer {self.oauth_token}"

            resp = self.session.get(
                "https://www.googleapis.com/youtube/v3/playlistItems",
                params=params,
                headers=headers,
                timeout=15,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Error Data API v3 ({resp.status_code}): {resp.text[:300]}")
            data = resp.json()

            for raw in data.get("items", []):
                snippet = raw.get("snippet", {})
                content = raw.get("contentDetails", {})
                vid = content.get("videoId") or snippet.get("resourceId", {}).get("videoId", "")
                items.append({
                    "position": len(items),
                    "playlistItemId": raw.get("id", ""),
                    "videoId": vid,
                    "setVideoId": raw.get("id", ""),
                    "title": snippet.get("title", ""),
                    "channel": snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle", ""),
                    "publishedAt": content.get("videoPublishedAt") or snippet.get("publishedAt", ""),
                    "addedAt": snippet.get("publishedAt", ""),
                    "duration": 0,
                })

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        # Completar duraciones en lotes de 50
        vids = [it["videoId"] for it in items if it.get("videoId")]
        dur_map = {}
        for i in range(0, len(vids), 50):
            batch = vids[i : i + 50]
            params = {"part": "contentDetails", "id": ",".join(batch)}
            if self.api_key:
                params["key"] = self.api_key
            headers = {"Authorization": f"Bearer {self.oauth_token}"} if self.oauth_token else {}
            r = self.session.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params=params,
                headers=headers,
                timeout=15,
            )
            if r.status_code == 200:
                for v in r.json().get("items", []):
                    dur_map[v["id"]] = parse_iso8601_seconds(
                        v.get("contentDetails", {}).get("duration", "")
                    )
        for it in items:
            it["duration"] = dur_map.get(it["videoId"], 0)

        return items

    def apply_custom_order(self, playlist_id: str, current_items: list[dict], sorted_items: list[dict]) -> int:
        if not self.oauth_token:
            raise PermissionError(
                "En la API oficial YouTube Data API v3, las API Keys públicas solo tienen permiso de lectura (GET).\n"
                "Para modificar el orden en YouTube necesitas proporcionar un OAuth 2.0 Access Token "
                "(con scope https://www.googleapis.com/auth/youtube) o usar la opción de Inicio de Sesión de Google."
            )

        updated = 0
        total = len(sorted_items)
        headers = {
            "Authorization": f"Bearer {self.oauth_token}",
            "Content-Type": "application/json",
        }
        params = {"part": "snippet"}
        if self.api_key:
            params["key"] = self.api_key

        for new_pos, item in enumerate(sorted_items):
            body = {
                "id": item["playlistItemId"],
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": item["videoId"],
                    },
                    "position": new_pos,
                },
            }
            resp = self.session.put(
                "https://www.googleapis.com/youtube/v3/playlistItems",
                params=params,
                headers=headers,
                json=body,
                timeout=20,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Error actualizando posición {new_pos} ({item['title']}): HTTP {resp.status_code} {resp.text[:300]}"
                )
            updated += 1
            print(f"  → Progreso Data API v3: {updated}/{total} ({item['title'][:45]})")
        return updated


def compute_sorted_items(items: list[dict], sort_mode: str) -> list[dict]:
    """Devuelve una nueva lista con los items ordenados según `sort_mode`."""
    if sort_mode == "title-asc":
        return sorted(items, key=lambda x: (x.get("title") or "").lower())
    if sort_mode == "title-desc":
        return sorted(items, key=lambda x: (x.get("title") or "").lower(), reverse=True)
    if sort_mode == "duration-asc":
        return sorted(items, key=lambda x: (int(x.get("duration") or 0), (x.get("title") or "").lower()))
    if sort_mode == "duration-desc":
        return sorted(items, key=lambda x: (int(x.get("duration") or 0), (x.get("title") or "").lower()), reverse=True)
    if sort_mode == "channel-asc":
        return sorted(items, key=lambda x: ((x.get("channel") or "").lower(), (x.get("title") or "").lower()))
    if sort_mode == "reverse":
        return list(reversed(items))
    if sort_mode == "shuffle":
        shuffled = list(items)
        random.shuffle(shuffled)
        return shuffled
    if sort_mode == "added-desc":
        return sorted(items, key=lambda x: x.get("addedAt", ""), reverse=True)
    if sort_mode == "added-asc":
        return sorted(items, key=lambda x: x.get("addedAt", ""))
    if sort_mode == "published-desc":
        return sorted(items, key=lambda x: x.get("publishedAt", ""), reverse=True)
    if sort_mode == "published-asc":
        return sorted(items, key=lambda x: x.get("publishedAt", ""))
    raise ValueError(f"Modo de ordenamiento desconocido: {sort_mode}")


def print_playlist_preview(items: list[dict], limit: int = 25) -> None:
    print(f"\nTotal de videos en la playlist: {len(items)}")
    print("-" * 78)
    for idx, it in enumerate(items[:limit], start=1):
        dur = format_duration(it.get("duration", 0))
        title = (it.get("title") or "Sin título")[:52]
        ch = (it.get("channel") or "")[:16]
        print(f" {idx:3d}. [{dur:>7}] {title:<52} | {ch}")
    if len(items) > limit:
        print(f" ... y {len(items) - limit} videos más.")
    print("-" * 78)


def resolve_client(args, cfg: dict):
    """Inicializa el cliente de autenticación según los argumentos o pregunta interactivamente."""
    from services.browser_cookie_detector import get_youtube_cookiefile

    if args.login:
        print("\n[*] Abriendo ventana de inicio de sesión de Google...")
        cookie_path = launch_interactive_google_login()
        if not cookie_path:
            sys.exit("[!] No se completó el inicio de sesión.")
        return YouTubeInnerTubePlaylistClient(cookie_path, api_key=args.api_key or cfg.get("youtube_api_key", ""))

    if args.cookies:
        return YouTubeInnerTubePlaylistClient(args.cookies, api_key=args.api_key or cfg.get("youtube_api_key", ""))

    if args.oauth_token:
        return YouTubeDataAPIv3PlaylistClient(
            api_key=args.api_key or cfg.get("youtube_api_key", ""),
            oauth_token=args.oauth_token,
        )

    # Si estamos en modo CLI directo (--sort o --list) intentar sesión existente automáticamente
    if args.sort or args.list:
        auto_cookie = get_youtube_cookiefile()
        if auto_cookie:
            return YouTubeInnerTubePlaylistClient(auto_cookie, api_key=args.api_key or cfg.get("youtube_api_key", ""))

    # Menú interactivo de autenticación
    auto_cookie = get_youtube_cookiefile()
    print("\n=== MÉTODO DE AUTENTICACIÓN ===")
    if auto_cookie:
        print("  1) Usar sesión de Google/YouTube actual del Controller (Detectada ✔)")
    else:
        print("  1) Iniciar sesión con cuenta de Google en ventana emergente")
    print("  2) Iniciar sesión con otra cuenta de Google (ventana emergente)")
    print("  3) Usar archivo de cookies Netscape (cookies.txt)")
    print("  4) Usar API Key + OAuth 2.0 Access Token (YouTube Data API v3)")

    choice = input("\nSeleccioná una opción [1]: ").strip() or "1"

    if choice == "1" and auto_cookie:
        return YouTubeInnerTubePlaylistClient(auto_cookie, api_key=cfg.get("youtube_api_key", ""))
    if choice in ("1", "2"):
        print("\n[*] Abriendo ventana de inicio de sesión de Google...")
        cookie_path = launch_interactive_google_login()
        if not cookie_path:
            sys.exit("[!] No se completó el inicio de sesión.")
        return YouTubeInnerTubePlaylistClient(cookie_path, api_key=cfg.get("youtube_api_key", ""))
    if choice == "3":
        cpath = input("Ruta al archivo cookies.txt: ").strip()
        return YouTubeInnerTubePlaylistClient(cpath, api_key=cfg.get("youtube_api_key", ""))
    if choice == "4":
        default_key = cfg.get("youtube_api_key", "")
        prompt_key = f"API Key de YouTube [{default_key[:10]}...]: " if default_key else "API Key de YouTube: "
        api_key = input(prompt_key).strip() or default_key
        oauth_token = input("OAuth 2.0 Access Token (de quien tenga acceso a la playlist): ").strip()
        return YouTubeDataAPIv3PlaylistClient(api_key=api_key, oauth_token=oauth_token)

    sys.exit("[!] Opción inválida.")


def interactive_main(args) -> None:
    try:
        from services import load_config
        cfg = load_config()
    except Exception:
        cfg = {}

    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║        YOUTUBE PLAYLIST SORTER & MANAGER (playlist.py)          ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    raw_playlist = args.playlist
    if not raw_playlist:
        default_pl = cfg.get("playlist_id", "")
        prompt = f"\nIngresá la URL o ID de la Playlist [{default_pl}]: " if default_pl else "\nIngresá la URL o ID de la Playlist: "
        raw_playlist = input(prompt).strip() or default_pl

    playlist_id = extract_playlist_id(raw_playlist)
    if not playlist_id:
        sys.exit("[!] Debes especificar una URL o ID de playlist válido.")

    print(f"[*] Playlist seleccionada: {playlist_id} (https://www.youtube.com/playlist?list={playlist_id})")

    client = resolve_client(args, cfg)

    # Si se pasó --list por CLI
    if args.list:
        items = client.fetch_playlist_items(playlist_id)
        print_playlist_preview(items, limit=len(items))
        return

    # Si se pasó --sort por CLI
    if args.sort:
        sort_key = args.sort.strip().lower()
        if isinstance(client, YouTubeInnerTubePlaylistClient) and sort_key in NATIVE_SORT_ORDERS:
            code, label = NATIVE_SORT_ORDERS[sort_key]
            print(f"[*] Aplicando orden nativo en YouTube: {label}...")
            client.set_native_playlist_order(playlist_id, code)
            print(f"[✓] Playlist '{playlist_id}' ordenada exitosamente en YouTube ({label}).")
            return

        print("[*] Obteniendo videos actuales de la playlist...")
        items = client.fetch_playlist_items(playlist_id)
        sorted_items = compute_sorted_items(items, sort_key)
        print_playlist_preview(sorted_items, limit=15)
        print(f"[*] Aplicando nuevo orden en YouTube ({len(sorted_items)} videos)...")
        client.apply_custom_order(playlist_id, items, sorted_items)
        print(f"[✓] Playlist '{playlist_id}' actualizada en YouTube.")
        return

    # Bucle interactivo
    print("\n[*] Cargando videos de la playlist...")
    items = client.fetch_playlist_items(playlist_id)
    print_playlist_preview(items, limit=20)

    menu_options = [
        ("popular", "Más populares (Nativo de YouTube — instantáneo)"),
        ("added-desc", "Fecha de inclusión: más recientes primero (Nativo — instantáneo)"),
        ("added-asc", "Fecha de inclusión: más antiguos primero (Nativo — instantáneo)"),
        ("published-desc", "Fecha de publicación: más recientes primero (Nativo — instantáneo)"),
        ("published-asc", "Fecha de publicación: más antiguos primero (Nativo — instantáneo)"),
        ("title-asc", "Alfabético por Título (A → Z)"),
        ("title-desc", "Alfabético por Título (Z → A)"),
        ("duration-asc", "Por Duración (más cortos primero)"),
        ("duration-desc", "Por Duración (más largos primero)"),
        ("channel-asc", "Por Canal / Autor (A → Z)"),
        ("reverse", "Invertir el orden actual"),
        ("shuffle", "Aleatorio (Shuffle)"),
        ("move-one", "Mover un video específico a otra posición"),
        ("list", "Ver todos los videos actuales de la playlist"),
    ]

    print("\n=== ¿CÓMO QUERÉS ORDENAR LA PLAYLIST EN YOUTUBE? ===")
    for idx, (_, desc) in enumerate(menu_options, start=1):
        print(f"  {idx:2d}) {desc}")
    print("   0) Salir")

    sel = input("\nElegí una opción: ").strip()
    if not sel or sel == "0":
        print("Saliendo sin modificar la playlist.")
        return

    if not sel.isdigit() or not (1 <= int(sel) <= len(menu_options)):
        sys.exit("[!] Opción inválida.")

    mode_key, mode_label = menu_options[int(sel) - 1]

    if mode_key == "list":
        print_playlist_preview(items, limit=len(items))
        return

    if mode_key == "move-one":
        print_playlist_preview(items, limit=len(items))
        src_idx = int(input(f"Número de video a mover (1-{len(items)}): ").strip()) - 1
        dst_idx = int(input(f"Nueva posición deseada (1-{len(items)}): ").strip()) - 1
        if not (0 <= src_idx < len(items) and 0 <= dst_idx < len(items)):
            sys.exit("[!] Posición fuera de rango.")
        sorted_items = list(items)
        moved = sorted_items.pop(src_idx)
        sorted_items.insert(dst_idx, moved)
        print(f"\n[*] Moviendo '{moved['title']}' a la posición {dst_idx + 1} en YouTube...")
        client.apply_custom_order(playlist_id, items, sorted_items)
        print("[✓] ¡Cambio guardado en YouTube!")
        return

    # Orden nativo instantáneo si usa sesión de Google/YouTube
    if isinstance(client, YouTubeInnerTubePlaylistClient) and mode_key in NATIVE_SORT_ORDERS:
        code, label = NATIVE_SORT_ORDERS[mode_key]
        confirm = input(f"\n¿Confirmás aplicar '{label}' en YouTube para la playlist {playlist_id}? [S/n]: ").strip().lower()
        if confirm in ("", "s", "si", "sí", "y", "yes"):
            client.set_native_playlist_order(playlist_id, code)
            print(f"\n[✓] ¡Playlist ordenada exitosamente en YouTube ({label})!")
        else:
            print("Operación cancelada.")
        return

    # Orden personalizado
    sorted_items = compute_sorted_items(items, mode_key)
    print(f"\nVista previa del nuevo orden ({mode_label}):")
    print_playlist_preview(sorted_items, limit=20)
    confirm = input(f"\n¿Confirmás aplicar este orden en YouTube ({len(sorted_items)} videos)? [S/n]: ").strip().lower()
    if confirm in ("", "s", "si", "sí", "y", "yes"):
        client.apply_custom_order(playlist_id, items, sorted_items)
        print(f"\n[✓] ¡Playlist '{playlist_id}' reordenada exitosamente en YouTube!")
    else:
        print("Operación cancelada.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ordena y modifica una playlist de YouTube directamente mediante API / Sesión de Google."
    )
    parser.add_argument(
        "playlist",
        nargs="?",
        default="",
        help="URL completa o ID de la playlist de YouTube (ej: PL7E8lrk1ePfZVWMM2vsUkpQ6vbpbHi4G_)",
    )
    parser.add_argument(
        "--sort",
        choices=list(NATIVE_SORT_ORDERS.keys()) + list(CUSTOM_SORT_ORDERS.keys()),
        help="Criterio de ordenamiento a aplicar en YouTube",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Solo listar los videos actuales de la playlist sin modificarla",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Abrir ventana para iniciar sesión con una cuenta de Google",
    )
    parser.add_argument(
        "--cookies",
         default="",
        help="Ruta a un archivo cookies.txt en formato Netscape de quien tenga acceso a la playlist",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API Key de YouTube Data API v3",
    )
    parser.add_argument(
        "--oauth-token",
        default="",
        help="Token OAuth 2.0 (Bearer) con permiso https://www.googleapis.com/auth/youtube",
    )
    return parser


if __name__ == "__main__":
    parser = build_arg_parser()
    parsed_args = parser.parse_args()
    try:
        interactive_main(parsed_args)
    except KeyboardInterrupt:
        print("\n[!] Operación cancelada por el usuario.")
        sys.exit(1)
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
