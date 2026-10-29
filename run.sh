#!/usr/bin/env bash
# Sobe o controle web e o stream WebRTC. Cria venv e instala deps na 1ª vez.
#
# Uso:
#   ./run.sh                     # porta serial/http padrão
#   ROOMBA_PORT=/dev/ttyACM0 ./run.sh
#   ROOMBA_HTTP_PORT=9090 ./run.sh
set -euo pipefail

cd "$(dirname "$0")"

VENV=".venv"
DEFAULT_TLS_DIR="${ROOMBA_TLS_DIR:-$HOME/.config/roomba_40k/tls}"

# setup_https.sh grava o par nesse diretório. Só complete automaticamente quando
# nenhuma variável customizada foi passada, para nunca misturar pares TLS.
if { [ -n "${ROOMBA_TLS_CERT:-}" ] && [ -z "${ROOMBA_TLS_KEY:-}" ]; } || \
   { [ -z "${ROOMBA_TLS_CERT:-}" ] && [ -n "${ROOMBA_TLS_KEY:-}" ]; }; then
  echo "[run] ERRO: ROOMBA_TLS_CERT e ROOMBA_TLS_KEY devem ser definidos juntos." >&2
  exit 1
fi
if [ -z "${ROOMBA_TLS_CERT:-}" ] && [ -z "${ROOMBA_TLS_KEY:-}" ] && \
   { [ ! -f "$DEFAULT_TLS_DIR/server.crt" ] || [ ! -f "$DEFAULT_TLS_DIR/server.key" ]; }; then
  echo "[run] primeiro acesso: configurando HTTPS e link da CA..."
  ./setup_https.sh
fi
if [ -z "${ROOMBA_TLS_CERT:-}" ] && [ -z "${ROOMBA_TLS_KEY:-}" ] && \
   [ -f "$DEFAULT_TLS_DIR/server.crt" ] && [ -f "$DEFAULT_TLS_DIR/server.key" ]; then
  export ROOMBA_TLS_CERT="$DEFAULT_TLS_DIR/server.crt"
  export ROOMBA_TLS_KEY="$DEFAULT_TLS_DIR/server.key"
fi

if ! command -v uv >/dev/null; then
  echo "[run] ERRO: 'uv' não encontrado. Instale uv antes de rodar."
  exit 1
fi

# Cria venv na primeira execução.
if [ ! -d "$VENV" ]; then
  echo "[run] criando venv..."
  uv venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

# Instala deps se aiohttp ainda não estiver presente.
if ! python -c "import aiohttp" 2>/dev/null; then
  echo "[run] instalando dependências..."
  uv pip install -r requirements.txt
fi

# Aviso se o usuário não está no grupo dialout (acesso à serial).
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx dialout; then
  echo "[run] AVISO: usuário fora do grupo 'dialout'. Acesso à serial pode falhar."
  echo "       Corrija com: sudo usermod -aG dialout $USER  (relogar depois)"
fi

# Aviso se o mpg123 (player de música) não estiver instalado.
if ! command -v mpg123 >/dev/null; then
  echo "[run] AVISO: 'mpg123' ausente. Música desabilitada."
  echo "       Instale com: sudo apt install mpg123   (Debian/Raspberry Pi OS)"
fi

# O interfone envia PCM cru diretamente ao ALSA através do aplay.
if ! command -v aplay >/dev/null; then
  echo "[run] AVISO: 'aplay' ausente. Interfone ao vivo desabilitado."
  echo "       Instale com: sudo apt install alsa-utils"
fi

# Deixa no máximo (e sem mute) todo controle de reprodução do cartão que o
# mpg123/aplay usam. "hw:0,0", "plughw:0,0" e "hw:Headphones" viram o cartão.
# Desligue com ROOMBA_MAX_VOLUME=0 (ex.: ao rodar no notebook).
max_card_volume() {
  local dev="${MUSIC_ALSA_DEV:-hw:1,0}" card ctl count=0
  card="${dev#*:}"
  card="${card%%,*}"
  if ! command -v amixer >/dev/null; then
    echo "[run] AVISO: 'amixer' ausente; volume do hardware não ajustado."
    return 0
  fi
  while IFS= read -r ctl; do
    amixer -c "$card" sget "$ctl" 2>/dev/null | grep -q pvolume || continue
    if amixer -q -c "$card" sset "$ctl" 100% unmute 2>/dev/null; then
      count=$((count + 1))
    fi
  done < <(amixer -c "$card" scontrols 2>/dev/null |
    sed -n "s/^Simple mixer control '\(.*\)',[0-9]*$/\1/p")
  if [ "$count" -eq 0 ]; then
    echo "[run] AVISO: nenhum controle de volume em '$dev' (cartão '$card')."
    return 0
  fi
  echo "[run] volume do hardware no máximo: $count controle(s) em '$dev'."
}

if [ "${ROOMBA_MAX_VOLUME:-1}" != "0" ]; then
  max_card_volume
fi

echo "[run] iniciando stream e servidor..."

STREAM_PID=""
WEB_PID=""
trap 'trap - EXIT INT TERM; kill "$WEB_PID" "$STREAM_PID" 2>/dev/null || true; wait "$WEB_PID" "$STREAM_PID" 2>/dev/null || true' EXIT INT TERM

./vision/stream_webrtc.sh &
STREAM_PID=$!
python -m web.server &
WEB_PID=$!

set +e
wait -n "$STREAM_PID" "$WEB_PID"
STATUS=$?
set -e
exit "$STATUS"
