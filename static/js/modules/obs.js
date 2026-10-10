// ─── 2. OBS STUDIO LOGIC ───
let currentCamStream = null;

async function startVirtualCameraPreview() {
  const fallback = document.getElementById('obsPreviewFallback');
  const msg = document.getElementById('obsPreviewMsg');
  const btn = document.getElementById('btnStartVirtualCam');
  let camSelect = document.getElementById('obsCamSelect');

  try {
    if (!camSelect.options || camSelect.options.length === 0) {
      msg.textContent = "Solicitando permisos de cámara...";
      await navigator.mediaDevices.getUserMedia({ video: true })
        .then(s => s.getTracks().forEach(t => t.stop()))
        .catch(e => { if(e.name !== "NotReadableError") throw e; });
    }

    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoInputs = devices.filter(d => d.kind === 'videoinput');

    if (videoInputs.length === 0) {
      throw new Error("No se detectaron cámaras en el sistema.");
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
    if (obsDev) camSelect.value = obsDev.deviceId;
    
    camSelect.style.display = 'block';
    btn.style.display = 'none';
    
    if (videoInputs.length > 0) {
        connectSelectedCamera(camSelect.value);
    }
  } catch (err) {
    msg.textContent = "Error: " + err.message;
    btn.style.display = "inline-flex";
    btn.textContent = "Dar permisos e intentar de nuevo";
  }
}

async function connectSelectedCamera(deviceId) {
    const video = document.getElementById('obsVideoCam');
    const fallback = document.getElementById('obsPreviewFallback');
    const msg = document.getElementById('obsPreviewMsg');
    
    if (currentCamStream) {
        currentCamStream.getTracks().forEach(t => t.stop());
    }
    
    try {
        msg.textContent = "Conectando cámara...";
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
        fallback.style.display = 'none';
        video.play().catch(e => console.log('Auto-play prevent: ', e));
        
        currentCamStream.getVideoTracks()[0].onended = () => {
            video.style.display = 'none';
            fallback.style.display = 'flex';
            msg.textContent = "La cámara virtual se desconectó. ¿Está iniciada en OBS?";
            if (document.getElementById('btnStartVirtualCam')) {
                document.getElementById('btnStartVirtualCam').style.display = 'inline-flex';
            }
        };
        
    } catch (err) {
        console.error(err);
        msg.textContent = "Error al conectar cámara: " + err.message;
        if (document.getElementById('btnStartVirtualCam')) {
            document.getElementById('btnStartVirtualCam').style.display = "inline-flex";
            document.getElementById('btnStartVirtualCam').textContent = "Reintentar conexión";
        }
    }
}

function stopObsPreviewLoop() {
    if (currentCamStream) {
        // currentCamStream.getTracks().forEach(t => t.stop());
    }
}

window.startObsPreviewLoop = startVirtualCameraPreview;

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

      // Iniciar automáticamente la previsualización de cámara virtual en el controller si no está corriendo
      if (!currentCamStream && document.getElementById('obsVideoCam') && document.getElementById('obsVideoCam').style.display !== 'block') {
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
    if (!res.ok) {
      showToast('Error al cambiar de escena', 'error');
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

