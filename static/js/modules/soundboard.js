// ─── 6. BOTONERA / SOUNDBOARD (MYINSTANTS) LOGIC ───
let currentSbTab = 'arg';
let currentSbPage = 1;
let sbHasMore = true;
let sbIsLoadingMore = false;
let sbAllLoadedSounds = [];
let savedFavorites = [];
let sbVolume = 80;
let sbVolDebounceTimer = null;
let sbIsAdjustingVolume = false;
let playingResetTimer = null;
let sbIntersectionObserver = null;

async function loadSoundboardView() {
  updateSoundboardAccountDisplay();
  await loadSavedFavoritesList();
  currentSbPage = 1;
  sbHasMore = true;
  loadSoundboardTab(currentSbTab, 1);
  setupSoundboardInfiniteScroll();
}

async function updateSoundboardAccountDisplay() {
  try {
    const res = await fetch('/api/soundboard/auth');
    const data = await res.json();
    const user = data.username || config.soundboard_username || '';
    const userEl = document.getElementById('sbAccountUsername');
    if (userEl) {
      userEl.textContent = user ? '@' + user : 'Sin vincular';
    }
    const badgeEl = document.getElementById('sbCloudSyncBadge');
    if (badgeEl) {
      if (data.has_session) {
        badgeEl.textContent = '🟢 Nube activa';
        badgeEl.style.color = '#34C759';
        badgeEl.style.background = 'rgba(52, 199, 89, 0.15)';
        badgeEl.title = 'Los favoritos se guardan localmente y en el servidor de MyInstants';
      } else if (user) {
        badgeEl.textContent = '🟡 Solo perfil';
        badgeEl.style.color = '#FFCC00';
        badgeEl.style.background = 'rgba(255, 204, 0, 0.15)';
        badgeEl.title = 'Importa favoritos públicos. Vincula sesión para guardar nuevos favoritos en la nube.';
      } else {
        badgeEl.textContent = 'Solo local';
        badgeEl.style.color = 'var(--muted)';
        badgeEl.style.background = 'rgba(255, 255, 255, 0.08)';
        badgeEl.title = 'Los favoritos solo se guardan en este dispositivo';
      }
    }
  } catch(e) {}
}

async function loadSavedFavoritesList() {
  try {
    const res = await fetch('/api/soundboard/favorites');
    savedFavorites = await res.json();
  } catch(e) {
    savedFavorites = [];
  }
}

function switchSoundboardTab(tab) {
  currentSbTab = tab;
  currentSbPage = 1;
  sbHasMore = true;
  sbAllLoadedSounds = [];

  document.querySelectorAll('.sb-tab-btn').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.getElementById('sbTab-' + tab);
  if (activeBtn) activeBtn.classList.add('active');

  const searchWrap = document.getElementById('sbSearchBarWrap');
  if (tab === 'search') {
    searchWrap.style.display = 'flex';
    document.getElementById('sbSearchInput').focus();
    const query = document.getElementById('sbSearchInput').value.trim();
    if (query) {
      executeSoundboardSearch();
      return;
    }
  }
  loadSoundboardTab(tab, 1);
}

