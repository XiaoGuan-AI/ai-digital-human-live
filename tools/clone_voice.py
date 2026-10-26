"""把一段参考录音做成 OmniVoice 克隆音色预设（自动转写参考文本）。

产出（都在项目内）：
  voices/<name>/ref_audio.wav   参考音频（不足 24k 会自动转）
  voices/<name>/ref_text.txt    参考音频的转写文本（模型自带 Whisper 自动出）
  voices/<name>/omnivoice.txt   标记文件（scan_voices 靠它识别为「克隆」音色）
  shots/clone_sample.wav        克隆后合成的一段样音

用法（WSL）：
  /root/omnivoice-venv/bin/python tools/clone_voice.py \
      --ref /mnt/d/Projects/ai-digital-human-live/voices/xiaoya_clone/ref_audio.wav \
      --name xiaoya_clone
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

ROOT = "/mnt/d/Projects/ai-digital-human-live" if os.path.exists("/mnt/d") else os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="参考音频路径（3~10 秒最佳）")
    ap.add_argument("--name", default="xiaoya_clone", help="音色目录名")
    ap.add_argument("--model", default=os.path.join(ROOT, "models", "OmniVoice"))
    ap.add_argument("--text", default="大家好呀，我是小雅。今天咱们随便聊聊，你想听点什么？")
    ap.add_argument("--asr-model", default=os.path.join(ROOT, "models", "whisper-large-v3-turbo"),
                    help="自动转写用的 Whisper（本地路径或 HF 名）；本地路径可离线、不被掐断")
    ap.add_argument("--dtype", default="float16", choices=["float16", "bfloat16", "float32"])
    ap.add_argument("--out-sample", default=os.path.join(ROOT, "shots", "clone_sample.wav"),
                    help="克隆样音输出路径（自检时可指向临时文件）")
    a = ap.parse_args()

    import soundfile as sf
    import torch
    from omnivoice import OmniVoice

    vdir = os.path.join(ROOT, "voices", a.name)
    os.makedirs(vdir, exist_ok=True)

    # 统一成 24k 单声道 wav（克隆样本要求）
    wav_path = os.path.join(vdir, "ref_audio.wav")
    if os.path.abspath(a.ref) != os.path.abspath(wav_path):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", a.ref, "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", wav_path],
                       check=True)
    print(f"参考音频: {wav_path}  {os.path.getsize(wav_path) // 1024} KB", flush=True)

    dt = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}[a.dtype]
    print("加载模型…", flush=True)
    model = OmniVoice.from_pretrained(a.model, device_map="cuda:0", dtype=dt,
                                      asr_model_name=a.asr_model)

    t0 = time.time()
    prompt = model.create_voice_clone_prompt(ref_audio=wav_path)   # ref_text 省略 → 自动 ASR
    asr_sec = time.time() - t0
    text = (prompt.ref_text or "").strip()
    print(f"自动转写（{asr_sec:.1f}s）: 「{text}」", flush=True)

    with open(os.path.join(vdir, "ref_text.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    with open(os.path.join(vdir, "omnivoice.txt"), "w", encoding="utf-8") as f:
        f.write("voice-clone preset\n")
    with open(os.path.join(vdir, "label.txt"), "w", encoding="utf-8") as f:
        f.write("小雅（原版音色克隆）\n")
    prompt.save(os.path.join(vdir, "voice.pt"))
    print("预设已写入:", vdir, flush=True)

    t0 = time.time()
    audio = model.generate(text=a.text, voice_clone_prompt=prompt)
    took = time.time() - t0
    x = np.asarray(audio[0]).astype(np.float32)
    out = a.out_sample
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sf.write(out, x, 24000)
    dur = len(x) / 24000
    print(f"克隆合成 {dur:.2f}s，耗时 {took:.2f}s（RTF {took / dur:.2f}），峰值 {np.abs(x).max():.3f}")
    print("样音:", out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
