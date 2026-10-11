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
let liveEmbedTimer = null;

function removeLiveFallback() {
  const container = document.getElementById('liveVideoContainer');
  const fb = container && container.querySelector('.live-fallback');
  if (fb) fb.remove();
}

/**
 * Muestra una tarjeta sobre el monitor cuando el embed de YouTube no se puede
 * reproducir (Error 153/150/101, embed deshabilitado, etc.), con miniatura y
 * botones para abrir el directo o reintentar.
 */
const LIVE_FALLBACK_MSG_CONNECTING = 'Conectando la vista previa de YouTube…';
const LIVE_FALLBACK_MSG_FAILED = 'YouTube no pudo mostrar la vista previa embebida (el directo está al aire igual).';

function setLiveFallbackMessage(text) {
  const el = document.querySelector('#liveVideoContainer .live-fallback-msg');
  if (el) el.textContent = text;
}

function showLiveFallback(videoId, title, connecting = false) {
  const container = document.getElementById('liveVideoContainer');
  if (!container) return;
  if (container.querySelector('.live-fallback')) {
    if (!connecting) setLiveFallbackMessage((title ? `${title} — ` : '') + LIVE_FALLBACK_MSG_FAILED);
    return;
  }
  container.style.position = 'relative';

  const wrap = document.createElement('div');
  wrap.className = 'live-fallback';
  wrap.style.cssText = 'position:absolute; inset:0; z-index:2; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; padding:20px; text-align:center; background:#000; color:#fff;';

  const img = document.createElement('img');
  const id = encodeURIComponent(videoId);
  img.src = `https://i.ytimg.com/vi/${id}/hqdefault_live.jpg`;
  img.onerror = () => { img.onerror = null; img.src = `https://i.ytimg.com/vi/${id}/hqdefault.jpg`; };
  img.style.cssText = 'position:absolute; inset:0; width:100%; height:100%; object-fit:cover; opacity:0.35; z-index:-1;';
  wrap.appendChild(img);

  const badge = document.createElement('div');
  badge.textContent = '🔴 Directo detectado';
  badge.style.cssText = 'font-weight:800; font-size:1.1rem;';
  wrap.appendChild(badge);

  const sub = document.createElement('div');
  sub.className = 'live-fallback-msg';
  sub.textContent = (title ? `${title} — ` : '') + (connecting ? LIVE_FALLBACK_MSG_CONNECTING : LIVE_FALLBACK_MSG_FAILED);
  sub.style.cssText = 'font-size:0.85rem; opacity:0.85; max-width:420px;';
  wrap.appendChild(sub);

  const row = document.createElement('div');
  row.style.cssText = 'display:flex; gap:10px; flex-wrap:wrap; justify-content:center;';
  const openBtn = document.createElement('button');
  openBtn.className = 'btn btn-accent';
  openBtn.textContent = '↗ Abrir en YouTube';
  openBtn.onclick = () => openLiveStreamLink();
  const retryBtn = document.createElement('button');
  retryBtn.className = 'btn';
  retryBtn.textContent = '🔄 Reintentar';
  retryBtn.onclick = () => refreshLiveStream();
  const hlsBtn = document.createElement('button');
  hlsBtn.className = 'btn';
  hlsBtn.textContent = '📺 Reproducir aquí';
  hlsBtn.onclick = () => startLiveHls(container, videoId, title);
  row.appendChild(openBtn);
  row.appendChild(hlsBtn);
  row.appendChild(retryBtn);
  wrap.appendChild(row);

  container.appendChild(wrap);
}

/**
 * Vigila el iframe del directo: escucha los mensajes de la IFrame API de YouTube
 * (onError / onReady) y mantiene una tarjeta de respaldo hasta recibir confirmación (5s sin señal => mensaje de fallo).
 * Si el player reporta que sí funciona más tarde, retira el fallback.
 */
function watchLiveEmbed(container, videoId, title) {
  if (liveEmbedTimer) clearTimeout(liveEmbedTimer);
  const iframe = container.querySelector('iframe');
  if (!iframe) return;

  iframe.addEventListener('load', () => {
    try {
      iframe.contentWindow.postMessage(JSON.stringify({ event: 'listening', id: 1, channel: 'widget' }), '*');
    } catch (e) {}
  });

  // Nunca mostrar un recuadro negro: tarjeta inmediata hasta que el player confirme que funciona
  showLiveFallback(videoId, title, true);
  liveEmbedTimer = setTimeout(() => {
    if (currentLiveVideoId === videoId) showLiveFallback(videoId, title, false);
  }, 5000);

  const onMsg = (ev) => {
    if (currentLiveVideoId !== videoId) {
      window.removeEventListener('message', onMsg);
      return;
    }
    if (typeof ev.origin !== 'string' || !ev.origin.includes('youtube')) return;
    let d = ev.data;
    if (typeof d === 'string') {
      try { d = JSON.parse(d); } catch (e) { return; }
    }
    if (!d || typeof d !== 'object') return;
    if (d.event === 'onError') {
      if (liveEmbedTimer) clearTimeout(liveEmbedTimer);
      showLiveFallback(videoId, title, false);
    } else if (d.event === 'onReady' || (d.event === 'infoDelivery' && d.info && d.info.playerState !== undefined)) {
      if (liveEmbedTimer) clearTimeout(liveEmbedTimer);
      removeLiveFallback();
    }
  };
  window.addEventListener('message', onMsg);
}

