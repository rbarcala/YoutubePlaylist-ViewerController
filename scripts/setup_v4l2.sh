#!/bin/bash
# Configurar v4l2loopback para que cargue automáticamente al inicio del sistema
# y OBS no pida contraseña nunca más.

if [ "$EUID" -ne 0 ]; then
  echo "Por favor ejecuta este script como root: sudo bash scripts/setup_v4l2.sh"
  exit 1
fi

echo "Configurando v4l2loopback para que cargue en el arranque..."

# 1. Archivo de opciones del módulo
cat << 'MODPROBE' > /etc/modprobe.d/obs-v4l2loopback.conf
options v4l2loopback exclusive_caps=1 card_label="OBS Virtual Camera"
MODPROBE

# 2. Archivo para cargar el módulo al iniciar
cat << 'MODULES' > /etc/modules-load.d/obs-v4l2loopback.conf
v4l2loopback
MODULES

# 3. Cargar el módulo ahora mismo para no tener que reiniciar
modprobe v4l2loopback exclusive_caps=1 card_label="OBS Virtual Camera"

echo "¡Listo! El módulo de cámara virtual ahora se cargará automáticamente en cada reinicio."
echo "OBS ya no te pedirá contraseña."
