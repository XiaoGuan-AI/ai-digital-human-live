"""临时验收（ad-hoc，非测试套件）：本轮改动 = ai-digital-human-live 适配 + push_rtmp 参数化。

A) ai-digital-human-live/tools/verify_stack.py  → 期望 6/6（覆盖 engine 选择、edge TTS、LLM）
B) ai-live-anchor/tools/verify_clarity.py   → 期望 0 失败（推流项在停机时应 SKIP）
C) push_rtmp：--size 非法退出 2；--window-match 无效时退出 1 且提示含该模式
D) 4 个 .cmd 纯 ASCII（cmd 里中文会毁解析）
E) douyin_relay 代理修复：mock → relay 能「已连接」（websockets proxy=None）
F) 启停闭环：stop 后端口释放 → start 后端口恢复
"""
import os
import re
import socket
import subprocess
import sys
import tempfile
import time

X = r"D:\Projects\ai-digital-human-live"
A = r"D:\Projects\ai-live-anchor"
XPY = os.path.join(X, ".venv", "Scripts", "python.exe")
APY = os.path.join(A, ".venv", "Scripts", "python.exe")
results = []
PYENV = {k: v for k, v in os.environ.items()
         if k not in ("PYTHONPATH", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}


def check(name, fn):
    try:
        results.append((True, name, fn()))
    except Exception as e:
        results.append((False, name, f"{type(e).__name__}: {e}"))


def port_open(p, timeout=1.0):
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", p)) == 0


def wait_port(p, want, timeout=70):
    end = time.time() + timeout
    while time.time() < end:
        if port_open(p) == want:
            return True
        time.sleep(0.5)
    return False


def t_verify_stack():
    r = subprocess.run([XPY, "tools/verify_stack.py"], cwd=X, capture_output=True,
                       text=True, timeout=240, errors="ignore", env=PYENV)
    out = (r.stdout or "") + (r.stderr or "")
    assert "6/6" in out, f"没跑出 6/6: {out[-400:]}"
    assert r.returncode == 0, f"退出码 {r.returncode}"
    return "6/6，退出 0（端口/舞台页/TTS/LLM/计费状态/配置）"


def t_verify_clarity():
    r = subprocess.run([APY, "tools/verify_clarity.py"], cwd=A, capture_output=True,
                       text=True, timeout=200, errors="ignore", env=PYENV)
    out = (r.stdout or "") + (r.stderr or "")
    assert "0 失败" in out, f"有失败项: {out[-400:]}"
    assert r.returncode == 0, f"退出码 {r.returncode}"
    skip = "SKIP" in out
    return f"0 失败，退出 0；推流项{'已' if skip else '未'}SKIP（停机时不应误报）"


def t_push_args():
    r = subprocess.run([APY, "tools/push_rtmp.py", "--size", "abc"], cwd=A,
                       capture_output=True, text=True, timeout=60, errors="ignore", env=PYENV)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 2 and "--size 格式错误" in out, f"--size: rc={r.returncode} {out[-120:]}"

    r2 = subprocess.run([APY, "tools/push_rtmp.py", "--window-match", "绝不可能匹配的标题XYZ"],
                        cwd=A, capture_output=True, text=True, timeout=60, errors="ignore", env=PYENV)
    out2 = (r2.stdout or "") + (r2.stderr or "")
    assert r2.returncode == 1, f"--window-match 应退出 1，实际 {r2.returncode}"
    assert "绝不可能匹配的标题XYZ" in out2, f"提示没带出自定义模式: {out2[-160:]}"
    return "非法 --size → 2；无匹配窗口 → 1 且提示含自定义模式"


def t_cmd_ascii():
    bad = []
    for f in ("start-stage.cmd", "stop-stage.cmd", "tools/run_bridge.cmd", "tools/run_tts.cmd"):
        p = os.path.join(X, f)
        assert os.path.exists(p), f"缺 {f}"
        raw = open(p, "rb").read()
        n = sum(1 for b in raw if b > 127)
        if n:
            bad.append(f"{f}({n} 字节非 ASCII)")
    assert not bad, "; ".join(bad)
    return "4 个 .cmd 全 ASCII（中文会破坏 cmd 解析）"


def t_relay_proxy():
    """mock:1089 → relay：能连上说明 proxy=None 生效（否则 Clash 会回 400）。"""
    src = os.path.join(r"D:\Projects\_tmp\mock_douyinlive", "mock_server.py")
    assert os.path.exists(src), "缺 mock_server.py"
    if not port_open(1089):
        # 必须在原目录跑：mock 用相对路径读 mock_messages.jsonl
        m = subprocess.Popen([APY, "-u", src, "--port", "1089", "--interval", "1.5", "--loop"],
                             cwd=os.path.dirname(src), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=PYENV)
        assert wait_port(1089, True, 25), "mock 没起来"
    else:
        m = None
    try:
        rl = subprocess.Popen([XPY, "-u", "tools/douyin_relay.py", "--room", "148108118778",
                               "--ws-base", "ws://127.0.0.1:1089"],
                              cwd=X, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors="ignore", env=PYENV)
        seen = ""
        end = time.time() + 20
        while time.time() < end:
            line = rl.stdout.readline() if rl.stdout else ""
            if line:
                seen += line
                if "已连接" in seen or "HTTP 400" in seen:
                    break
            else:
                time.sleep(0.3)
        rl.kill()
        assert "已连接" in seen, f"relay 没连上 mock: {seen[-200:]}"
        assert "HTTP 400" not in seen, "仍是 400：proxy=None 没生效"
    finally:
        if m:
            m.kill()
    return "relay 连上 mock（proxy=None 生效，之前必 400）"


def t_start_stop_cycle():
    r = subprocess.run(["cmd.exe", "/c", "stop-stage.cmd"], cwd=X, capture_output=True,
                       text=True, timeout=120, errors="ignore", env=PYENV)
    ok_stop = wait_port(8795, False, 30) and wait_port(18780, False, 30)
    assert ok_stop, f"stop 后端口没释放: 8795={port_open(8795)} 18780={port_open(18780)}"

    env = dict(PYENV, PYTHONPATH="")
    try:
        subprocess.run(["cmd.exe", "/c", "start-stage.cmd"], cwd=X, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, env=env)
    except subprocess.TimeoutExpired:
        pass      # cmd 会因 start 出的子进程句柄挂住，端口起来就算成功
    up = wait_port(8795, True, 70) and wait_port(18780, True, 70)
    assert up, f"start 后端口没起来: 8795={port_open(8795)} 18780={port_open(18780)}"
    return "stop 释放 8795/18780 → start 重新拉起，一键闭环可用"


check("cyber: 本栈验收 6/6", t_verify_stack)
check("ai-live: 清晰度验收 0 失败", t_verify_clarity)
check("push_rtmp 参数解析", t_push_args)
check(".cmd 纯 ASCII", t_cmd_ascii)
check("转发器代理修复", t_relay_proxy)
check("一键启停闭环", t_start_stop_cycle)

print("\n" + "=" * 78)
ok = 0
for good, name, detail in results:
    print(f"{'PASS' if good else 'FAIL'}  {name:22} {detail}")
    ok += good
print("=" * 78)
print(f"{ok}/{len(results)} 通过")
sys.exit(0 if ok == len(results) else 1)
