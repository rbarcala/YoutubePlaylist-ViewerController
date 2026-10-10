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

    def _connect_and_identify(self, event_subscriptions=None):
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
            "d": {
                "rpcVersion": 1,
                "eventSubscriptions": int(event_subscriptions) if event_subscriptions is not None else 0
            }
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

    def _recv_exact(self, sock, n: int):
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return buf

    def _recv_ws_frame(self, sock):
        header = self._recv_exact(sock, 2)
        if not header:
            return None
        length = header[1] & 0x7F
        if length == 126:
            ext = self._recv_exact(sock, 2)
            if not ext: return None
            length = int.from_bytes(ext, 'big')
        elif length == 127:
            ext = self._recv_exact(sock, 8)
            if not ext: return None
            length = int.from_bytes(ext, 'big')
        payload = self._recv_exact(sock, length)
        if not payload:
            return None
        return payload.decode('utf-8', errors='ignore')

    def _recv_response(self, sock, request_id: str = None, max_frames: int = 15):
        """Descarta frames de eventos (op 5) hasta encontrar la respuesta a una petición (op 7)."""
        for _ in range(max_frames):
            frame_str = self._recv_ws_frame(sock)
            if not frame_str:
                return None
            try:
                frame = json.loads(frame_str)
                op = frame.get("op")
                if op == 7:
                    if request_id is None or frame.get("d", {}).get("requestId") == request_id:
                        return frame
            except Exception:
                continue
        return None

    def switch_scene(self, scene_name: str) -> dict:
        """Cambia la escena actual en OBS Studio."""
        if not scene_name:
            return {"success": False, "error": "Nombre de escena vacío"}
        try:
            sock = self._connect_and_identify()
            if not sock:
                return {"success": False, "error": "No se pudo conectar a OBS"}

            req_id = "change-scene-" + str(int(time.time() * 1000))
            req_payload = {
                "op": 6,
                "d": {
                    "requestType": "SetCurrentProgramScene",
                    "requestId": req_id,
                    "requestData": {"sceneName": scene_name}
                }
            }
            self._send_ws_frame(sock, json.dumps(req_payload))
            resp = self._recv_response(sock, req_id)
            sock.close()

            if not resp:
                # Si no llegó frame op 7 pero se envió la trama sin error
                return {"success": True, "scene": scene_name}

            status = resp.get("d", {}).get("requestStatus", {})
            code = status.get("code", 0)
            result = status.get("result", False)
            if result or code == 100:
                return {"success": True, "scene": scene_name}

            comment = status.get("comment", "Error al cambiar de escena en OBS")
            return {"success": False, "error": comment}
        except Exception as e:
            return {"success": False, "error": str(e)}

    set_current_program_scene = switch_scene

    def get_scenes(self) -> dict:
        """Obtiene la lista de escenas y la escena actual activa."""
        try:
            sock = self._connect_and_identify()
            if not sock:
                return {"success": False, "scenes": [], "current_scene": ""}

            req_id = "scenes-" + str(int(time.time() * 1000))
            req1 = {
                "op": 6,
                "d": {
                    "requestType": "GetSceneList",
                    "requestId": req_id
                }
            }
            self._send_ws_frame(sock, json.dumps(req1))
            resp1 = self._recv_response(sock, req_id) or {}
            current_program = resp1.get("d", {}).get("responseData", {}).get("currentProgramSceneName", "")
            scenes_data = resp1.get("d", {}).get("responseData", {}).get("scenes", [])
            names = [s.get("sceneName") for s in reversed(scenes_data) if "sceneName" in s]

            sock.close()
            return {"success": True, "scenes": names, "current_scene": current_program}
        except Exception as e:
            return {"success": False, "error": str(e), "scenes": [], "current_scene": ""}

    def get_scene_list(self) -> list:
        """Alias para obtener la lista de nombres de escenas de OBS."""
        return self.get_scenes().get("scenes", [])

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
            resp_stream = self._recv_response(sock, "stream-status") or {}
            is_streaming = resp_stream.get("d", {}).get("responseData", {}).get("outputActive", False)

            # GetRecordStatus
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {"requestType": "GetRecordStatus", "requestId": "record-status"}
            }))
            resp_rec = self._recv_response(sock, "record-status") or {}
            is_recording = resp_rec.get("d", {}).get("responseData", {}).get("outputActive", False)

            # GetCurrentProgramScene
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {"requestType": "GetCurrentProgramScene", "requestId": "curr-scene"}
            }))
            resp_scene = self._recv_response(sock, "curr-scene") or {}
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
            resp = self._recv_response(sock, "toggle-stream") or {}
            sock.close()
            active = resp.get("d", {}).get("responseData", {}).get("outputActive", False)
            return {"success": True, "outputActive": active}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_screenshot(self, source_name: str = "", width: int = 480, height: int = 270, quality: int = 40) -> dict:
        try:
            sock = self._connect_and_identify()
            if not sock: return {"success": False, "error": "No se pudo conectar a OBS"}
            
            # Si no se pasó source_name, consultar la escena activa actual
            target_source = source_name
            if not target_source:
                self._send_ws_frame(sock, json.dumps({
                    "op": 6,
                    "d": {"requestType": "GetCurrentProgramScene", "requestId": "get-curr-scene"}
                }))
                resp_scene = self._recv_response(sock, "get-curr-scene") or {}
                target_source = resp_scene.get("d", {}).get("responseData", {}).get("currentProgramSceneName", "")

            if not target_source:
                sock.close()
                return {"success": False, "error": "No se pudo determinar la escena actual"}

            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {
                    "requestType": "GetSourceScreenshot",
                    "requestId": "get-screenshot",
                    "requestData": {
                        "sourceName": target_source,
                        "imageFormat": "jpeg",
                        "imageWidth": int(width),
                        "imageHeight": int(height),
                        "imageCompressionQuality": int(quality)
                    }
                }
            }))
            resp = self._recv_response(sock, "get-screenshot") or {}
            sock.close()
            img_data = resp.get("d", {}).get("responseData", {}).get("imageData", "")
            if img_data:
                return {"success": True, "imageData": img_data, "scene": target_source}
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
            resp = self._recv_response(sock, "start-vcam") or {}
            sock.close()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_video_settings(self) -> dict:
        """Obtiene la resolución base y de salida del lienzo de OBS."""
        try:
            sock = self._connect_and_identify()
            if not sock: return {"success": False}
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {"requestType": "GetVideoSettings", "requestId": "get-video-settings"}
            }))
            resp = self._recv_response(sock, "get-video-settings") or {}
            sock.close()
            data = resp.get("d", {}).get("responseData", {})
            return {
                "success": True,
                "baseWidth": data.get("baseWidth", 1920),
                "baseHeight": data.get("baseHeight", 1080),
                "outputWidth": data.get("outputWidth", 1920),
                "outputHeight": data.get("outputHeight", 1080)
            }
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
            resp = self._recv_response(sock, "toggle-record") or {}
            sock.close()
            active = resp.get("d", {}).get("responseData", {}).get("outputActive", False)
            return {"success": True, "outputActive": active}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_audio_inputs(self) -> dict:
        """Obtiene información de entradas de audio principales (Desktop Audio y Micrófono)."""
        try:
            sock = self._connect_and_identify()
            if not sock:
                return {"connected": False, "inputs": {}}

            # Consultar inputs especiales (desktop1, mic1)
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {"requestType": "GetSpecialInputs", "requestId": "get-special-inputs"}
            }))
            resp_spec = self._recv_response(sock, "get-special-inputs") or {}
            spec_data = resp_spec.get("d", {}).get("responseData", {})
            desktop_name = spec_data.get("desktop1") or "Desktop Audio"
            mic_name = spec_data.get("mic1") or "Mic/Aux"

            # Consultar lista general por si los nombres difieren
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {"requestType": "GetInputList", "requestId": "get-all-inputs"}
            }))
            resp_list = self._recv_response(sock, "get-all-inputs") or {}
            all_inputs = [x.get("inputName") for x in resp_list.get("d", {}).get("responseData", {}).get("inputs", [])]

            if desktop_name not in all_inputs:
                for inp in all_inputs:
                    if "desktop" in inp.lower() or "sistema" in inp.lower():
                        desktop_name = inp
                        break

            if mic_name not in all_inputs:
                for inp in all_inputs:
                    if "mic" in inp.lower() or "aux" in inp.lower():
                        mic_name = inp
                        break

            result_inputs = {}
            for key, name in [("desktop", desktop_name), ("mic", mic_name)]:
                if name and name in all_inputs:
                    self._send_ws_frame(sock, json.dumps({
                        "op": 6,
                        "d": {"requestType": "GetInputVolume", "requestId": f"vol-{key}", "requestData": {"inputName": name}}
                    }))
                    resp_vol = self._recv_response(sock, f"vol-{key}") or {}
                    vdata = resp_vol.get("d", {}).get("responseData", {})

                    self._send_ws_frame(sock, json.dumps({
                        "op": 6,
                        "d": {"requestType": "GetInputMute", "requestId": f"mute-{key}", "requestData": {"inputName": name}}
                    }))
                    resp_mute = self._recv_response(sock, f"mute-{key}") or {}
                    mdata = resp_mute.get("d", {}).get("responseData", {})

                    result_inputs[key] = {
                        "name": name,
                        "volumeDb": vdata.get("inputVolumeDb", 0.0),
                        "volumeMul": vdata.get("inputVolumeMul", 1.0),
                        "muted": mdata.get("inputMuted", False)
                    }
                else:
                    result_inputs[key] = {
                        "name": name,
                        "volumeDb": 0.0,
                        "volumeMul": 1.0,
                        "muted": False
                    }

            sock.close()
            return {"connected": True, "inputs": result_inputs}
        except Exception as e:
            return {"connected": False, "error": str(e), "inputs": {}}

    def set_input_volume(self, input_name: str, volume_mul: float) -> dict:
        """Establece el volumen de una fuente en multiplicador (0.0 a 1.0)."""
        try:
            sock = self._connect_and_identify()
            if not sock: return {"success": False, "error": "No conectado a OBS"}
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {
                    "requestType": "SetInputVolume",
                    "requestId": f"set-vol-{int(time.time()*1000)}",
                    "requestData": {"inputName": input_name, "inputVolumeMul": max(0.0, min(1.0, float(volume_mul)))}
                }
            }))
            self._recv_ws_frame(sock)
            sock.close()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_input_mute(self, input_name: str, muted: bool = None) -> dict:
        """Mutea, desmutea o alterna el mute de una fuente en OBS."""
        try:
            sock = self._connect_and_identify()
            if not sock: return {"success": False, "error": "No conectado a OBS"}
            if muted is None:
                req_type = "ToggleInputMute"
                req_data = {"inputName": input_name}
            else:
                req_type = "SetInputMute"
                req_data = {"inputName": input_name, "inputMuted": bool(muted)}
            
            self._send_ws_frame(sock, json.dumps({
                "op": 6,
                "d": {
                    "requestType": req_type,
                    "requestId": f"set-mute-{int(time.time()*1000)}",
                    "requestData": req_data
                }
            }))
            resp = json.loads(self._recv_ws_frame(sock) or "{}")
            sock.close()
            new_mute = resp.get("d", {}).get("responseData", {}).get("inputMuted", muted)
            return {"success": True, "muted": new_mute}
        except Exception as e:
            return {"success": False, "error": str(e)}

