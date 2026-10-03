#!/usr/bin/env python3
"""
YouTube Stream Controller — Lanzador de la Aplicación de Escritorio Nativa.
Integra servidor Flask en segundo plano y ventana nativa GTK3 / WebKit2 en Ubuntu.
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

browser_mgr = BrowserManager()

def check_dependencies() -> bool:
    """Verifica que las librerías necesarias de Python estén instaladas."""
    missing = []
    try:
        import flask
    except ImportError:
        missing.append("flask (paquete: python3-flask)")
    try:
        import yt_dlp
    except ImportError:
        missing.append("yt-dlp (paquete: yt-dlp)")

    if not missing:
        return True

    err_text = (
        "No se encontraron las siguientes dependencias de Python requeridas:\n\n"
        + "\n".join(f"  • {m}" for m in missing)
        + "\n\nPara solucionarlo, abre una terminal y ejecuta:\n"
        "  sudo apt update && sudo apt install -y python3-flask yt-dlp python3-requests\n"
        "\nO si utilizas pip / entorno virtual:\n"
        "  pip install -r requirements.txt"
    )

    print(f"\n{'='*70}\n[ERROR] YouTube Stream Controller:\n{err_text}\n{'='*70}\n", file=sys.stderr)

    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        try:
            import gi
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk
            dialog = Gtk.MessageDialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Faltan dependencias de Python"
            )
            dialog.format_secondary_text(
                "No se encontraron módulos necesarios:\n\n"
                + "\n".join(f"• {m}" for m in missing)
                + "\n\nEjecuta en tu terminal:\nsudo apt install -y python3-flask yt-dlp"
            )
            dialog.run()
            dialog.destroy()
        except Exception:
            pass

    return False


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
    """Inicia el servidor Flask en un hilo daemon."""
    from server import app as flask_app
    def _run():
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        flask_app.run(host='0.0.0.0', port=port, threaded=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    # Esperar hasta que esté arriba
    for _ in range(30):
        if is_server_running(port):
            return True
        time.sleep(0.1)
    return False

def launch_native_window(url: str, title: str = "YouTube Stream Controller"):
    """Lanza la ventana nativa de escritorio usando PyGObject GTK3 + WebKit2."""
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('WebKit2', '4.1')
        from gi.repository import Gtk, WebKit2, Gio, GLib, GdkPixbuf
    except Exception as e:
        print(f"[app] GTK3/WebKit2 no disponible: {e}. Fallback a navegador web.")
        webbrowser.open(url)
        return

    if not Gtk.init_check():
        print("[app] No se pudo inicializar display gráfico GTK. Abriendo en navegador.")
        webbrowser.open(url)
        return

    # Crear ventana GTK
    window = Gtk.Window(title=title)
    window.set_default_size(1220, 840)
    window.set_position(Gtk.WindowPosition.CENTER)

    # Cargar icono
    icon_paths = [
        BASE_DIR / "assets" / "icon.png",
        BASE_DIR / "assets" / "icon.svg",
        Path("/usr/share/icons/hicolor/scalable/apps/youtube-stream-controller.svg")
    ]
    for p in icon_paths:
        if p.exists():
            try:
                window.set_icon_from_file(str(p))
                break
            except Exception:
                pass

    # HeaderBar moderna de GNOME / Ubuntu
    header = Gtk.HeaderBar()
    header.set_show_close_button(True)
    header.props.title = "YouTube Stream Controller"
    header.props.subtitle = "Fondos & Stream Player"
    window.set_titlebar(header)

    # WebView con aceleración de hardware
    webview = WebKit2.WebView()
    settings = webview.get_settings()
    settings.set_enable_developer_extras(True)
    settings.set_enable_webgl(True)
    settings.set_enable_media_stream(True)
    settings.set_enable_smooth_scrolling(True)

    # Botón: Abrir en Navegador Web
    btn_browser = Gtk.Button.new_with_label("🌐 Modo Web")
    btn_browser.set_tooltip_text("Abrir este controlador en una pestaña del navegador web")
    def on_open_browser_clicked(widget):
        webbrowser.open(url)
    btn_browser.connect("clicked", on_open_browser_clicked)
    header.pack_start(btn_browser)

    # Botón: Abrir Viewer en Navegador
    btn_viewer = Gtk.Button.new_with_label("📺 Abrir Viewer")
    btn_viewer.set_tooltip_text("Abrir pantalla completa del Viewer para compartir en Meet / OBS")
    def on_open_viewer_clicked(widget):
        viewer_url = url.replace("controller.html", "viewer.html")
        threading.Thread(target=browser_mgr.open_smart_viewer, args=(viewer_url,), daemon=True).start()
    btn_viewer.connect("clicked", on_open_viewer_clicked)
    header.pack_start(btn_viewer)

    # Botón: Recargar
    btn_reload = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
    btn_reload.set_tooltip_text("Recargar controlador")
    btn_reload.connect("clicked", lambda w: webview.reload())
    header.pack_end(btn_reload)

    # Botón: Configuración
    btn_settings = Gtk.Button.new_from_icon_name("preferences-system-symbolic", Gtk.IconSize.BUTTON)
    btn_settings.set_tooltip_text("Configuración y Setup de Playlist / API Key / OBS")
    def on_settings_clicked(w):
        webview.run_javascript("if(window.openSettingsModal) window.openSettingsModal();", None, None, None)
    btn_settings.connect("clicked", on_settings_clicked)
    header.pack_end(btn_settings)

    # Contenedor Scrolled
    scrolled = Gtk.ScrolledWindow()
    scrolled.add(webview)
    window.add(scrolled)

    # Manejador de cierre
    window.connect("destroy", Gtk.main_quit)

    # Cargar URL
    webview.load_uri(url)
    window.show_all()

    # Loop GTK
    Gtk.main()

def main():
    if not check_dependencies():
        sys.exit(1)

    parser = argparse.ArgumentParser(description="YouTube Stream Controller")
    parser.add_argument("--mode", choices=["desktop", "web"], help="Modo de ejecución del controlador")
    parser.add_argument("--viewer", action="store_true", help="Abrir directamente el Viewer")
    parser.add_argument("--port", type=int, default=None, help="Puerto del servidor local")
    args = parser.parse_args()

    cfg = load_config()
    port = args.port or int(cfg.get("port", 8000))
    mode = args.mode or cfg.get("default_controller_mode", "desktop")

    # Iniciar servidor local si no está corriendo
    if not is_server_running(port):
        print(f"[app] Levantando servidor local en puerto {port}...")
        start_server_in_thread(port)
    else:
        print(f"[app] Servidor detectado en puerto {port}.")

    controller_url = f"http://localhost:{port}/controller.html"
    viewer_url = f"http://localhost:{port}/viewer.html"

    # Si se pide abrir el viewer directamente
    if args.viewer:
        print(f"[app] Abriendo Viewer inteligentemente: {viewer_url}")
        browser_mgr.open_smart_viewer(viewer_url)
        return

    # Apertura automática e inteligente del Viewer al abrir el Controller (Meet -> Pestaña abierta -> Nueva ventana)
    print(f"[app] Abriendo Viewer automáticamente: {viewer_url}")
    threading.Thread(target=browser_mgr.open_smart_viewer, args=(viewer_url,), daemon=True).start()

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
        print(f"[app] Abriendo Controller en ventana de escritorio nativa...")
        launch_native_window(controller_url)

if __name__ == "__main__":
    main()
