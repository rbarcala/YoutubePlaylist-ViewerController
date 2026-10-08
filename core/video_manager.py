import queue
import threading
from pathlib import Path
import yt_dlp

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
        while True:
            video_id = self.queue.get()
            try:
                with self.lock:
                    self.download_status[video_id] = 'downloading'
                
                output_template = str(self.cache_dir / f'{video_id}.%(ext)s')
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
                
                with self.lock:
                    self.download_status[video_id] = 'ready' if self.get_cached_path(video_id) else 'error'
            except Exception as exc:
                print(f'[video_manager] Error descargando {video_id}: {exc}')
                with self.lock:
                    self.download_status[video_id] = 'error'
            finally:
                self.queue.task_done()
