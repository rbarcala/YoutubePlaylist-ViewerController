from flask import Blueprint, request, jsonify
import time
import threading

timer_bp = Blueprint('timer', __name__)

# Variables que se inyectan desde server.py
load_config = None
save_config = None
broadcast_event = None

# Estado del timer
timer_state = {
    'running': False,
    'paused': False,
    'start_time': 0,
    'elapsed': 0,
    'mode': 'countup',  # 'countup' o 'countdown'
    'target_time': 0,
    'live_text': '',
    'phrases': []
}
timer_lock = threading.Lock()

def init_timer_routes(config_loader, config_saver, broadcast_fn):
    global load_config, save_config, broadcast_event
    load_config = config_loader
    save_config = config_saver
    broadcast_event = broadcast_fn
    
    # Cargar frases guardadas
    cfg = load_config()
    with timer_lock:
        timer_state['phrases'] = cfg.get('timer_phrases', [])


def _emit_timer_state():
    if broadcast_event:
        with timer_lock:
            state = timer_state.copy()
            if state['running'] and not state['paused']:
                if state['mode'] == 'countup':
                    state['display'] = state['elapsed'] + (time.time() - state['start_time'])
                else:
                    remaining = state['target_time'] - (state['elapsed'] + (time.time() - state['start_time']))
                    state['display'] = max(0, remaining)
            else:
                state['display'] = state['elapsed']
        broadcast_event('timer_state', state)


@timer_bp.route('/api/timer/status')
def timer_status():
    with timer_lock:
        state = timer_state.copy()
        if state['running'] and not state['paused']:
            if state['mode'] == 'countup':
                state['display'] = state['elapsed'] + (time.time() - state['start_time'])
            else:
                remaining = state['target_time'] - (state['elapsed'] + (time.time() - state['start_time']))
                state['display'] = max(0, remaining)
        else:
            state['display'] = state['elapsed']
    return jsonify(state)


@timer_bp.route('/api/timer/start', methods=['POST'])
def timer_start():
    data = request.get_json() or {}
    mode = data.get('mode', 'countup')
    target = data.get('target_time', 0)
    
    with timer_lock:
        timer_state['running'] = True
        timer_state['paused'] = False
        timer_state['mode'] = mode
        timer_state['target_time'] = target
        timer_state['start_time'] = time.time()
        if mode == 'countup':
            timer_state['elapsed'] = 0
        else:
            timer_state['elapsed'] = 0
    
    _emit_timer_state()
    return jsonify({'ok': True})


@timer_bp.route('/api/timer/add', methods=['POST'])
def timer_add():
    data = request.get_json() or {}
    seconds = data.get('seconds', 0)
    
    with timer_lock:
        if timer_state['running'] and not timer_state['paused']:
            now = time.time()
            timer_state['elapsed'] += now - timer_state['start_time']
            timer_state['start_time'] = now
        timer_state['elapsed'] += seconds
        if timer_state['mode'] == 'countdown':
            timer_state['target_time'] += seconds
    
    _emit_timer_state()
    return jsonify({'ok': True})


@timer_bp.route('/api/timer/pause', methods=['POST'])
def timer_pause():
    with timer_lock:
        if timer_state['running'] and not timer_state['paused']:
            now = time.time()
            timer_state['elapsed'] += now - timer_state['start_time']
            timer_state['paused'] = True
        elif timer_state['running'] and timer_state['paused']:
            timer_state['paused'] = False
            timer_state['start_time'] = time.time()
    
    _emit_timer_state()
    return jsonify({'ok': True})


@timer_bp.route('/api/timer/stop', methods=['POST'])
def timer_stop():
    with timer_lock:
        timer_state['running'] = False
        timer_state['paused'] = False
        timer_state['elapsed'] = 0
    
    _emit_timer_state()
    return jsonify({'ok': True})


@timer_bp.route('/api/timer/live_text', methods=['POST'])
def timer_set_live_text():
    data = request.get_json() or {}
    text = data.get('text', '')
    
    with timer_lock:
        timer_state['live_text'] = text
    
    if broadcast_event:
        broadcast_event('timer_live_text', {'text': text})
    return jsonify({'ok': True})


@timer_bp.route('/api/timer/phrases', methods=['GET'])
def timer_get_phrases():
    with timer_lock:
        return jsonify({'phrases': timer_state['phrases']})


@timer_bp.route('/api/timer/phrases/add', methods=['POST'])
def timer_add_phrase():
    data = request.get_json() or {}
    phrase = data.get('phrase', '').strip()
    if not phrase:
        return jsonify({'ok': False, 'error': 'Frase vacía'}), 400
    
    with timer_lock:
        if phrase not in timer_state['phrases']:
            timer_state['phrases'].append(phrase)
            cfg = load_config()
            cfg['timer_phrases'] = timer_state['phrases']
            save_config(cfg)
    
    return jsonify({'ok': True})


@timer_bp.route('/api/timer/phrases/remove', methods=['POST'])
def timer_remove_phrase():
    data = request.get_json() or {}
    phrase = data.get('phrase', '')
    
    with timer_lock:
        if phrase in timer_state['phrases']:
            timer_state['phrases'].remove(phrase)
            cfg = load_config()
            cfg['timer_phrases'] = timer_state['phrases']
            save_config(cfg)
    
    return jsonify({'ok': True})