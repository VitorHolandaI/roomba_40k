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
python web/server.py
```

Depois abra `http://<ip-do-pi>:8080` no navegador.

## Variáveis de ambiente

| Variável            | Padrão           | Descrição                       |
|---------------------|------------------|---------------------------------|
| `ROOMBA_PORT`       | `/dev/ttyUSB0`   | Porta serial do Create2         |
| `ROOMBA_HTTP_PORT`  | `8080`           | Porta HTTP do servidor web      |

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

> O robô pode estar ausente em ambiente de desenvolvimento: o servidor
> sobe normalmente e apenas registra um aviso, sem travar.
