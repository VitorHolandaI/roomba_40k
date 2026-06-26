#!/usr/bin/env bash
# Stream da webcam USB para o navegador com ustreamer (C, leve no RPi 3B+).
# Serve para testar rápido a POSIÇÃO da câmera no robô. Detalhes e diagnóstico
# (JPEG vs MJPEG, brownout de energia) em vision/STREAMING_NOTES.md.
#
# Uso:
#   ./vision/stream_cam.sh                 # 320x240 @10fps (padrão, seguro)
#   CAM_RES=160x120 ./vision/stream_cam.sh # mais leve (se cair energia/travar)
#   CAM_RES=640x480 ./vision/stream_cam.sh # só com energia estável
#   CAM_DEVICE=/dev/video1 CAM_PORT=9090 ./vision/stream_cam.sh
#
# Abra no navegador:  http://<ip-do-pi>:<porta>/
set -euo pipefail

DEVICE="${CAM_DEVICE:-/dev/video0}"
RES="${CAM_RES:-320x240}"
FPS="${CAM_FPS:-10}"
PORT="${CAM_PORT:-8081}"

if ! command -v ustreamer >/dev/null; then
  echo "[cam] ERRO: 'ustreamer' não encontrado."
  echo "      Instale com: sudo apt install ustreamer   (Debian/Raspberry Pi OS)"
  exit 1
fi

if [ ! -e "$DEVICE" ]; then
  echo "[cam] ERRO: dispositivo $DEVICE não existe. Liste com: v4l2-ctl --list-devices"
  exit 1
fi

echo "[cam] streaming $DEVICE  $RES @${FPS}fps  ->  http://0.0.0.0:$PORT/"
# --format=JPEG casa com o driver (a câmera entrega JPEG, não MJPG) e silencia
# o aviso de fallback. --drop-same-frames descarta quadros parados p/ não
# acumular latência.
exec ustreamer \
  --device="$DEVICE" \
  --resolution="$RES" \
  --format=JPEG \
  --desired-fps="$FPS" \
  --drop-same-frames=30 \
  --host=0.0.0.0 \
  --port="$PORT"
