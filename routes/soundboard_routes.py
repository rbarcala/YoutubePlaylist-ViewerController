from flask import Blueprint, request, jsonify, send_from_directory
import os
import json
import threading

soundboard_bp = Blueprint('soundboard', __name__)

# Variables que se inyectan desde server.py
soundboard_mgr = None
load_config = None
save_config = None
broadcast_event = None
browser_mgr = None

def init_soundboard_routes(sb_mgr, config_loader, config_saver, broadcast_fn, br_mgr):
    global soundboard_mgr, load_config, save_config, broadcast_event, browser_mgr
    soundboard_mgr = sb_mgr
    load_config = config_loader
    save_config = config_saver
    broadcast_event = broadcast_fn
    browser_mgr = br_mgr


@soundboard_bp.route('/api/soundboard/regional')
def soundboard_regional():
    region = request.args.get('region', 'ES')
    page = int(request.args.get('page', 1))
    result = soundboard_mgr.get_regional(region, page)
    return jsonify(result)


@soundboard_bp.route('/api/soundboard/trending')
def soundboard_trending():
    result = soundboard_mgr.get_regional('trending', 1)
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
    return jsonify({'ok': False, 'error': 'Gestor de navegador no disponible'}), 500


@soundboard_bp.route('/api/soundboard/auth', methods=['GET', 'POST'])
def soundboard_auth():
    if request.method == 'GET':
        cfg = load_config()
        cookie = cfg.get('soundboard_session_cookie', '')
        return jsonify({'authenticated': bool(cookie)})
    
    data = request.get_json() or {}
    cookie = data.get('cookie')
    if not cookie:
        return jsonify({'ok': False, 'error': 'Cookie requerida'}), 400
    
    cfg = load_config()
    cfg['soundboard_session_cookie'] = cookie
    save_config(cfg)
    
    if broadcast_event:
        broadcast_event('soundboard_auth', {'authenticated': True})
    
    return jsonify({'ok': True})


@soundboard_bp.route('/api/soundboard/login_window', methods=['POST'])
def soundboard_login_window():
    # Abrir ventana de login para MyInstants
    if browser_mgr:
        threading.Thread(target=browser_mgr.open_myinstants_login, daemon=True).start()
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Gestor de navegador no disponible'}), 500


@soundboard_bp.route('/api/soundboard/favorites', methods=['GET'])
def soundboard_favorites():
    cfg = load_config()
    username = cfg.get('soundboard_username', '')
    if username:
        favorites = soundboard_mgr.get_user_favorites(username)
        return jsonify({'favorites': favorites})
    return jsonify({'favorites': []})


@soundboard_bp.route('/api/soundboard/play', methods=['POST'])
def soundboard_play():
    data = request.get_json() or {}
    url = data.get('url')
    
    if not url:
        return jsonify({'ok': False, 'error': 'URL requerida'}), 400
    
    # Extraer info del sound desde la URL de MyInstants
    sound_info = {'url': url, 'name': 'Unknown'}
    ok = soundboard_mgr.play(sound_info)
    return jsonify({'ok': ok})


@soundboard_bp.route('/api/soundboard/volume', methods=['POST'])
def soundboard_volume():
    data = request.get_json() or {}
    volume = data.get('volume')
    if volume is None:
        return jsonify({'ok': False, 'error': 'volume requerido'}), 400
    
    cfg = load_config()
    cfg['soundboard_volume'] = volume
    save_config(cfg)
    soundboard_mgr.current_volume = volume
    return jsonify({'ok': True})


@soundboard_bp.route('/api/soundboard/stop', methods=['POST'])
def soundboard_stop():
    soundboard_mgr.stop_all()
    return jsonify({'ok': True})


@soundboard_bp.route('/api/soundboard/sync_account', methods=['POST'])
def soundboard_sync_account():
    data = request.get_json() or {}
    username = data.get('username')
    
    if not username:
        return jsonify({'ok': False, 'error': 'Usuario requerido'}), 400
    
    threading.Thread(target=soundboard_mgr.sync_account, args=(username,), daemon=True).start()
    return jsonify({'ok': True})


@soundboard_bp.route('/api/soundboard/account')
def soundboard_account():
    status = soundboard_mgr.get_auth_status()
    return jsonify(status)


@soundboard_bp.route('/api/soundboard/audio/<path:filename>')
def serve_soundboard_audio(filename):
    cache_dir = soundboard_mgr.cache_dir
    return send_from_directory(cache_dir, filename)