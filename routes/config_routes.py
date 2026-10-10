from flask import Blueprint, request, jsonify
from services.config_manager import load_config, save_config

config_bp = Blueprint('config', __name__)

# Variable para inyectar broadcast_event
broadcast_event = None


def init_config_routes(broadcast_fn):
    global broadcast_event
    broadcast_event = broadcast_fn


def _make_safe_config(cfg):
    safe = cfg.copy()
    raw_key = safe.get("youtube_api_key", "")
    safe["has_api_key"] = bool(raw_key)
    safe["youtube_api_key_masked"] = (raw_key[:4] + "..." + raw_key[-4:]) if len(raw_key) > 8 else ("***" if raw_key else "")
    safe["has_spotify_secret"] = bool(safe.get("spotify_client_secret", ""))
    safe["has_spotify_token"] = bool(safe.get("spotify_access_token", ""))
    safe["has_soundboard_session"] = bool(safe.get("soundboard_session_cookie", ""))

    # No exponer secretos en texto plano en la API
    safe.pop("spotify_client_secret", None)
    safe.pop("spotify_access_token", None)
    safe.pop("spotify_refresh_token", None)
    safe.pop("soundboard_session_cookie", None)
    safe.pop("youtube_api_key", None)
    return safe


@config_bp.route('/api/config', methods=['GET', 'POST'])
def manage_config():
    if request.method == 'POST':
        new_data = request.get_json(force=True, silent=True) or {}
        saved = save_config(new_data)
        safe_cfg = _make_safe_config(saved)
        if broadcast_event:
            broadcast_event("config_updated", safe_cfg)
        return jsonify({"success": True, "config": safe_cfg})

    cfg = load_config()
    return jsonify(_make_safe_config(cfg))