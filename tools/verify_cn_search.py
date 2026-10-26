"""cn_search.py（中文搜索取真实 URL）的仓库常驻验收。约 10 秒，零花费。

为什么要它：这个工具的价值全在「拿到真实 URL」而不是搜狗那层 `so.com/link` 加密跳转，
所以验收必须**真跑一次搜索**，只查字符串等于没验。

A) 编译
B) 模块接口：sogou/clean/fetch 存在，clean 去标签+解 HTML 实体
C) 真跑搜索：≥1 条标题且 ≥1 条真实 URL，且不含 so.com/link
D) 无参数：打印用法并 exit 2

用法: .venv\\Scripts\\python.exe tools\\verify_cn_search.py
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
ENV = {k: v for k, v in os.environ.items()
       if k not in ("PYTHONPATH", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
R = []


def run(a, timeout=200):
    return subprocess.run(a, cwd=ROOT, capture_output=True, text=True,
                          timeout=timeout, errors="ignore", env=ENV)


def check(n, fn):
    try:
        R.append((True, n, fn()))
    except Exception as e:                                        # noqa: BLE001
        R.append((False, n, f"{type(e).__name__}: {e}"))
    print(f"{'PASS' if R[-1][0] else 'FAIL'}  {n}: {R[-1][2]}", flush=True)


def t_compile():
    r = run([PY, "-m", "py_compile", "tools/cn_search.py"])
    assert r.returncode == 0, (r.stderr or "")[-400:]
    return "编译通过"


def t_api():
    spec = importlib.util.spec_from_file_location(
        "cn_search", os.path.join(ROOT, "tools", "cn_search.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    for fn in ("sogou", "clean", "fetch"):
        assert hasattr(m, fn), f"缺 {fn}()"
    got = m.clean("<b>你好</b>&amp;世界")
    assert got == "你好&世界", got
    return "sogou/clean/fetch 齐备；clean 去标签+解实体正确"


def t_real_search():
    """真跑一次；搜狗限流时自动降级 360，两者都算通过（只要拿到真实 URL）。"""
    r = run([PY, "tools/cn_search.py", "开源 实时 数字人 显存"])
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-400:]
    assert "[通道]" in out, "没打印通道名"
    channel = next((ln.split("]")[1].split("，")[0].strip()
                    for ln in out.splitlines() if "[通道]" in ln), "?")
    titles = [ln for ln in out.splitlines() if ln.strip().startswith("·")]
    urls = [ln.strip() for ln in out.splitlines()
            if ln.strip().startswith(("http://", "https://"))]
    assert titles, f"[{channel}] 没有标题"
    assert urls, f"[{channel}] 没有真实 URL"
    assert not any("so.com/link" in u for u in urls), "拿到加密跳转而非真实地址"
    return f"{channel}：{len(titles)} 条标题 / {len(urls)} 条真实 URL（例 {urls[0][:40]}）"


def t_usage():
    r = run([PY, "tools/cn_search.py"])
    assert r.returncode == 2, f"无参数应 exit 2，实际 {r.returncode}"
    return "无参数 → 打印用法并 exit 2"


if __name__ == "__main__":
    check("A 编译", t_compile)
    check("B 模块接口/清洗", t_api)
    check("C 真跑搜索", t_real_search)
    check("D 无参数用法", t_usage)
    ok = sum(1 for g, _, _ in R if g)
    print("\n" + "=" * 52)
    print(f"{ok}/{len(R)} 通过")
    sys.exit(0 if ok == len(R) else 1)
