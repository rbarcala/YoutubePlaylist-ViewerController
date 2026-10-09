"""
Módulo de Gestión de Overlays y Temporizador Cómico para OBS Studio y Viewer.
Mantiene el estado sincronizado en tiempo real del Temporizador "Ya Vuelvo"
y los eventos de Now Playing (Spotify / YouTube).
"""

import time
import threading

class OverlayManager:
    def __init__(self, broadcast_fn, config_loader, config_saver):
        self.broadcast = broadcast_fn
        self.load_config = config_loader
        self.save_config = config_saver
        self.lock = threading.RLock()
        
        cfg = self.load_config()
        self.timer_state = {
            "active": False,
            "running": False,
            "total_seconds": 300,
            "duration": 300,
            "remaining_seconds": 300,
            "remaining": 300,
            "start_epoch": 0,
            "title": cfg.get("timer_default_title", "Ya vuelvo"),
            "phrase": cfg.get("timer_default_phrase", "Compilando cerebro... (42 warnings, 0 errors)"),
            "play_sound": True
        }
        self._thread = None
        self._stop_event = threading.Event()

    def get_state(self) -> dict:
        with self.lock:
            return self.timer_state.copy()

    def get_status(self) -> dict:
        return self.get_state()

    def start_timer(self, seconds: int = None, duration: int = None, minutes: float = None, title: str = "Ya vuelvo", phrase: str = "", play_sound: bool = True) -> dict:
        with self.lock:
            sec = seconds or duration
            if sec is not None:
                total_sec = max(5, int(sec))
            elif minutes is not None:
                total_sec = max(5, int(float(minutes) * 60))
            else:
                total_sec = 300

            cfg = self.load_config()
            phrases = cfg.get("student_phrases", [])
            chosen_phrase = phrase.strip() if phrase else (phrases[0] if phrases else "Compilando...")

            self.timer_state = {
                "active": True,
                "running": True,
                "total_seconds": total_sec,
                "duration": total_sec,
                "remaining_seconds": total_sec,
                "remaining": total_sec,
                "start_epoch": time.time(),
                "title": title.strip() or "Ya vuelvo",
                "phrase": chosen_phrase,
                "play_sound": play_sound
            }
            self._stop_event.clear()

        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._countdown_loop, daemon=True)
            self._thread.start()

        self._emit_update()
        return self.get_state()

    def add_timer(self, seconds: int) -> dict:
        with self.lock:
            if not self.timer_state.get("active"):
                return self.start_timer(seconds=seconds)
            
            self.timer_state["remaining_seconds"] += seconds
            self.timer_state["remaining"] += seconds
            self.timer_state["total_seconds"] += seconds
            self.timer_state["duration"] += seconds
            self.timer_state["last_updated"] = time.time()
            self._save_timer_state()
            self._trigger_event()
            return self.get_status()

    def pause_timer(self) -> dict:
        with self.lock:
            if not self.timer_state["active"]:
                return self.timer_state.copy()
            self.timer_state["running"] = not self.timer_state["running"]
            if self.timer_state["running"]:
                self.timer_state["start_epoch"] = time.time() - (self.timer_state["total_seconds"] - self.timer_state["remaining_seconds"])
        self._emit_update()
        return self.get_state()

    def stop_timer(self) -> dict:
        with self.lock:
            self.timer_state["active"] = False
            self.timer_state["running"] = False
            self.timer_state["remaining_seconds"] = 0
            self.timer_state["remaining"] = 0
            self._stop_event.set()
        self._emit_update()
        return self.get_state()

    def set_live_text(self, title: str = None, phrase: str = None) -> dict:
        with self.lock:
            if phrase is not None:
                self.timer_state["phrase"] = phrase.strip()
            if title is not None:
                self.timer_state["title"] = title.strip()
        self._emit_update()
        return self.get_state()

    def _countdown_loop(self):
        while not self._stop_event.is_set():
            time.sleep(0.5)
            with self.lock:
                if not self.timer_state["active"]:
                    break
                if not self.timer_state["running"]:
                    continue

                elapsed = int(time.time() - self.timer_state["start_epoch"])
                rem = max(0, self.timer_state["total_seconds"] - elapsed)
                self.timer_state["remaining_seconds"] = rem
                self.timer_state["remaining"] = rem

                if rem <= 0:
                    self.timer_state["running"] = False
                    self.timer_state["remaining_seconds"] = 0
                    self.timer_state["remaining"] = 0
                    self._emit_update("timer_update")
                    self._emit_update("timer_finished")
                    threading.Thread(target=self._auto_deactivate_timer, daemon=True).start()
                    break

            self._emit_update()

    def _auto_deactivate_timer(self):
        time.sleep(4)
        with self.lock:
            if not self.timer_state["running"] and self.timer_state["active"] and self.timer_state["remaining_seconds"] <= 0:
                self.timer_state["active"] = False
        self._emit_update("timer_update")

    def _emit_update(self, event_name: str = "timer_update"):
        st = self.get_state()
        self.broadcast(event_name, st)

    # ─── GESTIÓN DE FRASES DE ESTUDIANTE ───
    def get_phrases(self) -> list[str]:
        cfg = self.load_config()
        return cfg.get("student_phrases", [])

    def save_phrases(self, phrases: list[str]) -> list[str]:
        clean = [p.strip() for p in phrases if p and p.strip()]
        self.save_config({"student_phrases": clean})
        return clean

    def add_phrase(self, phrase: str) -> list[str]:
        phrases = self.get_phrases()
        p = phrase.strip()
        if p and p not in phrases:
            phrases.insert(0, p)
            self.save_phrases(phrases)
        return phrases

    def remove_phrase(self, phrase: str) -> list[str]:
        phrases = self.get_phrases()
        phrases = [p for p in phrases if p != phrase]
        self.save_phrases(phrases)
        return phrases
