// ─── 3. SPOTIFY REMOTE LOGIC & MATRIZ DE CANCIONES ───
let spCurrentLoadedTracks = [];
let spCurrentPlaylistInfo = null;
let spFilterDebounce = null;
let spIsSeeking = false;
let spSeekCooldownUntil = 0;
let spCurrentProgressMs = 0;
let spCurrentDurationMs = 0;

let spIsAdjustingVolume = false;
let spVolumeCooldownUntil = 0;
let spVolumeDebounceTimer = null;

function onSpotifyVolumeInput(val) {
  spIsAdjustingVolume = true;
  spVolumeCooldownUntil = Date.now() + 3000;
  const valEl = document.getElementById('spVolumeValue');
  if (valEl) valEl.textContent = val + '%';

  clearTimeout(spVolumeDebounceTimer);
  spVolumeDebounceTimer = setTimeout(() => {
    spotifySetVolume(val);
  }, 100);
}

function onSpotifyVolumeChange(val) {
  clearTimeout(spVolumeDebounceTimer);
  spotifySetVolume(val);
  spVolumeCooldownUntil = Date.now() + 3000;
  setTimeout(() => {
    spIsAdjustingVolume = false;
  }, 400);
}

function onSpotifySeekInput(val) {
  spIsSeeking = true;
  spSeekCooldownUntil = Date.now() + 3500;
  if (spCurrentDurationMs > 0) {
    const targetMs = (parseInt(val, 10) / 1000) * spCurrentDurationMs;
    const curEl = document.getElementById('spTimeCurrent');
    if (curEl) curEl.textContent = formatDurationMs(targetMs);
  }
}

async function onSpotifySeekChange(val) {
  if (spCurrentDurationMs > 0) {
    const targetMs = Math.round((parseInt(val, 10) / 1000) * spCurrentDurationMs);
    spCurrentProgressMs = targetMs;
    spSeekCooldownUntil = Date.now() + 3500;

    const curEl = document.getElementById('spTimeCurrent');
    if (curEl) curEl.textContent = formatDurationMs(targetMs);

    try {
      await fetch('/api/spotify/seek', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position_ms: targetMs })
      });
    } catch(e) {}
  }
  // Permitir que el ticker de segundo a segundo avance sin saltos desde targetMs
  setTimeout(() => {
    spIsSeeking = false;
  }, 50);
}

function updateSpotifyPlayerUI(state) {
  if (!state || !state.available) return;
  const titleEl = document.getElementById('spTrackTitle');
  const artistEl = document.getElementById('spTrackArtist');
  const artEl = document.getElementById('spTrackArt');
  const playBtn = document.getElementById('spPlayBtn');
  const devEl = document.getElementById('spDeviceName');
  const curEl = document.getElementById('spTimeCurrent');
  const totEl = document.getElementById('spTimeTotal');
  const sliderEl = document.getElementById('spProgressSlider');

  if (titleEl && state.title) titleEl.textContent = state.title;
  if (artistEl && state.artist) artistEl.textContent = state.artist;
  if (artEl && state.album_art) artEl.src = state.album_art;
  if (playBtn) playBtn.textContent = state.is_playing ? '⏸' : '▶';
  if (devEl) devEl.textContent = `Dispositivo: ${state.device_name || 'PC'}`;

  if (state.duration_ms) {
    spCurrentDurationMs = state.duration_ms;
    if (totEl) totEl.textContent = formatDurationMs(state.duration_ms);
  }

  if (state.progress_ms !== undefined) {
    const now = Date.now();
    const inSeekCooldown = now < spSeekCooldownUntil;
    // Si estamos en cooldown por haber cambiado de posición, solo aceptamos la posición del servidor
    // si ya se sincronizó cerca de nuestra posición deseada (+/- 2.5s)
    const serverDelta = Math.abs(state.progress_ms - spCurrentProgressMs);
    const serverCaughtUp = serverDelta < 2500;

    if (!spIsSeeking && (!inSeekCooldown || serverCaughtUp)) {
      spCurrentProgressMs = state.progress_ms;
      if (curEl) curEl.textContent = formatDurationMs(state.progress_ms);
      if (sliderEl && spCurrentDurationMs > 0) {
        const pct = Math.min(1000, Math.round((state.progress_ms / spCurrentDurationMs) * 1000));
        sliderEl.value = pct;
      }
    }
  }
}

