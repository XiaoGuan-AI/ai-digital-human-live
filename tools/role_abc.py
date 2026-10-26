"""对比「念弹幕」与「回答」两种腔调（同一音色、同一句话）。

用途：调 `tts.read_params`（念观众原话：平一点、快一点）对比 `tts.voice` 的默认参数
（回答：软一点、有起伏）。只跑本地 TTS，不碰 Vidu 计费。

用法:
  .venv\\Scripts\\python.exe tools\\role_abc.py
  .venv\\Scripts\\python.exe tools\\role_abc.py --text "主播你今年几岁呀" --out-prefix role
产物：shots/<prefix>_talk.mp3、shots/<prefix>_read.mp3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.tts import audio, omnivoice as ov  # noqa: E402

DEFAULT_TEXT = "主播你今年几岁呀"


def synth(tts: ov.OmniVoiceTTS, text: str, preset: dict, out_wav: str) -> float:
    pcm = asyncio.run(tts.synth_pcm(text, preset))
    if not pcm:
        raise RuntimeError("空音频")
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio.SAMPLE_RATE)
        w.writeframes(pcm)
    return audio.pcm_seconds(pcm)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default=DEFAULT_TEXT)
    ap.add_argument("--out-prefix", default="role")
    a = ap.parse_args()

    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    t = cfg.get("tts") or {}
    base = (t.get("omnivoice_base") or "http://127.0.0.1:9877").rstrip("/")
    vdir = t.get("voices_dir") or "voices"
    if not os.path.isabs(vdir):
        vdir = os.path.join(ROOT, vdir)
    voices = ov.scan_voices(vdir)
    name = t.get("voice") or "xiaoya_clone"
    preset = voices.get(name)
    if not preset:
        print(f"找不到音色 {name}，可选: {list(voices)}")
        return 2

    read_params = t.get("read_params") or {}
    read_preset = {**preset, "params": {**(preset.get("params") or {}), **read_params}}

    tts = ov.OmniVoiceTTS(base, float(t.get("omnivoice_timeout_sec") or 120))
    os.makedirs(os.path.join(ROOT, "shots"), exist_ok=True)
    for tag, p in (("talk", preset), ("read", read_preset)):
        wav = os.path.join(ROOT, "shots", f"{a.out_prefix}_{tag}.wav")
        mp3 = os.path.join(ROOT, "shots", f"{a.out_prefix}_{tag}.mp3")
        secs = synth(tts, a.text, p, wav)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", wav,
                        "-ar", "44100", "-ac", "2", "-b:a", "192k", mp3], check=True)
        print(f"✅ {tag}: {secs:.2f}s  参数={p.get('params') or '默认'}  → {mp3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
