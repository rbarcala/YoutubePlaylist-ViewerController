import re

with open('controller.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Update CSS for Matrix Grid & Track Cards
matrix_css = '''  /* ─── 4. VISTA SPOTIFY REMOTE (WIDESCREEN DASHBOARD & MATRIX GRID) ─── */
  .spotify-dashboard-grid {
    display: grid;
    grid-template-columns: 320px 1fr;
    gap: 16px;
    align-items: start;
    width: 100%;
  }
  @media (max-width: 900px) {
    .spotify-dashboard-grid {
      grid-template-columns: 1fr;
    }
  }
  .spotify-side-panel {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .spotify-player-card {
    background: #121212;
    border: 1px solid #282828;
    border-radius: 12px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 100%;
    margin: 0;
  }
  .spotify-track-info {
    display: flex;
    gap: 12px;
    align-items: center;
  }
  .spotify-art {
    width: 76px; height: 76px;
    border-radius: 8px;
    object-fit: cover;
    background: #222;
    flex-shrink: 0;
  }
  .spotify-meta {
    overflow: hidden;
  }
  .spotify-meta h3 {
    font-size: 14px;
    color: #fff;
    margin-bottom: 3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .spotify-meta p {
    font-size: 12px;
    color: #aaa;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .spotify-meta span { font-size: 11px; color: var(--accent-spotify); }
  .spotify-controls-row {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 14px;
  }
  .spotify-saved-box {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px;
  }
  .sp-playlist-item {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    padding: 7px 10px;
    border-radius: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    transition: all 0.12s;
  }
  .sp-playlist-item:hover {
    background: rgba(255,255,255,0.07);
    border-color: var(--accent);
  }
  .spotify-main-panel {
    min-width: 0;
    width: 100%;
  }
  .spotify-search-box {
    width: 100%;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  /* MATRIZ DE CUADRADOS EN TODO EL ESPACIO DERECHO */
  .spotify-results-list {
    display: grid !important;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)) !important;
    gap: 10px !important;
    width: 100% !important;
    max-height: calc(100vh - 180px) !important;
    overflow-y: auto !important;
    padding-right: 6px;
    align-content: start;
  }
  .sp-track-card {
    background: #141414;
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 8px;
    padding: 7px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 6px;
    transition: background 0.12s, border-color 0.12s, transform 0.12s;
    user-select: none;
    cursor: pointer;
    contain: content;
  }
  .sp-track-card:hover {
    background: #202020;
    border-color: var(--accent-spotify);
    transform: translateY(-2px);
  }
  .sp-card-thumb-wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 1/1;
    border-radius: 6px;
    overflow: hidden;
    background: #111;
  }
  .sp-card-thumb {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .sp-card-idx {
    position: absolute;
    top: 3px;
    left: 3px;
    background: rgba(0, 0, 0, 0.8);
    color: #fff;
    font-size: 9px;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    font-family: 'Space Mono', monospace;
  }
  .sp-card-dur {
    position: absolute;
    bottom: 3px;
    right: 3px;
    background: rgba(0, 0, 0, 0.8);
    color: #ccc;
    font-size: 9px;
    padding: 1px 4px;
    border-radius: 3px;
    font-family: 'Space Mono', monospace;
  }
  .sp-card-info {
    display: flex;
    flex-direction: column;
    gap: 1px;
    overflow: hidden;
  }
  .sp-card-title {
    font-size: 11px;
    font-weight: 700;
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.25;
  }
  .sp-card-artist {
    font-size: 10px;
    color: #888;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.2;
  }
  .sp-card-actions {
    display: flex;
    gap: 4px;
    width: 100%;
  }
  .sp-card-btn-play {
    flex: 1;
    background: var(--accent-spotify);
    color: #000;
    font-weight: 700;
    border: none;
    border-radius: 4px;
    padding: 4px 6px;
    font-size: 10px;
    cursor: pointer;
    text-align: center;
    transition: opacity 0.1s;
  }
  .sp-card-btn-play:hover { opacity: 0.85; }
  .sp-card-btn-queue {
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
    font-weight: 700;
    border: none;
    border-radius: 4px;
    padding: 4px 7px;
    font-size: 10px;
    cursor: pointer;
    transition: background 0.1s;
  }
  .sp-card-btn-queue:hover { background: rgba(255, 255, 255, 0.2); }'''

html = re.sub(
    r'/\* ─── 4\. VISTA SPOTIFY REMOTE \(WIDESCREEN DASHBOARD\) ─── \*/[\s\S]*?/\* ─── 6\. VISTA SOUNDBOARD',
    matrix_css + '\n\n  /* ─── 6. VISTA SOUNDBOARD',
    html
)

# 2. Update Search Input placeholder and oninput attribute
html = html.replace(
    'placeholder="Buscar canción, artista o pegar enlace https://open.spotify.com/playlist/..." onkeydown="if(event.key === \'Enter\') spotifySearch()"',
    'placeholder="Buscar canción o: https://open.spotify.com/playlist/... [término para filtrar]" oninput="onSpotifySearchInput(this.value)" onkeydown="if(event.key === \'Enter\') spotifySearch()"'
)

# 3. Replace Spotify JavaScript logic with playlist parsing + filter support + matrix renderer
sp_logic_code = '''// ─── 3. SPOTIFY REMOTE LOGIC & MATRIZ DE CANCIONES ───
let spCurrentLoadedTracks = [];
let spCurrentPlaylistInfo = null;
let spFilterDebounce = null;

async function loadSpotifyData() {
  try {
    const res = await fetch('/api/spotify/state');
    const state = await res.json();

    if (state.available) {
      document.getElementById('spTrackTitle').textContent = state.title || 'En pausa';
      document.getElementById('spTrackArtist').textContent = state.artist || 'Spotify Desktop';
      document.getElementById('spDeviceName').textContent = `Dispositivo: ${state.device_name || 'PC'}`;
      if (state.album_art) {
        document.getElementById('spTrackArt').src = state.album_art;
      }
      document.getElementById('spPlayBtn').textContent = state.is_playing ? '⏸' : '▶';
      if (state.volume_percent !== undefined) {
        document.getElementById('spVolumeSlider').value = state.volume_percent;
        document.getElementById('spVolumeValue').textContent = state.volume_percent + '%';
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
      <div class="sp-playlist-item" onclick="loadPlaylist('${p.id}')" title="Cargar canciones de ${p.name}">
        <span style="color:var(--accent); font-weight:700; font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1;">
          🎵 ${p.name}
        </span>
        <button style="background:none; border:none; color:var(--muted); cursor:pointer; font-size:12px; padding:2px 4px;" onclick="event.stopPropagation(); deleteSpotifyPlaylist('${p.id}', '${p.name.replace(/'/g, "\\'")}')" title="Eliminar de guardadas">✖</button>
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
    showToast("Enlace de playlist no válido");
    return;
  }
  const pid = parsed.playlistId;
  showToast("Cargando y guardando playlist…");
  try {
    const res = await fetch('/api/spotify/playlist?id=' + pid);
    const data = await res.json();
    if (data.name) {
      await saveSpotifyPlaylist(pid, data.name);
      loadPlaylist(pid);
    } else {
      showToast("No se pudo obtener la playlist");
    }
  } catch(e) {
    showToast("Error conectando con Spotify");
  }
}

async function saveSpotifyPlaylist(id, name) {
  try {
    await fetch('/api/spotify/saved_playlists', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, name })
    });
    showToast(`Playlist "${name}" guardada ⭐`);
    loadSavedPlaylists();
  } catch(e) {
    showToast('Error al guardar playlist');
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
    showToast('Playlist eliminada de guardadas');
    loadSavedPlaylists();
  } catch(e) {
    showToast('Error al eliminar playlist');
  }
}

function loadPlaylist(id) {
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
  const urlMatch = trimmed.match(/(?:https?:\\/\\/open\\.spotify\\.com\\/playlist\\/|spotify:playlist:)([a-zA-Z0-9]+)(?:\\s+(.*))?/i);
  if (urlMatch) {
    return {
      isPlaylist: true,
      playlistId: urlMatch[1],
      filterQuery: (urlMatch[2] || '').trim()
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
  const terms = filterTerm.toLowerCase().split(/\\s+/).filter(Boolean);
  const filtered = spCurrentLoadedTracks.filter(t => {
    const text = `${t.title || ''} ${t.artist || ''} ${t.album || ''}`.toLowerCase();
    return terms.every(term => text.includes(term));
  });
  renderSpotifyMatrix(filtered, spCurrentPlaylistInfo, filterTerm);
}

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
            <button class="btn btn-accent" style="padding:5px 12px; font-size:11px; font-weight:700;" onclick="saveSpotifyPlaylist('${playlistInfo.id}', '${playlistInfo.name.replace(/'/g, "\\'")}')">
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

  list.innerHTML = tracks.map((track, idx) => {
    const safeTitle = (track.title || '').replace(/"/g, '&quot;');
    const safeArtist = (track.artist || '').replace(/"/g, '&quot;');
    const safeUri = track.uri || '';
    const dur = formatDurationMs(track.duration_ms);
    const thumb = track.thumb || '/assets/icon.png';
    const indexNum = track.index || (idx + 1);

    return `
      <div class="sp-track-card" data-uri="${safeUri}" title="${safeTitle} — ${safeArtist}" onclick="spotifyPlayTrack('${safeUri}')">
        <div class="sp-card-thumb-wrap">
          <img class="sp-card-thumb" src="${thumb}" loading="lazy" alt="art">
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
      </div>
    `;
  }).join('');
}

async function spotifySearch() {
  const val = document.getElementById('spSearchInput').value.trim();
  if (!val) return;
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
  showToast('Reproduciendo en Spotify de la PC...');
  await fetch('/api/spotify/play_track', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uri })
  });
  setTimeout(loadSpotifyData, 600);
}

async function spotifyAddQueue(uri) {
  showToast('Añadido a la cola de Spotify ✓');
  await fetch('/api/spotify/queue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uri })
  });
}
'''

# Replace Spotify logic starting from '// ─── 3. SPOTIFY REMOTE LOGIC ───' up to 'async function spotifyAddQueue'
pattern = r'// ─── 3\. SPOTIFY REMOTE LOGIC ───[\s\S]*?async function spotifyAddQueue\(uri\) \{[\s\S]*?\}\s*\}'
if not re.search(pattern, html):
    # Try alternate match
    pattern = r'// ─── 3\. SPOTIFY REMOTE LOGIC ───[\s\S]*?async function spotifyAddQueue\(uri\) \{[\s\S]*?\}'

html = re.sub(pattern, lambda m: sp_logic_code.strip(), html, count=1)

with open('controller.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("controller.html successfully updated with Spotify matrix grid and spacebar-filter parser.")