async function loadSoundboardTab(tab, page = 1) {
  const loading = document.getElementById('sbLoadingIndicator');
  const loadingMore = document.getElementById('sbLoadingMore');
  const btnMore = document.getElementById('sbBtnLoadMore');
  const grid = document.getElementById('soundboardGrid');

  if (page === 1) {
    loading.style.display = 'block';
    if (btnMore) btnMore.style.display = 'none';
    grid.innerHTML = '';
  } else {
    if (loadingMore) loadingMore.style.display = 'block';
  }

  try {
    let sounds = [];
    if (['arg', 'ar', 'latam', 'usa', 'us', 'global'].includes(tab)) {
      const regCode = (tab === 'arg') ? 'ar' : (tab === 'usa' ? 'us' : tab);
      const res = await fetch(`/api/soundboard/regional?region=${regCode}&page=${page}`);
      const data = await res.json();
      sounds = Array.isArray(data) ? data : (data.sounds || []);
      sbHasMore = Boolean(data.has_more !== undefined ? data.has_more : (sounds.length >= 20));
    } else if (tab === 'favorites') {
      await loadSavedFavoritesList();
      sounds = savedFavorites;
      sbHasMore = false;
    } else if (tab === 'search') {
      const q = document.getElementById('sbSearchInput').value.trim();
      if (q) {
        const res = await fetch(`/api/soundboard/search?q=${encodeURIComponent(q)}&page=${page}`);
        const data = await res.json();
        sounds = Array.isArray(data) ? data : (data.sounds || []);
        sbHasMore = Boolean(data.has_more !== undefined ? data.has_more : (sounds.length >= 20));
      } else {
        loading.style.display = 'none';
        if (loadingMore) loadingMore.style.display = 'none';
        grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:40px; color:var(--muted);">Escribe en el buscador de arriba para buscar sonidos en MyInstants.</div>';
        return;
      }
    }

    loading.style.display = 'none';
    if (loadingMore) loadingMore.style.display = 'none';

    if (page === 1) {
      sbAllLoadedSounds = sounds;
      renderSoundboardGrid(sounds, false);
    } else {
      sbAllLoadedSounds = sbAllLoadedSounds.concat(sounds);
      renderSoundboardGrid(sounds, true);
    }

    if (btnMore) {
      btnMore.style.display = (sbHasMore && tab !== 'favorites') ? 'inline-flex' : 'none';
    }
  } catch(e) {
    loading.style.display = 'none';
    if (loadingMore) loadingMore.style.display = 'none';
    if (page === 1) {
      grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:30px; color:var(--accent2);">Error al cargar sonidos. Revisa tu conexión con MyInstants.</div>';
    }
  }
}

async function loadMoreSounds() {
  if (!sbHasMore || sbIsLoadingMore || currentSbTab === 'favorites') return;
  sbIsLoadingMore = true;
  currentSbPage++;
  await loadSoundboardTab(currentSbTab, currentSbPage);
  sbIsLoadingMore = false;
}

function setupSoundboardInfiniteScroll() {
  if (sbIntersectionObserver) {
    sbIntersectionObserver.disconnect();
  }
  const sentinel = document.getElementById('sbScrollSentinel');
  if (!sentinel) return;

  const container = document.getElementById('sbScrollContainer');
  sbIntersectionObserver = new IntersectionObserver((entries) => {
    if (entries[0] && entries[0].isIntersecting && sbHasMore && !sbIsLoadingMore && currentView === 'soundboard') {
      loadMoreSounds();
    }
  }, { root: container || null, rootMargin: '400px' });

  sbIntersectionObserver.observe(sentinel);

  if (container && !container._hasScrollListener) {
    container._hasScrollListener = true;
    container.addEventListener('scroll', handleSoundboardScroll, { passive: true });
    container.addEventListener('scroll', updateFloatingTopBtn, { passive: true });
  }
}

// Scroll throttled to prevent lag
let sbScrollThrottleTimeout = null;
function handleSoundboardScroll() {
  if (currentView !== 'soundboard' || !sbHasMore || sbIsLoadingMore || currentSbTab === 'favorites') return;
  if (sbScrollThrottleTimeout) return;
  sbScrollThrottleTimeout = setTimeout(() => {
    sbScrollThrottleTimeout = null;
    const container = document.getElementById('sbScrollContainer');
    if (container) {
      if ((container.scrollTop + container.clientHeight) >= (container.scrollHeight - 400)) {
        loadMoreSounds();
      }
    } else if ((window.innerHeight + window.scrollY) >= (document.body.offsetHeight - 400)) {
      loadMoreSounds();
    }
  }, 300);
}
window.addEventListener('scroll', handleSoundboardScroll, { passive: true });

function executeSoundboardSearch() {
  const q = document.getElementById('sbSearchInput').value.trim();
  if (!q) {
    showToast('Ingresa un término de búsqueda');
    return;
  }
  currentSbTab = 'search';
  currentSbPage = 1;
  sbHasMore = true;
  document.querySelectorAll('.sb-tab-btn').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.getElementById('sbTab-search');
  if (activeBtn) activeBtn.classList.add('active');
  loadSoundboardTab('search', 1);
}

function clearSoundboardSearch() {
  document.getElementById('sbSearchInput').value = '';
  switchSoundboardTab('arg');
}

function isSoundFavorite(sound) {
  return savedFavorites.some(f => 
    (f.id && f.id === sound.id) || 
    (f.mp3 && f.mp3 === sound.mp3) || 
    (f.title && f.title.toLowerCase() === sound.title.toLowerCase())
  );
}

