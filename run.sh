#!/usr/bin/env bash
# Sobe o controle web do Roomba. Cria venv e instala deps na 1ª vez.
#
# Uso:
#   ./run.sh                     # porta serial/http padrão
#   ROOMBA_PORT=/dev/ttyACM0 ./run.sh
#   ROOMBA_HTTP_PORT=9090 ./run.sh
set -euo pipefail

cd "$(dirname "$0")"

VENV=".venv"

# Cria venv na primeira execução.
if [ ! -d "$VENV" ]; then
  echo "[run] criando venv..."
  python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

# Instala deps se aiohttp ainda não estiver presente.
if ! python -c "import aiohttp" 2>/dev/null; then
  echo "[run] instalando dependências..."
  pip install -q --disable-pip-version-check -r requirements.txt
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

echo "[run] iniciando servidor..."
exec python web/server.py