// ─── Reproductor HLS (ventana nativa / respaldo cuando el embed falla) ───
let liveHls = null;
let liveHlsScriptPromise = null;

function loadHlsLibrary() {
  if (window.Hls) return Promise.resolve();
  if (liveHlsScriptPromise) return liveHlsScriptPromise;
  liveHlsScriptPromise = new Promise((resolve, reject) => {
    const sc = document.createElement('script');
    sc.src = '/js/vendor/hls.min.js';
    sc.onload = () => resolve();
    sc.onerror = () => { liveHlsScriptPromise = null; reject(new Error('No se pudo cargar hls.js')); };
    document.head.appendChild(sc);
  });
  return liveHlsScriptPromise;
}

function destroyLiveHls() {
  if (liveHls) {
    try { liveHls.destroy(); } catch (e) {}
    liveHls = null;
  }
}

/**
 * Reproduce el directo con <video> + hls.js a través del proxy del backend.
 * Pensado para la ventana nativa (Qt WebEngine), donde el embed de YouTube no funciona.
 */
async function startLiveHls(container, videoId, title) {
  destroyLiveHls();
  if (liveEmbedTimer) { clearTimeout(liveEmbedTimer); liveEmbedTimer = null; }
  container.innerHTML = '<video id="liveHlsVideo" playsinline autoplay style="width:100%; height:100%; object-fit:contain; background:#000;"></video>';
  const video = container.querySelector('#liveHlsVideo');
  video.muted = liveIsMuted;
  showLiveFallback(videoId, title, true);

  const fail = (msg) => {
    if (currentLiveVideoId !== videoId) return;
    showLiveFallback(videoId, title, false);
    setLiveFallbackMessage((title ? `${title} — ` : '') + msg);
  };

  try {
    await loadHlsLibrary();
  } catch (e) {
    return fail('No se pudo cargar el reproductor HLS.');
  }
  if (currentLiveVideoId !== videoId) return;

  const h264 = window.MediaSource && MediaSource.isTypeSupported('video/mp4; codecs="avc1.4d401f,mp4a.40.2"');
  if (!window.Hls || !Hls.isSupported() || !h264) {
    return fail('Esta ventana no soporta H.264/HLS. Abrí el directo en YouTube.');
  }

  const hls = new Hls({ liveSyncDurationCount: 3, maxBufferLength: 20, enableWorker: true });
  liveHls = hls;
  hls.loadSource(`/api/youtube/live_hls/playlist.m3u8?v=${encodeURIComponent(videoId)}`);
  hls.attachMedia(video);
  hls.on(Hls.Events.MANIFEST_PARSED, () => { video.play().catch(() => {}); });
  hls.on(Hls.Events.ERROR, (_ev, data) => {
    if (!data.fatal) return;
    if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
      hls.startLoad();
      // Si tras reintentar sigue sin reproducir, avisar
      setTimeout(() => { if (liveHls === hls && video.readyState < 2) fail('No se pudo conectar con el directo.'); }, 8000);
    } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
      hls.recoverMediaError();
    } else {
      fail('El reproductor del directo falló. Probá Reintentar.');
    }
  });
  video.addEventListener('playing', () => { if (currentLiveVideoId === videoId) removeLiveFallback(); });
}

let isRefreshingLive = false;
let lastLiveRefreshTime = 0;

async function loadLiveData(force = false) {
  const container = document.getElementById('liveVideoContainer');
  const badge = document.getElementById('liveBadgeStatus');
  const title = document.getElementById('liveTitleText');
  const muteBtn = document.getElementById('btnLiveToggleMute');
  const shareBar = document.getElementById('liveShareBar');
  const shareInput = document.getElementById('liveShareLinkInput');

  updateLiveMuteButton();

  const now = Date.now();
  if (isRefreshingLive && !force) return;
  if (force && (now - lastLiveRefreshTime < 3000)) {
    showToast('Esperá unos segundos antes de volver a consultar ⏳');
    return;
  }
  isRefreshingLive = true;
  lastLiveRefreshTime = now;

  try {
    const url = force ? '/api/youtube/live?force=1' : '/api/youtube/live';
    const res = await fetch(url);
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
      if (currentLiveVideoId !== data.video_id || !container.querySelector('iframe, #liveHlsVideo')) {
        currentLiveVideoId = data.video_id;
        destroyLiveHls();
        // La ventana nativa (Qt WebEngine) no soporta el embed: usar HLS directamente
        if (/QtWebEngine/i.test(navigator.userAgent)) {
          startLiveHls(container, data.video_id, data.title);
          return;
        }
        const muteParam = liveIsMuted ? 1 : 0;
        const origin = encodeURIComponent(window.location.origin);
        container.innerHTML = `
          <iframe id="livePlayerIframe" src="https://www.youtube.com/embed/${encodeURIComponent(data.video_id)}?autoplay=1&mute=${muteParam}&enablejsapi=1&playsinline=1&origin=${origin}" referrerpolicy="strict-origin-when-cross-origin" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>
        `;
        watchLiveEmbed(container, data.video_id, data.title);
      }
    } else {
      currentLiveVideoId = '';
      destroyLiveHls();
      removeLiveFallback();
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
  } catch(e) {
  } finally {
    isRefreshingLive = false;
  }
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

  const hlsVideo = document.getElementById('liveHlsVideo');
  if (hlsVideo) {
    hlsVideo.muted = liveIsMuted;
    if (!liveIsMuted) hlsVideo.volume = 1;
  }

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
  loadLiveData(true);
}

