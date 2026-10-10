from flask import Blueprint, request, jsonify

spotify_bp = Blueprint('spotify', __name__)

# Variables que se inyectan desde server.py
spotify_mgr = None
load_config = None
save_config = None
broadcast_event = None

def init_spotify_routes(sp_mgr, config_loader, config_saver, broadcast_fn):
    global spotify_mgr, load_config, save_config, broadcast_event
    spotify_mgr = sp_mgr
    load_config = config_loader
    save_config = config_saver
    broadcast_event = broadcast_fn


@spotify_bp.route('/api/spotify/auth_url', methods=['GET', 'POST'])
def spotify_auth_url():
    cfg = load_config() if load_config else {}
    client_id = cfg.get('spotify_client_id', '')
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        req_cid = data.get('client_id', '').strip()
        req_csec = data.get('client_secret', '').strip()
        if req_cid:
            client_id = req_cid
            cfg['spotify_client_id'] = req_cid
        if req_csec:
            cfg['spotify_client_secret'] = req_csec
        if (req_cid or req_csec) and save_config:
            save_config(cfg)
    port = cfg.get('port', 8000)
    redirect_uri = cfg.get('spotify_redirect_uri', f'http://127.0.0.1:{port}/api/spotify/callback')
    scopes = 'user-read-playback-state user-modify-playback-state user-read-currently-playing streaming user-library-read user-read-recently-played playlist-read-private playlist-read-collaborative user-top-read'
    if client_id:
        from urllib.parse import urlencode
        params = {
            'client_id': client_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'scope': scopes,
            'show_dialog': 'true'
        }
        return jsonify({'auth_url': f'https://accounts.spotify.com/authorize?{urlencode(params)}'})
    return jsonify({'auth_url': ''})


