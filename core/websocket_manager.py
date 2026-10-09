import json
import time
import queue
import threading


class WebSocketManager:
    """Gestiona la difusión de eventos SSE a múltiples clientes."""

    def __init__(self):
        self.listeners = set()
        self.lock = threading.Lock()
        self.active_viewers = set()
        self.viewer_lock = threading.Lock()

    def add_listener(self, q):
        """Añade un nuevo cliente (cola) a la lista de escuchas."""
        with self.lock:
            self.listeners.add(q)

    def remove_listener(self, q):
        """Elimina un cliente de la lista de escuchas."""
        with self.lock:
            self.listeners.discard(q)

    def broadcast_event(self, event_type: str, data: dict):
        """Difunde un evento a todos los clientes conectados con formato SSE esperado por el frontend."""
        payload = json.dumps({"type": event_type, "data": data, "timestamp": time.time()})
        sse_message = f"event: {event_type}\ndata: {payload}\n\n"
        with self.lock:
            dead = []
            for q in list(self.listeners):
                try:
                    q.put_nowait(sse_message)
                except queue.Full:
                    try:
                        q.get_nowait()
                        q.put_nowait(sse_message)
                    except Exception:
                        pass
                except Exception:
                    dead.append(q)
            for q in dead:
                self.listeners.discard(q)


# Instancia global para ser usada por toda la aplicación
ws_manager = WebSocketManager()
broadcast_event = ws_manager.broadcast_event
