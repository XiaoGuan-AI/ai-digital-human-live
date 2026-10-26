"""克隆音色通路的仓库常驻验收（跑一次约 40 秒，不需要直播、不花 Vidu 钱）。

A) 静态：--asr-model → from_pretrained(asr_model_name=…)、--out-sample → out
B) 真跑：用临时音色名走一遍「本地 Whisper 转写 → 克隆合成」
   → 预设 5 件（ref_audio/ref_text/omnivoice/label/voice.pt）+ 样音落在 --out-sample
C) 清理：临时目录与样音用完即删，不污染 voices/ 与 shots/

用法: .venv\\Scripts\\python.exe tools\\verify_clone.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
WSLPY = "/root/omnivoice-venv/bin/python"
NAME = "_verify_clone"
VDIR = os.path.join(ROOT, "voices", NAME)
SAMPLE = os.path.join(ROOT, "shots", "verify_clone_sample.wav")
REF = os.path.join(ROOT, "voices", "xiaoya_clone", "ref_audio.wav")
ASR = os.path.join(ROOT, "models", "whisper-large-v3-turbo")
ENV = {k: v for k, v in os.environ.items()
       if k not in ("PYTHONPATH", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
R = []


def check(name, fn):
    try:
        R.append((True, name, fn()))
    except Exception as e:                                     # noqa: BLE001
        R.append((False, name, f"{type(e).__name__}: {e}"))
    print(f"{'PASS' if R[-1][0] else 'FAIL'}  {name}: {R[-1][2]}", flush=True)


def t_static():
    r = subprocess.run([PY, "-m", "py_compile", "tools/clone_voice.py"], cwd=ROOT,
                       capture_output=True, text=True, errors="ignore", env=ENV)
    assert r.returncode == 0, (r.stderr or "")[-300:]
    s = open(os.path.join(ROOT, "tools", "clone_voice.py"), encoding="utf-8").read()
    assert '"--asr-model"' in s and "asr_model_name=a.asr_model" in s, "asr 参数没接上"
    assert '"--out-sample"' in s and "out = a.out_sample" in s, "样音输出不可指定"
    return "编译通过；--asr-model→asr_model_name；--out-sample→out"


def t_run():
    for p in (REF, os.path.join(ASR, "model.safetensors")):
        assert os.path.exists(p), f"缺前置文件 {p}"
    shutil.rmtree(VDIR, ignore_errors=True)
    if os.path.exists(SAMPLE):
        os.remove(SAMPLE)

    cmd = ("export HF_HUB_OFFLINE=1; "
           f"cd /mnt/d/Projects/ai-digital-human-live && {WSLPY} tools/clone_voice.py "
           f"--ref {REF.replace(chr(92), '/').replace('D:/', '/mnt/d/')} "
           f"--name {NAME} --asr-model {ASR.replace(chr(92), '/').replace('D:/', '/mnt/d/')} "
           f"--out-sample {SAMPLE.replace(chr(92), '/').replace('D:/', '/mnt/d/')} "
           "--text 这是克隆通路自检。")
    r = subprocess.run(["wsl", "-d", "Ubuntu-24.04", "bash", "-lc", cmd],
                       capture_output=True, text=True, timeout=600, errors="ignore")
    log = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, log[-500:]
    assert "自动转写" in log, log[-500:]

    for f in ("ref_audio.wav", "ref_text.txt", "omnivoice.txt", "label.txt", "voice.pt"):
        p = os.path.join(VDIR, f)
        assert os.path.exists(p) and os.path.getsize(p) > 0, f"缺/空 {f}"
    text = open(os.path.join(VDIR, "ref_text.txt"), encoding="utf-8").read().strip()
    assert re.search(r"[\u4e00-\u9fff]", text), f"转写不是中文: {text!r}"
    with wave.open(os.path.join(VDIR, "ref_audio.wav")) as w:
        assert (w.getframerate(), w.getnchannels()) == (24000, 1), "参考音频不是 24k 单声道"
    assert os.path.exists(SAMPLE) and os.path.getsize(SAMPLE) > 10_000, "样音没落在 --out-sample"
    return f"转写「{text[:18]}」；预设 5 件齐；样音 {os.path.getsize(SAMPLE)//1024}KB"


def t_cleanup():
    shutil.rmtree(VDIR, ignore_errors=True)
    if os.path.exists(SAMPLE):
        os.remove(SAMPLE)
    assert not os.path.exists(VDIR) and not os.path.exists(SAMPLE), "临时产物没清干净"
    return "临时目录/样音已删，voices/ 只剩正式预设"


if __name__ == "__main__":
    check("A 静态", t_static)
    check("B 真跑（本地 Whisper + 克隆）", t_run)
    check("C 清理", t_cleanup)
    ok = sum(1 for g, _, _ in R if g)
    print("\n" + "=" * 52)
    print(f"{ok}/{len(R)} 通过")
    sys.exit(0 if ok == len(R) else 1)
