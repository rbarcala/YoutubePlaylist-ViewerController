import json
import time
import threading
from services.obs_client import OBSController

def start_spotify_monitor(spotify_mgr, broadcast_event):
    """Monitoriza el estado de Spotify y lo difunde."""
    def _loop():
        time.sleep(2)
        while True:
            try:
                time.sleep(6)
                st = spotify_mgr.get_playback_state()
                if st and st.get("available"):
                    broadcast_event("spotify_state", st)
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
