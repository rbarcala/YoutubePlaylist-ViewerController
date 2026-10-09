from flask import Blueprint, jsonify, send_from_directory

video_bp = Blueprint('video', __name__)

# Variable que se inyecta desde server.py
video_manager = None


def init_video_routes(video_mgr):
    global video_manager
    video_manager = video_mgr


@video_bp.route('/api/cache/video/<video_id>')
def serve_cached_video(video_id):
    if not video_manager:
        return jsonify({'error': 'Gestor de video no inicializado'}), 500
    cached_path = video_manager.get_cached_path(video_id)
    if not cached_path:
        return jsonify({'error': 'Video todavía no está disponible en cache'}), 404
    return send_from_directory(video_manager.cache_dir, cached_path.name, conditional=True)


@video_bp.route('/api/cache/status/<video_id>')
def cached_video_status(video_id):
    if not video_manager:
        return jsonify({'status': 'idle'})
    cached_path = video_manager.get_cached_path(video_id)
    if cached_path:
        return jsonify({'status': 'ready', 'url': f'/api/cache/video/{video_id}'})
    with video_manager.lock:
        status = video_manager.download_status.get(video_id, 'idle')
    return jsonify({'status': status})