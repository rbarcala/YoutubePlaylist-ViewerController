"""Ventana de escritorio nativa usando PyQt5 (Chromium/WebEngine)."""
import os
import sys
import signal
import webbrowser
import threading
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def launch_qt_window(url: str, title: str, port: int, browser_mgr=None) -> int:
    """
    Lanza la ventana nativa PyQt5 con WebEngine.
    Returns el código de salida de la aplicación.
    """
    try:
        # Deshabilitar GPU para evitar EGL_BAD_CONTEXT en Linux y garantizar renderizado 100% estable
        sys.argv.extend([
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-gpu-compositing",
            "--disable-dev-shm-usage"
        ])
        
        from PyQt5.QtCore import QUrl, Qt, QTimer
        from PyQt5.QtWidgets import QApplication, QMainWindow, QAction, QToolBar, QStyle
        from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile
        from PyQt5.QtGui import QIcon, QPalette, QColor
        
        # Permitir matar la app con Ctrl+C en la terminal
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        
        logger.info("[qt_app] Iniciando con motor PyQt5 (Chromium) en modo CPU estable...")
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
                    logger.debug(f"[qt_app js] {message} (line {line_number})")
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
        icon_path = str(Path(__file__).parent.parent / "assets" / "icon.png")
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
        logger.warning("[qt_app] PyQt5 no detectado. Intentando fallback a GTK3/WebKit2...")
        from .gtk_app import launch_webkit_window
        return launch_webkit_window(url, title, port)


def _open_in_browser(url: str):
    """Abre la URL en el navegador predeterminado."""
    import webbrowser
    webbrowser.open(url)


def _show_qr_dialog(parent, url: str):
    """Muestra un diálogo con código QR para acceso móvil."""
    try:
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
        from PyQt5.QtGui import QPixmap
        from PyQt5.QtCore import Qt
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
        
        pixmap = QPixmap()
        pixmap.loadFromData(buf.read())
        
        dialog = QDialog(parent)
        dialog.setWindowTitle('Acceso Móvil - Escanea el QR')
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        
        label = QLabel()
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
        url_label = QLabel(f'<a href="{url}">{url}</a>')
        url_label.setOpenExternalLinks(True)
        url_label.setAlignment(Qt.AlignCenter)
        url_label.setWordWrap(True)
        layout.addWidget(url_label)
        
        close_btn = QPushButton('Cerrar')
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec_()
    except Exception as e:
        logger.error(f"[qt_app] Error generando QR: {e}")