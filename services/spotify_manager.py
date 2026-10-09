"""
Gestor de Integración con Spotify (Spotify Connect Web API + MPRIS Local Linux)
Permite buscar canciones, controlar reproducción, cola y volumen del cliente Spotify en la PC.
"""

import json
import time
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path

class SpotifyManager:
    def __init__(self, config_getter, config_saver):
        self.get_config = config_getter
        self.save_config = config_saver
        self._last_seek_time = 0
        self._last_seek_pos = 0
        self._last_volume_time = 0
        self._last_volume = 50
        self._state_cache = None
        self._state_cache_time = 0

    def _get_tokens(self):
        cfg = self.get_config()
        return {
            "client_id": cfg.get("spotify_client_id", ""),
            "client_secret": cfg.get("spotify_client_secret", ""),
            "access_token": cfg.get("spotify_access_token", ""),
            "refresh_token": cfg.get("spotify_refresh_token", ""),
            "token_expires_at": cfg.get("spotify_token_expires_at", 0)
        }

    def get_auth_url(self, redirect_uri: str) -> str:
        """Genera la URL para iniciar sesión con Spotify."""
        tokens = self._get_tokens()
        client_id = tokens["client_id"]
        if not client_id:
            return ""

        scopes = "user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private user-read-playback-position"
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "show_dialog": "true"
        }
        return f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Intercambia el código de autorización por tokens de acceso."""
        tokens = self._get_tokens()
        client_id = tokens["client_id"]
        client_secret = tokens["client_secret"]
        if not client_id or not client_secret:
            return {"success": False, "error": "Falta client_id o client_secret de Spotify"}

        data = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret
        }).encode('utf-8')

        req = urllib.request.Request("https://accounts.spotify.com/api/token", data=data, method="POST")
        try:
            with urllib.request.urlopen(req) as res:
                resp_data = json.loads(res.read().decode('utf-8'))
                access_token = resp_data.get("access_token")
                refresh_token = resp_data.get("refresh_token")
                expires_in = resp_data.get("expires_in", 3600)

                self.save_config({
                    "spotify_access_token": access_token,
                    "spotify_refresh_token": refresh_token or tokens["refresh_token"],
                    "spotify_token_expires_at": time.time() + expires_in - 60
                })
                return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def refresh_access_token_if_needed(self) -> str:
        """Refresca el token si ha expirado."""
        tokens = self._get_tokens()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        expires_at = tokens["token_expires_at"]

        if access_token and time.time() < expires_at:
            return access_token

        if not refresh_token:
            return access_token  # Si el usuario ingresó token manual

        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": tokens["client_id"],
            "client_secret": tokens["client_secret"]
        }).encode('utf-8')

        req = urllib.request.Request("https://accounts.spotify.com/api/token", data=data, method="POST")
        try:
            with urllib.request.urlopen(req) as res:
                resp = json.loads(res.read().decode('utf-8'))
                new_token = resp.get("access_token")
                expires_in = resp.get("expires_in", 3600)
                self.save_config({
                    "spotify_access_token": new_token,
                    "spotify_token_expires_at": time.time() + expires_in - 60
                })
                return new_token
        except Exception:
            return access_token

    def _api_request(self, endpoint: str, method: str = "GET", body: dict = None) -> dict:
        token = self.refresh_access_token_if_needed()
        if not token:
            # Fallback a MPRIS local si no hay token configurado
            return self._mpris_fallback(endpoint, method, body)

        url = f"https://api.spotify.com/v1/{endpoint.lstrip('/')}"
        data = json.dumps(body).encode('utf-8') if body else None
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as res:
                if res.status == 204:
                    return {"success": True}
                content = res.read().decode('utf-8')
                return json.loads(content) if content else {"success": True}
        except urllib.error.HTTPError as e:
            # Si da error en la API, intentar fallback MPRIS local
            mpris_res = self._mpris_fallback(endpoint, method, body)
            if mpris_res.get("handled"):
                return mpris_res
            try:
                err_body = json.loads(e.read().decode('utf-8'))
                return {"error": err_body.get("error", {}).get("message", str(e))}
            except Exception:
                return {"error": str(e)}
        except Exception as e:
            return {"error": str(e)}

    # ─── CONTROLES DE REPRODUCCIÓN ───
    def get_playback_state(self) -> dict:
        """Obtiene el estado actual de reproducción."""
        import time
        if self._state_cache and time.time() - self._state_cache_time < 5.0:
            return self._state_cache
            
        res = self._api_request("me/player")
        # Si la API da error, está vacía, o devuelve 204 No Content (sin 'item')
        if "error" in res or not res or not res.get("item"):
            # Intentar leer desde MPRIS en Ubuntu (Spotify app local abierta)
            mpris_state = self._get_mpris_state()
            if mpris_state.get("available"):
                return mpris_state

        if res and res.get("item"):
            item = res["item"]
            artists = ", ".join([a["name"] for a in item.get("artists", [])])
            album_art = ""
            if item.get("album", {}).get("images"):
                album_art = item["album"]["images"][0]["url"]

            progress_ms = res.get("progress_ms", 0)
            is_playing = res.get("is_playing", False)
            duration_ms = item.get("duration_ms", 0)

            # Optimistic seek resolution: si hubo un seek en los últimos 3.5 segundos y el backend aún reporta la posición vieja
            now = time.time()
            if (now - self._last_seek_time) < 3.5:
                elapsed = int((now - self._last_seek_time) * 1000) if is_playing else 0
                estimated_pos = min(duration_ms, self._last_seek_pos + elapsed)
                if abs(progress_ms - estimated_pos) > 2000:
                    progress_ms = estimated_pos

            volume_pct = res.get("device", {}).get("volume_percent", 50)
            if (now - self._last_volume_time) < 3.0:
                volume_pct = self._last_volume

            return {
                "available": True,
                "is_playing": is_playing,
                "title": item.get("name", "Desconocido"),
                "artist": artists,
                "album": item.get("album", {}).get("name", ""),
                "album_art": album_art,
                "progress_ms": progress_ms,
                "duration_ms": duration_ms,
                "volume_percent": volume_pct,
                "device_name": res.get("device", {}).get("name", "PC")
            }

        return {"available": False, "is_playing": False, "title": "Sin reproducción", "artist": "", "album_art": ""}

    def play(self, context_uri: str = None, track_uris: list = None) -> dict:
        body = {}
        if context_uri:
            body["context_uri"] = context_uri
        elif track_uris:
            body["uris"] = track_uris
        return self._api_request("me/player/play", method="PUT", body=body if body else None)

    def pause(self) -> dict:
        return self._api_request("me/player/pause", method="PUT")

    def next_track(self) -> dict:
        return self._api_request("me/player/next", method="POST")

    def previous_track(self) -> dict:
        return self._api_request("me/player/previous", method="POST")

    def seek(self, position_ms: int) -> dict:
        """Adelanta o retrocede a un minuto/segundo específico de la canción."""
        pos = max(0, int(position_ms))
        self._last_seek_time = time.time()
        self._last_seek_pos = pos
        res = self._api_request(f"me/player/seek?position_ms={pos}", method="PUT")
        if "error" in res:
            try:
                import subprocess
                subprocess.run([
                    "gdbus", "call", "--session", "--dest", "org.mpris.MediaPlayer2.spotify",
                    "--object-path", "/org/mpris/MediaPlayer2", "--method",
                    "org.mpris.MediaPlayer2.Player.SetPosition",
                    "/org/mpris/MediaPlayer2/TrackList/NoTrack", str(pos * 1000)
                ], capture_output=True, timeout=1)
            except Exception:
                pass
        return res

    def set_volume(self, volume_percent: int) -> dict:
        vol = max(0, min(100, int(volume_percent)))
        self._last_volume_time = time.time()
        self._last_volume = vol
        return self._api_request(f"me/player/volume?volume_percent={vol}", method="PUT")

    def add_to_queue(self, uri: str) -> dict:
        encoded = urllib.parse.quote(uri)
        return self._api_request(f"me/player/queue?uri={encoded}", method="POST")

    def search(self, query: str) -> dict:
        if not query:
            return {"tracks": []}
        encoded = urllib.parse.quote(query)
        items = []
        error = None
        
        # Hacemos hasta 4 paginaciones de 10 para devolver 40 resultados
        # debido al nuevo límite restrictivo de 10 de Spotify Web API.
        for offset in [0, 10, 20, 30]:
            res = self._api_request(f"search?q={encoded}&type=track&limit=10&offset={offset}")
            if "tracks" in res:
                page_items = res["tracks"].get("items", [])
                if not page_items:
                    break
                for t in page_items:
                    items.append({
                        "id": t.get("id"),
                        "uri": t.get("uri"),
                        "title": t.get("name"),
                        "artist": ", ".join([a.get("name", "") for a in t.get("artists", [])]),
                        "album": t.get("album", {}).get("name", ""),
                        "thumb": (t.get("album", {}).get("images", [{}])[1].get("url") if len(t.get("album", {}).get("images", [])) > 1 else t.get("album", {}).get("images", [{}])[0].get("url", "")) if t.get("album", {}).get("images") else "",
                        "duration_ms": t.get("duration_ms", 0)
                    })
            else:
                if not items:
                    error = res.get("error")
                break
                
        if items:
            return {"tracks": items}
        return {"tracks": [], "error": error}

    def get_playlist(self, playlist_id: str, refresh: bool = False) -> dict:
        """Obtiene todas las canciones de una playlist de Spotify, paginando automáticamente con cache."""
        now = time.time()
        if not hasattr(self, '_playlist_cache'):
            self._playlist_cache = {}
        if not refresh and playlist_id in self._playlist_cache:
            cached_data, exp = self._playlist_cache[playlist_id]
            if now < exp and cached_data:
                return cached_data

        res = self._api_request(f"playlists/{playlist_id}")
        if not res or "error" in res:
            return {"tracks": [], "error": res.get("error") if isinstance(res, dict) else "Error de conexión"}

        name = res.get("name", "Playlist")
        tracks_obj = res.get("tracks") or res.get("items")
        all_raw_items = []

        if tracks_obj and isinstance(tracks_obj, dict):
            all_raw_items.extend(tracks_obj.get("items", []))
            total = tracks_obj.get("total", len(all_raw_items))
            offset = len(all_raw_items)

            # Paginar para traer todas las canciones (límite de seguridad 1000)
            while offset < total and offset < 1000:
                next_batch = self._api_request(f"playlists/{playlist_id}/items?offset={offset}&limit=100")
                if not next_batch or not isinstance(next_batch, dict) or not next_batch.get("items"):
                    next_batch = self._api_request(f"playlists/{playlist_id}/tracks?offset={offset}&limit=100")

                if next_batch and isinstance(next_batch, dict) and next_batch.get("items"):
                    batch_items = next_batch.get("items", [])
                    all_raw_items.extend(batch_items)
                    offset += len(batch_items)
                else:
                    break

        items = []
        for idx, item in enumerate(all_raw_items):
            if not isinstance(item, dict): continue
            t = item.get("track") or item.get("item")
            if not t or not isinstance(t, dict): continue

            # Extraer carátula
            thumb = ""
            album = t.get("album")
            if isinstance(album, dict) and album.get("images"):
                imgs = album["images"]
                thumb = imgs[1].get("url", "") if len(imgs) > 1 else (imgs[0].get("url", "") if imgs else "")

            # Formatear artistas
            artists = ", ".join([a.get("name", "") for a in t.get("artists", []) if isinstance(a, dict) and a.get("name")])

            items.append({
                "index": idx + 1,
                "id": t.get("id") or f"track_{idx}",
                "uri": t.get("uri") or f"spotify:track:{t.get('id')}",
                "title": t.get("name", "Sin título"),
                "artist": artists or "Desconocido",
                "album": album.get("name", "") if isinstance(album, dict) else "",
                "thumb": thumb,
                "duration_ms": t.get("duration_ms", 0)
            })

        out = {"name": name, "tracks": items, "total": len(items)}
        self._playlist_cache[playlist_id] = (out, now + 3600)
        return out

    # ─── FALLBACK MPRIS PARA SPOTIFY LOCAL EN LINUX ───
    def _mpris_call(self, method: str):
        cmd = ["gdbus", "call", "--session", "--dest", "org.mpris.MediaPlayer2.spotify",
               "--object-path", "/org/mpris/MediaPlayer2", "--method", f"org.mpris.MediaPlayer2.Player.{method}"]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1.5)
            return {"success": True, "handled": True}
        except Exception:
            return {"handled": False}

    def _mpris_fallback(self, endpoint: str, method: str, body: dict = None) -> dict:
        if "play" in endpoint and method == "PUT":
            return self._mpris_call("Play")
        elif "pause" in endpoint and method == "PUT":
            return self._mpris_call("Pause")
        elif "next" in endpoint:
            return self._mpris_call("Next")
        elif "previous" in endpoint:
            return self._mpris_call("Previous")
        return {"handled": False}

    def _get_mpris_state(self) -> dict:
        import shutil
        import time
        try:
            if shutil.which("playerctl"):
                status_res = subprocess.run(["playerctl", "-p", "spotify", "status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
                if status_res.returncode == 0:
                    is_playing = "Playing" in status_res.stdout
                    meta_res = subprocess.run(["playerctl", "-p", "spotify", "metadata"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
                    
                    title = "Spotify Desktop"
                    artist = "Unknown Artist"
                    art_url = ""
                    
                    for line in meta_res.stdout.splitlines():
                        if "xesam:title" in line:
                            title = line.split("xesam:title")[-1].strip()
                        elif "xesam:artist" in line:
                            artist = line.split("xesam:artist")[-1].strip()
                        elif "mpris:artUrl" in line:
                            art_url = line.split("mpris:artUrl")[-1].strip()
                            
                    if title.startswith("http"):
                        title = "Reproduciendo (Sin título)"
                        
                    # Extraer posicion para sincronizar lyrics!
                    progress_ms = 0
                    duration_ms = 0
                    
                    pos_res = subprocess.run(["playerctl", "-p", "spotify", "position"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
                    if pos_res.returncode == 0:
                        try:
                            progress_ms = int(float(pos_res.stdout.strip()) * 1000)
                        except: pass
                        
                    len_res = subprocess.run(["playerctl", "-p", "spotify", "metadata", "mpris:length"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
                    if len_res.returncode == 0:
                        try:
                            duration_ms = int(int(len_res.stdout.strip()) / 1000)
                        except: pass
                        
                    m_state = {
                        "available": True,
                        "is_playing": is_playing,
                        "title": title,
                        "artist": artist,
                        "album_art": art_url,
                        "progress_ms": progress_ms,
                        "duration_ms": duration_ms,
                        "device_name": "Spotify en PC (Local)"
                    }
                    self._state_cache = m_state
                    self._state_cache_time = time.time()
                    return m_state

            # Fallback a gdbus si no hay playerctl
            cmd = ["gdbus", "call", "--session", "--dest", "org.mpris.MediaPlayer2.spotify",
                   "--object-path", "/org/mpris/MediaPlayer2",
                   "--method", "org.freedesktop.DBus.Properties.Get",
                   "org.mpris.MediaPlayer2.Player", "PlaybackStatus"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
            if "PlaybackStatus" in res.stdout or "Playing" in res.stdout or "Paused" in res.stdout:
                is_playing = "Playing" in res.stdout

                cmd_meta = ["gdbus", "call", "--session", "--dest", "org.mpris.MediaPlayer2.spotify",
                            "--object-path", "/org/mpris/MediaPlayer2",
                            "--method", "org.freedesktop.DBus.Properties.Get",
                            "org.mpris.MediaPlayer2.Player", "Metadata"]
                res_meta = subprocess.run(cmd_meta, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
                
                title = "Spotify Desktop"
                artist = "Unknown Artist"
                art_url = ""
                for line in res_meta.stdout.splitlines():
                    if "xesam:title" in line:
                        parts = line.split("<'")
                        title = parts[-1].split("'>")[0] if len(parts) > 1 else (line.split("<\"")[-1].split("\">")[0] if "<\"" in line else "Spotify Track")
                    elif "xesam:artist" in line:
                        parts = line.split("['")
                        artist = parts[-1].split("']")[0] if len(parts) > 1 else "Unknown Artist"
                    elif "mpris:artUrl" in line:
                        parts = line.split("<'")
                        art_url = parts[-1].split("'>")[0] if len(parts) > 1 else ""

                if title.startswith("http"):
                    title = "Reproduciendo (Sin título MPRIS)"

                m_state = {
                    "available": True,
                    "is_playing": is_playing,
                    "title": title,
                    "artist": artist,
                    "album_art": art_url,
                    "device_name": "Spotify en esta PC (Ubuntu MPRIS)"
                }
                self._state_cache = m_state
                self._state_cache_time = time.time()
                return m_state
        except Exception:
            pass
        return {"available": False, "error": "AppArmor bloqueó la conexión (Instala playerctl) o Spotify está cerrado"}
