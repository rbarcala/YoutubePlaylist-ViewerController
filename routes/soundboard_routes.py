import os
import json
import shutil
import subprocess
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
    target_url = request.args.get('url') or ''
    if not target_url and request.is_json:
        data = request.get_json(silent=True) or {}
        target_url = data.get('url', '')
    if not target_url:
        target_url = request.form.get('url', '')
    if not target_url:
        target_url = "https://www.myinstants.com"

    # Resolver rutas relativas si se pasaron
    if target_url.startswith('/'):
        cfg = load_config() if load_config else {}
        port = cfg.get('port', 8000)
        target_url = f"http://127.0.0.1:{port}{target_url}"

    if browser_mgr and hasattr(browser_mgr, 'open_url'):
        browser_mgr.open_url(target_url)
    elif browser_mgr and hasattr(browser_mgr, 'open_myinstants_tab') and target_url == "https://www.myinstants.com":
        browser_mgr.open_myinstants_tab()
    else:
        try:
            if shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", target_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                webbrowser.open(target_url)
        except Exception:
            webbrowser.open(target_url)

    return jsonify({'ok': True, 'url': target_url})


from services.browser_cookie_detector import (
    detect_myinstants_session,
    SessionLoginWatcher
)

active_login_watcher = None


def _handle_session_detected(session_data, client_id=None):
    username = session_data.get("username", "")
    sessionid = session_data.get("sessionid", "")
    csrftoken = session_data.get("csrftoken", "")
    res = soundboard_mgr.save_auth(username, sessionid, csrftoken)
    if broadcast_event:
        broadcast_event("soundboard_auth_success", {
            "username": res.get("username", ""),
            "has_session": res.get("has_session", False),
            "clientId": client_id,
            "browser": session_data.get("browser", "Navegador")
        })
        favs = soundboard_mgr.get_saved_favorites()
        broadcast_event("soundboard_favorites_updated", {"favorites": favs, "clientId": client_id})
    return res


@soundboard_bp.route('/api/soundboard/detect_browser_session', methods=['GET'])
def detect_browser_session_route():
    try:
        session_info = detect_myinstants_session()
        return jsonify(session_info)
    except Exception as e:
        return jsonify({"found": False, "error": str(e)})


@soundboard_bp.route('/api/soundboard/import_browser_session', methods=['POST'])
def import_browser_session_route():
    data = request.get_json(force=True, silent=True) or {}
    client_id = data.get("clientId") or data.get("client_id")
    try:
        session_info = detect_myinstants_session()
        if session_info.get("found"):
            res = _handle_session_detected(session_info, client_id=client_id)
            return jsonify({
                "success": True,
                "username": res.get("username", ""),
                "has_session": res.get("has_session", False),
                "browser": session_info.get("browser", "Navegador")
            })
        return jsonify({
            "success": False,
            "error": "No se encontró ninguna sesión activa en los navegadores del sistema."
        }), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@soundboard_bp.route('/api/soundboard/auth', methods=['GET', 'POST'])
def soundboard_auth():
    if request.method == 'GET':
        status = soundboard_mgr.get_auth_status()
        if not status.get("has_session"):
            try:
                det = detect_myinstants_session()
                if det.get("found"):
                    status["browser_session_available"] = True
                    status["detected_username"] = det.get("username", "")
                    status["detected_browser"] = det.get("browser", "Navegador")
            except Exception:
                pass
        return jsonify(status)

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
    """Abre el navegador para iniciar sesión y vigila en segundo plano para vincular la sesión automáticamente."""
    global active_login_watcher
    data = request.get_json(force=True, silent=True) or {}
    client_id = data.get("clientId") or data.get("client_id")

    # 1. Comprobar si ya existe una sesión activa en el navegador
    try:
        existing = detect_myinstants_session()
        if existing.get("found"):
            res = _handle_session_detected(existing, client_id=client_id)
            return jsonify({
                "success": True,
                "auto_imported": True,
                "username": res.get("username", ""),
                "browser": existing.get("browser", "Navegador")
            })
    except Exception:
        pass

    # 2. Iniciar watcher para capturar la sesión en segundo plano
    if active_login_watcher:
        try:
            active_login_watcher.stop()
        except Exception:
            pass

    def on_detected(sess_info):
        _handle_session_detected(sess_info, client_id=client_id)

    active_login_watcher = SessionLoginWatcher(on_detected, poll_interval=1.5, timeout=180.0)
    active_login_watcher.start()

    # 3. Abrir la página de favoritos / login de MyInstants en el navegador del sistema
    target_url = "https://www.myinstants.com/en/favorites/"
    if browser_mgr and hasattr(browser_mgr, "open_url"):
        browser_mgr.open_url(target_url)
    elif browser_mgr and hasattr(browser_mgr, "open_myinstants_tab"):
        browser_mgr.open_myinstants_tab()
    else:
        try:
            if shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", target_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                webbrowser.open(target_url)
        except Exception:
            webbrowser.open(target_url)

    return jsonify({"success": True, "fallback": "browser", "watching": True})


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