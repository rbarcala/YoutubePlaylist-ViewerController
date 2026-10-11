import queue
import threading
import logging
from pathlib import Path
import yt_dlp

logger = logging.getLogger(__name__)

class VideoManager:
    """Gestiona la descarga y cache de videos de YouTube."""
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.download_status = {}
        self.lock = threading.Lock()
        self.queue = queue.Queue()
        self.video_url_cache = {} # Cache de URLs temporales (get_video_url)

        # Iniciar worker
        threading.Thread(target=self._download_worker, daemon=True, name='video-cache-worker').start()

    def get_cached_path(self, video_id):
        """Busca si el video ya está descargado en el cache."""
        candidates = [
            path for path in self.cache_dir.glob(f'{video_id}.*')
            if not path.name.endswith(('.part', '.ytdl'))
        ]
        return candidates[0] if candidates else None

    def queue_download(self, video_id):
        """Añade un video a la cola de descarga si no está ya en ella o descargado."""
        with self.lock:
            if self.download_status.get(video_id) in ('queued', 'downloading') or self.get_cached_path(video_id):
                return
            self.download_status[video_id] = 'queued'
        self.queue.put(video_id)

    def _download_worker(self):
        class _SilentLogger:
            def debug(self, msg):
                pass
            def warning(self, msg):
                pass
            def error(self, msg):
                pass

        while True:
            video_id = self.queue.get()
            try:
                with self.lock:
                    self.download_status[video_id] = 'downloading'
                
                output_template = str(self.cache_dir / f'{video_id}.%(ext)s')
                url = f'https://www.youtube.com/watch?v={video_id}'
                fmt_spec = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]/best'
                opts = {
                    'format': fmt_spec,
                    'outtmpl': output_template,
                    'merge_output_format': 'mp4',
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android', 'android_vr', 'web']
                        }
                    },
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True,
                    'logger': _SilentLogger(),
                }
                
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])
                except Exception:
                    from services.browser_cookie_detector import get_youtube_cookiefile
                    cookiefile = get_youtube_cookiefile()
                    if cookiefile:
                        auth_opts = {
                            'format': fmt_spec,
                            'outtmpl': output_template,
                            'merge_output_format': 'mp4',
                            'cookiefile': cookiefile,
                            'js_runtimes': {'node': {}},
                            'remote_components': ['ejs:github'],
                            'extractor_args': {
                                'youtube': {
                                    'player_client': ['mweb', 'web']
                                }
                            },
                            'quiet': True,
                            'no_warnings': True,
                            'noplaylist': True,
                            'logger': _SilentLogger(),
                        }
                        with yt_dlp.YoutubeDL(auth_opts) as ydl:
                            ydl.download([url])
                    else:
                        raise
                
                with self.lock:
                    self.download_status[video_id] = 'ready' if self.get_cached_path(video_id) else 'error'
            except Exception as exc:
                logger.error(f'[video_manager] Error descargando {video_id}: {exc}')
                with self.lock:
                    self.download_status[video_id] = 'error'
            finally:
                self.queue.task_done()

