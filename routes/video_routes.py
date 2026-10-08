from flask import Blueprint, request, jsonify, send_from_directory
from pathlib import Path
import threading
import queue

video_bp = Blueprint('video', __name__)

# Variables que se inyectan desde server.py
VIDEO_CACHE_DIR = None
video_download_status = None
video_download_lock = None
video_download_queue = None


def init_video_routes(vcache_dir, vdl_status, vdl_lck, vd_queue):
    global VIDEO_CACHE_DIR, video_download_status, video_download_lock, video_download_queue
    VIDEO_CACHE_DIR = vcache_dir
    video_download_status = vdl_status
    video_download_lock = vdl_lck
    video_download_queue = vd_queue


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


@video_bp.route('/api/cache/video/<video_id>')
def serve_cached_video(video_id):
    cached_path = _cached_video_path(video_id)
    if not cached_path:
        return jsonify({'error': 'Video todavía no está disponible en cache'}), 404
    return send_from_directory(VIDEO_CACHE_DIR, cached_path.name, conditional=True)


@video_bp.route('/api/cache/status/<video_id>')
def cached_video_status(video_id):
    cached_path = _cached_video_path(video_id)
    if cached_path:
        return jsonify({'status': 'ready', 'url': f'/api/cache/video/{video_id}'})
    with video_download_lock:
        status = video_download_status.get(video_id, 'idle')
    return jsonify({'status': status})