@spotify_bp.route('/api/spotify/callback')
def spotify_callback():
    code = request.args.get('code')
    if not code:
        return 'Error: No se recibió código de autorización', 400
    
    cfg = load_config()
    client_id = cfg.get('spotify_client_id', '')
    client_secret = cfg.get('spotify_client_secret', '')
    redirect_uri = cfg.get('spotify_redirect_uri', 'http://127.0.0.1:8000/api/spotify/callback')
    
    if not client_id or not client_secret:
        return 'Error: Cliente Spotify no configurado', 500
    
    import urllib.request
    import urllib.parse
    import json
    
    data = urllib.parse.urlencode({
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri
    }).encode()
    
    req = urllib.request.Request(
        'https://accounts.spotify.com/api/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    # Autenticación básica
    import base64
    auth = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    req.add_header('Authorization', f'Basic {auth}')
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            token_data = json.loads(response.read().decode())
        
        cfg['spotify_access_token'] = token_data.get('access_token')
        cfg['spotify_refresh_token'] = token_data.get('refresh_token')
        cfg['spotify_token_expires'] = __import__('time').time() + token_data.get('expires_in', 3600)
        save_config(cfg)
        
        # Inicializar manager con nuevos tokens
        spotify_mgr._access_token = cfg['spotify_access_token']
        spotify_mgr._refresh_token = cfg['spotify_refresh_token']
        spotify_mgr._token_expires = cfg['spotify_token_expires']
        
        if broadcast_event:
            broadcast_event('spotify_auth', {'authenticated': True})
        
        return '<html><body><script>window.close()</script>Autenticación exitosa. Puedes cerrar esta ventana.</body></html>'
    except Exception as e:
        return f'Error obteniendo token: {e}', 500


@spotify_bp.route('/api/spotify/seek', methods=['POST'])
def spotify_seek_route():
    data = request.get_json() or {}
    position_ms = data.get('position_ms')
    if position_ms is None:
        return jsonify({'ok': False, 'error': 'position_ms requerido'}), 400
    
    ok = spotify_mgr.seek(position_ms)
    return jsonify({'ok': ok})


@spotify_bp.route('/api/spotify/state')
def spotify_state():
    state = spotify_mgr.get_playback_state()
    return jsonify(state)


@spotify_bp.route('/api/spotify/play', methods=['POST'])
def spotify_play():
    data = request.get_json() or {}
    uri = data.get('uri')
    ok = spotify_mgr.play(uri)
    if ok and broadcast_event:
        # El monitor en background emitirá el estado actualizado
        pass
    return jsonify({'ok': ok})


@spotify_bp.route('/api/spotify/pause', methods=['POST'])
def spotify_pause():
    ok = spotify_mgr.pause()
    return jsonify({'ok': ok})


@spotify_bp.route('/api/spotify/next', methods=['POST'])
def spotify_next():
    ok = spotify_mgr.next_track()
    return jsonify({'ok': ok})


@spotify_bp.route('/api/spotify/previous', methods=['POST'])
def spotify_prev():
    ok = spotify_mgr.previous_track()
    return jsonify({'ok': ok})


@spotify_bp.route('/api/spotify/volume', methods=['POST'])
def spotify_volume():
    data = request.get_json() or {}
    volume = data.get('volume')
    if volume is None:
        return jsonify({'ok': False, 'error': 'volume requerido'}), 400
    
    ok = spotify_mgr.set_volume(volume)
    return jsonify({'ok': ok})


@spotify_bp.route('/api/spotify/search')
def spotify_search():
    query = request.args.get('q', '')
    type_ = request.args.get('type', 'track')
    limit = int(request.args.get('limit', 20))
    
    if not query:
        return jsonify({'tracks': {'items': []}})
    
    results = spotify_mgr.search(query, type_, limit)
    return jsonify(results)


@spotify_bp.route('/api/spotify/saved_playlists', methods=['GET', 'POST', 'DELETE'])
def spotify_saved_playlists():
    if not spotify_mgr:
        return jsonify({'playlists': []})

    if request.method == 'GET':
        playlists = spotify_mgr.get_user_playlists()
        return jsonify({'playlists': playlists})

    elif request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
        pid = data.get('id') or data.get('playlist_id')
        pname = data.get('name') or pid
        if not pid:
            return jsonify({'ok': False, 'error': 'playlist_id requerido'}), 400
        ok = spotify_mgr.save_playlist(pid, pname)
        return jsonify({'ok': ok, 'playlists': spotify_mgr.get_user_playlists()})

    elif request.method == 'DELETE':
        data = request.get_json(force=True, silent=True) or {}
        pid = data.get('id') or data.get('playlist_id') or request.args.get('id') or request.args.get('playlist_id')
        if not pid:
            return jsonify({'ok': False, 'error': 'playlist_id requerido'}), 400
        ok = spotify_mgr.remove_saved_playlist(pid)
        return jsonify({'ok': ok, 'playlists': spotify_mgr.get_user_playlists()})


@spotify_bp.route('/api/spotify/playlist')
def spotify_playlist():
    playlist_id = request.args.get('id') or request.args.get('playlist_id', '')
    if not playlist_id:
        return jsonify({'tracks': []})

    if not spotify_mgr:
        return jsonify({'tracks': []})

    return jsonify(spotify_mgr.get_playlist(playlist_id))


@spotify_bp.route('/api/spotify/lyrics')
def spotify_lyrics():
    track_id = request.args.get('track_id')
    if not track_id:
        return jsonify({'lyrics': ''})
    
    lyrics = spotify_mgr.get_lyrics(track_id)
    return jsonify({'lyrics': lyrics})


@spotify_bp.route('/api/spotify/queue', methods=['POST'])
def spotify_queue():
    data = request.get_json() or {}
    uri = data.get('uri')
    if not uri:
        return jsonify({'ok': False, 'error': 'uri requerido'}), 400
    
    ok = spotify_mgr.add_to_queue(uri)
    return jsonify({'ok': ok})


@spotify_bp.route('/api/spotify/play_track', methods=['POST'])
def spotify_play_track():
    data = request.get_json() or {}
    uri = data.get('uri')
    if not uri:
        return jsonify({'ok': False, 'error': 'uri requerido'}), 400
    
    ok = spotify_mgr.play(uri)
    return jsonify({'ok': ok})