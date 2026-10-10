#!/usr/bin/env python3
"""
Script de Configuración Automática de OBS Studio & Capas de Overlays.
Se ejecuta durante 'make install' (o manualmente con 'make setup-obs').

Acciones automáticas:
1. Detecta la instalación de OBS Studio (Nativa, Flatpak o Snap).
2. Habilita OBS WebSocket v5 en global.ini (puerto 4455, sin fricción).
3. Sincroniza las credenciales de OBS con config.json del Controller.
4. Agrega automáticamente la capa 'Overlay Stream Hub' (1920x1080)
   como Browser Source (fuente navegador) tanto si OBS está abierto
   (vía WebSocket en vivo) como si está cerrado (inyectado en scenes/*.json).
"""

import os
import sys
import json
import uuid
import shutil
import socket
import base64
import hashlib
import configparser
from pathlib import Path

# Directorio raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

try:
    from services.config_manager import load_config, save_config
except ImportError:
    try:
        from config_manager import load_config, save_config
    except ImportError:
        def load_config(): return {}
        def save_config(cfg): return cfg

OVERLAY_SOURCE_NAME = "Overlay Stream Controller"
OVERLAY_WIDTH = 1920
OVERLAY_HEIGHT = 1080
OVERLAY_CSS = "body { background-color: rgba(0, 0, 0, 0); margin: 0px auto; overflow: hidden; }"

def get_overlay_url(port=8000):
    return f"http://localhost:{port}/overlay.html"

def find_obs_config_dirs() -> list[Path]:
    """Busca todas las ubicaciones posibles de configuración de OBS en Linux."""
    home = Path.home()
    candidates = [
        home / ".config" / "obs-studio",                                        # Nativo (.deb / PPA / apt)
        home / ".var" / "app" / "com.obsproject.Studio" / "config" / "obs-studio", # Flatpak
        home / "snap" / "obs-studio" / "current" / ".config" / "obs-studio",    # Snap
    ]
    
    found = [p for p in candidates if p.exists() and p.is_dir()]
    
    # Si ninguna existe pero OBS está instalado en el sistema, preparamos la ruta nativa estándar
    if not found:
        default_dir = home / ".config" / "obs-studio"
        default_dir.mkdir(parents=True, exist_ok=True)
        found.append(default_dir)
        
    return found

def configure_obs_global_ini(obs_dir: Path) -> tuple[int, str]:
    """
    Configura global.ini en el directorio de OBS para habilitar WebSocket v5.
    Preserva el formato exacto del archivo sin alterar mayúsculas de otras secciones.
    Retorna (port, password).
    """
    ini_path = obs_dir / "global.ini"
    content = ""
    if ini_path.exists():
        try:
            content = ini_path.read_text(encoding="utf-8")
        except Exception:
            pass

    port = 4455
    password = ""
    auth_required = False

    lines = content.splitlines()
    in_ws_section = False
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped[1:-1].strip()
            if section_name.lower() == "obswebsocket":
                in_ws_section = True
                continue
            else:
                in_ws_section = False
        
        if in_ws_section:
            if "=" in line:
                k, v = line.split("=", 1)
                k_clean = k.strip().lower()
                v_clean = v.strip()
                if k_clean == "serverport":
                    try:
                        port = int(v_clean)
                    except ValueError:
                        pass
                elif k_clean == "serverpassword":
                    password = v_clean
                elif k_clean == "authrequired":
                    auth_required = v_clean.lower() in ("true", "1", "yes")
            continue
        
        new_lines.append(line)

    # Agregar la sección [OBSWebSocket] limpia y con CamelCase estándar de OBS
    ws_block = [
        "",
        "[OBSWebSocket]",
        "ServerEnabled=true",
        f"ServerPort={port}",
        f"ServerPassword={password if auth_required else ''}",
        f"AuthRequired={'true' if auth_required else 'false'}",
        "DebugEnabled=false",
        "AlertsEnabled=false"
    ]
    new_lines.extend(ws_block)

    try:
        final_content = "\n".join(new_lines).strip() + "\n"
        ini_path.write_text(final_content, encoding="utf-8")
        print(f"  [✓] OBS WebSocket v5 configurado en {ini_path.name} (Puerto: {port}, Autenticación: {'Sí' if auth_required else 'No'})")
    except Exception as e:
        print(f"  [!] No se pudo escribir {ini_path}: {e}")

    return port, password

