// ─── 2. OBS STUDIO LOGIC ───
let currentCamStream = null;
let snapshotLoopTimer = null;
let isSnapshotFetching = false;
let previewMode = 'auto'; // 'vcam' | 'snapshot' | 'auto'

function stopSnapshotPreviewLoop() {
  if (snapshotLoopTimer) {
    clearTimeout(snapshotLoopTimer);
    snapshotLoopTimer = null;
  }
}

let snapshotIntervalMs = 50; // ~20 FPS por defecto (Ultra fluido, tiempo real de video)
let lastFrameTimestamp = 0;
let frameCount = 0;
let lastFpsCalc = performance.now();

function setSnapshotSpeed(interval) {
  snapshotIntervalMs = parseInt(interval, 10) || 50;
}

async function fetchNextSnapshotFrame() {
  const img = document.getElementById('obsImgPreview');
  const fallback = document.getElementById('obsPreviewFallback');
  const fpsTag = document.getElementById('obsPreviewFpsTag');
  if (!img) return;

  if (isSnapshotFetching) return;
  isSnapshotFetching = true;

  try {
    const sceneParam = lastKnownCurrentScene ? `?scene=${encodeURIComponent(lastKnownCurrentScene)}` : '';
    const res = await fetch(`/api/obs/preview${sceneParam}&width=380&height=214&quality=30`, { cache: 'no-store' });
    const data = await res.json();

    if (data && data.success && data.imageData) {
      if (!currentCamStream) {
        if (img.style.display !== 'block') {
          img.style.display = 'block';
          const video = document.getElementById('obsVideoCam');
          if (video) video.style.display = 'none';
          if (fallback) fallback.style.display = 'none';
        }
        img.src = data.imageData;

        // Medir FPS reales alcanzados
        frameCount++;
        const now = performance.now();
        if (now - lastFpsCalc >= 1000) {
          const fps = Math.round((frameCount * 1000) / (now - lastFpsCalc));
          if (fpsTag) {
            fpsTag.style.display = 'inline-block';
            fpsTag.textContent = `● LIVE ${fps} FPS`;
          }
          frameCount = 0;
          lastFpsCalc = now;
        }
      }
    } else if (!currentCamStream && fallback && img.style.display !== 'block') {
      const msg = document.getElementById('obsPreviewMsg');
      if (msg && data.error) msg.textContent = 'OBS conectado. Esperando fotograma...';
    }
  } catch (err) {
    // Reintentar silenciosamente
  } finally {
    isSnapshotFetching = false;
    // Programa el siguiente frame inmediatamente con el intervalo seleccionado
    if (!currentCamStream && previewMode !== 'vcam_only') {
      snapshotLoopTimer = setTimeout(fetchNextSnapshotFrame, snapshotIntervalMs);
    }
  }
}

function startSnapshotPreviewLoop(force = false) {
  stopSnapshotPreviewLoop();
  if (force) {
    // Si el usuario fuerza la transmisión de pantalla, detener la cámara virtual
    if (currentCamStream) {
      currentCamStream.getTracks().forEach(t => t.stop());
      currentCamStream = null;
    }
    const video = document.getElementById('obsVideoCam');
    if (video) video.style.display = 'none';
  }
  fetchNextSnapshotFrame();
}

async function startVirtualCameraPreview() {
  const fallback = document.getElementById('obsPreviewFallback');
  const msg = document.getElementById('obsPreviewMsg');
  const btn = document.getElementById('btnStartVirtualCam');
  let camSelect = document.getElementById('obsCamSelect');

  if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== 'function') {
    // En móviles o conexiones HTTP sin getUserMedia, activar directamente la transmisión por red
    startSnapshotPreviewLoop();
    return;
  }

  try {
    if (!camSelect.options || camSelect.options.length === 0) {
      if (msg) msg.textContent = "Buscando cámara virtual...";
      await navigator.mediaDevices.getUserMedia({ video: true })
        .then(s => s.getTracks().forEach(t => t.stop()))
        .catch(e => { if(e.name !== "NotReadableError") throw e; });
    }

    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoInputs = devices.filter(d => d.kind === 'videoinput');

    if (videoInputs.length === 0) {
      // Sin cámaras: usar la previsualización de red
      startSnapshotPreviewLoop();
      return;
    }

    camSelect.innerHTML = '';
    videoInputs.forEach(device => {
        const option = document.createElement('option');
        option.value = device.deviceId;
        option.text = device.label || `Cámara ${camSelect.length + 1}`;
        camSelect.appendChild(option);
    });
    
    const obsDev = videoInputs.find(d => 
        d.label.toLowerCase().includes('obs') || 
        d.label.toLowerCase().includes('dummy') || 
        d.label.toLowerCase().includes('v4l2')
    );
    if (obsDev) {
      camSelect.value = obsDev.deviceId;
      camSelect.style.display = 'block';
      if (btn) btn.style.display = 'none';
      connectSelectedCamera(obsDev.deviceId);
    } else {
      // Si no hay cámara OBS instalada en este dispositivo, usar el snapshot en tiempo real
      startSnapshotPreviewLoop();
    }
  } catch (err) {
    // Si falla o no se dan permisos de cámara, fallback fluido automático por red
    startSnapshotPreviewLoop();
  }
}

