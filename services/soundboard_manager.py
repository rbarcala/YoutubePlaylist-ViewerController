"""
Módulo de Gestión de Botonera (Soundboard) integrado 100% en vivo con MyInstants.
Sin listas fijas ni URLs predefinidas: busca y extrae en tiempo real los sonidos
directamente desde MyInstants para cada país o región (Argentina, LATAM, USA, Global)
con soporte completo para paginación y scroll infinito (más y más sonidos al deslizar).
"""

import os
import re
import sys
import time
import json
import shutil
import urllib.request
import urllib.parse
import subprocess
import threading
from pathlib import Path

VIBRANT_PALETTE = [
    "#FF0055", "#007AFF", "#34C759", "#FF9500", "#AF52DE",
    "#FFCC00", "#5856D6", "#FF2D55", "#00C7BE", "#32ADE6"
]

# Códigos de países y regiones soportados en MyInstants
REGION_URL_TEMPLATES = {
    "ar": "https://www.myinstants.com/en/index/ar/?page={page}",
    "arg": "https://www.myinstants.com/en/index/ar/?page={page}",
    "latam": "https://www.myinstants.com/en/index/mx/?page={page}",
    "mx": "https://www.myinstants.com/en/index/mx/?page={page}",
    "cl": "https://www.myinstants.com/en/index/cl/?page={page}",
    "co": "https://www.myinstants.com/en/index/co/?page={page}",
    "pe": "https://www.myinstants.com/en/index/pe/?page={page}",
    "es": "https://www.myinstants.com/en/index/es/?page={page}",
    "us": "https://www.myinstants.com/en/index/us/?page={page}",
    "usa": "https://www.myinstants.com/en/index/us/?page={page}",
    "global": "https://www.myinstants.com/en/best_of_all_time/?page={page}",
    "trending": "https://www.myinstants.com/en/trending/?page={page}"
}

