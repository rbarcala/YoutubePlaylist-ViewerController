#!/bin/bash
# ==============================================================================
# Script de comprobación e instalación automática de dependencias para
# YouTube Stream Controller (Linux .deb y Android .apk)
# ==============================================================================

set -e

echo "================================================================="
echo "   Comprobando e instalando dependencias automáticamente...      "
echo "================================================================="

REQUIRED_PKGS=()

# 1. Dependencias del sistema para Linux (Python, Flask, GTK3, WebKit2)
dpkg -s python3-flask >/dev/null 2>&1 || REQUIRED_PKGS+=("python3-flask")
dpkg -s yt-dlp >/dev/null 2>&1 || REQUIRED_PKGS+=("yt-dlp")
dpkg -s python3-requests >/dev/null 2>&1 || REQUIRED_PKGS+=("python3-requests")
dpkg -s python3-qrcode >/dev/null 2>&1 || REQUIRED_PKGS+=("python3-qrcode")
dpkg -s python3-pyqt5 >/dev/null 2>&1 || REQUIRED_PKGS+=("python3-pyqt5")
dpkg -s python3-pyqt5.qtwebengine >/dev/null 2>&1 || REQUIRED_PKGS+=("python3-pyqt5.qtwebengine")
dpkg -s dpkg-dev >/dev/null 2>&1 || REQUIRED_PKGS+=("dpkg-dev")

# 2. Herramientas oficiales para compilar APK Android nativo sin Android Studio
dpkg -s aapt >/dev/null 2>&1 || REQUIRED_PKGS+=("aapt")
dpkg -s zipalign >/dev/null 2>&1 || REQUIRED_PKGS+=("zipalign")
dpkg -s apksigner >/dev/null 2>&1 || REQUIRED_PKGS+=("apksigner")
dpkg -s dalvik-exchange >/dev/null 2>&1 || REQUIRED_PKGS+=("dalvik-exchange")
dpkg -s libandroid-23-java >/dev/null 2>&1 || REQUIRED_PKGS+=("libandroid-23-java")
dpkg -s default-jdk-headless >/dev/null 2>&1 || REQUIRED_PKGS+=("default-jdk-headless")

# Si el sistema tiene paquetes interrumpidos o a medio configurar, repararlos
if dpkg -l | grep -q "^iU "; then
    echo "(!) Detectados paquetes en estado pendiente. Reparando dependencias con apt..."
    sudo apt-get update && sudo apt-get --fix-broken install -y
fi

if [ ${#REQUIRED_PKGS[@]} -gt 0 ]; then
    echo "(!) Faltan las siguientes dependencias requeridas en el sistema:"
    for pkg in "${REQUIRED_PKGS[@]}"; do
        echo "   • $pkg"
    done
    echo ""
    echo ">> Instalando automáticamente mediante apt (puede requerir sudo)..."
    sudo apt-get update
    sudo apt-get --fix-broken install -y
    sudo apt-get install -y "${REQUIRED_PKGS[@]}"
    echo "✓ Dependencias del sistema instaladas con éxito."
else
    echo "✓ Todas las dependencias del sistema ya están instaladas."
fi

# Instalar dependencias en el venv si existe
if [ -d "venv" ] && [ -f "requirements.txt" ]; then
    echo "[python] Actualizando dependencias en entorno virtual local (venv)..."
    venv/bin/pip install -q -r requirements.txt 2>/dev/null || true
fi

echo "================================================================="
