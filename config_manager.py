"""
Gestor de Configuración y Memoria del Sistema.
Guarda las preferencias del usuario de forma segura (fuera del control de git).
"""

import os
import json
from pathlib import Path

DEFAULT_CONFIG = {
    "youtube_api_key": "",
    "playlist_id": "PL7E8lrk1ePfZVWMM2vsUkpQ6vbpbHi4G_",
    "port": 8000,
    "host": "0.0.0.0",
    "default_controller_mode": "desktop",  # "desktop" o "web"
    "default_playback_rate": 1.7,
    "default_muted": True,
    "auto_open_viewer": False,
    "auto_focus_viewer": True,
    "youtube_channel_id": "",
    "youtube_live_video_id": "",
    "spotify_client_id": "",
    "spotify_client_secret": "",
    "spotify_access_token": "",
    "spotify_refresh_token": "",
    "spotify_token_expires_at": 0,
    "obs_enabled": False,
    "obs_host": "localhost",
    "obs_port": 4455,
    "obs_password": "",
    "obs_scene_on_play": "Fondos",
    "obs_scene_on_stop": "",
    "last_played_video_id": "",
    "last_played_title": "",
    "soundboard_username": "",
    "soundboard_session_cookie": "",
    "soundboard_csrf_token": "",
    "soundboard_volume": 80,
    "soundboard_favorites": []
}

USER_CONFIG_DIR = Path.home() / ".config" / "youtube-playlist-vc"
USER_CONFIG_PATH = USER_CONFIG_DIR / "config.json"
LOCAL_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

def get_config_file_path() -> Path:
    """Devuelve la ruta activa del archivo de configuración."""
    if LOCAL_CONFIG_PATH.exists():
        return LOCAL_CONFIG_PATH
    return USER_CONFIG_PATH

def load_config() -> dict:
    """Carga la configuración combinando defaults con el archivo persistido."""
    cfg = DEFAULT_CONFIG.copy()
    
    # Intentar leer desde config local o desde ~/.config/youtube-playlist-vc/config.json
    for path in [LOCAL_CONFIG_PATH, USER_CONFIG_PATH]:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                    cfg.update(user_data)
                break
            except Exception as e:
                print(f"[config] Error al leer {path}: {e}")

    # Variables de entorno opcionales como override
    if "YOUTUBE_API_KEY" in os.environ and os.environ["YOUTUBE_API_KEY"]:
        cfg["youtube_api_key"] = os.environ["YOUTUBE_API_KEY"]
    if "YOUTUBE_PLAYLIST_ID" in os.environ and os.environ["YOUTUBE_PLAYLIST_ID"]:
        cfg["playlist_id"] = os.environ["YOUTUBE_PLAYLIST_ID"]

    return cfg

def save_config(new_config: dict) -> dict:
    """Guarda la configuración persistente en disco."""
    current = load_config()
    current.update(new_config)

    # Aseguramos el directorio de usuario si guardamos allí
    target_path = LOCAL_CONFIG_PATH
    try:
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
        return current
    except (PermissionError, OSError):
        pass

    # Fallback a ~/.config/youtube-playlist-vc/config.json
    try:
        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(USER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[config] Error guardando config en {USER_CONFIG_PATH}: {e}")

    return current
