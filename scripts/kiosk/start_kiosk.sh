#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export LIBSEAT_BACKEND=seatd
export WLR_DRM_DEVICES=/dev/dri/card1
export WLR_LIBINPUT_NO_DEVICES=1
export WLR_RENDERER=pixman
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
exec cage -s -- /usr/bin/chromium --kiosk --noerrdialogs --disable-infobars --no-sandbox --disable-dev-shm-usage --ozone-platform=wayland --disable-gpu http://127.0.0.1:5000

