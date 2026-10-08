from flask import Blueprint, request, jsonify
import json
from obs_client import OBSController

obs_bp = Blueprint('obs', __name__)

# Variables que se inyectan desde server.py
load_config = None
broadcast_event = None
obs_scenes_cache = None
obs_scenes_lock = None

def init_obs_routes(config_loader, broadcast_fn, scenes_cache, scenes_lock):
    global load_config, broadcast_event, obs_scenes_cache, obs_scenes_lock
    load_config = config_loader
    broadcast_event = broadcast_fn
    obs_scenes_cache = scenes_cache
    obs_scenes_lock = scenes_lock


def _get_obs_controller():
    cfg = load_config()
    return OBSController(
        host=cfg.get('obs_host', 'localhost'),
        port=cfg.get('obs_port', 4455),
        password=cfg.get('obs_password', '')
    )


@obs_bp.route('/api/obs/status')
def get_obs_status():
    obs = _get_obs_controller()
    sock = obs._connect_and_identify()
    if sock:
        sock.close()
        return jsonify({'connected': True})
    return jsonify({'connected': False})


@obs_bp.route('/api/obs/scenes')
def get_obs_scenes():
    obs = _get_obs_controller()
    sock = obs._connect_and_identify()
    if sock:
        # Solicitar lista de escenas
        obs._send_ws_frame(sock, json.dumps({"op": 6, "d": {"requestType": "GetSceneList"}}))
        response = obs._recv_ws_frame(sock)
        sock.close()
        if response:
            try:
                data = json.loads(response)
                scenes_data = data.get("d", {}).get("responseData", {})
                scenes = [s.get("sceneName") for s in scenes_data.get("scenes", [])]
                with obs_scenes_lock:
                    obs_scenes_cache['scenes'] = scenes
                return jsonify({'scenes': scenes})
            except Exception:
                pass
    with obs_scenes_lock:
        return jsonify({'scenes': obs_scenes_cache['scenes']})


@obs_bp.route('/api/obs/switch', methods=['POST'])
def obs_switch():
    data = request.get_json() or {}
    scene_name = data.get('scene')
    if not scene_name:
        return jsonify({'ok': False, 'error': 'Nombre de escena requerido'}), 400
    
    obs = _get_obs_controller()
    sock = obs._connect_and_identify()
    if sock:
        obs._send_ws_frame(sock, json.dumps({
            "op": 6,
            "d": {"requestType": "SetCurrentProgramScene", "requestData": {"sceneName": scene_name}}
        }))
        sock.close()
        with obs_scenes_lock:
            obs_scenes_cache['current_scene'] = scene_name
        if broadcast_event:
            broadcast_event('obs_updated', {'scene': scene_name})
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'No se pudo conectar a OBS'}), 500


@obs_bp.route('/api/obs/toggle_stream', methods=['POST'])
def obs_toggle_stream():
    obs = _get_obs_controller()
    sock = obs._connect_and_identify()
    if sock:
        obs._send_ws_frame(sock, json.dumps({"op": 6, "d": {"requestType": "ToggleStream"}}))
        response = obs._recv_ws_frame(sock)
        sock.close()
        if response:
            try:
                data = json.loads(response)
                state = data.get("d", {}).get("responseData", {}).get("outputActive", False)
                if broadcast_event:
                    broadcast_event('obs_stream_state', {'streaming': state})
                return jsonify({'ok': True, 'streaming': state})
            except Exception:
                pass
    return jsonify({'ok': False, 'error': 'No se pudo conectar a OBS'}), 500


@obs_bp.route('/api/obs/credentials')
def get_obs_credentials():
    cfg = load_config()
    return jsonify({
        'host': cfg.get('obs_host', 'localhost'),
        'port': cfg.get('obs_port', 4455),
        'password': cfg.get('obs_password', '')
    })


@obs_bp.route('/api/obs/auth', methods=['POST'])
def generate_obs_auth():
    # Generar contraseña aleatoria para OBS WebSocket
    import secrets
    pwd = secrets.token_urlsafe(16)
    cfg = load_config()
    cfg['obs_password'] = pwd
    from config_manager import save_config
    save_config(cfg)
    if broadcast_event:
        broadcast_event('config_updated', cfg)
    return jsonify({'ok': True, 'password': pwd})


@obs_bp.route('/api/obs/start_virtual_cam', methods=['POST'])
def start_obs_virtual_cam():
    obs = _get_obs_controller()
    sock = obs._connect_and_identify()
    if sock:
        obs._send_ws_frame(sock, json.dumps({"op": 6, "d": {"requestType": "StartVirtualCam"}}))
        sock.close()
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'No se pudo conectar a OBS'}), 500


@obs_bp.route('/api/obs/toggle_record', methods=['POST'])
def obs_toggle_record():
    obs = _get_obs_controller()
    sock = obs._connect_and_identify()
    if sock:
        obs._send_ws_frame(sock, json.dumps({"op": 6, "d": {"requestType": "ToggleRecord"}}))
        response = obs._recv_ws_frame(sock)
        sock.close()
        if response:
            try:
                data = json.loads(response)
                state = data.get("d", {}).get("responseData", {}).get("outputActive", False)
                if broadcast_event:
                    broadcast_event('obs_record_state', {'recording': state})
                return jsonify({'ok': True, 'recording': state})
            except Exception:
                pass
    return jsonify({'ok': False, 'error': 'No se pudo conectar a OBS'}), 500


@obs_bp.route('/api/obs/audio/volume', methods=['POST'])
def set_obs_audio_volume():
    data = request.get_json() or {}
    input_name = data.get('input')
    volume = data.get('volume')
    if input_name is None or volume is None:
        return jsonify({'ok': False, 'error': 'Parámetros requeridos: input, volume'}), 400
    
    obs = _get_obs_controller()
    sock = obs._connect_and_identify()
    if sock:
        obs._send_ws_frame(sock, json.dumps({
            "op": 6,
            "d": {
                "requestType": "SetInputVolume",
                "requestData": {
                    "inputName": input_name,
                    "volumeDb": volume
                }
            }
        }))
        sock.close()
        if broadcast_event:
            broadcast_event('obs_audio_changed', {'input': input_name, 'volume': volume})
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'No se pudo conectar a OBS'}), 500


@obs_bp.route('/api/obs/audio/mute', methods=['POST'])
def set_obs_audio_mute():
    data = request.get_json() or {}
    input_name = data.get('input')
    muted = data.get('muted')
    if input_name is None or muted is None:
        return jsonify({'ok': False, 'error': 'Parámetros requeridos: input, muted'}), 400
    
    obs = _get_obs_controller()
    sock = obs._connect_and_identify()
    if sock:
        obs._send_ws_frame(sock, json.dumps({
            "op": 6,
            "d": {
                "requestType": "SetInputMute",
                "requestData": {
                    "inputName": input_name,
                    "inputMuted": muted
                }
            }
        }))
        sock.close()
        if broadcast_event:
            broadcast_event('obs_audio_changed', {'input': input_name, 'muted': muted})
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'No se pudo conectar a OBS'}), 500