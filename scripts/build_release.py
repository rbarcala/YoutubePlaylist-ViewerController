#!/usr/bin/env python3
"""
Script de construcción de Releases para Ubuntu (.deb) y Android (.apk).
Genera los instalables listos para distribución en la carpeta release/.
"""

import os
import sys
import shutil
import subprocess
import zipfile
import hashlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RELEASE_DIR = BASE_DIR / "release"
BUILD_DIR = BASE_DIR / "build"

VERSION = "1.0.0"
PACKAGE_NAME = "youtube-stream-controller"

def ensure_dirs():
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

def build_deb():
    print("\n[build] Construyendo paquete Debian/Ubuntu (.deb)...")
    deb_root = BUILD_DIR / "deb_pkg"
    debian_dir = deb_root / "DEBIAN"
    usr_bin = deb_root / "usr" / "bin"
    usr_share_app = deb_root / "usr" / "share" / PACKAGE_NAME
    usr_apps = deb_root / "usr" / "share" / "applications"
    usr_icons = deb_root / "usr" / "share" / "icons" / "hicolor"

    for d in [debian_dir, usr_bin, usr_share_app, usr_apps, usr_icons]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Copiar código de la app
    app_files = [
        "app.py", "server.py", "config_manager.py", "obs_client.py",
        "spotify_manager.py", "qr_svg.py", "controller.html", "viewer.html",
        "manifest.json", "sw.js", "config.example.json", "requirements.txt"
    ]
    for f in app_files:
        src = BASE_DIR / f
        if src.exists():
            shutil.copy2(src, usr_share_app / f)

    # Copiar carpetas assets y bin
    shutil.copytree(BASE_DIR / "assets", usr_share_app / "assets", dirs_exist_ok=True)
    shutil.copytree(BASE_DIR / "bin", usr_share_app / "bin", dirs_exist_ok=True)

    # Copiar extension
    if (BASE_DIR / "extension").exists():
        shutil.copytree(BASE_DIR / "extension", usr_share_app / "extension", dirs_exist_ok=True)

    # 2. Wrapper ejecutable en /usr/bin
    bin_wrapper = usr_bin / PACKAGE_NAME
    with open(bin_wrapper, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\nexec /usr/share/youtube-stream-controller/bin/youtube-stream-controller \"$@\"\n")
    os.chmod(bin_wrapper, 0o755)

    # 3. Desktop entry
    shutil.copy2(BASE_DIR / "youtube-stream-controller.desktop", usr_apps / f"{PACKAGE_NAME}.desktop")

    # 4. Iconos
    scalable_dir = usr_icons / "scalable" / "apps"
    scalable_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASE_DIR / "assets" / "icon.svg", scalable_dir / f"{PACKAGE_NAME}.svg")

    for size in [16, 32, 48, 64, 128, 256, 512]:
        size_dir = usr_icons / f"{size}x{size}" / "apps"
        size_dir.mkdir(parents=True, exist_ok=True)
        src_icon = BASE_DIR / "assets" / "icons" / f"{size}x{size}" / f"{PACKAGE_NAME}.png"
        if src_icon.exists():
            shutil.copy2(src_icon, size_dir / f"{PACKAGE_NAME}.png")

    # 5. Archivo DEBIAN/control
    control_content = f"""Package: {PACKAGE_NAME}
Version: {VERSION}
Section: video
Priority: optional
Architecture: all
Depends: python3, python3-flask, yt-dlp, python3-requests, gir1.2-gtk-3.0, gir1.2-webkit2-4.1
Maintainer: Ramiro Barcala Roca <rbarcala@fi.uba.ar>
Description: YouTube Playlist & Video Backgrounds Stream Controller
 Controlador en tiempo real de fondos de video para streaming, Google Meet y OBS Studio.
 Sincronizado en tiempo real entre múltiples dispositivos y escritorios.
"""
    with open(debian_dir / "control", "w", encoding="utf-8") as f:
        f.write(control_content)

    # 6. Scripts postinst y postrm
    postinst_content = """#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
"""
    postinst_file = debian_dir / "postinst"
    with open(postinst_file, "w", encoding="utf-8") as f:
        f.write(postinst_content)
    os.chmod(postinst_file, 0o755)

    postrm_content = """#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
"""
    postrm_file = debian_dir / "postrm"
    with open(postrm_file, "w", encoding="utf-8") as f:
        f.write(postrm_content)
    os.chmod(postrm_file, 0o755)

    # 7. Asegurar permisos correctos para dpkg-deb (0755 en directorios)
    for root, dirs, files in os.walk(deb_root):
        for d in dirs:
            os.chmod(Path(root) / d, 0o755)
        for f in files:
            p = Path(root) / f
            if p.name in ["postinst", "postrm"]:
                os.chmod(p, 0o755)
            elif "bin" in str(p):
                os.chmod(p, 0o755)
            else:
                os.chmod(p, 0o644)

    os.chmod(debian_dir, 0o755)
    os.chmod(debian_dir / "control", 0o644)
    if (debian_dir / "postinst").exists():
        os.chmod(debian_dir / "postinst", 0o755)
    if (debian_dir / "postrm").exists():
        os.chmod(debian_dir / "postrm", 0o755)

    # 8. Empaquetar con dpkg-deb
    deb_filename = f"{PACKAGE_NAME}_{VERSION}_all.deb"
    deb_dest = RELEASE_DIR / deb_filename
    subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(deb_root), str(deb_dest)], check=True)
    print(f"✓ Paquete Debian generado con éxito: {deb_dest}")
    return deb_dest

