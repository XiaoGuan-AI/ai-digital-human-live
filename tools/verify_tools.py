"""本轮 5 个辅助工具的仓库常驻验收（零成本，约 20 秒）。

  ask_vision.py           视觉模型看图（GLM 直连，绕开坏掉的 vision_analyze）
  face_count.py           数截图里有几张脸（判定"复制人像"）
  list_edge_windows.ps1   列出 Edge 窗口标题（UTF-8，中文不乱码）
  stage_click.py          --status / --shot-only / 多窗口告警
  create_live_avatar.py   建 Vidu 直播形象（数据 URL 上传 + 轮询 + 写回配置）

用法: .venv\\Scripts\\python.exe tools\\verify_tools.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
SHOT = os.path.join(ROOT, "shots", "_user_shot2.png")
WINS = os.path.join(ROOT, "logs", "_edge_windows.txt")
ENV = {k: v for k, v in os.environ.items()
       if k not in ("PYTHONPATH", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
R = []


def run(args, **kw):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          timeout=180, errors="ignore", env=ENV, **kw)


def check(name, fn):
    try:
        R.append((True, name, fn()))
    except Exception as e:                                          # noqa: BLE001
        R.append((False, name, f"{type(e).__name__}: {e}"))
    print(f"{'PASS' if R[-1][0] else 'FAIL'}  {name}: {R[-1][2]}", flush=True)


def phase() -> str:
    o = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with o.open("http://127.0.0.1:8795/api/health", timeout=8) as r:
        return json.load(r).get("phase")


def t_compile():
    r = run([PY, "-m", "py_compile", "tools/ask_vision.py", "tools/face_count.py",
             "tools/stage_click.py"])
    assert r.returncode == 0, (r.stderr or "")[-400:]
    ps = run(["powershell", "-NoProfile", "-Command",
              "$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
              f"'{os.path.join(ROOT, 'tools', 'list_edge_windows.ps1')}', [ref]$null, [ref]$e);"
              "if ($e.Count) { $e[0].Message; exit 1 } else { 'ok' }"])
    assert ps.returncode == 0, (ps.stdout or ps.stderr or "")[-300:]
    return "3 个 py 编译通过；ps1 语法 0 错误"


def t_ask_vision():
    s = open(os.path.join(ROOT, "tools", "ask_vision.py"), encoding="utf-8").read()
    for need in ('"--file"', '"--model"', "data:image/png;base64", "trust_env=False",
                 "def glm_key(", "api-keys.md"):
        assert need in s, f"缺 {need}"
    assert "print(key" not in s, "疑似打印了 key"
    r = run([PY, "tools/ask_vision.py", "--help"])
    assert r.returncode == 0 and "question" in r.stdout, (r.stderr or "")[-300:]
    return "契约齐全（vault 取 key 不打印 / data URL / trust_env=False）；--help 正常"


def t_face_count():
    r = run([PY, "tools/face_count.py", SHOT])
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-400:]
    assert "人脸总数 1" in out, out[-300:]
    return "已知截图 → 1 张脸（未误报复制人像）"


def t_stage_status():
    before = phase()
    r = run([PY, "tools/stage_click.py", "--status"])
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-300:]
    assert "page:" in out and ("窗口数:" in out or "同屏有" in out), out[-300:]
    after = phase()
    assert after == before, f"跑到一半 phase 变了: {before}→{after}"
    line = [ln for ln in out.splitlines() if "窗口数:" in ln or "同屏有" in ln][-1]
    return f"phase {before}→{after}；{line.strip()[:46]}"


def t_win_list():
    if os.path.exists(WINS):
        os.remove(WINS)
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         "tools/list_edge_windows.ps1"])
    assert os.path.exists(WINS), "没生成窗口清单"
    lines = [ln.strip() for ln in open(WINS, encoding="utf-8-sig") if ln.strip()]
    assert lines, "清单为空"
    return f"{len(lines)} 个 Edge 窗口，含舞台页的 {sum('数字人' in ln for ln in lines)} 个"


def t_avatar_tool():
    r = run([PY, "-m", "py_compile", "tools/create_live_avatar.py"])
    assert r.returncode == 0, (r.stderr or "")[-400:]
    s = open(os.path.join(ROOT, "tools", "create_live_avatar.py"), encoding="utf-8").read()
    for need in ('"--image"', '"--list"', '"--write-config"', "/live/v1/avatars",
                 "data:image/jpeg;base64", 'conf.setdefault("avatar"'):
        assert need in s, f"缺 {need}"
    r = run([PY, "tools/create_live_avatar.py", "--list"])
    assert r.returncode == 0, (r.stdout or r.stderr or "")[-300:]
    aid = (json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8")).get("avatar") or {}).get("avatar_id")
    assert aid and aid in (r.stdout or ""), f"config avatar_id {aid} 不在 --list 输出里"
    return f"编译通过；--list 正常，当前 avatar_id {aid} 在列表中"


if __name__ == "__main__":
    check("A 编译/语法", t_compile)
    check("B ask_vision 契约", t_ask_vision)
    check("C face_count 实测", t_face_count)
    check("D stage_click --status", t_stage_status)
    check("E 窗口清单 ps1", t_win_list)
    check("F 建形象工具", t_avatar_tool)
    ok = sum(1 for g, _, _ in R if g)
    print("\n" + "=" * 52)
    print(f"{ok}/{len(R)} 通过")
    sys.exit(0 if ok == len(R) else 1)
