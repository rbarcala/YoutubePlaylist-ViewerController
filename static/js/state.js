<script>
// ─── ESTADO Y NAVEGACIÓN ───
let config = {};
let currentView = 'menu';
let videoList = [];
let currentIndex = -1;
let currentPlaybackRate = 1.7;
let isMuted = true;
let viewerConnected = false;
let viewerWindow = null;

const channel = new BroadcastChannel('fondos_stream');
const myClientId = 'client_' + Math.random().toString(36).substring(2, 9) + '_' + Date.now();

function applySoundboardVolume(vol) {
  const num = parseInt(vol, 10);
  sbVolume = isNaN(num) ? 80 : Math.max(0, Math.min(100, num));
  const slider = document.getElementById('sbVolumeSlider');
  const text = document.getElementById('sbVolumeText');
  if (slider && !sbIsAdjustingVolume) slider.value = sbVolume;
  if (text) text.textContent = sbVolume + '%';
  const cfgSlider = document.getElementById('cfgSoundboardVolume');
  if (cfgSlider) cfgSlider.value = sbVolume;
  const cfgVal = document.getElementById('cfgSbVolVal');
  if (cfgVal) cfgVal.textContent = sbVolume + '%';
}

// Manejo del botón atrás (Android Go Back & Browser Back)
window.addEventListener('popstate', (e) => {
  if (e.state && e.state.view) {
    showView(e.state.view, false);
  } else {
    showView('menu', false);
  }
});

function navigateTo(viewName) {
  if (viewName === currentView) return;
  history.pushState({ view: viewName }, '', '#' + viewName);
  showView(viewName, false);
}

function showView(viewName, push = false) {
  if (viewName === 'live') viewName = 'obs';
  currentView = viewName;
  document.querySelectorAll('.view-container').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-pill').forEach(p => p.classList.remove('active'));

  const targetView = document.getElementById('view-' + viewName) || document.getElementById('view-menu');
  targetView.classList.add('active');

  const pill = document.getElementById('pill-' + viewName);
  if (pill) pill.classList.add('active');

  const backBtn = document.getElementById('btnBackHub');
  if (viewName === 'menu') {
    backBtn.style.display = 'none';
  } else {
    backBtn.style.display = 'inline-flex';
  }

  // Cargar datos según la vista
  if (viewName === 'fondos' && (!videoList || videoList.length === 0)) loadPlaylist();
  if (viewName === 'obs') {
    loadObsData();
    loadLiveData();
    if(typeof startObsPreviewLoop === 'function') startObsPreviewLoop();
  } else {
    if(typeof stopObsPreviewLoop === 'function') stopObsPreviewLoop();
  }
  if (viewName === 'spotify') loadSpotifyData();
  if (viewName === 'soundboard') loadSoundboardView();
  if (viewName === 'overlays') loadOverlaysView();

  // Si salimos de la vista de directo, silenciar para evitar audio en segundo plano
  if (viewName !== 'obs') {
    const iframe = document.getElementById('livePlayerIframe') || document.querySelector('#liveVideoContainer iframe');
    if (iframe && iframe.contentWindow) {
      iframe.contentWindow.postMessage(JSON.stringify({ event: 'command', func: 'mute', args: [] }), '*');
    }
  } else if (!liveIsMuted) {
    const iframe = document.getElementById('livePlayerIframe') || document.querySelector('#liveVideoContainer iframe');
    if (iframe && iframe.contentWindow) {
      iframe.contentWindow.postMessage(JSON.stringify({ event: 'command', func: 'unMute', args: [] }), '*');
    }
  }
}

