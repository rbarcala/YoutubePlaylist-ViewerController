"""
Módulo de Gestión de Botonera (Soundboard) integrado con MyInstants.
Permite buscar sonidos, explorar los rankings regionales (Argentina, LATAM, USA, Global),
sincronizar favoritos de cuenta MyInstants (o inicio con Google), guardar favoritos locales
y reproducir el audio directamente en la computadora anfitriona (Linux PipeWire/ALSA).
"""

import os
import re
import sys
import time
import urllib.request
import urllib.parse
import subprocess
import threading
from pathlib import Path

# ─── TOP CURADO POR REGIONES (DISPONIBLES ONLINE Y OFFLINE) ───

TOP_ARG_SOUNDS = [
    {
        "id": "sapeee",
        "title": "¡SAPEEEE! - El Bananero",
        "mp3": "https://www.myinstants.com/media/sounds/sapeee.mp3",
        "color": "#0099FF",
        "region": "arg"
    },
    {
        "id": "ricardo-fort-miameee",
        "title": "Ricardo Fort - ¡MIAMEEE!",
        "mp3": "https://www.myinstants.com/media/sounds/ricardo-fort-miameee.mp3",
        "color": "#FFD700",
        "region": "arg"
    },
    {
        "id": "ricardo-fort-mamaaaa",
        "title": "Ricardo Fort - Mamá cortaste toda la loz",
        "mp3": "https://www.myinstants.com/media/sounds/ricardo-fort-mamaaaa.mp3",
        "color": "#FF9500",
        "region": "arg"
    },
    {
        "id": "hermosa-manana-verdad",
        "title": "Francella - Hermosa mañana, ¿verdad?",
        "mp3": "https://www.myinstants.com/media/sounds/hermosa-manana-verdad.mp3",
        "color": "#34C759",
        "region": "arg"
    },
    {
        "id": "arrepentirse-samid",
        "title": "Samid - Usted se tiene que arrepentir",
        "mp3": "https://www.myinstants.com/media/sounds/arrepentirse-samid.mp3",
        "color": "#FF2D55",
        "region": "arg"
    },
    {
        "id": "a-comerla",
        "title": "Francella - ¡A comerla!",
        "mp3": "https://www.myinstants.com/media/sounds/a-comerla.mp3",
        "color": "#AF52DE",
        "region": "arg"
    },
    {
        "id": "maradona-eeee",
        "title": "Diego Maradona - Eeeeeeeee",
        "mp3": "https://www.myinstants.com/media/sounds/maradona-eeee.mp3",
        "color": "#75AADB",
        "region": "arg"
    },
    {
        "id": "muchachos-arg",
        "title": "Muchachos - ¡Ahora nos volvimo a ilusionar!",
        "mp3": "https://www.myinstants.com/media/sounds/muchachos-ahora-nos-volvimo-a-ilusionar.mp3",
        "color": "#007AFF",
        "region": "arg"
    },
    {
        "id": "nashe_2",
        "title": "Coscu - ¡NASHEEE!",
        "mp3": "https://www.myinstants.com/media/sounds/nashe_2.mp3",
        "color": "#FF3B30",
        "region": "arg"
    },
    {
        "id": "boee",
        "title": "Boee",
        "mp3": "https://www.myinstants.com/media/sounds/boee.mp3",
        "color": "#30B0C7",
        "region": "arg"
    },
    {
        "id": "buenas-tardes-grupo",
        "title": "Buenas tardes grupo",
        "mp3": "https://www.myinstants.com/media/sounds/buenas-tardes-grupo.mp3",
        "color": "#A3FFB8",
        "region": "arg"
    },
    {
        "id": "alarma-de-auron-play",
        "title": "Alarma Auronplay",
        "mp3": "https://www.myinstants.com/media/sounds/alarma-de-auron-play.mp3",
        "color": "#2EFF85",
        "region": "arg"
    }
]

