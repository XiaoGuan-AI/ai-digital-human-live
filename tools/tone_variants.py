"""听感 A/B：同一句话、同一个克隆音色，换 instruct / 语速，产出多个 MP3 供人选。

背景：参考音频取自 demo（6 秒，转写「她说路远也别怕天亮了就有光。」，像歌词），
克隆把它的**韵律**一起学走 → 听起来"说唱腔/念白感"。这里用 instruct 把语气拉回自然口语。

只跑本地 TTS，不碰 Vidu 计费。产物：shots/tone_*.mp3

用法: .venv\\Scripts\\python.exe tools/tone_variants.py
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.tts import audio, omnivoice as ov  # noqa: E402

TEXT = "今天天气不错啊，我刚看到有人在评论区问我是不是真人，其实我是数字人啦，陪你聊天是真的。"

VARIANTS = [
    ("v0_clone", {}, "克隆·现状（拖腔，18.2s）"),
    ("v1_clone_fast", {"sp": 1.3}, "克隆·语速 1.3"),
    ("v2_design", "__DESIGN__", "设计音色·自然口语女声（7.7s）"),
    ("v3_clone_faster", {"sp": 1.45}, "克隆·语速 1.45"),
]

DESIGN_PRESET = {
    "kind": "design",
    "label": "自然女声（design）",
    "params": {"gender": "Female / 女", "age": "Young Adult / 青年",
               "pitch": "Moderate Pitch / 中音调", "style": "Auto",
               "accent": "Auto", "dialect": "Auto", "lang": "Chinese", "sp": 1.0},
}


def main() -> int:
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    t = cfg.get("tts") or {}
    base = (t.get("omnivoice_base") or "http://127.0.0.1:9877").rstrip("/")
    vdir = t.get("voices_dir") or "voices"
    if not os.path.isabs(vdir):
        vdir = os.path.join(ROOT, vdir)
    preset = ov.scan_voices(vdir).get(t.get("voice") or "xiaoya_clone")
    if not preset:
        print("找不到音色:", t.get("voice"))
        return 2

    tts = ov.OmniVoiceTTS(base, float(t.get("omnivoice_timeout_sec") or 120))
    os.makedirs(os.path.join(ROOT, "shots"), exist_ok=True)

    for tag, overrides, desc in VARIANTS:
        if overrides == "__DESIGN__":
            p = json.loads(json.dumps(DESIGN_PRESET))
        else:
            p = dict(preset)
            params = dict(p.get("params") or {})
            params.update(overrides)
            p["params"] = params
        try:
            pcm = asyncio.run(tts.synth_pcm(TEXT, p))
        except Exception as e:  # noqa: BLE001
            print(f"❌ {tag}: {type(e).__name__}: {e}")
            continue
        if not pcm:
            print(f"❌ {tag}: 空音频")
            continue
        wav = os.path.join(ROOT, "shots", f"tone_{tag}.wav")
        mp3 = os.path.join(ROOT, "shots", f"tone_{tag}.mp3")
        with wave.open(wav, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(audio.SAMPLE_RATE)
            w.writeframes(pcm)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", wav,
                        "-ar", "44100", "-ac", "2", "-b:a", "192k", mp3], check=True)
        print(f"✅ {tag}: {audio.pcm_seconds(pcm):.2f}s  {desc}  → {mp3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