def try_add_overlay_via_websocket(port: int, password: str, overlay_url: str) -> bool:
    """Intenta conectarse a OBS si está en ejecución y agrega el overlay en vivo."""
    try:
        from services.obs_client import OBSController
        obs = OBSController(host="localhost", port=port, password=password)
        sock = obs._connect_and_identify()
        if not sock:
            return False

        # Obtener lista de escenas
        req = {
            "op": 6,
            "d": {
                "requestType": "GetSceneList",
                "requestId": "setup-get-scenes"
            }
        }
        obs._send_ws_frame(sock, json.dumps(req))
        resp = json.loads(obs._recv_ws_frame(sock) or "{}")
        scenes = resp.get("d", {}).get("responseData", {}).get("scenes", [])
        if not scenes:
            sock.close()
            return False

        has_clase = any(sc.get("sceneName") == "CLASE" for sc in scenes)
        if not has_clase:
            create_scene_req = {
                "op": 6,
                "d": {
                    "requestType": "CreateScene",
                    "requestId": "create-scene-clase",
                    "requestData": {
                        "sceneName": "CLASE"
                    }
                }
            }
            obs._send_ws_frame(sock, json.dumps(create_scene_req))
            obs._recv_ws_frame(sock)
            scenes.append({"sceneName": "CLASE"})

        # Obtener lista de inputs existentes para no duplicar si ya existe 'Overlay Stream Hub' o 'Overlay Stream Controller'
        req_inputs = {
            "op": 6,
            "d": {
                "requestType": "GetInputList",
                "requestId": "setup-get-inputs"
            }
        }
        obs._send_ws_frame(sock, json.dumps(req_inputs))
        resp_inputs = json.loads(obs._recv_ws_frame(sock) or "{}")
        all_inputs = resp_inputs.get("d", {}).get("responseData", {}).get("inputs", [])
        input_names = [inp.get("inputName") for inp in all_inputs]

        target_input_name = OVERLAY_SOURCE_NAME
        if "Overlay Stream Hub" in input_names and OVERLAY_SOURCE_NAME not in input_names:
            target_input_name = "Overlay Stream Hub"
        elif OVERLAY_SOURCE_NAME in input_names:
            target_input_name = OVERLAY_SOURCE_NAME

        added_count = 0
        for sc in scenes:
            scene_name = sc.get("sceneName")
            if not scene_name or scene_name != "CLASE":
                continue

            # Si el input ya existe en OBS, solo actualizamos sus parámetros
            if target_input_name in input_names:
                set_req = {
                    "op": 6,
                    "d": {
                        "requestType": "SetInputSettings",
                        "requestId": f"update-overlay-{scene_name}",
                        "requestData": {
                            "inputName": target_input_name,
                            "inputSettings": {
                                "url": overlay_url,
                                "width": OVERLAY_WIDTH,
                                "height": OVERLAY_HEIGHT,
                                "css": OVERLAY_CSS
                            }
                        }
                    }
                }
                obs._send_ws_frame(sock, json.dumps(set_req))
                obs._recv_ws_frame(sock)
                added_count += 1
                continue

            # Si no existe, crear la entrada Browser Source
            create_req = {
                "op": 6,
                "d": {
                    "requestType": "CreateInput",
                    "requestId": f"create-overlay-{scene_name}",
                    "requestData": {
                        "sceneName": scene_name,
                        "inputName": target_input_name,
                        "inputKind": "browser_source",
                        "inputSettings": {
                            "url": overlay_url,
                            "width": OVERLAY_WIDTH,
                            "height": OVERLAY_HEIGHT,
                            "css": OVERLAY_CSS,
                            "shutdown": False,
                            "restart_when_active": False,
                            "reroute_audio": False
                        },
                        "sceneItemEnabled": True
                    }
                }
            }
            obs._send_ws_frame(sock, json.dumps(create_req))
            c_resp = json.loads(obs._recv_ws_frame(sock) or "{}")
            code = c_resp.get("d", {}).get("requestStatus", {}).get("code", 0)

            # Si ya existía (code != 100), actualizamos los parámetros de la URL
            if code != 100:
                set_req = {
                    "op": 6,
                    "d": {
                        "requestType": "SetInputSettings",
                        "requestId": f"update-overlay-{scene_name}",
                        "requestData": {
                            "inputName": target_input_name,
                            "inputSettings": {
                                "url": overlay_url,
                                "width": OVERLAY_WIDTH,
                                "height": OVERLAY_HEIGHT,
                                "css": OVERLAY_CSS
                            }
                        }
                    }
                }
                obs._send_ws_frame(sock, json.dumps(set_req))
                obs._recv_ws_frame(sock)
            added_count += 1

        sock.close()
        print(f"  [✓] OBS en ejecución detectado: Capa '{target_input_name}' conectada vía WebSocket en vivo.")
        return True
    except Exception:
        return False

