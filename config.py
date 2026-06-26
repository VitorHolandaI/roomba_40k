"""Configuração estática do boombox-roomba.

Edite as constantes aqui para apontar os efeitos sonoros de batida. Cada vez
que o robô (iRobot 561) bate em algo e fecha o sensor de toque (bump), os
áudios desta pasta tocam em sequência — solte qualquer .mp3 lá e vira piada.
"""

import os

# Pasta varrida por efeitos sonoros tocados quando o robô bate em algo.
# Troque o caminho abaixo (ou exporte BUMP_AUDIO_DIR) para sua pasta de áudios.
BUMP_AUDIO_DIR = os.path.expanduser(os.environ.get("BUMP_AUDIO_DIR", "~/roomba_sounds"))

# Saída ALSA dos efeitos — mesmo alto-falante da música por padrão.
BUMP_AUDIO_ALSA_DEV = os.environ.get("BUMP_AUDIO_ALSA_DEV", "hw:1,0")