async function loadSpotifyData() {
  try {
    const res = await fetch('/api/spotify/state');
    const state = await res.json();
    if (state.available) {
      updateSpotifyPlayerUI(state);
    } else if (state.error) {
      document.getElementById('spTrackTitle').textContent = (state.error.includes('Too many') || state.error.includes('QUOTA')) ? 'Spotify bloqueó la API temporalmente (429)' : 'Sin conexión con Spotify';
      document.getElementById('spTrackArtist').textContent = state.error;
      document.getElementById('spTrackArt').src = '/assets/icon.png';
      document.getElementById('spDeviceName').textContent = 'Bloqueado por AppArmor/API';
      if (state.volume_percent !== undefined) {
        if (!spIsAdjustingVolume && Date.now() > spVolumeCooldownUntil) {
          const vSlider = document.getElementById('spVolumeSlider');
          const vVal = document.getElementById('spVolumeValue');
          if (vSlider) vSlider.value = state.volume_percent;
          if (vVal) vVal.textContent = state.volume_percent + '%';
        }
      }
    }
  } catch(e) {}
}

async function spotifyAction(action) {
  await fetch('/api/spotify/' + action, { method: 'POST' });
  setTimeout(loadSpotifyData, 400);
}

async function spotifyTogglePlay() {
  const btn = document.getElementById('spPlayBtn');
  if (btn.textContent === '⏸') {
    await spotifyAction('pause');
  } else {
    await spotifyAction('play');
  }
}

function spotifySetVolume(val) {
  document.getElementById('spVolumeValue').textContent = val + '%';
  fetch('/api/spotify/volume', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ volume: parseInt(val), clientId: myClientId })
  });
}

async function loadSavedPlaylists() {
  const container = document.getElementById('spSavedPlaylists');
  const countEl = document.getElementById('spSavedCount');
  if (!container) return;

  try {
    const res = await fetch('/api/spotify/saved_playlists');
    const data = await res.json();
    const playlists = data.playlists || [];

    if (countEl) countEl.textContent = `${playlists.length} guardadas`;

    if (playlists.length === 0) {
      container.innerHTML = '<span style="color:var(--muted); font-size:11px;">No tienes playlists guardadas. Pega un enlace arriba y haz clic en Buscar.</span>';
      return;
    }

    container.innerHTML = playlists.map(p => `
      <div class="sp-playlist-item" onclick="loadSpotifyPlaylist('${p.id}')" title="Cargar canciones de ${p.name}">
        <span style="color:var(--accent); font-weight:700; font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1;">
          🎵 ${p.name}
        </span>
        <button style="background:none; border:none; color:var(--muted); cursor:pointer; font-size:12px; padding:2px 4px;" onclick="event.stopPropagation(); deleteSpotifyPlaylist('${p.id}', '${p.name.replace(/'/g, "\'")}')" title="Eliminar de guardadas">✖</button>
      </div>
    `).join('');
  } catch(e) {
    if (container) container.innerHTML = '<span style="color:var(--accent2); font-size:11px;">Error al cargar playlists guardadas.</span>';
  }
}

async function promptAddPlaylist() {
  const url = prompt("Pega aquí el enlace de la Playlist de Spotify (ej: https://open.spotify.com/playlist/...):");
  if (!url || !url.trim()) return;
  const parsed = parseSearchInput(url);
  if (!parsed.isPlaylist) {
    showToast("Enlace de playlist no válido", 'warning');
    return;
  }
  const pid = parsed.playlistId;
  showToast("Cargando y guardando playlist…", 'info');
  try {
    const res = await fetch('/api/spotify/playlist?id=' + pid);
    const data = await res.json();
    if (data.name) {
      await saveSpotifyPlaylist(pid, data.name);
      loadSpotifyPlaylist(pid);
    } else {
      showToast("No se pudo obtener la playlist", 'error');
    }
  } catch(e) {
    showToast("Error conectando con Spotify", 'error');
  }
}

async function saveSpotifyPlaylist(id, name) {
  try {
    await fetch('/api/spotify/saved_playlists', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, name })
    });
    showToast(`Playlist "${name}" guardada ⭐`, 'success');
    loadSavedPlaylists();
  } catch(e) {
    showToast('Error al guardar playlist', 'error');
  }
}

