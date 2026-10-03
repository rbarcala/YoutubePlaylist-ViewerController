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
        res = self._api_request("me/player")
        if "error" in res or not res:
            # Intentar leer desde MPRIS en Ubuntu
            mpris_state = self._get_mpris_state()
            if mpris_state.get("available"):
                return mpris_state

        if res and "item" in res and res["item"]:
            item = res["item"]
            artists = ", ".join([a["name"] for a in item.get("artists", [])])
            album_art = ""
            if item.get("album", {}).get("images"):
                album_art = item["album"]["images"][0]["url"]

            return {
                "available": True,
                "is_playing": res.get("is_playing", False),
                "title": item.get("name", "Desconocido"),
                "artist": artists,
                "album": item.get("album", {}).get("name", ""),
                "album_art": album_art,
                "progress_ms": res.get("progress_ms", 0),
                "duration_ms": item.get("duration_ms", 0),
                "volume_percent": res.get("device", {}).get("volume_percent", 50),
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

    def set_volume(self, volume_percent: int) -> dict:
        vol = max(0, min(100, int(volume_percent)))
        return self._api_request(f"me/player/volume?volume_percent={vol}", method="PUT")

    def add_to_queue(self, uri: str) -> dict:
        encoded = urllib.parse.quote(uri)
        return self._api_request(f"me/player/queue?uri={encoded}", method="POST")

    def search(self, query: str) -> dict:
        if not query:
            return {"tracks": []}
        encoded = urllib.parse.quote(query)
        res = self._api_request(f"search?q={encoded}&type=track")
        if "tracks" in res:
            items = []
            for t in res["tracks"].get("items", []):
                items.append({
                    "id": t.get("id"),
                    "uri": t.get("uri"),
                    "title": t.get("name"),
                    "artist": ", ".join([a.get("name", "") for a in t.get("artists", [])]),
                    "album": t.get("album", {}).get("name", ""),
                    "thumb": t.get("album", {}).get("images", [{}])[-1].get("url", "") if t.get("album", {}).get("images") else "",
                    "duration_ms": t.get("duration_ms", 0)
                })
            return {"tracks": items}
        return {"tracks": [], "error": res.get("error")}

    def get_playlist(self, playlist_id: str) -> dict:
        """Obtiene todas las canciones de una playlist de Spotify, paginando automáticamente."""
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
                thumb = album["images"][-1].get("url", "")

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

        return {"name": name, "tracks": items, "total": len(items)}

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
        try:
            cmd = ["gdbus", "call", "--session", "--dest", "org.mpris.MediaPlayer2.spotify",
                   "--object-path", "/org/mpris/MediaPlayer2",
                   "--method", "org.freedesktop.DBus.Properties.Get",
                   "org.mpris.MediaPlayer2.Player", "PlaybackStatus"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
            if "PlaybackStatus" in res.stdout or "Playing" in res.stdout or "Paused" in res.stdout:
                is_playing = "Playing" in res.stdout

                # Obtener metadatos
                cmd_meta = ["gdbus", "call", "--session", "--dest", "org.mpris.MediaPlayer2.spotify",
                            "--object-path", "/org/mpris/MediaPlayer2",
                            "--method", "org.freedesktop.DBus.Properties.Get",
                            "org.mpris.MediaPlayer2.Player", "Metadata"]
                res_meta = subprocess.run(cmd_meta, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
                
                # Extracción rápida de campos comunes
                title = "Spotify Desktop"
                artist = ""
                art_url = ""
                for line in res_meta.stdout.splitlines():
                    if "xesam:title" in line:
                        title = line.split("<'")[-1].split("'>")[0] if "<'" in line else title
                    elif "xesam:artist" in line:
                        artist = line.split("['")[-1].split("']")[0] if "['" in line else artist
                    elif "mpris:artUrl" in line:
                        art_url = line.split("<'")[-1].split("'>")[0] if "<'" in line else ""

                return {
                    "available": True,
                    "is_playing": is_playing,
                    "title": title,
                    "artist": artist,
                    "album_art": art_url,
                    "device_name": "Spotify en esta PC (Ubuntu MPRIS)"
                }
        except Exception:
            pass
        return {"available": False}
