# Core package - Módulos de aplicación y servicios centrales
from .env_checker import check_and_install_dependencies, ensure_v4l2loopback
from .qt_app import launch_qt_window
from .gtk_app import launch_webkit_window
from .websocket_manager import ws_manager, broadcast_event, WebSocketManager
from .video_manager import VideoManager
from .monitors import start_spotify_monitor, start_obs_monitor

__all__ = [
    'check_and_install_dependencies',
    'ensure_v4l2loopback',
    'launch_qt_window',
    'launch_webkit_window',
    'ws_manager',
    'broadcast_event',
    'WebSocketManager',
    'VideoManager',
    'start_spotify_monitor',
    'start_obs_monitor',
]