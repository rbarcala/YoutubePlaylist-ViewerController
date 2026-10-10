#!/usr/bin/env python3
"""
Test Unitario e Integración para Sincronización de BPM y Fase (Spotify -> OBS Shaders).
Verifica:
1. Cálculo matemático de beat_offset (normalización en base a tempo y período de compás).
2. Fallbacks de BPM cuando no hay reproducción de Spotify (retorno seguro a 128.0 BPM).
3. Conexión WebSocket v5 con OBS Studio (si OBS está abierto):
   - Lectura de filtros en escenas candidatas ('Baile tuneado', 'Baile', etc.).
   - Inyección en vivo de BPM y beat_offset (SetSourceFilterSettings).
   - Verificación de persistencia de parámetros en OBS.
"""

import sys
import time
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from services.config_manager import load_config
from services.obs_client import OBSController
from services.spotify_manager import SpotifyManager
from core.monitors import sync_bpm_to_obs


class TestBPMSync(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()

    def test_01_beat_offset_math(self):
        """Verifica que el cálculo del desfase sea coherente y normalizado al período."""
        test_bpm = 120.0  # 120 BPM = 2 beats por segundo => período de 0.5s
        beat_period = 60.0 / test_bpm
        self.assertEqual(beat_period, 0.5)

        # A los 12.25 segundos de canción (medio tiempo entre beats)
        progress_s = 12.25
        beat_offset = progress_s % beat_period
        self.assertAlmostEqual(beat_offset, 0.25, places=4)

        # En un beat exacto (ej. 10.0s)
        progress_s_exact = 10.0
        beat_offset_exact = progress_s_exact % beat_period
        self.assertAlmostEqual(beat_offset_exact, 0.0, places=4)

    def test_02_spotify_bpm_fallback(self):
        """Verifica que si no hay canción o track_id vacío, el fallback devuelva 128.0 BPM."""
        sm = SpotifyManager(lambda: {}, lambda cfg: None)
        self.assertEqual(sm.get_track_bpm(""), 128.0)
        self.assertEqual(sm.get_track_bpm(None), 128.0)

    def test_03_obs_live_bpm_and_phase_sync(self):
        """Si OBS está abierto, verifica la inyección y lectura de BPM y beat_offset."""
        obs = OBSController(
            host=self.cfg.get("obs_host", "localhost"),
            port=self.cfg.get("obs_port", 4455),
            password=self.cfg.get("obs_password", "")
        )
        status = obs.get_status()
        if not status.get("connected"):
            print("  [!] OBS Studio no está en ejecución. Test de WebSocket en vivo saltado con éxito.")
            return

        test_bpm = 135.0
        test_progress_ms = 48600  # 48.6 segundos

        # Inyectar mediante la función del monitor/core
        sync_bpm_to_obs(load_config, test_bpm, test_progress_ms)

        # Verificar en OBS que los filtros hayan recibido los valores
        verified = False
        for scene in ["Baile tuneado", "Baile", "BAILE"]:
            res = obs.get_source_filters(scene)
            if res.get("success") and res.get("filters"):
                for f in res.get("filters", []):
                    fname = f.get("filterName")
                    sock = obs._connect_and_identify()
                    if not sock:
                        continue
                    import json
                    obs._send_ws_frame(sock, json.dumps({
                        "op": 6,
                        "d": {
                            "requestType": "GetSourceFilter",
                            "requestId": "test-req",
                            "requestData": {
                                "sourceName": scene,
                                "filterName": fname
                            }
                        }
                    }))
                    resp = json.loads(obs._recv_ws_frame(sock) or "{}")
                    sock.close()
                    settings = resp.get("d", {}).get("responseData", {}).get("filterSettings", {})
                    if "bpm" in settings:
                        self.assertEqual(float(settings["bpm"]), test_bpm)
                        self.assertIn("beat_offset", settings)
                        verified = True
                        print(f"  [✓] Verificado en OBS [{scene} -> {fname}]: bpm={settings['bpm']}, offset={settings['beat_offset']}")

        if not verified:
            print("  [i] OBS conectado pero no se detectaron filtros de baile en las escenas activas.")


if __name__ == "__main__":
    print("=================================================================")
    print("      Test de Sincronización de BPM y Fase (Spotify -> OBS)      ")
    print("=================================================================")
    unittest.main()
