#!/usr/bin/env python3
"""Servidor web para controle remoto do Roomba (iRobot Create2).

Arquitetura (não negociável):
  - A porta serial é um recurso ÚNICO e bloqueante (pycreate2 é síncrono).
  - Uma ÚNICA thread de controle é dona exclusiva do objeto `Create2`.
  - Os handlers web (asyncio) NUNCA tocam na serial; apenas ESCREVEM o
    "estado desejado" (target left/right + timestamp) protegido por lock.
  - Último comando vence (overwrite), nunca enfileira -> sensação real-time.
  - A thread de controle roda ~50 Hz e só chama drive_direct quando o alvo
    muda. Heartbeat: se nenhum comando novo chegar dentro de TIMEOUT, para.
  - Bateria é lida ~a cada 2 s (fora do hot loop) e publicada para os clientes.
"""

import os
import json
import time
import asyncio
import threading

from aiohttp import web, WSMsgType

from pycreate2 import Create2

from music import MusicPlayer


# ─────────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────────

PORT = os.environ.get("ROOMBA_PORT", "/dev/ttyUSB0")
HTTP_PORT = int(os.environ.get("ROOMBA_HTTP_PORT", "8080"))

# Música: pasta de MP3s e saída ALSA. No RPi o alto-falante no jack 3.5mm
# costuma ser card 1 (bcm2835 Headphones) -> hw:1,0.
MUSIC_DIR = os.environ.get("MUSIC_DIR", "~/Music")
MUSIC_ALSA_DEV = os.environ.get("MUSIC_ALSA_DEV", "hw:1,0")

MIN_VEL = 50
MAX_VEL = 500

# Carrinho RC: se nenhum comando novo chegar nesse intervalo, o robô para.
# Maior que os 0.15 s da CLI para tolerar jitter de rede.
TIMEOUT = 0.3

# Intervalo de leitura/publicação da bateria.
BATTERY_UPDATE = 2.0

# Período do loop de controle (~50 Hz).
LOOP_PERIOD = 0.02

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


# ─────────────────────────────────────────────────────────────────────────────
# Estado compartilhado entre a thread de controle e o mundo asyncio
# ─────────────────────────────────────────────────────────────────────────────

class SharedState:
    """Estado desejado + telemetria, protegido por um lock.

    A camada web só ESCREVE o alvo (set_drive/request_*). A thread de
    controle LÊ o alvo e ESCREVE a telemetria (bateria).
    """

    def __init__(self):
        self.lock = threading.Lock()

        # Alvo de velocidade (mm/s) das rodas e quando foi atualizado.
        self.target_left = 0
        self.target_right = 0
        self.last_update = 0.0

        # Pedido pontual de dock (consumido pela thread de controle).
        self.dock_requested = False

        # Última leitura de bateria (dict) para broadcast.
        self.battery = {"type": "battery", "ok": False}

    # -- escrito pela camada web ---------------------------------------------

    def set_drive(self, left, right):
        """Define o alvo das rodas. Último comando vence; reseta heartbeat."""
        with self.lock:
            self.target_left = int(left)
            self.target_right = int(right)
            self.last_update = time.time()

    def request_stop(self):
        with self.lock:
            self.target_left = 0
            self.target_right = 0
            self.last_update = time.time()

    def request_dock(self):
        with self.lock:
            self.target_left = 0
            self.target_right = 0
            self.dock_requested = True

    # -- lido/escrito pela thread de controle --------------------------------

    def snapshot_target(self):
        with self.lock:
            return self.target_left, self.target_right, self.last_update

    def take_dock_request(self):
        with self.lock:
            req = self.dock_requested
            self.dock_requested = False
            return req

    def set_battery(self, info):
        with self.lock:
            self.battery = info

    def get_battery(self):
        with self.lock:
            return dict(self.battery)


shared = SharedState()


# ─────────────────────────────────────────────────────────────────────────────
# Thread de controle: dona exclusiva da serial / objeto Create2
# ─────────────────────────────────────────────────────────────────────────────

def ler_bateria(bot):
    """Obtém informações da bateria (espelha a lógica do main.py)."""
    try:
        s = bot.get_sensors()

        percentual = (s.battery_charge / s.battery_capacity) * 100

        estado = {
            0: "Não carregando",
            1: "Recuperação",
            2: "Carregando",
            3: "Carga lenta",
            4: "Completa",
            5: "Falha",
        }.get(s.charger_state, "Desconhecido")

        return {
            "type": "battery",
            "ok": True,
            "percent": round(percentual, 1),
            "voltage": round(s.voltage / 1000, 2),
            "current": s.current,
            "state": estado,
        }

    except Exception:
        return {"type": "battery", "ok": False}


