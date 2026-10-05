#!/usr/bin/env python3
"""
YouTube Stream Controller — Lanzador de la Aplicación de Escritorio Nativa.
Integra servidor Flask en segundo plano y ventana nativa GTK3 / WebKit2 en Ubuntu.
"""

import os
import shutil
import subprocess
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

def is_spotify_running() -> bool:
    """Verifica si Spotify ya se encuentra en ejecución."""
    try:
        res = subprocess.run(['pgrep', '-x', 'spotify'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        res2 = subprocess.run(['pgrep', '-f', 'spotify'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        return bool(res.stdout.strip() or res2.stdout.strip())
    except Exception:
        return False

def find_spotify_command() -> list[str] | None:
    """Encuentra el comando adecuado para iniciar Spotify (Nativo, Flatpak o Snap)."""
    # Nativo / Snap en el PATH
    if shutil.which("spotify"):
        return ["spotify"]
    # Flatpak
    if shutil.which("flatpak"):
        try:
            r = subprocess.run(["flatpak", "info", "com.spotify.Client"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r.returncode == 0:
                return ["flatpak", "run", "com.spotify.Client"]
        except Exception:
            pass
    # Snap hardcoded fallback
    if os.path.isfile("/snap/bin/spotify"):
        return ["/snap/bin/spotify"]
    return None

def launch_spotify_if_needed():
    """Inicia Spotify en segundo plano si no está en ejecución."""
    if is_spotify_running():
        print("[app] Spotify ya se encuentra en ejecución.")
        return
        
    cmd = find_spotify_command()
    if not cmd:
        print("[app] Spotify no encontrado en el sistema.")
        return
        
    print(f"[app] Abriendo Spotify automáticamente ({' '.join(cmd)})...")
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[app] Error al abrir Spotify: {e}")

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

def ensure_v4l2loopback_installed():
    """Verifica e instala/carga v4l2loopback automáticamente para la cámara virtual de OBS."""
    try:
        # 1. Comprobar si el módulo ya está cargado en el kernel
        res = subprocess.run(["lsmod"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if "v4l2loopback" in res.stdout:
            return

        print("[app] Verificando soporte para Cámara Virtual de OBS (v4l2loopback)...")

        # 2. Comprobar si el paquete está instalado
        check_pkg = subprocess.run(["dpkg", "-s", "v4l2loopback-dkms"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        need_install = (check_pkg.returncode != 0)

        # Usar pkexec (ventana gráfica de contraseña de Ubuntu) o sudo interactivo
        cmd = []
        if shutil.which("pkexec"):
            cmd = ["pkexec", "bash", "-c"]
        elif shutil.which("sudo"):
            cmd = ["sudo", "bash", "-c"]
        else:
            return

        bash_script = ""
        if need_install:
            print("[app] Solicitando autorización para instalar v4l2loopback (Cámara Virtual OBS)...")
            bash_script += "apt-get update && apt-get install -y v4l2loopback-dkms && "
        bash_script += "modprobe v4l2loopback exclusive_caps=1 card_label='OBS Virtual Camera' && echo 'v4l2loopback' > /etc/modules-load.d/v4l2loopback.conf"

        subprocess.run(cmd + [bash_script], check=False)
    except Exception as e:
        print(f"[app] Aviso: No se pudo configurar v4l2loopback automáticamente: {e}")

def launch_obs_if_needed():
    """Inicia OBS Studio en segundo plano si no está en ejecución."""
    cfg = load_config()
    if not cfg.get("auto_open_obs", True):
        return

    # Asegurar módulo de cámara virtual antes de abrir OBS
    ensure_v4l2loopback_installed()

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
        # OBS must be running before the Browser Source can be synchronized via WebSocket.
        def _sync_obs_overlay():
            time.sleep(3)
            setup_script = BASE_DIR / "scripts" / "setup_obs.py"
            if setup_script.exists():
                for attempt in range(5):
                    result = subprocess.run(
                        [sys.executable, str(setup_script)],
                        cwd=str(BASE_DIR),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                    if result.returncode == 0 and "conectada vía WebSocket" in result.stdout:
                        print("[app] Overlay sincronizado con OBS.")
                        break
                    if result.stdout:
                        print(f"[app] Intento {attempt + 1} de sincronización OBS:\n{result.stdout.strip()}")
                    time.sleep(2)

            # Iniciar automáticamente la cámara virtual de OBS
            try:
                from obs_client import OBSController
                cfg_local = load_config()
                obs = OBSController(
                    host=cfg_local.get("obs_host", "localhost"),
                    port=cfg_local.get("obs_port", 4455),
                    password=cfg_local.get("obs_password", "")
                )
                res_vcam = obs.start_virtual_cam()
                if res_vcam.get("success"):
                    print("[app] Cámara virtual de OBS iniciada automáticamente ✓")
            except Exception as ex_vcam:
                print(f"[app] Aviso al iniciar cámara virtual: {ex_vcam}")
        threading.Thread(target=_sync_obs_overlay, daemon=True).start()
    except Exception as e:
        print(f"[app] Error al abrir OBS Studio: {e}")

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

def check_dependencies() -> bool:
    """Verifica que las librerías necesarias estén instaladas. Si falta alguna, intenta instalarla automáticamente."""
    missing_pkgs = []
    try:
        import flask
    except ImportError:
        missing_pkgs.append("python3-flask")
    try:
        import yt_dlp
    except ImportError:
        missing_pkgs.append("yt-dlp")
    try:
        import requests
    except ImportError:
        missing_pkgs.append("python3-requests")

    # Comprobar herramientas de ventana y sistema en Linux
    for tool, pkg in [("xdotool", "xdotool"), ("wmctrl", "wmctrl")]:
        if not shutil.which(tool):
            missing_pkgs.append(pkg)

    if not missing_pkgs:
        return True

    print(f"[app] Faltan paquetes requeridos: {', '.join(missing_pkgs)}. Intentando instalación automática...")

    # Intentar instalación automática mediante pkexec o sudo
    auth_cmd = []
    if shutil.which("pkexec"):
        auth_cmd = ["pkexec"]
    elif shutil.which("sudo"):
        auth_cmd = ["sudo"]

    if auth_cmd:
        try:
            install_cmd = auth_cmd + ["apt-get", "update"]
            subprocess.run(install_cmd, check=False)
            install_cmd = auth_cmd + ["apt-get", "install", "-y"] + missing_pkgs
            ret = subprocess.run(install_cmd, check=False)
            if ret.returncode == 0:
                print("[app] ¡Paquetes instalados correctamente!")
                return True
        except Exception as e:
            print(f"[app] Error durante la auto-instalación: {e}")

    err_text = (
        "No se pudieron instalar automáticamente las siguientes dependencias:\n\n"
        + "\n".join(f"  • {m}" for m in missing_pkgs)
        + "\n\nPara instalarlas manualmente, ejecuta en tu terminal:\n"
        f"  sudo apt update && sudo apt install -y {' '.join(missing_pkgs)}"
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
                text="Faltan dependencias de sistema"
            )
            dialog.format_secondary_text(
                "No se encontraron paquetes necesarios:\n\n"
                + "\n".join(f"• {m}" for m in missing_pkgs)
                + f"\n\nEjecuta en tu terminal:\nsudo apt install -y {' '.join(missing_pkgs)}"
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

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_refresh = Gtk.Button.new_with_label("🔄 Reintentar / Actualizar")
        btn_refresh.connect("clicked", lambda w: view.reload())
        btn_box.pack_start(btn_refresh, False, False, 0)
        
        btn_direct_login = Gtk.Button.new_with_label("🔑 Ir a Login")
        btn_direct_login.connect("clicked", lambda w: view.load_uri("https://www.myinstants.com/accounts/login/"))
        btn_box.pack_start(btn_direct_login, False, False, 0)
        header.pack_end(btn_box)

        status_lbl = Gtk.Label(label="Inicia sesión con tu cuenta en la ventana...")
        header.pack_start(status_lbl)

        view = WebKit2.WebView()
        st = view.get_settings()
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
                    def on_js_finished(v, async_res):
                        try:
                            js_val = v.run_javascript_finish(async_res)
                            data_str = js_val.get_js_value().to_string() if js_val else ""
                            # Formato retornado: loggedIn:username
                            if data_str and data_str.startswith("1:"):
                                real_user = data_str.split(":", 1)[1].strip() or user or ""
                                captured["done"] = True
                                print(f"[soundboard] ¡Sesión de MyInstants confirmada! Usuario: {real_user}")
                                from config_manager import save_config
                                from server import broadcast_event, soundboard_mgr
                                update_dict = {
                                    "soundboard_session_cookie": sess
                                }
                                if csrf:
                                    update_dict["soundboard_csrf_token"] = csrf
                                if real_user:
                                    update_dict["soundboard_username"] = real_user
                                save_config(update_dict)

                                if real_user:
                                    threading.Thread(target=soundboard_mgr.sync_account, args=(real_user,), daemon=True).start()

                                broadcast_event("soundboard_auth_success", {
                                    "username": real_user or "",
                                    "has_session": True
                                })
                                status_lbl.set_text("✅ ¡Sesión vinculada con éxito! Cerrando...")
                                GLib.timeout_add_seconds(2, win.destroy)
                        except Exception as e_js:
                            print(f"[app] Error verificando login JS: {e_js}")

                    # Verificar si la página tiene usuario autenticado
                    check_code = """
                    (function() {
                        var profLink = document.querySelector('a[href*="/profile/"]');
                        if (profLink) {
                            var m = profLink.href.match(/\\/profile\\/([^\\/\\?#]+)/);
                            var u = m ? m[1] : profLink.textContent.trim();
                            return '1:' + (u || '');
                        }
                        var logoutLink = document.querySelector('a[href*="/accounts/logout/"]');
                        if (logoutLink) {
                            return '1:';
                        }
                        var userEl = document.querySelector('.username, #username, .user-name');
                        if (userEl && userEl.textContent.trim()) {
                            return '1:' + userEl.textContent.trim();
                        }
                        return '0:';
                    })()
                    """
                    view.run_javascript(check_code, None, on_js_finished)
            except Exception as ex:
                print(f"[app] Error procesando cookies: {ex}")

        def on_load_changed(v, event):
            if event == WebKit2.LoadEvent.FINISHED:
                cur_uri = v.get_uri() or ""
                # Si está en favorites o index con sesión, verificar
                cm.get_cookies("https://www.myinstants.com/", None, on_cookies_ready, None)

        view.connect("load-changed", on_load_changed)
        view.load_uri("https://www.myinstants.com/accounts/login/")
        win.show_all()

    try:
        GLib.idle_add(_show_login_dialog)
        return True
    except Exception as e:
        print(f"[app] Error lanzando login window: {e}")
        webbrowser.open("https://www.myinstants.com/en/favorites/")
        return False

def launch_native_window(url: str, title: str = "YouTube Stream Controller", port: int = 8000):
    """Lanza la ventana nativa intentando usar PyQt5 (Chromium) primero, y WebKit2 como respaldo."""
    try:
        import os
        import sys
        
        # OBLIGA a usar X11 (XWayland) para evitar crasheos de NVIDIA en Wayland
        # (Desactivado XCB para probar Vulkan nativo)
        
        from PyQt5.QtCore import QUrl, Qt
        from PyQt5.QtWidgets import QApplication, QMainWindow, QAction, QToolBar, QStyle
        from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile
        from PyQt5.QtGui import QIcon, QPalette, QColor
        import signal
        
        # Permitir matar la app con Ctrl+C en la terminal
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        
        # Deshabilitar GPU para evitar EGL_BAD_CONTEXT en Linux y garantizar renderizado 100% estable
        sys.argv.extend([
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-gpu-compositing",
            "--disable-dev-shm-usage"
        ])
        
        print("[app] Iniciando con motor PyQt5 (Chromium) en modo CPU estable...")
        app = QApplication(sys.argv)
        
        # Agrupar en la barra lateral de Ubuntu y usar icono
        app.setApplicationName("youtube-stream-controller")
        app.setDesktopFileName("youtube-stream-controller.desktop")
        
        # Forzar tema oscuro nativo para bordes blancos
        app.setStyle("Fusion")
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(20, 20, 20))
        dark_palette.setColor(QPalette.WindowText, Qt.white)
        dark_palette.setColor(QPalette.Base, QColor(14, 14, 14))
        dark_palette.setColor(QPalette.AlternateBase, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, Qt.white)
        dark_palette.setColor(QPalette.Button, QColor(45, 45, 45))
        dark_palette.setColor(QPalette.ButtonText, Qt.white)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        app.setPalette(dark_palette)
        app.setStyleSheet("QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }")

        
        class CustomPage(QWebEnginePage):
            def __init__(self, profile, parent=None):
                super().__init__(profile, parent)
                self.featurePermissionRequested.connect(self.on_feature_permission_requested)
                self.setBackgroundColor(QColor(18, 18, 18))
            def javaScriptConsoleMessage(self, level, message, line_number, source_id):
                if level >= QWebEnginePage.WarningMessageLevel:
                    print(f"[app js] {message} (line {line_number})")
            def on_feature_permission_requested(self, sec_url, feature):
                # Auto-allow camera/mic for virtual camera WebRTC
                if feature in (QWebEnginePage.MediaAudioCapture, QWebEnginePage.MediaVideoCapture, QWebEnginePage.MediaAudioVideoCapture):
                    self.setFeaturePermission(sec_url, feature, QWebEnginePage.PermissionGrantedByUser)
                else:
                    self.setFeaturePermission(sec_url, feature, QWebEnginePage.PermissionDeniedByUser)
            def acceptNavigationRequest(self, url, nav_type, is_main_frame):
                url_str = url.toString()
                if url_str and not (url_str.startswith("http://localhost") or url_str.startswith("http://127.0.0.1") or url_str.startswith("file://")):
                    webbrowser.open(url_str)
                    return False
                return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        window = QMainWindow()
        window.setWindowTitle(title)
        window.resize(1220, 840)
        
        # Icono de la ventana
        icon_path = str(BASE_DIR / "assets" / "icon.png")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            window.setWindowIcon(QIcon(icon_path))
        
        # Barra superior con estilos oscuros
        toolbar = QToolBar("Opciones")
        toolbar.setMovable(False)
        toolbar.setStyleSheet("QToolBar { background-color: #111; border-bottom: 1px solid #333; padding: 5px; } QToolButton { color: white; font-weight: bold; padding: 5px 10px; border-radius: 4px; } QToolButton:hover { background-color: #333; }")
        window.addToolBar(toolbar)
        
        # Botones con iconos del sistema
        icon_web = window.style().standardIcon(QStyle.SP_ComputerIcon)
        btn_web = QAction(icon_web, " Modo Web", window)
        btn_web.triggered.connect(lambda: webbrowser.open(url))
        toolbar.addAction(btn_web)
        
        icon_viewer = window.style().standardIcon(QStyle.SP_DesktopIcon)
        btn_viewer = QAction(icon_viewer, " Abrir Viewer", window)
        def on_viewer():
            v_url = url.replace("controller.html", "viewer.html")
            threading.Thread(target=browser_mgr.open_smart_viewer, args=(v_url, port), daemon=True).start()
        btn_viewer.triggered.connect(on_viewer)
        toolbar.addAction(btn_viewer)
        
        # Spacer para empujar cosas a la derecha
        spacer = QAction("", window)
        spacer.setEnabled(False)
        toolbar.addAction(spacer)
        
        icon_reload = window.style().standardIcon(QStyle.SP_BrowserReload)
        btn_reload = QAction(icon_reload, " Recargar", window)
        btn_reload.triggered.connect(lambda: view.reload())
        toolbar.addAction(btn_reload)
        
        view = QWebEngineView()
        profile = QWebEngineProfile.defaultProfile()
        page = CustomPage(profile, view)
        view.setPage(page)
        window.setCentralWidget(view)
        
        view.load(QUrl(url))
        window.show()
        sys.exit(app.exec_())
        
    except ImportError:
        print("[app] PyQt5 no detectado. Intentando fallback a GTK3/WebKit2...")
        _launch_webkit_window(url, title, port)

def _launch_webkit_window(url: str, title: str, port: int):
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

    GLib.set_prgname("youtube-stream-controller")
    window = Gtk.Window(title=title)
    window.set_default_size(1220, 840)
    window.set_position(Gtk.WindowPosition.CENTER)

    header = Gtk.HeaderBar()
    header.set_show_close_button(True)
    header.props.title = "YouTube Stream Controller"
    window.set_titlebar(header)

    webview = WebKit2.WebView()
    settings = webview.get_settings()
    settings.set_enable_developer_extras(True)
    settings.set_enable_webgl(True)
    settings.set_enable_media_stream(True)
    
    def on_permission_request(view, request):
        try:
            request.allow()
            return True
        except Exception:
            return False
            
    webview.connect("permission-request", on_permission_request)

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

    btn_browser = Gtk.Button.new_with_label("🌐 Modo Web")
    btn_browser.connect("clicked", lambda w: webbrowser.open(url))
    header.pack_start(btn_browser)

    scrolled = Gtk.ScrolledWindow()
    scrolled.add(webview)
    window.add(scrolled)
    window.connect("destroy", Gtk.main_quit)
    webview.load_uri(url)
    window.show_all()
    Gtk.main()

def main():
    if not check_dependencies():
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

    # Apertura automática de OBS Studio si no está en ejecución
    threading.Thread(target=launch_obs_if_needed, daemon=True).start()
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
        # En modo escritorio, solo abrir el viewer si está explícitamente activado en la configuración
        if cfg.get("auto_open_viewer", False):
            def _smart_open_viewer():
                time.sleep(1.2)
                if not browser_mgr.is_viewer_open(port):
                    print(f"[app] Abriendo Viewer automáticamente: {viewer_url}")
                    browser_mgr.open_smart_viewer(viewer_url, port=port)

            threading.Thread(target=_smart_open_viewer, daemon=True).start()

        print(f"[app] Abriendo Controller nativo de escritorio: {controller_url}")
        launch_native_window(controller_url, title="YouTube Stream Controller", port=port)

if __name__ == "__main__":
    main()