// ─── INICIALIZACIÓN ───
async function initApp() {
  try {
    const res = await fetch('/api/config');
    config = await res.json();
    if (config.auto_focus_viewer !== undefined) {
      document.getElementById('cfgAutoFocusViewer').checked = config.auto_focus_viewer;
    }
    if (document.getElementById('cfgAutoOpenViewer')) {
      document.getElementById('cfgAutoOpenViewer').checked = Boolean(config.auto_open_viewer);
    }
    if (config.soundboard_volume !== undefined) {
      applySoundboardVolume(config.soundboard_volume);
    }
  } catch(e) {}

  // Verificar hash inicial en URL
  const hash = window.location.hash.replace('#', '');
  if (['fondos', 'obs', 'live', 'soundboard', 'overlays', 'spotify'].includes(hash)) {
    showView(hash === 'live' ? 'obs' : hash, false);
  } else {
    showView('menu', false);
  }

  initSSE();
  loadSavedPlaylists();
    populateOverlayCustomizationForm(config);
    updateHeaderHeight();
  initBroadcastChannel();
  loadPlaylist();
  loadObsData();
  loadSpotifyData();

  // SSE maneja Spotify en tiempo real, no necesitamos polling agresivo

  // Ticker de avance suave del slider de Spotify cada segundo
  setInterval(() => {
    if (spCurrentDurationMs > 0 && !spIsSeeking) {
      const playBtn = document.getElementById('spPlayBtn');
      if (playBtn && playBtn.textContent === '⏸') {
        spCurrentProgressMs += 1000;
        if (spCurrentProgressMs <= spCurrentDurationMs) {
          const curEl = document.getElementById('spTimeCurrent');
          const sliderEl = document.getElementById('spProgressSlider');
          if (curEl) curEl.textContent = formatDurationMs(spCurrentProgressMs);
          if (sliderEl) {
            sliderEl.value = Math.min(1000, Math.round((spCurrentProgressMs / spCurrentDurationMs) * 1000));
          }
        }
      }
    }
  }, 1000);
}

