"""校验本地 OmniVoice 权重是否与上游一致（sha256 + 大小）。

为什么必须有：2026-10-25 踩过一次 —— aria2 分段下载 + curl 续传混用，
`model.safetensors` **大小完全正确但内容错位**，加载不报错、TTS 直接输出噪声。
症状是"能出声但听不清"，非常难查；只有 sha256 能一眼定性。

用法：
  .venv\\Scripts\\python.exe tools\\verify_model.py
  .venv\\Scripts\\python.exe tools\\verify_model.py --repo k2-fsa/OmniVoice --dir models/OmniVoice
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256_of(path: str, bufsize: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(bufsize), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="k2-fsa/OmniVoice")
    ap.add_argument("--dir", default=os.path.join(ROOT, "models", "OmniVoice"))
    ap.add_argument("--endpoint", default="https://hf-mirror.com")
    a = ap.parse_args()

    url = f"{a.endpoint}/api/models/{a.repo}?blobs=true"
    try:
        # hf-mirror 直连可用；走代理反而极慢，故 trust_env=False
        r = httpx.Client(trust_env=False, timeout=60, verify=False).get(url)
        r.raise_for_status()
        info = r.json()
    except Exception as e:                                   # noqa: BLE001
        print(f"❌ 拉取上游清单失败: {type(e).__name__}: {e}")
        return 2

    checked = failed = missing = 0
    for sib in info.get("siblings") or []:
        lfs = sib.get("lfs") or {}
        sha, size = lfs.get("sha256"), lfs.get("size")
        if not sha:
            continue                                        # 小文件无 lfs 摘要，跳过
        name = sib["rfilename"]
        path = os.path.join(a.dir, name)
        if not os.path.exists(path):
            print(f"缺失   {name}")
            missing += 1
            continue
        checked += 1
        real = os.path.getsize(path)
        if size is not None and real != size:
            print(f"❌大小 {name}  本地 {real:,} / 期望 {size:,}")
            failed += 1
            continue
        got = sha256_of(path)
        if got == sha:
            print(f"✅     {name}  ({real / 1e6:.1f} MB)")
        else:
            print(f"❌摘要 {name}  本地 {got[:16]}… / 期望 {sha[:16]}…  → 重新下载这一个文件")
            failed += 1

    print("\n" + "=" * 52)
    print(f"校验 {checked} 个大文件：{checked - failed} 通过 / {failed} 不一致 / {missing} 缺失")
    return 0 if failed == 0 and missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
