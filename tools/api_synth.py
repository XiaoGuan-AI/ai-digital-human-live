"""用 OmniVoice 官方 Python API 直接合成（不经过 gradio demo），用于 A/B 对比。

README 标准用法：model.generate(text=...) → np.ndarray (T,) @24kHz → sf.write。
本脚本额外打印波形自检（峰值/包络/是否削顶），并写到 shots/。

用法（WSL 里跑）：
  /root/omnivoice-venv/bin/python tools/api_synth.py \
      --model /mnt/d/Projects/ai-digital-human-live/models/OmniVoice \
      --out /mnt/d/Projects/ai-digital-human-live/shots/api_auto.wav \
      --text "大家好，我是小雅，今天聊聊最近的事。"
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="/mnt/d/Projects/ai-digital-human-live/models/OmniVoice")
    ap.add_argument("--out", default="/mnt/d/Projects/ai-digital-human-live/shots/api_auto.wav")
    ap.add_argument("--text", default="大家好，我是小雅，今天聊聊最近的事。")
    ap.add_argument("--ref-audio", default="")
    ap.add_argument("--ref-text", default="")
    ap.add_argument("--dtype", default="float16", choices=["float16", "bfloat16", "float32"])
    a = ap.parse_args()

    import torch
    from omnivoice import OmniVoice

    print("加载模型…", flush=True)
    dt = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}[a.dtype]
    model = OmniVoice.from_pretrained(a.model, device_map="cuda:0", dtype=dt)
    print("已加载", flush=True)

    kw = {"text": a.text}
    if a.ref_audio:
        kw["ref_audio"] = a.ref_audio
        if a.ref_text:
            kw["ref_text"] = a.ref_text
    import time
    t0 = time.time()
    audio = model.generate(**kw)
    took = time.time() - t0

    x = np.asarray(audio[0]).astype(np.float32)
    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x ** 2)))
    print(f"生成 {len(x)/24000:.2f}s 音频，耗时 {took:.2f}s（RTF {took/(len(x)/24000):.2f}）")
    print(f"dtype={x.dtype} 峰值 {peak:.3f} RMS {rms:.4f}")
    print(f"前 12 个样本: {np.round(x[:12], 4)}")

    import soundfile as sf
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sf.write(a.out, x, 24000)
    print("已写入", a.out, os.path.getsize(a.out), "字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