TOP_LATAM_SOUNDS = [
    {
        "id": "gato-riendo",
        "title": "Gato Riendo",
        "mp3": "https://www.myinstants.com/media/sounds/gato-riendo_6bOc2ur.mp3",
        "color": "#FF9500",
        "region": "latam"
    },
    {
        "id": "eso-tilin_2",
        "title": "¡Eso Tilín! ¡Vaya Tilín!",
        "mp3": "https://www.myinstants.com/media/sounds/eso-tilin_2.mp3",
        "color": "#FF2D55",
        "region": "latam"
    },
    {
        "id": "ay-miguel-miguel",
        "title": "¡Ay Miguel, Miguel!",
        "mp3": "https://www.myinstants.com/media/sounds/ay-miguel-miguel.mp3",
        "color": "#AF52DE",
        "region": "latam"
    },
    {
        "id": "el-pepe",
        "title": "El Pepe",
        "mp3": "https://www.myinstants.com/media/sounds/el-pepe_yCsqW8h.mp3",
        "color": "#007AFF",
        "region": "latam"
    },
    {
        "id": "potasio",
        "title": "Con arroz blanco... Potaxio",
        "mp3": "https://www.myinstants.com/media/sounds/potasio.mp3",
        "color": "#FFCC00",
        "region": "latam"
    },
    {
        "id": "se-va-a-caer",
        "title": "¡Se va a caer, se cayó!",
        "mp3": "https://www.myinstants.com/media/sounds/se-va-a-caer.mp3",
        "color": "#FF3B30",
        "region": "latam"
    },
    {
        "id": "1500-es-hora-y-media",
        "title": "1500 es hora y media",
        "mp3": "https://www.myinstants.com/media/sounds/1500-es-hora-y-media.mp3",
        "color": "#34C759",
        "region": "latam"
    },
    {
        "id": "duermete-alv-ya",
        "title": "Duérmete alv ya",
        "mp3": "https://www.myinstants.com/media/sounds/duermete-alv-ya.mp3",
        "color": "#5856D6",
        "region": "latam"
    },
    {
        "id": "pi-pi-pi-el-chavo-del-8",
        "title": "El Chavo del 8 (Pipipi)",
        "mp3": "https://www.myinstants.com/media/sounds/pi-pi-pi-el-chavo-del-8.mp3",
        "color": "#FF9500",
        "region": "latam"
    },
    {
        "id": "oh-no-no-no-laugh",
        "title": "Risa Oh No No No",
        "mp3": "https://www.myinstants.com/media/sounds/oh-no-no-no-laugh.mp3",
        "color": "#FFD700",
        "region": "latam"
    }
]

TOP_USA_SOUNDS = [
    {
        "id": "vine-boom",
        "title": "Vine Boom Sound",
        "mp3": "https://www.myinstants.com/media/sounds/vine-boom.mp3",
        "color": "#FF3B30",
        "region": "usa"
    },
    {
        "id": "rizz-sound-effect",
        "title": "Rizz Sound Effect",
        "mp3": "https://www.myinstants.com/media/sounds/rizz-sound-effect.mp3",
        "color": "#AF52DE",
        "region": "usa"
    },
    {
        "id": "emotional-damage-meme",
        "title": "Emotional Damage",
        "mp3": "https://www.myinstants.com/media/sounds/emotional-damage-meme.mp3",
        "color": "#FF2D55",
        "region": "usa"
    },
    {
        "id": "movie_1",
        "title": "Bruh",
        "mp3": "https://www.myinstants.com/media/sounds/movie_1.mp3",
        "color": "#FF9500",
        "region": "usa"
    },
    {
        "id": "fbi-open-up-sfx",
        "title": "FBI Open Up!",
        "mp3": "https://www.myinstants.com/media/sounds/fbi-open-up-sfx.mp3",
        "color": "#007AFF",
        "region": "usa"
    },
    {
        "id": "what-the-dog-doin",
        "title": "What the Dog Doin",
        "mp3": "https://www.myinstants.com/media/sounds/what-the-dog-doin.mp3",
        "color": "#FFCC00",
        "region": "usa"
    },
    {
        "id": "mlg-airhorn",
        "title": "MLG Airhorn",
        "mp3": "https://www.myinstants.com/media/sounds/mlg-airhorn.mp3",
        "color": "#FF3B30",
        "region": "usa"
    },
    {
        "id": "roblox-death-sound_1",
        "title": "Roblox OOF",
        "mp3": "https://www.myinstants.com/media/sounds/roblox-death-sound_1.mp3",
        "color": "#34C759",
        "region": "usa"
    },
    {
        "id": "no-god-please-no-noooooooooo",
        "title": "No God Please No!",
        "mp3": "https://www.myinstants.com/media/sounds/no-god-please-no-noooooooooo.mp3",
        "color": "#FF2D55",
        "region": "usa"
    },
    {
        "id": "can-you-feel-my-heart",
        "title": "GigaChad Theme",
        "mp3": "https://www.myinstants.com/media/sounds/can-you-feel-my-heart.mp3",
        "color": "#5856D6",
        "region": "usa"
    }
]

