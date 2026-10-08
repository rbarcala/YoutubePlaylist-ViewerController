import json
import threading

class WebSocketManager:
    """Gestiona la difusión de eventos SSE a múltiples clientes."""
    def __init__(self):
        self.listeners = []
        self.lock = threading.Lock()

    def add_listener(self, queue):
        """Añade un nuevo cliente (cola) a la lista de escuchas."""
        with self.lock:
            self.listeners.append(queue)

    def remove_listener(self, queue):
        """Elimina un cliente de la lista de escuchas."""
        with self.lock:
            if queue in self.listeners:
                self.listeners.remove(queue)

    def broadcast_event(self, event_type: str, data: dict):
        """Difunde un evento a todos los clientes conectados."""
        payload = f'event: {event_type}\ndata: {json.dumps(data)}\n\n'
        with self.lock:
            dead = []
            for q in self.listeners:
                try:
                    q.put(payload)
                except Exception:
                    dead.append(q)
            for q in dead:
                if q in self.listeners:
                    self.listeners.remove(q)

# Instancia global para ser usada por toda la aplicación
ws_manager = WebSocketManager()
broadcast_event = ws_manager.broadcast_event
