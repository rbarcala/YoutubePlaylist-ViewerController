#!/bin/bash
# Lanzador de Fondos Stream — Linux (Backend Flask + Controller Nativo GTK / Web)
# Mantiene compatibilidad total con ejecuciones previas y lanza la nueva app

DIRECTORIO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIRECTORIO" || exit 1

# Si se pasa --web, --viewer u otros argumentos, se pasan a la app
exec "$DIRECTORIO/bin/youtube-stream-controller" "$@"