def inject_overlay_into_scene_json(json_path: Path, overlay_url: str) -> bool:
    """Inyecta la capa Browser Source directamente en el archivo JSON de colecciones de escenas de OBS."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [!] No se pudo leer {json_path}: {e}")
        return False

    sources = data.setdefault("sources", [])
    
    # Buscar si ya existe la fuente
    source_uuid = None
    target_source_name = OVERLAY_SOURCE_NAME
    for s in sources:
        if s.get("name") in (OVERLAY_SOURCE_NAME, "Overlay Stream Hub"):
            target_source_name = s.get("name")
            source_uuid = s.get("uuid")
            # Actualizar settings
            s.setdefault("settings", {})["url"] = overlay_url
            s["settings"]["width"] = OVERLAY_WIDTH
            s["settings"]["height"] = OVERLAY_HEIGHT
            s["settings"]["css"] = OVERLAY_CSS
            break

    # Si no existe, crear la fuente
    if not source_uuid:
        source_uuid = str(uuid.uuid4())
        new_source = {
            "prev_ver": 537001984,
            "name": target_source_name,
            "uuid": source_uuid,
            "id": "browser_source",
            "versioned_id": "browser_source",
            "settings": {
                "url": overlay_url,
                "width": OVERLAY_WIDTH,
                "height": OVERLAY_HEIGHT,
                "css": OVERLAY_CSS,
                "reroute_audio": False,
                "restart_when_active": False,
                "shutdown": False
            },
            "mixers": 0,
            "sync": 0,
            "flags": 0,
            "volume": 1.0,
            "balance": 0.5,
            "enabled": True,
            "muted": False,
            "push-to-mute": False,
            "push-to-mute-delay": 0,
            "push-to-talk": False,
            "push-to-talk-delay": 0,
            "hotkeys": {},
            "deinterlace_mode": 0,
            "deinterlace_field_order": 0,
            "monitoring_type": 0,
            "private_settings": {}
        }
        sources.append(new_source)

    # Asegurar que la escena CLASE exista
    clase_scene = next((s for s in sources if s.get("id") == "scene" and s.get("name") == "CLASE"), None)
    if not clase_scene:
        clase_scene = {
            "prev_ver": 537001984,
            "name": "CLASE",
            "uuid": str(uuid.uuid4()),
            "id": "scene",
            "versioned_id": "scene",
            "settings": {
                "id_counter": 1,
                "items": []
            }
        }
        sources.append(clase_scene)
        # Añadir al orden de escenas para que sea visible
        if "scene_order" in data:
            data["scene_order"].append({"name": "CLASE"})

    # Inyectar el ítem solo en la escena llamada CLASE
    modified_scenes = 0
    for s in sources:
        if s.get("id") == "scene" and s.get("name") == "CLASE":
            scene_settings = s.setdefault("settings", {})
            items = scene_settings.setdefault("items", [])

            # Comprobar si ya está en esta escena
            has_item = any(it.get("source_uuid") == source_uuid or it.get("name") in (OVERLAY_SOURCE_NAME, "Overlay Stream Hub") for it in items)
            if not has_item:
                current_id_counter = scene_settings.get("id_counter", 1)
                next_id = max([it.get("id", 0) for it in items], default=0) + 1
                next_id = max(next_id, current_id_counter + 1)
                scene_settings["id_counter"] = next_id

                new_item = {
                    "name": target_source_name,
                    "source_uuid": source_uuid,
                    "visible": True,
                    "locked": False,
                    "rot": 0.0,
                    "scale_ref": {"x": float(OVERLAY_WIDTH), "y": float(OVERLAY_HEIGHT)},
                    "align": 5,
                    "bounds_type": 0,
                    "bounds_align": 0,
                    "bounds_crop": False,
                    "crop_left": 0, "crop_top": 0, "crop_right": 0, "crop_bottom": 0,
                    "id": next_id,
                    "group_item_backup": False,
                    "pos": {"x": 0.0, "y": 0.0},
                    "pos_rel": {"x": -1.7777777910232544, "y": -1.0},
                    "scale": {"x": 1.0, "y": 1.0},
                    "scale_rel": {"x": 1.0, "y": 1.0},
                    "bounds": {"x": 0.0, "y": 0.0},
                    "bounds_rel": {"x": 0.0, "y": 0.0},
                    "scale_filter": "disable",
                    "blend_method": "default",
                    "blend_type": "normal",
                    "show_transition": {"duration": 300},
                    "hide_transition": {"duration": 300},
                    "private_settings": {}
                }
                # Insertar al inicio para que quede arriba en el orden visual de capas
                items.insert(0, new_item)
                modified_scenes += 1

    # Guardar copia de respaldo y archivo modificado
    try:
        bak_path = json_path.with_suffix(".json.bak")
        shutil.copy2(json_path, bak_path)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  [✓] Capa '{OVERLAY_SOURCE_NAME}' inyectada en {json_path.name} ({modified_scenes} escena/s)")
        return True
    except Exception as e:
        print(f"  [!] Error guardando {json_path}: {e}")
        return False

def create_default_scene_collection_if_needed(scenes_dir: Path, overlay_url: str):
    """Crea una colección inicial 'Untitled.json' si el usuario nunca ha abierto OBS."""
    scenes_dir.mkdir(parents=True, exist_ok=True)
    json_files = list(scenes_dir.glob("*.json"))
    if json_files:
        return

    default_file = scenes_dir / "Untitled.json"
    source_uuid = str(uuid.uuid4())
    scene_uuid = str(uuid.uuid4())

    default_data = {
        "name": "Untitled",
        "current_scene": "CLASE",
        "current_program_scene": "CLASE",
        "scene_order": [{"name": "CLASE"}],
        "sources": [
            {
                "prev_ver": 537001984,
                "name": OVERLAY_SOURCE_NAME,
                "uuid": source_uuid,
                "id": "browser_source",
                "versioned_id": "browser_source",
                "settings": {
                    "url": overlay_url,
                    "width": OVERLAY_WIDTH,
                    "height": OVERLAY_HEIGHT,
                    "css": OVERLAY_CSS,
                    "reroute_audio": False,
                    "restart_when_active": False,
                    "shutdown": False
                },
                "enabled": True,
                "muted": False
            },
            {
                "prev_ver": 537001984,
                "name": "CLASE",
                "uuid": scene_uuid,
                "id": "scene",
                "versioned_id": "scene",
                "settings": {
                    "id_counter": 2,
                    "items": [
                        {
                            "name": OVERLAY_SOURCE_NAME,
                            "source_uuid": source_uuid,
                            "visible": True,
                            "id": 1,
                            "pos": {"x": 0.0, "y": 0.0},
                            "scale": {"x": 1.0, "y": 1.0}
                        }
                    ]
                }
            }
        ]
    }

    try:
        with open(default_file, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2, ensure_ascii=False)
        print(f"  [✓] Colección base creada en {default_file}")
    except Exception as e:
        print(f"  [!] Error creando colección base: {e}")

def main():
    print("=================================================================")
    print("      Configuración Automática de OBS Studio & Stream Overlays   ")
    print("=================================================================")

    cfg = load_config()
    server_port = int(cfg.get("port", 8000))
    overlay_url = get_overlay_url(server_port)

    obs_dirs = find_obs_config_dirs()
    if not obs_dirs:
        print("[!] No se encontró ningún directorio de configuración de OBS Studio.")
        return 0

    print(f"[*] Directorios de OBS detectados: {len(obs_dirs)}")
    last_port = 4455
    last_password = ""

    # 1. Configurar global.ini para activar WebSocket en todas las instalaciones de OBS
    for obs_dir in obs_dirs:
        print(f"[*] Procesando OBS en: {obs_dir}")
        p, pwd = configure_obs_global_ini(obs_dir)
        last_port = p
        last_password = pwd

    # 2. Sincronizar credenciales en config.json del Controller
    cfg_updates = {
        "obs_enabled": True,
        "obs_host": "localhost",
        "obs_port": last_port,
        "obs_password": last_password
    }
    save_config(cfg_updates)
    print(f"  [✓] Controller configurado para conectarse a OBS en localhost:{last_port}")

    # 3. Inyectar o actualizar capa Browser Source
    # Intentamos primero vía WebSocket si OBS está en ejecución
    ws_success = try_add_overlay_via_websocket(last_port, last_password, overlay_url)
    
    # Si OBS no está abierto o no respondió al socket, inyectamos en los archivos de escenas
    for obs_dir in obs_dirs:
        scenes_dir = obs_dir / "basic" / "scenes"
        create_default_scene_collection_if_needed(scenes_dir, overlay_url)
        json_files = list(scenes_dir.glob("*.json"))
        for jf in json_files:
            inject_overlay_into_scene_json(jf, overlay_url)

    print("\n=================================================================")
    print("✓ ¡OBS Studio y Overlays configurados con éxito a 0 clics!")
    print(f"  - WebSocket v5: Habilitado en puerto {last_port}")
    print(f"  - Capa agregada: '{OVERLAY_SOURCE_NAME}' ({overlay_url})")
    print("=================================================================\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
