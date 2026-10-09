from flask import Blueprint, request, jsonify

timer_bp = Blueprint('timer', __name__)

# Variables que se inyectan desde server.py
overlay_mgr = None
load_config = None
save_config = None


def init_timer_routes(overlay_manager_inst, config_loader=None, config_saver=None):
    global overlay_mgr, load_config, save_config
    overlay_mgr = overlay_manager_inst
    load_config = config_loader
    save_config = config_saver


@timer_bp.route('/api/timer/status')
def timer_status():
    if not overlay_mgr:
        return jsonify({"active": False, "running": False})
    return jsonify(overlay_mgr.get_status())


@timer_bp.route('/api/timer/start', methods=['POST'])
def timer_start():
    data = request.get_json(force=True, silent=True) or {}
    duration = int(data.get('duration') or data.get('seconds') or 300)
    title = data.get('title', 'Ya Vuelvo')
    phrase = data.get('phrase', '')
    play_sound = data.get('play_sound', True)

    state = overlay_mgr.start_timer(duration=duration, title=title, phrase=phrase, play_sound=play_sound)

    if load_config and save_config:
        cfg = load_config()
        cfg["timer_default_title"] = title.strip()
        cfg["timer_default_phrase"] = phrase.strip()
        save_config(cfg)

    return jsonify({"success": True, "state": state})


@timer_bp.route('/api/timer/add', methods=['POST'])
def timer_add():
    data = request.get_json(force=True, silent=True) or {}
    duration = int(data.get('duration') or data.get('seconds') or 60)
    state = overlay_mgr.add_timer(duration)
    return jsonify({"success": True, "state": state})


@timer_bp.route('/api/timer/pause', methods=['POST'])
def timer_pause():
    state = overlay_mgr.pause_timer()
    return jsonify({"success": True, "state": state})


@timer_bp.route('/api/timer/stop', methods=['POST'])
def timer_stop():
    state = overlay_mgr.stop_timer()
    return jsonify({"success": True, "state": state})


@timer_bp.route('/api/timer/live_text', methods=['POST'])
@timer_bp.route('/api/timer/phrase', methods=['POST'])
def timer_set_live_text():
    data = request.get_json(force=True, silent=True) or {}
    title = data.get('title')
    phrase = data.get('phrase')
    state = overlay_mgr.set_live_text(title=title, phrase=phrase)

    if load_config and save_config:
        cfg = load_config()
        if title is not None:
            cfg["timer_default_title"] = title.strip()
        if phrase is not None:
            cfg["timer_default_phrase"] = phrase.strip()
        save_config(cfg)

    return jsonify({"success": True, "state": state})


@timer_bp.route('/api/timer/phrases', methods=['GET'])
def timer_get_phrases():
    return jsonify({"phrases": overlay_mgr.get_phrases()})


@timer_bp.route('/api/timer/phrases/add', methods=['POST'])
def timer_add_phrase():
    data = request.get_json(force=True, silent=True) or {}
    phrase = data.get('phrase', '').strip()
    if not phrase:
        return jsonify({"success": False, "error": "Frase requerida"}), 400
    phrases = overlay_mgr.add_phrase(phrase)
    return jsonify({"success": True, "phrases": phrases})


@timer_bp.route('/api/timer/phrases/remove', methods=['POST'])
def timer_remove_phrase():
    data = request.get_json(force=True, silent=True) or {}
    phrase = data.get('phrase', '').strip()
    phrases = overlay_mgr.remove_phrase(phrase)
    return jsonify({"success": True, "phrases": phrases})