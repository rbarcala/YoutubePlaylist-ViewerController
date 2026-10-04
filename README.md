# ⬡ YouTube Stream Controller — Fondos & Stream Hub

Panel de control integral para streaming, transmisiones en vivo y videollamadas. Permite controlar de forma sincronizada desde tu PC (App nativa o Web) o desde tu celular Android.

---

## 📱 Las 4 Funciones Principales (Hub Central)

Al abrir la aplicación en tu celular Android o en tu computadora, la pantalla principal te permite elegir entre **4 módulos independientes**:

1. 🎬 **Fondos & Videos (Controller al Viewer)**:
   - Explora la playlist de YouTube, selecciona y envía fondos de video en 1080p directamente al **Viewer**.
   - Ajusta la velocidad en tiempo real (`1.0x` a `3.0x`), silencia/activa el audio y pon en foco la ventana del Viewer automáticamente.
2. 🎥 **Control de Escenas de OBS Studio**:
   - Conexión oficial vía **OBS WebSocket v5** (puerto 4455).
   - Visualiza en una cuadrícula táctil todas tus escenas de OBS; pulsa cualquier tarjeta para cambiar de escena al instante.
   - Inicia o detén la **Transmisión (Streaming)** y la **Grabación** con un solo toque.
3. 🎵 **Spotify Remote (Control de tu PC)**:
   - Controla el cliente de Spotify de tu computadora (a través de Spotify Connect y MPRIS nativo en Linux).
   - Muestra carátula, título, artista, estado de reproducción y control de **Volumen del Spotify de la PC**.
   - Motor de búsqueda integrado: busca canciones en Spotify y elígelas para **Reproducir de inmediato** o **Añadir a la cola**.
4. 🔴 **Visualizador de Directo (YouTube Live Monitor)**:
   - Monitorea tu transmisión en directo de YouTube en tiempo real con la interfaz de YouTube y sonido conmutable (mute/unmute).
   - Detecta automáticamente el directo activo de tu canal configurado en Ajustes.
5. 🔊 **Botonera / Soundboard (MyInstants)**:
   - **Reproducción de audio en la PC**: Cada sonido se reproduce directamente en los parlantes/auriculares de tu computadora (Linux PipeWire/ALSA).
   - **Buscador en Vivo**: Busca entre más de 100.000 efectos de sonido y memes de MyInstants.
   - **Más Usados & Top Histórico**: Pestañas de tendencias y sonidos más virales siempre a mano.
   - **Favoritos Sincronizados**: Marca con la estrella (⭐) cualquier sonido para guardarlo en tu lista personal.
   - **Integración con Cuenta / Google**: Vincula tu usuario de MyInstants o perfil en Ajustes para importar automáticamente todos los favoritos guardados en tu cuenta.

> ↩️ **Navegación Intuitiva**: Desde cualquiera de los 5 módulos puedes regresar al Menú Principal en cualquier momento pulsando el botón **"Go Back" (Atrás)** de tu celular Android o el botón **"← Menú"** en la barra superior.

---

## 🖥️ Acceso en PC y Celular

- **En PC**:
  - **App Nativa de Escritorio** (por defecto en Ubuntu con GTK3 + WebKit2).
  - **Modo Navegador Web** (disponible pulsando el botón **"🌐 Web"** en la barra superior).
  - Barra superior con pestañas directas para saltar entre `Menú`, `Fondos`, `OBS`, `Spotify`, `Directo` y `Botonera`.
- **En Celular Android**:
  - **PWA sin instalación (Recomendada y directa)**: Pulsa el botón **`📱`** en la PC, escanea el código **QR** con la cámara de tu teléfono en la misma red Wi-Fi (o entra a `http://<IP_PC>:8000/controller.html`), toca el menú de 3 puntos (⋮) en Chrome/Brave/Edge y selecciona **"Instalar aplicación"** (o "Agregar a pantalla principal"). Se instalará como una app nativa a pantalla completa con su propio icono.
  - **Proyecto Android Nativo**: La carpeta `android/` contiene el proyecto Gradle/Android Studio listo para abrir y compilar en caso de desear un binario `.apk`.

---

## 🚀 Instalación en Ubuntu

### Dependencias del Sistema (Recomendado)
Antes de instalar, asegúrate de tener las dependencias de Python y GTK en Ubuntu:

```bash
sudo apt update && sudo apt install -y python3-flask yt-dlp python3-requests python3-pyqt5 python3-pyqt5.qtwebengine
```

### Opción 1: Con Makefile (Para usuario local y buscador del OS)

```bash
make install
```

> Ahora presiona la tecla `Super` (Windows) en Ubuntu, escribe **"YouTube Stream Controller"** o **"Fondos"** y la app se abrirá directamente.

Para desinstalar:
```bash
make uninstall
```

---

### Opción 2: Paquete `.deb` del Sistema

```bash
sudo apt install -y ./release/youtube-stream-controller_1.0.0_all.deb
```
*(O alternativamente: `sudo dpkg -i release/youtube-stream-controller_1.0.0_all.deb && sudo apt-get install -f -y`)*

---

## 🎮 Comandos de Uso

| Comando | Acción |
|---|---|
| `make run` | Inicia la aplicación Controller nativa de escritorio |
| `make run-web` | Inicia el Controller directamente en el navegador web |
| `make viewer` | Abre la pantalla de reproducción a pantalla completa (Viewer) |
| `make release` | Instala dependencias automáticamente y compila los instalables (`.deb` y `.apk`) |
| `make clean` | Limpia archivos temporales y caché |

---

## ⚙️ Configuración (Botón ⚙️)

En el panel de configuración puedes definir y recordar:

1. **YouTube API Key & Playlist**: Clave de YouTube Data API v3 y URL/ID de la playlist de fondos (guardado de forma segura en `config.json`, protegido por `.gitignore`).
2. **Canal de YouTube**: ID de tu canal para que el visualizador de directo detecte automáticamente tus transmisiones en vivo.
3. **Auto-Foco del Viewer**: Si está activo, al seleccionar o re-clickear un video en el controlador, la ventana del Viewer en el navegador pasa a primer plano automáticamente.
4. **Spotify**: Ingresa tu `Client ID` y `Client Secret` (de [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)) y pulsa **"Vincular Cuenta de Spotify"** para autorizar el control remoto.
5. **OBS Studio**: Habilita WebSocket (Host `localhost`, Puerto `4455`, Contraseña opcional) y escena por defecto al reproducir fondos.

---

## 📦 Releases Listos para Descargar

En la carpeta `release/` encontrarás:

- 🐧 **Ubuntu / Debian**: `release/youtube-stream-controller_1.0.0_all.deb`
- 🤖 **Android**: `release/youtube-stream-controller.apk` (APK nativo compilado y firmado)
- 📱 **Modo Web / PWA**: Acceso directo instantáneo con QR sin necesidad de instalar APK
- 🔒 **Sumas SHA256**: `release/checksums.sha256`

Para recompilar los paquetes en cualquier momento:
```bash
make release
```
> `make release` verificará tus dependencias y las instalará automáticamente con `apt` si falta alguna antes de compilar los ejecutables.
