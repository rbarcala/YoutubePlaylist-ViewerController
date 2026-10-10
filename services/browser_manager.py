"""
Módulo de Gestión de Navegadores y Pestañas (BrowserManager).
Permite:
1. Enumerar pestañas abiertas en Firefox (leyendo recovery.jsonlz4 de perfiles de usuario y snap)
   y Chromium/Chrome/Brave/Edge sin requerir extensiones externas.
2. Detectar si alguna pestaña o ventana abierta corresponde a Google Meet (meet.google.com).
3. Abrir inteligentemente el Viewer siguiendo la prioridad estricta del usuario:
   - 1º: En la misma pestaña/ventana donde está Google Meet.
   - 2º: Si no hay Meet, en una pestaña/ventana ya abierta del navegador.
   - 3º: Si no hay ningún navegador abierto, en una nueva ventana/instancia.
4. Poner la pestaña/ventana del Viewer en foco del sistema operativo cada vez que se reproduzca un video.
"""

import os
import re
import sys
import json
import time
import struct
import shutil
import threading
import subprocess
import webbrowser
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def decompress_mozlz4(data: bytes) -> bytes:
    """
    Descomprime datos con el formato LZ4 propietario de Mozilla (mozLz40\\0).
    Implementado en Python puro para no requerir librerías C externas (liblz4).
    """
    if not data.startswith(b"mozLz40\0"):
        # Podría ser JSON plano sin comprimir
        return data

    uncompressed_size = struct.unpack("<I", data[8:12])[0]
    inp = memoryview(data[12:])
    out = bytearray(uncompressed_size)
    ip = 0
    op = 0
    in_len = len(inp)

    while ip < in_len:
        token = inp[ip]
        ip += 1
        lit_len = token >> 4
        if lit_len == 15:
            while ip < in_len:
                s = inp[ip]
                ip += 1
                lit_len += s
                if s != 255:
                    break

        out[op : op + lit_len] = inp[ip : ip + lit_len]
        op += lit_len
        ip += lit_len

        if ip >= in_len:
            break

        offset = inp[ip] | (inp[ip + 1] << 8)
        ip += 2

        match_len = (token & 0x0F) + 4
        if match_len == 19:
            while ip < in_len:
                s = inp[ip]
                ip += 1
                match_len += s
                if s != 255:
                    break

        while match_len > 0:
            copy_len = min(match_len, offset)
            out[op : op + copy_len] = out[op - offset : op - offset + copy_len]
            op += copy_len
            match_len -= copy_len

    return bytes(out[:op])


