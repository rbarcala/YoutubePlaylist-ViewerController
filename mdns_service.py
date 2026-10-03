"""
Módulo de Detección Automática por Red (mDNS / Zeroconf / DNS-SD & UDP Beacon).
Permite conexión a 0 clics desde la app de celular sin necesidad de QR ni dígitos.
"""

import socket
import threading
import time

class MDNSServicePublisher:
    def __init__(self, port: int = 8000, service_name: str = "YouTube Stream Controller"):
        self.port = port
        self.service_name = service_name
        self.running = False
        self._entry_group = None
        self._udp_thread = None

    def start(self):
        """Inicia el anuncio por mDNS (Avahi/DBus) y el beacon de descubrimiento UDP."""
        self.running = True
        
        # 1. Anuncio mDNS nativo vía Avahi DBus (Linux)
        t_mdns = threading.Thread(target=self._start_avahi_mdns, daemon=True)
        t_mdns.start()

        # 2. Beacon de descubrimiento rápido UDP en LAN (puerto 8001)
        self._udp_thread = threading.Thread(target=self._start_udp_beacon, daemon=True)
        self._udp_thread.start()

    def _start_avahi_mdns(self):
        """Registra el servicio en Avahi mDNS vía DBus si está disponible."""
        try:
            from gi.repository import Gio
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            server = Gio.DBusProxy.new_sync(
                bus, Gio.DBusProxyFlags.NONE, None,
                "org.freedesktop.Avahi", "/", "org.freedesktop.Avahi.Server", None
            )
            entry_group_path = server.EntryGroupNew()
            group = Gio.DBusProxy.new_sync(
                bus, Gio.DBusProxyFlags.NONE, None,
                "org.freedesktop.Avahi", entry_group_path, "org.freedesktop.Avahi.EntryGroup", None
            )

            txt = [list(b"path=/controller.html"), list(b"app=fondosstream")]
            group.AddService("(iiussssqaay)", -1, -1, 0, self.service_name, "_streamcontroller._tcp", "", "", self.port, txt)
            group.Commit()
            self._entry_group = group
            print(f"[mDNS] Servicio Zeroconf '{self.service_name}' anunciado en _streamcontroller._tcp:{self.port} vía Avahi.")
        except Exception as e:
            print(f"[mDNS] Avahi no disponible o no accesible vía DBus: {e}. Beacon UDP activo.")

    def _start_udp_beacon(self):
        """Responde a solicitudes de descubrimiento UDP broadcast de la app Android."""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", 8001))
            sock.settimeout(2.0)
            print(f"[mDNS] Beacon de descubrimiento UDP escuchando en puerto 8001.")
        except Exception as e:
            print(f"[mDNS] Error al enlazar socket UDP 8001: {e}")
            if sock:
                try: sock.close()
                except Exception: pass
            return

        while self.running:
            try:
                data, addr = sock.recvfrom(1024)
                if not data:
                    continue
                msg = data.decode("utf-8", errors="ignore").strip()
                if "STREAM_CONTROLLER_DISCOVER" in msg:
                    response = f"STREAM_CONTROLLER_SERVER:{self.port}:{self.service_name}".encode("utf-8")
                    sock.sendto(response, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    time.sleep(0.5)

        try:
            sock.close()
        except Exception:
            pass

    def stop(self):
        self.running = False
        if self._entry_group:
            try:
                self._entry_group.Reset()
            except Exception:
                pass

_publisher = None

def start_mdns_publisher(port: int = 8000):
    global _publisher
    if _publisher is None:
        _publisher = MDNSServicePublisher(port=port)
        _publisher.start()
    return _publisher
