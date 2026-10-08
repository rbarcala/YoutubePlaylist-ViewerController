# routes package - Flask Blueprints para YouTube Stream Controller
from .obs_routes import obs_bp, init_obs_routes
from .spotify_routes import spotify_bp, init_spotify_routes
from .soundboard_routes import soundboard_bp, init_soundboard_routes
from .youtube_routes import youtube_bp, init_youtube_routes
from .config_routes import config_bp, init_config_routes
from .static_routes import static_bp, init_static_routes
from .timer_routes import timer_bp, init_timer_routes
from .video_routes import video_bp, init_video_routes

__all__ = [
    'obs_bp',
    'spotify_bp',
    'soundboard_bp',
    'youtube_bp',
    'config_bp',
    'static_bp',
    'timer_bp',
    'video_bp',
    'init_obs_routes',
    'init_spotify_routes',
    'init_soundboard_routes',
    'init_youtube_routes',
    'init_config_routes',
    'init_static_routes',
    'init_timer_routes',
    'init_video_routes',
]