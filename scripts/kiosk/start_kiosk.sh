#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export LIBSEAT_BACKEND=seatd
export WLR_DRM_DEVICES=/dev/dri/card1
export WLR_LIBINPUT_NO_DEVICES=1
export WLR_RENDERER=pixman
# ^^^ Forzar renderizado por software (pixman) — evita pantalla azul por crash EGL/GPU en RPi5
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
exec cage -s -- chromium-browser --kiosk --noerrdialogs --disable-infobars --no-sandbox --disable-dev-shm-usage --ozone-platform=wayland --disable-gpu --disable-software-rasterizer --use-gl=egl http://127.0.0.1:5000

