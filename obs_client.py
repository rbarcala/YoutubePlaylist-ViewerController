"""
OBS Studio WebSocket v5 Client (Protocolo oficial OBS Studio 28+)
Permite cambiar escenas y controlar fuentes, stream y grabación desde cualquier dispositivo.
"""

import json
import base64
import hashlib
import socket
import threading
import time

class OBSController:
    def __init__(self, host="localhost", port=4455, password=""):
        self.host = host
        self.port = int(port)
        self.password = password

    def _connect_and_identify(self):
        """Conecta con OBS WebSocket v5 y realiza la identificación."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.5)
        sock.connect((self.host, self.port))

        key = base64.b64encode(b"1234567890123456").decode('utf-8')
        req = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode('utf-8'))
        resp = sock.recv(4096).decode('utf-8', errors='ignore')
        if "101" not in resp:
            sock.close()
            return None

        # Leer Hello (OpCode 0)
        hello_str = self._recv_ws_frame(sock)
        if not hello_str:
            sock.close()
            return None

        hello = json.loads(hello_str)
        auth_info = hello.get("d", {}).get("authentication", {})
        auth_response = None

        if auth_info and self.password:
            salt = auth_info.get("salt", "")
            challenge = auth_info.get("challenge", "")
            h1 = hashlib.sha256((self.password + salt).encode('utf-8')).digest()
            h1_b64 = base64.b64encode(h1).decode('utf-8')
            h2 = hashlib.sha256((h1_b64 + challenge).encode('utf-8')).digest()
            auth_response = base64.b64encode(h2).decode('utf-8')

        identify_payload = {
            "op": 1,
            "d": {"rpcVersion": 1}
        }
        if auth_response:
            identify_payload["d"]["authentication"] = auth_response

        self._send_ws_frame(sock, json.dumps(identify_payload))
        # Identified (OpCode 2)
        self._recv_ws_frame(sock)
        return sock

    def _send_ws_frame(self, sock, message: str):
        data = message.encode('utf-8')
        length = len(data)
        frame = bytearray([0x81])
        mask = [0x12, 0x34, 0x56, 0x78]
        if length <= 125:
            frame.append(0x80 | length)
        elif length <= 65535:
            frame.append(0x80 | 126)
            frame.extend(length.to_bytes(2, byteorder='big'))
        else:
            frame.append(0x80 | 127)
            frame.extend(length.to_bytes(8, byteorder='big'))
        frame.extend(mask)
        masked_data = bytearray(data[i] ^ mask[i % 4] for i in range(length))
        frame.extend(masked_data)
        sock.sendall(frame)

    def _recv_ws_frame(self, sock):
        header = sock.recv(2)
        if len(header) < 2:
            return None
        length = header[1] & 0x7F
        if length == 126:
            length = int.from_bytes(sock.recv(2), byteorder='big')
        elif length == 127:
            length = int.from_bytes(sock.recv(8), byteorder='big')
        data = bytearray()
        while len(data) < length:
            chunk = sock.recv(min(4096, length - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        return data.decode('utf-8', errors='ignore')

    def switch_scene(self, scene_name: str) -> dict:
        """Cambia la escena actual en OBS Studio."""
        if not scene_name:
            return {"success": False, "error": "Nombre de escena vacío"}
        try:
            sock = self._connect_and_identify()
            if not sock:
                return {"success": False, "error": "No se pudo conectar a OBS"}

            req_payload = {
                "op": 6,
                "d": {
                    "requestType": "SetCurrentProgramScene",
                    "requestId": "change-scene-" + str(int(time.time())),
                    "requestData": {"sceneName": scene_name}
                }
            }
            self._send_ws_frame(sock, json.dumps(req_payload))
            resp_str = self._recv_ws_frame(sock)
            sock.close()
            return {"success": True, "scene": scene_name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_scenes(self) -> dict:
        """Obtiene la lista de escenas y la escena actual activa."""
        try:
            sock = self._connect_and_identify()
            if not sock:
                return {"success": False, "scenes": [], "current_scene": ""}

            # GetSceneList
            req1 = {
                "op": 6,
                "d": {
                    "requestType": "GetSceneList",
                    "requestId": "scenes-" + str(int(time.time()))
                }
            }
            self._send_ws_frame(sock, json.dumps(req1))
            resp1 = json.loads(self._recv_ws_frame(sock) or "{}")
            current_program = resp1.get("d", {}).get("responseData", {}).get("currentProgramSceneName", "")
            scenes_data = resp1.get("d", {}).get("responseData", {}).get("scenes", [])
            names = [s.get("sceneName") for s in reversed(scenes_data) if "sceneName" in s]

            sock.close()
            return {"success": True, "scenes": names, "current_scene": current_program}
        except Exception as e:
            return {"success": False, "error": str(e), "scenes": [], "current_scene": ""}

    def get_status(self) -> dict:
        """Obtiene el estado general de streaming, grabación y escena."""
        try:
            sock = self._connect_and_identify()
            if not sock:
                return {"connected": False}

            # GetStreamStatus
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {"requestType": "GetStreamStatus", "requestId": "stream-status"}
            }))
            resp_stream = json.loads(self._recv_ws_frame(sock) or "{}")
            is_streaming = resp_stream.get("d", {}).get("responseData", {}).get("outputActive", False)

            # GetRecordStatus
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {"requestType": "GetRecordStatus", "requestId": "record-status"}
            }))
            resp_rec = json.loads(self._recv_ws_frame(sock) or "{}")
            is_recording = resp_rec.get("d", {}).get("responseData", {}).get("outputActive", False)

            # GetCurrentProgramScene
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {"requestType": "GetCurrentProgramScene", "requestId": "curr-scene"}
            }))
            resp_scene = json.loads(self._recv_ws_frame(sock) or "{}")
            current_scene = resp_scene.get("d", {}).get("responseData", {}).get("currentProgramSceneName", "")

            sock.close()
            return {
                "connected": True,
                "is_streaming": is_streaming,
                "is_recording": is_recording,
                "current_scene": current_scene
            }
        except Exception:
            return {"connected": False}

    def toggle_stream(self) -> dict:
        try:
            sock = self._connect_and_identify()
            if not sock: return {"success": False}
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {"requestType": "ToggleStream", "requestId": "toggle-stream"}
            }))
            resp = json.loads(self._recv_ws_frame(sock) or "{}")
            sock.close()
            active = resp.get("d", {}).get("responseData", {}).get("outputActive", False)
            return {"success": True, "outputActive": active}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_screenshot(self, source_name: str) -> dict:
        try:
            sock = self._connect_and_identify()
            if not sock: return {"success": False}
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {
                    "requestType": "GetSourceScreenshot",
                    "requestId": "get-screenshot",
                    "requestData": {
                        "sourceName": source_name,
                        "imageFormat": "jpeg",
                        "imageWidth": 320,
                        "imageHeight": 180,
                        "imageCompressionQuality": 20
                    }
                }
            }))
            resp = json.loads(self._recv_ws_frame(sock) or "{}")
            sock.close()
            img_data = resp.get("d", {}).get("responseData", {}).get("imageData", "")
            if img_data:
                return {"success": True, "imageData": img_data}
            return {"success": False, "error": "No imageData in response"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def start_virtual_cam(self) -> dict:
        try:
            sock = self._connect_and_identify()
            if not sock: return {"success": False}
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {
                    "requestType": "StartVirtualCam",
                    "requestId": "start-vcam"
                }
            }))
            resp = json.loads(self._recv_ws_frame(sock) or "{}")
            sock.close()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def toggle_record(self) -> dict:
        try:
            sock = self._connect_and_identify()
            if not sock: return {"success": False}
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {"requestType": "ToggleRecord", "requestId": "toggle-record"}
            }))
            resp = json.loads(self._recv_ws_frame(sock) or "{}")
            sock.close()
            active = resp.get("d", {}).get("responseData", {}).get("outputActive", False)
            return {"success": True, "outputActive": active}
        except Exception as e:
            return {"success": False, "error": str(e)}