class BrowserManager:
    _global_lock = threading.Lock()
    _last_open_time = 0.0

    def __init__(self):
        self._xdotool = shutil.which("xdotool")
        self._wmctrl = shutil.which("wmctrl")
        self._xwininfo = shutil.which("xwininfo")

    def _is_process_running(self, name: str) -> bool:
        """Comprueba de forma rápida si un proceso está actualmente en ejecución."""
        try:
            res = subprocess.run(["pgrep", "-f", name], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=1)
            return res.returncode == 0 and bool(res.stdout.strip())
        except Exception:
            return False

    # ─── 1. ENUMERACIÓN DE PESTAÑAS Y VENTANAS ───

    def enumerate_firefox_tabs(self) -> list[dict]:
        """
        Enumera todas las pestañas abiertas en Firefox (activas y en segundo plano)
        analizando recovery.jsonlz4 en los perfiles nativos, Snap y Flatpak.
        Solo se ejecuta si Firefox está realmente corriendo.
        """
        if not self._is_process_running("firefox"):
            return []

        tabs = []
        base_paths = [
            Path.home() / ".mozilla" / "firefox",
            Path.home() / "snap" / "firefox" / "common" / ".mozilla" / "firefox",
            Path.home() / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox"
        ]

        for base in base_paths:
            if not base.exists():
                continue
            try:
                for profile in base.iterdir():
                    if not profile.is_dir():
                        continue
                    session_files = [
                        profile / "sessionstore-backups" / "recovery.jsonlz4",
                        profile / "sessionstore-backups" / "recovery.baklz4",
                        profile / "sessionstore.jsonlz4"
                    ]
                    for sf in session_files:
                        if sf.exists() and sf.stat().st_size > 16:
                            try:
                                with open(sf, "rb") as f:
                                    raw = f.read()
                                decompressed = decompress_mozlz4(raw)
                                data = json.loads(decompressed.decode("utf-8", errors="ignore"))
                                for w_idx, win in enumerate(data.get("windows", [])):
                                    sel_idx = win.get("selected", 1) - 1
                                    for t_idx, t in enumerate(win.get("tabs", [])):
                                        entries = t.get("entries", [])
                                        curr_idx = t.get("index", len(entries)) - 1
                                        curr = entries[curr_idx] if 0 <= curr_idx < len(entries) else (entries[-1] if entries else {})
                                        url = curr.get("url", "")
                                        title = curr.get("title", "")
                                        is_meet = "meet.google.com" in url or "meet -" in title.lower() or "meet:" in title.lower()
                                        # Solo marcar viewer si la URL coincide explícitamente con viewer.html
                                        is_viewer = "viewer.html" in url.lower() or "/viewer" in url.lower()
                                        tabs.append({
                                            "browser": "firefox",
                                            "url": url,
                                            "title": title,
                                            "is_selected": (t_idx == sel_idx),
                                            "window_idx": w_idx,
                                            "tab_idx": t_idx,
                                            "is_meet": is_meet,
                                            "is_viewer": is_viewer
                                        })
                                if tabs:
                                    return tabs
                            except Exception:
                                continue
            except Exception:
                pass
        return tabs

    def enumerate_system_windows(self) -> list[dict]:
        """
        Enumera todas las ventanas activas en el entorno gráfico (X11 / GNOME / Wayland).
        Retorna id de ventana (wid), título, y si es navegador / meet / viewer.
        """
        windows = []

        # 1. Intentar con wmctrl si está instalado
        if self._wmctrl:
            try:
                proc = subprocess.run(
                    [self._wmctrl, "-l"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=1.5
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    pat = re.compile(r'^(0x[0-9a-fA-F]+)\s+(\S+)\s+(\S+)\s+(.+)$', re.MULTILINE)
                    for m in pat.finditer(proc.stdout):
                        wid, desktop, host, title = m.groups()
                        tl = title.lower()
                        is_browser = any(b in tl for b in ["firefox", "chrome", "chromium", "brave", "edge", "navigator"])
                        is_meet = "meet.google.com" in tl or "meet -" in tl or "meet:" in tl or "google meet" in tl
                        # Solo marcar como viewer si contiene viewer y NO es el controller ni herramientas de desarrollo
                        is_viewer = ("viewer" in tl and "controller" not in tl and "hub" not in tl and "terminal" not in tl and "code" not in tl) or ("🔴 viewer" in tl)
                        windows.append({
                            "wid": wid,
                            "title": title,
                            "is_browser": is_browser or is_meet or is_viewer,
                            "is_meet": is_meet,
                            "is_viewer": is_viewer
                        })
                    if windows:
                        return windows
            except Exception:
                pass

        # 2. Intentar con xwininfo (estándar nativo de X11 en Ubuntu)
        if self._xwininfo:
            try:
                proc = subprocess.run(
                    [self._xwininfo, "-root", "-tree"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=2.0
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    pattern = re.compile(r'^\s*(0x[0-9a-fA-F]+)\s+\"([^\"]+)\":\s*\(\"([^\"]*)\"\s+\"([^\"]*)\"\)', re.MULTILINE)
                    for m in pattern.finditer(proc.stdout):
                        wid, title, c1, c2 = m.groups()
                        classes = f"{c1} {c2}".lower()
                        tl = title.lower()
                        is_browser = any(b in classes for b in ["navigator", "firefox", "chrome", "chromium", "brave", "edge"])
                        is_meet = "meet" in tl or "meet.google.com" in tl
                        is_viewer = ("viewer" in tl and "controller" not in tl and "hub" not in tl and "terminal" not in tl and "code" not in tl) or ("🔴 viewer" in tl)
                        if is_browser or is_meet or is_viewer:
                            windows.append({
                                "wid": wid,
                                "title": title,
                                "class": classes,
                                "is_browser": is_browser or is_meet or is_viewer,
                                "is_meet": is_meet,
                                "is_viewer": is_viewer
                            })
            except Exception:
                pass

        return windows

    # ─── 2. DETECCIÓN DE MEET Y PESTAÑAS ───

    def detect_meet(self) -> dict | None:
        """
        Comprueba si Google Meet está activo en alguna pestaña o ventana.
        Retorna la información del Meet encontrado (primero que encuentre).
        """
        # 1. Comprobar en ventanas del sistema
        windows = self.enumerate_system_windows()
        for w in windows:
            if w.get("is_meet"):
                return {"source": "window", "wid": w.get("wid"), "title": w.get("title")}

        # 2. Comprobar en pestañas de Firefox
        ff_tabs = self.enumerate_firefox_tabs()
        for t in ff_tabs:
            if t.get("is_meet"):
                return {"source": "firefox_tab", "tab": t}

        return None

    def detect_open_browser(self) -> dict | None:
        """
        Detecta si hay algún navegador web abierto actualmente en ejecución.
        """
        # 1. Comprobar procesos de navegadores populares
        for b in ["firefox", "chrome", "chromium", "brave", "edge"]:
            if self._is_process_running(b):
                return {"source": "process", "browser": b}

        # 2. Comprobar ventanas del sistema
        windows = self.enumerate_system_windows()
        for w in windows:
            if w.get("is_browser") and not w.get("is_viewer"):
                return {"source": "window", "wid": w.get("wid"), "title": w.get("title")}

        return None

    # ─── 3. APERTURA INTELIGENTE DEL VIEWER ───

    def is_viewer_open(self, port: int = 8000) -> bool:
        """
        Determina de manera confiable si ya existe una pestaña o ventana
        del Viewer activa. Prioriza la conexión SSE en vivo (activeViewers)
        como fuente de verdad para evitar falsos positivos de archivos diferidos de Firefox.
        """
        # Si ningún navegador está corriendo en el sistema, es imposible que haya un viewer abierto
        has_browser = any(self._is_process_running(b) for b in ["firefox", "chrome", "chromium", "brave", "edge"])
        if not has_browser:
            return False

        # 1. Comprobación de estado en vivo del servidor SSE (fuente de verdad inmediata)
        server_state_checked = False
        try:
            import urllib.request
            req = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=0.3)
            state = json.loads(req.read().decode())
            server_state_checked = True
            # Si el servidor responde y no hay sockets de viewer activos, no está abierto
            if state.get("activeViewers", 0) <= 0:
                return False
            # Si hay activeViewers reportados por el servidor y un navegador está corriendo:
            return True
        except Exception:
            pass

        # 2. Si el servidor no respondió la comprobación HTTP (ej. llamada interna antes de bind),
        # verificar ventanas nativas del entorno gráfico
        windows = self.enumerate_system_windows()
        if any(w.get("is_viewer") for w in windows):
            return True

        # 3. Solo si no se pudo comprobar el estado del servidor, consultar pestañas de Firefox
        if not server_state_checked:
            ff_tabs = self.enumerate_firefox_tabs()
            if any(t.get("is_viewer") for t in ff_tabs):
                return True

        return False

    def open_smart_viewer(self, viewer_url: str, port: int = 8000) -> dict:
        """
        Abre el Viewer según la prioridad jerárquica:
        0. Debounce estricto (1.5s) con lock atómico para evitar aperturas duplicadas en ráfaga.
        1. Si ya hay un Viewer abierto en cualquier parte del sistema -> Foco y NO abrir otro.
        2. Si no hay Viewer abierto o el foco falla -> abre exactamente una pestaña en el navegador web.
        """
        with BrowserManager._global_lock:
            now = time.time()
            if now - BrowserManager._last_open_time < 1.5:
                logger.debug("[browser_manager] Solicitud de apertura ignorada por debounce (< 1.5s).")
                return {"success": True, "action": "debounced", "url": viewer_url}

            # Regla: Si existe un Viewer abierto en vivo, intentar enfocarlo
            if self.is_viewer_open(port):
                logger.info("[browser_manager] Viewer detectado abierto en el sistema. Poniendo en foco.")
                focused = self.focus_viewer()
                if focused:
                    return {"success": True, "action": "focused_existing_viewer", "url": viewer_url}
                logger.info("[browser_manager] Viewer activo pero no se pudo enfocar por ventana; abriendo pestaña para asegurar visibilidad.")

            BrowserManager._last_open_time = now

            # Si hay Google Meet en primer plano y se puede navegar en él:
            meet_info = self.detect_meet()
            if meet_info and meet_info.get("wid") and self._xdotool:
                wid = meet_info["wid"]
                try:
                    subprocess.run([self._xdotool, "windowactivate", "--sync", wid], timeout=1)
                    time.sleep(0.1)
                    subprocess.run([self._xdotool, "key", "--clearmodifiers", "ctrl+l"], timeout=1)
                    time.sleep(0.05)
                    subprocess.run([self._xdotool, "type", "--delay", "0", viewer_url], timeout=1)
                    time.sleep(0.05)
                    subprocess.run([self._xdotool, "key", "Return"], timeout=1)
                    return {"success": True, "action": "navigated_in_meet_tab", "wid": wid, "url": viewer_url}
                except Exception as e:
                    logger.error(f"[browser_manager] Error xdotool en Meet: {e}")

            # Abrir limpiamente exactamente una pestaña en el navegador
            logger.info(f"[browser_manager] Abriendo Viewer: {viewer_url}")
            self._open_url_in_browser(viewer_url)
            return {"success": True, "action": "opened_in_browser", "url": viewer_url}

    def open_url(self, url: str) -> bool:
        """Abre cualquier URL en el navegador predeterminado del sistema respetando la configuración del usuario."""
        if not url:
            return False
        try:
            if shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
        except Exception:
            pass
        try:
            return webbrowser.open(url)
        except Exception as e:
            logger.error(f"[browser_manager] Error abriendo URL {url}: {e}")
            return False

    def open_myinstants_tab(self) -> bool:
        """Abre la web de MyInstants en el navegador predeterminado."""
        return self.open_url("https://www.myinstants.com")

    def _open_url_in_browser(self, url: str):
        """Lanza la URL en el navegador de forma segura con exactamente 1 llamada, sin flags que dupliquen ventanas/pestañas."""
        if not url:
            return
        self.open_url(url)

    # ─── 4. FOCO EN LA PESTAÑA DEL VIEWER AL PONER VIDEO ───

    def focus_viewer(self) -> bool:
        """
        Pone la pestaña/ventana del Viewer en primer plano en el sistema operativo
        utilizando herramientas nativas del entorno sin invocar nuevas instancias de la app.
        Retorna True solo si efectivamente se logró enfocar una ventana del Viewer.
        """
        if not (self._wmctrl or self._xdotool):
            return False

        # 1. Comprobar en ventanas nativas si hay wmctrl / xdotool
        try:
            windows = self.enumerate_system_windows()
            for w in windows:
                if w.get("is_viewer"):
                    wid = w.get("wid")
                    if wid:
                        if self._wmctrl:
                            try:
                                res = subprocess.run([self._wmctrl, "-ia", wid], timeout=1)
                                if res.returncode == 0:
                                    return True
                            except Exception:
                                pass
                        if self._xdotool:
                            try:
                                res = subprocess.run([self._xdotool, "windowactivate", wid], timeout=1)
                                if res.returncode == 0:
                                    return True
                            except Exception:
                                pass
        except Exception:
            pass

        # 2. Intentar activación por título exacto 'Viewer'
        if self._wmctrl:
            try:
                res = subprocess.run([self._wmctrl, "-a", "Viewer"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
                if res.returncode == 0:
                    return True
            except Exception:
                pass

        if self._xdotool:
            try:
                res = subprocess.run(
                    [self._xdotool, "search", "--name", "Viewer", "windowactivate"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1
                )
                if res.returncode == 0:
                    return True
            except Exception:
                pass

        return False