TOP_GLOBAL_SOUNDS = [
    {
        "id": "discord-notification",
        "title": "Discord Notification",
        "mp3": "https://www.myinstants.com/media/sounds/discord-notification.mp3",
        "color": "#5865F2",
        "region": "global"
    },
    {
        "id": "ba-dum-tss",
        "title": "Ba Dum Tss",
        "mp3": "https://www.myinstants.com/media/sounds/ba-dum-tss.mp3",
        "color": "#FFCC00",
        "region": "global"
    },
    {
        "id": "sad-violin",
        "title": "Sad Violin",
        "mp3": "https://www.myinstants.com/media/sounds/sad-violin.mp3",
        "color": "#5856D6",
        "region": "global"
    },
    {
        "id": "aplausos_2",
        "title": "Aplausos / Cheer",
        "mp3": "https://www.myinstants.com/media/sounds/aplausos_2.mp3",
        "color": "#34C759",
        "region": "global"
    },
    {
        "id": "sad-trombone",
        "title": "Sad Trombone (Wah Wah)",
        "mp3": "https://www.myinstants.com/media/sounds/sad-trombone.mp3",
        "color": "#FF9500",
        "region": "global"
    },
    {
        "id": "ding-sound-effect_2",
        "title": "Ding Campana",
        "mp3": "https://www.myinstants.com/media/sounds/ding-sound-effect_2.mp3",
        "color": "#34C759",
        "region": "global"
    },
    {
        "id": "anime-wow-sound-effect",
        "title": "Anime WOW!",
        "mp3": "https://www.myinstants.com/media/sounds/anime-wow-sound-effect.mp3",
        "color": "#AF52DE",
        "region": "global"
    },
    {
        "id": "windows-xp-error",
        "title": "Windows XP Error",
        "mp3": "https://www.myinstants.com/media/sounds/windows-xp-error.mp3",
        "color": "#FF2D55",
        "region": "global"
    },
    {
        "id": "x-files-theme-song-copy",
        "title": "Illuminati / X-Files",
        "mp3": "https://www.myinstants.com/media/sounds/x-files-theme-song-copy.mp3",
        "color": "#007AFF",
        "region": "global"
    },
    {
        "id": "cricket",
        "title": "Grillos / Silencio",
        "mp3": "https://www.myinstants.com/media/sounds/cricket.mp3",
        "color": "#30B0C7",
        "region": "global"
    }
]

VIBRANT_PALETTE = [
    "#FF0055", "#007AFF", "#34C759", "#FF9500", "#AF52DE",
    "#FFCC00", "#5856D6", "#FF2D55", "#00C7BE", "#32ADE6"
]

