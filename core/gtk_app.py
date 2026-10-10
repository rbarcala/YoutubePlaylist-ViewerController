"""Ventana de escritorio alternativa usando GTK3 + WebKit2."""
import os
import sys
import signal
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def launch_webkit_window(url: str, title: str, port: int) -> int:
    """
    Lanza la ventana nativa GTK3 con WebKit2.
    Returns el código de salida de la aplicación.
    """
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('WebKit2', '4.1')
        from gi.repository import Gtk, WebKit2, Gio, GLib, GdkPixbuf
        
        # Permitir matar la app con Ctrl+C
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        
        # Configurar WebKit2
        web_context = WebKit2.WebContext.get_default()
        cache_dir = Path.home() / '.cache' / 'youtube-stream-controller' / 'webkit'
        cache_dir.mkdir(parents=True, exist_ok=True)
        web_context.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)
        
        # Ventana principal
        window = Gtk.Window(title=title)
        window.set_default_size(1280, 800)
        window.connect('destroy', Gtk.main_quit)
        
        # Icono
        icon_path = Path(__file__).parent.parent / 'assets' / 'icon.png'
        if icon_path.exists():
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(icon_path))
                window.set_icon(pixbuf)
            except Exception:
                pass
        
        # WebView
        webview = WebKit2.WebView()
        webview.load_uri(url)
        
        # Configurar ajustes de WebKit
        settings = webview.get_settings()
        settings.set_enable_javascript(True)
        settings.set_enable_write_console_messages_to_stdout(True)
        settings.set_enable_developer_extras(True)
        settings.set_allow_modal_dialogs(True)
        settings.set_media_playback_requires_user_gesture(False)
        
        # Permitir autoplay de video
        settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.ALWAYS)
        
        # User agent moderno
        settings.set_user_agent(
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 '
            '(KHTML, like Gecko) Version/16.0 Safari/605.1.15'
        )
        
        # Contenedor con barra de herramientas
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        window.add(vbox)
        
        # Toolbar
        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.ICONS)
        vbox.pack_start(toolbar, False, False, 0)
        
        # Botón Atrás
        back_btn = Gtk.ToolButton.new_from_stock(Gtk.STOCK_GO_BACK)
        back_btn.connect('clicked', lambda _: webview.go_back())
        toolbar.insert(back_btn, 0)
        
        # Botón Adelante
        forward_btn = Gtk.ToolButton.new_from_stock(Gtk.STOCK_GO_FORWARD)
        forward_btn.connect('clicked', lambda _: webview.go_forward())
        toolbar.insert(forward_btn, 1)
        
        # Botón Recargar
        reload_btn = Gtk.ToolButton.new_from_stock(Gtk.STOCK_REFRESH)
        reload_btn.connect('clicked', lambda _: webview.reload())
        toolbar.insert(reload_btn, 2)
        
        # Separador
        toolbar.insert(Gtk.SeparatorToolItem(), 3)
        
        # Botón Navegador
        browser_btn = Gtk.ToolButton()
        browser_btn.set_label('🌐 Navegador')
        browser_btn.connect('clicked', lambda _: _open_in_browser(url))
        toolbar.insert(browser_btn, 4)
        
        # Botón QR
        qr_btn = Gtk.ToolButton()
        qr_btn.set_label('📱 QR Móvil')
        qr_btn.connect('clicked', lambda _: _show_qr_dialog(window, url))
        toolbar.insert(qr_btn, 5)
        
        # WebView en scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.add(webview)
        vbox.pack_start(scrolled, True, True, 0)
        
        window.show_all()
        
        # Iniciar main loop
        Gtk.main()
        return 0
        
    except Exception as e:
        logger.error(f"[gtk_app] Error lanzando ventana GTK/WebKit2: {e}")
        return 1


def _open_in_browser(url: str):
    """Abre la URL en el navegador predeterminado."""
    import webbrowser
    webbrowser.open(url)


def _show_qr_dialog(parent, url: str):
    """Muestra un diálogo con código QR para acceso móvil."""
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GdkPixbuf
        import qrcode
        import io
        
        # Generar QR
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=6,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color='black', back_color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        
        loader = GdkPixbuf.PixbufLoader()
        loader.write(buf.read())
        loader.close()
        pixbuf = loader.get_pixbuf()
        
        dialog = Gtk.Dialog(
            title='Acceso Móvil - Escanea el QR',
            transient_for=parent,
            flags=Gtk.DialogFlags.MODAL
        )
        dialog.set_default_size(300, 400)
        
        content_area = dialog.get_content_area()
        
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        content_area.pack_start(image, True, True, 0)
        
        url_label = Gtk.Label()
        url_label.set_markup(f'<a href="{url}">{url}</a>')
        url_label.set_line_wrap(True)
        content_area.pack_start(url_label, False, False, 10)
        
        dialog.add_button('Cerrar', Gtk.ResponseType.CLOSE)
        dialog.show_all()
        dialog.run()
        dialog.destroy()
        
    except Exception as e:
        logger.error(f"[gtk_app] Error generando QR: {e}")


def open_myinstants_login_window() -> bool:
    """
    Abre una ventana GTK WebKit2 dedicada para que el usuario inicie sesión en MyInstants.
    """
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('WebKit2', '4.1')
        from gi.repository import Gtk, WebKit2, GLib
    except Exception as e:
        logger.warning(f"[gtk_app] GTK/WebKit2 no disponible para ventana de login: {e}")
        import webbrowser
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
                            if data_str and data_str.startswith("1:"):
                                real_user = data_str.split(":", 1)[1].strip() or user or ""
                                captured["done"] = True
                                logger.info(f"[soundboard] ¡Sesión de MyInstants confirmada! Usuario: {real_user}")
                                from services.config_manager import save_config
                                from server import broadcast_event, soundboard_mgr
                                import threading
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
                            logger.debug(f"[gtk_app] Error verificando login JS: {e_js}")

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
                logger.debug(f"[gtk_app] Error procesando cookies: {ex}")

        def on_load_changed(v, event):
            if event == WebKit2.LoadEvent.FINISHED:
                cur_uri = v.get_uri() or ""
                cm.get_cookies("https://www.myinstants.com/", None, on_cookies_ready, None)

        view.connect("load-changed", on_load_changed)
        view.load_uri("https://www.myinstants.com/accounts/login/")
        win.show_all()

    try:
        GLib.idle_add(_show_login_dialog)
        return True
    except Exception as e:
        logger.error(f"[gtk_app] Error lanzando login window: {e}")
        import webbrowser
        webbrowser.open("https://www.myinstants.com/en/favorites/")
        return False