// ─── SINCRONIZACIÓN SSE (TIEMPO REAL ENTRE DISPOSITIVOS) ───
function initSSE() {
  const evtSource = new EventSource('/api/events');

  evtSource.addEventListener('sync_state', (e) => {
    try {
      const data = JSON.parse(e.data).data;
      if (!data) return;
      if (data.videoId) highlightActiveCard(data.videoId);
      if (data.title) document.getElementById('nowPlayingTitle').textContent = data.title;
      if (data.activeViewers !== undefined) setConnected(data.activeViewers > 0);
      if (data.playbackRate !== undefined) {
        currentPlaybackRate = parseFloat(data.playbackRate);
        const sl = document.getElementById('speedSlider');
        const tx = document.getElementById('speedValue');
        if (sl) sl.value = currentPlaybackRate;
        if (tx) tx.textContent = currentPlaybackRate.toFixed(1) + 'x';
      }
      if (data.muted !== undefined) {
        isMuted = Boolean(data.muted);
        const btn = document.getElementById('muteBtn');
        if (btn) {
          btn.textContent = isMuted ? 'Muted' : 'Unmuted';
          btn.classList.toggle('btn-accent', !isMuted);
        }
      }
      if (data.soundboard_volume !== undefined && !sbIsAdjustingVolume) {
        applySoundboardVolume(data.soundboard_volume);
      }
    } catch(err) {}
  });

  evtSource.addEventListener('play', (e) => {
    try {
      const data = JSON.parse(e.data).data;
      if (data.videoId) highlightActiveCard(data.videoId);
      if (data.title) document.getElementById('nowPlayingTitle').textContent = data.title;
    } catch(err) {}
  });

  evtSource.addEventListener('state', (e) => {
    try {
      const data = JSON.parse(e.data).data;
      if (data.playbackRate !== undefined) {
        currentPlaybackRate = parseFloat(data.playbackRate);
        const sl = document.getElementById('speedSlider');
        const tx = document.getElementById('speedValue');
        if (sl) sl.value = currentPlaybackRate;
        if (tx) tx.textContent = currentPlaybackRate.toFixed(1) + 'x';
      }
      if (data.muted !== undefined) {
        isMuted = Boolean(data.muted);
        const btn = document.getElementById('muteBtn');
        if (btn) {
          btn.textContent = isMuted ? 'Muted' : 'Unmuted';
          btn.classList.toggle('btn-accent', !isMuted);
        }
      }
      if (data.videoId) highlightActiveCard(data.videoId);
      if (data.title) document.getElementById('nowPlayingTitle').textContent = data.title;
    } catch(err) {}
  });

  // Volumen de la botonera en tiempo real
  evtSource.addEventListener('soundboard_volume', (e) => {
    try {
      const data = JSON.parse(e.data).data;
      if (data && data.volume !== undefined && data.clientId !== myClientId) {
        applySoundboardVolume(data.volume);
      }
    } catch(err) {}
  });

  // Sonido reproducido en vivo
  evtSource.addEventListener('soundboard_play', (e) => {
    try {
      const data = JSON.parse(e.data).data;
      if (data) {
        const npText = document.getElementById('sbNowPlayingText');
        if (npText) npText.textContent = '▶ ' + (data.title || 'Sonido');
        document.querySelectorAll('.sound-tile, .sound-card').forEach(c => {
          const matchMp3 = data.mp3 && c.dataset.mp3 === data.mp3;
          const cardTitle = c.querySelector('.sound-tile-title')?.textContent?.trim() || c.querySelector('.sound-name')?.textContent?.trim();
          const matchTitle = data.title && cardTitle === data.title.trim();
          if (matchMp3 || matchTitle) {
            c.classList.add('playing');
          } else {
            c.classList.remove('playing');
          }
        });
        if (playingResetTimer) clearTimeout(playingResetTimer);
        playingResetTimer = setTimeout(() => {
          document.querySelectorAll('.sound-tile, .sound-card').forEach(c => c.classList.remove('playing'));
          if (npText && npText.textContent.startsWith('▶')) npText.textContent = '⏹️ Listo / Silencio';
        }, 2200);
      }
    } catch(err) {}
  });

  // Sonido detenido
  evtSource.addEventListener('soundboard_stop', () => {
    try {
      const npText = document.getElementById('sbNowPlayingText');
      if (npText) npText.textContent = '⏹️ Detenido';
      document.querySelectorAll('.sound-tile, .sound-card').forEach(c => c.classList.remove('playing'));
    } catch(err) {}
  });

  // Favoritos actualizados
  evtSource.addEventListener('soundboard_favorites_updated', (e) => {
    try {
      const data = JSON.parse(e.data).data;
      if (data && data.favorites) {
        savedFavorites = data.favorites;
        if (currentSbTab === 'favorites') {
          renderSoundboardGrid(savedFavorites, false);
        } else {
          document.querySelectorAll('.sound-tile, .sound-card').forEach(card => {
            const btn = card.querySelector('.sound-tile-fav, .sound-fav-btn');
            const mp3 = card.dataset.mp3;
            if (btn && mp3) {
              const fav = savedFavorites.some(f => f.mp3 === mp3);
              btn.classList.toggle('is-fav', fav);
              btn.textContent = fav ? '★' : '☆';
            }
          });
        }
      }
    } catch(err) {}
  });

  // Sesión y cuenta de MyInstants vinculada
  evtSource.addEventListener('soundboard_auth_success', (e) => {
    try {
      const data = JSON.parse(e.data).data;
      if (data && data.username) {
        config.soundboard_username = data.username;
      }
      showToast(`¡Sesión de MyInstants vinculada como @${data.username || 'usuario'}! 🎉`);
      updateSoundboardAccountDisplay();
      loadSoundboardAuthStatus();
      if (currentSbTab === 'favorites') {
        loadSoundboardTab('favorites', 1);
      }
    } catch(err) {}
  });

  // Spotify sincronizado en tiempo real
  evtSource.addEventListener('spotify_volume', (e) => {
    try {
      const data = JSON.parse(e.data).data;
      if (data && data.volume !== undefined && data.clientId !== myClientId) {
        if (!spIsAdjustingVolume && Date.now() > spVolumeCooldownUntil) {
          const slider = document.getElementById('spVolumeSlider');
          const valText = document.getElementById('spVolumeValue');
          if (slider) slider.value = data.volume;
          if (valText) valText.textContent = data.volume + '%';
        }
      }
    } catch(err) {}
  });

  evtSource.addEventListener('spotify_action', () => {
    setTimeout(loadSpotifyData, 200);
  });

  evtSource.addEventListener('spotify_state', (e) => {
    try {
      const d = JSON.parse(e.data);
      const st = d.data || d;
      updateSpotifyPlayerUI(st);
    } catch(err) {}
  });

  // OBS actualizado
  evtSource.addEventListener('obs_updated', (e) => {
    try {
      const data = JSON.parse(e.data).data;
      if (data?.scene) highlightCurrentScene(data.scene);
    } catch(err) {}
  });
  evtSource.addEventListener('obs_scenes_list', (e) => {
    try {
      const data = JSON.parse(e.data).data;
      if (data?.scenes && data.scenes.length > 0) {
        renderObsScenesCards(data.scenes, lastKnownCurrentScene);
      }
    } catch(err) {}
  });
  evtSource.addEventListener('obs_status_changed', () => loadObsData());

  // OBS Audio & Vúmetros en tiempo real
  evtSource.addEventListener('obs_audio_levels', (e) => {
    try {
      const payload = JSON.parse(e.data).data;
      if (!payload || !payload.meters) return;
      const meters = payload.meters;

      // Desktop
      if (obsAudioInputs.desktop && meters[obsAudioInputs.desktop.name] !== undefined) {
        const val = meters[obsAudioInputs.desktop.name];
        const bar = document.getElementById('obsVuBarDesktop');
        if (bar) {
          const pct = Math.min(100, Math.round(val * 100));
          bar.style.width = pct + '%';
        }
      }

      // Mic/Aux
      if (obsAudioInputs.mic && meters[obsAudioInputs.mic.name] !== undefined) {
        const val = meters[obsAudioInputs.mic.name];
        const bar = document.getElementById('obsVuBarMic');
        if (bar) {
          const pct = Math.min(100, Math.round(val * 100));
          bar.style.width = pct + '%';
        }
      }
    } catch(err) {}
  });

  evtSource.addEventListener('obs_audio_changed', (e) => {
    try {
      const d = JSON.parse(e.data).data;
      if (!d) return;

      const inputName = d.input_name || d.inputName;
      let matchedType = null;
      if (obsAudioInputs.desktop && obsAudioInputs.desktop.name === inputName) matchedType = 'desktop';
      else if (obsAudioInputs.mic && obsAudioInputs.mic.name === inputName) matchedType = 'mic';

      if (matchedType) {
        if (d.inputMuted !== undefined || d.muted !== undefined) {
          const m = d.inputMuted !== undefined ? d.inputMuted : d.muted;
          obsAudioInputs[matchedType].muted = m;
        }
        if (d.inputVolumeMul !== undefined || d.volume_mul !== undefined) {
          const v = d.inputVolumeMul !== undefined ? d.inputVolumeMul : d.volume_mul;
          obsAudioInputs[matchedType].volume_mul = v;
          if (d.inputVolumeDb !== undefined) {
            obsAudioInputs[matchedType].volume_db = d.inputVolumeDb;
          } else if (v > 0.0001) {
            obsAudioInputs[matchedType].volume_db = 20 * Math.log10(v);
          } else {
            obsAudioInputs[matchedType].volume_db = -Infinity;
          }
        }
        updateObsAudioUI(matchedType, obsAudioInputs[matchedType]);
      } else {
        // Si no tenemos matcheado el inputName aún, recargamos la info completa
        loadObsAudioData();
      }
    } catch(err) {}
  });

  evtSource.addEventListener('viewer_ready', () => setConnected(true));

  // Temporizador y Overlays OBS
  evtSource.addEventListener('timer_update', (e) => {
    try {
      const data = JSON.parse(e.data).data;
      if (data) updateTimerUI(data);
    } catch(err) {}
  });

  evtSource.addEventListener('timer_finished', (e) => {
    try {
      const d = JSON.parse(e.data).data;
      updateTimerUI(d);
      updateStageOverlayView(currentStageScale);
    } catch(err) {}
    showToast('⏰ ¡El temporizador de recreo ha finalizado!');
    

  });
}