async function connectSelectedCamera(deviceId) {
    const video = document.getElementById('obsVideoCam');
    const img = document.getElementById('obsImgPreview');
    const fallback = document.getElementById('obsPreviewFallback');
    const msg = document.getElementById('obsPreviewMsg');
    const fpsTag = document.getElementById('obsPreviewFpsTag');
    
    stopSnapshotPreviewLoop();
    if (img) img.style.display = 'none';
    
    if (currentCamStream) {
        currentCamStream.getTracks().forEach(t => t.stop());
    }
    
    try {
        if (msg) msg.textContent = "Conectando cámara...";
        const constraints = { 
            video: {
                width: { ideal: 640, max: 1280 },
                height: { ideal: 360, max: 720 },
                frameRate: { ideal: 30, max: 60 }
            }
        };
        if (deviceId && deviceId !== "") {
            constraints.video.deviceId = deviceId;
        }
        currentCamStream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = currentCamStream;
        video.style.display = 'block';
        if (fallback) fallback.style.display = 'none';
        if (fpsTag) {
          fpsTag.style.display = 'inline-block';
          fpsTag.textContent = '60 FPS';
        }
        video.play().catch(e => console.log('Auto-play prevent: ', e));
        
        currentCamStream.getVideoTracks()[0].onended = () => {
            video.style.display = 'none';
            currentCamStream = null;
            // Si la cámara virtual se cae, pasar fluidamente a la transmisión por red
            startSnapshotPreviewLoop();
        };
        
    } catch (err) {
        console.error(err);
        // Fallback a transmisión por red
        startSnapshotPreviewLoop();
    }
}

function stopObsPreviewLoop() {
    stopSnapshotPreviewLoop();
    if (currentCamStream) {
        currentCamStream.getTracks().forEach(t => t.stop());
        currentCamStream = null;
    }
}

window.startObsPreviewLoop = startVirtualCameraPreview;
window.startSnapshotPreviewLoop = startSnapshotPreviewLoop;

let lastKnownObsScenes = [];
let lastKnownCurrentScene = '';

function highlightCurrentScene(sceneName) {
  if (!sceneName) return;
  lastKnownCurrentScene = sceneName;
  const cards = document.querySelectorAll('.obs-scene-card');
  let matched = false;
  cards.forEach(card => {
    const isThis = card.getAttribute('data-scene') === sceneName || card.textContent.trim() === sceneName.trim();
    card.classList.toggle('active', isThis);
    if (isThis) matched = true;
  });
  const statusElem = document.getElementById('obsStatusText');
  if (statusElem && (lastKnownObsScenes.length > 0 || matched)) {
    statusElem.textContent = `Conectado a OBS (Escena actual: ${sceneName})`;
  }
}

function renderObsScenesCards(scenes, currentScene) {
  const grid = document.getElementById('obsScenesGrid');
  const btnLaunch = document.getElementById('btnLaunchObs');
  if (!grid) return;
  if (scenes && scenes.length > 0) {
    lastKnownObsScenes = scenes;
    lastKnownCurrentScene = currentScene || lastKnownCurrentScene;
    if (btnLaunch) btnLaunch.style.display = 'none';
    grid.innerHTML = '';
    scenes.forEach(scene => {
      const card = document.createElement('div');
      card.className = 'obs-scene-card' + (scene === lastKnownCurrentScene ? ' active' : '');
      card.setAttribute('data-scene', scene);
      card.textContent = scene;
      card.onclick = () => switchObsScene(scene);
      grid.appendChild(card);
    });
    const statusElem = document.getElementById('obsStatusText');
    if (statusElem) {
      statusElem.textContent = `Conectado a OBS (Escena actual: ${lastKnownCurrentScene || 'Normal'})`;
    }
  }
}

