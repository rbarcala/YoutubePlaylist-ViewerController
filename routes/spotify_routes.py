import json
import re
import urllib.request
import urllib.parse
from flask import Blueprint, request, jsonify

spotify_bp = Blueprint('spotify', __name__)

_lyrics_cache = {}

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
    if not query:
        return jsonify({'tracks': []})
    
    results = spotify_mgr.search(query)
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
    artist = (request.args.get('artist') or '').strip()
    title = (request.args.get('title') or '').strip()

    # Si no se pasó artist ni title, intentar obtenerlo de la reproducción en vivo
    if not artist and not title and spotify_mgr:
        st = spotify_mgr.get_playback_state()
        if st and (st.get('is_playing') or st.get('available')):
            artist = (st.get('artist') or '').strip()
            title = (st.get('title') or '').strip()

    if not artist and not title:
        return jsonify({'lyrics': '', 'syncedLyrics': ''})

    cache_key = f"{artist.lower()}|||{title.lower()}"
    if cache_key in _lyrics_cache:
        cached = _lyrics_cache[cache_key]
        return jsonify(cached if isinstance(cached, dict) else {'lyrics': cached, 'syncedLyrics': ''})

    # Candidatos de artista
    artist_candidates = []
    if ',' in artist:
        artist_candidates.append(artist.split(',')[0].strip())
    if ';' in artist:
        artist_candidates.append(artist.split(';')[0].strip())
    if ' feat' in artist.lower():
        artist_candidates.append(re.split(r'\s+feat\.?', artist, flags=re.IGNORECASE)[0].strip())
    if ' ft.' in artist.lower():
        artist_candidates.append(re.split(r'\s+ft\.?', artist, flags=re.IGNORECASE)[0].strip())
    
    # Variante sin signos de exclamación o puntuación al final (ej. "Miranda!" -> "Miranda")
    no_punct_art = re.sub(r'[!¡?¿]+', '', artist).strip()
    if no_punct_art and no_punct_art != artist:
        artist_candidates.append(no_punct_art)

    if artist and artist not in artist_candidates:
        artist_candidates.insert(0, artist)

    # Limpieza de título
    clean_title = re.sub(r'\(feat\..*?\)', '', title, flags=re.IGNORECASE)
    clean_title = re.sub(r'\[.*?\]', '', clean_title)
    clean_title = re.sub(r'-\s*(remastered|live|radio edit|bonus track|deluxe).*?$', '', clean_title, flags=re.IGNORECASE).strip()
    title_candidates = [clean_title] if clean_title != title else [title]

    no_punct_title = re.sub(r'[!¡?¿]+', '', clean_title).strip()
    if no_punct_title and no_punct_title not in title_candidates:
        title_candidates.append(no_punct_title)

    if title and title not in title_candidates:
        title_candidates.append(title)

    ua = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

    # 1. Consultar lrclib.net get directo
    for art in artist_candidates:
        for tit in title_candidates:
            if not art or not tit:
                continue
            try:
                params = urllib.parse.urlencode({'artist_name': art, 'track_name': tit})
                url = f"https://lrclib.net/api/get?{params}"
                req = urllib.request.Request(url, headers={'User-Agent': ua})
                with urllib.request.urlopen(req, timeout=3.5) as r:
                    d = json.loads(r.read().decode('utf-8'))
                    synced_lyrics = d.get('syncedLyrics') or ''
                    plain_lyrics = d.get('plainLyrics') or ''
                    if synced_lyrics.strip():
                        if not plain_lyrics.strip():
                            plain_lyrics = re.sub(r'\[\d{2}:\d{2}(?:\.\d{2,3})?\]\s*', '', synced_lyrics).strip()
                        result = {"lyrics": plain_lyrics, "syncedLyrics": synced_lyrics, "source": "lrclib"}
                        _lyrics_cache[cache_key] = result
                        return jsonify(result)
                    if plain_lyrics.strip():
                        result = {"lyrics": plain_lyrics.strip(), "syncedLyrics": "", "source": "lrclib"}
                        _lyrics_cache[cache_key] = result
                        return jsonify(result)
            except Exception:
                pass

    # 2. Fallback de búsqueda abierta
    for art in artist_candidates[:1]:
        for tit in title_candidates[:1]:
            try:
                q_params = urllib.parse.urlencode({'q': f'{art} {tit}'})
                search_url = f"https://lrclib.net/api/search?{q_params}"
                req = urllib.request.Request(search_url, headers={'User-Agent': ua})
                with urllib.request.urlopen(req, timeout=3.5) as r:
                    items = json.loads(r.read().decode('utf-8'))
                    if items and isinstance(items, list) and len(items) > 0:
                        top = items[0]
                        synced = top.get('syncedLyrics') or ''
                        plain = top.get('plainLyrics') or ''
                        if synced.strip():
                            if not plain.strip():
                                plain = re.sub(r'\[\d{2}:\d{2}(?:\.\d{2,3})?\]\s*', '', synced).strip()
                            result = {"lyrics": plain, "syncedLyrics": synced, "source": "lrclib"}
                            _lyrics_cache[cache_key] = result
                            return jsonify(result)
                        if plain.strip():
                            result = {"lyrics": plain.strip(), "syncedLyrics": "", "source": "lrclib"}
                            _lyrics_cache[cache_key] = result
                            return jsonify(result)
            except Exception:
                pass

    return jsonify({'lyrics': '', 'syncedLyrics': ''})


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