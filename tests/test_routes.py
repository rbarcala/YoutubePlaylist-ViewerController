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
        css_files = [
            '/css/theme.css',
            '/css/base.css',
            '/css/controller.css',
            '/css/responsive.css',
            '/css/overlay.css',
            '/css/viewer.css',
            '/css/views/fondos.css',
            '/css/views/obs.css',
            '/css/views/spotify.css',
            '/css/views/soundboard.css',
            '/css/views/overlays.css',
        ]
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
            '/js/viewer.js',
        ]
        for js in js_files:
            res = self.client.get(js)
            _ = res.data
            self.assertEqual(res.status_code, 200, f"Error cargando {js}")
            self.assertGreater(len(res.data), 0)


    def test_controller_renders_all_partials(self):
        """Verifica que el controller compile e incluya todas las vistas modulares."""
        res = self.client.get('/controller.html')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        for view_id in ['view-menu', 'view-fondos', 'view-obs', 'view-spotify', 'view-soundboard', 'view-overlays', 'settingsModal']:
            self.assertIn(f'id="{view_id}"', html, f"Falta el módulo/vista {view_id} en el controller")

    def test_open_browser_endpoint(self):
        """Verifica que el endpoint /api/open_browser responda correctamente."""
        res = self.client.post('/api/open_browser?url=https://example.com')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('url'), 'https://example.com')

    def test_spotify_auth_url_endpoints(self):
        """Verifica que /api/spotify/auth_url soporte tanto GET como POST con credenciales."""
        # GET
        res_get = self.client.get('/api/spotify/auth_url')
        self.assertEqual(res_get.status_code, 200)

        # POST con client_id
        res_post = self.client.post('/api/spotify/auth_url', json={'client_id': 'test_id', 'client_secret': 'test_sec'})
        self.assertEqual(res_post.status_code, 200)
        data = res_post.get_json()
        self.assertIn('auth_url', data)
        self.assertIn('client_id=test_id', data['auth_url'])

    def test_soundboard_detect_browser_session(self):
        """Verifica que el endpoint de detección de sesión de navegador responda correctamente."""
        res = self.client.get('/api/soundboard/detect_browser_session')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('found', data)

    def test_soundboard_login_window_route(self):
        """Verifica que /api/soundboard/login_window responda exitosamente."""
        res = self.client.post('/api/soundboard/login_window', json={'client_id': 'test_client'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))

    def test_soundboard_auth_status_route(self):
        """Verifica que /api/soundboard/auth devuelva el estado de sesión."""
        res = self.client.get('/api/soundboard/auth')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('logged_in', data)


if __name__ == '__main__':
    unittest.main()
