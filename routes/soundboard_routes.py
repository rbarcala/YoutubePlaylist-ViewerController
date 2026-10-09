import os
import json
import threading
import webbrowser
from flask import Blueprint, request, jsonify, send_from_directory

soundboard_bp = Blueprint('soundboard', __name__)

# Variables que se inyectan desde server.py
soundboard_mgr = None
load_config = None
save_config = None
broadcast_event = None
browser_mgr = None


def init_soundboard_routes(sb_mgr, config_loader, config_saver, broadcast_fn, br_mgr=None):
    global soundboard_mgr, load_config, save_config, broadcast_event, browser_mgr
    soundboard_mgr = sb_mgr
    load_config = config_loader
    save_config = config_saver
    broadcast_event = broadcast_fn
    browser_mgr = br_mgr


@soundboard_bp.route('/api/soundboard/regional')
def soundboard_regional():
    region = request.args.get('region', 'ar')
    page = int(request.args.get('page', 1))
    result = soundboard_mgr.get_regional(region, page)
    return jsonify(result)


@soundboard_bp.route('/api/soundboard/trending')
def soundboard_trending():
    page = int(request.args.get('page', 1))
    result = soundboard_mgr.get_regional('trending', page)
    return jsonify(result)


@soundboard_bp.route('/api/soundboard/search')
def soundboard_search():
    query = request.args.get('q', '')
    page = int(request.args.get('page', 1))
    if not query:
        return jsonify({'sounds': []})
    result = soundboard_mgr.search(query, page)
    return jsonify(result)


@soundboard_bp.route('/api/open_browser', methods=['GET', 'POST'])
def open_browser():
    if browser_mgr:
        browser_mgr.open_myinstants_tab()
        return jsonify({'ok': True})
    webbrowser.open("https://www.myinstants.com")
    return jsonify({'ok': True, 'fallback': 'browser'})


@soundboard_bp.route('/api/soundboard/auth', methods=['GET', 'POST'])
def soundboard_auth():
    if request.method == 'GET':
        return jsonify(soundboard_mgr.get_auth_status())

    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    session_cookie = data.get("session_cookie") or data.get("cookie", "")
    csrf_token = data.get("csrf_token", "")
    client_id = data.get("clientId") or data.get("client_id")

    res = soundboard_mgr.save_auth(username, session_cookie, csrf_token)
    if broadcast_event:
        broadcast_event("soundboard_auth_success", {
            "username": res.get("username", ""),
            "has_session": res.get("has_session", False),
            "clientId": client_id
        })
        favs = soundboard_mgr.get_saved_favorites()
        broadcast_event("soundboard_favorites_updated", {"favorites": favs, "clientId": client_id})
    return jsonify(res)


@soundboard_bp.route('/api/soundboard/login_window', methods=['POST'])
def soundboard_login_window():
    """Abre la ventana nativa de escritorio o navegador para iniciar sesión en MyInstants."""
    try:
        import importlib
        app_mod = importlib.import_module("app")
        if hasattr(app_mod, "open_myinstants_login_window"):
            success = app_mod.open_myinstants_login_window()
            return jsonify({"success": success})
    except Exception:
        pass

    if browser_mgr and hasattr(browser_mgr, "open_myinstants_login"):
        threading.Thread(target=browser_mgr.open_myinstants_login, daemon=True).start()
        return jsonify({"success": True})

    webbrowser.open("https://www.myinstants.com/en/favorites/")
    return jsonify({"success": True, "fallback": "browser"})


@soundboard_bp.route('/api/soundboard/favorites', methods=['GET', 'POST'])
def soundboard_favorites():
    """Obtiene o agrega a la lista persistida de favoritos con sincronización en la nube."""
    if request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
        res = soundboard_mgr.add_favorite(data)
        favs = res.get('favorites', res) if isinstance(res, dict) else res
        client_id = data.get('clientId') or data.get('client_id')
        if broadcast_event:
            broadcast_event("soundboard_favorites_updated", {"favorites": favs, "clientId": client_id})
        return jsonify(res)
    return jsonify(soundboard_mgr.get_saved_favorites())


@soundboard_bp.route('/api/soundboard/favorites/remove', methods=['POST'])
def soundboard_favorites_remove():
    """Elimina un sonido de los favoritos."""
    data = request.get_json(force=True, silent=True) or {}
    sound_id = data.get('id') or data.get('title') or data.get('mp3')
    favs = soundboard_mgr.remove_favorite(sound_id)
    client_id = data.get('clientId') or data.get('client_id')
    if broadcast_event:
        broadcast_event("soundboard_favorites_updated", {"favorites": favs, "clientId": client_id})
    return jsonify(favs)


@soundboard_bp.route('/api/soundboard/play', methods=['POST'])
def soundboard_play():
    """Reproduce el audio en la PC anfitriona (Linux PipeWire/ALSA)."""
    data = request.get_json(force=True, silent=True) or {}
    mp3_url = data.get('mp3') or data.get('url', '')
    title = data.get('title', '')
    cfg = load_config() if load_config else {}
    vol = data.get('volume')
    if vol is None:
        vol = cfg.get('soundboard_volume', 80)
    res = soundboard_mgr.play(mp3_url, title, vol)
    client_id = data.get('clientId') or data.get('client_id')
    if broadcast_event:
        broadcast_event("soundboard_play", {"title": title, "mp3": mp3_url, "volume": vol, "clientId": client_id})
    return jsonify(res)


@soundboard_bp.route('/api/soundboard/volume', methods=['POST'])
def soundboard_volume():
    """Actualiza y persiste el volumen predeterminado de la botonera."""
    data = request.get_json(force=True, silent=True) or {}
    vol = data.get('volume', 80)
    res = soundboard_mgr.set_volume(vol)
    vol_val = res.get("volume", vol)
    client_id = data.get('clientId') or data.get('client_id')
    if broadcast_event:
        broadcast_event("soundboard_volume", {"volume": vol_val, "clientId": client_id})
    return jsonify(res)


@soundboard_bp.route('/api/soundboard/stop', methods=['POST'])
def soundboard_stop():
    """Detiene cualquier sonido en reproducción en la PC."""
    data = request.get_json(force=True, silent=True) or {}
    res = soundboard_mgr.stop_all()
    client_id = data.get('clientId') or data.get('client_id')
    if broadcast_event:
        broadcast_event("soundboard_stop", {"clientId": client_id})
    return jsonify(res)


@soundboard_bp.route('/api/soundboard/sync_account', methods=['POST'])
def soundboard_sync_account():
    """Sincroniza favoritos de la cuenta o perfil de MyInstants."""
    data = request.get_json(force=True, silent=True) or {}
    username = data.get('username', '').strip()
    if not username and load_config:
        cfg = load_config()
        username = cfg.get('soundboard_username', '')

    if not username:
        return jsonify({'ok': False, 'error': 'Usuario requerido'}), 400

    def _sync():
        res = soundboard_mgr.sync_account(username)
        if broadcast_event:
            favs = soundboard_mgr.get_saved_favorites()
            broadcast_event("soundboard_favorites_updated", {"favorites": favs})
    threading.Thread(target=_sync, daemon=True).start()
    return jsonify({'ok': True})


@soundboard_bp.route('/api/soundboard/account')
def soundboard_account():
    status = soundboard_mgr.get_auth_status()
    return jsonify(status)


@soundboard_bp.route('/api/soundboard/audio/<path:filename>')
def serve_soundboard_audio(filename):
    cache_dir = soundboard_mgr.cache_dir
    return send_from_directory(cache_dir, filename)