class ControlThread(threading.Thread):
    """Loop de controle bloqueante rodando em thread dedicada."""

    def __init__(self, state):
        super().__init__(daemon=True)
        self.state = state
        self.bot = None
        self._running = threading.Event()
        self._running.set()

        # True quando o robô está em Passive (após Dock) e ignora movimento.
        self.passivo = False

        # Último alvo efetivamente enviado à serial (evita spam).
        self.sent_left = None
        self.sent_right = None

    # -- ciclo de vida do robô (reutiliza lógica do main.py) -----------------

    def _conectar(self):
        try:
            self.bot = Create2(PORT)
            self.bot.start()
            self.bot.safe()
            time.sleep(0.2)
            print(f"[control] Conectado ao Roomba em {PORT}")
        except Exception as e:
            # Robô ausente em dev: segue rodando sem hardware.
            self.bot = None
            # O Create2 meio-construído seria coletado pelo GC e seu __del__
            # chamaria drive_stop() numa porta fechada -> PortNotOpenError.
            # Neutralizamos o destrutor para não poluir o log.
            Create2.__del__ = lambda self: None
            print(f"[control] AVISO: falha ao conectar em {PORT}: {e}")

    def _garantir_safe(self):
        """Reativa Safe se o robô caiu em Passive (ex: após Dock)."""
        if self.passivo and self.bot is not None:
            try:
                self.bot.safe()
            except Exception:
                pass
            self.passivo = False

    def _seek_dock(self):
        """Envia o Roomba para a base (opcode 143, a partir de Passive)."""
        if self.bot is None:
            self.passivo = True
            return
        try:
            self.bot.drive_stop()
            self.bot.start()
            time.sleep(0.2)
            self.bot.SCI.write(143)
            self.passivo = True
        except Exception as e:
            print(f"[control] erro no dock: {e}")
        # Zera o que foi enviado para forçar reenvio no próximo movimento.
        self.sent_left = None
        self.sent_right = None

    def _drive(self, left, right):
        """Só envia à serial quando o alvo realmente muda."""
        if left == self.sent_left and right == self.sent_right:
            return

        if self.bot is not None:
            try:
                if left == 0 and right == 0:
                    self.bot.drive_stop()
                else:
                    # Movimento manual: garante Safe se voltamos de Passive.
                    self._garantir_safe()
                    self.bot.drive_direct(int(left), int(right))
            except Exception as e:
                print(f"[control] erro no drive: {e}")
                return

        self.sent_left = left
        self.sent_right = right

    # -- loop principal -------------------------------------------------------

    def run(self):
        self._conectar()

        ultima_leitura_bateria = 0.0

        while self._running.is_set():
            agora = time.time()

            # Pedido de dock tem prioridade.
            if self.state.take_dock_request():
                self._seek_dock()

            target_left, target_right, last_update = self.state.snapshot_target()

            # Heartbeat do carrinho RC: comando velho -> para.
            if agora - last_update > TIMEOUT:
                target_left = 0
                target_right = 0

            self._drive(target_left, target_right)

            # Bateria fora do hot loop (~2 s).
            if agora - ultima_leitura_bateria >= BATTERY_UPDATE:
                self.state.set_battery(ler_bateria(self.bot))
                ultima_leitura_bateria = agora

            time.sleep(LOOP_PERIOD)

        self._shutdown()

    def stop(self):
        self._running.clear()

    def _shutdown(self):
        """Para o robô e encerra a conexão com segurança (vide main.py)."""
        if self.bot is None:
            return
        print("[control] Parando o robô e encerrando conexão...")
        try:
            self.bot.drive_stop()
            self.bot.start()
            self.bot.close()
        except Exception:
            pass
        # pycreate2 chama drive_stop() no __del__ (GC), escrevendo numa porta
        # já fechada -> PortNotOpenError. Neutralizamos o destrutor.
        Create2.__del__ = lambda self: None


# ─────────────────────────────────────────────────────────────────────────────
# Camada web (aiohttp) — só ESCREVE estado desejado, nunca toca na serial
# ─────────────────────────────────────────────────────────────────────────────

# Conjunto de WebSockets ativos (para broadcast de bateria).
clients = set()

# Single-driver lock: apenas UM cliente comanda o robô por vez; os demais
# ficam como espectadores (só veem bateria). O primeiro a conectar vira
# motorista; outro pode assumir enviando {"type":"claim"}.
driver = None

# Player de música (boombox-roomba) e o event loop asyncio para agendar
# broadcasts a partir da thread do player.
player = None
app_loop = None


def _on_music_change():
    """Callback (thread do player) -> agenda broadcast no loop asyncio."""
    if app_loop is not None:
        app_loop.call_soon_threadsafe(lambda: asyncio.ensure_future(broadcast_music()))


