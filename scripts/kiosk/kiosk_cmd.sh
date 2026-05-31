#!/bin/bash
# =============================================================================
# ForenSys - Modo Kiosko
# Uso: kiosk [start|stop|status]
# =============================================================================

ACTION="${1:-start}"

case "$ACTION" in
    start)
        echo "[ForenSys] Iniciando modo kiosko..."

        # Verificar que la web app esté corriendo
        if ! systemctl is-active --quiet forensys.service 2>/dev/null; then
            echo "[ForenSys] Iniciando web app (forensys.service)..."
            sudo systemctl start forensys.service
            sleep 2
        else
            echo "[ForenSys] Web app ya está corriendo."
        fi

        # Verificar si hay un servicio kiosk instalado
        if systemctl list-unit-files kiosk.service &>/dev/null | grep -q kiosk.service; then
            echo "[ForenSys] Iniciando kiosk.service..."
            sudo systemctl start kiosk.service
        else
            # Fallback: ejecutar directamente
            echo "[ForenSys] Lanzando kiosko manualmente..."
            export XDG_RUNTIME_DIR=/run/user/$(id -u)
            export LIBSEAT_BACKEND=seatd
            export WLR_DRM_DEVICES=/dev/dri/card1
            export WLR_LIBINPUT_NO_DEVICES=1
            export WLR_RENDERER=pixman
            mkdir -p "$XDG_RUNTIME_DIR"
            chmod 700 "$XDG_RUNTIME_DIR"
            exec /usr/bin/cage -s -- chromium-browser \
                --kiosk \
                --noerrdialogs \
                --disable-infobars \
                --no-sandbox \
                --disable-dev-shm-usage \
                --ozone-platform=wayland \
                --disable-gpu \
                http://127.0.0.1:5000
        fi
        ;;

    stop)
        echo "[ForenSys] Deteniendo modo kiosko..."
        sudo systemctl stop kiosk.service 2>/dev/null || pkill -x cage
        echo "[ForenSys] Kiosko detenido."
        ;;

    status)
        echo "=== ForenSys Kiosko Status ==="
        echo "--- Web App (forensys) ---"
        systemctl status forensys.service --no-pager -l 2>/dev/null || echo "No instalado como servicio"
        echo ""
        echo "--- Kiosko (kiosk) ---"
        systemctl status kiosk.service --no-pager -l 2>/dev/null || echo "No instalado como servicio"
        ;;

    *)
        echo "Uso: kiosk [start|stop|status]"
        exit 1
        ;;
esac
