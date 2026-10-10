"""
Gestor de Configuración y Memoria del Sistema.
Guarda las preferencias del usuario de forma segura (fuera del control de git).
"""

import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "youtube_api_key": "",
    "playlist_id": "PL7E8lrk1ePfZVWMM2vsUkpQ6vbpbHi4G_",
    "port": 8000,
    "host": "0.0.0.0",
    "default_controller_mode": "desktop",  # "desktop" o "web"
    "default_playback_rate": 1.7,
    "default_muted": True,
    "video_playback_mode": "original",
    "auto_open_viewer": True,
    "auto_focus_viewer": True,
    "youtube_channel_id": "",
    "youtube_live_video_id": "",
    "spotify_client_id": "",
    "spotify_client_secret": "",
    "spotify_access_token": "",
    "spotify_refresh_token": "",
    "spotify_token_expires_at": 0,
    "obs_enabled": True,
    "auto_open_obs": True,
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
    "soundboard_favorites": [],
    "overlay_enabled": True,
    "overlay_timer_enabled": True,
    "overlay_now_playing_enabled": True,
    "overlay_show_idle": False,
    "overlay_now_playing": True,
    "overlay_now_playing_pos": "bottom-left",
    "overlay_show_song_title": True,
    "overlay_show_artist": True,
    "overlay_show_badge": True,
    "overlay_show_cover": True,
    "overlay_show_equalizer": True,
    "overlay_show_lyrics": True,
    "overlay_extra_text": "",
    "overlay_position": "bottom-left",
    "overlay_pos_x": 28,
    "overlay_pos_y": 28,
    "overlay_scale": 1.0,
    "overlay_font_family": "system-ui",
    "overlay_text_wave": 0,
    "overlay_bg_color": "#0a0a0a",
    "overlay_bg_opacity": 75,
    "overlay_border_color": "rgba(255, 255, 255, 0.08)",
    "overlay_border_radius": 12,
    "overlay_text_color": "#ffffff",
    "overlay_timer_sound": True,
    "overlay_timer_clock_font": "",
    "overlay_timer_title_font": "",
    "overlay_timer_badge_font": "",
    "overlay_timer_phrase_font": "",
    "overlay_timer_image_enabled": False,
    "overlay_timer_image_url": "",
    "overlay_timer_image_x": 0,
    "overlay_timer_image_y": -100,
    "overlay_timer_image_scale": 1.0,
    "overlay_timer_image_radius": 10,
    "spotify_playlists": [],
    "student_phrases": [
        "Compilando cerebro... (42 warnings, 0 errors)",
        "Buscando la respuesta en Stack Overflow...",
        "El código compila en mi máquina, profe.",
        "git commit -m 'ya vuelvo me fui a buscar cafe'",
        "Segfault: paciencia dumped at 0x7fff",
        "while (clase.estaPesada()) { cafe.tomar(); }",
        "Esperando que termine el build de C++...",
        "El profe: 'Esto entra en el final'. Yo: 💀",
        "Analizando la complejidad O(n!) de este tema...",
        "Reiniciando el router mental...",
        "TODO: Entender lo que el profe acaba de explicar",
        "rm -rf /dudas/dificiles --no-preserve-root"
    ]
}

USER_CONFIG_DIR = Path.home() / ".config" / "youtube-stream-controller"
USER_CONFIG_PATH = USER_CONFIG_DIR / "config.json"
LEGACY_USER_CONFIG_DIR = Path.home() / ".config" / "youtube-playlist-vc"
LEGACY_USER_CONFIG_PATH = LEGACY_USER_CONFIG_DIR / "config.json"
LOCAL_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

PROTECTED_SECRET_KEYS = {
    "youtube_api_key",
    "spotify_client_secret",
    "spotify_access_token",
    "spotify_refresh_token",
    "soundboard_session_cookie",
    "soundboard_csrf_token"
}

def get_config_file_path() -> Path:
    """Devuelve la ruta activa del archivo de configuración prioritario."""
    if USER_CONFIG_PATH.exists():
        return USER_CONFIG_PATH
    if LOCAL_CONFIG_PATH.exists():
        return LOCAL_CONFIG_PATH
    return LEGACY_USER_CONFIG_PATH

def load_config() -> dict:
    """Carga la configuración combinando defaults con el archivo persistido del usuario como fuente suprema."""
    cfg = DEFAULT_CONFIG.copy()
    
    # 1. Cargar desde el archivo local del proyecto (si existe, para defaults o desarrollo)
    if LOCAL_CONFIG_PATH.exists():
        try:
            with open(LOCAL_CONFIG_PATH, "r", encoding="utf-8") as f:
                local_data = json.load(f)
                if isinstance(local_data, dict):
                    cfg.update(local_data)
        except Exception as e:
            logger.error(f"[config] Error al leer {LOCAL_CONFIG_PATH}: {e}")

    # 2. Cargar desde ruta legacy si existe
    if LEGACY_USER_CONFIG_PATH.exists():
        try:
            with open(LEGACY_USER_CONFIG_PATH, "r", encoding="utf-8") as f:
                user_data = json.load(f)
                if isinstance(user_data, dict):
                    cfg.update(user_data)
        except Exception as e:
            logger.error(f"[config] Error al leer {LEGACY_USER_CONFIG_PATH}: {e}")

    # 3. Cargar desde la copia canónica del usuario (~/.config/youtube-stream-controller/config.json)
    # Esta es la fuente de verdad definitiva y sobreescribe cualquier archivo local o legacy
    if USER_CONFIG_PATH.exists():
        try:
            with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f:
                user_data = json.load(f)
                if isinstance(user_data, dict):
                    cfg.update(user_data)
        except Exception as e:
            logger.error(f"[config] Error al leer {USER_CONFIG_PATH}: {e}")

    # Variables de entorno opcionales como override
    if "YOUTUBE_API_KEY" in os.environ and os.environ["YOUTUBE_API_KEY"]:
        cfg["youtube_api_key"] = os.environ["YOUTUBE_API_KEY"]
    if "YOUTUBE_PLAYLIST_ID" in os.environ and os.environ["YOUTUBE_PLAYLIST_ID"]:
        cfg["playlist_id"] = os.environ["YOUTUBE_PLAYLIST_ID"]

    return cfg

def save_config(new_config: dict) -> dict:
    """Guarda la configuración persistente protegiendo credenciales y respaldando en ~/.config."""
    current = load_config()

    # Proteger contra borrado accidental de secretos si se envían strings vacíos o None
    for k, v in new_config.items():
        if k in PROTECTED_SECRET_KEYS and (v is None or (isinstance(v, str) and not v.strip())):
            # Si ya teníamos una clave guardada y el payload viene vacío, conservar la existente
            if current.get(k):
                continue
        current[k] = v

    # 1. Guardar SIEMPRE primero en USER_CONFIG_PATH (~/.config/youtube-stream-controller/)
    try:
        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(USER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[config] Error guardando config en {USER_CONFIG_PATH}: {e}")

    # 2. Respaldar en ruta legacy si es posible
    try:
        LEGACY_USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LEGACY_USER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"[config] No se pudo respaldar en {LEGACY_USER_CONFIG_PATH}: {e}")

    # 3. Guardar en LOCAL_CONFIG_PATH si es posible
    try:
        with open(LOCAL_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
    except (PermissionError, OSError) as e:
        logger.debug(f"[config] No se pudo escribir en {LOCAL_CONFIG_PATH}: {e}")

    return current
