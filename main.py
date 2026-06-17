#!/usr/bin/env python3

import sys
import time
import tty
import termios
import select

from pycreate2 import Create2

PORT = "/dev/ttyUSB0"

# Velocidade inicial (mm/s)
vel = 150

MIN_VEL = 50
MAX_VEL = 500

# Se nenhuma tecla for recebida nesse intervalo,
# o robô é parado automaticamente.
TIMEOUT = 0.15

# Intervalo de atualização da bateria
BATTERY_UPDATE = 2.0


# ANSI colors
RESET = "\033[0m"
BOLD = "\033[1m"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
WHITE = "\033[37m"
GRAY = "\033[90m"


def color(text, code):
    return f"{code}{text}{RESET}"


def get_key():
    """Lê uma tecla sem bloquear."""
    r, _, _ = select.select([sys.stdin], [], [], 0)

    if r:
        return sys.stdin.read(1)

    return None


def seek_dock():
    """Envia o Roomba para a base.

    Opcode 143 (Seek Dock) faz o robô voltar para o modo Passive da OI.
    Em Passive os comandos de movimento são ignorados, então marcamos
    `passivo = True` para re-entrar em Safe na próxima tecla manual.
    """
    global passivo
    bot.drive_stop()
    bot.start()          # Seek Dock atua a partir do modo Passive
    time.sleep(0.2)
    bot.SCI.write(143)   # 143 = Force Seeking Dock (opcode int, não bytes!)
    passivo = True


def garantir_safe():
    """Reativa o modo Safe se o robô caiu em Passive (ex: após Dock)."""
    global passivo
    if passivo:
        bot.safe()
        passivo = False


def atualizar_sensores():
    """Obtém informações da bateria."""
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
            "percentual": percentual,
            "voltagem": s.voltage / 1000,
            "corrente": s.current,
            "estado": estado,
        }

    except Exception:
        return None


def formatar_bateria(info):
    if info is None:
        return color("N/D", RED)

    pct = info["percentual"]

    if pct >= 60:
        cor = GREEN
    elif pct >= 25:
        cor = YELLOW
    else:
        cor = RED

    return color(f"{pct:5.1f}%", cor)


def mostrar_status(acao):
    bateria = formatar_bateria(bateria_info)

    if acao == "Parado":
        acao_cor = color(f"{acao:<10}", WHITE)

    elif acao == "Dock":
        acao_cor = color(f"{acao:<10}", CYAN)

    else:
        acao_cor = color(f"{acao:<10}", GREEN)

    extra = ""

    if bateria_info is not None:
        extra = (
            f" | {GRAY}{bateria_info['voltagem']:.1f}V{RESET}"
            f" | {GRAY}{bateria_info['corrente']}mA{RESET}"
        )

    linha = (
        f"\r{BOLD}[{acao_cor}]{RESET} "
        f"Vel: {color(f'{vel:>3} mm/s', BLUE)}"
        f" | Bat: {bateria}"
        f"{extra}"
    )

    print(linha, end="", flush=True)


print(color("\n🤖 Conectando ao Roomba...\n", CYAN))

bot = Create2(PORT)
bot.start()
bot.safe()

time.sleep(0.2)

fd = sys.stdin.fileno()
old_settings = termios.tcgetattr(fd)

tty.setcbreak(fd)

ultima_acao = time.time()
movendo = False

bateria_info = None
ultima_leitura_bateria = 0

# True quando o robô está em modo Passive (após Dock) e ignora movimento.
passivo = False

print(
    f"""{BOLD}
Controles
──────────
{color("W", GREEN)} = frente      {color("S", GREEN)} = ré
{color("A", GREEN)} = esquerda    {color("D", GREEN)} = direita

{color("+", BLUE)} = aumentar velocidade
{color("-", BLUE)} = diminuir velocidade

{color("B", CYAN)} = voltar para a base

{color("ESPAÇO", YELLOW)} = parar
{color("Q", RED)} = sair
{RESET}
"""
)

mostrar_status("Parado")

try:
    while True:
        agora = time.time()

        if agora - ultima_leitura_bateria >= BATTERY_UPDATE:
            bateria_info = atualizar_sensores()
            ultima_leitura_bateria = agora

            mostrar_status("Movendo" if movendo else "Parado")

        tecla = get_key()

        if tecla:
            tecla = tecla.lower()
            ultima_acao = agora

            if tecla == "w":
                garantir_safe()
                bot.drive_direct(vel, vel)
                movendo = True
                mostrar_status("Frente")

            elif tecla == "s":
                garantir_safe()
                bot.drive_direct(-vel, -vel)
                movendo = True
                mostrar_status("Ré")

            elif tecla == "a":
                garantir_safe()
                bot.drive_direct(-vel, vel)
                movendo = True
                mostrar_status("Esquerda")

            elif tecla == "d":
                garantir_safe()
                bot.drive_direct(vel, -vel)
                movendo = True
                mostrar_status("Direita")

            elif tecla == "+":
                vel = min(MAX_VEL, vel + 25)
                mostrar_status("Movendo" if movendo else "Parado")

            elif tecla == "-":
                vel = max(MIN_VEL, vel - 25)
                mostrar_status("Movendo" if movendo else "Parado")

            elif tecla == " ":
                bot.drive_stop()
                movendo = False
                mostrar_status("Parado")

            elif tecla == "b":
                movendo = False
                seek_dock()
                mostrar_status("Dock")

            elif tecla == "q":
                break

        # Comportamento de carrinho RC:
        # para automaticamente quando a tecla é solta.
        if movendo and (agora - ultima_acao > TIMEOUT):
            bot.drive_stop()
            movendo = False
            mostrar_status("Parado")

        time.sleep(0.01)

finally:
    print("\n")

    print(color("Parando o robô...", YELLOW))

    try:
        bot.drive_stop()
        bot.start()
        bot.close()
    except Exception:
        pass

    # pycreate2 chama drive_stop() no __del__ (GC), escrevendo numa porta
    # já fechada -> PortNotOpenError. __del__ é resolvido na classe, então
    # neutralizamos o destrutor depois de fechar manualmente.
    Create2.__del__ = lambda self: None

    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    print(color("Conexão encerrada.", GREEN))
