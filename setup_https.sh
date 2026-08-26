#!/usr/bin/env bash
# Gera uma CA local e um certificado HTTPS para o IP atual do Raspberry Pi.
set -euo pipefail

TLS_DIR="${ROOMBA_TLS_DIR:-$HOME/.config/roomba_40k/tls}"
PI_IP="${1:-}"

if [ -z "$PI_IP" ]; then
  read -r PI_IP _ <<< "$(hostname -I 2>/dev/null || true)"
fi
if [ -z "$PI_IP" ] && command -v ip >/dev/null; then
  PI_IP="$(ip route get 1.1.1.1 2>/dev/null \
    | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}' \
    || true)"
fi

if ! command -v openssl >/dev/null; then
  echo "[https] ERRO: 'openssl' não encontrado." >&2
  exit 1
fi
if [ -z "$PI_IP" ]; then
  echo "[https] ERRO: não encontrei o IP; use ./setup_https.sh <ip-do-pi>." >&2
  exit 1
fi

mkdir -p "$TLS_DIR"
chmod 700 "$TLS_DIR"

if [ ! -f "$TLS_DIR/ca.key" ] || [ ! -f "$TLS_DIR/ca.crt" ]; then
  openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
    -keyout "$TLS_DIR/ca.key" -out "$TLS_DIR/ca.crt" \
    -subj "/CN=Roomba Local CA"
fi

openssl req -newkey rsa:2048 -sha256 -nodes \
  -keyout "$TLS_DIR/server.key" -out "$TLS_DIR/server.csr" \
  -subj "/CN=$PI_IP"

EXT_FILE="$(mktemp)"
trap 'rm -f "$EXT_FILE"' EXIT
printf 'subjectAltName=IP:%s,DNS:localhost\nextendedKeyUsage=serverAuth\n' \
  "$PI_IP" > "$EXT_FILE"
openssl x509 -req -sha256 -days 825 \
  -in "$TLS_DIR/server.csr" -CA "$TLS_DIR/ca.crt" \
  -CAkey "$TLS_DIR/ca.key" -CAcreateserial \
  -extfile "$EXT_FILE" -out "$TLS_DIR/server.crt"
rm -f "$TLS_DIR/server.csr"
chmod 600 "$TLS_DIR/ca.key" "$TLS_DIR/server.key"

echo "[https] certificado criado para $PI_IP"
echo "[https] instale SOMENTE esta CA no celular: $TLS_DIR/ca.crt"
echo "[https] depois rode ./run.sh e abra https://$PI_IP:8080"