class SoundboardManager:
    def __init__(self, config_loader, config_saver, on_idle=None):
        self.load_config = config_loader
        self.save_config = config_saver
        self.on_idle = on_idle
        self.active_processes = []
        self.lock = threading.Lock()
        cfg = self.load_config()
        self.current_volume = cfg.get("soundboard_volume", 80) if cfg else 80
        self.has_wpctl = shutil.which("wpctl") is not None

        # Directorio de caché local para reproducción instantánea con 0 latencia
        self.cache_dir = Path.home() / ".cache" / "youtube-stream-controller" / "sounds"
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.cache_dir = Path(__file__).resolve().parent / "cache" / "sounds"
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
        }

    # ─── GESTIÓN DINÁMICA DE VOLUMEN EN TIEMPO REAL (PIPEWIRE) ───

    def _apply_volume_to_node(self, node_id, vol: int):
        """Aplica instantáneamente el volumen o mute a un nodo de PipeWire."""
        if not node_id or not self.has_wpctl:
            return
        try:
            nid = str(node_id)
            if vol <= 0:
                subprocess.run(["wpctl", "set-mute", nid, "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["wpctl", "set-volume", nid, "0%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(["wpctl", "set-mute", nid, "0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["wpctl", "set-volume", nid, f"{vol}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _find_node_for_pid(self, pid: int):
        """Busca el ID de nodo de PipeWire asociado al proceso especificado."""
        try:
            res = subprocess.check_output(["pw-dump"], timeout=0.6)
            data = json.loads(res.decode("utf-8", errors="ignore"))
            for item in data:
                if item.get("type") == "PipeWire:Interface:Node":
                    props = item.get("info", {}).get("props", {})
                    if props.get("application.process.id") == pid:
                        return item.get("id")
        except Exception:
            pass
        return None

    def _track_process_volume(self, item: dict, target_vol: int):
        """Espera a que el stream aparezca en PipeWire y le aplica el volumen actual."""
        pid = item.get("pid")
        for _ in range(30):
            proc = item.get("proc")
            if proc and proc.poll() is not None:
                return
            nid = self._find_node_for_pid(pid)
            if nid:
                item["node_id"] = nid
                vol_to_apply = self.current_volume if self.current_volume is not None else target_vol
                self._apply_volume_to_node(nid, vol_to_apply)
                break
            time.sleep(0.015)

    def _watch_process_completion(self, item: dict):
        """Monitorea el proceso de audio y notifica cuando todos los audios terminaron."""
        proc = item.get("proc")
        if proc:
            try:
                proc.wait()
            except Exception:
                pass
        with self.lock:
            self.active_processes = [p for p in self.active_processes if p["proc"].poll() is None]
            still_running = len(self.active_processes) > 0
        if not still_running and self.on_idle:
            try:
                self.on_idle()
            except Exception:
                pass

    # ─── REPRODUCCIÓN DE AUDIO EN LA PC ───

    def play(self, mp3_url: str, title: str = "", volume: int = None) -> dict:
        """
        Descarga (si no está en caché) y reproduce el sonido localmente
        a través de ffplay directamente en el servidor Linux con control de volumen en vivo.
        """
        if not mp3_url:
            return {"success": False, "error": "No se proporcionó URL de MP3"}

        target_file = self._resolve_local_audio(mp3_url)

        # Preparar entorno para asegurar salida de audio PipeWire / PulseAudio
        env = os.environ.copy()
        uid = os.getuid()
        runtime_dir = f"/run/user/{uid}"
        if os.path.exists(runtime_dir):
            env["XDG_RUNTIME_DIR"] = runtime_dir

        if volume is not None:
            try:
                vol = max(0, min(100, int(volume)))
            except (ValueError, TypeError):
                vol = self.current_volume
        else:
            vol = self.current_volume

        self.current_volume = vol
        vol_ratio = f"{vol / 100.0:.2f}"

        cmd = [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-loglevel", "error",
            "-volume", str(vol),
            "-af", f"volume={vol_ratio}",
            str(target_file)
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True
            )
            item = {"proc": proc, "pid": proc.pid, "node_id": None}
            with self.lock:
                self.active_processes = [p for p in self.active_processes if p["proc"].poll() is None]
                self.active_processes.append(item)

            if self.has_wpctl:
                threading.Thread(target=self._track_process_volume, args=(item, vol), daemon=True).start()

            threading.Thread(target=self._watch_process_completion, args=(item,), daemon=True).start()

            return {
                "success": True,
                "playing": title or Path(target_file).stem,
                "volume": vol
            }
        except FileNotFoundError:
            return {"success": False, "error": "ffplay no está disponible en el sistema"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def stop_all(self) -> dict:
        """Detiene de inmediato todos los sonidos en reproducción en la PC."""
        with self.lock:
            for item in self.active_processes:
                try:
                    p = item.get("proc")
                    if p and p.poll() is None:
                        p.terminate()
                except Exception:
                    pass
            self.active_processes.clear()

        try:
            subprocess.run(["pkill", "-f", "ffplay.*sounds"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-f", "ffplay"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        return {"success": True, "message": "Todos los sonidos han sido detenidos"}

    def _resolve_local_audio(self, mp3_url: str) -> str:
        """Devuelve la ruta al archivo MP3 local, descargando a caché si es necesario."""
        if os.path.exists(mp3_url):
            return mp3_url

        # Generar nombre de archivo único y seguro
        clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', mp3_url.split('/')[-1])
        if not clean_name.endswith('.mp3'):
            clean_name += '.mp3'

        local_path = self.cache_dir / clean_name
        if local_path.exists() and local_path.stat().st_size > 1024:
            return str(local_path)

        try:
            req = urllib.request.Request(mp3_url, headers=self._headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
                with open(local_path, "wb") as f:
                    f.write(data)
            return str(local_path)
        except Exception as e:
            print(f"[soundboard] Advertencia descargando a caché: {e}. Pasando URL directa.")
            return mp3_url

    # ─── PARSING DE MYINSTANTS ───

    def _parse_instants_html(self, html: str) -> list[dict]:
        """Extrae botones de sonido 100% reales desde el HTML de MyInstants."""
        sounds = []
        blocks = html.split('<div class="instant">')[1:]
        color_idx = 0

        for block in blocks:
            try:
                mp3_m = re.search(r"onclick=\"play\(\'([^\']+)\'", block)
                if not mp3_m:
                    continue
                mp3_path = mp3_m.group(1)
                mp3_url = mp3_path if mp3_path.startswith("http") else f"https://www.myinstants.com{mp3_path}"

                title_m = re.search(r'class=\"instant-link[^\"]*\">([^<]+)</a>', block)
                title = title_m.group(1).strip() if title_m else Path(mp3_path).stem

                color_m = re.search(r'background-color:\s*([^;\"]+)', block)
                if color_m:
                    color = color_m.group(1).strip()
                else:
                    color = VIBRANT_PALETTE[color_idx % len(VIBRANT_PALETTE)]
                    color_idx += 1

                slug_m = re.search(r'/instant/([^/]+)/', block)
                sound_id = slug_m.group(1) if slug_m else Path(mp3_path).stem

                loader_m = re.search(r'id=[\"\']loader-(\d+)[\"\']', block)
                fav_m = re.search(r'favorite\([\'\"]?(\d+)[\'\"]?\)', block)
                instant_numeric_id = fav_m.group(1) if fav_m else (loader_m.group(1) if loader_m else None)

                sounds.append({
                    "id": sound_id,
                    "instant_id": instant_numeric_id,
                    "title": title,
                    "mp3": mp3_url,
                    "color": color,
                    "source": "myinstants"
                })
            except Exception:
                continue

        return sounds

    # ─── BÚSQUEDA Y RANKINGS EN VIVO CON PAGINACIÓN ───

    def get_regional(self, region: str = "ar", page: int = 1) -> dict:
        cache_key = f"{region}_{page}"
        if not hasattr(self, "_cache"):
            self._cache = {}
            self._cache_time = {}
        import time
        if cache_key in self._cache and time.time() - self._cache_time.get(cache_key, 0) < 3600:
            return self._cache[cache_key]
        """
        Obtiene los sonidos en vivo directamente desde MyInstants para el país o región.
        Soporta paginación: page 1, 2, 3, etc. (36 sonidos por página).
        """
        reg = (region or "ar").lower().strip()
        template = REGION_URL_TEMPLATES.get(reg, REGION_URL_TEMPLATES["ar"])
        target_url = template.format(page=max(1, int(page)))

        try:
            req = urllib.request.Request(target_url, headers=self._headers)
            with urllib.request.urlopen(req, timeout=6) as res:
                html = res.read().decode('utf-8', errors='ignore')
                sounds = self._parse_instants_html(html)
                result = {
                    "sounds": sounds,
                    "page": int(page),
                    "has_more": len(sounds) >= 20,
                    "region": reg
                }
                self._cache[cache_key] = result
                self._cache_time[cache_key] = time.time()
                return result
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"sounds": [], "page": int(page), "has_more": False, "region": reg}
            print(f"[soundboard] HTTPError cargando región '{reg}' pág {page}: {e}")
        except Exception as e:
            print(f"[soundboard] Error cargando región '{reg}' pág {page}: {e}")

        return {"sounds": [], "page": int(page), "has_more": False, "region": reg}

    def search(self, query: str, page: int = 1) -> dict:
        """
        Busca sonidos en vivo en MyInstants con la consulta del usuario y paginación.
        Con memoria caché en RAM para respuesta instantánea a 0 ms.
        """
        query = query.strip()
        if not query:
            return self.get_regional("ar", page)

        p = max(1, int(page))
        cache_key = f"search_{query.lower()}_{p}"
        if not hasattr(self, "_cache"):
            self._cache = {}
            self._cache_time = {}
        import time
        if cache_key in self._cache and time.time() - self._cache_time.get(cache_key, 0) < 3600:
            return self._cache[cache_key]

        p = max(1, int(page))
        url = f"https://www.myinstants.com/en/search/?name={urllib.parse.quote(query)}&page={p}"
        try:
            req = urllib.request.Request(url, headers=self._headers)
            with urllib.request.urlopen(req, timeout=6) as res:
                html = res.read().decode('utf-8', errors='ignore')
                sounds = self._parse_instants_html(html)
                result = {
                    "sounds": sounds,
                    "page": p,
                    "has_more": len(sounds) >= 20,
                    "query": query
                }
                self._cache[cache_key] = result
                self._cache_time[cache_key] = time.time()
                return result
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # MyInstants devuelve 404 cuando una búsqueda no tiene resultados o se llegó al final
                return {"sounds": [], "page": p, "has_more": False, "query": query}
            print(f"[soundboard] HTTPError buscando '{query}' pág {p}: {e}")
        except Exception as e:
            print(f"[soundboard] Error buscando '{query}' pág {p}: {e}")

        return {"sounds": [], "page": p, "has_more": False, "query": query}

    # ─── CUENTA DE USUARIO Y FAVORITOS ───

    def get_user_favorites(self, username_or_url: str) -> list[dict]:
        """Obtiene favoritos públicos de un perfil de MyInstants."""
        user = username_or_url.strip()
        if not user:
            return []

        if "myinstants.com" in user:
            match = re.search(r'/profile/([^/]+)/?', user)
            if match:
                user = match.group(1)
            else:
                user = user.rstrip('/').split('/')[-1]

        url = f"https://www.myinstants.com/en/profile/{urllib.parse.quote(user)}/"
        try:
            req = urllib.request.Request(url, headers=self._headers)
            with urllib.request.urlopen(req, timeout=6) as res:
                html = res.read().decode('utf-8', errors='ignore')
                return self._parse_instants_html(html)
        except Exception as e:
            print(f"[soundboard] Error cargando favoritos de '{user}': {e}")
            return []

    def get_auth_status(self) -> dict:
        """Devuelve el estado de autenticación y vinculación con MyInstants."""
        cfg = self.load_config()
        username = cfg.get("soundboard_username", "").strip()
        session = cfg.get("soundboard_session_cookie", "").strip()
        return {
            "logged_in": bool(username or session),
            "username": username,
            "has_session": bool(session),
            "favorites_count": len(cfg.get("soundboard_favorites", []))
        }

    def save_auth(self, username: str, session_cookie: str = "", csrf_token: str = "") -> dict:
        """Guarda las credenciales de MyInstants y sincroniza los favoritos existentes."""
        clean_user = (username or "").strip()
        if "myinstants.com" in clean_user:
            m = re.search(r'/profile/([^/]+)/?', clean_user)
            if m:
                clean_user = m.group(1)
            else:
                clean_user = clean_user.rstrip('/').split('/')[-1]

        update = {
            "soundboard_username": clean_user,
            "soundboard_session_cookie": (session_cookie or "").strip(),
        }
        if csrf_token:
            update["soundboard_csrf_token"] = csrf_token.strip()

        self.save_config(update)

        sync_result = {}
        if clean_user:
            try:
                sync_result = self.sync_account(clean_user)
            except Exception as e:
                sync_result = {"success": False, "error": str(e)}

        return {
            "success": True,
            "username": clean_user,
            "has_session": bool(update["soundboard_session_cookie"]),
            "sync": sync_result
        }

    def get_saved_favorites(self) -> list[dict]:
        """Devuelve la lista persistida de favoritos en config.json."""
        cfg = self.load_config()
        return cfg.get("soundboard_favorites", [])

    def add_favorite(self, sound: dict) -> dict:
        """
        Agrega un sonido a la lista de favoritos local y lo guarda en MyInstants en la nube
        si el usuario tiene sesión vinculada.
        """
        cfg = self.load_config()
        favs = cfg.get("soundboard_favorites", [])
        sound_id = sound.get("id") or sound.get("title")

        # Verificar si ya está en favoritos
        existing = next((f for f in favs if f.get("id") == sound_id or f.get("mp3") == sound.get("mp3")), None)
        if not existing:
            favs.insert(0, sound)
            self.save_config({"soundboard_favorites": favs})

        cloud_synced = False
        session_cookie = cfg.get("soundboard_session_cookie", "").strip()
        csrf_token = cfg.get("soundboard_csrf_token", "").strip()

        instant_id = sound.get("instant_id")
        if not instant_id and sound_id and str(sound_id).isdigit():
            instant_id = str(sound_id)

        if session_cookie:
            if not instant_id and sound.get("id"):
                instant_id = self._resolve_numeric_id(sound.get("id"))
            if instant_id:
                threading.Thread(
                    target=self._add_favorite_cloud,
                    args=(instant_id, session_cookie, csrf_token),
                    daemon=True
                ).start()
                cloud_synced = True

        return {
            "favorites": favs,
            "cloud_synced": cloud_synced,
            "has_session": bool(session_cookie)
        }

    def _add_favorite_cloud(self, instant_id: str, sessionid: str, csrftoken: str = ""):
        """Llama al endpoint oficial de MyInstants para guardar el favorito en la cuenta del usuario."""
        if not instant_id or not sessionid:
            return False
        url = f"https://www.myinstants.com/api/v1/favorite/add/{instant_id}/"
        cookie_header = f"sessionid={sessionid}"
        if csrftoken:
            cookie_header += f"; csrftoken={csrftoken}"
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.myinstants.com/",
            "Cookie": cookie_header
        }
        if csrftoken:
            headers["X-CSRFToken"] = csrftoken
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                print(f"[soundboard] Sonido {instant_id} guardado con éxito en MyInstants en la nube (Status: {resp.status})")
                return True
        except urllib.error.HTTPError as e:
            print(f"[soundboard] Error HTTP al guardar favorito {instant_id} en MyInstants: {e.code}")
            return False
        except Exception as e:
            print(f"[soundboard] Error conectando a MyInstants nube para favorito {instant_id}: {e}")
            return False

    def _resolve_numeric_id(self, identifier: str) -> str | None:
        """Intenta obtener el ID numérico a partir del slug o título."""
        if not identifier:
            return None
        if str(identifier).isdigit():
            return str(identifier)
        try:
            res = self.search(str(identifier), page=1)
            for s in res.get("sounds", []):
                if s.get("id") == identifier or identifier in s.get("mp3", ""):
                    if s.get("instant_id"):
                        return str(s.get("instant_id"))
            if res.get("sounds") and res["sounds"][0].get("instant_id"):
                return str(res["sounds"][0]["instant_id"])
        except Exception:
            pass
        return None

    def remove_favorite(self, sound_id_or_title: str) -> list[dict]:
        """Elimina un sonido de los favoritos locales."""
        cfg = self.load_config()
        favs = cfg.get("soundboard_favorites", [])
        favs = [f for f in favs if f.get("id") != sound_id_or_title and f.get("title") != sound_id_or_title and f.get("mp3") != sound_id_or_title]
        self.save_config({"soundboard_favorites": favs})
        return favs

    def sync_account(self, username_or_url: str) -> dict:
        """Sincroniza los favoritos de la cuenta en la lista local."""
        if not username_or_url:
            return {"success": False, "error": "Nombre de usuario o URL requerida"}

        user_favs = self.get_user_favorites(username_or_url)
        if not user_favs:
            return {
                "success": False,
                "error": "No se encontraron favoritos o el perfil no es público."
            }

        clean_user = username_or_url.strip()
        if "myinstants.com" in clean_user:
            m = re.search(r'/profile/([^/]+)/?', clean_user)
            if m: clean_user = m.group(1)

        cfg = self.load_config()
        existing_favs = cfg.get("soundboard_favorites", [])
        existing_ids = {f.get("id") for f in existing_favs if f.get("id")}
        existing_mp3s = {f.get("mp3") for f in existing_favs if f.get("mp3")}

        added_count = 0
        for f in user_favs:
            if f.get("id") not in existing_ids and f.get("mp3") not in existing_mp3s:
                existing_favs.append(f)
                added_count += 1

        self.save_config({
            "soundboard_username": clean_user,
            "soundboard_favorites": existing_favs
        })

        return {
            "success": True,
            "username": clean_user,
            "total_synced": len(user_favs),
            "new_added": added_count,
            "favorites": existing_favs
        }

    def set_volume(self, volume: int) -> dict:
        """Actualiza, persiste y aplica en tiempo real el volumen a todos los audios en reproducción."""
        try:
            vol = max(0, min(100, int(volume)))
        except (ValueError, TypeError):
            vol = 80

        self.current_volume = vol
        self.save_config({"soundboard_volume": vol})

        if not self.has_wpctl:
            return {"success": True, "volume": vol}

        with self.lock:
            self.active_processes = [p for p in self.active_processes if p["proc"].poll() is None]
            current_items = list(self.active_processes)

        missing_items = []
        for item in current_items:
            nid = item.get("node_id")
            if nid:
                self._apply_volume_to_node(nid, vol)
            else:
                missing_items.append(item)

        # Si hay procesos cuyo ID aún no teníamos en caché, o para asegurar cualquier ffplay
        if missing_items or current_items:
            try:
                res = subprocess.check_output(["pw-dump"], timeout=0.6)
                data = json.loads(res.decode("utf-8", errors="ignore"))
                for dump_item in data:
                    if dump_item.get("type") == "PipeWire:Interface:Node":
                        props = dump_item.get("info", {}).get("props", {})
                        pid = props.get("application.process.id")
                        app_name = props.get("application.name")
                        nid = dump_item.get("id")
                        if not nid:
                            continue
                        for m in missing_items:
                            if pid == m.get("pid"):
                                m["node_id"] = nid
                                self._apply_volume_to_node(nid, vol)
                        if app_name == "ffplay":
                            self._apply_volume_to_node(nid, vol)
            except Exception:
                pass

        return {"success": True, "volume": vol}
