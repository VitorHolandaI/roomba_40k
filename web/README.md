# Roomba RC — Controle Web

Controle remoto em tempo real (estilo carrinho RC) para o iRobot Create2,
servido por uma aplicação web leve feita para rodar num Raspberry Pi 3B+.

Abra o endereço no celular ou no desktop e dirija o robô em tempo real.

## Arquitetura

- A porta serial é um recurso **único e bloqueante** (`pycreate2` é síncrono).
- Uma **única thread de controle** é dona exclusiva do objeto `Create2`.
- Os handlers web (asyncio) **nunca** tocam na serial: só escrevem o
  "estado desejado" (velocidade alvo das rodas + timestamp), protegido por lock.
- **Último comando vence** (sobrescreve, nunca enfileira) → sensação real-time.
- Loop de controle a ~50 Hz; `drive_direct` só é chamado quando o alvo muda.
- **Heartbeat**: se nenhum comando novo chegar em ~0,3 s, o robô para sozinho.
  O cliente reenvia o comando ~10 Hz enquanto um controle está ativo.
- Em desconexão do WebSocket, o robô para imediatamente.
- Bateria é lida ~a cada 2 s (fora do hot loop) e transmitida a todos os clientes.

## Instalação

```bash
pip install -r requirements.txt
# (aiohttp + pycreate2 + pyserial)
```

## Como rodar

```bash
./run.sh
```

O script inicia o servidor web e o stream WebRTC juntos. Depois abra
`http://<ip-do-pi>:8080` no navegador; `Ctrl+C` encerra os dois processos.

## HTTPS e microfone no celular

O navegador só libera o microfone em HTTPS. No Raspberry Pi, gere uma CA local
e um certificado para o IP atual:

```bash
./setup_https.sh
```

Se o Pi tiver várias interfaces e detectar o endereço errado, passe o IP da
rede usada pelo celular: `./setup_https.sh 192.168.1.50`.

Instale **somente** o arquivo `~/.config/roomba_40k/tls/ca.crt` como certificado
de CA no celular. Nunca copie `ca.key` ou `server.key`. Depois, `./run.sh`
detecta o certificado automaticamente e sobe o controle em
`https://<ip-do-pi>:8080` e a câmera em `https://<ip-do-pi>:8889`.

Se o IP do Pi mudar, rode `./setup_https.sh` novamente para emitir um
certificado com o novo IP.

## Variáveis de ambiente

| Variável            | Padrão           | Descrição                       |
|---------------------|------------------|---------------------------------|
| `ROOMBA_PORT`       | `/dev/ttyUSB0`   | Porta serial do Create2         |
| `ROOMBA_HTTP_PORT`  | `8080`           | Porta HTTP do servidor web      |
| `VOICE_ALSA_DEV`    | `plughw:1,0`     | Saída ALSA do interfone          |
| `ROOMBA_TLS_CERT`   | detecção local   | Certificado HTTPS opcional       |
| `ROOMBA_TLS_KEY`    | detecção local   | Chave HTTPS opcional             |

Exemplo:

```bash
ROOMBA_PORT=/dev/ttyUSB0 ROOMBA_HTTP_PORT=8080 python web/server.py
```

## Acesso à serial (Raspberry Pi)

O usuário precisa pertencer ao grupo `dialout` para acessar `/dev/ttyUSB0`
sem `sudo`:

```bash
sudo usermod -aG dialout pi
# faça logout/login (ou reinicie) para o grupo passar a valer
```

## Controles na interface

- **D-Pad**: botões de toque (frente/ré/esquerda/direita). Segure = move,
  solte = para. Slider de velocidade (50..500 mm/s).
- **Joystick analógico**: arraste o thumbstick; a velocidade é proporcional
  ao deslocamento (mixagem differential/arcade). Funciona com toque e mouse.
- **Dock**: envia o robô para a base (opcode 143). O robô entra em Passive;
  o próximo comando de movimento re-entra em Safe automaticamente.
- **STOP**: para imediatamente.
- **FALAR AO VIVO**: abre um WebSocket PCM mono de 16 kHz diretamente para
  `aplay` no Raspberry Pi. Toque novamente para encerrar. Música em andamento
  é parada antes de o interfone assumir a saída de áudio.

> O robô pode estar ausente em ambiente de desenvolvimento: o servidor
> sobe normalmente e apenas registra um aviso, sem travar.
