"""Pruebas unitarias para las rutas modularizadas en Flask."""
import unittest
import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from server import app


class TestRoutes(unittest.TestCase):
    """Pruebas para las rutas de la aplicación modular."""

    def setUp(self):
        self.client = app.test_client()

    def test_state_route(self):
        response = self.client.get('/api/state')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("videoId", data)
        self.assertIn("playbackRate", data)

    def test_network_info_route(self):
        response = self.client.get('/api/network_info')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("lan_ip", data)
        self.assertIn("port", data)
        self.assertIn("qr_code_svg", data)

    def test_config_get_masks_secrets(self):
        response = self.client.get('/api/config')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertNotIn("spotify_client_secret", data)
        self.assertNotIn("youtube_api_key", data)
        self.assertIn("has_api_key", data)

    def test_timer_status(self):
        response = self.client.get('/api/timer/status')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("active", data)
        self.assertIn("running", data)

    def test_timer_phrases(self):
        response = self.client.get('/api/timer/phrases')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("phrases", data)

    def test_soundboard_favorites_get(self):
        response = self.client.get('/api/soundboard/favorites')
        self.assertEqual(response.status_code, 200)

    def test_action_handler_state(self):
        response = self.client.post('/api/action', json={"action": "state", "playbackRate": 2.0})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("state", {}).get("playbackRate"), 2.0)

    def test_cache_status_unknown_video(self):
        response = self.client.get('/api/cache/status/xyz999')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("status", data)

    def test_static_html_served(self):
        for page in ['/viewer.html', '/controller.html', '/overlay.html']:
            res = self.client.get(page)
            _ = res.data
            self.assertEqual(res.status_code, 200, f"Error cargando {page}")

    def test_modular_css_served(self):
        css_files = ['/css/theme.css', '/css/controller.css', '/css/responsive.css', '/css/overlay.css']
        for css in css_files:
            res = self.client.get(css)
            _ = res.data
            self.assertEqual(res.status_code, 200, f"Error cargando {css}")
            self.assertGreater(len(res.data), 0)

    def test_modular_js_served(self):
        js_files = [
            '/js/state.js',
            '/js/modules/youtube.js',
            '/js/modules/obs.js',
            '/js/modules/spotify.js',
            '/js/modules/soundboard.js',
            '/js/modules/modals.js',
            '/js/modules/timer.js',
            '/js/overlay.js',
        ]
        for js in js_files:
            res = self.client.get(js)
            _ = res.data
            self.assertEqual(res.status_code, 200, f"Error cargando {js}")
            self.assertGreater(len(res.data), 0)


if __name__ == '__main__':
    unittest.main()
