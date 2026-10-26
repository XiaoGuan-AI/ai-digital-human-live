"""本栈验收：端口 / 舞台页 / TTS 合成 / LLM 回复 / 计费状态。

用法: .venv\\Scripts\\python.exe tools\\verify_stack.py
退出码 0 = 全绿；非 0 = 有项失败。
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

OP = httpx.Client(timeout=10, trust_env=False)
BRIDGE = "http://127.0.0.1:8795"


def _tts_conf() -> tuple[str, int, str]:
    """TTS 端点/端口/音色全部取 config。

    2026-10-25：原来这里硬编码了老 edge-tts 服务的端口，早已换成 OmniVoice，
    导致本验收长期假红（端口/TTS 合成两项必失败）。现在统一读 tts.omnivoice_base。
    """
    import json
    from urllib.parse import urlparse
    c = (json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8")).get("tts") or {})
    base = (c.get("omnivoice_base") or "http://127.0.0.1:9877").rstrip("/")
    port = urlparse(base).port or 9877
    return base, port, c.get("voice") or "tw_a"


TTS, TTS_PORT, TTS_VOICE = _tts_conf()
results: list[tuple[bool, str, str]] = []


def check(name, fn):
    try:
        results.append((True, name, fn()))
    except Exception as e:
        results.append((False, name, f"{type(e).__name__}: {e}"))


def port_open(p: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1.5)
        return s.connect_ex(("127.0.0.1", p)) == 0


def t_ports():
    assert port_open(8795), "桥 8795 未监听"
    assert port_open(TTS_PORT), f"TTS {TTS_PORT} 未监听（config tts.omnivoice_base={TTS}）"
    return f"8795(桥) + {TTS_PORT}(TTS, {TTS_VOICE}) 均在监听"


def t_stage():
    r = OP.get(f"{BRIDGE}/stage")
    assert r.status_code == 200, f"/stage {r.status_code}"
    assert "html" in r.headers.get("content-type", "").lower(), "返回不是 html"
    return f"/stage 200（{len(r.text)} 字节）"


def t_tts():
    """走项目真正在用的 TTS（OmniVoice），不再打老的 edge 服务。"""
    from src.tts import omnivoice as ov
    import json
    c = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8")).get("tts") or {}
    vdir = c.get("voices_dir") or "voices"
    vdir = vdir if os.path.isabs(vdir) else os.path.join(ROOT, vdir)
    preset = ov.scan_voices(vdir).get(TTS_VOICE)
    assert preset, f"音色 {TTS_VOICE} 不存在（{vdir}）"
    t = ov.OmniVoiceTTS(TTS, float(c.get("omnivoice_timeout_sec") or 120))
    t0 = time.time()
    pcm = asyncio.run(t.synth_pcm("验收测试，声音通不通", preset))
    dt = time.time() - t0
    assert len(pcm) > 24000, f"PCM 只有 {len(pcm)} 字节"
    return (f"音色 {TTS_VOICE}；PCM {len(pcm)/1024:.0f}KB = {len(pcm)/48000:.2f}s，"
            f"耗时 {dt:.2f}s（RTF {dt/max(0.01, len(pcm)/48000):.2f}）")


def t_llm():
    from src import config as appconf, llm as llmmod
    cli = llmmod.LLMClient(lambda: appconf.load().get("llm") or {})

    async def run():
        out = []
        async for piece in cli.stream("用一句话介绍你自己，20字以内"):
            out.append(piece)
        return "".join(out).strip()

    txt = asyncio.run(run())
    assert txt, "LLM 返回空"
    return f"LLM 回复 {len(txt)} 字：{txt[:28]}…"


def t_idle_not_billing():
    d = OP.get(f"{BRIDGE}/api/live/status", params={"since": 0}).json()
    assert d.get("phase") == "idle", f"当前 phase={d.get('phase')}（非 idle 可能已在计费）"
    assert d.get("active") is False, "active=true，可能已连线计费"
    return f"phase=idle / active=false（未连线，不计费）；tts_base={d.get('tts_base')}"


def t_config_ready():
    c = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    missing = []
    if not c["vidu"].get("api_key"):
        missing.append("vidu.api_key")
    if not c["avatar"].get("avatar_id"):
        missing.append("avatar.avatar_id")
    if not c["llm"].get("key_file") or not Path(c["llm"]["key_file"]).exists():
        missing.append("llm.key_file")
    if missing == ["vidu.api_key", "avatar.avatar_id"]:
        return "本地已就绪；仅缺 Vidu 凭据（api_key + avatar_id）→ 开播前必填"
    assert not missing, "缺: " + ", ".join(missing)
    return "全部配置就绪"


check("端口", t_ports)
check("舞台页", t_stage)
check("TTS 合成", t_tts)
check("LLM 回复", t_llm)
check("计费状态", t_idle_not_billing)
check("配置完整度", t_config_ready)

print("\n" + "=" * 78)
ok = 0
for good, name, detail in results:
    print(f"{'PASS' if good else 'FAIL'}  {name:10} {detail}")
    ok += good
print("=" * 78)
print(f"{ok}/{len(results)} 通过")
sys.exit(0 if ok == len(results) else 1)