async def broadcast_music():
    if player is None:
        return
    info = player.state()
    for ws in list(clients):
        try:
            await ws.send_json(info)
        except Exception:
            clients.discard(ws)


async def notify_roles():
    """Informa a cada cliente se ele é o motorista atual."""
    for ws in list(clients):
        try:
            await ws.send_json({"type": "role", "driver": ws is driver})
        except Exception:
            clients.discard(ws)


async def handle_index(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))


def _clamp_vel(v):
    """Limita um valor de roda ao intervalo seguro [-MAX_VEL, MAX_VEL]."""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 0
    if v > MAX_VEL:
        return MAX_VEL
    if v < -MAX_VEL:
        return -MAX_VEL
    return v


async def handle_ws(request):
    global driver

    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    clients.add(ws)
    # Primeiro a conectar assume o controle automaticamente.
    if driver is None:
        driver = ws
    print(f"[ws] cliente conectado ({len(clients)} ativos)")

    # Envia a última bateria conhecida e o papel (motorista/espectador).
    try:
        await ws.send_json(shared.get_battery())
        if player is not None:
            await ws.send_json(player.state())
    except Exception:
        pass
    await notify_roles()

    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                if msg.type == WSMsgType.ERROR:
                    break
                continue

            try:
                data = json.loads(msg.data)
            except (ValueError, TypeError):
                continue

            tipo = data.get("type")

            # Pedido de assumir o controle: vira motorista e avisa todos.
            if tipo == "claim":
                if ws is not driver:
                    driver = ws
                    shared.request_stop()  # estado limpo ao trocar de dono
                    await notify_roles()
                continue

            # Música: qualquer cliente pode controlar (não é crítico/seguro).
            if tipo == "music":
                if player is not None:
                    acao = data.get("action")
                    if acao == "play":
                        player.play(data.get("index"))
                    elif acao == "pause":
                        player.pause()
                    elif acao == "stop":
                        player.stop()
                    elif acao == "next":
                        player.next()
                    elif acao == "prev":
                        player.prev()
                    elif acao == "volume":
                        player.set_volume(data.get("value", 80))
                    elif acao == "rescan":
                        player.rescan()
                continue

            # Comandos de movimento só valem para o motorista atual.
            if ws is not driver:
                continue

            if tipo == "drive":
                left = _clamp_vel(data.get("left", 0))
                right = _clamp_vel(data.get("right", 0))
                shared.set_drive(left, right)

            elif tipo == "stop":
                shared.request_stop()

            elif tipo == "dock":
                shared.request_dock()

            elif tipo == "vel":
                # Ajuste de velocidade do d-pad é tratado no cliente; aqui
                # apenas ignoramos (o cliente envia drive já escalado).
                pass

    finally:
        clients.discard(ws)
        # Para o robô imediatamente quando o WebSocket cai.
        shared.request_stop()
        # Se o motorista saiu, promove outro cliente (se houver) e avisa.
        if ws is driver:
            driver = next(iter(clients), None)
            await notify_roles()
        print(f"[ws] cliente desconectado ({len(clients)} ativos)")

    return ws


async def battery_broadcaster(app):
    """Task de fundo: publica a bateria para todos os clientes (~2 s)."""
    try:
        while True:
            await asyncio.sleep(BATTERY_UPDATE)
            if not clients:
                continue
            info = shared.get_battery()
            for ws in list(clients):
                try:
                    await ws.send_json(info)
                except Exception:
                    clients.discard(ws)
    except asyncio.CancelledError:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap da aplicação
# ─────────────────────────────────────────────────────────────────────────────

async def on_startup(app):
    global player, app_loop
    app_loop = asyncio.get_running_loop()

    app["control"] = ControlThread(shared)
    app["control"].start()
    app["broadcaster"] = asyncio.create_task(battery_broadcaster(app))

    player = MusicPlayer(MUSIC_DIR, alsa_dev=MUSIC_ALSA_DEV, on_change=_on_music_change)
    player.start()


async def on_cleanup(app):
    # Encerra clientes WS.
    for ws in list(clients):
        try:
            await ws.close()
        except Exception:
            pass

    task = app.get("broadcaster")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    ctrl = app.get("control")
    if ctrl:
        ctrl.stop()
        ctrl.join(timeout=2.0)

    if player is not None:
        player.stop_proc()


def build_app():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", handle_ws)
    app.router.add_static("/static/", STATIC_DIR, name="static")
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main():
    app = build_app()
    print(f"[http] servindo em http://0.0.0.0:{HTTP_PORT}  (serial: {PORT})")
    web.run_app(app, host="0.0.0.0", port=HTTP_PORT, print=None)


if __name__ == "__main__":
    main()
