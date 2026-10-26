"""TTS 自检：用项目里的 TTS 适配层直接合成一句，验证 OmniVoice 真能出声。

不走直播（不花 Vidu 的钱），只测本机 TTS 链路：
  config.json → src.tts.omnivoice.OmniVoiceTTS → omnivoice-demo(:9877) → PCM

用法：
  .venv\\Scripts\\python.exe tools\\test_tts.py
  .venv\\Scripts\\python.exe tools\\test_tts.py --voice xiaoya --text "自定义文本"
产物：shots/tts_test.wav（24kHz 单声道 16bit，可直接播）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.tts import omnivoice as ov  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="xiaoya")
    ap.add_argument("--text", default="大家好呀，我是小雅。现在用的是项目原版的声音，你听听自然不自然？")
    a = ap.parse_args()

    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    ttsc = cfg.get("tts") or {}
    base = (ttsc.get("omnivoice_base") or "http://127.0.0.1:9877").rstrip("/")
    voices_dir = ttsc.get("voices_dir") or "voices"
    if not os.path.isabs(voices_dir):
        voices_dir = os.path.join(ROOT, voices_dir)

    print(f"engine      : {ttsc.get('engine')}")
    print(f"base        : {base}")
    print(f"voices_dir  : {voices_dir}")

    voices = ov.scan_voices(voices_dir)
    print(f"音色预设    : {list(voices) or '(空)'}")
    if a.voice not in voices:
        print(f"❌ 找不到音色 {a.voice}；先建 {os.path.join(voices_dir, a.voice, 'design.json')}")
        return 2
    preset = voices[a.voice]
    print(f"选中        : {preset.get('label')} kind={preset.get('kind')}")

    import asyncio

    tts = ov.OmniVoiceTTS(base, float(ttsc.get("omnivoice_timeout_sec") or 120))
    t0 = time.time()
    try:
        pcm = asyncio.run(tts.synth_pcm(a.text, preset))
    except Exception as e:
        print(f"❌ 合成失败: {type(e).__name__}: {e}")
        return 1
    took = time.time() - t0

    if not pcm:
        print("❌ 合成返回空 PCM")
        return 1

    sr = 24000
    dur = len(pcm) / (sr * 2)
    peak = max(abs(int.from_bytes(pcm[i:i + 2], "little", signed=True))
               for i in range(0, min(len(pcm), sr * 2 * 3), 2))
    os.makedirs(os.path.join(ROOT, "shots"), exist_ok=True)
    out = os.path.join(ROOT, "shots", "tts_test.wav")
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)

    print(f"✅ 合成 {len(pcm)} 字节 = {dur:.2f} 秒音频，耗时 {took:.2f}s（RTF {took / dur:.2f}）")
    print(f"   峰值幅度 {peak}/32767")
    print(f"   产物 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
