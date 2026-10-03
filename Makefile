# Makefile para YouTube Stream Controller
SHELL := /bin/bash
APP_NAME := youtube-stream-controller
VERSION := 1.0.0
PREFIX ?= $(HOME)/.local

.PHONY: help install install-deb uninstall run run-web viewer release clean

help:
	@echo "================================================================="
	@echo "               YouTube Stream Controller — Makefile              "
	@echo "================================================================="
	@echo "Comandos disponibles:"
	@echo "  make install       -> Instala la app en Ubuntu (~/.local) y buscador del OS"
	@echo "  make run           -> Inicia la aplicación Controller nativa de escritorio"
	@echo "  make run-web       -> Inicia el Controller en modo navegador web"
	@echo "  make viewer        -> Abre directamente la pantalla de fondo (Viewer)"
	@echo "  make release       -> Compila los paquetes instalables (.deb y .apk)"
	@echo "  make install-deb   -> Instala el paquete .deb del sistema (requiere sudo)"
	@echo "  make uninstall     -> Desinstala la app del sistema del usuario"
	@echo "  make clean         -> Limpia archivos temporales y de compilación"
	@echo "================================================================="

# Instalación a nivel de usuario (sin necesidad de sudo)
install:
	@echo "[install] Preparando entorno Python y dependencias..."
	@if [ ! -d "venv" ]; then \
		python3 -m venv --system-site-packages venv; \
	fi
	@echo "[install] Verificando e instalando dependencias en venv..."
	@venv/bin/pip install -r requirements.txt 2>/dev/null || true
	@echo "[install] Instalando lanzador de escritorio nativo de Ubuntu..."
	@mkdir -p $(PREFIX)/share/applications
	@mkdir -p $(PREFIX)/bin
	@mkdir -p $(PREFIX)/share/icons/hicolor/scalable/apps
	@for s in 16 32 48 64 128 256 512; do \
		mkdir -p $(PREFIX)/share/icons/hicolor/$${s}x$${s}/apps; \
		if [ -f assets/icons/$${s}x$${s}/$(APP_NAME).png ]; then \
			cp assets/icons/$${s}x$${s}/$(APP_NAME).png $(PREFIX)/share/icons/hicolor/$${s}x$${s}/apps/$(APP_NAME).png; \
		fi \
	done
	@cp assets/icon.svg $(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_NAME).svg
	@# Generar desktop file con ruta absoluta para mayor compatibilidad
	@sed 's|Exec=$(APP_NAME)|Exec=$(PREFIX)/bin/$(APP_NAME)|g' $(APP_NAME).desktop > $(PREFIX)/share/applications/$(APP_NAME).desktop
	@ln -sf $(CURDIR)/bin/$(APP_NAME) $(PREFIX)/bin/$(APP_NAME)
	@chmod +x $(PREFIX)/bin/$(APP_NAME)
	@chmod +x $(PREFIX)/share/applications/$(APP_NAME).desktop
	@if command -v update-desktop-database >/dev/null 2>&1; then \
		update-desktop-database $(PREFIX)/share/applications || true; \
	fi
	@if command -v gtk-update-icon-cache >/dev/null 2>&1; then \
		gtk-update-icon-cache -q -t -f $(PREFIX)/share/icons/hicolor || true; \
	fi
	@echo "✓ Instalación completada con éxito."
	@echo "✓ Para asegurar que el sistema tenga todos los paquetes, ejecuta en la terminal:"
	@echo "    sudo apt install -y python3-flask yt-dlp python3-requests"
	@echo "✓ Ahora puedes abrir la aplicación buscando 'YouTube Stream Controller' en el buscador de Ubuntu (tecla Super/Windows)!"

# Instalación del paquete Debian para todo el sistema
install-deb: release
	@echo "[install-deb] Instalando paquete .deb en Ubuntu con resolución automática de dependencias..."
	sudo apt install -y ./release/$(APP_NAME)_$(VERSION)_all.deb || (sudo dpkg -i release/$(APP_NAME)_$(VERSION)_all.deb && sudo apt-get install -f -y)

# Desinstalación limpia
uninstall:
	@echo "[uninstall] Eliminando lanzadores e iconos..."
	@rm -f $(PREFIX)/share/applications/$(APP_NAME).desktop
	@rm -f $(PREFIX)/bin/$(APP_NAME)
	@rm -f $(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_NAME).svg
	@for s in 16 32 48 64 128 256 512; do \
		rm -f $(PREFIX)/share/icons/hicolor/$${s}x$${s}/apps/$(APP_NAME).png; \
	done
	@if command -v update-desktop-database >/dev/null 2>&1; then \
		update-desktop-database $(PREFIX)/share/applications || true; \
	fi
	@echo "✓ Desinstalación completada."

# Ejecutar la aplicación en modo nativo de escritorio (por defecto)
run:
	@./bin/$(APP_NAME)

# Ejecutar en modo navegador web
run-web:
	@./bin/$(APP_NAME) --mode web

# Abrir el viewer
viewer:
	@./bin/$(APP_NAME) --viewer

# Generar releases (.deb y .apk) con instalación automática de dependencias
release:
	@bash scripts/install_deps.sh
	@python3 scripts/build_release.py

# Limpiar archivos temporales
clean:
	@rm -rf build/ __pycache__/ *.pyc
	@echo "✓ Directorio limpio."
