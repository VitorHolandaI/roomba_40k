#!/usr/bin/env bash
# Stream da câmera CSI (cabo flat — módulo Pi ov5647) para o navegador.
# Sobe o servidor MJPEG do picamera2 (vision/csi_server.py): encoder JPEG de
# HW, multi-cliente, sobrevive a reconexão. Substituiu o antigo rpicam-vid|
# ffmpeg, que caía com 'Broken pipe' quando o cliente do -listen 1 desconectava.
#
# Uso:
#   ./vision/stream_csi.sh                  # 640x480 (padrão)
#   CAM_WIDTH=1296 CAM_HEIGHT=972 ./vision/stream_csi.sh
#   CAM_PORT=9090 ./vision/stream_csi.sh
#
# Abra:  http://<ip-do-pi>:8081/   (ou embutido no app :8080 via <img>)
set -euo pipefail

# picamera2 vem do apt (python do sistema), não do venv uv deste projeto.
if ! python3 -c "import picamera2" 2>/dev/null; then
  echo "[csi] ERRO: picamera2 não encontrado." >&2
  echo "      Instale: sudo apt install -y python3-picamera2" >&2
  exit 1
fi

exec python3 "$(dirname "$0")/csi_server.py"
