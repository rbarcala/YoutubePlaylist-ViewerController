// ─── 1. FONDOS STREAM LOGIC ───
async function loadPlaylist() {
  const loading = document.getElementById('loadingVideos');
  if (loading) {
    loading.style.display = 'block';
    loading.innerHTML = '<div class="spinner"></div><p style="margin-top:10px; color:var(--muted); font-size:13px;">Cargando lista de fondos...</p>';
  }

  const playlistId = config.playlist_id || "PL7E8lrk1ePfZVWMM2vsUkpQ6vbpbHi4G_";
  videoList = [];

  // 1. Cargar directamente desde el servidor local (usa la API Key segura guardada en el backend o yt-dlp)
  try {
    const res = await fetch(`/api/youtube/playlist?playlist_id=${encodeURIComponent(playlistId)}`);
    const data = await res.json();
    const rawList = data.items || data.videos || [];
    if (Array.isArray(rawList) && rawList.length > 0) {
      videoList = rawList.map(v => ({
        videoId: v.videoId || v.id,
        title: v.title || 'Video sin título',
        thumb: v.thumb || v.thumbnail || '',
        duration: v.duration || ''
      })).filter(v => v.videoId && v.thumb);

      if (videoList.length > 0) {
        if (config.last_played_video_id) {
          currentPlayingVideoId = config.last_played_video_id;
          const npTitle = document.getElementById('nowPlayingTitle');
          if (npTitle && config.last_played_title && (npTitle.textContent === '—' || !npTitle.textContent)) {
            npTitle.textContent = config.last_played_title;
          }
        }
        renderVideosGrid();
        if (loading) loading.style.display = 'none';
        return;
      }
    }
    if (data.error) {
      console.warn("Backend reportó error al cargar playlist:", data.error);
    }
  } catch (backendErr) {
    console.warn("Fallo cargando playlist por backend:", backendErr);
  }

  // 2. Si no se cargaron videos, verificar si es porque falta la API Key
  const hasKey = Boolean(config.has_api_key || config.youtube_api_key);
  if (!hasKey) {
    if (loading) {
      loading.innerHTML = `
        <p style="color:var(--accent); margin-bottom:10px;">⚠️ Falta configurar tu YouTube Data API v3 Key para ver los fondos o no se pudo cargar la playlist.</p>
        <button class="btn btn-accent" onclick="openSettingsModal()">⚙️ Configurar API Key</button>
      `;
    }
    return;
  }

  // Si tiene API Key guardada pero falló por algún otro motivo
  if (loading) {
    loading.innerHTML = `
      <p style="color:var(--accent); margin-bottom:10px;">⚠️ No se pudo cargar la playlist. Verifica tu conexión o el ID de la playlist.</p>
      <button class="btn btn-accent" onclick="loadPlaylist()">🔄 Reintentar</button>
    `;
  }
}

let currentFilterVideos = [];
let renderedVideosCount = 0;
const VIDEOS_PAGE_SIZE = 36;
let videosObserver = null;
let currentPlayingVideoId = config.last_played_video_id || '';
let fondosearchInitialized = false;

function initFondosSearch() {
  if (fondosearchInitialized) return;
  const searchInput = document.getElementById('searchInput');
  if (searchInput) {
    let debounceTimer = null;
    searchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        renderVideosGrid(true);
      }, 120);
    });
    fondosearchInitialized = true;
  }
}

function renderVideosGrid(reset = true) {
  initFondosSearch();
  const grid = document.getElementById('gridVideos');
  if (!grid) return;

  if (reset) {
    const query = (document.getElementById('searchInput')?.value || '').trim().toLowerCase();
    if (query) {
      currentFilterVideos = videoList.filter(v => (v.title || '').toLowerCase().includes(query));
    } else {
      currentFilterVideos = [...videoList];
    }

    const badge = document.getElementById('videoCountBadge');
    if (badge) {
      badge.textContent = query 
        ? `${currentFilterVideos.length} / ${videoList.length}` 
        : `${videoList.length} videos`;
    }

    grid.innerHTML = '';
    renderedVideosCount = 0;

    if (currentFilterVideos.length === 0) {
      grid.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 48px 20px; color: var(--muted); font-size: 13px;">No se encontraron videos con ese nombre.</div>';
      return;
    }
  }

  renderNextVideosBatch();
}

