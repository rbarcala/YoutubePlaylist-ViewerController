#!/usr/bin/env python3
"""
Servicio para detectar y extraer cookies de sesión de navegadores locales
(Firefox Snap/Nativo/Flatpak, Chrome, Chromium, Brave) para MyInstants y otros servicios.
"""

import os
import glob
import sqlite3
import shutil
import tempfile
import urllib.request
import urllib.parse
import re
import logging
import threading
import time

logger = logging.getLogger("cookie_detector")


def find_firefox_cookie_dbs() -> list[str]:
    """Encuentra bases de datos cookies.sqlite de perfiles de Firefox."""
    home = os.path.expanduser("~")
    patterns = [
        # Snap Firefox (Ubuntu default)
        os.path.join(home, "snap", "firefox", "common", ".mozilla", "firefox", "*", "cookies.sqlite"),
        os.path.join(home, "snap", "firefox", "current", ".mozilla", "firefox", "*", "cookies.sqlite"),
        # Firefox nativo (.deb / tar)
        os.path.join(home, ".mozilla", "firefox", "*", "cookies.sqlite"),
        # Flatpak Firefox
        os.path.join(home, ".var", "app", "org.mozilla.firefox", ".mozilla", "firefox", "*", "cookies.sqlite"),
    ]
    matches = []
    for pat in patterns:
        for f in glob.glob(pat):
            if os.path.isfile(f):
                matches.append(f)
    # Ordenar por fecha de modificación más reciente primero
    matches.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    return matches


def find_chromium_cookie_dbs() -> list[tuple[str, str]]:
    """Encuentra bases de datos Cookies de navegadores basados en Chromium."""
    home = os.path.expanduser("~")
    configs = [
        ("Google Chrome", os.path.join(home, ".config", "google-chrome", "*", "Cookies")),
        ("Chromium", os.path.join(home, ".config", "chromium", "*", "Cookies")),
        ("Brave", os.path.join(home, ".config", "BraveSoftware", "Brave-Browser", "*", "Cookies")),
        ("Snap Chromium", os.path.join(home, "snap", "chromium", "common", "chromium", "*", "Cookies")),
        ("Flatpak Chrome", os.path.join(home, ".var", "app", "com.google.Chrome", "config", "google-chrome", "*", "Cookies")),
    ]
    results = []
    for b_name, pat in configs:
        for f in glob.glob(pat):
            if os.path.isfile(f):
                results.append((b_name, f))
    results.sort(key=lambda item: os.path.getmtime(item[1]) if os.path.exists(item[1]) else 0, reverse=True)
    return results