class SoundboardManager:
    def __init__(self, config_loader, config_saver):
        self.load_config = config_loader
        self.save_config = config_saver
        self.active_processes = []
        self.lock = threading.Lock()
        
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

    # ─── REPRODUCCIÓN DE AUDIO EN LA PC ───

    def play(self, mp3_url: str, title: str = "", volume: int = 80) -> dict:
        """
        Descarga (si no está en caché) y reproduce el sonido localmente
        a través de ffplay directamente en el servidor Linux.
        """
        if not mp3_url:
            return {"success": False, "error": "No mp3 URL provided"}

        target_file = self._resolve_local_audio(mp3_url)

        # Preparar entorno para asegurar salida de audio PipeWire / PulseAudio
        env = os.environ.copy()
        uid = os.getuid()
        runtime_dir = f"/run/user/{uid}"
        if os.path.exists(runtime_dir):
            env["XDG_RUNTIME_DIR"] = runtime_dir

        vol = max(0, min(100, int(volume)))

        cmd = [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-loglevel", "error",
            "-volume", str(vol),
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
            with self.lock:
                self.active_processes = [p for p in self.active_processes if p.poll() is None]
                self.active_processes.append(proc)

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
            for p in self.active_processes:
                try:
                    if p.poll() is None:
                        p.terminate()
                except Exception:
                    pass
            self.active_processes.clear()

        try:
            subprocess.run(["pkill", "-f", "ffplay.*sounds"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        return {"success": True, "message": "Todos los sonidos han sido detenidos"}

    def _resolve_local_audio(self, mp3_url: str) -> str:
        """Devuelve la ruta al archivo MP3 local, descargando a caché si es necesario."""
        if os.path.exists(mp3_url):
            return mp3_url

        filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', mp3_url.split('/')[-1])
        if not filename.endswith('.mp3'):
            filename += '.mp3'

        local_path = self.cache_dir / filename
        if local_path.exists() and local_path.stat().st_size > 1024:
            return str(local_path)

        try:
            req = urllib.request.Request(mp3_url, headers=self._headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = resp.read()
                with open(local_path, "wb") as f:
                    f.write(data)
            return str(local_path)
        except Exception as e:
            print(f"[soundboard] Advertencia: No se pudo descargar a caché ({e}), pasando URL directa.")
            return mp3_url

    # ─── PARSING DE MYINSTANTS ───

    def _parse_instants_html(self, html: str) -> list[dict]:
        """Extrae botones de sonido desde el HTML de MyInstants."""
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

                sounds.append({
                    "id": sound_id,
                    "title": title,
                    "mp3": mp3_url,
                    "color": color,
                    "source": "myinstants"
                })
            except Exception:
                continue

        return sounds

    # ─── RANKINGS REGIONALES (ARG, LATAM, USA, GLOBAL) ───

    def get_regional(self, region: str = "arg") -> list[dict]:
        """
        Devuelve el TOP de sonidos para la región especificada:
        - arg: Top Argentina (en vivo de MyInstants /index/ar/ + clásicos meme argentinos)
        - latam: Top Latinoamérica (en vivo /index/mx/ + clásicos meme latam)
        - usa: Top Estados Unidos (/index/us/ + memes virales USA)
        - global: Top Mundial (/best_of_all_time/ + clásicos de stream)
        """
        region_clean = (region or "arg").lower().strip()

        region_urls = {
            "arg": "https://www.myinstants.com/en/index/ar/",
            "latam": "https://www.myinstants.com/en/index/mx/",
            "usa": "https://www.myinstants.com/en/index/us/",
            "global": "https://www.myinstants.com/en/best_of_all_time/"
        }

        fallback_maps = {
            "arg": TOP_ARG_SOUNDS,
            "latam": TOP_LATAM_SOUNDS,
            "usa": TOP_USA_SOUNDS,
            "global": TOP_GLOBAL_SOUNDS
        }

        curated = fallback_maps.get(region_clean, TOP_GLOBAL_SOUNDS)
        target_url = region_urls.get(region_clean, region_urls["global"])

        try:
            req = urllib.request.Request(target_url, headers=self._headers)
            with urllib.request.urlopen(req, timeout=5) as res:
                html = res.read().decode('utf-8', errors='ignore')
                live_sounds = self._parse_instants_html(html)
                if live_sounds:
                    # Mezclar: poner primero los clásicos más icónicos y luego las tendencias en vivo sin duplicados
                    seen_mp3 = {s["mp3"] for s in curated}
                    merged = list(curated)
                    for s in live_sounds:
                        if s["mp3"] not in seen_mp3:
                            merged.append(s)
                            seen_mp3.add(s["mp3"])
                    return merged
        except Exception as e:
            print(f"[soundboard] Advertencia cargando región '{region_clean}': {e}")

        return curated

    def search(self, query: str) -> list[dict]:
        """Busca sonidos en MyInstants con la consulta del usuario."""
        query = query.strip()
        if not query:
            return self.get_regional("arg")

        url = f"https://www.myinstants.com/en/search/?name={urllib.parse.quote(query)}"
        try:
            req = urllib.request.Request(url, headers=self._headers)
            with urllib.request.urlopen(req, timeout=5) as res:
                html = res.read().decode('utf-8', errors='ignore')
                results = self._parse_instants_html(html)
                return results
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            print(f"[soundboard] HTTPError buscando '{query}': {e}")
        except Exception as e:
            print(f"[soundboard] Error buscando '{query}': {e}")

        # Fallback local de búsqueda sobre todos los predefinidos
        q_lower = query.lower()
        all_curated = TOP_ARG_SOUNDS + TOP_LATAM_SOUNDS + TOP_USA_SOUNDS + TOP_GLOBAL_SOUNDS
        return [s for s in all_curated if q_lower in s["title"].lower()]

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
            with urllib.request.urlopen(req, timeout=5) as res:
                html = res.read().decode('utf-8', errors='ignore')
                return self._parse_instants_html(html)
        except Exception as e:
            print(f"[soundboard] Error cargando favoritos de '{user}': {e}")
            return []

    def get_saved_favorites(self) -> list[dict]:
        """Devuelve la lista persistida de favoritos en config.json."""
        cfg = self.load_config()
        favs = cfg.get("soundboard_favorites", [])
        if not favs:
            return TOP_ARG_SOUNDS[:6] + TOP_GLOBAL_SOUNDS[:6]
        return favs

    def add_favorite(self, sound: dict) -> list[dict]:
        """Agrega un sonido a la lista de favoritos persistida."""
        cfg = self.load_config()
        favs = cfg.get("soundboard_favorites", [])
        sound_id = sound.get("id") or sound.get("title")
        if not any(f.get("id") == sound_id or f.get("mp3") == sound.get("mp3") for f in favs):
            favs.insert(0, sound)
            self.save_config({"soundboard_favorites": favs})
        return favs

    def remove_favorite(self, sound_id_or_title: str) -> list[dict]:
        """Elimina un sonido de los favoritos."""
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
