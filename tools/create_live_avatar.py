"""用一张干净肖像创建 Vidu **直播形象**（/live/v1/avatars），并可选写回 config。

为什么单独写这个：`/ent/v2/subjects` 建的是"生成用主体"，拿去开播会 404；
直播形象只认 `POST /live/v1/avatars`，且 **image_uri 必须是可访问的图片**
（本工具把本地图片转成 data URL 上传，实测可用）。

用法：
  .venv\\Scripts\\python.exe tools\\create_live_avatar.py --image <肖像.png> [--name xiaoya-v2] [--write-config]
  .venv\\Scripts\\python.exe tools\\create_live_avatar.py --list
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = "https://api.vidu.cn"


def client() -> httpx.Client:
    conf = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    key = (conf.get("vidu") or {}).get("api_key") or ""
    if not key:
        raise SystemExit("config.json 里没有 vidu.api_key")
    return httpx.Client(trust_env=False, timeout=120,
                        headers={"Authorization": f"Token {key}"})


def to_data_url(path: str, max_side: int = 1280) -> str:
    """压到 max_side 以内再转 data URL（太大容易被拒或超时）。"""
    from PIL import Image
    import io

    im = Image.open(path).convert("RGB")
    if max(im.size) > max_side:
        r = max_side / max(im.size)
        im = im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=95)
    raw = buf.getvalue()
    print(f"上传图: {im.size[0]}x{im.height} {len(raw)//1024}KB")
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image")
    ap.add_argument("--name", default="xiaoya")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--write-config", action="store_true")
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()

    c = client()

    if a.list:
        r = c.get(f"{HOST}/live/v1/avatars")
        print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:1500])
        return 0

    if not a.image:
        print("需要 --image <图片>（或用 --list 看已有形象）")
        return 2

    body = {"image_uri": to_data_url(a.image), "name": a.name}
    r = c.post(f"{HOST}/live/v1/avatars", json=body)
    print("创建 →", r.status_code)
    if r.status_code >= 300:
        print(r.text[:400])
        return 1
    av = r.json().get("avatar") or r.json()
    aid = str(av.get("id") or av.get("avatar_id") or "")
    print("avatar_id:", aid, "| status:", av.get("status"))
    if not aid:
        print(json.dumps(r.json(), ensure_ascii=False)[:400])
        return 1

    t0 = time.time()
    status = av.get("status")
    while status not in ("success", "failed") and time.time() - t0 < a.timeout:
        time.sleep(3)
        d = c.get(f"{HOST}/live/v1/avatars/{aid}").json()
        status = (d.get("avatar") or d).get("status")
        print(f"  {int(time.time()-t0):3d}s status={status}", flush=True)
    if status != "success":
        print("❌ 形象未就绪:", status)
        return 1

    print("✅ 直播形象就绪:", aid)
    if a.write_config:
        p = os.path.join(ROOT, "config.json")
        conf = json.load(open(p, encoding="utf-8"))
        conf.setdefault("avatar", {})["avatar_id"] = aid
        conf["avatar"]["name"] = a.name
        json.dump(conf, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("已写回 config.json → avatar.avatar_id =", aid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
