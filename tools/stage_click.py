"""用舞台页自己的「开始连线」按钮开会话，并确认视频真的挂上了。

为什么需要：
  通过 POST /api/live/start 开会话，**页面不会自动订阅**（页面只在它自己点
  「开始连线」时才 join RTC）→ 桥说 phase=live，但浏览器里 still 图还在、video
  没有 srcObject，用户看到的就是「没有画面」。
  本工具点页面按钮，然后校验 video.srcObject / videoWidth 真的到位。

用法：
  .venv\\Scripts\\python.exe tools\\stage_click.py            # 开始连线并等视频挂上
  .venv\\Scripts\\python.exe tools\\stage_click.py --status    # 只看当前页面状态
  .venv\\Scripts\\python.exe tools\\stage_click.py --stop      # 点「挂断」

前置：舞台页已在一个带 --remote-debugging-port=9334 的 Edge 里打开。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

import httpx
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9334"
BRIDGE = "http://127.0.0.1:8795"

JS_STATUS = """() => {
  const v = document.querySelector('video');
  const img = document.getElementById('avatarStill');
  const pill = document.querySelector('.pill');
  return {
    pill: (pill && pill.textContent) || '',
    still: img ? getComputedStyle(img).display : '-',
    vw: v ? v.videoWidth : 0, vh: v ? v.videoHeight : 0,
    ready: v ? v.readyState : -1, paused: v ? v.paused : null,
    muted: v ? v.muted : null, srcObject: !!(v && v.srcObject),
    t: v ? Math.round(v.currentTime * 10) / 10 : 0,
    mask: (document.getElementById('mask') || {}).style?.display
  };
}"""


def page(browser):
    pgs = [x for ctx in browser.contexts for x in ctx.pages if "8795" in x.url]
    if not pgs:
        sys.exit("没找到舞台页（先在带 9334 调试端口的 Edge 里打开 http://127.0.0.1:8795/stage）")
    return pgs[0]


def bridge_phase() -> str:
    try:
        return httpx.Client(trust_env=False, timeout=8).get(f"{BRIDGE}/api/health").json().get("phase", "?")
    except Exception as e:
        return f"unreachable({e.__class__.__name__})"


def _dup_windows() -> int:
    """数有多少个 Edge 窗口标题含「数字人」（= 同屏开了几个舞台页）。

    ≥2 时会看到"一大一小两份画面"的假重影 —— 2026-10-25 用户实际踩过：
    早期用 `start msedge <url>` 开过一个普通窗口，后来又用 --app 开了小窗口，
    两个窗口叠在一起，截图里就像重影。
    """
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-Process msedge -ErrorAction SilentlyContinue | "
                            "Where-Object { $_.MainWindowTitle -match '数字人' } | "
                            "Measure-Object | Select-Object -ExpandProperty Count"],
                           capture_output=True, text=True, timeout=25, errors="ignore")
        return int((r.stdout or "0").strip() or 0)
    except Exception:
        return -1


def _shot(pg) -> str:
    """把舞台页截图存到项目 shots/（纯读操作，不触发开会话）。"""
    shot = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "shots", "stage_after_click.png")
    os.makedirs(os.path.dirname(shot), exist_ok=True)
    pg.screenshot(path=shot)
    print(f"截图: {shot}")
    return shot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--shot-only", action="store_true",
                    help="只截一张舞台页图就退出（绝不点击开播、不开会话、不花钱）")
    a = ap.parse_args()

    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP)
        pg = page(b)

        if a.status:
            print("server phase:", bridge_phase())
            print("page:", json.dumps(pg.evaluate(JS_STATUS), ensure_ascii=False))
            n = _dup_windows()
            if n > 1:
                print(f"⚠ 同屏有 {n} 个舞台页窗口 → 会看到两大一小两份画面的假重影！"
                      f"关掉多余的窗口，只留一个（推荐用 start-vidu.cmd 启动的 app 窗口）")
            elif n >= 0:
                print(f"窗口数: {n}（只应有一个）")
            b.close()
            return 0

        if a.shot_only:
            _shot(pg)
            b.close()
            return 0

        if a.stop:
            pg.click("#btnStop")
            time.sleep(2)
            print("已点挂断 → server phase:", bridge_phase())
            b.close()
            return 0

        # 开始连线
        before = pg.evaluate(JS_STATUS)
        if before["srcObject"] and before["vw"]:
            print("已经在推流，无需重复点（重复点会挂断旧会话 = 多花钱）")
            print(json.dumps(before, ensure_ascii=False))
            _shot(pg)                       # 已在推流也留一张取证截图（纯读，不花钱）
            b.close()
            return 0

        print("点击「开始连线」…", flush=True)
        try:
            pg.click("#btnGo", timeout=8000)
        except Exception:
            pg.evaluate("() => document.getElementById('btnGo').click()")
            print("（普通点击超时，已用 JS 点击）")

        t0 = time.time()
        ok = False
        while time.time() - t0 < a.timeout:
            time.sleep(2)
            st = pg.evaluate(JS_STATUS)
            print(f"  t+{int(time.time()-t0):2d}s pill={st['pill'][:14]:14s} still={st['still']:5s} "
                  f"video={st['vw']}x{st['vh']} ready={st['ready']} src={st['srcObject']} "
                  f"t={st['t']} muted={st['muted']}", flush=True)
            if st["srcObject"] and st["vw"] > 0 and st["ready"] >= 2:
                ok = True
                break
        print()
        print("server phase:", bridge_phase())
        print("结果:", "✅ 视频已挂上，画面可见" if ok else "❌ 超时：视频没挂上（看上面的 pill / 页面提示）")
        try:
            _shot(pg)
        except Exception:
            pass
        b.close()
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