// ─── SINCRONIZACIÓN LOCAL (BroadcastChannel) ───
function initBroadcastChannel() {
  channel.onmessage = (e) => {
    const d = e.data;
    if (!d || d.clientId === myClientId) return;
    if (d.type === 'viewer_ready') setConnected(true);
    if (d.type === 'play' && d.videoId) highlightActiveCard(d.videoId);
    if (d.type === 'soundboard_volume' && d.volume !== undefined) {
      applySoundboardVolume(d.volume);
    }
    if (d.type === 'soundboard_play') {
      const npText = document.getElementById('sbNowPlayingText');
      if (npText) npText.textContent = '▶ ' + (d.title || 'Sonido');
    }
    if (d.type === 'soundboard_stop') {
      const npText = document.getElementById('sbNowPlayingText');
      if (npText) npText.textContent = '⏹️ Detenido';
      document.querySelectorAll('.sound-tile, .sound-card').forEach(c => c.classList.remove('playing'));
    }
    if (d.type === 'state') {
      if (d.playbackRate !== undefined) {
        currentPlaybackRate = parseFloat(d.playbackRate);
        const sl = document.getElementById('speedSlider');
        const tx = document.getElementById('speedValue');
        if (sl) sl.value = currentPlaybackRate;
        if (tx) tx.textContent = currentPlaybackRate.toFixed(1) + 'x';
      }
      if (d.muted !== undefined) {
        isMuted = Boolean(d.muted);
        const btn = document.getElementById('muteBtn');
        if (btn) {
          btn.textContent = isMuted ? 'Muted' : 'Unmuted';
          btn.classList.toggle('btn-accent', !isMuted);
        }
      }
    }
  };
}

