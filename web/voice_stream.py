"""Dedicated WebSocket endpoint for the browser-to-Pi intercom."""

import asyncio
from functools import partial

from aiohttp import WSMsgType, web

from media.bump_audio import BumpAudioPlayer
from media.live_voice import LiveVoicePlayer
from media.music import MusicPlayer


MAX_PCM_CHUNK_BYTES = 8192


async def handle_voice_ws(request: web.Request) -> web.WebSocketResponse:
    """Forward live PCM WebSocket frames to the Raspberry Pi speaker.

    Example: ``app.router.add_get('/voice-ws', handle_voice_ws)``.
    """
    ws = web.WebSocketResponse(heartbeat=10, max_msg_size=MAX_PCM_CHUNK_BYTES)
    await ws.prepare(request)
    voice: LiveVoicePlayer = request.app["live_voice"]
    voice_lock: asyncio.Lock = request.app["voice_lock"]
    if not voice.available or voice.playing or voice_lock.locked():
        message = "aplay indisponível" if not voice.available else "interfone ocupado"
        await ws.send_json({"type": "error", "message": message})
        await ws.close()
        return ws

    await voice_lock.acquire()
    request.app["voice_ws"] = ws
    music = request.app["registry"].player
    effects = request.app.get("effects")
    try:
        if effects is not None:
            await asyncio.to_thread(effects.suspend)
        if music is not None:
            await asyncio.to_thread(music.suspend)
        if not await voice.start():
            await ws.send_json({"type": "error", "message": "falha na saída de áudio"})
            await ws.close()
            return ws
        await ws.send_json({"type": "ready"})
        async for message in ws:
            if message.type == WSMsgType.BINARY and not await voice.write(message.data):
                break
            if message.type == WSMsgType.ERROR:
                break
    finally:
        cleanup = asyncio.create_task(
            _cleanup_voice_session(request, voice, music, effects)
        )
        cleanup.add_done_callback(
            partial(_release_voice_session, request.app, voice_lock)
        )
        await asyncio.shield(cleanup)
    return ws


async def _cleanup_voice_session(
    request: web.Request,
    voice: LiveVoicePlayer,
    music: MusicPlayer | None,
    effects: BumpAudioPlayer | None,
) -> None:
    try:
        await voice.stop()
    finally:
        if not request.app["shutting_down"]:
            try:
                if music is not None:
                    await asyncio.to_thread(music.resume)
            finally:
                if effects is not None:
                    effects.resume()


def _release_voice_session(
    app: web.Application,
    voice_lock: asyncio.Lock,
    cleanup: asyncio.Task[None],
) -> None:
    try:
        error = cleanup.exception()
        if error is not None:
            print(f"[voice] erro no cleanup do interfone: {error}", flush=True)
    finally:
        app["voice_ws"] = None
        if voice_lock.locked():
            voice_lock.release()