function renderSoundboardGrid(sounds, append = false) {
  const grid = document.getElementById('soundboardGrid');
  if (!append && (!sounds || sounds.length === 0)) {
    grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:40px; color:var(--muted);">No se encontraron sonidos en esta sección.</div>';
    return;
  }

  const html = sounds.map(s => {
    const isFav = isSoundFavorite(s);
    const safeTitle = (s.title || '').replace(/"/g, '&quot;');
    const safeMp3 = (s.mp3 || '').replace(/"/g, '&quot;');
    const color = s.color || '#ff0055';
    const jsonStr = JSON.stringify(s).replace(/"/g, '&quot;');

    return `
      <div class="sound-tile" data-mp3="${safeMp3}" onclick="triggerPlaySound('${safeMp3}', '${safeTitle}', this)" title="${safeTitle}">
        <div class="sound-tile-top">
          <span class="sound-tile-dot" style="background:${color};"></span>
          <button class="sound-tile-fav ${isFav ? 'is-fav' : ''}" onclick="event.stopPropagation(); toggleFavoriteSound(${jsonStr}, this)" title="${isFav ? 'Quitar de favoritos' : 'Agregar a favoritos'}">
            ${isFav ? '★' : '☆'}
          </button>
        </div>
        <div class="sound-tile-title">${safeTitle}</div>
      </div>
    `;
  }).join('');

  if (append) {
    grid.insertAdjacentHTML('beforeend', html);
  } else {
    grid.innerHTML = html;
  }
}

async function triggerPlaySound(mp3Url, title, cardEl) {
  // Quitar el estado activo de cualquier otro botón anterior
  document.querySelectorAll('.sound-tile, .sound-card').forEach(c => c.classList.remove('playing'));

  if (cardEl) {
    cardEl.classList.add('playing', 'pressed');
    setTimeout(() => cardEl.classList.remove('pressed'), 180);
  }

  const npText = document.getElementById('sbNowPlayingText');
  if (npText) {
    npText.textContent = '▶ ' + title;
  }

  try {
    const res = await fetch('/api/soundboard/play', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mp3: mp3Url,
        title: title,
        volume: sbVolume,
        clientId: myClientId
      })
    });
    const data = await res.json();
    if (!data.success && data.error) {
      showToast('Error audio: ' + data.error);
      if (cardEl) cardEl.classList.remove('playing');
      if (npText && npText.textContent === '▶ ' + title) {
        npText.textContent = '⏹️ Error';
      }
    }
  } catch(e) {
    showToast('Error conectando con el servidor');
    if (cardEl) cardEl.classList.remove('playing');
  }

  // Quitar estado activo individualmente para este botón específico
  const thisEl = cardEl;
  setTimeout(() => {
    if (thisEl) thisEl.classList.remove('playing');
    const curNp = document.getElementById('sbNowPlayingText');
    if (curNp && curNp.textContent === '▶ ' + title) {
      curNp.textContent = '⏹️ Listo / Silencio';
    }
  }, 2200);
}

async function stopSoundboard() {
  document.querySelectorAll('.sound-tile, .sound-card').forEach(c => c.classList.remove('playing'));
  const npText = document.getElementById('sbNowPlayingText');
  if (npText) npText.textContent = '⏹️ Detenido';

  try {
    await fetch('/api/soundboard/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clientId: myClientId })
    });
    showToast('Audio detenido ⏹️');
  } catch(e) {}
}

