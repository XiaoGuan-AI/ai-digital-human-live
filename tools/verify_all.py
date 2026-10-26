"""一条命令跑完项目全部验收（**规范入口**）。

用法:
  .venv\\Scripts\\python.exe tools\\verify_all.py            # 跑全部
  .venv\\Scripts\\python.exe tools\\verify_all.py sentence    # 只跑名字含 sentence 的

约定：每个 `tools/verify_*.py` 自己打印 PASS/FAIL 并以退出码 0/1 表示结果；
本脚本只负责顺序执行 + 汇总，不重复实现检查逻辑（DRY）。
耗时的（clone/tts/model）可以用 `--skip` 排除。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
ENV = {k: v for k, v in os.environ.items()
       if k not in ("PYTHONPATH", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
TIMEOUT = 600


def discover(skip: set[str]) -> list[str]:
    names = sorted(f for f in os.listdir(os.path.join(ROOT, "tools"))
                   if f.startswith("verify_") and f.endswith(".py") and f != "verify_all.py")
    return [n for n in names if not any(s in n for s in skip)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("filters", nargs="*", help="只跑名字含这些词的（空=全部）")
    ap.add_argument("--skip", default="", help="逗号分隔，跳过名字含这些词的")
    a = ap.parse_args()

    skip = {s.strip() for s in a.skip.split(",") if s.strip()}
    files = [f for f in discover(skip)
             if not a.filters or any(k in f for k in a.filters)]
    if not files:
        print("没有匹配的验收脚本")
        return 2

    rows: list[tuple[str, bool, str]] = []
    for f in files:
        print(f"\n─── {f} " + "─" * max(0, 46 - len(f)), flush=True)
        try:
            r = subprocess.run([PY, "-u", os.path.join("tools", f)], cwd=ROOT,
                               capture_output=True, text=True, errors="ignore",
                               timeout=TIMEOUT, env=ENV)
            out = (r.stdout or "") + (r.stderr or "")
            tail = next((ln for ln in reversed(out.splitlines())
                         if "通过" in ln or "FAIL" in ln), "")
            print(out.strip()[-1200:], flush=True)
            rows.append((f, r.returncode == 0, tail.strip() or f"exit={r.returncode}"))
        except subprocess.TimeoutExpired:
            rows.append((f, False, f"超时 >{TIMEOUT}s"))

    ok = sum(1 for _, good, _ in rows if good)
    print("\n" + "=" * 62)
    for f, good, tail in rows:
        print(f"{'✅' if good else '❌'}  {f:32s} {tail[:40]}")
    print("=" * 62)
    print(f"总计 {ok}/{len(rows)} 个验收脚本通过")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
