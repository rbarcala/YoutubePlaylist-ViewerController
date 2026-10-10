// ─── OVERLAYS Y TEMPORIZADOR "YA VUELVO" ───
let timerPhrasesList = [];
let currentTimerState = { active: false, running: false, remaining: 600, duration: 600, title: 'Ya vuelvo', phrase: '' };

function getOverlayUrl() {
  const host = window.location.hostname || 'localhost';
  const port = window.location.port || '8000';
  return `http://${host}:${port}/overlay.html`;
}

function copyObsOverlayUrl() {
  const url = getOverlayUrl();
  navigator.clipboard.writeText(url).then(() => {
    showToast('Enlace de Overlay copiado ✓');
  }).catch(() => {
    const input = document.getElementById('obsOverlayUrlInput');
    if (input) {
      input.select();
      document.execCommand('copy');
      showToast('Enlace de Overlay copiado ✓');
    }
  });
}

async function loadOverlaysView() {
  const urlInput = document.getElementById('obsOverlayUrlInput');
  if (urlInput) urlInput.value = getOverlayUrl();

  try {
    const res = await fetch('/api/timer/status');
    const state = await res.json();
    updateTimerUI(state);
  } catch(e) {}

  await loadTimerPhrases();
  await syncObsCanvasResolution();
  initOverlayStudio();
  switchInspectorTab('now_playing', true);
  requestAnimationFrame(() => {
    updateStageMockups();
  });
  setTimeout(updateStageMockups, 50);
  setTimeout(updateStageMockups, 180);
}

async function loadTimerPhrases() {
  try {
    const res = await fetch('/api/timer/phrases');
    const data = await res.json();
    timerPhrasesList = data.phrases || [];
    renderTimerPhraseSelect();
  } catch(e) {}
}

function renderTimerPhraseSelect() {
  const select = document.getElementById('timerPhraseSelect');
  if (!select) return;
  const currentVal = currentTimerState.phrase || select.value;
  select.innerHTML = '<option value="">-- Sin frase / Solo temporizador --</option>' +
    timerPhrasesList.map(p => {
      const escaped = p.replace(/"/g, '&quot;');
      const selected = p === currentVal ? 'selected' : '';
      return `<option value="${escaped}" ${selected}>${p}</option>`;
    }).join('');

  const preview = document.getElementById('timerPhrasePreview');
  if (preview) {
    preview.textContent = currentVal ? `"${currentVal}"` : '';
  }
}

function updateTimerUI(state) {
  if (!state) return;
  currentTimerState = state;

  const rem = Math.max(0, parseInt(state.remaining || 0, 10));
  const mins = Math.floor(rem / 60);
  const secs = rem % 60;
  const timeStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

  const clockEl = document.getElementById('timerClockDisplay');
  if (clockEl) clockEl.textContent = timeStr;

  const badge = document.getElementById('timerStatusBadge');
  if (badge) {
    badge.className = 'timer-status-badge';
    if (!state.active) {
      badge.classList.add('timer-status-inactive');
      badge.textContent = 'Inactivo (Oculto en OBS)';
    } else if (state.running) {
      badge.classList.add('timer-status-running');
      badge.textContent = 'En vivo (Corriendo)';
    } else if (rem === 0) {
      badge.classList.add('timer-status-finished');
      badge.textContent = '¡Terminado! (00:00)';
    } else {
      badge.classList.add('timer-status-paused');
      badge.textContent = 'Pausado';
    }
  }

  const progressFill = document.getElementById('timerProgressFill');
  if (progressFill) {
    const dur = Math.max(1, parseInt(state.duration || 600, 10));
    const pct = Math.min(100, Math.max(0, (rem / dur) * 100));
    progressFill.style.width = pct + '%';
  }

  // Sincronizar el slider si el usuario no está arrastrándolo en ese instante
  const slider = document.getElementById('timerDurationSlider');
  const sliderValLabel = document.getElementById('timerSliderMinutesVal');
  if (slider && document.activeElement !== slider) {
    const activeMins = Math.max(1, Math.round(rem / 60));
    const maxVal = parseInt(slider.max || '30', 10);
    if (activeMins > maxVal) {
      updateTimerSliderMax(activeMins);
    }
    slider.value = activeMins;
    if (sliderValLabel) sliderValLabel.textContent = `${activeMins} min`;
  }

  const titleInput = document.getElementById('timerTitleInput');
  if (titleInput && (!state.active || document.activeElement !== titleInput)) {
    if (state.title) titleInput.value = state.title;
  }

  const select = document.getElementById('timerPhraseSelect');
  if (select && state.phrase) {
    select.value = state.phrase;
  }
  const preview = document.getElementById('timerPhrasePreview');
  if (preview) {
    preview.textContent = state.phrase ? `"${state.phrase}"` : '';
  }

  const btnPause = document.getElementById('btnTimerPause');
  if (btnPause) {
    btnPause.textContent = (state.active && state.running) ? '⏸ Pausar' : '▶ Reanudar';
    btnPause.style.display = state.active ? 'inline-flex' : 'none';
  }
  const btnStop = document.getElementById('btnTimerStop');
  if (btnStop) {
    btnStop.style.display = state.active ? 'inline-flex' : 'none';
  }
}

function onTimerSliderChange(val) {
  const mins = parseInt(val, 10) || 1;
  const label = document.getElementById('timerSliderMinutesVal');
  if (label) label.textContent = `${mins} min`;

  const clockEl = document.getElementById('timerClockDisplay');
  if (clockEl) {
    clockEl.textContent = `${String(mins).padStart(2, '0')}:00`;
  }

  // Si está activo en vivo, opcionalmente el usuario puede dar inicio o add
  if (currentTimerState && !currentTimerState.active) {
    currentTimerState.duration = mins * 60;
    currentTimerState.remaining = mins * 60;
  }
}

function updateTimerSliderMax(maxVal) {
  let maxNum = parseInt(maxVal, 10);
  if (isNaN(maxNum) || maxNum < 1) maxNum = 30;

  const slider = document.getElementById('timerDurationSlider');
  const maxDisplay = document.getElementById('timerSliderMaxDisplay');
  const maxInput = document.getElementById('timerSliderMaxInput');

  if (slider) {
    slider.max = maxNum;
    if (parseInt(slider.value, 10) > maxNum) {
      slider.value = maxNum;
      onTimerSliderChange(maxNum);
    }
  }
  if (maxDisplay) maxDisplay.textContent = `${maxNum} min`;
  if (maxInput && String(maxInput.value) !== String(maxNum)) maxInput.value = maxNum;
}

async function startTimerWithMinutes(mins) {
  const titleInput = document.getElementById('timerTitleInput');
  const title = (titleInput && titleInput.value.trim()) || 'Recreo';
  const phrase = getSelectedOrRandomPhrase();
  const duration = mins * 60;

  try {
    const res = await fetch('/api/timer/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ duration, title, phrase })
    });
    const data = await res.json();
    if (data.state) updateTimerUI(data.state);
    showToast(`⏱ Temporizador iniciado: ${mins} min`);
  } catch(e) {
    showToast('Error al iniciar temporizador');
  }
}


async function addTimerMinutes(mins) {
  if (currentTimerState && currentTimerState.active) {
    // Si ya está activo, le sumamos tiempo en vivo
    try {
      const res = await fetch('/api/timer/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration: mins * 60 })
      });
      const data = await res.json();
      if (data.state) updateTimerUI(data.state);
      showToast(`⏱ Añadidos ${mins} min al temporizador`);
    } catch(e) {
      showToast('Error al añadir tiempo');
    }
  } else {
    // Si está inactivo, sumamos a la visualización y slider
    let currentMins = 0;
    const clockText = document.getElementById('timerClockDisplay')?.textContent || '10:00';
    const parts = clockText.split(':');
    if (parts.length === 2) {
      currentMins = parseInt(parts[0], 10) || 0;
    }
    const newMins = Math.max(1, currentMins + mins);
    const slider = document.getElementById('timerDurationSlider');
    if (slider) {
      const maxVal = parseInt(slider.max || '30', 10);
      if (newMins > maxVal) {
        updateTimerSliderMax(newMins);
      }
      slider.value = newMins;
    }
    const label = document.getElementById('timerSliderMinutesVal');
    if (label) label.textContent = `${newMins} min`;
    const clockEl = document.getElementById('timerClockDisplay');
    if (clockEl) clockEl.textContent = `${String(newMins).padStart(2, '0')}:00`;
  }
}

async function startCustomTimer() {
  const clockText = document.getElementById('timerClockDisplay')?.textContent || '10:00';
  const parts = clockText.split(':');
  let mins = 10;
  if (parts.length === 2) {
    mins = parseInt(parts[0], 10) || 10;
  }
  startTimerWithMinutes(mins > 0 ? mins : 10);
}

async function pauseOverlayTimer() {
  try {
    const res = await fetch('/api/timer/pause', { method: 'POST' });
    const data = await res.json();
    if (data.state) updateTimerUI(data.state);
  } catch(e) {}
}

async function stopOverlayTimer() {
  try {
    const res = await fetch('/api/timer/stop', { method: 'POST' });
    const data = await res.json();
    if (data.state) updateTimerUI(data.state);
    showToast('Overlay ocultado');
  } catch(e) {}
}

function getSelectedOrRandomPhrase() {
  const select = document.getElementById('timerPhraseSelect');
  if (select && select.value) return select.value;
  if (timerPhrasesList.length > 0) {
    const idx = Math.floor(Math.random() * timerPhrasesList.length);
    return timerPhrasesList[idx];
  }
  return '';
}

async function changeTimerPhrase(val) {
  const preview = document.getElementById('timerPhrasePreview');
  if (preview) preview.textContent = val ? `"${val}"` : '';

  if (currentTimerState.active) {
    try {
      const res = await fetch('/api/timer/phrase', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phrase: val })
      });
      const data = await res.json();
      if (data.state) updateTimerUI(data.state);
    } catch(e) {}
  }
}

function randomizeTimerPhrase() {
  if (!timerPhrasesList || timerPhrasesList.length === 0) return;
  const random = timerPhrasesList[Math.floor(Math.random() * timerPhrasesList.length)];
  const select = document.getElementById('timerPhraseSelect');
  if (select) {
    select.value = random;
    changeTimerPhrase(random);
  }
}

// Modal de gestión de frases / memes
function openManagePhrasesModal() {
  renderPhrasesModalList();
  document.getElementById('phrasesModal').classList.add('active');
}

function closeManagePhrasesModal() {
  document.getElementById('phrasesModal').classList.remove('active');
}

function renderPhrasesModalList() {
  const container = document.getElementById('phrasesModalList');
  if (!container) return;
  if (timerPhrasesList.length === 0) {
    container.innerHTML = '<div style="color:var(--muted); font-size:12px; padding:10px 0;">No hay frases configuradas.</div>';
    return;
  }
  container.innerHTML = timerPhrasesList.map((phrase, idx) => {
    return `
      <div class="phrases-list-item">
        <span style="flex:1;">${phrase}</span>
        <button class="btn btn-danger" style="padding:4px 8px; font-size:11px;" onclick="deleteTimerPhrase(${idx})">🗑</button>
      </div>
    `;
  }).join('');
}

async function addTimerPhrase() {
  const input = document.getElementById('newPhraseInput');
  const val = input ? input.value.trim() : '';
  if (!val) return;

  try {
    const res = await fetch('/api/timer/phrases/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phrase: val })
    });
    const data = await res.json();
    timerPhrasesList = data.phrases || [];
    input.value = '';
    renderPhrasesModalList();
    renderTimerPhraseSelect();
    showToast('Meme de informática agregado ✓');
  } catch(e) {
    showToast('Error al agregar frase');
  }
}

async function deleteTimerPhrase(idx) {
  const phrase = timerPhrasesList[idx];
  if (!phrase) return;
  try {
    const res = await fetch('/api/timer/phrases/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phrase })
    });
    const data = await res.json();
    timerPhrasesList = data.phrases || [];
    renderPhrasesModalList();
    renderTimerPhraseSelect();
    showToast('Frase eliminada');
  } catch(e) {
    showToast('Error al eliminar frase');
  }
}