function scrollToTopFondos() {
  const container = document.getElementById('fondosScrollContent');
  if (container) {
    container.scrollTo({ top: 0, behavior: 'smooth' });
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function scrollToTopSpotify() {
  const container = document.getElementById('spResultsList');
  if (container) {
    container.scrollTo({ top: 0, behavior: 'smooth' });
  }
  const side = document.getElementById('spSavedPlaylists');
  if (side) {
    side.scrollTo({ top: 0, behavior: 'smooth' });
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function scrollToTopSoundboard() {
  const container = document.getElementById('sbScrollContainer');
  if (container) {
    container.scrollTo({ top: 0, behavior: 'smooth' });
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function scrollToTopCurrentView() {
  if (currentView === 'fondos') {
    scrollToTopFondos();
  } else if (currentView === 'spotify') {
    scrollToTopSpotify();
  } else if (currentView === 'soundboard') {
    scrollToTopSoundboard();
  } else {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

function updateFloatingTopBtn() {
  const floatBtn = document.getElementById('sbFloatingTopBtn');
  if (!floatBtn) return;
  let scrollPos = window.scrollY;

  if (currentView === 'soundboard') {
    const sb = document.getElementById('sbScrollContainer');
    if (sb && sb.scrollTop > 0) scrollPos = sb.scrollTop;
  } else if (currentView === 'fondos') {
    const fc = document.getElementById('fondosScrollContent');
    if (fc && fc.scrollTop > 0) scrollPos = fc.scrollTop;
  } else if (currentView === 'spotify') {
    const sp = document.getElementById('spResultsList');
    if (sp && sp.scrollTop > 0) scrollPos = sp.scrollTop;
  }

  if (['fondos', 'spotify', 'soundboard'].includes(currentView) && scrollPos > 120) {
    floatBtn.classList.add('visible');
  } else {
    floatBtn.classList.remove('visible');
  }
}
window.addEventListener('scroll', updateFloatingTopBtn, { passive: true });
document.addEventListener('DOMContentLoaded', () => {
  const fc = document.getElementById('fondosScrollContent');
  if (fc) fc.addEventListener('scroll', updateFloatingTopBtn, { passive: true });
  const sp = document.getElementById('spResultsList');
  if (sp) sp.addEventListener('scroll', updateFloatingTopBtn, { passive: true });
  const sb = document.getElementById('sbScrollContainer');
  if (sb) sb.addEventListener('scroll', updateFloatingTopBtn, { passive: true });
});

// Ajustar cualquier valor numérico fácilmente con la ruedita del mouse (mouse wheel)
document.addEventListener('wheel', (e) => {
  if (e.target && e.target.matches && e.target.matches('input[type="number"]') && !e.target.disabled) {
    e.preventDefault();
    const step = parseFloat(e.target.step) || 1;
    const min = e.target.min !== '' ? parseFloat(e.target.min) : -Infinity;
    const max = e.target.max !== '' ? parseFloat(e.target.max) : Infinity;
    let val = (parseFloat(e.target.value) || 0) + (e.deltaY < 0 ? step : -step);
    val = Math.min(max, Math.max(min, Math.round(val * 100) / 100));
    e.target.value = val;
    e.target.dispatchEvent(new Event('input', { bubbles: true }));
    e.target.dispatchEvent(new Event('change', { bubbles: true }));
  }
}, { passive: false });

let lastVolSentTime = 0;

function sendSoundboardVolumeToServer(vol) {
  fetch('/api/soundboard/volume', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ volume: vol, clientId: myClientId })
  }).catch(() => {});
  if (config) config.soundboard_volume = vol;
}

function updateSoundboardVolume(val) {
  const num = parseInt(val, 10);
  sbVolume = isNaN(num) ? 80 : Math.max(0, Math.min(100, num));
  const label = document.getElementById('sbVolumeText');
  if (label) label.textContent = sbVolume + '%';
  const slider = document.getElementById('sbVolumeSlider');
  if (slider && slider.value != sbVolume) slider.value = sbVolume;
  const cfgSlider = document.getElementById('cfgSoundboardVolume');
  if (cfgSlider && cfgSlider.value != sbVolume) cfgSlider.value = sbVolume;
  const cfgVal = document.getElementById('cfgSbVolVal');
  if (cfgVal) cfgVal.textContent = sbVolume + '%';

  sbIsAdjustingVolume = true;
  channel.postMessage({ type: 'soundboard_volume', volume: sbVolume, clientId: myClientId });

  const now = Date.now();
  if (now - lastVolSentTime > 35) {
    lastVolSentTime = now;
    sendSoundboardVolumeToServer(sbVolume);
  }

  if (sbVolDebounceTimer) clearTimeout(sbVolDebounceTimer);
  sbVolDebounceTimer = setTimeout(() => {
    sendSoundboardVolumeToServer(sbVolume);
    setTimeout(() => { sbIsAdjustingVolume = false; }, 80);
  }, 60);
}

async function toggleFavoriteSound(sound, btnEl) {
  const isFav = isSoundFavorite(sound);
  try {
    if (isFav) {
      const res = await fetch('/api/soundboard/favorites/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: sound.id, title: sound.title, mp3: sound.mp3, clientId: myClientId })
      });
      const data = await res.json();
      savedFavorites = Array.isArray(data) ? data : (data.favorites || []);
      btnEl.classList.remove('is-fav');
      btnEl.textContent = '☆';
      btnEl.title = 'Agregar a favoritos';
      showToast('Eliminado de favoritos');
      if (currentSbTab === 'favorites') {
        const card = btnEl.closest('.sound-tile, .sound-card');
        if (card) card.remove();
      }
    } else {
      const res = await fetch('/api/soundboard/favorites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...sound, clientId: myClientId })
      });
      const data = await res.json();
      savedFavorites = Array.isArray(data) ? data : (data.favorites || []);
      btnEl.classList.add('is-fav');
      btnEl.textContent = '★';
      btnEl.title = 'Quitar de favoritos';
      if (data && data.cloud_synced) {
        showToast('⭐ Guardado localmente y en tu cuenta de MyInstants en la nube!');
      } else if (data && data.has_session === false) {
        showToast('⭐ Guardado localmente. Vincula tu cuenta para guardarlo en la nube.');
      } else {
        showToast('Guardado en favoritos ⭐');
      }
    }
  } catch(e) {
    showToast('Error al modificar favoritos');
  }
}

async function syncMyInstantsAccount() {
  let user = config.soundboard_username || '';
  if (!user) {
    openMyInstantsAuthModal();
    return;
  }

  showToast('Sincronizando favoritos de MyInstants...');
  try {
    const res = await fetch('/api/soundboard/sync_account', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user })
    });
    const data = await res.json();
    if (data.success) {
      savedFavorites = data.favorites;
      config.soundboard_username = data.username;
      updateSoundboardAccountDisplay();
      showToast(`¡Sincronizados ${data.total_synced} favoritos de @${data.username}!`);
      if (currentSbTab === 'favorites') {
        loadSoundboardTab('favorites', 1);
      }
    } else {
      showToast(data.error || 'No se pudieron sincronizar los favoritos');
    }
  } catch(e) {
    showToast('Error al sincronizar con MyInstants');
  }
}

