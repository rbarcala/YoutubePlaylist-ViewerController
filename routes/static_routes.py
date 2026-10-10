import json
import time
import queue
import socket
import threading
import webbrowser
from flask import Blueprint, request, jsonify, send_from_directory, Response, redirect, render_template
from services.qr_svg import generate_qr_svg

static_bp = Blueprint('static', __name__)

# Variables globales que serán inyectadas desde server.py
current_state = {}
ws_manager = None
broadcast_event = None
browser_mgr = None
obs_scenes_cache = {"scenes": [], "current_scene": ""}
obs_scenes_lock = threading.Lock()
video_manager = None
load_config = None
save_config = None


def init_static_routes(
    state,
    ws_manager_inst,
    obs_cache,
    obs_lck,
    video_manager_inst,
    config_loader=None,
    config_saver=None,
    broadcast_fn=None,
    browser_manager_inst=None,
):
    global current_state, ws_manager, broadcast_event
    global obs_scenes_cache, obs_scenes_lock
    global video_manager, load_config, save_config, browser_mgr

    current_state = state
    ws_manager = ws_manager_inst
    broadcast_event = broadcast_fn or (ws_manager_inst.broadcast_event if ws_manager_inst else None)
    obs_scenes_cache = obs_cache
    obs_scenes_lock = obs_lck
    video_manager = video_manager_inst
    load_config = config_loader
    save_config = config_saver
    browser_mgr = browser_manager_inst


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
    try:
        return render_template('controller.html')
    except Exception:
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
    """Stream de Server-Sent Events (SSE) para sincronización en tiempo real."""
    client_type = request.args.get('client', '')
    client_id = request.args.get('id', '')
    is_viewer = (client_type == 'viewer')

    if is_viewer and client_id and ws_manager:
        with ws_manager.viewer_lock:
            ws_manager.active_viewers.add(client_id)
            current_state["activeViewers"] = len(ws_manager.active_viewers)
            if broadcast_event:
                broadcast_event("state", current_state)

    q = queue.Queue(maxsize=50)
    if ws_manager:
        ws_manager.add_listener(q)
        current_state["activeControllers"] = max(1, len(ws_manager.listeners))

    # Enviar estado actual de inmediato al conectar
    init_msg = json.dumps({"type": "sync_state", "data": current_state, "timestamp": time.time()})
    q.put(f"event: sync_state\ndata: {init_msg}\n\n")

    def event_stream():
        try:
            while True:
                try:
                    msg = q.get(timeout=15)
                    yield msg
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            if ws_manager:
                ws_manager.remove_listener(q)
                current_state["activeControllers"] = len(ws_manager.listeners)
            if is_viewer and client_id and ws_manager:
                with ws_manager.viewer_lock:
                    ws_manager.active_viewers.discard(client_id)
                    current_state["activeViewers"] = len(ws_manager.active_viewers)
                    if broadcast_event:
                        broadcast_event("state", current_state)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@static_bp.route('/api/action', methods=['POST'])
def handle_action():
    """Recibe acciones de cualquier controlador y las replica a todos los dispositivos."""
    data = request.get_json(force=True, silent=True) or {}
    action_type = data.get("action")
    cfg = load_config() if load_config else {}

    if action_type == "play":
        current_state["videoId"] = data.get("videoId", "")
        current_state["title"] = data.get("title", "")
        current_state["thumb"] = data.get("thumb", "")
        current_state["isPlaying"] = True
        current_state["lastAction"] = "play"
        current_state["updatedAt"] = time.time()

        if save_config:
            save_config({
                "last_played_video_id": current_state["videoId"],
                "last_played_title": current_state["title"]
            })

        if cfg.get("obs_enabled") and cfg.get("obs_scene_on_play"):
            def _switch_obs():
                try:
                    from services.obs_client import OBSController
                    obs = OBSController(
                        host=cfg.get("obs_host", "localhost"),
                        port=cfg.get("obs_port", 4455),
                        password=cfg.get("obs_password", "")
                    )
                    obs.switch_scene(cfg.get("obs_scene_on_play"))
                except Exception:
                    pass
            threading.Thread(target=_switch_obs, daemon=True).start()

        if cfg.get("auto_focus_viewer", True) and browser_mgr:
            threading.Thread(target=browser_mgr.focus_viewer, daemon=True).start()

    elif action_type == "state":
        if "playbackRate" in data:
            current_state["playbackRate"] = float(data["playbackRate"])
        if "muted" in data:
            current_state["muted"] = bool(data["muted"])
        current_state["lastAction"] = "state"
        current_state["updatedAt"] = time.time()

    elif action_type == "viewer_ready":
        current_state["activeViewers"] = current_state.get("activeViewers", 0) + 1
        current_state["lastAction"] = "viewer_ready"

    elif action_type == "viewer_closed":
        current_state["activeViewers"] = max(0, current_state.get("activeViewers", 1) - 1)
        current_state["lastAction"] = "viewer_closed"

    elif action_type == "obs_switch":
        scene = data.get("scene")
        if scene:
            try:
                from services.obs_client import OBSController
                obs = OBSController(
                    host=cfg.get("obs_host", "localhost"),
                    port=cfg.get("obs_port", 4455),
                    password=cfg.get("obs_password", "")
                )
                result = obs.switch_scene(scene)
                if broadcast_event:
                    broadcast_event("obs_updated", {"scene": scene, "result": result})
                return jsonify(result)
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 500

    if broadcast_event:
        broadcast_event(action_type or "update", current_state)
    return jsonify({"success": True, "state": current_state})


@static_bp.route('/api/network_info')
def network_info():
    def get_lan_ip():
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass

    cfg = load_config() if load_config else {}
    port = cfg.get("port", 8000)
    lan_ip = get_lan_ip()
    controller_url = f"http://{lan_ip}:{port}/controller.html"
    viewer_url = f"http://localhost:{port}/viewer.html"

    qr_svg = generate_qr_svg(controller_url, size=240)

    return jsonify({
        "ip": lan_ip,
        "lan_ip": lan_ip,
        "port": port,
        "url": controller_url,
        "controller_url": controller_url,
        "viewer_url": viewer_url,
        "overlay_url": f"http://{lan_ip}:{port}/overlay.html",
        "qr_code_svg": qr_svg
    })


@static_bp.route('/api/open_viewer', methods=['GET', 'POST'])
def open_smart_viewer():
    data = request.get_json(force=True, silent=True) or {}
    target = data.get("target", "viewer")
    cfg = load_config() if load_config else {}
    port = cfg.get("port", 8000)

    if target == "viewer" or request.path == "/api/open_viewer":
        viewer_url = f"http://localhost:{port}/viewer.html"
        if browser_mgr:
            res = browser_mgr.open_smart_viewer(viewer_url, port=port)
            return jsonify(res)
        webbrowser.open(viewer_url)
        return jsonify({"success": True, "url": viewer_url})
    else:
        url = f"http://localhost:{port}/controller.html"
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
        return jsonify({"success": True, "url": url})


@static_bp.route('/api/focus_viewer', methods=['POST'])
def focus_viewer_route():
    """Pone la pestaña/ventana del Viewer en primer plano en el sistema operativo."""
    focused = browser_mgr.focus_viewer() if browser_mgr else False
    if broadcast_event:
        broadcast_event("focus_viewer", {})
    return jsonify({"success": True, "focused": focused})