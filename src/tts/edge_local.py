"""edge 引擎适配（替代 OmniVoice）：把 WSL 里的 edge-tts HTTP 服务接进组件版。

作者 README §6 明确说「要接 Edge-TTS 需要自己写一个适配层（src/tts/ 下加一个类即可）」，
本文件就是那个类。接口与 OmniVoiceTTS 保持一致：
    await tts.synth_pcm(text, preset) -> PCM s16le / 24kHz / mono
    tts.active_base() -> str

配置（config.json）：
    "tts": {
      "engine": "edge",
      "edge_base": "http://127.0.0.1:18780",
      "voice": "zh-CN-XiaoxiaoNeural"
    }
preset 里可带 rate / pitch（沿用音色预设目录机制）。
"""
from __future__ import annotations

import asyncio

import httpx

from . import audio


class EdgeTTS:
    def __init__(self, base: str = "http://127.0.0.1:18780",
                 timeout_sec: float = 60, default_voice: str = "zh-CN-XiaoxiaoNeural"):
        self.base = (base or "http://127.0.0.1:18780").rstrip("/")
        self.timeout = float(timeout_sec or 60)
        self.default_voice = default_voice or "zh-CN-XiaoxiaoNeural"
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    # ---- 与 OmniVoiceTTS 对齐的两个方法 ----
    def active_base(self) -> str:
        return self.base

    async def synth_pcm(self, text: str, preset: dict | None = None) -> bytes:
        """文本 → PCM s16le/24kHz/mono。失败向上抛，由引擎收尾。"""
        if not text or not text.strip():
            return b""
        preset = preset or {}
        voice = preset.get("voice") or preset.get("name") or self.default_voice
        rate = preset.get("rate") or "+0%"
        pitch = preset.get("pitch") or "+0Hz"

        async with self._lock:
            if self._client is None:
                # trust_env=False：Clash 会把 127.0.0.1 的请求也塞进代理，
                # 表现为 "400 The plain HTTP request was sent to HTTPS port"
                self._client = httpx.AsyncClient(timeout=self.timeout, trust_env=False)
            try:
                r = await self._client.get(
                    f"{self.base}/tts",
                    params={"text": text.strip(), "voice": voice, "rate": rate, "pitch": pitch},
                )
            except Exception as e:
                self._client = None
                raise RuntimeError(f"edge-tts 服务不可达({self.base}): {type(e).__name__}: {e}") from e
            if r.status_code != 200 or not r.content:
                raise RuntimeError(f"edge-tts 合成失败: HTTP {r.status_code} {r.text[:200]}")
            mp3 = r.content

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, audio.decode_to_pcm, None, mp3, "audio/mpeg")


def health(base: str = "http://127.0.0.1:18780", timeout: float = 5.0) -> bool:
    """启动前自检：WSL 侧服务在不在。"""
    try:
        return httpx.get(f"{base.rstrip('/')}/healthz", timeout=timeout,
                         trust_env=False).status_code == 200
    except Exception:
        return False
