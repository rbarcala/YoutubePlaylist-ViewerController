# ⬡ YouTube Stream Controller

> Centro de control integral para streaming, fondos de video y overlays en OBS Studio, videollamadas y control multimedia. Compatible con PC (Escritorio nativo / Web) y dispositivos móviles (PWA / Android).

---

## ⚡ Inicio Rápido

```bash
# 1. Instalar en Ubuntu (lanzador en el sistema y vinculación con OBS)
make install

# 2. Iniciar la aplicación
make run
```

---

## 🎛️ Módulos Principales

| Módulo | Descripción |
|---|---|
| 🎬 **Fondos & Videos** | Control y reproducción de fondos 1080p en el **Viewer**. Velocidad en vivo (1.0x a 5.0x), mute y auto-foco de ventana. |
| 🎥 **OBS Studio & Directo** | Control vía **OBS WebSocket v5**. Cambio de escenas, inicio/fin de Stream y Grabación, y vúmetros de audio en tiempo real. |
| 🎵 **Spotify Remote** | Control del reproductor en PC (MPRIS / Spotify Connect). Carátula, buscador, cola y volumen. |
| 🔊 **Botonera (MyInstants)** | Más de 100.000 efectos y memes reproducidos en la PC (PipeWire/ALSA). Búsqueda en vivo y favoritos sincronizados. |
| 📺 **Estudio de Overlays** | Lienzo 16:9 interactivo con arrastre libre para OBS (Now Playing, temporizador con frases, letras y textos en pantalla). |

---

## 📱 Acceso Multiplataforma

- **PC (Escritorio)**: Lanzador nativo en Ubuntu (búsqueda de aplicaciones `Super` o `make run`). Modo navegador web con `make run-web`.
- **Celular / Tablet**: Pulsa el botón **`📱`** en el controlador y escanea el código **QR** para abrir la PWA táctil a pantalla completa, o instala el `.apk` desde `release/`.

---

## 🎮 Comandos Útiles

| Comando | Acción |
|---|---|
| `make install` | Instala lanzadores, dependencias y vincula la capa en OBS Studio |
| `make run` | Inicia la aplicación en modo nativo de escritorio |
| `make run-web` | Inicia el controlador en el navegador web |
| `make viewer` | Abre directamente la ventana del Viewer 1080p |
| `make test` | Ejecuta la suite de pruebas unitarias |
| `make release` | Compila los paquetes instalables (`.deb` y `.apk`) |
| `make clean` | Limpia caché y archivos temporales |

---

## ⚙️ Configuración y Persistencia

Las preferencias se gestionan desde el botón **⚙️** de la app y se guardan automáticamente en `config.json` con respaldo permanente en `~/.config/youtube-stream-controller/`:

- **YouTube**: API Key v3 y Playlist ID de fondos.
- **Spotify**: Client ID y Secret para vinculación remota.
- **OBS Studio**: Host (`localhost`), Puerto (`4455`) y contraseña de WebSocket v5.
- **Viewer**: Auto-foco y resolución.
- **Botonera**: Usuario o cookie de sesión de MyInstants.

---

## 📦 Releases

En la carpeta `release/` se incluyen los instalables precompilados:
- 🐧 **Ubuntu / Debian**: `youtube-stream-controller_1.0.0_all.deb` (`sudo apt install -y ./release/...`)
- 🤖 **Android**: `youtube-stream-controller.apk`
- 🔒 **Sumas de verificación**: `release/checksums.sha256`

