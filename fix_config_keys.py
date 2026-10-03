with open('config_manager.py', 'r', encoding='utf-8') as f:
    code = f.read()

old_keys = '''    "overlay_enabled": True,
    "overlay_now_playing": True,
    "overlay_now_playing_pos": "bottom-left",'''

new_keys = '''    "overlay_enabled": True,
    "overlay_timer_enabled": True,
    "overlay_now_playing_enabled": True,
    "overlay_source_mode": "both",
    "overlay_now_playing": True,
    "overlay_now_playing_pos": "bottom-left",'''

code = code.replace(old_keys, new_keys)

with open('config_manager.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("config_manager.py updated.")
