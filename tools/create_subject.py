"""在 Vidu 建「主体」（= 数字人形象），拿到 avatar_id。

用法：
  .venv\\Scripts\\python.exe tools\\create_subject.py --image ..\\LiveStream\\assets\\xiaoya_avatar.png --name xiaoya-main
  .venv\\Scripts\\python.exe tools\\create_subject.py --list          # 列出现有主体
  .venv\\Scripts\\python.exe tools\\create_subject.py --write-config  # 把最新主体的 id 写进 config.json

为什么单独写：项目自带的 src/vidu/client.py 只封装了开播相关接口，没有「主体库」，
而开播前必须先有 avatar_id。
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "config.json")
HOST = "https://api.vidu.cn"


def key() -> str:
    with open(CFG, encoding="utf-8") as f:
        k = (json.load(f).get("vidu") or {}).get("api_key") or ""
    if not k:
        sys.exit("config.json 里 vidu.api_key 是空的")
    return k


def client() -> httpx.Client:
    # trust_env=False：Clash 会把国内 API 也劫走，导致证书/超时问题
    return httpx.Client(trust_env=False, timeout=60,
                        headers={"Authorization": f"Token {key()}",
                                 "Content-Type": "application/json"})


def as_data_url(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        raw = f.read()
    mb = len(raw) / 1024 / 1024
    if mb > 15:
        sys.exit(f"图片 {mb:.1f}MB 偏大（base64 后要 <20MB），先压缩")
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def list_subjects(c: httpx.Client) -> dict:
    r = c.get(f"{HOST}/ent/v2/subjects", params={"page": 0, "page_size": 20})
    return {"status": r.status_code, "body": r.text[:2000]}


def create(c: httpx.Client, name: str, path: str) -> dict:
    body = {"name": name, "images": [as_data_url(path)], "videos": [], "voice_id": ""}
    r = c.post(f"{HOST}/ent/v2/subjects", json=body)
    return {"status": r.status_code, "body": r.text[:2000]}


def wait_ready(c: httpx.Client, sid: str, timeout: int = 300) -> tuple[bool, dict]:
    t0 = time.time()
    last = {}
    while time.time() - t0 < timeout:
        r = c.get(f"{HOST}/ent/v2/subjects/{sid}")
        try:
            last = r.json()
        except Exception:
            last = {"raw": r.text[:300]}
        state = str(last.get("status") or last.get("state") or "").lower()
        print(f"  [{int(time.time() - t0):3d}s] status={state or last} ", flush=True)
        # enabled 是 Vidu 的"可用"状态（不是 pending），别只等 success
        if state in ("enabled", "success", "succeeded", "completed", "ready", "done"):
            return True, last
        if state in ("failed", "error", "rejected"):
            return False, last
        time.sleep(5)
    return False, last


def write_config(sid: str) -> None:
    with open(CFG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("avatar", {})["avatar_id"] = str(sid)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"已写入 config.json → avatar.avatar_id = {sid}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image")
    ap.add_argument("--name", default="xiaoya-main")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--write-config", action="store_true")
    ap.add_argument("--subject-id")
    ap.add_argument("--no-wait", action="store_true")
    a = ap.parse_args()

    with client() as c:
        if a.list:
            out = list_subjects(c)
            print("HTTP", out["status"])
            print(out["body"])
            return 0 if out["status"] == 200 else 1

        if a.write_config:
            if not a.subject_id:
                sys.exit("--write-config 需要同时给 --subject-id")
            write_config(a.subject_id)
            return 0

        if not a.image:
            sys.exit("需要 --image，或 --list / --write-config")

        print(f"创建主体 name={a.name} image={a.image}")
        out = create(c, a.name, a.image)
        print("HTTP", out["status"])
        print(out["body"])
        if out["status"] not in (200, 201):
            return 1
        try:
            sid = str(out["body"] and json.loads(out["body"]).get("id") or "")
        except Exception:
            sid = ""
        if not sid:
            print("响应里没有 id，先 --list 看现状")
            return 1
        print(f"subject id = {sid}")
        if a.no_wait:
            return 0
        ok, last = wait_ready(c, sid)
        print("最终:", json.dumps(last, ensure_ascii=False)[:400])
        if ok:
            write_config(sid)
            return 0
        return 1


if __name__ == "__main__":
    sys.exit(main())
