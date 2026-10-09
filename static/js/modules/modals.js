// ─── APERTURA DE VENTANAS Y UTILIDADES ───
let isOpeningViewer = false;
function openViewer() {
  if (viewerConnected) {
    fetch('/api/focus_viewer', { method: 'POST' }).catch(() => {});
    if (viewerWindow) {
      try { viewerWindow.focus(); } catch(e) {}
    }
    showToast('Viewer ya conectado — Enfocando 📺');
    return;
  }
  if (isOpeningViewer) return;
  isOpeningViewer = true;
  setTimeout(() => { isOpeningViewer = false; }, 2500);

  fetch('/api/open_viewer', { method: 'POST' })
    .then(r => r.json())
    .then(res => {
      if (res && res.action === 'focused_existing_viewer') {
        showToast('Viewer ya abierto — Enfocado 📺');
      } else {
        showToast('Viewer abierto en navegador 📺');
      }
    })
    .catch(() => {
      showToast('Error al abrir Viewer');
    });
}

function openWebController() {
  window.open('/controller.html', '_blank');
}

function setConnected(val) {
  viewerConnected = Boolean(val);
  const dot = document.getElementById('viewerStatusDot');
  dot.textContent = viewerConnected ? 'Viewer conectado' : 'Sin viewer';
  dot.className = 'status-dot' + (viewerConnected ? ' connected' : '');
}

function showToast(msg) {
  const t = document.getElementById('toastNotice');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2600);
}

// ─── MODAL AJUSTES ───
function openSettingsModal() {
  document.getElementById('cfgApiKey').value = config.youtube_api_key || '';
  document.getElementById('cfgPlaylistId').value = config.playlist_id || '';
  document.getElementById('cfgChannelId').value = config.youtube_channel_id || '';
  document.getElementById('cfgAutoFocusViewer').checked = config.auto_focus_viewer !== false;
  document.getElementById('cfgAutoOpenViewer').checked = config.auto_open_viewer === true;
  document.getElementById('cfgVideoPlaybackMode').value = config.video_playback_mode || 'original';
  document.getElementById('cfgOverlayEnabled').checked = config.overlay_enabled !== false;
  document.getElementById('cfgShowLyrics').checked = config.overlay_show_lyrics !== false;
  document.getElementById('cfgSpotifyClientId').value = config.spotify_client_id || '';
  document.getElementById('cfgSpotifyClientSecret').value = config.spotify_client_secret || '';
  const secretSavedBadge = document.getElementById('cfgSpotifySecretSavedStatus');
  if (secretSavedBadge) {
    secretSavedBadge.style.display = (config.has_spotify_secret || config.spotify_client_secret) ? 'inline' : 'none';
  }

  document.getElementById('cfgObsEnabled').checked = Boolean(config.obs_enabled);
  document.getElementById('cfgAutoOpenObs').checked = config.auto_open_obs !== false;
  document.getElementById('cfgObsHost').value = config.obs_host || 'localhost';
  document.getElementById('cfgObsPort').value = config.obs_port || 4455;
  document.getElementById('cfgObsPassword').value = config.obs_password || '';

  document.getElementById('cfgSoundboardUsername').value = config.soundboard_username || '';
  const sbVol = config.soundboard_volume !== undefined ? config.soundboard_volume : 80;
  document.getElementById('cfgSoundboardVolume').value = sbVol;
  document.getElementById('cfgSbVolVal').textContent = sbVol + '%';

  document.getElementById('settingsModal').classList.add('active');
}

function closeSettingsModal() {
  document.getElementById('settingsModal').classList.remove('active');
}

async function saveSettings() {
  let pl = document.getElementById('cfgPlaylistId').value.trim();
  const listMatch = pl.match(/[?&]list=([a-zA-Z0-9_-]+)/);
  if (listMatch) {
    pl = listMatch[1];
  }

  const payload = {
    youtube_api_key: document.getElementById('cfgApiKey').value.trim(),
    playlist_id: pl,
    youtube_channel_id: document.getElementById('cfgChannelId').value.trim(),
    auto_focus_viewer: document.getElementById('cfgAutoFocusViewer').checked,
    auto_open_viewer: document.getElementById('cfgAutoOpenViewer').checked,
    video_playback_mode: document.getElementById('cfgVideoPlaybackMode').value,
    overlay_enabled: document.getElementById('cfgOverlayEnabled').checked,
    overlay_show_lyrics: document.getElementById('cfgShowLyrics').checked,
    spotify_client_id: document.getElementById('cfgSpotifyClientId').value.trim(),
    obs_enabled: document.getElementById('cfgObsEnabled').checked,
    auto_open_obs: document.getElementById('cfgAutoOpenObs').checked,
    obs_host: document.getElementById('cfgObsHost').value.trim(),
    obs_port: parseInt(document.getElementById('cfgObsPort').value),
    obs_password: document.getElementById('cfgObsPassword').value,
    soundboard_username: document.getElementById('cfgSoundboardUsername').value.trim(),
    soundboard_volume: isNaN(parseInt(document.getElementById('cfgSoundboardVolume').value, 10)) ? 80 : Math.max(0, Math.min(100, parseInt(document.getElementById('cfgSoundboardVolume').value, 10)))
  };

  const secretVal = document.getElementById('cfgSpotifyClientSecret').value.trim();
  if (secretVal) {
    payload.spotify_client_secret = secretVal;
  }

  const res = await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  config = data.config;
  closeSettingsModal();
  showToast('Configuración guardada ✓');
  loadPlaylist();
  loadObsData();
  updateSoundboardAccountDisplay();
}

// ─── MODAL QR ───
let currentLanUrl = '';
async function openQRModal() {
  document.getElementById('qrModal').classList.add('active');
  try {
    const res = await fetch('/api/network_info');
    const data = await res.json();
    currentLanUrl = data.controller_url;
    document.getElementById('qrLanUrl').textContent = data.controller_url;
    document.getElementById('qrCodeContainer').innerHTML = data.qr_code_svg;
    
    // Extraer los últimos dígitos de la IP local para la app móvil
    const ip = data.lan_ip || '';
    const parts = ip.split('.');
    const lastDigits = parts.length > 0 ? parts[parts.length - 1] : ip;
    const quickDigitsEl = document.getElementById('qrQuickDigits');
    if (quickDigitsEl) {
      quickDigitsEl.textContent = lastDigits || ip;
    }
  } catch(e) {
    document.getElementById('qrLanUrl').textContent = window.location.href;
    const quickDigitsEl = document.getElementById('qrQuickDigits');
    if (quickDigitsEl) {
      quickDigitsEl.textContent = '8000';
    }
  }
}

function closeQRModal() {
  document.getElementById('qrModal').classList.remove('active');
}

function copyLanUrl() {
  navigator.clipboard.writeText(currentLanUrl || window.location.href).then(() => {
    showToast('Enlace copiado al portapapeles');
  });
}

