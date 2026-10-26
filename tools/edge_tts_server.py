#!/usr/bin/env python3
"""WSL 侧 edge-tts HTTP 服务（给 ai-digital-human-live 的 edge 引擎用）。

为什么绕这一层：Windows 侧 edge-tts 会 403（speech.platform.bing.com 拒），
WSL 侧正常；而 ai-digital-human-live 的桥在 Windows 跑，所以用本地 HTTP 服务跨过去。

接口：
  GET /tts?text=...&voice=zh-CN-XiaoxiaoNeural&rate=+0%&pitch=+0Hz  → audio/mpeg
  GET /healthz → ok

启动（WSL）：
  nohup setsid /root/livetalking/LiveTalking/.venv-lt/bin/python \
    /mnt/d/Projects/ai-digital-human-live/tools/edge_tts_server.py --port 18780 \
    > /tmp/edge_tts.log 2>&1 &
"""
from __future__ import annotations

import argparse
import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import edge_tts

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


def synth(text: str, voice: str, rate: str, pitch: str) -> bytes:
    async def _run() -> bytes:
        c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        out = bytearray()
        async for ch in c.stream():
            if ch["type"] == "audio":
                out += ch["data"]
        return bytes(out)

    return asyncio.run(_run())


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):   # 静音访问日志，避免刷屏
        pass

    def _send(self, code: int, body: bytes, ctype: str = "audio/mpeg") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        u = urlparse(self.path)
        if u.path == "/healthz":
            self._send(200, b"ok", "text/plain")
            return
        if u.path != "/tts":
            self._send(404, b"not found", "text/plain")
            return
        q = parse_qs(u.query)
        text = (q.get("text") or [""])[0].strip()
        voice = (q.get("voice") or [DEFAULT_VOICE])[0] or DEFAULT_VOICE
        rate = (q.get("rate") or ["+0%"])[0]
        pitch = (q.get("pitch") or ["+0Hz"])[0]
        if not text:
            self._send(400, b"empty text", "text/plain")
            return
        try:
            data = synth(text[:600], voice, rate, pitch)
        except Exception as e:
            msg = json.dumps({"error": f"{type(e).__name__}: {e}"[:300]}).encode()
            self._send(500, msg, "application/json")
            return
        if not data:
            self._send(500, b"empty audio", "text/plain")
            return
        self._send(200, data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18780)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"edge-tts 服务已启动 http://{a.host}:{a.port}（默认音色 {DEFAULT_VOICE}）", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
