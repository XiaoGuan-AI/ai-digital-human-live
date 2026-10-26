"""对比「说唱腔」修复效果：同一段话，旧切法 vs 新切法。

旧切法（soft_min=10, 逗号即切）→ 10~30 字一块，每块独立起调 → 念白感/rap 感
新切法（soft_min=28, 整句到句号）→ 一句一次合成 → 韵律连贯

不花 Vidu 的钱（只本地 TTS）。产物：shots/style_old.mp3 / shots/style_new.mp3

用法: .venv\\Scripts\\python.exe tools/style_compare.py
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.llm import SentenceStream          # noqa: E402
from src.tts import audio, omnivoice as ov  # noqa: E402

TEXT = ("今天天气不错啊，我刚看到有人在评论区问我是不是真人，"
        "其实我是数字人啦，不过陪你聊天是真的。")


def synth(tts, preset, text):
    return asyncio.run(tts.synth_pcm(text, preset))


def write_wav(path, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio.SAMPLE_RATE)
        w.writeframes(pcm)


def main() -> int:
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
        print("找不到音色", name)
        return 2

    tts = ov.OmniVoiceTTS(base, float(t.get("omnivoice_timeout_sec") or 120))

    # ---- 旧切法 ----
    old_split = SentenceStream(soft_min=10, hard_max=30)
    old_pieces = old_split.feed(TEXT) + ([old_split.flush()] if old_split.flush() else [])
    old_pieces = [p for p in old_pieces if p]
    print(f"旧切法: {len(old_pieces)} 块 → {[len(p) for p in old_pieces]} 字")

    gap = audio.silence_pcm(120)
    t0 = time.time()
    old_pcm = gap.join(synth(tts, preset, p) for p in old_pieces)
    old_ms = int((time.time() - t0) * 1000)
    print(f"  合成耗时 {old_ms}ms，总长 {audio.pcm_seconds(old_pcm):.2f}s")

    # ---- 新切法 ----
    cfg_soft = int(t.get("sentence_soft_min", 28))
    cfg_hard = int(t.get("sentence_hard_max", 60))
    new_split = SentenceStream(soft_min=cfg_soft, hard_max=cfg_hard)
    new_pieces = new_split.feed(TEXT)
    tail = new_split.flush()
    if tail:
        new_pieces.append(tail)
    new_pieces = [p for p in new_pieces if p]
    print(f"新切法({cfg_soft}/{cfg_hard}): {len(new_pieces)} 块 → {[len(p) for p in new_pieces]} 字")

    t0 = time.time()
    new_pcm = gap.join(synth(tts, preset, p) for p in new_pieces)
    new_ms = int((time.time() - t0) * 1000)
    print(f"  合成耗时 {new_ms}ms，总长 {audio.pcm_seconds(new_pcm):.2f}s")

    os.makedirs(os.path.join(ROOT, "shots"), exist_ok=True)
    outs = []
    for tag, pcm in (("old", old_pcm), ("new", new_pcm)):
        wav = os.path.join(ROOT, "shots", f"style_{tag}.wav")
        mp3 = os.path.join(ROOT, "shots", f"style_{tag}.mp3")
        write_wav(wav, pcm)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", wav, "-ar", "44100", "-ac", "2", "-b:a", "192k", mp3], check=True)
        outs.append(mp3)
        print(f"  {mp3}  {os.path.getsize(mp3)//1024}KB")

    print("\n对比：旧 {} 块 / 新 {} 块。块数越少、单块越长 → 韵律越连贯（念白感越弱）。"
          .format(len(old_pieces), len(new_pieces)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
