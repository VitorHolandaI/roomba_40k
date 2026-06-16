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

# Se nenhuma tecla for recebida nesse intervalo,
# o robô é parado automaticamente.
TIMEOUT = 0.15


def get_key():
    """Lê uma tecla sem bloquear."""
    r, _, _ = select.select([sys.stdin], [], [], 0)

    if r:
        return sys.stdin.read(1)

    return None


def mostrar_status(acao, vel):
    """Atualiza a linha de status."""
    print(
        f"\r[{acao:<10}] Velocidade: {vel:>3} mm/s",
        end="",
        flush=True,
    )


print("Conectando ao Roomba...")

bot = Create2(PORT)
bot.start()
bot.safe()

time.sleep(0.2)

fd = sys.stdin.fileno()
old_settings = termios.tcgetattr(fd)

tty.setcbreak(fd)

ultima_acao = time.time()
movendo = False

print("""
Controles:
  W = frente
  S = ré
  A = esquerda
  D = direita

  + = aumentar velocidade
  - = diminuir velocidade

  Espaço = parar
  Q = sair
""")

mostrar_status("Parado", vel)

try:
    while True:
        tecla = get_key()

        if tecla:
            tecla = tecla.lower()
            ultima_acao = time.time()

            if tecla == "w":
                bot.drive_direct(vel, vel)
                movendo = True
                mostrar_status("Frente", vel)

            elif tecla == "s":
                bot.drive_direct(-vel, -vel)
                movendo = True
                mostrar_status("Ré", vel)

            elif tecla == "a":
                bot.drive_direct(-vel, vel)
                movendo = True
                mostrar_status("Esquerda", vel)

            elif tecla == "d":
                bot.drive_direct(vel, -vel)
                movendo = True
                mostrar_status("Direita", vel)

            elif tecla == "+":
                vel = min(500, vel + 25)
                mostrar_status("Parado", vel)

            elif tecla == "-":
                vel = max(50, vel - 25)
                mostrar_status("Parado", vel)

            elif tecla == " ":
                bot.drive_stop()
                movendo = False
                mostrar_status("Parado", vel)

            elif tecla == "q":
                break

        # Simula o comportamento de um carrinho RC:
        # se nenhuma tecla chegar por um tempo,
        # envia STOP automaticamente.
        if movendo and (time.time() - ultima_acao > TIMEOUT):
            bot.drive_stop()
            movendo = False
            mostrar_status("Parado", vel)

        time.sleep(0.01)

finally:
    print("\n\nParando o robô...")

    bot.drive_stop()

    # Volta para modo passive
    bot.start()

    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    print("Encerrado.")
