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
import subprocess
import webbrowser
from pathlib import Path

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
    def __init__(self):
        self._xdotool = shutil.which("xdotool")
        self._wmctrl = shutil.which("wmctrl")
        self._xwininfo = shutil.which("xwininfo")

    # ─── 1. ENUMERACIÓN DE PESTAÑAS Y VENTANAS ───

    def enumerate_firefox_tabs(self) -> list[dict]:
        """
        Enumera todas las pestañas abiertas en Firefox (activas y en segundo plano)
        analizando recovery.jsonlz4 en los perfiles nativos, Snap y Flatpak.
        """
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
                                        is_viewer = "viewer" in url.lower() or "viewer" in title.lower()
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
                        is_viewer = "viewer" in tl or "fondos & stream player" in tl
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
                        is_viewer = "viewer" in tl or "fondos" in tl
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
        Detecta si hay algún navegador web abierto actualmente.
        """
        windows = self.enumerate_system_windows()
        for w in windows:
            if w.get("is_browser") and not w.get("is_viewer"):
                return {"source": "window", "wid": w.get("wid"), "title": w.get("title")}

        ff_tabs = self.enumerate_firefox_tabs()
        if ff_tabs:
            return {"source": "firefox_tab", "tab_count": len(ff_tabs)}

        return None

    # ─── 3. APERTURA INTELIGENTE DEL VIEWER ───

    def open_smart_viewer(self, viewer_url: str) -> dict:
        """
        Abre el Viewer según la prioridad jerárquica solicitada:
        1. Si hay Meet: se mete en la primera pestaña/ventana donde esté Meet.
        2. Si no hay Meet pero hay navegador abierto: se mete en una pestaña abierta.
        3. Si no hay navegador abierto: se abre en una nueva ventana/instancia.
        """
        # Ya hay un Viewer abierto? Ponerlo en foco y retornar
        if self.focus_viewer():
            return {"success": True, "action": "focused_existing_viewer", "url": viewer_url}

        # Nivel 1: ¿Existe Meet?
        meet_info = self.detect_meet()
        if meet_info:
            print(f"[browser_manager] Detectado Google Meet: {meet_info}")
            if meet_info.get("wid") and self._xdotool:
                wid = meet_info["wid"]
                try:
                    # Activar ventana de Meet y navegar en su pestaña actual hacia el Viewer
                    subprocess.run([self._xdotool, "windowactivate", "--sync", wid], timeout=1)
                    time.sleep(0.1)
                    subprocess.run([self._xdotool, "key", "--clearmodifiers", "ctrl+l"], timeout=1)
                    time.sleep(0.05)
                    subprocess.run([self._xdotool, "type", "--delay", "0", viewer_url], timeout=1)
                    time.sleep(0.05)
                    subprocess.run([self._xdotool, "key", "Return"], timeout=1)
                    return {"success": True, "action": "navigated_in_meet_tab", "wid": wid, "url": viewer_url}
                except Exception as e:
                    print(f"[browser_manager] Error xdotool en Meet: {e}")

            # Si no hay xdotool o falló, abrir navegador normalmente
            self._open_url_in_browser(viewer_url)
            return {"success": True, "action": "opened_near_meet", "url": viewer_url}

        # Nivel 2: ¿Hay alguna ventana o pestaña de navegador abierta?
        browser_info = self.detect_open_browser()
        if browser_info:
            print(f"[browser_manager] Detectado navegador abierto: {browser_info}")
            if browser_info.get("wid") and self._xdotool:
                wid = browser_info["wid"]
                try:
                    subprocess.run([self._xdotool, "windowactivate", "--sync", wid], timeout=1)
                    time.sleep(0.1)
                    # Abrir en la pestaña activa
                    subprocess.run([self._xdotool, "key", "--clearmodifiers", "ctrl+l"], timeout=1)
                    time.sleep(0.05)
                    subprocess.run([self._xdotool, "type", "--delay", "0", viewer_url], timeout=1)
                    time.sleep(0.05)
                    subprocess.run([self._xdotool, "key", "Return"], timeout=1)
                    return {"success": True, "action": "navigated_in_open_tab", "wid": wid, "url": viewer_url}
                except Exception as e:
                    print(f"[browser_manager] Error xdotool en navegador abierto: {e}")

            self._open_url_in_browser(viewer_url)
            return {"success": True, "action": "opened_in_browser", "url": viewer_url}

        # Nivel 3: No hay navegador abierto -> abrir en nueva instancia
        print(f"[browser_manager] No hay navegador abierto. Abriendo nueva ventana con {viewer_url}")
        self._open_url_in_browser(viewer_url, new_window=True)
        return {"success": True, "action": "opened_new_window", "url": viewer_url}

    def _open_url_in_browser(self, url: str, new_window: bool = False):
        """Lanza la URL en el navegador predeterminado del sistema o Firefox."""
        try:
            if shutil.which("firefox"):
                cmd = ["firefox", "--new-window" if new_window else "", url]
                cmd = [c for c in cmd if c]
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        except Exception:
            pass

        try:
            if new_window:
                webbrowser.open_new(url)
            else:
                webbrowser.open(url)
        except Exception as e:
            print(f"[browser_manager] Error en webbrowser.open: {e}")

    # ─── 4. FOCO EN LA PESTAÑA DEL VIEWER AL PONER VIDEO ───

    def focus_viewer(self) -> bool:
        """
        Pone la pestaña/ventana del Viewer en primer plano en el sistema operativo.
        Se ejecuta automáticamente cada vez que se selecciona un nuevo video.
        """
        windows = self.enumerate_system_windows()
        for w in windows:
            if w.get("is_viewer"):
                wid = w.get("wid")
                if wid:
                    # 1. Intentar wmctrl
                    if self._wmctrl:
                        try:
                            res = subprocess.run([self._wmctrl, "-ia", wid], timeout=1)
                            if res.returncode == 0:
                                return True
                        except Exception:
                            pass
                    # 2. Intentar xdotool
                    if self._xdotool:
                        try:
                            res = subprocess.run([self._xdotool, "windowactivate", wid], timeout=1)
                            if res.returncode == 0:
                                return True
                        except Exception:
                            pass

        # Búsqueda por título global
        if self._wmctrl:
            try:
                subprocess.run([self._wmctrl, "-a", "Viewer"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                pass

        if self._xdotool:
            try:
                subprocess.run(
                    [self._xdotool, "search", "--name", "Viewer", "windowactivate"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True
            except Exception:
                pass

        return False
