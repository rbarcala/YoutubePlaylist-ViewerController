import os
import sys
import subprocess
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def check_and_install_dependencies(app_dir: Path) -> bool:
    """
    Verifica e instala dependencias del sistema (APT) y de Python (pip).
    Returns True si todo está OK, False si hubo errores críticos.
    """
    # 1. Verificar dependencias APT
    missing_apt = []
    for pkg in ('python3-pyqt5', 'python3-pyqt5.qtwebengine', 
                'python3-flask', 'python3-requests', 'yt-dlp', 'playerctl'):
        try:
            subprocess.run(['dpkg', '-s', pkg], 
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except subprocess.CalledProcessError:
            missing_apt.append(pkg)
    
    if missing_apt:
        logger.info(f"[env] Instalando paquetes APT faltantes: {' '.join(missing_apt)}")
        try:
            if shutil.which('pkexec'):
                subprocess.run(['pkexec', 'apt-get', 'install', '-y'] + missing_apt, check=True)
            else:
                subprocess.run(['sudo', 'apt-get', 'install', '-y'] + missing_apt, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"[env] Error instalando dependencias APT: {e}")
            return False
    
    # 2. Verificar dependencias pip en el venv
    venv_python = _get_venv_python(app_dir)
    if venv_python:
        req_file = app_dir / 'requirements.txt'
        if req_file.exists():
            try:
                subprocess.run([str(venv_python), '-m', 'pip', 'install', '-q', '-r', str(req_file)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            except subprocess.CalledProcessError as e:
                logger.warning(f"[env] Advertencia: error instalando dependencias pip: {e}")
    
    return True


def _get_venv_python(app_dir: Path) -> Path | None:
    """Detecta el ejecutable de Python del entorno virtual."""
    candidates = [
        app_dir / 'venv' / 'bin' / 'python',
        app_dir / '.venv' / 'bin' / 'python',
        Path.home() / '.local' / 'share' / 'youtube-stream-controller' / 'venv' / 'bin' / 'python',
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def ensure_v4l2loopback() -> bool:
    """
    Configura el módulo v4l2loopback para la cámara virtual de OBS.
    Returns True si ya está configurado o se configuró correctamente.
    """
    modprobe_conf = Path('/etc/modules-load.d/obs-v4l2loopback.conf')
    if modprobe_conf.exists():
        return True
    
    logger.info("[env] Configurando v4l2loopback para cámara virtual de OBS...")
    script_path = Path(__file__).parent.parent / 'scripts' / 'setup_v4l2.sh'
    if not script_path.exists():
        logger.warning("[env] Script setup_v4l2.sh no encontrado")
        return False
    
    try:
        if shutil.which('pkexec'):
            subprocess.run(['pkexec', 'bash', str(script_path)], check=True)
        else:
            subprocess.run(['sudo', 'bash', str(script_path)], check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"[env] Error configurando v4l2loopback: {e}")
        return False


def find_obs_command() -> list[str] | None:
    """Encuentra el comando adecuado para iniciar OBS Studio."""
    if shutil.which('obs'):
        return ['obs']
    if shutil.which('flatpak') and _flatpak_installed('com.obsproject.Studio'):
        return ['flatpak', 'run', 'com.obsproject.Studio']
    if shutil.which('snap') and _snap_installed('obs-studio'):
        return ['snap', 'run', 'obs-studio']
    return None


def _flatpak_installed(app_id: str) -> bool:
    try:
        result = subprocess.run(['flatpak', 'list', '--app'], 
                               capture_output=True, text=True, check=True)
        return app_id in result.stdout
    except subprocess.CalledProcessError:
        return False


def _snap_installed(snap_name: str) -> bool:
    try:
        result = subprocess.run(['snap', 'list'], 
                               capture_output=True, text=True, check=True)
        return snap_name in result.stdout
    except subprocess.CalledProcessError:
        return False


def is_obs_running() -> bool:
    """Verifica si OBS Studio ya se encuentra en ejecución."""
    try:
        current_pid = os.getpid()
        result = subprocess.run(['pgrep', '-x', 'obs'], 
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        pids = result.stdout.strip().split()
        return any(pid != str(current_pid) for pid in pids)
    except Exception:
        return False


def launch_obs_if_needed(cfg: dict, app_dir: Path) -> bool:
    """Lanza OBS Studio si no está en ejecución y configura overlay."""
    if not cfg.get("auto_open_obs", True):
        return True
    
    # Asegurar módulo de cámara virtual antes de abrir OBS
    ensure_v4l2loopback()
    
    if is_obs_running():
        logger.info("[env] OBS Studio ya se encuentra en ejecución.")
        return True
    
    cmd = find_obs_command()
    if not cmd:
        logger.warning("[env] OBS Studio no encontrado en el sistema.")
        return False
    
    logger.info(f"[env] Abriendo OBS Studio automáticamente ({' '.join(cmd)})...")
    try:
        import time
        import threading
        import sys
        
        subprocess.Popen(cmd, start_new_session=True)
        
        # Sincronizar overlay con OBS después de que inicie
        def _sync_obs_overlay():
            time.sleep(3)
            setup_script = app_dir / "scripts" / "setup_obs.py"
            if setup_script.exists():
                for attempt in range(5):
                    result = subprocess.run(
                        [sys.executable, str(setup_script)],
                        cwd=str(app_dir),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                    if result.returncode == 0 and "conectada vía WebSocket" in result.stdout:
                        logger.info("[env] Overlay sincronizado con OBS.")
                        break
                    if result.stdout:
                        logger.debug(f"[env] Intento {attempt + 1} de sincronización OBS:\n{result.stdout.strip()}")
                    time.sleep(2)
            
            # Iniciar automáticamente la cámara virtual de OBS
            try:
                from services.obs_client import OBSController
                obs = OBSController(
                    host=cfg.get("obs_host", "localhost"),
                    port=cfg.get("obs_port", 4455),
                    password=cfg.get("obs_password", "")
                )
                res_vcam = obs.start_virtual_cam()
                if res_vcam.get("success"):
                    logger.info("[env] Cámara virtual de OBS iniciada automáticamente ✓")
            except Exception as ex_vcam:
                logger.warning(f"[env] Aviso al iniciar cámara virtual: {ex_vcam}")
        
        threading.Thread(target=_sync_obs_overlay, daemon=True).start()
        return True
    except Exception as e:
        logger.error(f"[env] Error lanzando OBS: {e}")
        return False


def find_spotify_command() -> list[str] | None:
    """Encuentra el comando adecuado para iniciar Spotify."""
    if shutil.which("spotify"):
        return ["spotify"]
    if shutil.which("flatpak") and _flatpak_installed("com.spotify.Client"):
        return ["flatpak", "run", "com.spotify.Client"]
    if os.path.isfile("/snap/bin/spotify"):
        return ["/snap/bin/spotify"]
    return None


def is_spotify_running() -> bool:
    """Verifica si Spotify ya se encuentra en ejecución."""
    try:
        res = subprocess.run(['pgrep', '-x', 'spotify'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        res2 = subprocess.run(['pgrep', '-f', 'spotify'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        return bool(res.stdout.strip() or res2.stdout.strip())
    except Exception:
        return False


def launch_spotify_if_needed():
    """Inicia Spotify en segundo plano si no está en ejecución."""
    if is_spotify_running():
        logger.info("[env] Spotify ya se encuentra en ejecución.")
        return
    
    cmd = find_spotify_command()
    if not cmd:
        logger.warning("[env] Spotify no encontrado en el sistema.")
        return
    
    logger.info(f"[env] Abriendo Spotify automáticamente ({' '.join(cmd)})...")
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.error(f"[env] Error al abrir Spotify: {e}")