async function deleteSpotifyPlaylist(id, name) {
  if (!confirm(`¿Eliminar la playlist "${name || id}" de tu lista guardada?`)) return;
  try {
    await fetch('/api/spotify/saved_playlists', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id })
    });
    showToast('Playlist eliminada de guardadas', 'info');
    loadSavedPlaylists();
  } catch(e) {
    showToast('Error al eliminar playlist', 'error');
  }
}

function loadSpotifyPlaylist(id) {
  if (!id || id === 'undefined' || typeof id !== 'string') return;
  const input = document.getElementById('spSearchInput');
  if (input) input.value = 'https://open.spotify.com/playlist/' + id;
  spotifySearch();
}

function formatDurationMs(ms) {
  if (!ms) return '';
  const totalSecs = Math.floor(ms / 1000);
  const m = Math.floor(totalSecs / 60);
  const s = totalSecs % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

// Analizador de input: detecta si es playlist y extrae filtros después del espacio
function parseSearchInput(val) {
  const trimmed = (val || '').trim();
  const match = trimmed.match(/(?:https?:\/\/open\.spotify\.com\/playlist\/|spotify:playlist:)?([a-zA-Z0-9]{22})(?:\?[^\s]*)?(?:\s+(.*))?/i);
  if (match && match[1]) {
    return {
      isPlaylist: true,
      playlistId: match[1],
      filterQuery: (match[2] || '').trim()
    };
  }
  return {
    isPlaylist: false,
    query: trimmed
  };
}

// Búsqueda/Filtro en tiempo real al escribir
function onSpotifySearchInput(val) {
  const parsed = parseSearchInput(val);
  if (parsed.isPlaylist) {
    // Si la playlist ya está cargada en memoria, filtrar inmediatamente
    if (spCurrentPlaylistInfo && spCurrentPlaylistInfo.id === parsed.playlistId) {
      applyTrackFilter(parsed.filterQuery);
      return;
    }
  }
}

function applyTrackFilter(filterTerm) {
  if (!filterTerm) {
    renderSpotifyMatrix(spCurrentLoadedTracks, spCurrentPlaylistInfo);
    return;
  }
  const terms = filterTerm.toLowerCase().split(/\s+/).filter(Boolean);
  const filtered = spCurrentLoadedTracks.filter(t => {
    const text = `${t.title || ''} ${t.artist || ''} ${t.album || ''}`.toLowerCase();
    return terms.every(term => text.includes(term));
  });
  renderSpotifyMatrix(filtered, spCurrentPlaylistInfo, filterTerm);
}

let spCurrentDisplayedTracks = [];
let spRenderedTrackCount = 0;
const SP_BATCH_SIZE = 40;
let spTracksObserver = null;

function renderSpotifyMatrix(tracks, playlistInfo = null, activeFilter = '') {
  const list = document.getElementById('spResultsList');
  const header = document.getElementById('spPlaylistHeader');
  if (!list) return;

  if (playlistInfo) {
    if (header) {
      header.style.display = 'block';
      const isSaved = (config.spotify_playlists || []).some(p => p.id === playlistInfo.id);
      header.innerHTML = `
        <div style="background:rgba(232,255,71,0.06); border:1px solid rgba(232,255,71,0.25); border-radius:10px; padding:10px 14px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
          <div>
            <span style="font-size:14px; font-weight:800; color:var(--accent);">🎵 ${playlistInfo.name}</span>
            <span style="font-size:12px; color:var(--muted); margin-left:8px;">(${tracks.length} ${activeFilter ? `encontradas con "${activeFilter}"` : 'canciones'})</span>
          </div>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-accent" style="padding:5px 12px; font-size:11px; font-weight:700;" onclick="saveSpotifyPlaylist('${playlistInfo.id}', '${playlistInfo.name.replace(/'/g, "\'")}')">
              ${isSaved ? '⭐ Guardada' : '⭐ Guardar Playlist'}
            </button>
          </div>
        </div>
      `;
    }
  } else {
    if (header) {
      header.style.display = 'none';
      header.innerHTML = '';
    }
  }

  if (!tracks || tracks.length === 0) {
    list.innerHTML = `<div style="grid-column:1/-1; color:var(--muted); font-size:13px; text-align:center; padding:60px 20px;">
      ${activeFilter ? `No se encontraron canciones que coincidan con "${activeFilter}".` : 'No se encontraron resultados.'}
    </div>`;
    return;
  }

  spCurrentDisplayedTracks = tracks;
  spRenderedTrackCount = 0;
  list.innerHTML = '';
  renderNextSpotifyBatch();
}

function renderNextSpotifyBatch() {
  const list = document.getElementById('spResultsList');
  if (!list || spRenderedTrackCount >= spCurrentDisplayedTracks.length) return;

  const nextCount = Math.min(spRenderedTrackCount + SP_BATCH_SIZE, spCurrentDisplayedTracks.length);
  const fragment = document.createDocumentFragment();

  for (let i = spRenderedTrackCount; i < nextCount; i++) {
    const track = spCurrentDisplayedTracks[i];
    const safeTitle = (track.title || '').replace(/"/g, '&quot;');
    const safeArtist = (track.artist || '').replace(/"/g, '&quot;');
    const safeUri = track.uri || '';
    const dur = formatDurationMs(track.duration_ms);
    const thumb = track.thumb || '';
    const indexNum = track.index || (i + 1);

    const card = document.createElement('div');
    card.className = 'sp-track-card';
    card.dataset.uri = safeUri;
    card.title = `${safeTitle} — ${safeArtist}`;
    card.onclick = () => spotifyPlayTrack(safeUri);

    card.innerHTML = `
      <div class="sp-card-thumb-wrap">
        ${thumb ? `<img class="sp-card-thumb" src="${thumb}" decoding="async" alt="art" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='flex';">` : ''}
        <div class="sp-card-thumb-fallback" style="${thumb ? 'display:none;' : 'display:flex;'} width:100%; height:100%; align-items:center; justify-content:center; background:#1e1e1e; color:var(--muted); font-size:22px;">🎵</div>
        <span class="sp-card-idx">#${indexNum}</span>
        ${dur ? `<span class="sp-card-dur">${dur}</span>` : ''}
      </div>
      <div class="sp-card-info">
        <span class="sp-card-title">${safeTitle}</span>
        <span class="sp-card-artist">${safeArtist}</span>
      </div>
      <div class="sp-card-actions" onclick="event.stopPropagation()">
        <button class="sp-card-btn-play" onclick="spotifyPlayTrack('${safeUri}')" title="Reproducir">▶ Play</button>
        <button class="sp-card-btn-queue" onclick="spotifyAddQueue('${safeUri}')" title="Agregar a la cola">➕</button>
      </div>
    `;
    fragment.appendChild(card);
  }

  // Quitar sentinel previo si existía
  const oldSentinel = document.getElementById('spSentinel');
  if (oldSentinel) oldSentinel.remove();

  list.appendChild(fragment);
  spRenderedTrackCount = nextCount;

  // Si aún quedan más canciones por renderizar, agregar un sentinel al final
  if (spRenderedTrackCount < spCurrentDisplayedTracks.length) {
    const sentinel = document.createElement('div');
    sentinel.id = 'spSentinel';
    sentinel.style.cssText = 'grid-column: 1 / -1; height: 35px; display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 11px; opacity: 0.7;';
    sentinel.innerHTML = '<span>Cargando más canciones…</span>';
    list.appendChild(sentinel);

    if (spTracksObserver) spTracksObserver.disconnect();
    spTracksObserver = new IntersectionObserver((entries) => {
      if (entries[0] && entries[0].isIntersecting) {
        renderNextSpotifyBatch();
      }
    }, { rootMargin: '300px' });
    spTracksObserver.observe(sentinel);
  }
}

async function spotifySearch() {
  const inputEl = document.getElementById('spSearchInput');
  let val = inputEl ? inputEl.value.trim() : '';
  if (!val || val.includes('undefined')) {
    if (inputEl && val.includes('undefined')) {
      inputEl.value = '';
    }
    return;
  }
  const parsed = parseSearchInput(val);

  if (parsed.isPlaylist) {
    const pid = parsed.playlistId;
    const filterTerm = parsed.filterQuery;

    // Si ya tenemos esta playlist cargada en memoria, aplicar filtro al instante
    if (spCurrentPlaylistInfo && spCurrentPlaylistInfo.id === pid && spCurrentLoadedTracks.length > 0) {
      applyTrackFilter(filterTerm);
      return;
    }

    const list = document.getElementById('spResultsList');
    list.innerHTML = '<p style="grid-column:1/-1; color:var(--muted); font-size:13px; text-align:center; padding:50px;">Cargando todas las canciones de la playlist…</p>';

    try {
      const res = await fetch('/api/spotify/playlist?id=' + pid);
      const data = await res.json();
      if (data.tracks && data.tracks.length > 0) {
        spCurrentLoadedTracks = data.tracks;
        spCurrentPlaylistInfo = { id: pid, name: data.name || 'Playlist' };
        applyTrackFilter(filterTerm);
      } else {
        list.innerHTML = `<p style="grid-column:1/-1; color:var(--accent2); font-size:12px; text-align:center; padding:30px;">No se encontraron canciones en esta playlist (${data.error || 'Revisa tu cuenta de Spotify en Ajustes'}).</p>`;
      }
    } catch(e) {
      list.innerHTML = '<p style="grid-column:1/-1; color:var(--accent2); font-size:12px; text-align:center; padding:30px;">Error al cargar la playlist.</p>';
    }
  } else {
    const list = document.getElementById('spResultsList');
    list.innerHTML = '<p style="grid-column:1/-1; color:var(--muted); font-size:13px; text-align:center; padding:50px;">Buscando en Spotify…</p>';
    try {
      const res = await fetch('/api/spotify/search?q=' + encodeURIComponent(parsed.query));
      const data = await res.json();
      spCurrentLoadedTracks = data.tracks || [];
      spCurrentPlaylistInfo = null;
      renderSpotifyMatrix(spCurrentLoadedTracks, null);
    } catch(e) {
      list.innerHTML = '<p style="grid-column:1/-1; color:var(--accent2); font-size:12px; text-align:center; padding:30px;">Error en búsqueda de Spotify.</p>';
    }
  }
}

async function spotifyPlayTrack(uri) {
  showToast('Reproduciendo en Spotify de la PC...', 'info');
  try {
    await fetch('/api/spotify/play_track', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri })
    });
    setTimeout(loadSpotifyData, 600);
  } catch(e) {
    showToast('Error al reproducir canción en Spotify', 'error');
  }
}

async function spotifyAddQueue(uri) {
  try {
    await fetch('/api/spotify/queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri })
    });
    showToast('Añadido a la cola de Spotify ✓', 'success');
  } catch(e) {
    showToast('Error al añadir a la cola de Spotify', 'error');
  }
}

async function loginSpotifyOAuth() {
  const inputId = document.getElementById('cfgSpotifyClientId');
  const inputSecret = document.getElementById('cfgSpotifyClientSecret');
  const clientId = inputId ? inputId.value.trim() : (config.spotify_client_id || '');
  const clientSecret = inputSecret ? inputSecret.value.trim() : (config.spotify_client_secret || '');

  if (!clientId || !clientSecret) {
    showToast('Ingresa tanto el Client ID como el Client Secret de Spotify', 'warning');
    return;
  }

  // Guardar credenciales automáticamente en el backend si fueron ingresadas en el modal
  try {
    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        spotify_client_id: clientId,
        spotify_client_secret: clientSecret
      })
    });
    config.spotify_client_id = clientId;
    config.spotify_client_secret = clientSecret;
  } catch(e) {}

  try {
    const res = await fetch('/api/spotify/auth_url');
    const data = await res.json();
    if (!data.auth_url) {
      showToast('Configura Client ID y Client Secret de Spotify primero', 'warning');
      return;
    }
    // Abrir en el navegador predeterminado del sistema operativo
    fetch(`/api/open_browser?url=${encodeURIComponent(data.auth_url)}`, { method: 'POST' }).catch(() => {});
    try {
      window.open(data.auth_url, '_blank');
    } catch(e) {}
    showToast('Abriendo autorización de Spotify en tu navegador...', 'info');
  } catch(e) {
    showToast('No se pudo iniciar la vinculación con Spotify', 'error');
  }
}

