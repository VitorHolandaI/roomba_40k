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
SCHEME="http"

if [ -n "${ROOMBA_TLS_CERT:-}" ] && [ -n "${ROOMBA_TLS_KEY:-}" ]; then
  export MTX_WEBRTCENCRYPTION=true
  export MTX_WEBRTCSERVERCERT="$ROOMBA_TLS_CERT"
  export MTX_WEBRTCSERVERKEY="$ROOMBA_TLS_KEY"
  SCHEME="https"
elif [ -n "${ROOMBA_TLS_CERT:-}" ] || [ -n "${ROOMBA_TLS_KEY:-}" ]; then
  echo "[webrtc] ERRO: certificado e chave TLS devem ser definidos juntos." >&2
  exit 1
fi

if [ ! -x "$BIN" ]; then
  mkdir -p "$DIR/mediamtx_bin"
  # Pi 3/4/5 em 64-bit = arm64. (Troque p/ armv7 se for OS 32-bit.)
  arch="linux_arm64"
  echo "[webrtc] baixando mediamtx ($arch)..."
  # Pega a tag pelo redirect do github.com (a api.github.com limita 60/h sem
  # token e vinha vazia); daí monta a URL do asset.
  tag="$(curl -sI "https://github.com/$REPO/releases/latest" \
    | grep -i '^location:' | grep -o 'v[0-9][^[:space:]]*' | tr -d '\r')"
  if [ -z "$tag" ]; then
    echo "[webrtc] ERRO: não consegui achar a versão mais nova no GitHub." >&2
    exit 1
  fi
  url="https://github.com/$REPO/releases/download/$tag/mediamtx_${tag}_${arch}.tar.gz"
  echo "[webrtc] $url"
  curl -fSL "$url" | tar -xz -C "$DIR/mediamtx_bin" mediamtx
  echo "[webrtc] mediamtx instalado em $BIN"
fi

# O mediamtx às vezes só descobre 127.0.0.1 como candidato ICE — aí clientes
# em outra máquina dão "deadline exceeded while waiting connection". Anuncia
# o IP real (wifi ou AP) para o WebRTC ter um candidato alcançável.
IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
if [ -z "$IP" ] && command -v ip >/dev/null; then
  IP="$(ip route get 1.1.1.1 2>/dev/null \
    | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}' \
    || true)"
fi
if [ -n "$IP" ]; then
  export MTX_WEBRTCADDITIONALHOSTS="$IP"
  echo "[webrtc] anunciando host ICE: $IP"
fi

echo "[webrtc] player: $SCHEME://$IP:8889/cam"
exec "$BIN" "$CFG"
