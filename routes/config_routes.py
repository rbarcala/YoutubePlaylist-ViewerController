from flask import Blueprint, request, jsonify
from config_manager import load_config, save_config

config_bp = Blueprint('config', __name__)

# Variable para inyectar broadcast_event
broadcast_event = None

def init_config_routes(broadcast_fn):
    global broadcast_event
    broadcast_event = broadcast_fn


@config_bp.route('/api/config', methods=['GET', 'POST'])
def manage_config():
    if request.method == 'GET':
        cfg = load_config()
        # No exponer secretos sensibles
        safe_cfg = cfg.copy()
        safe_cfg.pop('youtube_api_key', None)
        safe_cfg.pop('spotify_client_secret', None)
        safe_cfg.pop('spotify_access_token', None)
        safe_cfg.pop('spotify_refresh_token', None)
        safe_cfg.pop('soundboard_session_cookie', None)
        return jsonify(safe_cfg)
    
    data = request.get_json() or {}
    new_data = {k: v for k, v in data.items() if k not in (
        'youtube_api_key', 'spotify_client_secret',
        'spotify_access_token', 'spotify_refresh_token',
        'soundboard_session_cookie'
    )}
    
    saved = save_config(new_data)
    safe_broadcast = saved.copy()
    safe_broadcast.pop('youtube_api_key', None)
    safe_broadcast.pop('spotify_client_secret', None)
    safe_broadcast.pop('spotify_access_token', None)
    safe_broadcast.pop('spotify_refresh_token', None)
    safe_broadcast.pop('soundboard_session_cookie', None)
    
    if broadcast_event:
        broadcast_event('config_updated', safe_broadcast)
    
    return jsonify({'ok': True, 'config': safe_broadcast})