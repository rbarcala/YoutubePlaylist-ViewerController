#!/usr/bin/env python3
"""
YouTube Stream Controller — Lanzador Principal.
Punto de entrada ligero que orquesta el servidor Flask y la ventana de escritorio.
"""

import os
import sys
import time
import socket
import threading
import argparse
import webbrowser
from pathlib import Path

# Añadir directorio actual al path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config_manager import load_config, save_config
from browser_manager import BrowserManager
from core.env_checker import (
    check_and_install_dependencies,
    launch_obs_if_needed,
    launch_spotify_if_needed,
)
from core.qt_app import launch_qt_window

browser_mgr = BrowserManager()


def normalize_runtime_ports(cfg: dict) -> dict:
    """Normaliza los puertos persistidos antes de iniciar el servidor y OBS."""
    updates = {}
    for key, default in (("port", 8000), ("obs_port", 4455)):
        try:
            value = int(cfg.get(key, default))
            if not 1 <= value <= 65535:
                raise ValueError
        except (TypeError, ValueError):
            value = default
            updates[key] = value
        cfg[key] = value
    if updates:
        save_config(updates)
        print(f"[app] Puertos normalizados: {updates}")
    return cfg


def is_server_running(port: int = 8000) -> bool:
    """Comprueba si el servidor local ya está respondiendo."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        s.connect(('127.0.0.1', port))
        s.close()
        return True
    except Exception:
        return False


def start_server_in_thread(port: int = 8000):
    """Inicia el servidor Flask en un hilo daemon y arranca el anuncio mDNS."""
    from server import app as flask_app
    def _run():
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        try:
            from mdns_service import start_mdns_publisher
            start_mdns_publisher(port)
        except Exception as e:
            print(f"[mDNS] No se pudo iniciar publicador mDNS: {e}")
        flask_app.run(host='0.0.0.0', port=port, threaded=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    # Esperar hasta que esté arriba
    for _ in range(30):
        if is_server_running(port):
            return True
        time.sleep(0.1)
    return False


def main():
    # Verificar dependencias
    if not check_and_install_dependencies(BASE_DIR):
        sys.exit(1)

    parser = argparse.ArgumentParser(description="YouTube Stream Controller")
    parser.add_argument("--mode", choices=["desktop", "web"], help="Modo de ejecución del controlador")
    parser.add_argument("--viewer", action="store_true", help="Abrir directamente el Viewer")
    parser.add_argument("--port", type=int, default=None, help="Puerto del servidor local")
    args = parser.parse_args()

    cfg = normalize_runtime_ports(load_config())
    port = args.port or int(cfg.get("port", 8000))
    mode = args.mode or cfg.get("default_controller_mode", "desktop")

    # Iniciar servidor local si no está corriendo
    if not is_server_running(port):
        print(f"[app] Levantando servidor local en puerto {port}...")
        start_server_in_thread(port)
    else:
        print(f"[app] Servidor detectado en puerto {port}.")

    controller_url = f"http://127.0.0.1:{port}/controller.html"
    viewer_url = f"http://127.0.0.1:{port}/viewer.html"

    # Si se pide abrir el viewer directamente
    if args.viewer:
        print(f"[app] Abriendo Viewer inteligentemente: {viewer_url}")
        browser_mgr.open_smart_viewer(viewer_url, port=port)
        return

    # Apertura automática de OBS Studio y Spotify
    threading.Thread(target=launch_obs_if_needed, args=(cfg, BASE_DIR), daemon=True).start()
    threading.Thread(target=launch_spotify_if_needed, daemon=True).start()

    if mode == "web":
        print(f"[app] Abriendo Controller en navegador web: {controller_url}")
        webbrowser.open(controller_url)
        # Mantener proceso vivo para que el servidor siga corriendo
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[app] Cerrando aplicación.")
    else:
        # En modo escritorio, abrir el viewer si está activado en config
        if cfg.get("auto_open_viewer", False):
            def _smart_open_viewer():
                time.sleep(1.2)
                if not browser_mgr.is_viewer_open(port):
                    print(f"[app] Abriendo Viewer automáticamente: {viewer_url}")
                    browser_mgr.open_smart_viewer(viewer_url, port=port)

            threading.Thread(target=_smart_open_viewer, daemon=True).start()

        print(f"[app] Abriendo Controller nativo de escritorio: {controller_url}")
        launch_qt_window(controller_url, title="YouTube Stream Controller", port=port, browser_mgr=browser_mgr)


if __name__ == "__main__":
    main()
