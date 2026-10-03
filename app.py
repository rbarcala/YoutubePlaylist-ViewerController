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

def is_obs_running() -> bool:
    """Verifica si OBS Studio ya se encuentra en ejecución."""
    try:
        import subprocess
        current_pid = os.getpid()
        res = subprocess.run(['pgrep', '-x', 'obs'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        pids = [int(p.strip()) for p in res.stdout.strip().split() if p.strip().isdigit() and int(p.strip()) != current_pid]
        if pids:
            return True
        res2 = subprocess.run(['pgrep', '-f', 'obs-studio/bin|/app/bin/obs|com.obsproject.Studio'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        pids2 = [int(p.strip()) for p in res2.stdout.strip().split() if p.strip().isdigit() and int(p.strip()) != current_pid]
        if pids2:
            return True
    except Exception:
        pass
    return False

def find_obs_command() -> list[str] | None:
    """Encuentra el comando adecuado para iniciar OBS Studio (Nativo, Flatpak o Snap)."""
    import shutil, subprocess
    if shutil.which("obs"):
        return ["obs"]
    if shutil.which("flatpak"):
        try:
            r = subprocess.run(["flatpak", "info", "com.obsproject.Studio"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r.returncode == 0:
                return ["flatpak", "run", "com.obsproject.Studio"]
        except Exception:
            pass
    if shutil.which("obs-studio"):
        return ["obs-studio"]
    if os.path.isfile("/snap/bin/obs-studio"):
        return ["/snap/bin/obs-studio"]
    return None

def launch_obs_if_needed():
    """Inicia OBS Studio en segundo plano si no está en ejecución."""
    cfg = load_config()
    if not cfg.get("auto_open_obs", True):
        return

    if is_obs_running():
        print("[app] OBS Studio ya se encuentra en ejecución.")
        return

    cmd = find_obs_command()
    if not cmd:
        print("[app] OBS Studio no encontrado en el sistema.")
        return

    print(f"[app] Abriendo OBS Studio automáticamente ({' '.join(cmd)})...")
    try:
        import subprocess
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception as e:
        print(f"[app] Error al abrir OBS Studio: {e}")

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

def open_myinstants_login_window():
    """
    Abre una ventana GTK WebKit2 dedicada para que el usuario inicie sesión en MyInstants
    (con Google o su cuenta) e intercepta automáticamente las cookies y el nombre de usuario.
    """
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('WebKit2', '4.1')
        from gi.repository import Gtk, WebKit2, GLib
    except Exception as e:
        print(f"[app] GTK/WebKit2 no disponible para ventana de login: {e}")
        webbrowser.open("https://www.myinstants.com/en/favorites/")
        return False

    def _show_login_dialog():
        win = Gtk.Window(title="Iniciar Sesión en MyInstants")
        win.set_default_size(720, 800)
        win.set_position(Gtk.WindowPosition.CENTER)

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "Conectar MyInstants"
        header.props.subtitle = "Inicia sesión con Google o tu usuario para guardar favoritos en la nube"
        win.set_titlebar(header)

        status_lbl = Gtk.Label(label="Esperando inicio de sesión en MyInstants...")
        header.pack_start(status_lbl)

        view = WebKit2.WebView()
        st = view.get_settings()
        # Usar User-Agent de Chrome de escritorio moderno para compatibilidad con Google OAuth
        st.set_user_agent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        st.set_enable_javascript(True)
        st.set_enable_webgl(True)
        st.set_enable_developer_extras(True)

        scr = Gtk.ScrolledWindow()
        scr.add(view)
        win.add(scr)

        ctx = view.get_context()
        cm = ctx.get_cookie_manager()
        captured = {"done": False}

        def on_cookies_ready(source, res, data):
            try:
                cookies = source.get_cookies_finish(res)
                sess = None
                csrf = None
                user = None
                for c in cookies:
                    n = c.get_name()
                    v = c.get_value()
                    if n == "sessionid":
                        sess = v
                    elif n == "csrftoken":
                        csrf = v
                    elif n == "username":
                        user = v

                if sess and not captured["done"]:
                    captured["done"] = True
                    print(f"[soundboard] ¡Sesión de MyInstants detectada exitosamente! Usuario: {user}")
                    from config_manager import save_config
                    from server import broadcast_event, soundboard_mgr
                    update_dict = {
                        "soundboard_session_cookie": sess
                    }
                    if csrf:
                        update_dict["soundboard_csrf_token"] = csrf
                    if user:
                        update_dict["soundboard_username"] = user
                    save_config(update_dict)

                    if user:
                        threading.Thread(target=soundboard_mgr.sync_account, args=(user,), daemon=True).start()

                    broadcast_event("soundboard_auth_success", {
                        "username": user or "",
                        "has_session": True
                    })
                    status_lbl.set_text("✅ ¡Sesión vinculada con éxito! Cerrando...")
                    GLib.timeout_add_seconds(2, win.destroy)
            except Exception as ex:
                print(f"[app] Error procesando cookies: {ex}")

        def on_load_changed(v, event):
            if event == WebKit2.LoadEvent.FINISHED:
                cm.get_cookies("https://www.myinstants.com/", None, on_cookies_ready, None)

        view.connect("load-changed", on_load_changed)
        view.load_uri("https://www.myinstants.com/en/favorites/")
        win.show_all()

    try:
        GLib.idle_add(_show_login_dialog)
        return True
    except Exception as e:
        print(f"[app] Error lanzando login window: {e}")
        webbrowser.open("https://www.myinstants.com/en/favorites/")
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

    # Manejar enlaces externos y window.open para abrirlos en el navegador real
    def on_decide_policy(view, decision, decision_type):
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            action = decision.get_navigation_action()
            req = action.get_request()
            uri = req.get_uri() if req else ""
            if uri and not (uri.startswith("http://localhost") or uri.startswith("http://127.0.0.1") or uri.startswith("file://")):
                webbrowser.open(uri)
                decision.ignore()
                return True
        return False

    webview.connect("decide-policy", on_decide_policy)

    def on_create_window(view, action):
        req = action.get_request()
        uri = req.get_uri() if req else ""
        if uri:
            webbrowser.open(uri)
        return None

    webview.connect("create", on_create_window)

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

    # Apertura automática de OBS Studio si no está en ejecución
    threading.Thread(target=launch_obs_if_needed, daemon=True).start()

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
