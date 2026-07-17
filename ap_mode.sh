#!/usr/bin/env bash
# Põe a Raspberry Pi em modo Access Point (ponto de acesso) e libera SSH,
# para você conectar direto no Wi-Fi do robô e abrir o controle web — sem
# rede/roteador. Usa o NetworkManager (padrão no Raspberry Pi OS Bookworm+),
# que já entrega DHCP + DNS no modo hotspot. Gateway do AP: 10.42.0.1.
#
# Uso:
#   sudo ./ap_mode.sh on     # liga o AP + habilita ssh (padrão)
#   sudo ./ap_mode.sh off    # desliga o AP, volta pro Wi-Fi normal
#   sudo ./ap_mode.sh status
#
# Depois de "on": conecte no Wi-Fi "$SSID" (senha "$PASS") e abra
#   http://10.42.0.1:8080
#
# ponytail: assume NetworkManager (Bookworm+). Bullseye/antigo usa
# dhcpcd+hostapd+dnsmasq — outra receita; migre pra Bookworm em vez de
# reescrever este script.
set -euo pipefail

SSID="${AP_SSID:-Roomba40k}"
PASS="${AP_PASS:-roomba123}"          # troque: >=8 chars (exigência WPA2)
IFACE="${AP_IFACE:-wlan0}"
HTTP_PORT="${ROOMBA_HTTP_PORT:-8080}"

if ! command -v nmcli >/dev/null; then
  echo "[ap] ERRO: nmcli não encontrado — este script exige NetworkManager." >&2
  exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "[ap] rode com sudo." >&2
  exit 1
fi

allow_ssh() {
  # ssh vem desabilitado por padrão no Raspberry Pi OS; garante acesso remoto.
  systemctl enable --now ssh 2>/dev/null || systemctl enable --now sshd
  echo "[ap] ssh habilitado."
}

case "${1:-on}" in
  on)
    allow_ssh
    nmcli device wifi hotspot ifname "$IFACE" ssid "$SSID" password "$PASS"
    # Reconecta o AP sozinho no boot enquanto estiver ligado.
    nmcli connection modify Hotspot connection.autoconnect yes
    echo "[ap] AP no ar: SSID '$SSID' | senha '$PASS'"
    echo "[ap] conecte e abra: http://10.42.0.1:${HTTP_PORT}"
    ;;
  off)
    nmcli connection down Hotspot 2>/dev/null || true
    nmcli connection modify Hotspot connection.autoconnect no 2>/dev/null || true
    nmcli device connect "$IFACE" 2>/dev/null || true   # volta pro Wi-Fi salvo
    echo "[ap] AP desligado; voltando ao Wi-Fi normal."
    ;;
  status)
    nmcli -f NAME,TYPE,DEVICE connection show --active
    ;;
  *)
    echo "uso: sudo $0 {on|off|status}" >&2
    exit 1
    ;;
esac