// ─── ESTUDIO VISUAL Y PERSONALIZACIÓN MODULAR DE OVERLAYS ───
let isDraggingStage = false;
let isResizingStage = false;
let activeStageTarget = null;
let currentSelectedModule = 'now_playing';
let stageDragStartX = 0;
let stageDragStartY = 0;
let stageOrigX = 0;
let stageOrigY = 0;
let stageOrigScale = 1.0;
let stageCapturedEl = null;
let stageActivePointerId = null;
let stageMoveRaf = null;
let modularSaveTimeout = null;
let stageGuidesVisible = true;

function hexToRgba(hex, alpha) {
  if (!hex) return `rgba(10, 10, 10, ${alpha})`;
  if (hex.startsWith('rgba') || hex.startsWith('rgb')) return hex;
  let cleanHex = hex.replace('#', '');
  if (cleanHex.length === 3) cleanHex = cleanHex.split('').map(c => c + c).join('');
  const r = parseInt(cleanHex.substring(0, 2), 16) || 10;
  const g = parseInt(cleanHex.substring(2, 4), 16) || 10;
  const b = parseInt(cleanHex.substring(4, 6), 16) || 10;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function colorToHex(col, fallback = '#ffffff') {
  if (!col || typeof col !== 'string') return fallback;
  col = col.trim();
  if (col.startsWith('#')) {
    if (col.length === 4) {
      return '#' + col[1] + col[1] + col[2] + col[2] + col[3] + col[3];
    }
    if (col.length >= 7) {
      return col.substring(0, 7);
    }
  }
  const match = col.match(/rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
  if (match) {
    const r = Math.min(255, parseInt(match[1], 10)).toString(16).padStart(2, '0');
    const g = Math.min(255, parseInt(match[2], 10)).toString(16).padStart(2, '0');
    const b = Math.min(255, parseInt(match[3], 10)).toString(16).padStart(2, '0');
    return `#${r}${g}${b}`;
  }
  return fallback;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function toggleStageGuides() {
  stageGuidesVisible = !stageGuidesVisible;
  const guides = document.getElementById('stageGuides');
  if (guides) {
    guides.style.display = stageGuidesVisible ? 'block' : 'none';
  }
  const btn = document.getElementById('btnToggleGuides');
  if (btn) {
    btn.classList.toggle('active', stageGuidesVisible);
  }
}

let stageObsPreviewActive = false;
let obsBaseWidth = 1920;
let obsBaseHeight = 1080;
let stageObsScreenshotInterval = null;

async function syncObsCanvasResolution() {
  try {
    const res = await fetch('/api/obs/video_settings');
    const data = await res.json();
    if (data.success && data.baseWidth && data.baseHeight) {
      obsBaseWidth = data.baseWidth;
      obsBaseHeight = data.baseHeight;

      const badge = document.getElementById('stageObsResolutionBadge');
      if (badge) {
        badge.textContent = `🖥️ PANTALLA OBS ${obsBaseWidth} × ${obsBaseHeight} (LÍMITE TOTAL)`;
      }
      const tr = document.getElementById('stageCornerTR');
      if (tr) tr.textContent = `${obsBaseWidth}, 0 ⌝`;
      const bl = document.getElementById('stageCornerBL');
      if (bl) bl.textContent = `⌞ 0, ${obsBaseHeight}`;
      const br = document.getElementById('stageCornerBR');
      if (br) br.textContent = `${obsBaseWidth}, ${obsBaseHeight} ⌟`;

      updateStageMockups();
    }
  } catch(e) {}
}

async function toggleStageObsPreview() {
  stageObsPreviewActive = !stageObsPreviewActive;
  const btn = document.getElementById('btnToggleObsCanvasPreview');
  const videoEl = document.getElementById('stageObsVideoBg');
  const imgEl = document.getElementById('stageObsScreenshotBg');

  if (btn) btn.classList.toggle('btn-accent', stageObsPreviewActive);

  if (stageObsPreviewActive) {
    showToast('Conectando preview de OBS al lienzo…');

    // 1. Intentar obtener la cámara virtual de OBS (60 FPS Ultra HD en PC)
    let stream = (typeof currentCamStream !== 'undefined' && currentCamStream && currentCamStream.active) ? currentCamStream : null;
    if (!stream && typeof window.getOrAcquireVirtualCamStream === 'function') {
      try {
        stream = await window.getOrAcquireVirtualCamStream();
      } catch(e) {}
    }

    if (stream && videoEl) {
      videoEl.srcObject = stream;
      videoEl.style.display = 'block';
      if (imgEl) imgEl.style.display = 'none';
      videoEl.play().catch(() => {});
      showToast('Preview de OBS conectado a 60 FPS ✓');
      return;
    }

    // 2. Fallback: Transmisión de alta velocidad por red si no hay cámara virtual (móvil o sin permisos)
    if (imgEl) imgEl.style.display = 'block';
    if (videoEl) videoEl.style.display = 'none';

    let isFetchingStageFrame = false;
    const fetchScreenshot = async () => {
      if (!stageObsPreviewActive || isFetchingStageFrame) return;
      isFetchingStageFrame = true;
      try {
        const scRes = await fetch('/api/obs/status');
        const scData = await scRes.json();
        const currentScene = scData.current_scene || '';
        const sceneParam = currentScene ? `?scene=${encodeURIComponent(currentScene)}` : '';
        const res = await fetch(`/api/obs/preview${sceneParam}&width=640&height=360&quality=45`, { cache: 'no-store' });
        const pData = await res.json();
        if (pData.success && pData.imageData && stageObsPreviewActive) {
          imgEl.src = pData.imageData;
        }
      } catch(e) {
      } finally {
        isFetchingStageFrame = false;
      }
    };

    fetchScreenshot();
    if (stageObsScreenshotInterval) clearInterval(stageObsScreenshotInterval);
    stageObsScreenshotInterval = setInterval(fetchScreenshot, 80); // ~12 FPS fluido
  } else {
    if (stageObsScreenshotInterval) clearInterval(stageObsScreenshotInterval);
    stageObsScreenshotInterval = null;
    if (videoEl) {
      videoEl.style.display = 'none';
      videoEl.srcObject = null;
    }
    if (imgEl) {
      imgEl.style.display = 'none';
      imgEl.src = '';
    }
    showToast('Preview de OBS desactivada del lienzo');
  }
}

let stageBgMode = 'dark';
function toggleStageBgMode() {
  const canvas = document.getElementById('stageCanvas');
  const btn = document.getElementById('btnToggleBgMode');
  if (!canvas) return;
  if (stageBgMode === 'dark') {
    stageBgMode = 'checkerboard';
    canvas.classList.remove('bg-dark');
    canvas.classList.add('bg-checkerboard');
    if (btn) btn.textContent = '🏁 Fondo: Cuadrícula';
    showToast('Fondo cambiado a Cuadrícula Transparente');
  } else {
    stageBgMode = 'dark';
    canvas.classList.remove('bg-checkerboard');
    canvas.classList.add('bg-dark');
    if (btn) btn.textContent = '🏁 Fondo: Oscuro';
    showToast('Fondo cambiado a Oscuro OBS');
  }
}

let layersPanelVisible = false;
function toggleLayersPanel() {
  layersPanelVisible = !layersPanelVisible;
  const panel = document.getElementById('stageLayersPanel');
  const btn = document.getElementById('btnToggleLayers');
  if (panel) {
    panel.style.display = layersPanelVisible ? 'block' : 'none';
    if (layersPanelVisible) renderLayersList();
  }
  if (btn) btn.classList.toggle('btn-accent', layersPanelVisible);
}

function renderLayersList() {
  const listEl = document.getElementById('stageLayersList');
  const fullListEl = document.getElementById('inspectorLayersFullList');

  const items = [
    { id: 'now_playing', name: 'Now Playing', icon: '🎵', type: 'now_playing', z: config.overlay_now_playing_z_index !== undefined ? Number(config.overlay_now_playing_z_index) : 30, enabled: config.overlay_now_playing_enabled !== false },
    { id: 'timer', name: 'Temporizador', icon: '⏱️', type: 'timer', z: config.overlay_timer_z_index !== undefined ? Number(config.overlay_timer_z_index) : 20, enabled: config.overlay_timer_enabled !== false },
    { id: 'lyrics', name: 'Letras en Vivo', icon: '📜', type: 'lyrics', z: config.overlay_lyrics_z_index !== undefined ? Number(config.overlay_lyrics_z_index) : 15, enabled: config.overlay_show_lyrics === true }
  ];
  (config.overlay_custom_texts || []).forEach((t, i) => {
    items.push({
      id: 'custom_text_' + t.id,
      name: t.text ? (t.text.length > 22 ? t.text.substring(0, 22) + '...' : t.text) : `Texto #${i+1}`,
      icon: '🔤',
      type: 'custom_text',
      txtId: t.id,
      z: t.z_index !== undefined ? Number(t.z_index) : 25,
      enabled: true
    });
  });

  items.sort((a, b) => b.z - a.z);

  const maxZ = items.length ? Math.max(...items.map(it => it.z)) : 30;
  const minZ = items.length ? Math.min(...items.map(it => it.z)) : 10;

  if (listEl) {
    listEl.innerHTML = items.map((it, idx) => `
      <div style="display:flex; align-items:center; justify-content:space-between; padding:6px 8px; border-radius:6px; background:${currentSelectedModule === it.id ? 'rgba(232,255,71,0.18)' : 'rgba(255,255,255,0.04)'}; border:1px solid ${currentSelectedModule === it.id ? 'var(--accent)' : 'rgba(255,255,255,0.08)'}; font-size:11px; cursor:pointer;" onclick="selectStageElement('${it.id}')">
        <div style="display:flex; align-items:center; gap:6px;">
          <span style="font-family:'Space Mono',monospace; font-weight:700; color:var(--muted); font-size:10px;">#${idx + 1}</span>
          <span style="font-weight:700; color:${currentSelectedModule === it.id ? 'var(--accent)' : '#fff'};">${it.icon} ${escapeHtml(it.name)}</span>
        </div>
        <div style="display:flex; align-items:center; gap:4px;" onclick="event.stopPropagation()">
          <span style="font-family:'Space Mono',monospace; font-size:10px; color:var(--accent); font-weight:700; min-width:24px; text-align:right;">${it.z}</span>
          <button class="btn btn-sm" style="padding:1px 5px; font-size:10px;" onclick="changeModuleLayer('${it.id}', 5)" title="Subir nivel">▲</button>
          <button class="btn btn-sm" style="padding:1px 5px; font-size:10px;" onclick="changeModuleLayer('${it.id}', -5)" title="Bajar nivel">▼</button>
        </div>
      </div>
    `).join('');
  }

  if (fullListEl) {
    fullListEl.innerHTML = items.map((it, idx) => `
      <div style="display:flex; flex-direction:column; gap:8px; padding:10px 12px; border-radius:8px; background:${currentSelectedModule === it.id ? 'rgba(232,255,71,0.12)' : 'rgba(255,255,255,0.03)'}; border:1px solid ${currentSelectedModule === it.id ? 'var(--accent)' : 'rgba(255,255,255,0.08)'};">
        <div style="display:flex; align-items:center; justify-content:space-between;">
          <div style="display:flex; align-items:center; gap:8px; cursor:pointer;" onclick="selectStageElement('${it.id}')">
            <span style="font-family:'Space Mono',monospace; font-size:11px; font-weight:800; color:var(--muted);">#${idx + 1}</span>
            <span style="font-size:16px;">${it.icon}</span>
            <div style="display:flex; flex-direction:column;">
              <span style="font-weight:800; font-size:13px; color:${currentSelectedModule === it.id ? 'var(--accent)' : '#fff'};">${escapeHtml(it.name)}</span>
              <span style="font-size:10px; color:var(--muted);">${idx === 0 ? '🔝 Capa superior (al frente de la pantalla)' : (idx === items.length - 1 ? '🔻 Capa inferior (al fondo)' : 'Nivel intermedio')}</span>
            </div>
          </div>
          <span style="font-family:'Space Mono',monospace; font-size:12px; font-weight:800; color:var(--accent); background:rgba(232,255,71,0.12); padding:3px 8px; border-radius:4px; border:1px solid rgba(232,255,71,0.3);">Z: ${it.z}</span>
        </div>

        <div style="display:flex; align-items:center; justify-content:space-between; gap:6px; border-top:1px solid rgba(255,255,255,0.06); padding-top:8px;">
          <div style="display:flex; gap:4px;">
            <button class="btn btn-sm btn-accent" style="padding:3px 9px; font-size:11px;" onclick="changeModuleLayer('${it.id}', 5)" title="Subir capa (traer adelante)">⬆️ Subir</button>
            <button class="btn btn-sm" style="padding:3px 9px; font-size:11px;" onclick="changeModuleLayer('${it.id}', -5)" title="Bajar capa (enviar atrás)">⬇️ Bajar</button>
            <button class="btn btn-sm" style="padding:3px 7px; font-size:10px;" onclick="setModuleLayer('${it.id}', ${maxZ + 5})" title="Poner al frente de todo">🔝 Al Frente</button>
            <button class="btn btn-sm" style="padding:3px 7px; font-size:10px;" onclick="setModuleLayer('${it.id}', ${Math.max(1, minZ - 5)})" title="Poner al fondo de todo">🔻 Al Fondo</button>
          </div>
          <button class="btn btn-sm" style="padding:3px 8px; font-size:11px;" onclick="selectStageElement('${it.id}')" title="Configurar elemento">🎯 Configurar</button>
        </div>
      </div>
    `).join('');
  }
}

function setModuleLayer(modId, val) {
  val = Math.max(1, Math.min(999, parseInt(val, 10) || 10));
  if (modId === 'now_playing') {
    config.overlay_now_playing_z_index = val;
    const inp = document.getElementById('modNpZIndex');
    const badge = document.getElementById('modNpZVal');
    if (inp) inp.value = val;
    if (badge) badge.textContent = val;
  } else if (modId === 'timer') {
    config.overlay_timer_z_index = val;
    const inp = document.getElementById('modTmZIndex');
    const badge = document.getElementById('modTmZVal');
    if (inp) inp.value = val;
    if (badge) badge.textContent = val;
  } else if (modId === 'lyrics') {
    config.overlay_lyrics_z_index = val;
    const inp = document.getElementById('modLyZIndex');
    const badge = document.getElementById('modLyZVal');
    if (inp) inp.value = val;
    if (badge) badge.textContent = val;
  } else if (modId.startsWith('custom_text_')) {
    const txtId = modId.replace('custom_text_', '');
    const item = (config.overlay_custom_texts || []).find(t => t.id === txtId);
    if (item) item.z_index = val;
  }
  updateStageMockups();
  renderLayersList();
  scheduleModularConfigSave();
}

function changeModuleLayer(modId, delta) {
  let currentVal = 20;
  if (modId === 'now_playing') currentVal = config.overlay_now_playing_z_index !== undefined ? config.overlay_now_playing_z_index : 30;
  else if (modId === 'timer') currentVal = config.overlay_timer_z_index !== undefined ? config.overlay_timer_z_index : 20;
  else if (modId === 'lyrics') currentVal = config.overlay_lyrics_z_index !== undefined ? config.overlay_lyrics_z_index : 15;
  else if (modId.startsWith('custom_text_')) {
    const txtId = modId.replace('custom_text_', '');
    const item = (config.overlay_custom_texts || []).find(t => t.id === txtId);
    if (item) currentVal = item.z_index !== undefined ? item.z_index : 25;
  }
  setModuleLayer(modId, currentVal + delta);
}

function alignActiveModule(alignment) {
  const modId = currentSelectedModule || 'now_playing';
  const canvasW = 1920;
  const canvasH = 1080;
  const pad = 48;

  const isTL = (alignment === 'tl' || alignment === 'top-left');
  const isTR = (alignment === 'tr' || alignment === 'top-right');
  const isBL = (alignment === 'bl' || alignment === 'bottom-left');
  const isBR = (alignment === 'br' || alignment === 'bottom-right');
  const isCenter = (alignment === 'center' || alignment === 'c');

  if (modId === 'now_playing') {
    const w = parseInt(config.overlay_now_playing_width || 380, 10);
    const h = 76;
    let nx = Number(config.overlay_now_playing_x) || 40;
    let ny = Number(config.overlay_now_playing_y) || 40;

    if (isTL) { nx = pad; ny = canvasH - h - pad; }
    else if (isTR) { nx = canvasW - w - pad; ny = canvasH - h - pad; }
    else if (isBL) { nx = pad; ny = pad; }
    else if (isBR) { nx = canvasW - w - pad; ny = pad; }
    else if (isCenter) { nx = Math.round((canvasW - w) / 2); ny = Math.round((canvasH - h) / 2); }

    config.overlay_now_playing_x = nx;
    config.overlay_now_playing_y = ny;
    const inpX = document.getElementById('modNpX');
    const inpY = document.getElementById('modNpY');
    if (inpX) inpX.value = nx;
    if (inpY) inpY.value = ny;
    showToast(`Now Playing alineado: ${alignment}`);
  } else if (modId === 'timer') {
    const w = parseInt(config.overlay_timer_width || 560, 10);
    const h = 260;
    let nx = Number(config.overlay_timer_x) || 680;
    let ny = Number(config.overlay_timer_y) || 320;

    if (isTL) { nx = pad; ny = pad; }
    else if (isTR) { nx = canvasW - w - pad; ny = pad; }
    else if (isBL) { nx = pad; ny = canvasH - h - pad; }
    else if (isBR) { nx = canvasW - w - pad; ny = canvasH - h - pad; }
    else if (isCenter) { nx = Math.round((canvasW - w) / 2); ny = Math.round((canvasH - h) / 2); }

    config.overlay_timer_x = nx;
    config.overlay_timer_y = ny;
    const inpX = document.getElementById('modTmX');
    const inpY = document.getElementById('modTmY');
    if (inpX) inpX.value = nx;
    if (inpY) inpY.value = ny;
    showToast(`Temporizador alineado: ${alignment}`);
  } else if (modId === 'lyrics') {
    const w = parseInt(config.overlay_lyrics_width || 440, 10);
    const h = parseInt(config.overlay_lyrics_max_height || 150, 10);
    let nx = Number(config.overlay_lyrics_x) || 40;
    let ny = Number(config.overlay_lyrics_y) || 130;

    if (isTL) { nx = pad; ny = canvasH - h - pad; }
    else if (isTR) { nx = canvasW - w - pad; ny = canvasH - h - pad; }
    else if (isBL) { nx = pad; ny = pad; }
    else if (isBR) { nx = canvasW - w - pad; ny = pad; }
    else if (isCenter) { nx = Math.round((canvasW - w) / 2); ny = Math.round((canvasH - h) / 2); }

    config.overlay_lyrics_x = nx;
    config.overlay_lyrics_y = ny;
    const inpX = document.getElementById('modLyX');
    const inpY = document.getElementById('modLyY');
    if (inpX) inpX.value = nx;
    if (inpY) inpY.value = ny;
    showToast(`Letras alineadas: ${alignment}`);
  } else if (modId.startsWith('custom_text_')) {
    const txtId = modId.replace('custom_text_', '');
    const item = (config.overlay_custom_texts || []).find(t => t.id === txtId);
    if (item) {
      const w = 320;
      const h = 50;
      let nx = Number(item.x) || 100;
      let ny = Number(item.y) || 100;

      if (isTL) { nx = pad; ny = pad; }
      else if (isTR) { nx = canvasW - w - pad; ny = pad; }
      else if (isBL) { nx = pad; ny = canvasH - h - pad; }
      else if (isBR) { nx = canvasW - w - pad; ny = pad; }
      else if (isCenter) { nx = Math.round((canvasW - w) / 2); ny = Math.round((canvasH - h) / 2); }

      item.x = nx;
      item.y = ny;
      showToast(`Texto alineado: ${alignment}`);
    }
  }

  updateStageMockups();
  scheduleModularConfigSave();
}

function resetOverlayPositions() {
  config.overlay_now_playing_x = 40;
  config.overlay_now_playing_y = 40;
  config.overlay_timer_x = 680;
  config.overlay_timer_y = 320;
  config.overlay_lyrics_x = 40;
  config.overlay_lyrics_y = 130;

  (config.overlay_custom_texts || []).forEach((text, index) => {
    text.x = 400 + (index % 3) * 180;
    text.y = 180 + Math.floor(index / 3) * 90;
  });

  initOverlayStudio();
  updateStageMockups();
  scheduleModularConfigSave(true);
  showToast('Posiciones de overlays restauradas');
}

function setStudioMode(mode) {
  const visualBtn = document.getElementById('btnStudioModeVisual');
  const timerBtn = document.getElementById('btnStudioModeTimer');
  const visualContainer = document.getElementById('studioVisualContainer');
  const timerContainer = document.getElementById('studioTimerOpContainer');
  const simToggles = document.getElementById('studioSimToggles');
  const mobileSwitcher = document.getElementById('overlayMobileSwitcher');
  const visualActions = document.getElementById('studioVisualActions');

  if (mode === 'visual') {
    if (visualBtn) visualBtn.className = 'btn btn-sm btn-accent';
    if (timerBtn) timerBtn.className = 'btn btn-sm';
    if (visualContainer) visualContainer.style.display = 'flex';
    if (timerContainer) timerContainer.style.display = 'none';
    if (simToggles) simToggles.style.display = 'flex';
    if (mobileSwitcher) mobileSwitcher.style.display = '';
    if (visualActions) visualActions.style.display = '';
    requestAnimationFrame(updateStageMockups);
  } else {
    if (visualBtn) visualBtn.className = 'btn btn-sm';
    if (timerBtn) timerBtn.className = 'btn btn-sm btn-accent';
    if (visualContainer) visualContainer.style.display = 'none';
    if (timerContainer) timerContainer.style.display = 'block';
    if (simToggles) simToggles.style.display = 'none';
    if (mobileSwitcher) mobileSwitcher.style.display = 'none';
    if (visualActions) visualActions.style.display = 'none';
  }
}

function setOverlayMobileView(target) {
  const container = document.getElementById('studioVisualContainer');
  const btnControls = document.getElementById('btnMobileOverlayControls');
  const btnCanvas = document.getElementById('btnMobileOverlayCanvas');
  if (!container) return;

  if (target === 'canvas') {
    container.classList.remove('mobile-view-controls');
    container.classList.add('mobile-view-canvas');
    if (btnCanvas) {
      btnCanvas.classList.add('btn-accent', 'active');
    }
    if (btnControls) {
      btnControls.classList.remove('btn-accent', 'active');
    }
    if (typeof updateStageMockups === 'function') {
      requestAnimationFrame(updateStageMockups);
    }
  } else {
    container.classList.remove('mobile-view-canvas');
    container.classList.add('mobile-view-controls');
    if (btnCanvas) {
      btnCanvas.classList.remove('btn-accent', 'active');
    }
    if (btnControls) {
      btnControls.classList.add('btn-accent', 'active');
    }
  }
}
window.setOverlayMobileView = setOverlayMobileView;

function toggleSimModule(mod, visible) {
  if (mod === 'now_playing') {
    const el = document.getElementById('stageNowPlaying');
    if (el) el.style.display = visible ? 'flex' : 'none';
  } else if (mod === 'timer') {
    const el = document.getElementById('stageTimer');
    if (el) el.style.display = visible ? 'flex' : 'none';
  } else if (mod === 'lyrics') {
    const el = document.getElementById('stageLyrics');
    if (el) el.style.display = visible ? 'flex' : 'none';
  }
}

function switchInspectorTab(tabKey, updateSelection = true) {
  const tabs = {
    'layers': { tab: 'tabInspLayers', pane: 'paneInspLayers', stageId: null, label: '📑 Orden de Capas (Z-Index)' },
    'now_playing': { tab: 'tabInspNp', pane: 'paneInspNowPlaying', stageId: 'stageNowPlaying', label: '🎵 Música (Now Playing)' },
    'timer': { tab: 'tabInspTimer', pane: 'paneInspTimer', stageId: 'stageTimer', label: '⏱️ Temporizador' },
    'lyrics': { tab: 'tabInspLyrics', pane: 'paneInspLyrics', stageId: 'stageLyrics', label: '📜 Letras en Pantalla' },
    'custom_texts': { tab: 'tabInspTexts', pane: 'paneInspTexts', stageId: null, label: '🔤 Textos Modulares' }
  };

  Object.entries(tabs).forEach(([k, info]) => {
    const t = document.getElementById(info.tab);
    const p = document.getElementById(info.pane);
    if (t) t.classList.toggle('active', k === tabKey);
    if (p) p.style.display = (k === tabKey) ? 'flex' : 'none';
  });

  const activeLabelEl = document.getElementById('inspectorActiveModuleTag');
  if (activeLabelEl && tabs[tabKey]) {
    activeLabelEl.textContent = tabs[tabKey].label;
  }

  const statusBadge = document.getElementById('inspectorActiveStatusBadge');
  if (statusBadge) {
    let isVis = true;
    if (tabKey === 'now_playing') {
      const chk = document.getElementById('modNpEnabled');
      isVis = chk ? chk.checked : true;
    } else if (tabKey === 'timer') {
      const chk = document.getElementById('modTmEnabled');
      isVis = chk ? chk.checked : true;
    } else if (tabKey === 'lyrics') {
      const chk = document.getElementById('modLyEnabled');
      isVis = chk ? chk.checked : true;
    }
    statusBadge.textContent = isVis ? '🟢 Visible' : '⚪ Oculto';
    statusBadge.classList.toggle('disabled', !isVis);
  }

  if (tabKey === 'layers') {
    renderLayersList();
  }

  if (updateSelection && tabs[tabKey] && tabs[tabKey].stageId) {
    selectStageElement(tabKey);
  }
}

function selectStageElement(modId) {
  currentSelectedModule = modId;
  document.querySelectorAll('.stage-item').forEach(el => el.classList.remove('selected'));
  let targetEl = null;
  let label = 'Now Playing';

  if (modId === 'now_playing') {
    targetEl = document.getElementById('stageNowPlaying');
    switchInspectorTab('now_playing', false);
    label = 'Now Playing';
  } else if (modId === 'timer') {
    targetEl = document.getElementById('stageTimer');
    switchInspectorTab('timer', false);
    label = 'Temporizador';
  } else if (modId === 'lyrics') {
    targetEl = document.getElementById('stageLyrics');
    switchInspectorTab('lyrics', false);
    label = 'Letras';
  } else if (modId.startsWith('custom_text_')) {
    const txtId = modId.replace('custom_text_', '');
    targetEl = document.getElementById('stageCustomText_' + txtId);
    switchInspectorTab('custom_texts', false);
    const item = (config.overlay_custom_texts || []).find(t => t.id === txtId);
    label = item && item.text ? `Texto: "${item.text.substring(0, 16)}"` : 'Texto Modular';
  }

  if (targetEl) targetEl.classList.add('selected');
  const badge = document.getElementById('stageActiveElementName');
  if (badge) badge.textContent = label;
  const inspTag = document.getElementById('inspectorActiveModuleTag');
  if (inspTag) inspTag.textContent = label;
  renderLayersList();
}

function showStageTooltip(x, y, text) {
  const tt = document.getElementById('stageTooltip');
  if (!tt) return;
  const canvas = document.getElementById('stageCanvas');
  const rect = canvas ? canvas.getBoundingClientRect() : { left: 0, top: 0 };
  tt.style.left = (x - rect.left + 14) + 'px';
  tt.style.top = (y - rect.top + 14) + 'px';
  tt.textContent = text;
  tt.classList.add('visible');
}

function hideStageTooltip() {
  const tt = document.getElementById('stageTooltip');
  if (tt) tt.classList.remove('visible');
}

function centerTimerModule() {
  alignActiveModule('center');
}

function updateModularProp(mod, prop, val) {
  if (mod === 'now_playing') {
    if (prop === 'enabled') {
      config.overlay_now_playing_enabled = val;
    } else if (prop === 'x') {
      config.overlay_now_playing_x = parseInt(val, 10) || 0;
    } else if (prop === 'y') {
      config.overlay_now_playing_y = parseInt(val, 10) || 0;
    } else if (prop === 'scale') {
      config.overlay_now_playing_scale = parseFloat(val) || 1.0;
      const lb = document.getElementById('modNpScaleVal');
      if (lb) lb.textContent = config.overlay_now_playing_scale.toFixed(2) + 'x';
    } else if (prop === 'width') {
      config.overlay_now_playing_width = parseInt(val, 10) || 380;
    } else if (prop === 'bg_color') {
      config.overlay_now_playing_bg_color = val;
    } else if (prop === 'bg_opacity') {
      config.overlay_now_playing_bg_opacity = parseInt(val, 10) || 0;
      const lb = document.getElementById('modNpOpVal');
      if (lb) lb.textContent = val + '%';
    } else if (prop === 'border_color') {
      config.overlay_now_playing_border_color = val;
    } else if (prop === 'border_radius') {
      config.overlay_now_playing_border_radius = parseInt(val, 10) || 0;
      const lb = document.getElementById('modNpRadiusVal');
      if (lb) lb.textContent = val + 'px';
    } else if (prop === 'font') {
      config.overlay_now_playing_font = val;
    } else if (prop === 'text_color') {
      config.overlay_now_playing_text_color = val;
    } else if (prop === 'marquee') {
      config.overlay_now_playing_marquee = Boolean(val);
    } else if (prop === 'wave') {
      config.overlay_now_playing_wave = parseInt(val, 10) || 0;
      const lb = document.getElementById('modNpWaveVal');
      if (lb) lb.textContent = val;
    } else if (prop === 'show_cover') {
      config.overlay_show_cover = Boolean(val);
    } else if (prop === 'show_badge') {
      config.overlay_show_badge = Boolean(val);
    } else if (prop === 'show_title') {
      config.overlay_show_song_title = Boolean(val);
      config.overlay_show_title = Boolean(val);
    } else if (prop === 'show_artist') {
      config.overlay_show_artist = Boolean(val);
    } else if (prop === 'show_equalizer') {
      config.overlay_show_equalizer = Boolean(val);
    } else if (prop === 'title_size') {
      config.overlay_now_playing_title_size = parseInt(val, 10) || 13;
    } else if (prop === 'artist_size') {
      config.overlay_now_playing_artist_size = parseInt(val, 10) || 11;
    } else if (prop === 'badge_size') {
      config.overlay_now_playing_badge_size = parseInt(val, 10) || 9;
    }
  } else if (mod === 'timer') {
    if (prop === 'enabled') {
      config.overlay_timer_enabled = val;
    } else if (prop === 'x') {
      config.overlay_timer_x = parseInt(val, 10) || 0;
    } else if (prop === 'y') {
      config.overlay_timer_y = parseInt(val, 10) || 0;
    } else if (prop === 'scale') {
      config.overlay_timer_scale = parseFloat(val) || 1.0;
      const lb = document.getElementById('modTmScaleVal');
      if (lb) lb.textContent = config.overlay_timer_scale.toFixed(2) + 'x';
    } else if (prop === 'width') {
      config.overlay_timer_width = parseInt(val, 10) || 560;
    } else if (prop === 'bg_color') {
      config.overlay_timer_bg_color = val;
    } else if (prop === 'bg_opacity') {
      config.overlay_timer_bg_opacity = parseInt(val, 10) || 0;
      const lb = document.getElementById('modTmOpVal');
      if (lb) lb.textContent = val + '%';
    } else if (prop === 'border_color') {
      config.overlay_timer_border_color = val;
    } else if (prop === 'border_radius') {
      config.overlay_timer_border_radius = parseInt(val, 10) || 0;
      const lb = document.getElementById('modTmRadiusVal');
      if (lb) lb.textContent = val + 'px';
    } else if (prop === 'badge_text') {
      config.overlay_timer_badge_text = val;
    } else if (prop === 'badge_color') {
      config.overlay_timer_badge_color = val;
    } else if (prop === 'title_text') {
      config.overlay_timer_title_text = val;
    } else if (prop === 'title_color') {
      config.overlay_timer_title_color = val;
    } else if (prop === 'clock_color') {
      config.overlay_timer_clock_color = val;
    } else if (prop === 'progress_color') {
      config.overlay_timer_progress_color = val;
    } else if (prop === 'phrase_color') {
      config.overlay_timer_phrase_color = val;
    } else if (prop === 'clock_size') {
      config.overlay_timer_clock_size = parseInt(val, 10) || 72;
    } else if (prop === 'title_size') {
      config.overlay_timer_title_size = parseInt(val, 10) || 30;
    } else if (prop === 'badge_size') {
      config.overlay_timer_badge_size = parseInt(val, 10) || 12;
    } else if (prop === 'phrase_size') {
      config.overlay_timer_phrase_size = parseInt(val, 10) || 14;
    } else if (prop === 'clock_font') {
      config.overlay_timer_clock_font = val;
    } else if (prop === 'title_font') {
      config.overlay_timer_title_font = val;
    } else if (prop === 'badge_font') {
      config.overlay_timer_badge_font = val;
    } else if (prop === 'phrase_font') {
      config.overlay_timer_phrase_font = val;
    } else if (prop === 'img_enabled') {
      config.overlay_timer_image_enabled = Boolean(val);
    } else if (prop === 'img_url') {
      config.overlay_timer_image_url = val;
    } else if (prop === 'img_x') {
      config.overlay_timer_image_x = parseInt(val, 10) || 0;
    } else if (prop === 'img_y') {
      config.overlay_timer_image_y = parseInt(val, 10) || 0;
    } else if (prop === 'img_scale') {
      config.overlay_timer_image_scale = parseFloat(val) || 1.0;
      const lb = document.getElementById('modTmImgScaleVal');
      if (lb) lb.textContent = config.overlay_timer_image_scale.toFixed(2) + 'x';
    } else if (prop === 'img_radius') {
      config.overlay_timer_image_radius = parseInt(val, 10) || 0;
    } else if (prop === 'show_badge') {
      config.overlay_timer_show_badge = Boolean(val);
    } else if (prop === 'show_title') {
      config.overlay_timer_show_title = Boolean(val);
    } else if (prop === 'show_clock') {
      config.overlay_timer_show_clock = Boolean(val);
    } else if (prop === 'show_progress') {
      config.overlay_timer_show_progress = Boolean(val);
    } else if (prop === 'show_phrase') {
      config.overlay_timer_show_phrase = Boolean(val);
    }
  } else if (mod === 'lyrics') {
    if (prop === 'enabled') {
      config.overlay_show_lyrics = Boolean(val);
    } else if (prop === 'x') {
      config.overlay_lyrics_x = parseInt(val, 10) || 0;
    } else if (prop === 'y') {
      config.overlay_lyrics_y = parseInt(val, 10) || 0;
    } else if (prop === 'scale') {
      config.overlay_lyrics_scale = parseFloat(val) || 1.0;
      const lb = document.getElementById('modLyScaleVal');
      if (lb) lb.textContent = config.overlay_lyrics_scale.toFixed(2) + 'x';
    } else if (prop === 'width') {
      config.overlay_lyrics_width = parseInt(val, 10) || 440;
    } else if (prop === 'max_height') {
      config.overlay_lyrics_max_height = parseInt(val, 10) || 150;
    } else if (prop === 'bg_color') {
      config.overlay_lyrics_bg_color = val;
    } else if (prop === 'bg_opacity') {
      config.overlay_lyrics_bg_opacity = parseInt(val, 10) || 0;
      const lb = document.getElementById('modLyOpVal');
      if (lb) lb.textContent = val + '%';
    } else if (prop === 'text_color') {
      config.overlay_lyrics_text_color = val;
    } else if (prop === 'font_size') {
      config.overlay_lyrics_font_size = parseInt(val, 10) || 13;
    } else if (prop === 'mode') {
      config.overlay_lyrics_mode = val;
    } else if (prop === 'highlight_color') {
      config.overlay_lyrics_highlight_color = val;
    }
  }

  updateStageMockups();
  scheduleModularConfigSave();
}

function onStagePointerDown(e, modId) {
  if (e.target && e.target.classList.contains('resize-handle')) return;
  if (e.button !== undefined && e.button !== 0) return;

  try { e.preventDefault(); } catch(err){}
  try { e.stopPropagation(); } catch(err){}

  isDraggingStage = true;
  isResizingStage = false;
  activeStageTarget = modId;
  currentSelectedModule = modId;
  stageDragStartX = e.clientX;
  stageDragStartY = e.clientY;

  // Pointer capture para no perder nunca el seguimiento si el puntero se mueve rápido
  if (e.pointerId !== undefined && e.currentTarget && e.currentTarget.setPointerCapture) {
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
      stageCapturedEl = e.currentTarget;
      stageActivePointerId = e.pointerId;
    } catch(err){}
  }

  // Prevenir que WebKitGTK inicie un Drag-and-Drop nativo del sistema operativo
  document.ondragstart = () => false;

  selectStageElement(modId);
  updateStageMockups();

  if (modId === 'now_playing') {
    stageOrigX = Number(config.overlay_now_playing_x !== undefined ? config.overlay_now_playing_x : (config.overlay_pos_x !== undefined ? config.overlay_pos_x : 40));
    stageOrigY = Number(config.overlay_now_playing_y !== undefined ? config.overlay_now_playing_y : (config.overlay_pos_y !== undefined ? config.overlay_pos_y : 40));
  } else if (modId === 'lyrics') {
    stageOrigX = Number(config.overlay_lyrics_x !== undefined ? config.overlay_lyrics_x : 40);
    stageOrigY = Number(config.overlay_lyrics_y !== undefined ? config.overlay_lyrics_y : 130);
  } else if (modId === 'timer') {
    stageOrigX = Number(config.overlay_timer_x !== undefined ? config.overlay_timer_x : 680);
    stageOrigY = Number(config.overlay_timer_y !== undefined ? config.overlay_timer_y : 320);
  } else if (modId.startsWith('custom_text_')) {
    const txtId = modId.replace('custom_text_', '');
    const item = (config.overlay_custom_texts || []).find(t => t.id === txtId);
    stageOrigX = Number(item && item.x !== undefined ? item.x : 100);
    stageOrigY = Number(item && item.y !== undefined ? item.y : 100);
  }

  showStageTooltip(e.clientX, e.clientY, `X: ${stageOrigX}px | Y: ${stageOrigY}px`);
}

function onResizePointerDown(e, modId) {
  if (e.button !== undefined && e.button !== 0) return;
  try { e.preventDefault(); } catch(err){}
  try { e.stopPropagation(); } catch(err){}

  isResizingStage = true;
  isDraggingStage = false;
  activeStageTarget = modId;
  currentSelectedModule = modId;
  stageDragStartX = e.clientX;
  stageDragStartY = e.clientY;

  if (e.pointerId !== undefined && e.currentTarget && e.currentTarget.setPointerCapture) {
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
      stageCapturedEl = e.currentTarget;
      stageActivePointerId = e.pointerId;
    } catch(err){}
  }

  document.ondragstart = () => false;

  selectStageElement(modId);
  updateStageMockups();

  if (modId === 'now_playing') {
    stageOrigScale = parseFloat(config.overlay_now_playing_scale !== undefined ? config.overlay_now_playing_scale : (config.overlay_scale || 1.0));
  } else if (modId === 'timer') {
    stageOrigScale = parseFloat(config.overlay_timer_scale || 1.0);
  } else if (modId === 'lyrics') {
    stageOrigScale = parseFloat(config.overlay_lyrics_scale || 1.0);
  } else if (modId.startsWith('custom_text_')) {
    const txtId = modId.replace('custom_text_', '');
    const item = (config.overlay_custom_texts || []).find(t => t.id === txtId);
    stageOrigScale = parseFloat(item && item.scale !== undefined ? item.scale : 1.0);
  }
}

function handleGlobalStageMove(clientX, clientY) {
  if (!isDraggingStage && !isResizingStage) return;
  if (!activeStageTarget) return;

  const canvas = document.getElementById('stageCanvas');
  if (!canvas) return;
  const canvasW = canvas.offsetWidth || canvas.getBoundingClientRect().width || 960;
  const stageScale = Math.max(0.1, canvasW / (obsBaseWidth || 1920));

  if (isDraggingStage) {
    const dx = (clientX - stageDragStartX) / stageScale;
    const dy = (clientY - stageDragStartY) / stageScale;

    if (activeStageTarget === 'now_playing') {
      const newX = Math.round(Math.max(0, Math.min(1820, stageOrigX + dx)));
      const newY = Math.round(Math.max(0, Math.min(1020, stageOrigY - dy)));
      config.overlay_now_playing_x = newX;
      config.overlay_now_playing_y = newY;
      const inpX = document.getElementById('modNpX');
      const inpY = document.getElementById('modNpY');
      if (inpX) inpX.value = newX;
      if (inpY) inpY.value = newY;
      const el = document.getElementById('stageNowPlaying');
      if (el) {
        el.style.left = (newX * stageScale) + 'px';
        el.style.bottom = (newY * stageScale) + 'px';
        el.style.top = '';
      }
      showStageTooltip(clientX, clientY, `🎵 Now Playing: X: ${newX}px, Y: ${newY}px`);
    } else if (activeStageTarget === 'lyrics') {
      const newX = Math.round(Math.max(0, Math.min(1820, stageOrigX + dx)));
      const newY = Math.round(Math.max(0, Math.min(1020, stageOrigY - dy)));
      config.overlay_lyrics_x = newX;
      config.overlay_lyrics_y = newY;
      const inpX = document.getElementById('modLyX');
      const inpY = document.getElementById('modLyY');
      if (inpX) inpX.value = newX;
      if (inpY) inpY.value = newY;
      const el = document.getElementById('stageLyrics');
      if (el) {
        el.style.left = (newX * stageScale) + 'px';
        el.style.bottom = (newY * stageScale) + 'px';
        el.style.top = '';
      }
      showStageTooltip(clientX, clientY, `📜 Letras: X: ${newX}px, Y: ${newY}px`);
    } else if (activeStageTarget === 'timer') {
      const newX = Math.round(Math.max(0, Math.min(1720, stageOrigX + dx)));
      const newY = Math.round(Math.max(0, Math.min(980, stageOrigY + dy)));
      config.overlay_timer_x = newX;
      config.overlay_timer_y = newY;
      const inpX = document.getElementById('modTmX');
      const inpY = document.getElementById('modTmY');
      if (inpX) inpX.value = newX;
      if (inpY) inpY.value = newY;
      const el = document.getElementById('stageTimer');
      if (el) {
        const sc = parseFloat(config.overlay_timer_scale || 1.0);
        el.style.left = (newX * stageScale) + 'px';
        el.style.top = (newY * stageScale) + 'px';
        el.style.bottom = '';
        el.style.transform = `scale(${stageScale * sc})`;
        el.style.transformOrigin = 'top left';
      }
      showStageTooltip(clientX, clientY, `⏱️ Temporizador: X: ${newX}px, Y: ${newY}px`);
    } else if (activeStageTarget.startsWith('custom_text_')) {
      const txtId = activeStageTarget.replace('custom_text_', '');
      const item = (config.overlay_custom_texts || []).find(t => t.id === txtId);
      if (item) {
        const newX = Math.round(Math.max(0, Math.min(1860, stageOrigX + dx)));
        const newY = Math.round(Math.max(0, Math.min(1050, stageOrigY + dy)));
        item.x = newX;
        item.y = newY;
        const el = document.getElementById(`stageCustomText_${txtId}`);
        if (el) {
          el.style.left = (newX * stageScale) + 'px';
          el.style.top = (newY * stageScale) + 'px';
          el.style.bottom = '';
        }
        showStageTooltip(clientX, clientY, `🔤 Texto: X: ${newX}px, Y: ${newY}px`);
      }
    }
  } else if (isResizingStage) {
    const dx = clientX - stageDragStartX;
    const ds = dx / 160;
    const newScale = Math.max(0.4, Math.min(2.5, +(stageOrigScale + ds).toFixed(2)));

    if (activeStageTarget === 'now_playing') {
      config.overlay_now_playing_scale = newScale;
      const sl = document.getElementById('modNpScale');
      const lb = document.getElementById('modNpScaleVal');
      if (sl) sl.value = newScale;
      if (lb) lb.textContent = newScale.toFixed(2) + 'x';
      const el = document.getElementById('stageNowPlaying');
      if (el) el.style.transform = `scale(${stageScale * newScale})`;
      showStageTooltip(clientX, clientY, `Escala Now Playing: ${newScale}x`);
    } else if (activeStageTarget === 'timer') {
      config.overlay_timer_scale = newScale;
      const sl = document.getElementById('modTmScale');
      const lb = document.getElementById('modTmScaleVal');
      if (sl) sl.value = newScale;
      if (lb) lb.textContent = newScale.toFixed(2) + 'x';
      const el = document.getElementById('stageTimer');
      if (el) el.style.transform = `scale(${stageScale * newScale})`;
      showStageTooltip(clientX, clientY, `Escala Temporizador: ${newScale}x`);
    } else if (activeStageTarget === 'lyrics') {
      config.overlay_lyrics_scale = newScale;
      const sl = document.getElementById('modLyScale');
      const lb = document.getElementById('modLyScaleVal');
      if (sl) sl.value = newScale;
      if (lb) lb.textContent = newScale.toFixed(2) + 'x';
      const el = document.getElementById('stageLyrics');
      if (el) el.style.transform = `scale(${stageScale * newScale})`;
      showStageTooltip(clientX, clientY, `Escala Letras: ${newScale}x`);
    } else if (activeStageTarget.startsWith('custom_text_')) {
      const txtId = activeStageTarget.replace('custom_text_', '');
      const item = (config.overlay_custom_texts || []).find(t => t.id === txtId);
      if (item) {
        item.scale = newScale;
        const el = document.getElementById(`stageCustomText_${txtId}`);
        if (el) el.style.transform = `scale(${stageScale * newScale})`;
        showStageTooltip(clientX, clientY, `Escala Texto: ${newScale}x`);
      }
    }
  }
}

function onGlobalStagePointerMove(e) {
  if (!isDraggingStage && !isResizingStage) return;
  try { e.preventDefault(); } catch(err){}
  const cx = e.clientX;
  const cy = e.clientY;
  if (stageMoveRaf) cancelAnimationFrame(stageMoveRaf);
  stageMoveRaf = requestAnimationFrame(() => handleGlobalStageMove(cx, cy));
}

function onGlobalStagePointerUp(e) {
  if (isDraggingStage || isResizingStage) {
    isDraggingStage = false;
    isResizingStage = false;
    activeStageTarget = null;
    hideStageTooltip();
    document.ondragstart = null;
    if (stageCapturedEl && stageActivePointerId !== null) {
      try {
        if (stageCapturedEl.releasePointerCapture) {
          stageCapturedEl.releasePointerCapture(stageActivePointerId);
        }
      } catch(err){}
    }
    stageCapturedEl = null;
    stageActivePointerId = null;
    scheduleModularConfigSave();
    renderLayersList();
  }
}

// Escuchadores globales persistentes duales (Pointer + Mouse) para compatibilidad total con WebKitGTK y Firefox
window.addEventListener('pointermove', onGlobalStagePointerMove, { passive: false });
window.addEventListener('pointerup', onGlobalStagePointerUp, { passive: false });
window.addEventListener('pointercancel', onGlobalStagePointerUp, { passive: false });

function addCustomText() {
  if (!config.overlay_custom_texts) config.overlay_custom_texts = [];
  const newId = 'txt_' + Math.random().toString(36).substring(2, 8);
  const newTxt = {
    id: newId,
    text: 'Aviso o Red Social: @usuario',
    x: 400 + Math.floor(Math.random() * 200),
    y: 180 + Math.floor(Math.random() * 150),
    scale: 1.0,
    z_index: 25,
    color: '#ffffff',
    bg_color: '#0a0a0a',
    bg_opacity: 75,
    border_color: '#e8ff47',
    border_radius: 8,
    font_size: 16,
    font_family: 'system-ui',
    animation: 'none'
  };
  config.overlay_custom_texts.push(newTxt);
  switchInspectorTab('custom_texts');
  updateStageMockups();
  renderLayersList();
  selectStageElement('custom_text_' + newId);
  scheduleModularConfigSave();
  showToast('Nuevo texto agregado al lienzo');
}

function deleteCustomText(id) {
  if (!config.overlay_custom_texts) return;
  config.overlay_custom_texts = config.overlay_custom_texts.filter(t => t.id !== id);
  updateStageMockups();
  renderLayersList();
  scheduleModularConfigSave();
  showToast('Texto eliminado');
}

function updateCustomTextProp(id, prop, val) {
  if (!config.overlay_custom_texts) return;
  const item = config.overlay_custom_texts.find(t => t.id === id);
  if (!item) return;
  item[prop] = val;
  updateStageMockups();
  renderLayersList();
  scheduleModularConfigSave();
}

function updateStageMockups() {
  const canvas = document.getElementById('stageCanvas');
  if (!canvas) return;
  const parentW = canvas.parentElement ? canvas.parentElement.clientWidth : 0;
  const canvasW = canvas.offsetWidth || canvas.getBoundingClientRect().width || parentW || 960;
  const aspect = (obsBaseWidth > 0 && obsBaseHeight > 0) ? (obsBaseHeight / obsBaseWidth) : (9 / 16);
  canvas.style.height = Math.round(canvasW * aspect) + 'px';
  const scale = Math.max(0.1, canvasW / (obsBaseWidth || 1920));

  // Asegurar que los mocks de simulación estén visibles si no se han apagado
  const simNp = document.getElementById('simNowPlayingToggle');
  const simTm = document.getElementById('simTimerToggle');
  const simLy = document.getElementById('simLyricsToggle');
  if (simNp && simNp.checked) {
    const el = document.getElementById('stageNowPlaying');
    if (el && el.style.display === 'none') el.style.display = 'flex';
  }
  if (simTm && simTm.checked) {
    const el = document.getElementById('stageTimer');
    if (el && el.style.display === 'none') el.style.display = 'flex';
  }
  if (simLy && simLy.checked) {
    const el = document.getElementById('stageLyrics');
    if (el && el.style.display === 'none') el.style.display = 'flex';
  }

  // 1. NOW PLAYING
  const npEl = document.getElementById('stageNowPlaying');
  const npCard = document.getElementById('stageNpCard');
  if (npEl && npCard) {
    const npX = config.overlay_now_playing_x !== undefined ? config.overlay_now_playing_x : (config.overlay_pos_x !== undefined ? config.overlay_pos_x : 40);
    const npY = config.overlay_now_playing_y !== undefined ? config.overlay_now_playing_y : (config.overlay_pos_y !== undefined ? config.overlay_pos_y : 40);
    const npScale = parseFloat(config.overlay_now_playing_scale !== undefined ? config.overlay_now_playing_scale : (config.overlay_scale || 1.0));
    const npWidth = parseInt(config.overlay_now_playing_width || 380, 10);
    const npBg = config.overlay_now_playing_bg_color || config.overlay_bg_color || '#0a0a0a';
    const npOp = (config.overlay_now_playing_bg_opacity !== undefined ? config.overlay_now_playing_bg_opacity : (config.overlay_bg_opacity !== undefined ? config.overlay_bg_opacity : 78)) / 100;
    const npBorder = config.overlay_now_playing_border_color || config.overlay_border_color || 'rgba(255, 255, 255, 0.12)';
    const npRadius = (config.overlay_now_playing_border_radius !== undefined ? config.overlay_now_playing_border_radius : (config.overlay_border_radius !== undefined ? config.overlay_border_radius : 12)) + 'px';
    const npFont = config.overlay_now_playing_font || config.overlay_font_family || 'system-ui';
    const npTextCol = config.overlay_now_playing_text_color || config.overlay_text_color || '#ffffff';
    const npZ = config.overlay_now_playing_z_index !== undefined ? config.overlay_now_playing_z_index : 30;

    npEl.style.left = (npX * scale) + 'px';
    npEl.style.bottom = (npY * scale) + 'px';
    npEl.style.top = '';
    npEl.style.transform = `scale(${scale * npScale})`;
    npEl.style.transformOrigin = 'bottom left';
    npEl.style.opacity = (config.overlay_now_playing_enabled !== false) ? '1' : '0.4';
    npEl.style.zIndex = (currentSelectedModule === 'now_playing' ? 1000 : npZ);

    npCard.style.width = npWidth + 'px';
    npCard.style.background = hexToRgba(npBg, npOp);
    npCard.style.borderColor = npBorder;
    npCard.style.borderRadius = npRadius;
    npCard.style.fontFamily = npFont;

    const npTitleSize = (config.overlay_now_playing_title_size !== undefined ? config.overlay_now_playing_title_size : 13) + 'px';
    const npArtistSize = (config.overlay_now_playing_artist_size !== undefined ? config.overlay_now_playing_artist_size : 11) + 'px';
    const npBadgeSize = (config.overlay_now_playing_badge_size !== undefined ? config.overlay_now_playing_badge_size : 9) + 'px';

    const titleEl = document.getElementById('stageNpTitle');
    if (titleEl) {
      titleEl.style.color = npTextCol;
      titleEl.style.fontSize = npTitleSize;
      titleEl.style.display = (config.overlay_show_song_title !== false && config.overlay_show_title !== false) ? 'block' : 'none';
    }
    const artistEl = document.getElementById('stageNpArtist');
    if (artistEl) {
      artistEl.style.fontSize = npArtistSize;
      artistEl.style.display = (config.overlay_show_artist !== false) ? 'block' : 'none';
    }
    const coverEl = document.getElementById('stageNpCover');
    if (coverEl) coverEl.style.display = (config.overlay_show_cover !== false) ? 'block' : 'none';
    const badgeEl = document.getElementById('stageNpBadge');
    if (badgeEl) {
      badgeEl.style.fontSize = npBadgeSize;
      badgeEl.style.display = (config.overlay_show_badge !== false) ? 'flex' : 'none';
    }
  }

  // 2. TEMPORIZADOR
  const tmEl = document.getElementById('stageTimer');
  const tmCard = document.getElementById('stageTimerCard');
  if (tmEl && tmCard) {
    const tmX = config.overlay_timer_x !== undefined ? config.overlay_timer_x : 680;
    const tmY = config.overlay_timer_y !== undefined ? config.overlay_timer_y : 320;
    const tmScale = parseFloat(config.overlay_timer_scale || 1.0);
    const tmWidth = parseInt(config.overlay_timer_width || 560, 10);
    const tmBg = config.overlay_timer_bg_color || '#0a0a0a';
    const tmOp = (config.overlay_timer_bg_opacity !== undefined ? config.overlay_timer_bg_opacity : 85) / 100;
    const tmBorder = config.overlay_timer_border_color || 'rgba(232, 255, 71, 0.35)';
    const tmRadius = (config.overlay_timer_border_radius !== undefined ? config.overlay_timer_border_radius : 20) + 'px';
    const tmFont = config.overlay_timer_font || 'system-ui';
    const tmZ = config.overlay_timer_z_index !== undefined ? config.overlay_timer_z_index : 20;

    tmEl.style.opacity = (config.overlay_timer_enabled !== false) ? '1' : '0.4';
    tmEl.style.left = (tmX * scale) + 'px';
    tmEl.style.top = (tmY * scale) + 'px';
    tmEl.style.bottom = '';
    tmEl.style.transform = `scale(${scale * tmScale})`;
    tmEl.style.transformOrigin = 'top left';
    tmEl.style.zIndex = (currentSelectedModule === 'timer' ? 1000 : tmZ);

    tmCard.style.width = tmWidth + 'px';
    tmCard.style.background = hexToRgba(tmBg, tmOp);
    tmCard.style.borderColor = tmBorder;
    tmCard.style.borderRadius = tmRadius;
    tmCard.style.fontFamily = tmFont;

    const tmClockSize = (config.overlay_timer_clock_size !== undefined ? config.overlay_timer_clock_size : 72) + 'px';
    const tmTitleSize = (config.overlay_timer_title_size !== undefined ? config.overlay_timer_title_size : 30) + 'px';
    const tmBadgeSize = (config.overlay_timer_badge_size !== undefined ? config.overlay_timer_badge_size : 12) + 'px';
    const tmPhraseSize = (config.overlay_timer_phrase_size !== undefined ? config.overlay_timer_phrase_size : 14) + 'px';
    const tmImgEl = document.getElementById('stageTimerImage');
    if (tmImgEl) {
      if (config.overlay_timer_image_enabled && config.overlay_timer_image_url) {
        tmImgEl.style.display = 'block';
        tmImgEl.src = config.overlay_timer_image_url;
        const ix = config.overlay_timer_image_x !== undefined ? config.overlay_timer_image_x : 0;
        const iy = config.overlay_timer_image_y !== undefined ? config.overlay_timer_image_y : -100;
        const iscale = config.overlay_timer_image_scale || 1.0;
        tmImgEl.style.left = `calc(50% + ${ix}px)`;
        tmImgEl.style.top = `calc(50% + ${iy}px)`;
        tmImgEl.style.transform = `translate(-50%, -50%) scale(${iscale})`;
        tmImgEl.style.borderRadius = (config.overlay_timer_image_radius !== undefined ? config.overlay_timer_image_radius : 10) + 'px';
      } else {
        tmImgEl.style.display = 'none';
        tmImgEl.src = '';
      }
    }

    const bBadge = document.getElementById('stageTimerBadge');
    if (bBadge) {
      bBadge.style.display = (config.overlay_timer_show_badge !== false) ? 'inline-flex' : 'none';
      bBadge.style.fontSize = tmBadgeSize;
      if (config.overlay_timer_badge_font) bBadge.style.fontFamily = config.overlay_timer_badge_font;
      if (config.overlay_timer_badge_text) bBadge.textContent = config.overlay_timer_badge_text;
      if (config.overlay_timer_badge_color) {
        bBadge.style.color = config.overlay_timer_badge_color;
        bBadge.style.borderColor = config.overlay_timer_badge_color;
      }
    }

    const bTitle = document.getElementById('stageTimerTitle');
    if (bTitle) {
      bTitle.style.display = (config.overlay_timer_show_title !== false) ? 'block' : 'none';
      bTitle.style.fontSize = tmTitleSize;
      if (config.overlay_timer_title_font) bTitle.style.fontFamily = config.overlay_timer_title_font;
      if (config.overlay_timer_title_text) bTitle.textContent = config.overlay_timer_title_text;
      if (config.overlay_timer_title_color) bTitle.style.color = config.overlay_timer_title_color;
    }

    const bClock = document.getElementById('stageTimerClock');
    if (bClock) {
      bClock.style.display = (config.overlay_timer_show_clock !== false) ? 'block' : 'none';
      bClock.style.fontSize = tmClockSize;
      if (config.overlay_timer_clock_font) bClock.style.fontFamily = config.overlay_timer_clock_font;
      if (config.overlay_timer_clock_color) {
        bClock.style.color = config.overlay_timer_clock_color;
        bClock.style.textShadow = `0 0 16px ${hexToRgba(config.overlay_timer_clock_color, 0.45)}`;
      }
    }

    const bProgTrack = document.getElementById('stageTimerProgressTrack');
    const bProgBar = document.getElementById('stageTimerProgressBar');
    if (bProgTrack) bProgTrack.style.display = (config.overlay_timer_show_progress !== false) ? 'block' : 'none';
    if (bProgBar && config.overlay_timer_progress_color) bProgBar.style.background = config.overlay_timer_progress_color;

    const bPhrase = document.getElementById('stageTimerPhrase');
    if (bPhrase) {
      bPhrase.style.display = (config.overlay_timer_show_phrase !== false) ? 'block' : 'none';
      bPhrase.style.fontSize = tmPhraseSize;
      if (config.overlay_timer_phrase_color) bPhrase.style.color = config.overlay_timer_phrase_color;
      if (config.overlay_timer_phrase_font) bPhrase.style.fontFamily = config.overlay_timer_phrase_font;
    }
  }

  // 3. LYRICS (LETRAS)
  const lyEl = document.getElementById('stageLyrics');
  const lyCard = document.getElementById('stageLyricsCard');
  if (lyEl && lyCard) {
    const lyX = config.overlay_lyrics_x !== undefined ? config.overlay_lyrics_x : 40;
    const lyY = config.overlay_lyrics_y !== undefined ? config.overlay_lyrics_y : 130;
    const lyScale = parseFloat(config.overlay_lyrics_scale || 1.0);
    const lyWidth = parseInt(config.overlay_lyrics_width || 440, 10);
    const lyMaxH = parseInt(config.overlay_lyrics_max_height || 150, 10);
    const lyBg = config.overlay_lyrics_bg_color || '#0a0a0a';
    const lyOp = (config.overlay_lyrics_bg_opacity !== undefined ? config.overlay_lyrics_bg_opacity : 75) / 100;
    const lyBorder = config.overlay_lyrics_border_color || 'rgba(255, 255, 255, 0.12)';
    const lyRadius = (config.overlay_lyrics_border_radius !== undefined ? config.overlay_lyrics_border_radius : 10) + 'px';
    const lyTextCol = config.overlay_lyrics_text_color || '#e0e0e0';
    const lyFontSize = (config.overlay_lyrics_font_size || 13) + 'px';
    const lyZ = config.overlay_lyrics_z_index !== undefined ? config.overlay_lyrics_z_index : 15;

    lyEl.style.left = (lyX * scale) + 'px';
    lyEl.style.bottom = (lyY * scale) + 'px';
    lyEl.style.top = '';
    lyEl.style.transform = `scale(${scale * lyScale})`;
    lyEl.style.transformOrigin = 'bottom left';
    lyEl.style.opacity = (config.overlay_show_lyrics !== false) ? '1' : '0.4';
    lyEl.style.zIndex = (currentSelectedModule === 'lyrics' ? 1000 : lyZ);

    lyCard.style.width = lyWidth + 'px';
    lyCard.style.maxHeight = lyMaxH + 'px';
    lyCard.style.background = hexToRgba(lyBg, lyOp);
    lyCard.style.borderColor = lyBorder;
    lyCard.style.borderRadius = lyRadius;

    const lt = document.getElementById('stageLyricsText');
    if (lt) {
      lt.style.color = lyTextCol;
      lt.style.fontSize = lyFontSize;
    }
  }

  // 4. TEXTOS PERSONALIZADOS
  renderStageCustomTexts(scale);
}

function renderStageCustomTexts(scale) {
  const container = document.getElementById('stageCustomTextsContainer');
  const listEl = document.getElementById('inspectorCustomTextsList');
  const countBadge = document.getElementById('txtCountBadge');
  const texts = config.overlay_custom_texts || [];

  if (countBadge) countBadge.textContent = texts.length;

  if (container) {
    container.innerHTML = texts.map(t => {
      const posX = t.x !== undefined ? t.x : 100;
      const posY = t.y !== undefined ? t.y : 100;
      const tScale = t.scale !== undefined ? t.scale : 1.0;
      const bgOpacity = (t.bg_opacity !== undefined ? t.bg_opacity : 75) / 100;
      const bgColor = t.bg_color ? hexToRgba(t.bg_color, bgOpacity) : 'transparent';
      const border = t.border_color ? `1px solid ${t.border_color}` : 'none';
      const radius = (t.border_radius !== undefined ? t.border_radius : 8) + 'px';
      const color = t.color || '#ffffff';
      const font = t.font_family || 'system-ui';
      const size = (t.font_size || 16) + 'px';
      const tZ = t.z_index !== undefined ? t.z_index : 25;
      const isSel = currentSelectedModule === ('custom_text_' + t.id);

      return `
        <div class="stage-item${isSel ? ' selected' : ''}" id="stageCustomText_${t.id}" data-module="custom_text_${t.id}"
             ondragstart="return false;"
             onpointerdown="onStagePointerDown(event, 'custom_text_${t.id}')"
             style="left:${posX * scale}px; top:${posY * scale}px; transform:scale(${scale * tScale}); transform-origin:top left; z-index:${isSel ? 1000 : tZ};">
          <span class="stage-tag">🔤 Texto</span>
          <div style="background:${bgColor}; border:${border}; border-radius:${radius}; padding:8px 14px; color:${color}; font-family:${font}; font-size:${size}; font-weight:700; white-space:pre-wrap; max-width:500px; box-shadow:0 4px 16px rgba(0,0,0,0.4);">
            ${escapeHtml(t.text || 'Texto')}
          </div>
          <div class="resize-handle" ondragstart="return false;" onpointerdown="onResizePointerDown(event, 'custom_text_${t.id}')">⤡</div>
        </div>
      `;
    }).join('');
  }

  if (listEl) {
    if (texts.length === 0) {
      listEl.innerHTML = '<div style="font-size:11px; color:var(--muted); text-align:center; padding:16px;">No hay textos adicionales. Haz clic en "➕ Nuevo Texto" para agregar uno.</div>';
    } else {
      listEl.innerHTML = texts.map((t, idx) => `
        <div class="inspector-section" style="border-left:3px solid var(--accent); position:relative;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <span style="font-weight:700; font-size:12px; color:var(--accent);">#${idx + 1} - ${escapeHtml(t.text ? t.text.substring(0, 16) : 'Texto')}</span>
            <div style="display:flex; gap:4px;">
              <button class="btn btn-sm" onclick="selectStageElement('custom_text_${t.id}')" style="padding:2px 8px; font-size:10px;">🎯 Enfocar</button>
              <button class="btn btn-danger btn-sm" onclick="deleteCustomText('${t.id}')" style="padding:2px 6px; font-size:10px;">🗑</button>
            </div>
          </div>
          <div>
            <label class="form-label" style="font-size:10px;">Texto en Pantalla</label>
            <input type="text" class="form-input" style="font-size:11px;" value="${escapeHtml(t.text || '')}" oninput="updateCustomTextProp('${t.id}', 'text', this.value)">
          </div>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:6px;">
            <div>
              <label class="form-label" style="font-size:10px;">Color Letra</label>
              <input type="color" class="form-input" style="height:28px; padding:2px;" value="${colorToHex(t.color, '#ffffff')}" oninput="updateCustomTextProp('${t.id}', 'color', this.value)">
            </div>
            <div>
              <label class="form-label" style="font-size:10px;">Color Fondo</label>
              <input type="color" class="form-input" style="height:28px; padding:2px;" value="${colorToHex(t.bg_color, '#0a0a0a')}" oninput="updateCustomTextProp('${t.id}', 'bg_color', this.value)">
            </div>
          </div>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:6px;">
            <div>
              <label class="form-label" style="font-size:10px;">Color Borde</label>
              <input type="color" class="form-input" style="height:28px; padding:2px;" value="${colorToHex(t.border_color, '#e8ff47')}" oninput="updateCustomTextProp('${t.id}', 'border_color', this.value)">
            </div>
            <div>
              <label class="form-label" style="font-size:10px;">Tamaño (px)</label>
              <input type="number" class="form-input" style="font-size:11px;" min="10" max="300" value="${t.font_size || 16}" oninput="updateCustomTextProp('${t.id}', 'font_size', parseInt(this.value, 10))">
            </div>
          </div>
          <div style="margin-top:6px; display:flex; align-items:center; justify-content:space-between; gap:8px;">
            <div style="flex:1;">
              <label class="form-label" style="font-size:10px;">Animación</label>
              <select class="form-input" style="font-size:11px;" onchange="updateCustomTextProp('${t.id}', 'animation', this.value)">
                <option value="none" ${t.animation === 'none' ? 'selected' : ''}>Ninguna (Estático)</option>
                <option value="wave" ${t.animation === 'wave' ? 'selected' : ''}>Onda Suave (Wave)</option>
                <option value="pulse" ${t.animation === 'pulse' ? 'selected' : ''}>Pulso Brillante</option>
              </select>
            </div>
            <div style="width:100px;">
              <label class="form-label" style="font-size:10px;">Capa (Z)</label>
              <div style="display:flex; gap:2px;">
                <input type="number" class="form-input" style="font-size:11px; padding:3px 4px; text-align:center;" min="1" max="999" value="${t.z_index !== undefined ? t.z_index : 25}" onchange="updateCustomTextProp('${t.id}', 'z_index', parseInt(this.value, 10) || 25)">
              </div>
            </div>
          </div>
        </div>
      `).join('');
    }
  }
}

function initOverlayStudio() {
  if (!config) return;

  const setCheck = (id, val, defVal = true) => {
    const el = document.getElementById(id);
    if (el) el.checked = (val !== undefined ? Boolean(val) : defVal);
  };
  const setVal = (id, val, defVal = '') => {
    const el = document.getElementById(id);
    if (el) el.value = (val !== undefined ? val : defVal);
  };
  const setColorVal = (id, val, defFallback = '#ffffff') => {
    const el = document.getElementById(id);
    if (el) el.value = colorToHex(val, defFallback);
  };
  const setText = (id, txt) => {
    const el = document.getElementById(id);
    if (el) el.textContent = txt;
  };

  // 1. Inputs Now Playing
  setCheck('modNpEnabled', config.overlay_now_playing_enabled, true);
  const npX = config.overlay_now_playing_x !== undefined ? config.overlay_now_playing_x : (config.overlay_pos_x !== undefined ? config.overlay_pos_x : 40);
  const npY = config.overlay_now_playing_y !== undefined ? config.overlay_now_playing_y : (config.overlay_pos_y !== undefined ? config.overlay_pos_y : 40);
  const npScale = parseFloat(config.overlay_now_playing_scale !== undefined ? config.overlay_now_playing_scale : (config.overlay_scale || 1.0));
  setVal('modNpX', npX);
  setVal('modNpY', npY);
  setVal('modNpScale', npScale);
  setText('modNpScaleVal', npScale.toFixed(2) + 'x');
  setVal('modNpWidth', config.overlay_now_playing_width, 380);
  setColorVal('modNpBgColor', config.overlay_now_playing_bg_color || config.overlay_bg_color, '#0a0a0a');
  const npOp = config.overlay_now_playing_bg_opacity !== undefined ? config.overlay_now_playing_bg_opacity : (config.overlay_bg_opacity !== undefined ? config.overlay_bg_opacity : 78);
  setVal('modNpBgOpacity', npOp);
  setText('modNpOpVal', npOp + '%');
  setColorVal('modNpBorderColor', config.overlay_now_playing_border_color || config.overlay_border_color, '#ffffff');
  const npRad = config.overlay_now_playing_border_radius !== undefined ? config.overlay_now_playing_border_radius : (config.overlay_border_radius !== undefined ? config.overlay_border_radius : 12);
  setVal('modNpBorderRadius', npRad);
  setText('modNpRadiusVal', npRad + 'px');
  setVal('modNpFont', config.overlay_now_playing_font || config.overlay_font_family, 'system-ui');
  setColorVal('modNpTextColor', config.overlay_now_playing_text_color || config.overlay_text_color, '#ffffff');
  const npWave = config.overlay_now_playing_wave !== undefined ? config.overlay_now_playing_wave : (config.overlay_text_wave || 0);
  setVal('modNpWave', npWave);
  setText('modNpWaveVal', npWave);
  setCheck('modNpShowCover', config.overlay_show_cover, true);
  setCheck('modNpShowBadge', config.overlay_show_badge, true);
  setCheck('modNpShowTitle', (config.overlay_show_song_title !== undefined ? config.overlay_show_song_title : config.overlay_show_title), true);
  setCheck('modNpShowArtist', config.overlay_show_artist, true);
  setCheck('modNpShowEq', config.overlay_show_equalizer, true);
  setVal('modNpTitleSize', config.overlay_now_playing_title_size, 13);
  setVal('modNpArtistSize', config.overlay_now_playing_artist_size, 11);
  setVal('modNpBadgeSize', config.overlay_now_playing_badge_size, 9);
  const npZ = config.overlay_now_playing_z_index !== undefined ? config.overlay_now_playing_z_index : 30;
  setVal('modNpZIndex', npZ);
  setText('modNpZVal', npZ);

  // 2. Inputs Temporizador
  setCheck('modTmEnabled', config.overlay_timer_enabled, true);
  setVal('modTmX', config.overlay_timer_x !== undefined ? config.overlay_timer_x : 680);
  setVal('modTmY', config.overlay_timer_y !== undefined ? config.overlay_timer_y : 320);
  const tmScale = parseFloat(config.overlay_timer_scale || 1.0);
  setVal('modTmScale', tmScale);
  setText('modTmScaleVal', tmScale.toFixed(2) + 'x');
  setVal('modTmWidth', config.overlay_timer_width, 560);
  setColorVal('modTmBgColor', config.overlay_timer_bg_color, '#0a0a0a');
  const tmOp = config.overlay_timer_bg_opacity !== undefined ? config.overlay_timer_bg_opacity : 85;
  setVal('modTmBgOpacity', tmOp);
  setText('modTmOpVal', tmOp + '%');
  setColorVal('modTmBorderColor', config.overlay_timer_border_color, '#e8ff47');
  const tmRad = config.overlay_timer_border_radius !== undefined ? config.overlay_timer_border_radius : 20;
  setVal('modTmBorderRadius', tmRad);
  setText('modTmRadiusVal', tmRad + 'px');
  setVal('modTmBadgeText', config.overlay_timer_badge_text, '⏱️ PAUSA DE STREAM & CLASE');
  setColorVal('modTmBadgeColor', config.overlay_timer_badge_color, '#e8ff47');
  setVal('modTmTitleText', config.overlay_timer_title_text, 'Ya Vuelvo');
  setColorVal('modTmTitleColor', config.overlay_timer_title_color, '#ffffff');
  setColorVal('modTmClockColor', config.overlay_timer_clock_color, '#e8ff47');
  setColorVal('modTmProgressColor', config.overlay_timer_progress_color, '#e8ff47');
  setColorVal('modTmPhraseColor', config.overlay_timer_phrase_color, '#bbbbbb');
  setVal('modTmClockSize', config.overlay_timer_clock_size, 72);
  setVal('modTmTitleSize', config.overlay_timer_title_size, 30);
  setVal('modTmBadgeSize', config.overlay_timer_badge_size, 12);
  setVal('modTmPhraseSize', config.overlay_timer_phrase_size, 14);
  setVal('modTmClockFont', config.overlay_timer_clock_font || '');
  setVal('modTmTitleFont', config.overlay_timer_title_font || '');
  setVal('modTmBadgeFont', config.overlay_timer_badge_font || '');
  setVal('modTmPhraseFont', config.overlay_timer_phrase_font || '');

  setCheck('modTmShowBadge', config.overlay_timer_show_badge, true);
  setCheck('modTmShowTitle', config.overlay_timer_show_title, true);
  setCheck('modTmShowClock', config.overlay_timer_show_clock, true);
  setCheck('modTmShowProgress', config.overlay_timer_show_progress, true);
  setCheck('modTmShowPhrase', config.overlay_timer_show_phrase, true);
  const tmZ = config.overlay_timer_z_index !== undefined ? config.overlay_timer_z_index : 20;
  setVal('modTmZIndex', tmZ);
  setText('modTmZVal', tmZ);

  // 3. Inputs Letras
  setCheck('modLyEnabled', config.overlay_show_lyrics, true);
  setVal('modLyX', config.overlay_lyrics_x !== undefined ? config.overlay_lyrics_x : 40);
  setVal('modLyY', config.overlay_lyrics_y !== undefined ? config.overlay_lyrics_y : 130);
  const lyScale = parseFloat(config.overlay_lyrics_scale || 1.0);
  setVal('modLyScale', lyScale);
  setText('modLyScaleVal', lyScale.toFixed(2) + 'x');
  setVal('modLyWidth', config.overlay_lyrics_width, 440);
  setVal('modLyMaxHeight', config.overlay_lyrics_max_height, 150);
  setColorVal('modLyBgColor', config.overlay_lyrics_bg_color, '#0a0a0a');
  const lyOp = config.overlay_lyrics_bg_opacity !== undefined ? config.overlay_lyrics_bg_opacity : 75;
  setVal('modLyBgOpacity', lyOp);
  setText('modLyOpVal', lyOp + '%');
  setColorVal('modLyTextColor', config.overlay_lyrics_text_color, '#e0e0e0');
  setVal('modLyFontSize', config.overlay_lyrics_font_size, 13);
  const lyZ = config.overlay_lyrics_z_index !== undefined ? config.overlay_lyrics_z_index : 15;
  setVal('modLyZIndex', lyZ);
  setText('modLyZVal', lyZ);

  updateStageMockups();
  renderLayersList();
}

function scheduleModularConfigSave(immediate = false) {
  if (modularSaveTimeout) clearTimeout(modularSaveTimeout);
  if (immediate) {
    saveModularOverlayConfig();
  } else {
    modularSaveTimeout = setTimeout(saveModularOverlayConfig, 400);
  }
}

async function saveModularOverlayConfig() {
  try {
    const payload = {
      // Now playing
      overlay_now_playing_enabled: config.overlay_now_playing_enabled !== false,
      overlay_now_playing_x: config.overlay_now_playing_x !== undefined ? config.overlay_now_playing_x : (config.overlay_pos_x !== undefined ? config.overlay_pos_x : 40),
      overlay_now_playing_y: config.overlay_now_playing_y !== undefined ? config.overlay_now_playing_y : (config.overlay_pos_y !== undefined ? config.overlay_pos_y : 40),
      overlay_now_playing_scale: parseFloat(config.overlay_now_playing_scale !== undefined ? config.overlay_now_playing_scale : (config.overlay_scale || 1.0)),
      overlay_now_playing_width: parseInt(config.overlay_now_playing_width || 380, 10),
      overlay_now_playing_z_index: parseInt(config.overlay_now_playing_z_index !== undefined ? config.overlay_now_playing_z_index : 30, 10),
      overlay_now_playing_bg_color: config.overlay_now_playing_bg_color || config.overlay_bg_color || '#0a0a0a',
      overlay_now_playing_bg_opacity: parseInt(config.overlay_now_playing_bg_opacity !== undefined ? config.overlay_now_playing_bg_opacity : (config.overlay_bg_opacity !== undefined ? config.overlay_bg_opacity : 78), 10),
      overlay_now_playing_border_color: config.overlay_now_playing_border_color || config.overlay_border_color || 'rgba(255, 255, 255, 0.12)',
      overlay_now_playing_border_radius: parseInt(config.overlay_now_playing_border_radius !== undefined ? config.overlay_now_playing_border_radius : (config.overlay_border_radius !== undefined ? config.overlay_border_radius : 12), 10),
      overlay_now_playing_text_color: config.overlay_now_playing_text_color || config.overlay_text_color || '#ffffff',
      overlay_now_playing_font: config.overlay_now_playing_font || config.overlay_font_family || 'system-ui',
      overlay_now_playing_wave: parseInt(config.overlay_now_playing_wave !== undefined ? config.overlay_now_playing_wave : (config.overlay_text_wave || 0), 10),
      overlay_now_playing_marquee: Boolean(config.overlay_now_playing_marquee),
      overlay_show_cover: config.overlay_show_cover !== false,
      overlay_show_badge: config.overlay_show_badge !== false,
      overlay_show_song_title: config.overlay_show_song_title !== false,
      overlay_show_title: config.overlay_show_song_title !== false,
      overlay_show_artist: config.overlay_show_artist !== false,
      overlay_show_equalizer: config.overlay_show_equalizer !== false,
      overlay_now_playing_title_size: parseInt(config.overlay_now_playing_title_size || 13, 10),
      overlay_now_playing_artist_size: parseInt(config.overlay_now_playing_artist_size || 11, 10),
      overlay_now_playing_badge_size: parseInt(config.overlay_now_playing_badge_size || 9, 10),

      // Timer
      overlay_timer_enabled: config.overlay_timer_enabled !== false,
      overlay_timer_x: config.overlay_timer_x !== undefined ? config.overlay_timer_x : 680,
      overlay_timer_y: config.overlay_timer_y !== undefined ? config.overlay_timer_y : 320,
      overlay_timer_scale: parseFloat(config.overlay_timer_scale || 1.0),
      overlay_timer_width: parseInt(config.overlay_timer_width || 560, 10),
      overlay_timer_z_index: parseInt(config.overlay_timer_z_index !== undefined ? config.overlay_timer_z_index : 20, 10),
      overlay_timer_bg_color: config.overlay_timer_bg_color || '#0a0a0a',
      overlay_timer_bg_opacity: parseInt(config.overlay_timer_bg_opacity !== undefined ? config.overlay_timer_bg_opacity : 85, 10),
      overlay_timer_border_color: config.overlay_timer_border_color || 'rgba(232, 255, 71, 0.35)',
      overlay_timer_border_radius: parseInt(config.overlay_timer_border_radius !== undefined ? config.overlay_timer_border_radius : 20, 10),
      overlay_timer_font: config.overlay_timer_font || 'system-ui',
      overlay_timer_badge_text: config.overlay_timer_badge_text || '⏱️ PAUSA DE STREAM & CLASE',
      overlay_timer_badge_color: config.overlay_timer_badge_color || '#e8ff47',
      overlay_timer_title_text: config.overlay_timer_title_text || 'Ya Vuelvo',
      overlay_timer_title_color: config.overlay_timer_title_color || '#ffffff',
      overlay_timer_clock_color: config.overlay_timer_clock_color || '#e8ff47',
      overlay_timer_progress_color: config.overlay_timer_progress_color || '#e8ff47',
      overlay_timer_phrase_color: config.overlay_timer_phrase_color || '#bbbbbb',
      overlay_timer_clock_size: parseInt(config.overlay_timer_clock_size || 72, 10),
      overlay_timer_title_size: parseInt(config.overlay_timer_title_size || 30, 10),
      overlay_timer_badge_size: parseInt(config.overlay_timer_badge_size || 12, 10),
      overlay_timer_phrase_size: parseInt(config.overlay_timer_phrase_size || 14, 10),
      overlay_timer_clock_font: config.overlay_timer_clock_font || '',
      overlay_timer_title_font: config.overlay_timer_title_font || '',
      overlay_timer_badge_font: config.overlay_timer_badge_font || '',
      overlay_timer_phrase_font: config.overlay_timer_phrase_font || '',
      overlay_timer_image_enabled: config.overlay_timer_image_enabled || false,
      overlay_timer_image_url: config.overlay_timer_image_url || '',
      overlay_timer_image_x: parseInt(config.overlay_timer_image_x || 0, 10),
      overlay_timer_image_y: parseInt(config.overlay_timer_image_y || 0, 10),
      overlay_timer_image_scale: parseFloat(config.overlay_timer_image_scale || 1.0),
      overlay_timer_image_radius: parseInt(config.overlay_timer_image_radius || 0, 10),
      overlay_timer_show_badge: config.overlay_timer_show_badge !== false,
      overlay_timer_show_title: config.overlay_timer_show_title !== false,
      overlay_timer_show_clock: config.overlay_timer_show_clock !== false,
      overlay_timer_show_progress: config.overlay_timer_show_progress !== false,
      overlay_timer_show_phrase: config.overlay_timer_show_phrase !== false,

      // Lyrics
      overlay_show_lyrics: config.overlay_show_lyrics !== false,
      overlay_lyrics_x: config.overlay_lyrics_x !== undefined ? config.overlay_lyrics_x : 40,
      overlay_lyrics_y: config.overlay_lyrics_y !== undefined ? config.overlay_lyrics_y : 130,
      overlay_lyrics_scale: parseFloat(config.overlay_lyrics_scale || 1.0),
      overlay_lyrics_width: parseInt(config.overlay_lyrics_width || 440, 10),
      overlay_lyrics_max_height: parseInt(config.overlay_lyrics_max_height || 150, 10),
      overlay_lyrics_z_index: parseInt(config.overlay_lyrics_z_index !== undefined ? config.overlay_lyrics_z_index : 15, 10),
      overlay_lyrics_bg_color: config.overlay_lyrics_bg_color || '#0a0a0a',
      overlay_lyrics_bg_opacity: parseInt(config.overlay_lyrics_bg_opacity !== undefined ? config.overlay_lyrics_bg_opacity : 75, 10),
      overlay_lyrics_border_color: config.overlay_lyrics_border_color || 'rgba(255, 255, 255, 0.12)',
      overlay_lyrics_border_radius: parseInt(config.overlay_lyrics_border_radius !== undefined ? config.overlay_lyrics_border_radius : 10, 10),
      overlay_lyrics_text_color: config.overlay_lyrics_text_color || '#e0e0e0',
      overlay_lyrics_font: config.overlay_lyrics_font || 'system-ui',
      overlay_lyrics_font_size: parseInt(config.overlay_lyrics_font_size || 13, 10),
      overlay_lyrics_mode: config.overlay_lyrics_mode || 'single',
      overlay_lyrics_highlight_color: config.overlay_lyrics_highlight_color || '#e8ff47',

      // Custom texts
      overlay_custom_texts: config.overlay_custom_texts || []
    };

    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.config) config = data.config;
  } catch(e) {}
}

async function saveAllModularOverlay(showToastNotice = true) {
  await saveModularOverlayConfig();
  if (showToastNotice) {
    showToast('¡Configuración guardada y sincronizada en OBS! ✨');
  }
}

function populateOverlayCustomizationForm(cfg) {
  initOverlayStudio();
}

function updateHeaderHeight() {
  const h = document.querySelector('header');
  if (h) {
    const height = Math.max(48, h.offsetHeight);
    document.documentElement.style.setProperty('--header-h', height + 'px');
  }
}
window.addEventListener('resize', () => {
  updateHeaderHeight();
  if (currentView === 'overlays') {
    updateStageMockups();
  }
}, { passive: true });

