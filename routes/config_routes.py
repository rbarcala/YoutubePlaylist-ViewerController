from flask import Blueprint, request, jsonify
from services.config_manager import load_config, save_config

config_bp = Blueprint('config', __name__)

# Variable para inyectar broadcast_event
broadcast_event = None


def init_config_routes(broadcast_fn):
    global broadcast_event
    broadcast_event = broadcast_fn


@config_bp.route('/api/config', methods=['GET', 'POST'])
def manage_config():
    if request.method == 'POST':
        new_data = request.get_json(force=True, silent=True) or {}
        saved = save_config(new_data)
        safe_broadcast = saved.copy()
        safe_broadcast.pop("youtube_api_key", None)
        safe_broadcast.pop("spotify_client_secret", None)
        safe_broadcast.pop("spotify_access_token", None)
        safe_broadcast.pop("spotify_refresh_token", None)
        safe_broadcast.pop("soundboard_session_cookie", None)
        if broadcast_event:
            broadcast_event("config_updated", safe_broadcast)
        return jsonify({"success": True, "config": saved})

    cfg = load_config()
    safe_cfg = cfg.copy()
    raw_key = safe_cfg.get("youtube_api_key", "")
    safe_cfg["has_api_key"] = bool(raw_key)
    safe_cfg["youtube_api_key_masked"] = (raw_key[:4] + "..." + raw_key[-4:]) if len(raw_key) > 8 else ("***" if raw_key else "")
    safe_cfg["has_spotify_secret"] = bool(safe_cfg.get("spotify_client_secret", ""))
    safe_cfg["has_spotify_token"] = bool(safe_cfg.get("spotify_access_token", ""))
    safe_cfg["has_soundboard_session"] = bool(safe_cfg.get("soundboard_session_cookie", ""))

    # No exponer secretos en texto plano en la API de lectura
    safe_cfg.pop("spotify_client_secret", None)
    safe_cfg.pop("spotify_access_token", None)
    safe_cfg.pop("spotify_refresh_token", None)
    safe_cfg.pop("soundboard_session_cookie", None)
    safe_cfg.pop("youtube_api_key", None)

    return jsonify(safe_cfg)