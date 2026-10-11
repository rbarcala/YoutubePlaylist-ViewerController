import json
import time
import threading
from services.obs_client import OBSController

_last_synced_bpm = None
_last_synced_track = None
_last_synced_playing = None

def sync_bpm_to_obs(load_config, bpm_val: float, progress_ms: int = 0, is_playing: bool = True):
    """Sincroniza el BPM, estado de música y la fase (progreso) de Spotify con los filtros de shader en OBS."""
    global _last_synced_bpm, _last_synced_playing
    if not bpm_val or bpm_val <= 0:
        bpm_val = 128.0

    cfg = load_config() if callable(load_config) else {}
    if not cfg.get("obs_enabled", True):
        return

    obs = OBSController(
        host=cfg.get("obs_host", "localhost"),
        port=cfg.get("obs_port", 4455),
        password=cfg.get("obs_password", "")
    )

    # Calcular beat_offset normalizado al período del compás (evita desfases por números grandes)
    progress_s = float(progress_ms) / 1000.0 if progress_ms > 0 else 0.0
    beat_period = 60.0 / float(bpm_val)
    beat_offset = (progress_s % beat_period) if is_playing else 0.0

    # Escenas y fuentes con shaders rítmicos (Baile 1-4, Kaleidoscopio/Orbitar, Bola de disco, etc.)
    candidate_sources = [
        "Baile", "Baile tuneado", "Baile super tuneado", "Baile super ultra tuneado",
        "Orbitar", "Bola disco", "BAILE", "Camara", "Cámara"
    ]
    current_scene = cfg.get("obs_scene_on_play")
    if current_scene and current_scene not in candidate_sources:
        candidate_sources.insert(0, current_scene)

    updated_any = False
    for source in candidate_sources:
        filter_res = obs.get_source_filters(source)
        if filter_res.get("success"):
            for f in filter_res.get("filters", []):
                fname = f.get("filterName")
                fkind = f.get("filterKind")
                if fkind == "shader_filter" or "shader" in fname.lower():
                    fsettings = f.get("filterSettings", {})
                    default_bpm = float(fsettings.get("bpm_default", 128.0))
                    effective_bpm = float(bpm_val) if is_playing else default_bpm
                    settings_payload = {
                        "bpm": effective_bpm,
                        "beat_offset": float(beat_offset),
                        "musica_activa": bool(is_playing)
                    }
                    obs.set_source_filter_settings(source, fname, settings_payload, overlay=True)
                    updated_any = True

    _last_synced_bpm = bpm_val
    _last_synced_playing = is_playing
    if updated_any:
        state_lbl = "EN VIVO" if is_playing else "PAUSADO (Default)"
        print(f"[spotify-bpm] Sincronizado a OBS [{state_lbl}]: {bpm_val} BPM | Progreso: {round(progress_s, 2)}s")

def start_spotify_monitor(spotify_mgr, broadcast_event, load_config=None):
    """Monitoriza el estado de Spotify y lo difunde, sincronizando BPM y estado con OBS."""
    def _loop():
        global _last_synced_track, _last_synced_bpm, _last_synced_playing
        time.sleep(2)
        while True:
            try:
                time.sleep(4)
                st = spotify_mgr.get_playback_state()
                if st and st.get("available"):
                    broadcast_event("spotify_state", st)

                    track_id = st.get("track_id") or st.get("title")
                    bpm = float(st.get("bpm") or 128.0)
                    progress_ms = int(st.get("progress_ms") or 0)
                    is_playing = bool(st.get("is_playing", False))

                    # Sincronizar al cambiar de canción, si el BPM cambió, o si se pausó/reanudó la música
                    if (track_id != _last_synced_track or bpm != _last_synced_bpm or is_playing != _last_synced_playing):
                        _last_synced_track = track_id
                        if load_config:
                            threading.Thread(
                                target=sync_bpm_to_obs,
                                args=(load_config, bpm, progress_ms, is_playing),
                                daemon=True
                            ).start()
            except Exception:
                pass
    threading.Thread(target=_loop, daemon=True, name="spotify-monitor").start()


def start_obs_monitor(load_config, broadcast_event, obs_scenes_cache, obs_scenes_lock, ws_manager):
    """Monitoriza el estado de OBS Studio (niveles de audio, escenas, etc.) y lo difunde."""
    def _loop():
        time.sleep(3)
        while True:
            try:
                cfg = load_config()
                # Verificar si hay clientes conectados antes de estresar el websocket de OBS
                with ws_manager.lock:
                    has_listeners = len(ws_manager.listeners) > 0
                
                if not has_listeners:
                    time.sleep(2)
                    continue

                obs = OBSController(
                    host=cfg.get("obs_host", "localhost"),
                    port=cfg.get("obs_port", 4455),
                    password=cfg.get("obs_password", "")
                )
                sock = obs._connect_and_identify(event_subscriptions=65536 | 8 | 4)
                if not sock:
                    time.sleep(3)
                    continue

                try:
                    obs.start_virtual_cam()
                except Exception:
                    pass

                sock.settimeout(3.0)
                last_emit = 0.0

                while True:
                    with ws_manager.lock:
                        if len(ws_manager.listeners) == 0:
                            break

                    frame = obs._recv_ws_frame(sock)
                    if not frame:
                        break

                    try:
                        msg = json.loads(frame)
                    except Exception:
                        continue

                    op = msg.get("op")
                    if op == 5:  # Event
                        event_type = msg.get("d", {}).get("eventType")
                        event_data = msg.get("d", {}).get("eventData", {})

                        if event_type == "InputVolumeMeters":
                            now = time.time()
                            if now - last_emit >= 0.08:
                                last_emit = now
                                inputs = event_data.get("inputs", [])
                                meter_map = {}
                                for inp in inputs:
                                    name = inp.get("inputName")
                                    levels = inp.get("inputLevelsMul", [])
                                    peak = 0.0
                                    for ch in levels:
                                        if ch and len(ch) > 0:
                                            peak = max(peak, float(ch[0]))
                                    meter_map[name] = round(peak, 4)
                                broadcast_event("obs_audio_levels", {"meters": meter_map})

                        elif event_type in ("InputMuteStateChanged", "InputVolumeChanged"):
                            broadcast_event("obs_audio_changed", event_data)

                        elif event_type == "CurrentProgramSceneChanged":
                            scene_name = event_data.get("sceneName", "")
                            with obs_scenes_lock:
                                obs_scenes_cache["current_scene"] = scene_name
                            broadcast_event("obs_updated", {"scene": scene_name})

                        elif event_type == "SceneListChanged":
                            try:
                                scenes_list = event_data.get("scenes", [])
                                if scenes_list:
                                    names = [s.get("sceneName") for s in reversed(scenes_list) if "sceneName" in s]
                                    with obs_scenes_lock:
                                        obs_scenes_cache["scenes"] = names
                                    broadcast_event("obs_scenes_list", {"scenes": names})
                            except Exception:
                                pass
                            broadcast_event("obs_status_changed", {})

                try:
                    sock.close()
                except Exception:
                    pass
                time.sleep(1)
            except Exception:
                time.sleep(3)

    threading.Thread(target=_loop, daemon=True, name="obs-monitor").start()