async function syncMyInstantsFromSettings() {
  const user = document.getElementById('cfgSoundboardUsername').value.trim();
  if (!user) {
    showToast('Ingresa primero un nombre de usuario de MyInstants');
    return;
  }
  showToast('Consultando perfil público...');
  try {
    const res = await fetch('/api/soundboard/sync_account', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user })
    });
    const data = await res.json();
    if (data.success) {
      savedFavorites = data.favorites;
      config.soundboard_username = data.username;
      showToast(`✓ ¡${data.total_synced} favoritos importados exitosamente!`);
      updateSoundboardAccountDisplay();
    } else {
      showToast(data.error || 'Usuario no encontrado o perfil sin favoritos públicos');
    }
  } catch(e) {
    showToast('Error al sincronizar cuenta');
  }
}

// ─── MODAL Y VINCULACIÓN DE CUENTA MYINSTANTS (GOOGLE / NUBE) ───
function openMyInstantsAuthModal() {
  const modal = document.getElementById('myinstantsAuthModal');
  if (modal) modal.classList.add('active');
  loadSoundboardAuthStatus();
}

function closeMyInstantsAuthModal() {
  const modal = document.getElementById('myinstantsAuthModal');
  if (modal) modal.classList.remove('active');
}

function toggleCookieHelp() {
  const box = document.getElementById('cookieHelpBox');
  if (box) {
    box.style.display = box.style.display === 'none' ? 'block' : 'none';
  }
}

async function loadSoundboardAuthStatus() {
  try {
    const res = await fetch('/api/soundboard/auth');
    const data = await res.json();
    const user = data.username || config.soundboard_username || '';
    const hasSession = Boolean(data.has_session);

    const userText = document.getElementById('modalAuthUsernameText');
    if (userText) userText.textContent = user ? '@' + user : 'Sin configurar';

    const inputUser = document.getElementById('modalInputUsername');
    if (inputUser) inputUser.value = user;

    const badge = document.getElementById('modalAuthStatusBadge');
    if (badge) {
      if (hasSession) {
        badge.textContent = '🟢 Conectado con Sesión Activa';
        badge.style.color = '#34C759';
      } else if (user) {
        badge.textContent = '🟡 Usuario vinculado (sin sesión nube)';
        badge.style.color = '#FFCC00';
      } else {
        badge.textContent = '⚪ No vinculado';
        badge.style.color = '#ff5555';
      }
    }

    const cloudStatus = document.getElementById('modalAuthCloudStatus');
    if (cloudStatus) {
      if (hasSession) {
        cloudStatus.textContent = '🟢 Activo (los nuevos favoritos se guardan en el servidor de MyInstants)';
        cloudStatus.style.color = '#34C759';
      } else {
        cloudStatus.textContent = '⚪ Inactivo (los favoritos solo se guardan de forma local)';
        cloudStatus.style.color = 'var(--muted)';
      }
    }

    const btnDisconnect = document.getElementById('btnDisconnectSb');
    if (btnDisconnect) {
      btnDisconnect.style.display = (user || hasSession) ? 'inline-block' : 'none';
    }
  } catch(e) {}
}

