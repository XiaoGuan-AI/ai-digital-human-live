"""Vidu 按秒计费的看门狗：计时、算钱、到预算强制停止。

为什么必须有：Vidu S2 = 1 积分/秒 ≈ ¥0.031/秒。忘了关就是 ¥112.5/小时。
本脚本只认桥的 /api/health 里的 phase：只有 `live` 才计时（此时才真的在烧钱），
到预算或超时就 POST /api/live/stop。

用法：
  python tools/cost_guard.py                # 默认 25 分钟预算，前台常驻
  python tools/cost_guard.py --budget-min 10
  python tools/cost_guard.py --once          # 只看当前状态，不起循环
  python tools/cost_guard.py --keep-on-exit  # Ctrl+C 时不停止（默认会停）

费用口径：
  --rate-standard（默认） 1 积分/秒 × ¥0.03125  = ¥0.03125/秒（标价，偏保守）
  --rate-package          1 积分/秒 × ¥0.02188  = ¥0.02188/秒（69 元包折算）

产物：logs/cost_guard.log（每 10 秒一行，含累计金额）
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "logs", "cost_guard.log")
BRIDGE = "http://127.0.0.1:8795"
RATE_STANDARD = 0.03125      # 元/秒（1 积分/秒，标价）
RATE_PACKAGE = 0.02188       # 元/秒（69 元 = 3154 积分折算）

_stop_requested = False


def log(msg: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def get_phase(c: httpx.Client) -> str:
    try:
        r = c.get(f"{BRIDGE}/api/health", timeout=5)
        if r.status_code == 200:
            return str(r.json().get("phase") or "unknown")
    except Exception:
        return "unreachable"
    return "unknown"


def stop_live(c: httpx.Client) -> bool:
    try:
        r = c.post(f"{BRIDGE}/api/live/stop", timeout=30)
        log(f"已发送停止指令 → HTTP {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        log(f"停止指令失败：{e}")
        return False


def fmt(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-min", type=float, default=25.0, help="计时预算（分钟）")
    ap.add_argument("--budget-cny", type=float, default=0.0, help="金额预算（元），0=不限，与分钟取先到者")
    ap.add_argument("--rate-package", action="store_true", help="用 69 元包折算单价")
    ap.add_argument("--once", action="store_true", help="只打印当前状态")
    ap.add_argument("--keep-on-exit", action="store_true", help="退出时不停止直播")
    ap.add_argument("--interval", type=float, default=2.0)
    a = ap.parse_args()

    rate = RATE_PACKAGE if a.rate_package else RATE_STANDARD
    budget_sec = int(a.budget_min * 60)
    if a.budget_cny > 0:
        budget_sec = min(budget_sec, int(a.budget_cny / rate))

    c = httpx.Client(trust_env=False)          # Clash 会把 127.0.0.1 也劫走

    if a.once:
        ph = get_phase(c)
        print(f"phase = {ph}（只有 live 才计费）")
        return 0 if ph != "unreachable" else 2

    def _on_sig(signum, frame):                # noqa: ARG001
        global _stop_requested
        _stop_requested = True

    for _sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(_sig, _on_sig)
        except ValueError:
            # 在子线程里跑 main()（测试/嵌入场景）时注册不了信号，忽略即可
            pass

    log(f"计费看门狗启动：预算 {fmt(budget_sec)}（¥{budget_sec * rate:.2f}），单价 ¥{rate:.5f}/秒")

    billed = 0.0          # 秒，浮点：允许 --interval 0.5 这类细粒度测试
    was_live = False
    already_stopped = False
    warned = False
    try:
        while not _stop_requested:
            ph = get_phase(c)
            if ph == "live":
                if not was_live:
                    log("检测到 phase=live → 开始计时（正在烧钱）")
                    was_live = True
                billed += a.interval
                cny = billed * rate
                if not warned and billed >= budget_sec * 0.8:
                    log(f"⚠ 已用 80% 预算：{fmt(billed)} / ¥{cny:.2f}")
                    warned = True
                if billed >= budget_sec:
                    log(f"⛔ 到达预算上限 {fmt(budget_sec)}（¥{cny:.2f}）→ 强制停止")
                    stop_live(c)
                    already_stopped = True
                    return 0
                if int(billed) % 10 == 0:
                    log(f"[计费] 已播 {fmt(billed)} | 约 ¥{cny:.2f} | 预算剩余 {fmt(budget_sec - billed)}")
            else:
                if was_live:
                    log(f"检测到 phase={ph} → 停止计时（累计 {fmt(billed)}，约 ¥{billed * rate:.2f}）")
                    was_live = False
            time.sleep(a.interval)
    finally:
        cny = billed * rate
        if not already_stopped and not a.keep_on_exit and get_phase(c) == "live":
            log(f"退出时仍在 live（累计 {fmt(billed)} / ¥{cny:.2f}）→ 自动停止")
            stop_live(c)
        else:
            log(f"退出。累计计费 {fmt(billed)}，约 ¥{cny:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
