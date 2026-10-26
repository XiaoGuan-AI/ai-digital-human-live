"""中文搜索（搜狗）取标题+真实 URL —— 供调研用，按 china-web-research 技能配方。

用法: python tools/cn_search.py "关键词1" "关键词2" ...
输出: 每个关键词下的前 N 条标题 + data-url（真实地址）+ 摘要片段。
     搜狗限流特征：返回 html 只有 ~5KB → 自动 sleep 重试（最多 2 次）。
"""
from __future__ import annotations

import html as H
import os
import re
import sys
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
PROXY = "http://127.0.0.1:7897"
MIN_GAP_S = 12.0          # 连续搜索最小间隔（搜狗限流实测：连发即空壳）
_STAMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", ".cn_search_last")


def _wait_turn() -> None:
    """跨进程冷却：上次搜索时间落盘，任何进程再搜都先补够间隔（连发必被限流）。"""
    try:
        last = float(open(_STAMP, encoding="utf-8").read().strip() or 0)
    except Exception:                                            # noqa: BLE001
        last = 0.0
    gap = MIN_GAP_S - (time.time() - last)
    if gap > 0:
        time.sleep(gap)


def _mark_turn() -> None:
    try:
        os.makedirs(os.path.dirname(_STAMP), exist_ok=True)
        with open(_STAMP, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except Exception:                                            # noqa: BLE001
        pass


def fetch(url: str, use_proxy: bool = False, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    if use_proxy:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    else:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc, "ignore")
        except Exception:  # noqa: BLE001
            continue
    return raw.decode("utf-8", "ignore")


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = H.unescape(s).replace("\u3000", " ")
    return re.sub(r"\s+", " ", s).strip()      # 折叠换行/制表（360 结果里全是


def sogou(kw: str, n: int = 6) -> list[tuple[str, str, str]]:
    """搜狗搜索 → [(标题, 真实URL, 摘要)]。

    限流对策（2026-10-25 实测踩坑）：①连续调用必须间隔 ≥ MIN_GAP_S（连发第二发必空壳）；
    ②**零结果也当限流重试**（只看返回体积会漏判：空壳页面也可能 >80KB）。
    """
    url = "https://www.sogou.com/web?query=" + urllib.parse.quote(kw)
    out: list[tuple[str, str, str]] = []
    for attempt in range(3):
        _wait_turn()
        try:
            page = fetch(url)
        except Exception as e:  # noqa: BLE001
            print(f"  ! 抓取失败 {type(e).__name__}", flush=True)
            page = ""
        _mark_turn()

        blocks = re.split(r'<div class="vrwrap"|<div class="rb"', page)
        out = []
        for b in blocks[1:]:
            m = re.search(r'data-url="([^"]+)"', b)
            t = re.search(r"<h3[^>]*>(.*?)</h3>", b, re.S)
            if not m or not t:
                continue
            title = clean(t.group(1))
            if not title:
                continue
            snippet = ""
            sm = re.search(r'<div class="(?:text-layout|str-text-info|fz-mid)[^"]*"[^>]*>(.*?)</div>',
                           b, re.S)
            if sm:
                snippet = clean(sm.group(1))[:120]
            out.append((title, H.unescape(m.group(1)), snippet))
            if len(out) >= n:
                break
        if out:
            return out
        if attempt < 2:
            print(f"  ~ 零结果（{len(page)}B），按限流处理，等 {int(MIN_GAP_S)}s 重试", flush=True)
    return out


def so360_news(kw: str, n: int = 6) -> list[tuple[str, str, str]]:
    """360 新闻聚合通道（搜狗限流时的降级）：直接给源站 URL + 标题。

    搜狗 5.4KB 空壳 = 被限流（实测）。360 新闻聚合页的 `<a href>` 是**真实源站地址**，
    不需要解密（别用 so.com/link，那是服务端加密跳转）。
    """
    url = "https://news.so.com/ns?q=" + urllib.parse.quote(kw)
    try:
        page = fetch(url, use_proxy=True)
    except Exception:                                            # noqa: BLE001
        try:
            page = fetch(url)
        except Exception:                                        # noqa: BLE001
            return []
    if len(page) < 20000:
        return []
    out: list[tuple[str, str, str]] = []
    for u, t in re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', page, re.S):
        title = clean(t)
        if len(title) < 8 or "so.com" in u or "360.cn" in u:
            continue
        out.append((title, H.unescape(u), ""))
        if len(out) >= n:
            break
    return out


def search(kw: str, n: int = 6) -> tuple[str, list[tuple[str, str, str]]]:
    """统一入口：搜狗优先，限流/零结果自动降级 360 新闻聚合。返回 (通道名, 结果)。"""
    got = sogou(kw, n)
    if got:
        return "搜狗", got
    got = so360_news(kw, n)
    if got:
        return "360新闻", got
    return "无", []


def main() -> int:
    kws = sys.argv[1:]
    if not kws:
        print(__doc__)
        return 2
    for i, kw in enumerate(kws):
        print(f"\n=== {kw}")
        channel, rows = search(kw)
        print(f"  [通道] {channel}，{len(rows)} 条")
        for title, url, snip in rows:
            print(f"  · {title[:80]}")
            print(f"    {url[:110]}")
            if snip:
                print(f"    {snip}")
        if i < len(kws) - 1:
            time.sleep(13)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