async function loadObsData() {
  try {
    fetch('/api/obs/start_virtual_cam', { method: 'POST' }).catch(() => {});
    const btnLaunch = document.getElementById('btnLaunchObs');
    const grid = document.getElementById('obsScenesGrid');

    // Consultar status y scenes en paralelo
    const [scenesRes, stRes] = await Promise.allSettled([
      fetch('/api/obs/scenes').then(r => r.json()),
      fetch('/api/obs/status').then(r => r.json())
    ]);

    const data = scenesRes.status === 'fulfilled' ? scenesRes.value : null;
    const st = stRes.status === 'fulfilled' ? stRes.value : null;

    const isConnected = (st && st.connected) || (data && data.success && data.scenes && data.scenes.length > 0);

    if (data && data.scenes && data.scenes.length > 0) {
      renderObsScenesCards(data.scenes, data.current_scene);
    } else if (lastKnownObsScenes.length > 0 && isConnected) {
      // Si la llamada puntual de escenas falló pero OBS está conectado, mantenemos las escenas
      if (btnLaunch) btnLaunch.style.display = 'none';
      if (st && st.current_scene) highlightCurrentScene(st.current_scene);
    } else if (!isConnected && lastKnownObsScenes.length === 0) {
      // Solo mostramos desconectado si realmente no está conectado y no tenemos escenas previas
      if (btnLaunch) btnLaunch.style.display = 'inline-flex';
      if (grid) grid.innerHTML = '<p style="color:var(--muted);">OBS Studio no está conectado o está cerrado. Haz clic en "🎬 Abrir OBS" para iniciarlo.</p>';
      const statusElem = document.getElementById('obsStatusText');
      if (statusElem) {
        statusElem.innerHTML = 'OBS no conectado &bull; <a href="javascript:void(0)" onclick="openObsStudio()" style="color:var(--accent); text-decoration:underline;">Abrir OBS Studio</a>';
      }
    }

    if (st && st.connected) {
      currentObsScene = st.current_scene || currentObsScene;
      if (st.current_scene) highlightCurrentScene(st.current_scene);
      if (btnLaunch) btnLaunch.style.display = 'none';
      const btnStream = document.getElementById('btnObsStream');
      if (btnStream) {
        btnStream.textContent = st.is_streaming ? 'Detener Stream' : 'Iniciar Stream';
        btnStream.className = st.is_streaming ? 'btn btn-danger' : 'btn';
      }
      const btnRecord = document.getElementById('btnObsRecord');
      if (btnRecord) {
        btnRecord.textContent = st.is_recording ? 'Detener Grabación' : 'Iniciar Grabación';
        btnRecord.className = st.is_recording ? 'btn btn-danger' : 'btn';
      }
      loadObsAudioData();

      // Iniciar automáticamente la previsualización (Cámara Virtual o Transmisión Snapshot por red) si no está activa
      const video = document.getElementById('obsVideoCam');
      const img = document.getElementById('obsImgPreview');
      const isVideoActive = currentCamStream || (video && video.style.display === 'block');
      const isImgActive = snapshotLoopTimer || (img && img.style.display === 'block');
      if (!isVideoActive && !isImgActive) {
        startVirtualCameraPreview().catch(() => {});
      }
    }
  } catch(e) {}
}

// ─── OBS AUDIO CONTROLS & VUMETERS ───
let obsAudioInputs = { desktop: null, mic: null };
let obsAudioDragging = { desktop: false, mic: false };

async function loadObsAudioData() {
  try {
    const res = await fetch('/api/obs/audio');
    const data = await res.json();
    const tag = document.getElementById('obsAudioStatusTag');
    if (!data.connected) {
      if (tag) {
        tag.textContent = 'OBS Desconectado';
        tag.style.color = 'var(--muted)';
      }
      return;
    }
    if (tag) {
      tag.textContent = 'En vivo';
      tag.style.color = 'var(--accent)';
    }

    obsAudioInputs.desktop = data.desktop;
    obsAudioInputs.mic = data.mic;

    updateObsAudioUI('desktop', data.desktop);
    updateObsAudioUI('mic', data.mic);
  } catch(e) {}
}