function renderNextVideosBatch() {
  const grid = document.getElementById('gridVideos');
  if (!grid) return;

  const fragment = document.createDocumentFragment();
  for (let i = 0; i < currentFilterVideos.length; i++) {
    const v = currentFilterVideos[i];
    const card = document.createElement('div');
    const isPlaying = v.videoId === currentPlayingVideoId;
    card.className = 'video-card' + (isPlaying ? ' active' : '');
    card.dataset.videoId = v.videoId;
    const durationHtml = v.duration ? `<span class="duration-badge">${v.duration}</span>` : '';
    card.innerHTML = `
      <div class="thumb-wrap">
        <img src="${v.thumb}" alt="${(v.title || '').replace(/"/g, '&quot;')}" loading="lazy" decoding="async">
        ${durationHtml}
      </div>
      <div class="video-card-info">
        <p>${v.title || 'Video sin título'}</p>
      </div>
    `;
    card.onclick = () => playVideo(v);
    fragment.appendChild(card);
  }

  const oldSentinel = document.getElementById('videosSentinel');
  if (oldSentinel) oldSentinel.remove();

  grid.appendChild(fragment);
  renderedVideosCount = currentFilterVideos.length;
}

function playVideo(v) {
  if (!v || !v.videoId) return;
  currentPlayingVideoId = v.videoId;
  const originalIdx = videoList.findIndex(item => item.videoId === v.videoId);
  if (originalIdx !== -1) currentIndex = originalIdx;

  const npTitle = document.getElementById('nowPlayingTitle');
  if (npTitle) npTitle.textContent = v.title || '';
  highlightActiveCard(v.videoId);

  channel.postMessage({ type: 'play', videoId: v.videoId });

  // Auto-foco del viewer si está habilitado
  if (config.auto_focus_viewer !== false) {
    if (viewerWindow && !viewerWindow.closed) {
      try { viewerWindow.focus(); } catch(e) {}
    }
    channel.postMessage({ type: 'focus_viewer' });
    fetch('/api/focus_viewer', { method: 'POST' }).catch(() => {});
  }

  fetch('/api/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'play', videoId: v.videoId, title: v.title, thumb: v.thumb })
  }).catch(() => {});
}

function playVideoByIndex(i) {
  if (videoList[i]) playVideo(videoList[i]);
}

function highlightActiveCard(videoId) {
  currentPlayingVideoId = videoId;
  document.querySelectorAll('.video-card').forEach(c => {
    c.classList.toggle('active', c.dataset.videoId === videoId);
  });
}

document.getElementById('speedSlider').addEventListener('input', (e) => {
  currentPlaybackRate = parseFloat(e.target.value);
  document.getElementById('speedValue').textContent = currentPlaybackRate.toFixed(1) + 'x';
  channel.postMessage({ type: 'state', playbackRate: currentPlaybackRate, muted: isMuted });
  fetch('/api/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'state', playbackRate: currentPlaybackRate, muted: isMuted })
  }).catch(() => {});
});

function toggleMute() {
  isMuted = !isMuted;
  const btn = document.getElementById('muteBtn');
  btn.textContent = isMuted ? 'Muted' : 'Unmuted';
  btn.classList.toggle('btn-accent', !isMuted);
  channel.postMessage({ type: 'state', playbackRate: currentPlaybackRate, muted: isMuted });
  fetch('/api/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'state', playbackRate: currentPlaybackRate, muted: isMuted })
  }).catch(() => {});
}



// ─── 4. YOUTUBE LIVE MONITOR LOGIC ───
let liveIsMuted = true;
let currentLiveVideoId = '';

