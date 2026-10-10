import json
import base64
import hashlib
import secrets
import threading
from pathlib import Path
from flask import Blueprint, request, jsonify
from services.obs_client import OBSController
from core.env_checker import is_obs_running, launch_obs_if_needed

obs_bp = Blueprint('obs', __name__)

BASE_DIR = Path(__file__).resolve().parent.parent

# Variables que se inyectan desde server.py
load_config = None
broadcast_event = None
obs_scenes_cache = {"scenes": [], "current_scene": ""}
obs_scenes_lock = threading.Lock()


def init_obs_routes(config_loader, broadcast_fn, scenes_cache, scenes_lock):
    global load_config, broadcast_event, obs_scenes_cache, obs_scenes_lock
    load_config = config_loader
    broadcast_event = broadcast_fn
    obs_scenes_cache = scenes_cache
    obs_scenes_lock = scenes_lock


def _get_obs_controller():
    cfg = load_config() if load_config else {}
    return OBSController(
        host=cfg.get('obs_host', 'localhost'),
        port=cfg.get('obs_port', 4455),
        password=cfg.get('obs_password', '')
    )


@obs_bp.route('/api/open_obs', methods=['POST'])
def open_obs_route():
    """Abre OBS Studio en segundo plano si no está corriendo."""
    try:
        running = is_obs_running()
        if not running:
            cfg = load_config() if load_config else {}
            threading.Thread(target=launch_obs_if_needed, args=(cfg, BASE_DIR), daemon=True).start()
        return jsonify({"success": True, "was_running": running})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@obs_bp.route('/api/obs/status')
def get_obs_status():
    obs = _get_obs_controller()
    return jsonify(obs.get_status())


@obs_bp.route('/api/obs/scenes')
def get_obs_scenes():
    obs = _get_obs_controller()
    res = obs.get_scenes() if hasattr(obs, 'get_scenes') else {'scenes': obs.get_scene_list()}
    scenes = res.get('scenes', []) if isinstance(res, dict) else (res or [])
    current_scene = res.get('current_scene', '') if isinstance(res, dict) else ''
    if scenes:
        with obs_scenes_lock:
            obs_scenes_cache['scenes'] = scenes
            if current_scene:
                obs_scenes_cache['current_scene'] = current_scene
        return jsonify({'scenes': scenes, 'current_scene': current_scene})
    with obs_scenes_lock:
        return jsonify({'scenes': obs_scenes_cache.get('scenes', []), 'current_scene': obs_scenes_cache.get('current_scene', '')})


@obs_bp.route('/api/obs/switch', methods=['POST'])
def obs_switch():
    data = request.get_json(force=True, silent=True) or {}
    scene_name = data.get('scene') or data.get('scene_name')
    if not scene_name:
        return jsonify({'success': False, 'error': 'Nombre de escena requerido'}), 400

    obs = _get_obs_controller()
    res = obs.switch_scene(scene_name)
    if res.get("success"):
        with obs_scenes_lock:
            obs_scenes_cache['current_scene'] = scene_name
        if broadcast_event:
            broadcast_event('obs_scene_changed', {'scene': scene_name})
            broadcast_event('obs_updated', {'scene': scene_name})
        return jsonify(res)
    return jsonify(res), 400


@obs_bp.route('/api/obs/toggle_stream', methods=['POST'])
def obs_toggle_stream():
    obs = _get_obs_controller()
    res = obs.toggle_stream()
    if broadcast_event:
        broadcast_event("obs_status_changed", res)
    return jsonify(res)


@obs_bp.route('/api/obs/toggle_record', methods=['POST'])
def obs_toggle_record():
    obs = _get_obs_controller()
    res = obs.toggle_record()
    if broadcast_event:
        broadcast_event("obs_status_changed", res)
    return jsonify(res)


@obs_bp.route('/api/obs/start_virtual_cam', methods=['POST'])
def start_obs_virtual_cam():
    obs = _get_obs_controller()
    return jsonify(obs.start_virtual_cam())


@obs_bp.route('/api/obs/video_settings')
def get_obs_video_settings():
    obs = _get_obs_controller()
    return jsonify(obs.get_video_settings())


@obs_bp.route('/api/obs/preview')
def get_obs_preview():
    obs = _get_obs_controller()
    scene = request.args.get('scene', '')
    if not scene:
        return jsonify({"success": False, "error": "No scene provided"})
    return jsonify(obs.get_screenshot(scene))


@obs_bp.route('/api/obs/audio')
def get_obs_audio():
    obs = _get_obs_controller()
    res = obs.get_audio_inputs()
    inputs = res.get("inputs", {})
    desktop = inputs.get("desktop", {})
    mic = inputs.get("mic", {})
    return jsonify({
        "connected": res.get("connected", False),
        "desktop": {
            "name": desktop.get("name"),
            "volume_mul": desktop.get("volumeMul", 1.0),
            "volume_db": desktop.get("volumeDb", 0.0),
            "muted": desktop.get("muted", False)
        } if desktop else None,
        "mic": {
            "name": mic.get("name"),
            "volume_mul": mic.get("volumeMul", 1.0),
            "volume_db": mic.get("volumeDb", 0.0),
            "muted": mic.get("muted", False)
        } if mic else None
    })


@obs_bp.route('/api/obs/audio/volume', methods=['POST'])
def set_obs_audio_volume():
    data = request.get_json(force=True, silent=True) or {}
    input_name = data.get("input_name") or data.get("input")
    volume_mul = data.get("volume_mul")
    if volume_mul is None:
        volume_mul = data.get("volume", 1.0)
    if not input_name:
        return jsonify({"success": False, "error": "Falta input_name"}), 400

    obs = _get_obs_controller()
    res = obs.set_input_volume(input_name, float(volume_mul))
    if broadcast_event:
        broadcast_event("obs_audio_changed", {"input_name": input_name, "volume_mul": float(volume_mul)})
    return jsonify(res)


@obs_bp.route('/api/obs/audio/mute', methods=['POST'])
def set_obs_audio_mute():
    data = request.get_json(force=True, silent=True) or {}
    input_name = data.get("input_name") or data.get("input")
    muted = data.get("muted")
    if not input_name:
        return jsonify({"success": False, "error": "Falta input_name"}), 400

    obs = _get_obs_controller()
    res = obs.set_input_mute(input_name, muted)
    if broadcast_event:
        broadcast_event("obs_audio_changed", {"input_name": input_name, "muted": res.get("muted", muted)})
    return jsonify(res)


@obs_bp.route('/api/obs/credentials')
def get_obs_credentials():
    cfg = load_config() if load_config else {}
    return jsonify({
        'host': cfg.get('obs_host', 'localhost'),
        'port': cfg.get('obs_port', 4455),
        'password': cfg.get('obs_password', '')
    })


@obs_bp.route('/api/obs/auth', methods=['POST'])
def generate_obs_auth():
    pwd = secrets.token_urlsafe(16)
    cfg = load_config() if load_config else {}
    cfg['obs_password'] = pwd
    from services.config_manager import save_config
    save_config(cfg)
    if broadcast_event:
        broadcast_event('config_updated', cfg)
    return jsonify({'ok': True, 'password': pwd})