let sbLoginPollInterval = null;

async function startDesktopLoginWindow() {
  showToast('Abriendo ventana de inicio de sesión de MyInstants...');
  if (sbLoginPollInterval) clearInterval(sbLoginPollInterval);

  // Consultar periódicamente mientras el usuario se loguea en la ventana
  sbLoginPollInterval = setInterval(async () => {
    try {
      const res = await fetch('/api/soundboard/auth');
      const data = await res.json();
      if (data && (data.has_session || data.username)) {
        clearInterval(sbLoginPollInterval);
        sbLoginPollInterval = null;
        config.soundboard_username = data.username;
        loadSoundboardAuthStatus();
        updateSoundboardAccountDisplay();
        if (currentSbTab === 'favorites') {
          loadSoundboardTab('favorites', 1);
        }
      }
    } catch(e) {}
  }, 1200);

  // Detener el polling tras 3 minutos si no hubo respuesta
  setTimeout(() => {
    if (sbLoginPollInterval) {
      clearInterval(sbLoginPollInterval);
      sbLoginPollInterval = null;
    }
  }, 180000);

  try {
    const res = await fetch('/api/soundboard/login_window', { method: 'POST' });
    const data = await res.json();
    if (data.fallback === 'browser') {
      showToast('Inicia sesión en tu navegador y copia tu usuario o cookie.');
      openMyInstantsInBrowser();
    } else {
      showToast('Completa el inicio de sesión en la ventana en pantalla.');
    }
  } catch(e) {
    openMyInstantsInBrowser();
  }
}

function openMyInstantsInBrowser() {
  const url = 'https://www.myinstants.com/en/favorites/';
  fetch(`/api/open_browser?url=${encodeURIComponent(url)}`, { method: 'POST' }).catch(() => {});
  try {
    window.open(url, '_blank');
  } catch(e) {}
  showToast('Abriendo MyInstants en el navegador 🌐');
}

function openMyInstantsWeb() {
  openMyInstantsAuthModal();
}

async function saveMyInstantsAuth() {
  const user = document.getElementById('modalInputUsername').value.trim();
  const session = document.getElementById('modalInputSessionCookie').value.trim();

  showToast('Guardando y sincronizando con MyInstants...');
  try {
    const res = await fetch('/api/soundboard/auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: user,
        session_cookie: session,
        clientId: myClientId
      })
    });
    const data = await res.json();
    if (data.success) {
      config.soundboard_username = data.username;
      showToast(data.has_session
        ? '¡Cuenta vinculada y guardado en la nube activado! 🎉'
        : '¡Usuario guardado y favoritos sincronizados!');
      updateSoundboardAccountDisplay();
      closeMyInstantsAuthModal();
      if (currentSbTab === 'favorites') {
        loadSoundboardTab('favorites', 1);
      }
    } else {
      showToast('Error al vincular cuenta');
    }
  } catch(e) {
    showToast('Error conectando con el servidor');
  }
}

async function disconnectMyInstantsAccount() {
  if (!confirm('¿Deseas desvincular tu cuenta de MyInstants de este controlador?')) return;
  try {
    await fetch('/api/soundboard/auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: '', session_cookie: '', csrf_token: '', clientId: myClientId })
    });
    config.soundboard_username = '';
    showToast('Cuenta desvinculada');
    updateSoundboardAccountDisplay();
    closeMyInstantsAuthModal();
  } catch(e) {}
}

async function saveSettingsQuietly(partialCfg) {
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(partialCfg)
    });
    const data = await res.json();
    config = data.config;
  } catch(e) {}
}

