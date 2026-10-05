import os
import re
import sys
import json
import time
import subprocess
import queue
import socket
import threading
import urllib.request
import urllib.parse
import webbrowser
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, Response, redirect

import yt_dlp
from config_manager import load_config, save_config
from obs_client import OBSController
from spotify_manager import SpotifyManager
from soundboard_manager import SoundboardManager
from browser_manager import BrowserManager
from overlay_manager import OverlayManager
from qr_svg import generate_qr_svg

app = Flask(__name__, static_folder='.', static_url_path='')

VIDEO_CACHE_DIR = Path.home() / '.cache' / 'youtube-playlist-vc' / 'videos'
VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
video_download_queue = queue.Queue()
video_download_status = {}
video_download_lock = threading.Lock()

def _cached_video_path(video_id):
    candidates = [
        path for path in VIDEO_CACHE_DIR.glob(f'{video_id}.*')
        if not path.name.endswith(('.part', '.ytdl'))
    ]
    return candidates[0] if candidates else None

def _queue_video_download(video_id):
    with video_download_lock:
        if video_download_status.get(video_id) in ('queued', 'downloading') or _cached_video_path(video_id):
            return
        video_download_status[video_id] = 'queued'
    video_download_queue.put(video_id)

def _video_download_worker():
    while True:
        video_id = video_download_queue.get()
        try:
            with video_download_lock:
                video_download_status[video_id] = 'downloading'
            output_template = str(VIDEO_CACHE_DIR / f'{video_id}.%(ext)s')
            opts = {
                'format': 'best[height<=1080][ext=mp4]/best[height<=1080]/best',
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web']
                    }
                },
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
            with video_download_lock:
                video_download_status[video_id] = 'ready' if _cached_video_path(video_id) else 'error'
        except Exception as exc:
            print(f'[cache] Error descargando {video_id}: {exc}')
            with video_download_lock:
                video_download_status[video_id] = 'error'
        finally:
            video_download_queue.task_done()

threading.Thread(target=_video_download_worker, daemon=True, name='video-cache-worker').start()

@app.after_request
def add_cache_headers(response):
    if request.path.endswith('.html') or request.path in ['/', '/controller', '/viewer', '/sw.js']:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

spotify_mgr = SpotifyManager(load_config, save_config)
soundboard_mgr = SoundboardManager(load_config, save_config)
browser_mgr = BrowserManager()

# ─── ESTADO CENTRALIZADO Y SINCRONIZACIÓN EN TIEMPO REAL ───
initial_cfg = load_config()

current_state = {
    "videoId": initial_cfg.get("last_played_video_id", ""),
    "title": initial_cfg.get("last_played_title", ""),
    "thumb": "",
    "playbackRate": float(initial_cfg.get("default_playback_rate", 1.7)),
    "muted": bool(initial_cfg.get("default_muted", True)),
    "isPlaying": False,
    "activeViewers": 0,
    "activeControllers": 0,
    "soundboard_volume": int(initial_cfg.get("soundboard_volume", 80)),
    "lastAction": "init",
    "updatedAt": time.time()
}

# Cola de eventos SSE para todos los clientes conectados
event_listeners = set()
listeners_lock = threading.Lock()
active_viewer_ids = set()
active_viewer_lock = threading.Lock()
video_cache = {}  # Cache de URLs resueltas por yt-dlp

def broadcast_event(event_type: str, data: dict):
    """Transmite un evento a todos los clientes SSE conectados (Desktop, Web, Móvil, Viewer)."""
    payload = json.dumps({"type": event_type, "data": data, "timestamp": time.time()})
    sse_message = f"event: {event_type}\ndata: {payload}\n\n"
    
    with listeners_lock:
        dead_queues = []
        for q in list(event_listeners):
            try:
                q.put_nowait(sse_message)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(sse_message)
                except Exception:
                    pass
            except Exception:
                dead_queues.append(q)
        for dead in dead_queues:
            event_listeners.discard(dead)

# Gestor de Overlays y Temporizador
overlay_mgr = OverlayManager(broadcast_event, load_config, save_config)
soundboard_mgr.on_idle = lambda: broadcast_event("soundboard_stop", {})

