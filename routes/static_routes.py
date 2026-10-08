from flask import Blueprint, request, jsonify, send_from_directory, Response, redirect
import time
import threading
import queue

static_bp = Blueprint('static', __name__)

# Variables globales que serán inyectadas desde server.py
current_state = {}
ws_manager = None
obs_scenes_cache = {"scenes": [], "current_scene": ""}
obs_scenes_lock = threading.Lock()
video_manager = None
load_config = None


def init_static_routes(state, ws_manager_inst, obs_cache, obs_lck, video_manager_inst, config_loader=None):
    global current_state, ws_manager
    global obs_scenes_cache, obs_scenes_lock
    global video_manager, load_config
    
    current_state = state
    ws_manager = ws_manager_inst
    obs_scenes_cache = obs_cache
    obs_scenes_lock = obs_lck
    video_manager = video_manager_inst
    load_config = config_loader


@static_bp.after_request
def add_cache_headers(response):
    if request.path.endswith('.html') or request.path in ['/', '/controller', '/viewer', '/sw.js']:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@static_bp.route('/')
def index():
    return redirect('/controller')


@static_bp.route('/viewer')
@static_bp.route('/viewer.html')
def serve_viewer():
    return send_from_directory('static', 'viewer.html')


@static_bp.route('/controller')
@static_bp.route('/controller.html')
def serve_controller():
    return send_from_directory('static', 'controller.html')


@static_bp.route('/overlay')
@static_bp.route('/overlay.html')
def serve_overlay():
    return send_from_directory('static', 'overlay.html')


@static_bp.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')


@static_bp.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js')


@static_bp.route('/app.apk')
@static_bp.route('/download/apk')
def serve_apk():
    return send_from_directory('.', 'youtube-stream-controller.apk')


@static_bp.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)


@static_bp.route('/api/state')
def get_state():
    return jsonify(current_state)


@static_bp.route('/api/events')
def sse_events():
    q = queue.Queue()
    if ws_manager:
        ws_manager.add_listener(q)
    
    def event_stream():
        try:
            while True:
                payload = q.get()
                yield payload
        except GeneratorExit:
            pass
        finally:
            if ws_manager:
                ws_manager.remove_listener(q)
    
    return Response(event_stream(), mimetype='text/event-stream')


@static_bp.route('/api/action', methods=['POST'])
def handle_action():
    from flask import current_app
    data = request.get_json() or {}
    action = data.get('action')
    
    # Las acciones se delegan a los managers correspondientes
    # que se registran vía init_static_routes
    if hasattr(current_app, 'action_handlers') and action in current_app.action_handlers:
        return current_app.action_handlers[action](data)
    
    return jsonify({'ok': False, 'error': f'Acción desconocida: {action}'}), 400


@static_bp.route('/api/network_info')
def network_info():
    import socket
    def get_lan_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    lan_ip = get_lan_ip()
    cfg = load_config() if load_config else {}
    port = cfg.get('port', 8000)
    return jsonify({
        'lan_ip': lan_ip,
        'port': port,
        'url': f'http://{lan_ip}:{port}/controller.html',
        'viewer_url': f'http://{lan_ip}:{port}/viewer.html',
        'overlay_url': f'http://{lan_ip}:{port}/overlay.html',
    })