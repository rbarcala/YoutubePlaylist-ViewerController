#!/usr/bin/env python3
"""
YouTube Stream Controller — Servidor Flask Modular.
Registra Blueprints por dominio y gestiona estado compartido.
"""

import sys
from pathlib import Path
from flask import Flask

# ─── Configuración inicial ───
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Importar Servicios Centralizados
from services import (
    load_config, save_config,
    SpotifyManager, SoundboardManager,
    BrowserManager, OverlayManager,
    start_mdns_publisher
)

# Importar Managers de Core
from core import (
    ws_manager, broadcast_event, VideoManager,
    start_spotify_monitor, start_obs_monitor
)

# Importar Blueprints y sus funciones de inicialización
from routes import (
    obs_bp, init_obs_routes,
    spotify_bp, init_spotify_routes,
    soundboard_bp, init_soundboard_routes,
    youtube_bp, init_youtube_routes,
    config_bp, init_config_routes,
    static_bp, init_static_routes,
    timer_bp, init_timer_routes,
    video_bp, init_video_routes,
)

app = Flask(__name__, static_folder='static', static_url_path='')

# Directorio de cache de videos
VIDEO_CACHE_DIR = Path.home() / '.cache' / 'youtube-playlist-vc' / 'videos'
video_mgr = VideoManager(VIDEO_CACHE_DIR)

# ─── Inicializar managers ───
cfg_initial = load_config()
spotify_mgr = SpotifyManager(load_config, save_config)
soundboard_mgr = SoundboardManager(load_config, save_config, on_idle=lambda: broadcast_event("soundboard_stop", {}))
browser_mgr = BrowserManager()
overlay_mgr = OverlayManager(broadcast_event, load_config, save_config)

# ─── Estado global compartido ───
current_state = {
    "videoId": cfg_initial.get("last_played_video_id", ""),
    "title": cfg_initial.get("last_played_title", ""),
    "thumb": "",
    "playbackRate": float(cfg_initial.get("default_playback_rate", 1.7)),
    "muted": bool(cfg_initial.get("default_muted", True)),
    "volume": float(cfg_initial.get("default_volume", 1.0)),
    "loop": bool(cfg_initial.get("default_loop", False)),
    "autoplay": bool(cfg_initial.get("default_autoplay", True)),
    "isPlaying": False,
    "activeViewers": 0,
    "activeControllers": 0,
    "soundboard_volume": int(cfg_initial.get("soundboard_volume", 80)),
}

obs_scenes_cache = {"scenes": [], "current_scene": ""}
obs_scenes_lock = video_mgr.lock

# ─── Registrar Blueprints y inyectar dependencias ───
init_static_routes(
    state=current_state,
    ws_manager_inst=ws_manager,
    obs_cache=obs_scenes_cache,
    obs_lck=obs_scenes_lock,
    video_manager_inst=video_mgr,
    config_loader=load_config,
    config_saver=save_config,
    broadcast_fn=broadcast_event,
    browser_manager_inst=browser_mgr,
)
app.register_blueprint(static_bp)

init_config_routes(broadcast_event)
app.register_blueprint(config_bp)

init_obs_routes(load_config, broadcast_event, obs_scenes_cache, obs_scenes_lock)
app.register_blueprint(obs_bp)

init_spotify_routes(spotify_mgr, load_config, save_config, broadcast_event)
app.register_blueprint(spotify_bp)

init_soundboard_routes(soundboard_mgr, load_config, save_config, broadcast_event, browser_mgr)
app.register_blueprint(soundboard_bp)

init_youtube_routes(load_config, save_config, broadcast_event, current_state, video_mgr)
app.register_blueprint(youtube_bp)

init_timer_routes(overlay_mgr, load_config, save_config)
app.register_blueprint(timer_bp)

init_video_routes(video_mgr)
app.register_blueprint(video_bp)

# Cache de URLs de video
app.video_cache = video_mgr.video_url_cache

# Iniciar monitores en background
start_spotify_monitor(spotify_mgr, broadcast_event)
start_obs_monitor(load_config, broadcast_event, obs_scenes_cache, obs_scenes_lock, ws_manager)

# ─── Punto de entrada principal ───
if __name__ == '__main__':
    cfg = load_config()
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else int(cfg.get("port", 8000))
    host = cfg.get("host", "0.0.0.0")
    print(f"[fondos-stream] Iniciando servidor en http://{host}:{puerto}")
    try:
        start_mdns_publisher(puerto)
    except Exception as e:
        print(f"[mDNS] No se pudo iniciar publicador mDNS: {e}")
    app.run(host=host, port=puerto, threaded=True)