def _read_firefox_cookies(cookie_file: str, host_filter: str) -> dict[str, str]:
    """Lee cookies de un archivo cookies.sqlite de Firefox de forma segura contra bloqueos."""
    cookies = {}
    tmp_dir = tempfile.mkdtemp(prefix="ff_cookies_")
    try:
        tmp_db = os.path.join(tmp_dir, "cookies.sqlite")
        shutil.copy2(cookie_file, tmp_db)
        # Copiar WAL / SHM si existen para reflejar escrituras recientes
        for ext in ("-wal", "-shm"):
            src_wal = cookie_file + ext
            if os.path.exists(src_wal):
                shutil.copy2(src_wal, tmp_db + ext)

        conn = sqlite3.connect(tmp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, value FROM moz_cookies WHERE host LIKE ?",
            (f"%{host_filter}%",)
        )
        for name, val in cursor.fetchall():
            cookies[name] = val
        conn.close()
    except Exception as e:
        logger.debug(f"[cookie_detector] Error leyendo {cookie_file}: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return cookies


def _read_chromium_cookies(cookie_file: str, host_filter: str) -> dict[str, str]:
    """Lee cookies en texto plano (si las hay) de Chromium."""
    cookies = {}
    tmp_dir = tempfile.mkdtemp(prefix="cr_cookies_")
    try:
        tmp_db = os.path.join(tmp_dir, "Cookies")
        shutil.copy2(cookie_file, tmp_db)
        for ext in ("-wal", "-shm"):
            src_wal = cookie_file + ext
            if os.path.exists(src_wal):
                shutil.copy2(src_wal, tmp_db + ext)

        conn = sqlite3.connect(tmp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, value FROM cookies WHERE host_key LIKE ?",
            (f"%{host_filter}%",)
        )
        for name, val in cursor.fetchall():
            if val:
                cookies[name] = val
        conn.close()
    except Exception as e:
        logger.debug(f"[cookie_detector] Error leyendo {cookie_file}: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return cookies


def verify_myinstants_session(sessionid: str, csrftoken: str = "") -> dict:
    """
    Verifica si una cookie sessionid es válida en MyInstants y obtiene el nombre de usuario asociado.
    """
    if not sessionid:
        return {"valid": False, "error": "No sessionid"}

    url = "https://www.myinstants.com/en/my_profile/"
    cookie_hdr = f"sessionid={sessionid}"
    if csrftoken:
        cookie_hdr += f"; csrftoken={csrftoken}"

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
        "Cookie": cookie_hdr,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        # Usar un opener que maneje redirecciones y capture la URL final
        with urllib.request.urlopen(req, timeout=8) as resp:
            final_url = resp.geturl()
            html = resp.read().decode("utf-8", errors="ignore")

            # Si nos redirigió a /profile/<usuario>/
            m = re.search(r'/profile/([^/\"\'\s]+)/', final_url)
            if m:
                username = m.group(1).strip()
                return {"valid": True, "username": username}

            # Buscar en el contenido HTML
            m2 = re.search(r'href=[\"\']/en/profile/([^/\"\'\s]+)/[\"\']', html)
            if m2:
                username = m2.group(1).strip()
                return {"valid": True, "username": username}

            # Si sigue en login o logout no presente
            if "/accounts/login/" in final_url or "accounts/login" in html:
                return {"valid": False, "error": "Sesión expirada o no autenticada"}

            # Verificar si contiene enlaces de usuario autenticado
            if "/accounts/logout/" in html:
                m3 = re.search(r'/profile/([^/\"\'\s]+)/', html)
                if m3:
                    return {"valid": True, "username": m3.group(1).strip()}
                return {"valid": True, "username": "usuario_vinculado"}

            return {"valid": False, "error": "No se pudo identificar usuario"}
    except Exception as e:
        logger.error(f"[cookie_detector] Error al verificar sesión en MyInstants: {e}")
        return {"valid": False, "error": str(e)}


def detect_myinstants_session() -> dict:
    """
    Escanea todos los navegadores disponibles en el sistema y busca una sesión activa de MyInstants.
    Retorna información de la sesión encontrada o {'found': False}.
    """
    # 1. Probar Firefox (Snap, Nativo, Flatpak)
    for ff_path in find_firefox_cookie_dbs():
        cookies = _read_firefox_cookies(ff_path, "myinstants")
        sess = cookies.get("sessionid", "").strip()
        csrf = cookies.get("csrftoken", "").strip()
        if sess:
            check = verify_myinstants_session(sess, csrf)
            if check.get("valid"):
                return {
                    "found": True,
                    "browser": "Firefox",
                    "username": check.get("username", ""),
                    "sessionid": sess,
                    "csrftoken": csrf,
                    "cookie_path": ff_path
                }

    # 2. Probar navegadores Chromium
    for b_name, cr_path in find_chromium_cookie_dbs():
        cookies = _read_chromium_cookies(cr_path, "myinstants")
        sess = cookies.get("sessionid", "").strip()
        csrf = cookies.get("csrftoken", "").strip()
        if sess:
            check = verify_myinstants_session(sess, csrf)
            if check.get("valid"):
                return {
                    "found": True,
                    "browser": b_name,
                    "username": check.get("username", ""),
                    "sessionid": sess,
                    "csrftoken": csrf,
                    "cookie_path": cr_path
                }

    return {"found": False}


class SessionLoginWatcher:
    """
    Vigila en segundo plano la aparición de una sesión de MyInstants
    mientras el usuario inicia sesión en su navegador.
    """
    def __init__(self, on_success_callback, poll_interval: float = 2.0, timeout: float = 180.0):
        self.on_success = on_success_callback
        self.poll_interval = poll_interval
        self.timeout = timeout
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run(self):
        start_t = time.time()
        logger.info("[cookie_detector] Iniciando watcher de sesión en segundo plano...")
        while not self._stop_event.is_set():
            if time.time() - start_t > self.timeout:
                logger.info("[cookie_detector] Timeout de watcher de sesión alcanzado.")
                break

            try:
                res = detect_myinstants_session()
                if res.get("found"):
                    logger.info(f"[cookie_detector] ¡Sesión detectada para @{res.get('username')} en {res.get('browser')}!")
                    if self.on_success:
                        self.on_success(res)
                    break
            except Exception as e:
                logger.debug(f"[cookie_detector] Error durante polling de sesión: {e}")

            time.sleep(self.poll_interval)


# ─── SESIÓN DE YOUTUBE (PARA YT-DLP SIN BLOQUEOS) ───

_YT_AUTH_COOKIE_NAMES = {"SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure-1PSID", "__Secure-3PSID", "LOGIN_INFO"}
_yt_cookiefile_lock = threading.Lock()


def find_qtwebengine_cookie_dbs() -> list[str]:
    """Encuentra bases de datos Cookies del perfil embebido QtWebEngine del controlador."""
    home = os.path.expanduser("~")
    patterns = [
        os.path.join(home, ".local", "share", "youtube-stream-controller", "QtWebEngine", "*", "Cookies"),
        os.path.join(home, ".local", "share", "YouTube Stream Controller", "QtWebEngine", "*", "Cookies"),
    ]
    matches = []
    for pat in patterns:
        for f in glob.glob(pat):
            if os.path.isfile(f):
                matches.append(f)
    matches.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    return matches


def _extract_chromium_rows_for_youtube(cookie_db: str) -> list[tuple]:
    """Lee filas (host, httponly, path, secure, unix_exp, name, value) de SQLite Chromium/QtWebEngine."""
    rows_out = []
    tmp_dir = tempfile.mkdtemp(prefix="yt_cr_cookies_")
    try:
        tmp_db = os.path.join(tmp_dir, "Cookies")
        shutil.copy2(cookie_db, tmp_db)
        for ext in ("-wal", "-shm", "-journal"):
            src_wal = cookie_db + ext
            if os.path.exists(src_wal):
                shutil.copy2(src_wal, tmp_db + ext)
        conn = sqlite3.connect(tmp_db)
        cur = conn.cursor()
        cur.execute(
            "SELECT host_key, is_httponly, path, is_secure, expires_utc, name, value "
            "FROM cookies WHERE host_key LIKE '%youtube%' OR host_key LIKE '%google%'"
        )
        for host, httponly, path, secure, exp, name, val in cur.fetchall():
            if not val:
                continue
            unix_exp = max(0, int(exp / 1000000 - 11644473600)) if exp else 0
            rows_out.append((host, bool(httponly), path or "/", bool(secure), unix_exp, name, val))
        conn.close()
    except Exception as e:
        logger.debug(f"[cookie_detector] Error leyendo cookies QtWebEngine {cookie_db}: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return rows_out


def _extract_firefox_rows_for_youtube(cookie_db: str) -> list[tuple]:
    """Lee filas (host, httponly, path, secure, unix_exp, name, value) de SQLite Firefox."""
    rows_out = []
    tmp_dir = tempfile.mkdtemp(prefix="yt_ff_cookies_")
    try:
        tmp_db = os.path.join(tmp_dir, "cookies.sqlite")
        shutil.copy2(cookie_db, tmp_db)
        for ext in ("-wal", "-shm"):
            src_wal = cookie_db + ext
            if os.path.exists(src_wal):
                shutil.copy2(src_wal, tmp_db + ext)
        conn = sqlite3.connect(tmp_db)
        cur = conn.cursor()
        cur.execute(
            "SELECT host, isHttpOnly, path, isSecure, expiry, name, value "
            "FROM moz_cookies WHERE host LIKE '%youtube%' OR host LIKE '%google%'"
        )
        for host, httponly, path, secure, exp, name, val in cur.fetchall():
            if not val:
                continue
            rows_out.append((host, bool(httponly), path or "/", bool(secure), int(exp or 0), name, val))
        conn.close()
    except Exception as e:
        logger.debug(f"[cookie_detector] Error leyendo cookies Firefox {cookie_db}: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return rows_out


def _has_yt_auth_in_rows(rows: list[tuple]) -> bool:
    yt_cookies = {name for host, _, _, _, _, name, val in rows if "youtube.com" in host and val}
    return bool(yt_cookies & {"SAPISID", "SID", "__Secure-1PSID", "__Secure-3PSID", "LOGIN_INFO"})


def get_youtube_cookiefile(force_refresh: bool = False) -> str | None:
    """
    Exporta las cookies de sesión de YouTube (desde QtWebEngine o Firefox) a un archivo
    Netscape compatible con yt-dlp y retorna su ruta, o None si no hay sesión iniciada.
    """
    with _yt_cookiefile_lock:
        chosen_rows = []
        # 1. Priorizar perfil embebido QtWebEngine del propio Controller
        for db in find_qtwebengine_cookie_dbs():
            rows = _extract_chromium_rows_for_youtube(db)
            if _has_yt_auth_in_rows(rows):
                chosen_rows = rows
                break

        # 2. Fallback: perfiles de Firefox con sesión de YouTube activa
        if not chosen_rows:
            for db in find_firefox_cookie_dbs():
                rows = _extract_firefox_rows_for_youtube(db)
                if _has_yt_auth_in_rows(rows):
                    chosen_rows = rows
                    break

        target_dir = os.path.join(os.path.expanduser("~"), ".config", "youtube-stream-controller")
        os.makedirs(target_dir, exist_ok=True)
        cookie_file = os.path.join(target_dir, "youtube_cookies.txt")

        if not chosen_rows:
            # Si ya existe un archivo previo válido en disco, conservarlo
            if os.path.isfile(cookie_file) and os.path.getsize(cookie_file) > 100:
                return cookie_file
            return None

        try:
            with open(cookie_file, "w", encoding="utf-8") as f:
                f.write("# Netscape HTTP Cookie File\n")
                for host, httponly, path, secure, unix_exp, name, val in chosen_rows:
                    sub = "TRUE" if host.startswith(".") else "FALSE"
                    sec = "TRUE" if secure else "FALSE"
                    f.write(f"{host}\t{sub}\t{path}\t{sec}\t{unix_exp}\t{name}\t{val}\n")
            return cookie_file
        except Exception as e:
            logger.debug(f"[cookie_detector] Error escribiendo {cookie_file}: {e}")
            return None


def has_youtube_session() -> bool:
    """Indica si existe una sesión autenticada de YouTube disponible para yt-dlp."""
    return bool(get_youtube_cookiefile())


