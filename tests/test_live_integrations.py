"""
Tests de Integración con APIs y Servicios Reales.
Lee las credenciales y claves guardadas localmente en la máquina del usuario
(mediante services.config_manager.load_config() / variables de entorno).

¡NUNCA expone ni guarda las claves en el repositorio de git!
Si una clave no está configurada, el test correspondiente se salta (skip) elegantemente.
"""

import os
import unittest
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from services.config_manager import load_config
from services.spotify_manager import SpotifyManager
from services.soundboard_manager import SoundboardManager
from services.overlay_manager import OverlayManager
from core.video_manager import VideoManager
from server import app


class TestLiveIntegrations(unittest.TestCase):
    """
    Categoría de pruebas con servicios y APIs reales utilizando
    las credenciales configuradas en el sistema local.
    """

    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.client = app.test_client()

    # ─────────────────────────────────────────────────────────────
    # 1. YOUTUBE API (FONDOS, PLAYLISTS Y CANAL)
    # ─────────────────────────────────────────────────────────────

    def test_youtube_playlist_live(self):
        """Prueba de obtención de fondos/videos de la playlist real usando la YouTube API Key."""
        api_key = self.config.get("youtube_api_key") or os.environ.get("YOUTUBE_API_KEY")
        playlist_id = self.config.get("playlist_id") or os.environ.get("YOUTUBE_PLAYLIST_ID")

        if not api_key:
            self.skipTest("YouTube API Key no está configurada en la máquina.")
        if not playlist_id:
            self.skipTest("Playlist ID no está configurada en la máquina.")

        res = self.client.get(f"/api/youtube/playlist?playlist_id={playlist_id}&key={api_key}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertTrue(data.get("success"), f"La API de YouTube retornó error: {data.get('error')}")
        videos = data.get("videos", [])
        self.assertGreater(len(videos), 0, "La playlist debe contener al menos 1 video")

        first = videos[0]
        self.assertTrue(bool(first.get("id")), "El video debe tener un 'id' válido")
        self.assertTrue(bool(first.get("title")), "El video debe tener un 'title'")

    def test_youtube_channel_live_detection(self):
        """Prueba de detección del canal de YouTube configurado (por ID o Handle @)."""
        api_key = self.config.get("youtube_api_key") or os.environ.get("YOUTUBE_API_KEY")
        channel_id = self.config.get("youtube_channel_id") or os.environ.get("YOUTUBE_CHANNEL_ID")

        if not api_key:
            self.skipTest("YouTube API Key no está configurada en la máquina.")
        if not channel_id:
            self.skipTest("Canal de YouTube no configurado en la máquina.")

        res = self.client.get("/api/youtube/live")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertIn("is_live", data)
        self.assertTrue(bool(data.get("channel_id")), "Debe resolver o contener el ID del canal")
        self.assertNotIn("API Key no configurados", data.get("error", ""))

    def test_youtube_video_stream_url_resolution(self):
        """Prueba de resolución de URL directa de video para reproducción en Viewer."""
        # Usar el último video reproducido o un video genérico de prueba
        video_id = self.config.get("last_played_video_id") or "dQw4w9WgXcQ"
        res = self.client.get(f"/api/get_video_url?v={video_id}&mode=stream")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertTrue(bool(data.get("video_url")), "Debe generar una URL de streaming ejecutable")
        self.assertIn("expires_at", data)

    # ─────────────────────────────────────────────────────────────
    # 2. SPOTIFY API & MPRIS LOCAL
    # ─────────────────────────────────────────────────────────────

    def test_spotify_token_refresh_and_search_live(self):
        """Prueba que el token de Spotify se refresque correctamente y permita buscar canciones."""
        client_id = self.config.get("spotify_client_id")
        client_secret = self.config.get("spotify_client_secret")
        refresh_token = self.config.get("spotify_refresh_token")

        if not (client_id and client_secret and refresh_token):
            self.skipTest("Credenciales de Spotify (Client ID / Secret / Refresh Token) no configuradas en la máquina.")

        sm = SpotifyManager(load_config, lambda c: None)
        token = sm.refresh_access_token_if_needed()
        self.assertTrue(bool(token), "SpotifyManager debe poder refrescar el access token con las credenciales locales")

        search_res = sm.search("Miranda")
        self.assertIsInstance(search_res, dict)
        has_items = bool(search_res.get("tracks") or search_res.get("playlists") or search_res.get("artists"))
        self.assertTrue(has_items, "La búsqueda en la API de Spotify debe devolver resultados válidos")

    def test_spotify_playback_state_live(self):
        """Prueba que el estado de reproducción de Spotify local (MPRIS/API) retorne el esquema correcto."""
        res = self.client.get("/api/spotify/state")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        for key in ["available", "is_playing", "title", "artist", "album_art"]:
            self.assertIn(key, data, f"El estado de Spotify debe incluir la clave '{key}'")

    def test_spotify_lyrics_resolution_live(self):
        """Prueba de búsqueda y obtención de letras reales (incluyendo sincronizadas)."""
        res = self.client.get("/api/spotify/lyrics?artist=Miranda!&title=Romance%20Juvenil")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertIn("lyrics", data)
        self.assertIn("syncedLyrics", data)
        self.assertTrue(bool(data.get("lyrics")), "Debe encontrar las letras para Miranda! - Romance Juvenil")

    # ─────────────────────────────────────────────────────────────
    # 3. SOUNDBOARD (FAVORITOS Y RECURSOS)
    # ─────────────────────────────────────────────────────────────

    def test_soundboard_favorites_and_auth_live(self):
        """Prueba que el módulo de Soundboard lea la sesión y favoritos guardados del usuario."""
        sbm = SoundboardManager(load_config, lambda c: None)
        status = sbm.get_auth_status()

        self.assertIn("logged_in", status)
        self.assertIn("favorites_count", status)

        # Si el usuario tiene sesión guardada en la máquina:
        if status.get("has_session"):
            self.assertTrue(status.get("logged_in"), "Si hay sesión, debe reportarse logueado")
            favs = sbm.get_saved_favorites()
            self.assertIsInstance(favs, list)

    # ─────────────────────────────────────────────────────────────
    # 4. OVERLAY & ESTÁTICOS
    # ─────────────────────────────────────────────────────────────

    def test_overlay_icon_asset_serving(self):
        """Prueba que el icono oficial /assets/icon.png se sirva para evitar portadas rotas."""
        res = self.client.get("/assets/icon.png")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("Content-Type"), "image/png")

    def test_overlay_html_and_js_serving(self):
        """Prueba que los componentes del overlay se sirvan correctamente."""
        res_html = self.client.get("/overlay.html")
        self.assertEqual(res_html.status_code, 200)

        res_js = self.client.get("/js/overlay.js")
        self.assertEqual(res_js.status_code, 200)


if __name__ == '__main__':
    unittest.main()

