"""Shim de compatibilidad hacia services.spotify_manager."""
import subprocess
from services.spotify_manager import SpotifyManager

__all__ = ['SpotifyManager', 'subprocess']
