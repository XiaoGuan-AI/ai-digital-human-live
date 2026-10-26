"""看图问答（GLM 视觉），用于 vision_analyze 不可用时。

背景：本机 `vision_analyze` 走代理常报 cloudflare 400/502，而 GLM（智谱）国内直连稳定。
本工具直接从 `D:\\Projects\\me\\secrets\\api-keys.md` 读 GLM key，不落盘、不打印。

用法:
  .venv\\Scripts\\python.exe tools\\ask_vision.py <图片> "你的问题"
  .venv\\Scripts\\python.exe tools\\ask_vision.py <图片> --file prompt.txt
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys

import httpx

VAULT = r"D:\Projects\me\secrets\api-keys.md"
API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


def glm_key() -> str:
    text = open(VAULT, encoding="utf-8", errors="ignore").read()
    # 1) 形如 `GLM_API_KEY = 32hex.xxxx.yyyy`
    for line in text.splitlines():
        if "GLM" in line.upper():
            m = re.search(r"([0-9a-zA-Z]{16,}\.[0-9a-zA-Z_-]{8,}\.[0-9a-zA-Z_-]{8,})", line)
            if m:
                return m.group(1)
            m = re.search(r"([0-9a-f]{32}\.[0-9a-zA-Z]{10,})", line)
            if m:
                return m.group(1)
    # 2) 全文兜底
    for pat in (r"([0-9a-zA-Z]{16,}\.[0-9a-zA-Z_-]{8,}\.[0-9a-zA-Z_-]{8,})",
                r"([0-9a-f]{32}\.[0-9a-zA-Z]{10,})"):
        m = re.search(pat, text)
        if m:
            return m.group(1)
    raise SystemExit("没在 vault 里找到 GLM key")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("question", nargs="?", default="")
    ap.add_argument("--file", default="")
    ap.add_argument("--model", default="glm-4.5v")
    a = ap.parse_args()

    q = a.question
    if a.file:
        q = open(a.file, encoding="utf-8").read()
    if not q:
        q = "请详细描述这张图的内容，包括所有文字（逐字抄写+位置）和任何异常。"

    b64 = base64.b64encode(open(a.image, "rb").read()).decode()
    key = glm_key()
    c = httpx.Client(trust_env=False, timeout=180)
    r = c.post(API, headers={"Authorization": f"Bearer {key}"},
               json={"model": a.model, "messages": [{"role": "user", "content": [
                   {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                   {"type": "text", "text": q}]}]})
    if r.status_code != 200:
        print(f"HTTP {r.status_code}: {r.text[:400]}")
        return 1
    print(r.json()["choices"][0]["message"]["content"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
