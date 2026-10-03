import os
import sys
import json
import time
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
from qr_svg import generate_qr_svg

app = Flask(__name__, static_folder='.', static_url_path='')

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
        broadcast_event("config_updated", {
            "playlist_id": saved.get("playlist_id"),
            "has_api_key": bool(saved.get("youtube_api_key")),
            "obs_enabled": saved.get("obs_enabled"),
            "auto_focus_viewer": saved.get("auto_focus_viewer", True)
        })
        return jsonify({"success": True, "config": saved})

    cfg = load_config()
    safe_cfg = cfg.copy()
    raw_key = safe_cfg.get("youtube_api_key", "")
    safe_cfg["has_api_key"] = bool(raw_key)
    safe_cfg["youtube_api_key_masked"] = (raw_key[:4] + "..." + raw_key[-4:]) if len(raw_key) > 8 else ("***" if raw_key else "")
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
@app.route('/api/open_browser', methods=['POST'])
def open_browser():
    data = request.get_json(force=True, silent=True) or {}
    target = data.get("target", "viewer")
    cfg = load_config()
    port = cfg.get("port", 8000)

    if target == "viewer" or request.path == "/api/open_viewer":
        viewer_url = f"http://localhost:{port}/viewer.html"
        res = browser_mgr.open_smart_viewer(viewer_url)
        return jsonify(res)
    else:
        url = f"http://localhost:{port}/controller.html"
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
        return jsonify({"success": True, "url": url})

@app.route('/api/focus_viewer', methods=['POST'])
def focus_viewer_route():
    """Pone la pestaña/ventana del Viewer en primer plano en el sistema operativo."""
    focused = browser_mgr.focus_viewer()
    return jsonify({"success": True, "focused": focused})

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

@app.route('/api/obs/scenes')
def get_obs_scenes():
    cfg = load_config()
    obs = OBSController(
        host=cfg.get("obs_host", "localhost"),
        port=cfg.get("obs_port", 4455),
        password=cfg.get("obs_password", "")
    )
    return jsonify(obs.get_scenes())

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

# ─── API SPOTIFY REMOTE ───
@app.route('/api/spotify/auth_url')
def spotify_auth_url():
    lan_ip = get_lan_ip()
    port = load_config().get("port", 8000)
    redirect_uri = f"http://{lan_ip}:{port}/api/spotify/callback"
    url = spotify_mgr.get_auth_url(redirect_uri)
    return jsonify({"auth_url": url, "redirect_uri": redirect_uri})

@app.route('/api/spotify/callback')
def spotify_callback():
    code = request.args.get("code")
    error = request.args.get("error")
    if error or not code:
        return f"<h3>Error autorizando Spotify: {error}</h3><p><a href='/controller.html'>Volver</a></p>", 400

    lan_ip = get_lan_ip()
    port = load_config().get("port", 8000)
    redirect_uri = f"http://{lan_ip}:{port}/api/spotify/callback"
    res = spotify_mgr.exchange_code(code, redirect_uri)
    if res.get("success"):
        return redirect("/controller.html#spotify")
    return f"<h3>Error canjeando código: {res.get('error')}</h3>", 400

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

# ─── API YOUTUBE LIVE MONITOR ───
@app.route('/api/youtube/live')
def youtube_live():
    """Detecta o resuelve la transmisión en vivo del canal o video especificado."""
    cfg = load_config()
    api_key = cfg.get("youtube_api_key", "")
    channel_id = cfg.get("youtube_channel_id", "")
    live_vid = cfg.get("youtube_live_video_id", "")

    # Si se configuró directamente un video ID de directo o URL
    if live_vid:
        return jsonify({
            "is_live": True,
            "video_id": live_vid,
            "embed_url": f"https://www.youtube.com/embed/{live_vid}?autoplay=1&enablejsapi=1"
        })

    # Si se configuró Channel ID y API Key, buscar el directo activo del canal
    if channel_id and api_key:
        try:
            url = (
                f"https://www.googleapis.com/youtube/v3/search?part=snippet"
                f"&channelId={channel_id}&eventType=live&type=video&key={api_key}"
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
        except Exception as e:
            print(f"[youtube_live] Error buscando directo: {e}")

    return jsonify({
        "is_live": False,
        "video_id": "",
        "message": "No hay transmisión activa detectada o falta configurar el ID de canal / video en Ajustes."
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

# ─── RESOLUCIÓN DE VIDEO Y CACHE CON YT-DLP ───
@app.route('/api/get_video_url')
def get_video_url():
    video_id = request.args.get('v')
    if not video_id:
        return jsonify({'error': 'No video id provided'}), 400

    now = time.time()
    if video_id in video_cache:
        cached_data, exp_time = video_cache[video_id]
        if now < exp_time:
            return jsonify(cached_data)

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'requested_formats' in info:
                video_url = info['requested_formats'][0]['url']
                audio_url = info['requested_formats'][1]['url']
            else:
                video_url = info['url']
                audio_url = info['url']

            result = {'video_url': video_url, 'audio_url': audio_url}
            video_cache[video_id] = (result, now + 7200)
            return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
