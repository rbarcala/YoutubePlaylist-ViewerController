#!/usr/bin/env python3
"""
playlist.py — Punto de entrada modular para el Gestor de Playlist de YouTube.

Utiliza el servicio `services.playlist_manager.YouTubePlaylistManager` integrado
en el Controller web (`http://localhost:8000/controller.html#fondos`) para:
  - Ver y administrar únicamente los nuevos videos agregados por el usuario (abajo del todo).
  - Borrar videos agregados por el usuario directamente en YouTube.
  - Cambiar manualmente la posición de un video sin alterar el orden original del resto de la playlist.
  - Agregar nuevos videos al final de la playlist.
"""

import argparse
import sys
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from services.config_manager import load_config, save_config
from services.playlist_manager import (
    YouTubePlaylistManager,
    extract_playlist_id,
    launch_interactive_google_login,
)


def print_editable_videos(details: dict) -> None:
    items = details.get("items", [])
    editable = [it for it in items if it.get("canDelete")]
    print(f"\nPlaylist: {details.get('title')} ({details.get('playlistId')})")
    print(f"Total en playlist: {details.get('total')} videos | Administrables por vos: {len(editable)}")
    print("-" * 80)
    if not editable:
        print("  No hay videos agregados por tu cuenta actual en esta playlist.")
    else:
        for it in editable:
            dur = it.get("duration") or "--:--"
            title = (it.get("title") or "Sin título")[:50]
            print(f"  Pos #{it['index']:3d} | [{dur:>7}] {title:<50} | ID: {it['videoId']}")
    print("-" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Gestor manual de nuevos videos en la Playlist de YouTube (integrado al Controller)."
    )
    parser.add_argument("playlist", nargs="?", default="", help="URL o ID de la playlist de YouTube")
    parser.add_argument("--web", action="store_true", help="Abrir el Gestor de Playlist en la interfaz web del Controller")
    parser.add_argument("--login", action="store_true", help="Iniciar sesión de Google interactivamente")
    parser.add_argument("--add", default="", help="URL o ID de un video para agregar al final de la playlist")
    parser.add_argument("--remove-pos", type=int, default=0, help="Borrar el video en la posición # indicada (solo videos propios)")
    parser.add_argument("--move", nargs=2, metavar=("FROM_POS", "TO_POS"), type=int, help="Mover manualmente el video de FROM_POS a TO_POS")

    args = parser.parse_args()
    cfg = load_config()
    mgr = YouTubePlaylistManager(load_config, save_config)

    if args.login:
        print("[*] Abriendo ventana de inicio de sesión de Google...")
        cookie_path = launch_interactive_google_login()
        if not cookie_path:
            sys.exit("[!] No se completó el inicio de sesión.")
        print("[✓] Sesión de Google vinculada correctamente.")

    if args.web:
        port = cfg.get("port", 8000)
        url = f"http://localhost:{port}/controller.html#fondos"
        print(f"[*] Abriendo Gestor de Playlist en el Controller: {url}")
        webbrowser.open(url)
        return

    pid = extract_playlist_id(args.playlist or cfg.get("playlist_id", ""))
    if not pid:
        sys.exit("[!] Especificá el ID o URL de la playlist o configuralo en el Controller.")

    details = mgr.get_playlist(pid, force_refresh=True)

    if args.add:
        res = mgr.add_video(pid, args.add)
        print(f"[✓] Video {res['videoId']} agregado al final de la playlist.")
        print_editable_videos(res["playlist"])
        return

    if args.remove_pos:
        target = next((it for it in details["items"] if it["index"] == args.remove_pos), None)
        if not target:
            sys.exit(f"[!] No existe ningún video en la posición #{args.remove_pos}.")
        if not target.get("canDelete"):
            sys.exit(f"[!] El video en la posición #{args.remove_pos} no fue agregado por tu cuenta y está protegido.")
        res = mgr.remove_video(pid, target["setVideoId"], target["videoId"])
        print(f"[✓] Video '{target['title']}' eliminado de la playlist.")
        print_editable_videos(res["playlist"])
        return

    if args.move:
        from_pos, to_pos = args.move
        target = next((it for it in details["items"] if it["index"] == from_pos), None)
        if not target:
            sys.exit(f"[!] No existe ningún video en la posición #{from_pos}.")
        if not target.get("canDelete"):
            sys.exit(f"[!] Solo podés administrar los videos agregados por vos (#{from_pos} está fijo).")
        res = mgr.move_video(pid, target["setVideoId"], to_pos - 1)
        print(f"[✓] Video '{target['title']}' movido manualmente a la posición #{res['newIndex']}.")
        print_editable_videos(res["playlist"])
        return

    print_editable_videos(details)
    port = cfg.get("port", 8000)
    print(f"\n💡 Para administrar visualmente desde la web, abrí el Controller en:")
    print(f"   http://localhost:{port}/controller.html#fondos  (botón '🛠️ Administrar Playlist')")


if __name__ == "__main__":
    main()
