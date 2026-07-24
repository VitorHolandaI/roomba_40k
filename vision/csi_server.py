#!/usr/bin/env python3
"""Servidor MJPEG da câmera CSI (ov5647) via picamera2 — multi-cliente e robusto.

Substitui o pipeline rpicam-vid|ffmpeg (que caía com 'Broken pipe' quando o
único cliente do `-listen 1` desconectava). Aqui o picamera2 usa o encoder
JPEG de HW e entrega o quadro pronto; o Python só repassa os bytes ao socket
(sem re-encode, sem varrer marcadores FFD8/FFD9 — ver STREAMING_NOTES.md §2).
Cada cliente roda em sua thread; uma queda derruba só aquele cliente.

Roda com o python do SISTEMA (picamera2 vem do apt, não do venv uv):
    python3 vision/csi_server.py
Abra:  http://<ip-do-pi>:8081/   (ou embutido no app em /static via <img>)
"""

import io
import os
import socketserver
from http import server
from threading import Condition

from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput

WIDTH = int(os.environ.get("CAM_WIDTH", "640"))
HEIGHT = int(os.environ.get("CAM_HEIGHT", "480"))
PORT = int(os.environ.get("CAM_PORT", "8081"))
BOUNDARY = "FRAME"


class LatestFrame(io.BufferedIOBase):
    """Guarda só o último quadro JPEG e acorda os clientes que esperam."""

    def __init__(self) -> None:
        self.frame = b""
        self.condition = Condition()

    def write(self, buf: bytes) -> int:
        with self.condition:
            self.frame = buf
            self.condition.notify_all()
        return len(buf)


class MjpegHandler(server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (nome exigido pelo BaseHTTPRequestHandler)
        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header(
            "Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}"
        )
        self.end_headers()
        try:
            self._stream_frames()
        except (BrokenPipeError, ConnectionResetError):
            # Cliente fechou a aba — normal; só encerra esta thread.
            return

    def _stream_frames(self) -> None:
        while True:
            with frames.condition:
                frames.condition.wait()
                frame = frames.frame
            self.wfile.write(f"--{BOUNDARY}\r\n".encode())
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
            self.wfile.write(b"\r\n")

    def log_message(self, *_args: object) -> None:
        pass  # silencia o log por request (poluía o terminal)


class ThreadingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    picam2 = Picamera2()
    picam2.configure(
        picam2.create_video_configuration(main={"size": (WIDTH, HEIGHT)})
    )
    picam2.start_recording(JpegEncoder(), FileOutput(frames))
    print(f"[csi] MJPEG {WIDTH}x{HEIGHT} -> http://0.0.0.0:{PORT}/")
    try:
        ThreadingServer(("0.0.0.0", PORT), MjpegHandler).serve_forever()
    finally:
        picam2.stop_recording()


frames = LatestFrame()

if __name__ == "__main__":
    main()
