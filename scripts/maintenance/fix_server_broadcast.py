with open('server.py', 'r', encoding='utf-8') as f:
    code = f.read()

old_broadcast = '''        saved = save_config(new_data)
        broadcast_event("config_updated", {
            "playlist_id": saved.get("playlist_id"),
            "has_api_key": bool(saved.get("youtube_api_key")),
            "obs_enabled": saved.get("obs_enabled"),
            "auto_focus_viewer": saved.get("auto_focus_viewer", True),
            "overlay_enabled": saved.get("overlay_enabled", True)
        })'''

new_broadcast = '''        saved = save_config(new_data)
        safe_broadcast = saved.copy()
        safe_broadcast.pop("youtube_api_key", None)
        safe_broadcast.pop("spotify_client_secret", None)
        safe_broadcast.pop("spotify_access_token", None)
        safe_broadcast.pop("spotify_refresh_token", None)
        broadcast_event("config_updated", safe_broadcast)'''

code = code.replace(old_broadcast, new_broadcast)

with open('server.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("server.py updated to broadcast all configuration updates.")
