#!/usr/bin/env bash
# Stream da câmera CSI (cabo flat — módulo Pi ov5647/imx) para o navegador.
# No Raspberry Pi OS Bookworm/trixie a CSI só fala via libcamera: NÃO existe
# /dev/video0 entregando JPEG (o ustreamer de vision/stream_cam.sh é só p/
# webcam USB). Aqui o rpicam-vid entrega JPEG pelo encoder de HW e o ffmpeg
# só REMUXA (-c copy, sem re-encode) num MJPEG HTTP — nada de Python no loop
# de quadros (ver vision/STREAMING_NOTES.md, seção 2).
#
# Uso:
#   ./vision/stream_csi.sh                  # 640x480 @10fps (padrão)
#   CAM_RES=1296x972 ./vision/stream_csi.sh # ov5647 suporta; mais pesado
#   CAM_FPS=15 CAM_PORT=9090 ./vision/stream_csi.sh
#
# Abra no navegador:  http://<ip-do-pi>:<porta>/
#
# ponytail: ffmpeg -listen serve UM cliente por vez — suficiente p/ testar
# posição da câmera. Se precisar de vários espectadores, troque por ustreamer
# com v4l2loopback ou mediamtx.
set -euo pipefail

WIDTH="${CAM_WIDTH:-640}"
HEIGHT="${CAM_HEIGHT:-480}"
FPS="${CAM_FPS:-10}"
PORT="${CAM_PORT:-8081}"

for bin in rpicam-vid ffmpeg; do
  if ! command -v "$bin" >/dev/null; then
    echo "[csi] ERRO: '$bin' não encontrado." >&2
    echo "      Instale: sudo apt install -y rpicam-apps ffmpeg" >&2
    exit 1
  fi
done

echo "[csi] streaming CSI ${WIDTH}x${HEIGHT} @${FPS}fps -> http://0.0.0.0:$PORT/"
# --inline repete os headers JPEG em cada quadro (browser precisa); --nopreview
# evita abrir janela num Pi headless.
rpicam-vid -t 0 --inline --nopreview --codec mjpeg \
  --width "$WIDTH" --height "$HEIGHT" --framerate "$FPS" -o - \
  | ffmpeg -loglevel warning -f mjpeg -i - -c:v copy \
      -f mpjpeg -listen 1 "http://0.0.0.0:$PORT"
