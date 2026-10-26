"""计费看门狗验收：用假桥模拟「连线中」，验证到预算会自动停止。

为什么必须验：这是唯一防止"忘了关 = 一直烧钱"的闸门，写错等于没有。

A) 静态：py_compile；有单价常量；trust_env=False（否则 Clash 劫持 127.0.0.1）；有 stop 调用
B) phase=live → 到预算自动 POST /api/live/stop（假桥记录请求）
C) phase=idle → 不计时、不发停止请求
D) --once 只读状态

用法: .venv\\Scripts\\python.exe tools\\verify_cost_guard.py
"""
from __future__ import annotations

import http.server
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
GUARD = os.path.join(ROOT, "tools", "cost_guard.py")
R = []


def check(name, fn):
    try:
        R.append((True, name, fn()))
    except Exception as e:
        R.append((False, name, f"{type(e).__name__}: {e}"))
    print(f"{'PASS' if R[-1][0] else 'FAIL'}  {name}: {R[-1][2]}", flush=True)


class FakeBridge:
    """最小假桥：/api/health 返回设定 phase，/api/live/stop 记录调用。"""

    def __init__(self, phase: str):
        self.phase = phase
        self.stops = 0
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):        # 静音
                pass

            def do_GET(self):
                body = {"ok": True, "phase": outer.phase}
                self._send(body)

            def do_POST(self):
                if self.path.startswith("/api/live/stop"):
                    outer.stops += 1
                    outer.phase = "idle"        # 真桥停完就是 idle
                self._send({"ok": True})

            def _send(self, obj):
                data = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def close(self):
        self.httpd.shutdown()


def load_guard():
    spec = importlib.util.spec_from_file_location("cost_guard", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def t_static():
    r = subprocess.run([PY, "-m", "py_compile", GUARD], capture_output=True,
                       text=True, errors="ignore")
    assert r.returncode == 0, (r.stderr or "")[-300:]
    s = open(GUARD, encoding="utf-8").read()
    for need in ("RATE_STANDARD", "RATE_PACKAGE", "trust_env=False",
                 "/api/live/stop", "强制停止", "budget_sec"):
        assert need in s, f"缺 {need}"
    return "编译通过；单价/Clash 规避/停止调用/预算判断都在"


def t_autostop_at_budget():
    fb = FakeBridge("live")
    try:
        g = load_guard()
        g.BRIDGE = fb.url
        g.LOG = os.path.join(ROOT, "logs", "cost_guard_test.log")
        if os.path.exists(g.LOG):
            os.remove(g.LOG)
        sys.argv = ["cost_guard.py", "--budget-min", "0.05", "--interval", "0.5"]
        t0 = time.time()
        rc = g.main()
        took = time.time() - t0
        assert rc == 0, f"返回码 {rc}"
        assert fb.stops == 1, f"停止请求次数 {fb.stops}（应为 1）"
        log = open(g.LOG, encoding="utf-8").read()
        assert "强制停止" in log, "日志里没有强制停止记录"
        assert took < 20, f"耗时 {took:.1f}s 太长（预算 3 秒）"
        return f"3 秒预算到点自动停止（{took:.1f}s，stop 调用 {fb.stops} 次）"
    finally:
        fb.close()


def t_idle_no_billing():
    fb = FakeBridge("idle")
    logp = os.path.join(ROOT, "logs", "cost_guard_test_idle.log")
    try:
        if os.path.exists(logp):
            os.remove(logp)
        # 用子进程跑：进程内改不了模块常量，所以先写一份临时配置脚本
        shim = os.path.join(ROOT, "logs", "_guard_shim.py")
        open(shim, "w", encoding="utf-8").write(
            "import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('cost_guard', r'{GUARD}')\n"
            "g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)\n"
            f"g.BRIDGE = '{fb.url}'\n"
            f"g.LOG = r'{logp}'\n"
            "sys.argv = ['cost_guard.py', '--budget-min', '0.02', '--interval', '0.5', '--keep-on-exit']\n"
            "sys.exit(g.main())\n")
        pr = subprocess.Popen([PY, shim], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
        time.sleep(4)
        pr.terminate()
        pr.wait(timeout=15)
        assert fb.stops == 0, f"idle 却调用了停止 {fb.stops} 次"
        log = open(logp, encoding="utf-8").read() if os.path.exists(logp) else ""
        assert "开始计时" not in log, "idle 却开始计时了"
        return "idle 不计费（跑 4s，stop 调用 0 次，无开始计时日志）"
    finally:
        fb.close()


def t_once():
    fb = FakeBridge("live")
    try:
        r = subprocess.run([PY, GUARD, "--once"], capture_output=True, text=True,
                           timeout=30, errors="ignore",
                           env={**os.environ, "NO_PROXY": "127.0.0.1,localhost"})
        # 真桥没起时应该报不可达（退出码 2），这里只验证程序不崩
        assert r.returncode in (0, 2), f"退出码 {r.returncode}: {r.stderr[-200:]}"
        return f"--once 正常返回（退出码 {r.returncode}）"
    finally:
        fb.close()


if __name__ == "__main__":
    check("A 静态", t_static)
    check("B 到预算自动停", t_autostop_at_budget)
    check("C idle 不计费", t_idle_no_billing)
    check("D --once", t_once)
    ok = sum(1 for g, _, _ in R if g)
    print("\n" + "=" * 56)
    print(f"{ok}/{len(R)} 通过")
    sys.exit(0 if ok == len(R) else 1)