def get_lan_ip():
    """Detecta la IP local de la máquina en la red Wi-Fi / Ethernet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"

# ─── RUTAS ESTÁTICAS Y PRINCIPALES ───
@app.route('/')
def index():
    return send_from_directory('.', 'controller.html')

@app.route('/viewer')
@app.route('/viewer.html')
def serve_viewer():
    return send_from_directory('.', 'viewer.html')

@app.route('/controller')
@app.route('/controller.html')
def serve_controller():
    return send_from_directory('.', 'controller.html')

@app.route('/overlay')
@app.route('/overlay.html')
def serve_overlay():
    return send_from_directory('.', 'overlay.html')

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('.', 'manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('.', 'sw.js', mimetype='application/javascript')

@app.route('/app.apk')
@app.route('/download/apk')
def serve_apk():
    return send_from_directory('release', 'youtube-stream-controller.apk', mimetype='application/vnd.android.package-archive', as_attachment=True)

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# ─── API DE ESTADO Y SINCRONIZACIÓN (SSE) ───
@app.route('/api/state')
def get_state():
    return jsonify(current_state)

@app.route('/api/events')
def sse_events():
    """Stream de Server-Sent Events (SSE) para sincronización en tiempo real."""
    client_type = request.args.get('client', '')
    client_id = request.args.get('id', '')
    is_viewer = (client_type == 'viewer')

    if is_viewer and client_id:
        with active_viewer_lock:
            active_viewer_ids.add(client_id)
            current_state["activeViewers"] = len(active_viewer_ids)
            broadcast_event("state", current_state)

    q = queue.Queue(maxsize=50)
    with listeners_lock:
        event_listeners.add(q)
        current_state["activeControllers"] = max(1, len(event_listeners))

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
            with listeners_lock:
                event_listeners.discard(q)
                current_state["activeControllers"] = len(event_listeners)
            if is_viewer and client_id:
                with active_viewer_lock:
                    active_viewer_ids.discard(client_id)
                    current_state["activeViewers"] = len(active_viewer_ids)
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

@app.route('/api/action', methods=['POST'])
def handle_action():
    """Recibe acciones de cualquier controlador y las replica a todos los dispositivos."""
    data = request.get_json(force=True, silent=True) or {}
    action_type = data.get("action")
    cfg = load_config()

    if action_type == "play":
        current_state["videoId"] = data.get("videoId", "")
        current_state["title"] = data.get("title", "")
        current_state["thumb"] = data.get("thumb", "")
        current_state["isPlaying"] = True
        current_state["lastAction"] = "play"
        current_state["updatedAt"] = time.time()
        
        save_config({
            "last_played_video_id": current_state["videoId"],
            "last_played_title": current_state["title"]
        })

        if cfg.get("obs_enabled") and cfg.get("obs_scene_on_play"):
            def _switch_obs():
                obs = OBSController(
                    host=cfg.get("obs_host", "localhost"),
                    port=cfg.get("obs_port", 4455),
                    password=cfg.get("obs_password", "")
                )
                obs.switch_scene(cfg.get("obs_scene_on_play"))
            threading.Thread(target=_switch_obs, daemon=True).start()

        if cfg.get("auto_focus_viewer", True):
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
            obs = OBSController(
                host=cfg.get("obs_host", "localhost"),
                port=cfg.get("obs_port", 4455),
                password=cfg.get("obs_password", "")
            )
            result = obs.switch_scene(scene)
            broadcast_event("obs_updated", {"scene": scene, "result": result})
            return jsonify(result)

    broadcast_event(action_type or "update", current_state)
    return jsonify({"success": True, "state": current_state})

# ─── API DE CONFIGURACIÓN Y SETUP ───
@app.route('/api/config', methods=['GET', 'POST'])
def manage_config():
    if request.method == 'POST':
        new_data = request.get_json(force=True, silent=True) or {}
        saved = save_config(new_data)
        safe_broadcast = saved.copy()
        safe_broadcast.pop("youtube_api_key", None)
        safe_broadcast.pop("spotify_client_secret", None)
        safe_broadcast.pop("spotify_access_token", None)
        safe_broadcast.pop("spotify_refresh_token", None)
        broadcast_event("config_updated", safe_broadcast)
        return jsonify({"success": True, "config": saved})

    cfg = load_config()
    safe_cfg = cfg.copy()
    raw_key = safe_cfg.get("youtube_api_key", "")
    safe_cfg["has_api_key"] = bool(raw_key)
    safe_cfg["youtube_api_key_masked"] = (raw_key[:4] + "..." + raw_key[-4:]) if len(raw_key) > 8 else ("***" if raw_key else "")
    safe_cfg["has_spotify_secret"] = bool(safe_cfg.get("spotify_client_secret", ""))
    safe_cfg["has_spotify_token"] = bool(safe_cfg.get("spotify_access_token", ""))
    return jsonify(safe_cfg)

# ─── API DE RED Y CÓDIGO QR PARA CELULAR ───
@app.route('/api/network_info')
def network_info():
    cfg = load_config()
    port = cfg.get("port", 8000)
    lan_ip = get_lan_ip()
    controller_url = f"http://{lan_ip}:{port}/controller.html"
    viewer_url = f"http://localhost:{port}/viewer.html"

    qr_svg = generate_qr_svg(controller_url, size=240)

    return jsonify({
        "lan_ip": lan_ip,
        "port": port,
        "controller_url": controller_url,
        "viewer_url": viewer_url,
        "qr_code_svg": qr_svg
    })

# ─── APERTURA INTELIGENTE DEL VIEWER Y NAVEGADOR DEL SISTEMA ───
@app.route('/api/open_viewer', methods=['GET', 'POST'])
def open_smart_viewer():
    data = request.get_json(force=True, silent=True) or {}
    target = data.get("target", "viewer")
    cfg = load_config()
    port = cfg.get("port", 8000)

    if target == "viewer" or request.path == "/api/open_viewer":
        viewer_url = f"http://localhost:{port}/viewer.html"
        res = browser_mgr.open_smart_viewer(viewer_url, port=port)
        return jsonify(res)
    else:
        url = f"http://localhost:{port}/controller.html"
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
        return jsonify({"success": True, "url": url})

@app.route('/api/focus_viewer', methods=['POST'])
def focus_viewer_route():
    """Pone la pestaña/ventana del Viewer en primer plano en el sistema operativo."""
    focused = browser_mgr.focus_viewer()
    broadcast_event("focus_viewer", {})
    return jsonify({"success": True, "focused": focused})

@app.route('/api/open_obs', methods=['POST'])
def open_obs_route():
    """Abre OBS Studio en segundo plano si no está corriendo."""
    try:
        from app import launch_obs_if_needed, is_obs_running
        running = is_obs_running()
        if not running:
            threading.Thread(target=launch_obs_if_needed, daemon=True).start()
        return jsonify({"success": True, "was_running": running})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ─── API OBS STUDIO EXPANDIDA ───
@app.route('/api/obs/status')
def get_obs_status():
    cfg = load_config()
    obs = OBSController(
        host=cfg.get("obs_host", "localhost"),
        port=cfg.get("obs_port", 4455),
        password=cfg.get("obs_password", "")
    )
    return jsonify(obs.get_status())

# Cache de escenas OBS para evitar parpadeos o fallos transitorios en el controller
obs_scenes_cache = {"scenes": [], "current_scene": "", "last_success_time": 0}
obs_scenes_lock = threading.Lock()

@app.route('/api/obs/scenes')
def get_obs_scenes():
    cfg = load_config()
    obs = OBSController(
        host=cfg.get("obs_host", "localhost"),
        port=cfg.get("obs_port", 4455),
        password=cfg.get("obs_password", "")
    )
    res = obs.get_scenes()
    with obs_scenes_lock:
        if res.get("success") and res.get("scenes"):
            obs_scenes_cache["scenes"] = res.get("scenes", [])
            obs_scenes_cache["current_scene"] = res.get("current_scene", "")
            obs_scenes_cache["last_success_time"] = time.time()
            return jsonify(res)
        
        # Si falló la conexión puntual pero tenemos escenas recientes en caché y OBS responde a status o está vivo
        if obs_scenes_cache["scenes"]:
            cached_res = {
                "success": True,
                "scenes": obs_scenes_cache["scenes"],
                "current_scene": obs_scenes_cache["current_scene"],
                "cached": True
            }
            return jsonify(cached_res)
    return jsonify(res)

@app.route('/api/obs/switch', methods=['POST'])
def obs_switch():
    data = request.get_json(force=True, silent=True) or {}
    scene = data.get("scene")
    cfg = load_config()
    obs = OBSController(
        host=cfg.get("obs_host", "localhost"),
        port=cfg.get("obs_port", 4455),
        password=cfg.get("obs_password", "")
    )
    res = obs.switch_scene(scene)
    broadcast_event("obs_updated", {"scene": scene})
    return jsonify(res)

@app.route('/api/obs/toggle_stream', methods=['POST'])
def obs_toggle_stream():
    cfg = load_config()
    obs = OBSController(
        host=cfg.get("obs_host", "localhost"),
        port=cfg.get("obs_port", 4455),
        password=cfg.get("obs_password", "")
    )
    res = obs.toggle_stream()
    broadcast_event("obs_status_changed", res)
    return jsonify(res)

@app.route('/api/obs/credentials')
def get_obs_credentials():
    cfg = load_config()
    return jsonify({
        "host": cfg.get("obs_host", "localhost"),
        "port": cfg.get("obs_port", 4455),
        "password": cfg.get("obs_password", "")
    })

@app.route('/api/obs/auth', methods=['POST'])
def generate_obs_auth():
    cfg = load_config()
    password = cfg.get("obs_password", "")
    data = request.json or {}
    salt = data.get("salt", "")
    challenge = data.get("challenge", "")
    if not password:
        return jsonify({"auth": ""})
        
    import hashlib, base64
    h1 = hashlib.sha256((password + salt).encode('utf-8')).digest()
    h1_b64 = base64.b64encode(h1).decode('utf-8')
    h2 = hashlib.sha256((h1_b64 + challenge).encode('utf-8')).digest()
    auth_response = base64.b64encode(h2).decode('utf-8')
    
    return jsonify({"auth": auth_response})

@app.route('/api/obs/video_settings')
def get_obs_video_settings():
    cfg = load_config()
    obs = OBSController(cfg.get("obs_host", "localhost"), cfg.get("obs_port", 4455), cfg.get("obs_password", ""))
    return jsonify(obs.get_video_settings())

@app.route('/api/obs/preview')
def get_obs_preview():
    cfg = load_config()
    obs = OBSController(cfg.get("obs_host", "localhost"), cfg.get("obs_port", 4455), cfg.get("obs_password", ""))
    scene = request.args.get('scene', '')
    if not scene:
        return jsonify({"success": False, "error": "No scene provided"})
    res = obs.get_screenshot(scene)
    return jsonify(res)

@app.route('/api/obs/start_virtual_cam', methods=['POST'])
def start_obs_virtual_cam():
    cfg = load_config()
    obs = OBSController(cfg.get("obs_host", "localhost"), cfg.get("obs_port", 4455), cfg.get("obs_password", ""))
    return jsonify(obs.start_virtual_cam())

@app.route('/api/obs/toggle_record', methods=['POST'])
def obs_toggle_record():
    cfg = load_config()
    obs = OBSController(
        host=cfg.get("obs_host", "localhost"),
        port=cfg.get("obs_port", 4455),
        password=cfg.get("obs_password", "")
    )
    res = obs.toggle_record()
    broadcast_event("obs_status_changed", res)
    return jsonify(res)

@app.route('/api/obs/audio')
def get_obs_audio():
    cfg = load_config()
    obs = OBSController(
        host=cfg.get("obs_host", "localhost"),
        port=cfg.get("obs_port", 4455),
        password=cfg.get("obs_password", "")
    )
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

@app.route('/api/obs/audio/volume', methods=['POST'])
def set_obs_audio_volume():
    data = request.get_json(force=True, silent=True) or {}
    input_name = data.get("input_name")
    volume_mul = data.get("volume_mul", 1.0)
    if not input_name:
        return jsonify({"success": False, "error": "Falta input_name"}), 400
    cfg = load_config()
    obs = OBSController(
        host=cfg.get("obs_host", "localhost"),
        port=cfg.get("obs_port", 4455),
        password=cfg.get("obs_password", "")
    )
    res = obs.set_input_volume(input_name, float(volume_mul))
    broadcast_event("obs_audio_changed", {"input_name": input_name, "volume_mul": float(volume_mul)})
    return jsonify(res)

@app.route('/api/obs/audio/mute', methods=['POST'])
def set_obs_audio_mute():
    data = request.get_json(force=True, silent=True) or {}
    input_name = data.get("input_name")
    muted = data.get("muted") # None or boolean
    if not input_name:
        return jsonify({"success": False, "error": "Falta input_name"}), 400
    cfg = load_config()
    obs = OBSController(
        host=cfg.get("obs_host", "localhost"),
        port=cfg.get("obs_port", 4455),
        password=cfg.get("obs_password", "")
    )
    res = obs.set_input_mute(input_name, muted)
    broadcast_event("obs_audio_changed", {"input_name": input_name, "muted": res.get("muted", muted)})
    return jsonify(res)

# ─── API SPOTIFY REMOTE ───
@app.route('/api/spotify/auth_url')
def spotify_auth_url():
    redirect_uri = request.host_url.rstrip('/') + '/api/spotify/callback'
    url = spotify_mgr.get_auth_url(redirect_uri)
    return jsonify({"auth_url": url, "redirect_uri": redirect_uri})

@app.route('/api/spotify/callback')
def spotify_callback():
    code = request.args.get("code")
    error = request.args.get("error")
    if error or not code:
        return f"<h3>Error autorizando Spotify: {error}</h3><p><a href='/controller.html'>Volver</a></p>", 400

    redirect_uri = request.host_url.rstrip('/') + '/api/spotify/callback'
    res = spotify_mgr.exchange_code(code, redirect_uri)
    if res.get("success"):
        broadcast_event("spotify_action", {"action": "auth_success"})
        return """
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><title>Spotify Conectado</title></head>
        <body style="background:#121212; color:#fff; font-family:sans-serif; display:flex; flex-direction:column; align-items:center; justify-content:center; height:90vh;">
            <h2 style="color:#1db954;">¡Spotify vinculado con éxito! 🎉</h2>
            <p>Ya puedes cerrar esta pestaña y volver a la aplicación.</p>
        </body>
        </html>
        """
    return f"<h3>Error canjeando código: {res.get('error')}</h3>", 400

@app.route('/api/spotify/seek', methods=['POST'])
def spotify_seek_route():
    data = request.get_json(force=True, silent=True) or {}
    pos = int(data.get("position_ms", 0))
    res = spotify_mgr.seek(pos)
    return jsonify(res)

@app.route('/api/spotify/state')
def spotify_state():
    return jsonify(spotify_mgr.get_playback_state())

@app.route('/api/spotify/play', methods=['POST'])
def spotify_play():
    data = request.get_json(force=True, silent=True) or {}
    res = spotify_mgr.play(context_uri=data.get("context_uri"), track_uris=data.get("track_uris"))
    client_id = data.get("clientId") or data.get("client_id")
    broadcast_event("spotify_action", {"action": "play", "clientId": client_id})
    return jsonify(res)

@app.route('/api/spotify/pause', methods=['POST'])
def spotify_pause():
    data = request.get_json(force=True, silent=True) or {}
    res = spotify_mgr.pause()
    client_id = data.get("clientId") or data.get("client_id")
    broadcast_event("spotify_action", {"action": "pause", "clientId": client_id})
    return jsonify(res)

@app.route('/api/spotify/next', methods=['POST'])
def spotify_next():
    data = request.get_json(force=True, silent=True) or {}
    res = spotify_mgr.next_track()
    client_id = data.get("clientId") or data.get("client_id")
    broadcast_event("spotify_action", {"action": "next", "clientId": client_id})
    return jsonify(res)

@app.route('/api/spotify/previous', methods=['POST'])
def spotify_prev():
    data = request.get_json(force=True, silent=True) or {}
    res = spotify_mgr.previous_track()
    client_id = data.get("clientId") or data.get("client_id")
    broadcast_event("spotify_action", {"action": "previous", "clientId": client_id})
    return jsonify(res)

@app.route('/api/spotify/volume', methods=['POST'])
def spotify_volume():
    data = request.get_json(force=True, silent=True) or {}
    vol = data.get("volume", 50)
    res = spotify_mgr.set_volume(vol)
    client_id = data.get("clientId") or data.get("client_id")
    broadcast_event("spotify_volume", {"volume": vol, "clientId": client_id})
    return jsonify(res)

@app.route('/api/spotify/search')
def spotify_search():
    q = request.args.get("q", "")
    return jsonify(spotify_mgr.search(q))


@app.route('/api/spotify/saved_playlists', methods=['GET', 'POST', 'DELETE'])
def spotify_saved_playlists():
    cfg = load_config()
    playlists = cfg.get("spotify_playlists", [])
    
    if request.method == 'GET':
        return jsonify({"playlists": playlists})
        
    if request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
        pid = data.get("id")
        pname = data.get("name")
        if pid and pname:
            if not any(p["id"] == pid for p in playlists):
                playlists.append({"id": pid, "name": pname})
                save_config({"spotify_playlists": playlists})
        return jsonify({"playlists": playlists})
        
    if request.method == 'DELETE':
        data = request.get_json(force=True, silent=True) or {}
        pid = data.get("id")
        playlists = [p for p in playlists if p["id"] != pid]
        save_config({"spotify_playlists": playlists})
        return jsonify({"playlists": playlists})

@app.route('/api/spotify/playlist')
def spotify_playlist():
    playlist_id = request.args.get("id", "")
    refresh = request.args.get("refresh") == "1"
    return jsonify(spotify_mgr.get_playlist(playlist_id, refresh=refresh))


_lyrics_cache = {}

@app.route('/api/spotify/lyrics')
def spotify_lyrics():
    artist = (request.args.get("artist") or "").strip()
    title = (request.args.get("title") or "").strip()
    if not artist or not title:
        return jsonify({"lyrics": ""})

    cache_key = f"{artist.lower()}|||{title.lower()}"
    if cache_key in _lyrics_cache:
        cached = _lyrics_cache[cache_key]
        return jsonify(cached if isinstance(cached, dict) else {"lyrics": cached})

    # 1. Candidatos de artista (artista principal o lista completa)
    artist_candidates = []
    a1 = re.split(r'[,&]|\s+feat\b|\s+ft\b', artist, flags=re.I)[0].strip()
    if a1:
        artist_candidates.append(a1)
    if artist not in artist_candidates:
        artist_candidates.append(artist)

    # 2. Candidatos de título (eliminar sufijos remaster, live, edit, paréntesis)
    title_candidates = [title]
    t1 = re.sub(r'\s*-\s*(?:\d{4}\s+)?(?:remaster|remastered|live|radio edit|edit|mono|stereo|deluxe|bonus|single|album|mix|acoustic|version|original).*$', '', title, flags=re.I).strip()
    if t1 and t1 not in title_candidates:
        title_candidates.append(t1)
    t2 = re.sub(r'\s*[\(\[].*?[\)\]]', '', t1).strip()
    if t2 and t2 not in title_candidates:
        title_candidates.append(t2)
    t3 = title.split(' - ')[0].strip()
    if t3 and t3 not in title_candidates:
        title_candidates.append(t3)

    ua = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'

    for a in artist_candidates:
        for t in title_candidates:
            # Proveedor A: lrclib.net (base de datos masiva sincronizada para Spotify)
            try:
                url = 'https://lrclib.net/api/get?' + urllib.parse.urlencode({'artist_name': a, 'track_name': t})
                req = urllib.request.Request(url, headers={'User-Agent': ua})
                with urllib.request.urlopen(req, timeout=3) as r:
                    d = json.loads(r.read().decode('utf-8'))
                    synced_lyrics = d.get('syncedLyrics') or ''
                    if synced_lyrics.strip():
                        plain_lyrics = d.get('plainLyrics') or re.sub(r'\[\d{2}:\d{2}(?:\.\d{2,3})?\]\s*', '', synced_lyrics).strip()
                        result = {"lyrics": plain_lyrics, "syncedLyrics": synced_lyrics, "source": "lrclib"}
                        _lyrics_cache[cache_key] = result
                        return jsonify(result)
                    plain_lyrics = d.get('plainLyrics') or ''
                    if plain_lyrics.strip():
                        result = {"lyrics": plain_lyrics.strip(), "source": "lrclib"}
                        _lyrics_cache[cache_key] = result
                        return jsonify(result)
            except Exception:
                pass

            # Proveedor B: api.lyrics.ovh
            try:
                url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(a)}/{urllib.parse.quote(t)}"
                req = urllib.request.Request(url, headers={'User-Agent': ua})
                with urllib.request.urlopen(req, timeout=3) as r:
                    d = json.loads(r.read().decode('utf-8'))
                    lyrics = d.get('lyrics', '').strip()
                    if lyrics:
                        _lyrics_cache[cache_key] = lyrics
                        return jsonify({"lyrics": lyrics, "source": "lyrics.ovh"})
            except Exception:
                pass

    _lyrics_cache[cache_key] = ""
    return jsonify({"lyrics": ""})

@app.route('/api/spotify/queue', methods=['POST'])
def spotify_queue():
    data = request.get_json(force=True, silent=True) or {}
    uri = data.get("uri", "")
    return jsonify(spotify_mgr.add_to_queue(uri))

@app.route('/api/spotify/play_track', methods=['POST'])
def spotify_play_track():
    data = request.get_json(force=True, silent=True) or {}
    uri = data.get("uri", "")
    if not uri: return jsonify({"error": "No uri"}), 400
    return jsonify(spotify_mgr.play(track_uris=[uri]))

# ─── API YOUTUBE PLAYLIST (FONDOS) ───
_yt_playlist_cache = {}

@app.route('/api/youtube/playlist')
def get_youtube_playlist():
    cfg = load_config()
    playlist_id = request.args.get('playlist_id') or cfg.get('playlist_id', 'PL7E8lrk1ePfZVWMM2vsUkpQ6vbpbHi4G_')
    api_key = request.args.get('key') or cfg.get('youtube_api_key', '')
    refresh = request.args.get('refresh') == '1'

    now = time.time()
    if not refresh and playlist_id in _yt_playlist_cache:
        cached_items, exp = _yt_playlist_cache[playlist_id]
        if now < exp and cached_items:
            return jsonify({"success": True, "source": "cache", "items": cached_items})

    # 1. Si hay API key, consultar primero con YouTube Data API v3
    if api_key:
        try:
            items = []
            page_token = ""
            while True:
                url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={playlist_id}&key={api_key}"
                if page_token:
                    url += f"&pageToken={page_token}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode())
                if data.get("error"):
                    break
                for item in data.get("items", []):
                    vid = item.get("snippet", {}).get("resourceId", {}).get("videoId")
                    thumbs = item.get("snippet", {}).get("thumbnails", {})
                    thumb_url = thumbs.get("medium", {}).get("url") or thumbs.get("default", {}).get("url") or f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
                    if vid:
                        items.append({
                            "videoId": vid,
                            "title": item.get("snippet", {}).get("title", ""),
                            "thumb": thumb_url
                        })
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
            if items:
                _yt_playlist_cache[playlist_id] = (items, now + 3600)
                return jsonify({"success": True, "source": "api", "items": items})
        except Exception as e:
            print(f"[youtube_playlist] API Key falló ({e}), usando fallback con yt-dlp...")

    # 2. Fallback ultra confiable con yt-dlp (no requiere API key ni cuotas)
    try:
        pl_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        cmd = ["yt-dlp", "--flat-playlist", "-J", pl_url]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            items = []
            for entry in data.get("entries", []):
                vid = entry.get("id")
                if not vid:
                    continue
                thumbs = entry.get("thumbnails", [])
                thumb_url = thumbs[0].get("url") if thumbs else f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
                items.append({
                    "videoId": vid,
                    "title": entry.get("title", ""),
                    "thumb": thumb_url
                })
            if items:
                _yt_playlist_cache[playlist_id] = (items, now + 3600)
                return jsonify({"success": True, "source": "yt-dlp", "items": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": False, "error": "No se pudo cargar la playlist"}), 500

# ─── API YOUTUBE LIVE MONITOR ───
_resolved_channel_ids = {}

@app.route('/api/youtube/live')
def youtube_live():
    """Detecta o resuelve la transmisión en vivo del canal o video especificado (soporta @handles, IDs UC... y URLs)."""
    cfg = load_config()
    api_key = cfg.get("youtube_api_key", "").strip()
    channel_input = cfg.get("youtube_channel_id", "").strip()
    live_vid = cfg.get("youtube_live_video_id", "").strip()

    if live_vid:
        return jsonify({
            "is_live": True,
            "video_id": live_vid,
            "embed_url": f"https://www.youtube.com/embed/{live_vid}?autoplay=1&enablejsapi=1"
        })

    if not channel_input:
        return jsonify({
            "is_live": False,
            "video_id": "",
            "message": "Configura tu @usuario o ID de canal en Ajustes."
        })

    # 1. Si tenemos API Key, resolver el handle/ID limpiamente
    resolved_id = _resolved_channel_ids.get(channel_input)
    channel_title = ""

    if not resolved_id and api_key:
        # Extraer handle si viene como URL o con @
        handle = None
        if "@" in channel_input:
            handle = channel_input.split("@")[-1].split("/")[0].split("?")[0].strip()
        elif channel_input.startswith("UC") and len(channel_input) >= 20:
            resolved_id = channel_input

        if handle:
            try:
                h_url = f"https://www.googleapis.com/youtube/v3/channels?part=id,snippet&forHandle={handle}&key={api_key}"
                req = urllib.request.Request(h_url)
                with urllib.request.urlopen(req, timeout=4) as res:
                    h_data = json.loads(res.read().decode('utf-8'))
                    items = h_data.get("items", [])
                    if items:
                        resolved_id = items[0]["id"]
                        channel_title = items[0]["snippet"].get("title", "")
                        _resolved_channel_ids[channel_input] = resolved_id
            except Exception as e:
                pass

    if not resolved_id:
        if channel_input.startswith("UC"):
            resolved_id = channel_input
        else:
            resolved_id = _resolved_channel_ids.get(channel_input, channel_input)

    # 2. Buscar directo activo vía YouTube API
    if resolved_id and api_key and resolved_id.startswith("UC"):
        try:
            url = (
                f"https://www.googleapis.com/youtube/v3/search?part=snippet"
                f"&channelId={resolved_id}&eventType=live&type=video&key={api_key}"
            )
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=4) as res:
                data = json.loads(res.read().decode('utf-8'))
                items = data.get("items", [])
                if items:
                    v_id = items[0]["id"]["videoId"]
                    title = items[0]["snippet"]["title"]
                    return jsonify({
                        "is_live": True,
                        "video_id": v_id,
                        "title": title,
                        "embed_url": f"https://www.youtube.com/embed/{v_id}?autoplay=1&enablejsapi=1"
                    })
                else:
                    return jsonify({
                        "is_live": False,
                        "video_id": "",
                        "channel_id": resolved_id,
                        "channel_title": channel_title or channel_input,
                        "message": f"El canal {channel_title or channel_input} no está transmitiendo en vivo en este momento."
                    })
        except Exception as e:
            # Fallback a scraping web sin imprimir error 400
            pass

    # 3. Fallback scraping de /live para canales sin API key o en caso de error
    try:
        clean_handle = channel_input.split("/")[-1].split("?")[0]
        if not clean_handle.startswith("@") and not clean_handle.startswith("UC"):
            clean_handle = "@" + clean_handle
        target_url = f"https://www.youtube.com/{clean_handle}/live"
        req = urllib.request.Request(target_url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)'})
        with urllib.request.urlopen(req, timeout=4) as res:
            html = res.read().decode('utf-8', errors='ignore')
            import re
            m = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
            if m and ("isLive" in html or "viewCount" in html):
                v_id = m.group(1)
                return jsonify({
                    "is_live": True,
                    "video_id": v_id,
                    "embed_url": f"https://www.youtube.com/embed/{v_id}?autoplay=1&enablejsapi=1"
                })
    except Exception:
        pass

    return jsonify({
        "is_live": False,
        "video_id": "",
        "message": f"No hay transmisión activa detectada para {channel_input}."
    })

# ─── API SOUNDBOARD / BOTONERA (MYINSTANTS & RANKINGS) ───
@app.route('/api/soundboard/regional')
@app.route('/api/soundboard/trending')
def soundboard_regional():
    """Devuelve sonidos por región: ar (Argentina), latam, us, global con paginación."""
    region = request.args.get('region') or request.args.get('mode') or 'ar'
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    return jsonify(soundboard_mgr.get_regional(region, page))

@app.route('/api/soundboard/search')
def soundboard_search():
    """Busca sonidos en MyInstants con paginación."""
    q = request.args.get('q', '').strip()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    return jsonify(soundboard_mgr.search(q, page))

@app.route('/api/open_browser', methods=['GET', 'POST'])
def open_browser():
    """Abre una URL en el navegador web predeterminado del sistema anfitrión."""
    target_url = request.args.get('url')
    if not target_url:
        body = request.get_json(force=True, silent=True) or {}
        target_url = body.get('url')
    if not target_url:
        target_url = "https://www.myinstants.com/en/favorites/"
    try:
        import webbrowser
        webbrowser.open(target_url)
        return jsonify({"success": True, "url": target_url})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/soundboard/auth', methods=['GET', 'POST'])
def soundboard_auth():
    """Obtiene o actualiza las credenciales y estado de MyInstants."""
    if request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
        user = data.get('username', '')
        cookie = data.get('session_cookie', '')
        csrf = data.get('csrf_token', '')
        res = soundboard_mgr.save_auth(user, cookie, csrf)
        client_id = data.get('clientId') or data.get('client_id')
        broadcast_event("soundboard_auth_success", {
            "username": res.get("username", ""),
            "has_session": res.get("has_session", False),
            "clientId": client_id
        })
        favs = soundboard_mgr.get_saved_favorites()
        broadcast_event("soundboard_favorites_updated", {"favorites": favs, "clientId": client_id})
        return jsonify(res)
    return jsonify(soundboard_mgr.get_auth_status())

@app.route('/api/soundboard/login_window', methods=['POST'])
def soundboard_login_window():
    """Abre la ventana nativa de escritorio para iniciar sesión en MyInstants."""
    try:
        import importlib
        app_mod = importlib.import_module("app")
        if hasattr(app_mod, "open_myinstants_login_window"):
            success = app_mod.open_myinstants_login_window()
            return jsonify({"success": success})
    except Exception as e:
        print(f"[server] Error abriendo ventana login: {e}")
    # Fallback al navegador web predeterminado
    import webbrowser
    webbrowser.open("https://www.myinstants.com/en/favorites/")
    return jsonify({"success": True, "fallback": "browser"})

@app.route('/api/soundboard/favorites', methods=['GET', 'POST'])
def soundboard_favorites():
    """Obtiene o agrega a la lista persistida de favoritos con sincronización en la nube."""
    if request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
        res = soundboard_mgr.add_favorite(data)
        favs = res.get('favorites', res) if isinstance(res, dict) else res
        client_id = data.get('clientId') or data.get('client_id')
        broadcast_event("soundboard_favorites_updated", {"favorites": favs, "clientId": client_id})
        return jsonify(res)
    return jsonify(soundboard_mgr.get_saved_favorites())

@app.route('/api/soundboard/favorites/remove', methods=['POST'])
def soundboard_favorites_remove():
    """Elimina un sonido de los favoritos."""
    data = request.get_json(force=True, silent=True) or {}
    sound_id = data.get('id') or data.get('title') or data.get('mp3')
    favs = soundboard_mgr.remove_favorite(sound_id)
    client_id = data.get('clientId') or data.get('client_id')
    broadcast_event("soundboard_favorites_updated", {"favorites": favs, "clientId": client_id})
    return jsonify(favs)

@app.route('/api/soundboard/play', methods=['POST'])
def soundboard_play():
    """Reproduce el audio en la PC anfitriona (Linux PipeWire/ALSA)."""
    data = request.get_json(force=True, silent=True) or {}
    mp3_url = data.get('mp3') or data.get('url', '')
    title = data.get('title', '')
    cfg = load_config()
    vol = data.get('volume')
    if vol is None:
        vol = cfg.get('soundboard_volume', 80)
    res = soundboard_mgr.play(mp3_url, title, vol)
    client_id = data.get('clientId') or data.get('client_id')
    broadcast_event("soundboard_play", {"title": title, "mp3": mp3_url, "volume": vol, "clientId": client_id})
    return jsonify(res)

@app.route('/api/soundboard/volume', methods=['POST'])
def soundboard_volume():
    """Actualiza y persiste el volumen predeterminado de la botonera."""
    data = request.get_json(force=True, silent=True) or {}
    vol = data.get('volume', 80)
    res = soundboard_mgr.set_volume(vol)
    vol_val = res.get("volume", vol)
    current_state["soundboard_volume"] = vol_val
    client_id = data.get('clientId') or data.get('client_id')
    broadcast_event("soundboard_volume", {"volume": vol_val, "clientId": client_id})
    return jsonify(res)

@app.route('/api/soundboard/stop', methods=['POST'])
def soundboard_stop():
    """Detiene cualquier sonido en reproducción en la PC."""
    data = request.get_json(force=True, silent=True) or {}
    res = soundboard_mgr.stop_all()
    client_id = data.get('clientId') or data.get('client_id')
    broadcast_event("soundboard_stop", {"clientId": client_id})
    return jsonify(res)

@app.route('/api/soundboard/sync_account', methods=['POST'])
def soundboard_sync_account():
    """Sincroniza favoritos de la cuenta o perfil de MyInstants."""
    data = request.get_json(force=True, silent=True) or {}
    username = data.get('username', '').strip()
    if not username:
        cfg = load_config()
        username = cfg.get('soundboard_username', '')
    return jsonify(soundboard_mgr.sync_account(username))

@app.route('/api/soundboard/account')
def soundboard_account():
    """Información de la cuenta de MyInstants guardada."""
    cfg = load_config()
    return jsonify({
        "username": cfg.get("soundboard_username", ""),
        "volume": cfg.get("soundboard_volume", 80),
        "favorites_count": len(cfg.get("soundboard_favorites", []))
    })

# ─── API DE TEMPORIZADOR Y OVERLAYS ───
@app.route('/api/timer/status')
def timer_status():
    return jsonify(overlay_mgr.get_status())

@app.route('/api/timer/start', methods=['POST'])
def timer_start():
    data = request.json or {}
    duration = int(data.get('duration', 300))
    title = data.get('title', 'Ya Vuelvo')
    phrase = data.get('phrase', '')
    state = overlay_mgr.start_timer(duration=duration, title=title, phrase=phrase)
    
    cfg = load_config()
    cfg["timer_default_title"] = title.strip()
    cfg["timer_default_phrase"] = phrase.strip()
    save_config(cfg)

    return jsonify({"success": True, "state": state})

@app.route('/api/timer/add', methods=['POST'])
def timer_add():
    data = request.json or {}
    duration = int(data.get('duration', 60))
    state = overlay_mgr.add_timer(duration)
    return jsonify({"success": True, "state": state})

@app.route('/api/timer/pause', methods=['POST'])
def timer_pause():
    state = overlay_mgr.pause_timer()
    return jsonify({"success": True, "state": state})

@app.route('/api/timer/stop', methods=['POST'])
def timer_stop():
    state = overlay_mgr.stop_timer()
    return jsonify({"success": True, "state": state})

@app.route('/api/timer/live_text', methods=['POST'])
def timer_set_live_text():
    data = request.json or {}
    title = data.get('title')
    phrase = data.get('phrase')
    state = overlay_mgr.set_live_text(title=title, phrase=phrase)
    
    # Save to config to remember as defaults
    cfg = load_config()
    if title is not None:
        cfg["timer_default_title"] = title.strip()
    if phrase is not None:
        cfg["timer_default_phrase"] = phrase.strip()
    save_config(cfg)
    
    return jsonify({"success": True, "state": state})

@app.route('/api/timer/phrases', methods=['GET'])
def timer_get_phrases():
    return jsonify({"phrases": overlay_mgr.get_phrases()})

@app.route('/api/timer/phrases/add', methods=['POST'])
def timer_add_phrase():
    data = request.json or {}
    phrase = data.get('phrase', '')
    phrases = overlay_mgr.add_phrase(phrase)
    return jsonify({"success": True, "phrases": phrases})

@app.route('/api/timer/phrases/remove', methods=['POST'])
def timer_remove_phrase():
    data = request.json or {}
    phrase = data.get('phrase', '')
    phrases = overlay_mgr.remove_phrase(phrase)
    return jsonify({"success": True, "phrases": phrases})

# ─── RESOLUCIÓN DE VIDEO Y CACHE CON YT-DLP ───
@app.route('/api/get_video_url')
def get_video_url():
    video_id = request.args.get('v')
    if not video_id:
        return jsonify({'error': 'No video id provided'}), 400

    cfg = load_config()
    force_combined = request.args.get('fallback') == 'combined'
    force_fresh = request.args.get('fresh') == '1' or force_combined
    playback_mode = 'combined' if force_combined else cfg.get('video_playback_mode', 'original')
    now = time.time()
    cached_path = _cached_video_path(video_id)
    if cached_path and playback_mode in ('cache', 'adaptive'):
        cached_url = f'/api/cache/video/{video_id}'
        result = {'video_url': cached_url, 'audio_url': cached_url, 'combined_audio': True, 'cached': True}
        video_cache[video_id] = (result, now + 7200)
        return jsonify(result)

    if not force_fresh and video_id in video_cache:
        cached_data, exp_time = video_cache[video_id]
        # Consideramos válida si queda más de 3 minutos
        if now < exp_time - 180:
            return jsonify(cached_data)

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'format': (
            'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/'
            'bestvideo[height<=1080]+bestaudio/best'
            if playback_mode == 'original'
            else '18/best[height<=1080]/best'
        ),
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if playback_mode == 'original' and 'requested_formats' in info:
                video_url = info['requested_formats'][0]['url']
                audio_url = info['requested_formats'][1]['url']
                combined_audio = False
            else:
                video_url = info['url']
                audio_url = video_url
                combined_audio = True

            # Leer la expiración real de la URL de YouTube (parámetro expire=)
            import urllib.parse as _up
            def _parse_expire(u):
                try:
                    qs = _up.parse_qs(_up.urlparse(u).query)
                    exp = qs.get('expire', qs.get('exp', [None]))[0]
                    if exp:
                        return int(exp)
                except Exception:
                    pass
                return None

            real_expire = _parse_expire(video_url) or _parse_expire(audio_url)
            if real_expire and real_expire > now:
                # Usamos la expiración real menos 3 min de margen
                cache_until = real_expire - 180
            else:
                # Fallback conservador: 25 minutos
                cache_until = now + 1500

            result = {'video_url': video_url, 'audio_url': audio_url, 'combined_audio': combined_audio,
                      'expires_at': int(cache_until + 180)}
            video_cache[video_id] = (result, cache_until)
            if playback_mode in ('cache', 'adaptive'):
                _queue_video_download(video_id)
            return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/prefetch_video_url')
def prefetch_video_url():
    """Renueva proactivamente la URL de un video en background (lo llama el viewer antes de que expire)."""
    video_id = request.args.get('v')
    if not video_id:
        return jsonify({'ok': False}), 400
    # Eliminar del cache para forzar renovación en la próxima llamada
    video_cache.pop(video_id, None)
    # Lanzar en background para no bloquear
    def _renew():
        try:
            import requests as _req
            _req.get(f'http://127.0.0.1:{request.environ.get("SERVER_PORT", 5000)}/api/get_video_url?v={video_id}', timeout=30)
        except Exception:
            pass
    threading.Thread(target=_renew, daemon=True).start()
    return jsonify({'ok': True})

@app.route('/api/cache/video/<video_id>')
def serve_cached_video(video_id):
    cached_path = _cached_video_path(video_id)
    if not cached_path:
        return jsonify({'error': 'Video todavía no está disponible en cache'}), 404
    return send_from_directory(VIDEO_CACHE_DIR, cached_path.name, conditional=True)

@app.route('/api/cache/status/<video_id>')
def cached_video_status(video_id):
    cached_path = _cached_video_path(video_id)
    if cached_path:
        return jsonify({'status': 'ready', 'url': f'/api/cache/video/{video_id}'})
    with video_download_lock:
        status = video_download_status.get(video_id, 'idle')
    return jsonify({'status': status})

# ─── SERVICIO PRINCIPAL ───
if __name__ == '__main__':
    cfg = load_config()
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else int(cfg.get("port", 8000))
    host = cfg.get("host", "0.0.0.0")
    print(f"[fondos-stream] Iniciando servidor en http://{host}:{puerto}")
    try:
        from mdns_service import start_mdns_publisher
        start_mdns_publisher(puerto)
    except Exception as e:
        print(f"[mDNS] No se pudo iniciar publicador mDNS: {e}")
    app.run(host=host, port=puerto, threaded=True)


# ─── MONITOR EN SEGUNDO PLANO DE SPOTIFY (TIEMPO REAL) ───
def start_spotify_monitor():
    def _loop():
        time.sleep(2)
        while True:
            try:
                time.sleep(6)
                st = spotify_mgr.get_playback_state()
                if st and st.get("available"):
                    broadcast_event("spotify_state", st)
            except Exception:
                pass
    threading.Thread(target=_loop, daemon=True).start()

start_spotify_monitor()

# ─── MONITOR EN SEGUNDO PLANO DE AUDIO & VÚMETROS OBS (SSE TIEMPO REAL) ───
def start_obs_audio_monitor():
    def _loop():
        time.sleep(3)
        while True:
            try:
                cfg = load_config()
                # Verificar si hay clientes conectados a SSE
                with listeners_lock:
                    has_listeners = len(event_listeners) > 0
                if not has_listeners:
                    time.sleep(2)
                    continue

                obs = OBSController(
                    host=cfg.get("obs_host", "localhost"),
                    port=cfg.get("obs_port", 4455),
                    password=cfg.get("obs_password", "")
                )
                # EventSubscription: InputVolumeMeters (65536) | Inputs (8) | Scenes (4)
                sock = obs._connect_and_identify(event_subscriptions=65536 | 8 | 4)
                if not sock:
                    time.sleep(3)
                    continue

                # Iniciar la cámara virtual de OBS automáticamente tan pronto conecta el socket
                try:
                    obs.start_virtual_cam()
                except Exception:
                    pass

                sock.settimeout(3.0)
                last_emit = 0.0

                while True:
                    with listeners_lock:
                        if len(event_listeners) == 0:
                            break

                    frame = obs._recv_ws_frame(sock)
                    if not frame:
                        break

                    try:
                        msg = json.loads(frame)
                    except Exception:
                        continue

                    op = msg.get("op")
                    if op == 5: # Event
                        event_type = msg.get("d", {}).get("eventType")
                        event_data = msg.get("d", {}).get("eventData", {})

                        if event_type == "InputVolumeMeters":
                            now = time.time()
                            # Limitar a ~10-12 FPS para no saturar la red local y permitir animación ultra fluida
                            if now - last_emit >= 0.08:
                                last_emit = now
                                inputs = event_data.get("inputs", [])
                                meter_map = {}
                                for inp in inputs:
                                    name = inp.get("inputName")
                                    levels = inp.get("inputLevelsMul", [])
                                    # levels es lista de [peak, rms, inputPeak] por canal
                                    # Tomamos el valor de pico máximo entre canales
                                    peak = 0.0
                                    for ch in levels:
                                        if ch and len(ch) > 0:
                                            peak = max(peak, float(ch[0]))
                                    meter_map[name] = round(peak, 4)
                                broadcast_event("obs_audio_levels", {"meters": meter_map})

                        elif event_type in ("InputMuteStateChanged", "InputVolumeChanged"):
                            broadcast_event("obs_audio_changed", event_data)

                        elif event_type == "CurrentProgramSceneChanged":
                            scene_name = event_data.get("sceneName", "")
                            with obs_scenes_lock:
                                obs_scenes_cache["current_scene"] = scene_name
                            broadcast_event("obs_updated", {"scene": scene_name})

                        elif event_type == "SceneListChanged":
                            # Refrescar lista de escenas
                            try:
                                scenes_list = event_data.get("scenes", [])
                                if scenes_list:
                                    names = [s.get("sceneName") for s in reversed(scenes_list) if "sceneName" in s]
                                    with obs_scenes_lock:
                                        obs_scenes_cache["scenes"] = names
                                    broadcast_event("obs_scenes_list", {"scenes": names})
                            except Exception:
                                pass
                            broadcast_event("obs_status_changed", {})

                try:
                    sock.close()
                except Exception:
                    pass
                time.sleep(1)
            except Exception:
                time.sleep(3)

    threading.Thread(target=_loop, daemon=True, name="obs-audio-monitor").start()

start_obs_audio_monitor()
