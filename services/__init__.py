"""
services package — Gestores y clientes de servicios para YouTube Stream Controller.
"""
from .browser_manager import BrowserManager
from .config_manager import load_config, save_config, get_config_file_path
from .obs_client import OBSController
from .overlay_manager import OverlayManager
from .qr_svg import generate_qr_svg
from .soundboard_manager import SoundboardManager
from .spotify_manager import SpotifyManager
from .mdns_service import start_mdns_publisher

__all__ = [
    'BrowserManager',
    'load_config',
    'save_config',
    'get_config_file_path',
    'OBSController',
    'OverlayManager',
    'generate_qr_svg',
    'SoundboardManager',
    'SpotifyManager',
    'start_mdns_publisher',
]