async function loadLiveData() {
  const container = document.getElementById('liveVideoContainer');
  const badge = document.getElementById('liveBadgeStatus');
  const title = document.getElementById('liveTitleText');
  const muteBtn = document.getElementById('btnLiveToggleMute');
  const shareBar = document.getElementById('liveShareBar');
  const shareInput = document.getElementById('liveShareLinkInput');

  updateLiveMuteButton();

  try {
    const res = await fetch('/api/youtube/live');
    const data = await res.json();

    if (data.is_live && data.video_id) {
      badge.textContent = '🔴 EN VIVO';
      badge.style.color = 'var(--accent2)';
      title.textContent = data.title || 'Transmisión activa';
      if (muteBtn) muteBtn.style.display = 'inline-flex';

      // Mostrar link de compartir transmisión directa
      if (shareBar && shareInput) {
        shareInput.value = `https://www.youtube.com/watch?v=${data.video_id}`;
        shareBar.style.display = 'flex';
      }

      // Recrear solo si cambió el video o no hay iframe cargado
      if (currentLiveVideoId !== data.video_id || !container.querySelector('iframe')) {
        currentLiveVideoId = data.video_id;
        const muteParam = liveIsMuted ? 1 : 0;
        container.innerHTML = `
          <iframe id="livePlayerIframe" src="https://www.youtube.com/embed/${data.video_id}?autoplay=1&mute=${muteParam}&enablejsapi=1" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>
        `;
      }
    } else {
      currentLiveVideoId = '';
      if (muteBtn) muteBtn.style.display = 'none';
      if (shareBar) shareBar.style.display = 'none';
      badge.textContent = '⏸️ SIN DIRECTO ACTIVO';
      badge.style.color = 'var(--muted)';
      title.textContent = data.message || 'Configura tu canal de YouTube en Ajustes';
      container.innerHTML = `
        <div style="display:flex; height:100%; align-items:center; justify-content:center; color:var(--muted); flex-direction:column; gap:12px; padding:20px; text-align:center;">
          <p>No se detectó una transmisión en vivo activa en tu canal.</p>
          <button class="btn btn-accent" onclick="openSettingsModal()">⚙️ Configurar ID de Canal / Video en Vivo</button>
        </div>
      `;
    }
  } catch(e) {}
}

function copyLiveStreamLink() {
  const shareInput = document.getElementById('liveShareLinkInput');
  if (!shareInput || !shareInput.value) {
    showToast('No hay enlace de directo disponible');
    return;
  }
  const text = shareInput.value;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast('¡Enlace del directo copiado al portapapeles! 📋');
    }).catch(() => {
      shareInput.select();
      document.execCommand('copy');
      showToast('¡Enlace copiado! 📋');
    });
  } else {
    shareInput.select();
    document.execCommand('copy');
    showToast('¡Enlace copiado! 📋');
  }
}

function openLiveStreamLink() {
  const shareInput = document.getElementById('liveShareLinkInput');
  if (shareInput && shareInput.value) {
    if (typeof openExternalUrl === 'function') {
      openExternalUrl(shareInput.value);
    } else {
      fetch(`/api/open_browser?url=${encodeURIComponent(shareInput.value)}`, { method: 'POST' }).catch(() => {});
      try { window.open(shareInput.value, '_blank'); } catch(e) {}
    }
  } else {
    showToast('No hay enlace disponible');
  }
}

function updateLiveMuteButton() {
  const muteBtn = document.getElementById('btnLiveToggleMute');
  if (!muteBtn) return;
  if (liveIsMuted) {
    muteBtn.innerHTML = '🔇 Muteado';
    muteBtn.className = 'btn';
    muteBtn.style.color = 'var(--muted)';
  } else {
    muteBtn.innerHTML = '🔊 Con Sonido';
    muteBtn.className = 'btn btn-accent';
    muteBtn.style.color = '#000';
  }
}

function toggleLiveMute() {
  liveIsMuted = !liveIsMuted;
  updateLiveMuteButton();

  const iframe = document.getElementById('livePlayerIframe') || document.querySelector('#liveVideoContainer iframe');
  if (iframe && iframe.contentWindow) {
    const func = liveIsMuted ? 'mute' : 'unMute';
    iframe.contentWindow.postMessage(JSON.stringify({ event: 'command', func: func, args: [] }), '*');
    if (!liveIsMuted) {
      iframe.contentWindow.postMessage(JSON.stringify({ event: 'command', func: 'setVolume', args: [100] }), '*');
    }
  }

  showToast(liveIsMuted ? 'Monitor de directo silenciado 🔇' : 'Sonido del monitor activado 🔊');
}

function refreshLiveStream() {
  currentLiveVideoId = '';
  showToast('Actualizando monitor de directo...');
  loadLiveData();
}

