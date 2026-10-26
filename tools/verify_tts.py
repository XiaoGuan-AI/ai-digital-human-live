"""TTS 回归验收（仓库常驻）。

验的是本项目 TTS 链路：config → src/tts/omnivoice.py → omnivoice-demo(:9877) → PCM。
不碰直播，不花 Vidu 的钱。

A) design.json 合法且枚举值在服务端接受范围内（写错会被 gradio 拒）
B) 真合成一句 → 退出 0、时长/峰值合理（不是静音）
C) 未知音色 → 退出 2 且提示清楚
D) 配置接线：tts.engine=omnivoice 且 omnivoice_base 可达

用法: .venv\\Scripts\\python.exe tools\\verify_tts.py
"""
from __future__ import annotations

import array
import json
import os
import socket
import subprocess
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
ENV = {k: v for k, v in os.environ.items()
       if k not in ("PYTHONPATH", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
R = []

# gradio /_design_fn 实际接受的枚举（2026-10-25 由 view_api 读出）
ALLOWED = {
    "gender": {"Auto", "Male / 男", "Female / 女"},
    "age": {"Auto", "Child / 儿童", "Teenager / 少年", "Young Adult / 青年",
            "Middle-aged / 中年", "Elderly / 老年"},
    "pitch": {"Auto", "Very Low Pitch / 极低音调", "Low Pitch / 低音调",
              "Moderate Pitch / 中音调", "High Pitch / 高音调", "Very High Pitch / 极高音调"},
}


def check(name, fn):
    try:
        R.append((True, name, fn()))
    except Exception as e:                                    # noqa: BLE001
        R.append((False, name, f"{type(e).__name__}: {e}"))
    print(f"{'PASS' if R[-1][0] else 'FAIL'}  {name}: {R[-1][2]}", flush=True)


def preset() -> dict:
    with open(os.path.join(ROOT, "voices", "xiaoya", "design.json"), encoding="utf-8") as f:
        return json.load(f)


def t_preset():
    p = preset()
    for k in ("label", "gender", "age", "pitch", "lang"):
        assert k in p, f"design.json 缺 {k}"
    return f"合法；label={p['label']}"


def t_enums():
    p = preset()
    for k, ok in ALLOWED.items():
        if k in p:
            assert p[k] in ok, f"{k}={p[k]!r} 不在允许集合"
    assert p.get("lang") in ("Chinese", "Auto"), f"lang={p.get('lang')!r}"
    assert 0.5 <= float(p.get("sp", 1.0)) <= 2.0, "sp 越界"
    return "gender/age/pitch/lang/sp 均在服务端接受范围内"


def _peak_and_dur(path: str) -> tuple[float, int]:
    with wave.open(path) as w:
        dur = w.getnframes() / w.getframerate()
        raw = w.readframes(w.getnframes())          # 读一次即可：循环里重复读会让指针前移
    a = array.array("h")
    a.frombytes(raw[: (len(raw) // 2) * 2])
    return dur, max((abs(x) for x in a), default=0)


def t_synth():
    r = subprocess.run([PY, "tools/test_tts.py", "--text", "你好，这是一句很短的测试。"],
                       cwd=ROOT, capture_output=True, text=True, timeout=180,
                       errors="ignore", env=ENV)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-400:]
    dur, peak = _peak_and_dur(os.path.join(ROOT, "shots", "tts_test.wav"))
    assert dur > 0.5, f"音频太短 {dur:.2f}s"
    assert peak > 1000, f"峰值 {peak} 像静音"
    return f"合成 {dur:.2f}s，峰值 {peak}/32767"


def t_bad_voice():
    r = subprocess.run([PY, "tools/test_tts.py", "--voice", "no_such_voice"], cwd=ROOT,
                       capture_output=True, text=True, timeout=60, errors="ignore", env=ENV)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 2, f"退出码 {r.returncode}（应 2）"
    assert "找不到音色" in out, out[-200:]
    return "未知音色 → 退出 2 且提示清楚"


def t_config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        t = (json.load(f).get("tts") or {})
    assert t.get("engine") == "omnivoice", f"engine={t.get('engine')}"
    base = str(t.get("omnivoice_base") or "")
    assert "9877" in base, base
    host, port = base.replace("http://", "").split(":")
    with socket.socket() as s:
        s.settimeout(3)
        assert s.connect_ex((host, int(port.split("/")[0]))) == 0, f"{base} 不通"
    return f"engine=omnivoice；{base} 可达"


if __name__ == "__main__":
    check("A 音色预设结构", t_preset)
    check("B 枚举值合法", t_enums)
    check("C 真合成", t_synth)
    check("D 未知音色路径", t_bad_voice)
    check("E 配置接线", t_config)
    ok = sum(1 for g, _, _ in R if g)
    print("\n" + "=" * 56)
    print(f"{ok}/{len(R)} 通过")
    sys.exit(0 if ok == len(R) else 1)