def build_apk():
    print("\n[build] Verificando entorno para compilación de Android (.apk)...")
    android_dir = BASE_DIR / "android"
    gradle_cmd = None
    if (android_dir / "gradlew").exists() and os.access(android_dir / "gradlew", os.X_OK):
        gradle_cmd = str(android_dir / "gradlew")
    elif shutil.which("gradle"):
        gradle_cmd = "gradle"

    has_sdk = bool(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or (Path.home() / "Android/Sdk").exists())

    if gradle_cmd and has_sdk:
        try:
            print("  Compilando APK nativo con Gradle...")
            subprocess.run([gradle_cmd, "assembleRelease"], cwd=android_dir, check=True)
            apk_candidates = list((android_dir / "app" / "build" / "outputs" / "apk").glob("**/*.apk"))
            if apk_candidates:
                apk_dest = RELEASE_DIR / f"{PACKAGE_NAME}.apk"
                shutil.copy2(apk_candidates[0], apk_dest)
                print(f"✓ Paquete Android APK generado con éxito: {apk_dest}")
                return apk_dest
        except Exception as e:
            print(f"⚠️ Error al compilar con Gradle: {e}")

    print("ℹ️ Android SDK / Gradle no detectados en este sistema para compilar APK binario.")
    print("ℹ️ Recomendación para Android:")
    print("   1. Modo PWA (Recomendado sin instalación manual):")
    print("      Abre http://<IP_LOCAL>:8000/controller.html en Chrome/Brave en tu celular y pulsa 'Agregar a la pantalla de inicio'.")
    print("   2. Para compilar el APK nativo:")
    print("      Abre la carpeta 'android/' en Android Studio y selecciona Build > Build APK.")
    return None

def generate_checksums(files):
    valid_files = [f for f in files if f and Path(f).exists()]
    if not valid_files:
        return
    print("\n[build] Generando sumas de verificación SHA256...")
    chk_file = RELEASE_DIR / "checksums.sha256"
    with open(chk_file, "w", encoding="utf-8") as out:
        for f in valid_files:
            h = hashlib.sha256()
            with open(f, "rb") as b:
                while chunk := b.read(8192):
                    h.update(chunk)
            out.write(f"{h.hexdigest()}  {f.name}\n")
            print(f"  {f.name}: {h.hexdigest()}")
    print(f"✓ Checksums guardados en: {chk_file}")

def main():
    ensure_dirs()
    deb = build_deb()
    apk = build_apk()
    generate_checksums([f for f in [deb, apk] if f is not None])
    print("\n🎉 Proceso de release finalizado en release/")

if __name__ == "__main__":
    main()
