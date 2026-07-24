#!/usr/bin/env bash
# Stream da câmera CSI por WebRTC (baixa latência, mídia UDP) usando o
# mediamtx: 1 binário Go que lê a câmera via libcamera (source rpiCamera,
# H.264 por HW) e serve WebRTC + um player pronto. Baixa o binário na 1ª vez.
#
# Uso:
#   ./vision/stream_webrtc.sh
#
# Abra o player:  http://<ip-do-pi>:8889/cam
# (o web app :8080 já embute esse player num <iframe>)
#
# ponytail: baixa o release mais novo do GitHub. Se quiser 100% reprodutível,
# fixe a versão em MTX_VERSION.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$DIR/mediamtx_bin/mediamtx"
CFG="$DIR/mediamtx.yml"
REPO="bluenviron/mediamtx"

if [ ! -x "$BIN" ]; then
  mkdir -p "$DIR/mediamtx_bin"
  # Pi 3/4/5 em 64-bit = arm64v8. (Troque p/ armv7 se for OS 32-bit.)
  arch="linux_arm64v8"
  echo "[webrtc] baixando mediamtx ($arch)..."
  url="$(curl -sL "https://api.github.com/repos/$REPO/releases/latest" \
    | grep -o "https://[^\"]*${arch}\.tar\.gz" | head -1)"
  if [ -z "$url" ]; then
    echo "[webrtc] ERRO: não achei o release $arch no GitHub." >&2
    exit 1
  fi
  curl -sL "$url" | tar -xz -C "$DIR/mediamtx_bin" mediamtx
  echo "[webrtc] mediamtx instalado em $BIN"
fi

echo "[webrtc] player: http://0.0.0.0:8889/cam"
exec "$BIN" "$CFG"