function updateObsAudioUI(type, input) {
  if (!input) return;
  const strip = document.getElementById(type === 'desktop' ? 'obsVuStripDesktop' : 'obsVuStripMic');
  const slider = document.getElementById(type === 'desktop' ? 'obsVuSliderDesktop' : 'obsVuSliderMic');
  const muteBtn = document.getElementById(type === 'desktop' ? 'obsVuMuteDesktop' : 'obsVuMuteMic');
  const valText = document.getElementById(type === 'desktop' ? 'obsVuValDesktop' : 'obsVuValMic');

  if (strip) {
    strip.classList.toggle('muted', Boolean(input.muted));
  }
  if (muteBtn) {
    muteBtn.classList.toggle('muted', Boolean(input.muted));
    if (type === 'desktop') {
      muteBtn.textContent = input.muted ? '🔇' : '🔊';
    } else {
      muteBtn.textContent = input.muted ? '🔇' : '🎙️';
    }
  }
  if (slider && !obsAudioDragging[type]) {
    const pct = Math.round((input.volume_mul || 0) * 100);
    slider.value = pct;
  }
  if (valText && input.volume_db !== undefined && input.volume_db !== null) {
    valText.textContent = input.volume_db === -Infinity ? '-inf dB' : `${input.volume_db.toFixed(1)} dB`;
  }
}

function onObsAudioSliderInput(type, val) {
  obsAudioDragging[type] = true;
  const mul = parseFloat(val) / 100.0;
  const valText = document.getElementById(type === 'desktop' ? 'obsVuValDesktop' : 'obsVuValMic');
  if (valText) {
    if (mul <= 0.0001) {
      valText.textContent = '-inf dB';
    } else {
      const db = 20 * Math.log10(mul);
      valText.textContent = `${db.toFixed(1)} dB`;
    }
  }
}

async function onObsAudioSliderChange(type, val) {
  obsAudioDragging[type] = false;
  const mul = parseFloat(val) / 100.0;
  const inputObj = obsAudioInputs[type];
  const inputName = inputObj ? inputObj.name : null;

  try {
    await fetch('/api/obs/audio/volume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: type, input_name: inputName, volume_mul: mul })
    });
  } catch(e) {}
}

async function toggleObsAudioMute(type) {
  const inputObj = obsAudioInputs[type];
  const inputName = inputObj ? inputObj.name : null;
  const currentlyMuted = inputObj ? Boolean(inputObj.muted) : false;
  const newMuted = !currentlyMuted;

  if (inputObj) inputObj.muted = newMuted;
  updateObsAudioUI(type, inputObj || { muted: newMuted });

  try {
    const res = await fetch('/api/obs/audio/mute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: type, input_name: inputName, muted: newMuted })
    });
    const data = await res.json();
    if (data.ok && inputObj) {
      inputObj.muted = data.muted;
      updateObsAudioUI(type, inputObj);
    }
  } catch(e) {}
}

async function openObsStudio() {
  showToast('Iniciando OBS Studio en la computadora…', 'info');
  try {
    const res = await fetch('/api/open_obs', { method: 'POST' });
    const data = await res.json();
    if (data.was_running) {
      showToast('OBS Studio ya estaba en ejecución.', 'info');
    } else {
      showToast('OBS Studio abierto con éxito ✓', 'success');
    }
    setTimeout(loadObsData, 2500);
    setTimeout(loadObsData, 5000);
  } catch(e) {
    showToast('Error al solicitar apertura de OBS', 'error');
  }
}

async function switchObsScene(scene) {
  showToast('Cambiando a escena: ' + scene, 'info');
  try {
    const res = await fetch('/api/obs/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast('Escena cambiada: ' + scene, 'success');
    } else {
      showToast(data.error || 'Error al cambiar de escena', 'error');
    }
  } catch(e) {
    showToast('Error de conexión con OBS', 'error');
  }
  loadObsData();
}

async function toggleObsStream() {
  try {
    const res = await fetch('/api/obs/toggle_stream', { method: 'POST' });
    const data = await res.json();
    showToast(data.outputActive ? 'Stream iniciado' : 'Stream detenido', data.outputActive ? 'success' : 'info');
    loadObsData();
  } catch(e) {
    showToast('Error al controlar streaming de OBS', 'error');
  }
}

async function toggleObsRecord() {
  try {
    const res = await fetch('/api/obs/toggle_record', { method: 'POST' });
    const data = await res.json();
    showToast(data.outputActive ? 'Grabación iniciada' : 'Grabación detenida', data.outputActive ? 'success' : 'info');
    loadObsData();
  } catch(e) {
    showToast('Error al controlar grabación de OBS', 'error');
  }
}

