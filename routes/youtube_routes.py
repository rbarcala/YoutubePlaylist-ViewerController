import json
import time
import threading
import urllib.request
import urllib.parse
from flask import Blueprint, request, jsonify

youtube_bp = Blueprint('youtube', __name__)

# Variables que se inyectan desde server.py
load_config = None
save_config = None
broadcast_event = None
current_state = None
video_manager = None


def init_youtube_routes(config_loader, config_saver, broadcast_fn, state, video_mgr_inst):
    global load_config, save_config, broadcast_event, current_state, video_manager
    load_config = config_loader
    save_config = config_saver
    broadcast_event = broadcast_fn
    current_state = state
    video_manager = video_mgr_inst


@youtube_bp.route('/api/youtube/playlist')
def get_youtube_playlist():
    cfg = load_config() if load_config else {}
    api_key = request.args.get('key') or cfg.get('youtube_api_key', '')
    playlist_id = request.args.get('playlist_id') or cfg.get('playlist_id', '')

    if not api_key or not playlist_id:
        return jsonify({'success': False, 'videos': [], 'items': [], 'error': 'API Key o Playlist ID no configurados'})

    videos = []
    items = []
    next_page_token = None
    max_results = 50

    try:
        while True:
            params = {
                'part': 'snippet,contentDetails',
                'playlistId': playlist_id,
                'maxResults': max_results,
                'key': api_key
            }
            if next_page_token:
                params['pageToken'] = next_page_token

            url = f'https://www.googleapis.com/youtube/v3/playlistItems?{urllib.parse.urlencode(params)}'

            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())

            for item in data.get('items', []):
                snippet = item.get('snippet', {})
                content = item.get('contentDetails', {})
                video_id = content.get('videoId')
                thumb = (snippet.get('thumbnails', {}).get('high', {}).get('url', '') or
                         snippet.get('thumbnails', {}).get('medium', {}).get('url', '') or
                         snippet.get('thumbnails', {}).get('default', {}).get('url', ''))
                if video_id:
                    videos.append({
                        'id': video_id,
                        'title': snippet.get('title', ''),
                        'thumbnail': thumb,
                        'channel': snippet.get('channelTitle', ''),
                        'published': snippet.get('publishedAt', '')
                    })
                    items.append({
                        'videoId': video_id,
                        'title': snippet.get('title', ''),
                        'thumb': thumb,
                        'duration': ''
                    })

            next_page_token = data.get('nextPageToken')
            if not next_page_token:
                break

        return jsonify({'success': True, 'videos': videos, 'items': items})
    except Exception as e:
        # Fallback ultra-confiable con yt-dlp si la API da error (ej. quota excedida o red)
        try:
            import yt_dlp
            ydl_opts = {
                'extract_flat': True,
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f'https://www.youtube.com/playlist?list={playlist_id}', download=False)
                for entry in info.get('entries', []):
                    vid = entry.get('id')
                    if vid:
                        t = entry.get('title', '')
                        th = f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg'
                        videos.append({
                            'id': vid,
                            'title': t,
                            'thumbnail': th,
                            'channel': entry.get('uploader', ''),
                            'published': ''
                        })
                        items.append({
                            'videoId': vid,
                            'title': t,
                            'thumb': th,
                            'duration': ''
                        })
                if items:
                    return jsonify({'success': True, 'videos': videos, 'items': items, 'fallback': True})
        except Exception:
            pass

        return jsonify({'success': False, 'videos': [], 'items': [], 'error': str(e)})


@youtube_bp.route('/api/youtube/live')
def youtube_live():
    cfg = load_config() if load_config else {}
    channel_id = cfg.get('youtube_channel_id', '')
    api_key = cfg.get('youtube_api_key', '')

    if not channel_id or not api_key:
        return jsonify({'live': None, 'error': 'Canal o API Key no configurados'})

    params = {
        'part': 'snippet',
        'channelId': channel_id,
        'eventType': 'live',
        'type': 'video',
        'key': api_key
    }
    url = f'https://www.googleapis.com/youtube/v3/search?{urllib.parse.urlencode(params)}'

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        return jsonify({'live': None, 'error': str(e)})

    items = data.get('items', [])
    if items:
        video_id = items[0].get('id', {}).get('videoId')
        if video_id:
            return jsonify({'live': {'videoId': video_id}})

    return jsonify({'live': None})


@youtube_bp.route('/api/get_video_url')
def get_video_url():
    video_id = request.args.get('v')
    playback_mode = request.args.get('mode', 'stream')

    if not video_id:
        return jsonify({'error': 'Parámetro v requerido'}), 400

    # Verificar cache local primero
    cached = video_manager.get_cached_path(video_id) if video_manager else None
    if cached and playback_mode in ('cache', 'adaptive'):
        return jsonify({
            'video_url': f'/api/cache/video/{video_id}',
            'audio_url': f'/api/cache/video/{video_id}',
            'combined_audio': True,
            'expires_at': 0
        })

    # Obtener URL de streaming via yt-dlp
    import yt_dlp
    opts = {
        'format': 'best[height<=1080][ext=mp4]/best[height<=1080]/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)

        video_url = None
        audio_url = None
        combined_audio = False

        for fmt in info.get('formats', []):
            if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
                video_url = fmt.get('url')
                combined_audio = True
                break

        if not video_url:
            for fmt in info.get('formats', []):
                if fmt.get('vcodec') != 'none' and fmt.get('acodec') == 'none':
                    video_url = fmt.get('url')
                    break
            for fmt in info.get('formats', []):
                if fmt.get('vcodec') == 'none' and fmt.get('acodec') != 'none':
                    audio_url = fmt.get('url')
                    break

        if not video_url:
            return jsonify({'error': 'No se encontró formato de video válido'}), 500

        # Parsear expiración real de la URL
        def _parse_expire(u):
            try:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
                exp = qs.get('expire', qs.get('exp', [None]))[0]
                if exp:
                    return int(exp)
            except Exception:
                pass
            return None

        real_expire = _parse_expire(video_url) or _parse_expire(audio_url)
        now = time.time()
        if real_expire and real_expire > now:
            cache_until = real_expire - 180
        else:
            cache_until = now + 1500

        result = {
            'video_url': video_url,
            'audio_url': audio_url,
            'combined_audio': combined_audio,
            'expires_at': int(cache_until + 180)
        }

        if playback_mode in ('cache', 'adaptive') and video_manager:
            video_manager.queue_download(video_id)

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@youtube_bp.route('/api/prefetch_video_url')
def prefetch_video_url():
    video_id = request.args.get('v')
    if not video_id:
        return jsonify({'ok': False}), 400

    from flask import current_app
    if hasattr(current_app, 'video_cache') and video_id in current_app.video_cache:
        current_app.video_cache.pop(video_id, None)

    if video_manager and hasattr(video_manager, 'video_url_cache') and video_id in video_manager.video_url_cache:
        video_manager.video_url_cache.pop(video_id, None)

    def _renew():
        try:
            import requests as _req
            port = request.environ.get("SERVER_PORT", 8000)
            _req.get(f'http://127.0.0.1:{port}/api/get_video_url?v={video_id}', timeout=30)
        except Exception:
            pass

    threading.Thread(target=_renew, daemon=True).start()
    return jsonify({'ok': True})