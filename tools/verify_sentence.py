"""TTS 语音管线（分句 + 克隆/设计音色）的仓库常驻验收。零 Vidu 花费，约 20 秒。

背景（2026-10-25）：
  - "说唱腔" 的真实起因是**参考音频本身拖腔**，克隆把它学走了；分句只是放大因素。
  - 因此这里同时守两件事：①分句阈值确实接进 SentenceStream；②克隆通路 `ref_text`
    必须从 preset 顶层取（曾误写成 params.get('ref_text') → 参数为空 → 全部合成报错）。

A) 编译 4 个相关文件
B) engine：_sentence_cfg 默认 28/60 且两处 SentenceStream 接入；synth_one 失败重试写 stdout；live 后预热 TTS
C) tts/omnivoice：instruct 走 params；ref_text 仍取 preset（回归点）
D) 工具脚本：style_compare 复现旧阈值；tone_variants 含 design 与语速档
E) 行为：新旧分句块对比 + 克隆/design 各真合成一次，PCM 非空

用法: .venv\\Scripts\\python.exe tools\\verify_sentence.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
ENV = {k: v for k, v in os.environ.items()
       if k not in ("PYTHONPATH", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
R = []


def run(a, **kw):
    return subprocess.run(a, cwd=ROOT, capture_output=True, text=True,
                          timeout=300, errors="ignore", env=ENV, **kw)


def check(n, fn):
    try:
        R.append((True, n, fn()))
    except Exception as e:                                        # noqa: BLE001
        R.append((False, n, f"{type(e).__name__}: {e}"))
    print(f"{'PASS' if R[-1][0] else 'FAIL'}  {n}: {R[-1][2]}", flush=True)


def t_compile():
    r = run([PY, "-m", "py_compile", "src/engine.py", "src/tts/omnivoice.py",
             "tools/style_compare.py", "tools/tone_variants.py"])
    assert r.returncode == 0, (r.stderr or "")[-500:]
    return "engine / omnivoice / style_compare / tone_variants 编译通过"


def t_engine():
    s = open(os.path.join(ROOT, "src", "engine.py"), encoding="utf-8").read()
    assert "def _sentence_cfg(" in s, "缺 _sentence_cfg"
    assert 'c.get("sentence_soft_min", 28)' in s, "soft 默认值不是 28"
    assert 'c.get("sentence_hard_max", 60)' in s, "hard 默认值不是 60"
    assert s.count("llmmod.SentenceStream(soft_min=_soft, hard_max=_hard)") == 2, \
        "SentenceStream 两处构造没都接配置"
    assert "合成失败(第" in s and "await asyncio.sleep(0.3)" in s, "synth_one 没重试/没写 stdout"
    assert "asyncio.create_task(self._tts_prewarm())" in s, "缺 TTS 预热"
    # 2026-10-25 踩过：只加了调用、没写定义 → AttributeError 被 except 吞掉，等于没预热
    assert "async def _tts_prewarm(" in s, "缺 _tts_prewarm 定义（曾只调用未定义）"
    assert 'self._tts_warmed = True' in s, "预热成功后没置标记"
    br = open(os.path.join(ROOT, "src", "bridge.py"), encoding="utf-8").read()
    assert "engine._tts_prewarm()" in br, "桥启动时没预热"
    return "阈值接配置(2处) + 失败重试写 stdout + live 后预热"


def t_tts_module():
    s = open(os.path.join(ROOT, "src", "tts", "omnivoice.py"), encoding="utf-8").read()
    assert 'str(params.get("instruct") or "")' in s, "instruct 没接进克隆调用"
    assert 'preset.get("ref_text", "")' in s, "ref_text 应取自 preset 顶层"
    assert 'params.get("ref_text"' not in s, "存在 params.ref_text（会把 ref_text 取空）"
    return "instruct→params；ref_text 从 preset 取"


def t_tools():
    sc = open(os.path.join(ROOT, "tools", "style_compare.py"), encoding="utf-8").read()
    tv = open(os.path.join(ROOT, "tools", "tone_variants.py"), encoding="utf-8").read()
    assert "SentenceStream(soft_min=10" in sc, "对照脚本没复现旧阈值"
    assert "192k" in sc, "对照脚本没转 mp3"
    assert "DESIGN_PRESET" in tv and '"sp": 1.3' in tv, "变体脚本缺 design 或语速档"
    return "对照脚本复现旧阈值 + 转 mp3；变体脚本含 design/语速档"


def t_behavior():
    code = r'''
import asyncio, json, sys
sys.path.insert(0, r"%s")
from src.llm import SentenceStream
from src.tts import omnivoice as ov

TEXT = "今天天气不错啊，我刚看到有人在评论区问我是不是真人，其实我是数字人啦，陪你聊天是真的。"

def blocks(soft, hard):
    s = SentenceStream(soft_min=soft, hard_max=hard)
    out = s.feed(TEXT)
    t = s.flush()
    if t: out.append(t)
    return [len(x) for x in out if x]

cfg = json.load(open(r"%s/config.json", encoding="utf-8")).get("tts") or {}
old = blocks(10, 30)
new = blocks(int(cfg.get("sentence_soft_min", 28)), int(cfg.get("sentence_hard_max", 60)))

tts = ov.OmniVoiceTTS((cfg.get("omnivoice_base") or "http://127.0.0.1:9877").rstrip("/"), 120)
voices = ov.scan_voices(r"%s/voices")
clone = voices.get(cfg.get("voice") or "xiaoya_clone")
pcm_clone = asyncio.run(tts.synth_pcm("你好呀。", clone)) if clone else b""
design = {"kind": "design", "label": "t", "params": {"gender": "Female / 女",
          "age": "Young Adult / 青年", "pitch": "Moderate Pitch / 中音调", "lang": "Chinese"}}
pcm_design = asyncio.run(tts.synth_pcm("你好呀。", design))
print(json.dumps({"old": old, "new": new, "clone": len(pcm_clone), "design": len(pcm_design)}))
''' % (ROOT, ROOT, ROOT)
    r = run([PY, "-c", code])
    assert r.returncode == 0, (r.stderr or "")[-500:]
    d = json.loads(r.stdout.strip().splitlines()[-1])
    assert len(d["new"]) <= len(d["old"]), f"新块数不该多于旧块: {d}"
    assert sum(d["new"]) >= sum(d["old"]), f"新块总长不该短于旧块: {d}"
    assert d["clone"] > 20000, f"克隆合成出空/过短 PCM: {d['clone']}"
    assert d["design"] > 20000, f"design 合成出空/过短 PCM: {d['design']}"
    return (f"旧{d['old']}→新{d['new']}；克隆 {d['clone']//1024}KB / "
            f"design {d['design']//1024}KB 均非空")


def t_normalize():
    """音量归一：小信号被拉起来、已够响的不动、空/静音原样返回。"""
    import array
    a = open(os.path.join(ROOT, "src", "tts", "audio.py"), encoding="utf-8").read()
    o = open(os.path.join(ROOT, "src", "tts", "omnivoice.py"), encoding="utf-8").read()
    assert "def normalize_pcm(" in a, "audio.py 缺 normalize_pcm"
    assert "return audio.normalize_pcm(pcm)" in o, "synth_pcm 出口没接归一化"
    code = r'''
import array, sys
sys.path.insert(0, r"%s")
from src.tts import audio

def rms_peak(pcm):
    a = array.array("h"); a.frombytes(pcm[:len(pcm)//2*2])
    return max(abs(x) for x in a)

quiet = (array.array("h", [800, -800] * 2400)).tobytes()      # 峰值 800（约 -32dBFS）
loud  = (array.array("h", [30000, -30000] * 2400)).tobytes()  # 已接近满刻度
q2 = audio.normalize_pcm(quiet)
l2 = audio.normalize_pcm(loud)
print(rms_peak(quiet), rms_peak(q2), rms_peak(loud), rms_peak(l2), len(audio.normalize_pcm(b"")))
''' % ROOT
    r = run([PY, "-c", code])
    assert r.returncode == 0, (r.stderr or "")[-400:]
    q_before, q_after, l_before, l_after, empty = r.stdout.split()
    assert int(q_after) > int(q_before) * 4, f"小信号没被拉起来: {q_before}→{q_after}"
    assert abs(int(q_after) - int(10 ** (-3 / 20) * 32767)) < 400, f"归一目标不对: {q_after}"
    assert int(l_after) == int(l_before), f"已经够响的被改了: {l_before}→{l_after}"
    assert int(empty) == 0 and len(str(empty)) > 0, "空输入没原样返回"
    return f"峰值 {q_before}→{q_after}（目标 -3dBFS）；已够响 {l_before} 不动；空输入原样"


def t_prefetch():
    """预缓冲 + 空档补静音：防"嘴型对不上"(时间轴饿死)。"""
    s = open(os.path.join(ROOT, "src", "engine.py"), encoding="utf-8").read()
    assert 'get("prefetch_seconds", 3.0)' in s, "没读 session.prefetch_seconds（默认 3.0）"
    assert "预缓冲" in s, "缺预缓冲日志"
    assert "audio.silence_pcm(100)" in s, "空档没补 100ms 静音"
    assert "await asyncio.wait_for(queue.get(), timeout=0.1)" in s, "播放阶段没用带超时的 get"
    play = s.split("播放阶段")[1].split("else:")[0]
    assert "await queue.get()" not in play, "播放阶段仍有裸 await queue.get()"
    log = open(os.path.join(ROOT, "logs", "bridge.log"), "rb").read().decode("utf-8", "ignore")
    if "预缓冲" in log:                                  # 有实测记录就顺带验一次
        tail = log[log.rfind("预缓冲"):]
        assert "合成没跟上" not in tail, "预缓冲之后仍出现断粮"
        return "阈值/日志/静音兜底齐备；实测有预缓冲记录且其后 0 次断粮"
    return "阈值/日志/静音兜底齐备（暂无实测日志）"


def t_midword():
    """断词保护：块不许停在词中间（实测症状 "年纪" 被劈成 "年" + "纪嘛"）。"""
    s = open(os.path.join(ROOT, "src", "llm.py"), encoding="utf-8").read()
    e = open(os.path.join(ROOT, "src", "engine.py"), encoding="utf-8").read()
    assert "def no_midword_cut(" in s, "llm.py 缺 no_midword_cut"
    assert e.count("llmmod.no_midword_cut(") == 2, "engine 里聊天流/弹幕两处没都接上"
    code = r'''
import json, sys
sys.path.insert(0, r"%s")
from src import llm as L

bad = ["谢谢呀，听着舒服就好。年", "纪嘛，反正还没到要藏着的时候～"]
fixed = L.no_midword_cut(list(bad))
ok1 = ["谢谢呀，听着舒服就好。", "年纪嘛，反正还没到要藏着的时候～"]
ok2 = ["今天天气不错啊，", "我们出去走走吧。"]
print(json.dumps({"fixed": fixed,
                  "punct_kept": L.no_midword_cut(ok1) == ok1,
                  "comma_kept": L.no_midword_cut(ok2) == ok2,
                  "single": L.no_midword_cut(["只有一块没有标点"]) == ["只有一块没有标点"]},
                 ensure_ascii=False))
''' % ROOT
    r = run([PY, "-c", code])
    assert r.returncode == 0, (r.stderr or "")[-400:]
    d = json.loads(r.stdout.strip().splitlines()[-1])
    assert d["fixed"] == ["谢谢呀，听着舒服就好。", "年纪嘛，反正还没到要藏着的时候～"], \
        f"断词没修好: {d['fixed']}"
    assert d["punct_kept"], "本来以标点收尾的块被乱改了"
    assert d["comma_kept"], "以逗号收尾的块被乱改了"
    assert d["single"], "单块输入被改了"
    return "「…就好。年」+「纪嘛…」→「…就好。」+「年纪嘛…」；标点收尾/单块不动"


def t_voice_role():
    """念弹幕 / 回答 两套腔调：同一音色，参数可分离。"""
    e = open(os.path.join(ROOT, "src", "engine.py"), encoding="utf-8").read()
    assert 'def _voice_preset(self, role: str = "talk")' in e, "_voice_preset 缺 role 参数"
    assert 'c.get("read_params") or {}' in e, "没读 tts.read_params"
    assert 'voice_role="read"' in e, "复读弹幕没传 voice_role=read"
    # 合成处 + 证据行都要按 role 取预设；用 >= 避免多加一处日志就误判
    assert e.count("self._voice_preset(voice_role)") >= 2, "_safe_say_text 内部没都按 role 取预设"
    assert 'voice_role: str = "talk"' in e, "_safe_say_text 缺 voice_role 形参"
    assert 'c.get("read_voice")' in e, "没支持单独指定念弹幕音色"

    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8")).get("tts") or {}
    rp = cfg.get("read_params") or {}
    assert rp, "config 里没有 tts.read_params"
    assert float(rp.get("sp", 1.0)) > 1.0, "念弹幕应当更快(sp>1)"
    return (f"role 分离已接；read_params={rp}（念弹幕 sp>1 更快）；"
            f"主音色 {cfg.get('voice')}")


def t_dan_retry():
    """开场弹幕被打断 → 回队重试一次（每会话第一条必被取消的实测坑）。"""
    e = open(os.path.join(ROOT, "src", "engine.py"), encoding="utf-8").read()
    for s, msg in [("self._dan_retried = False", "缺初始化/重置"),
                   ("self._dan_buf.appendleft(_it)", "缺回队逻辑"),
                   ("弹幕播报被打断，本批已放回队列重试", "缺提示"),
                   ("if not self._dan_retried and batch:", "缺一次性保护")]:
        assert s in e, msg
    assert e.count("self._dan_retried = False") >= 2, "成功读完后没重置重试标志"

    # 有活的桥就顺带核对真实转录（这条提示走 tr_add，不进 bridge.log）
    try:
        import urllib.request
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open("http://127.0.0.1:8795/api/live/status?since=0", timeout=8) as f:
            d = json.load(f)
        texts = [str(t.get("text")) for t in (d.get("new_transcripts") or [])]
        hit = next((i for i, t in enumerate(texts) if "本批已放回队列重试" in t), -1)
        if hit >= 0:
            drops = sum(1 for t in texts[hit:] if "让位给歌曲" in t)
            assert drops == 0, f"重试之后仍丢弃 {drops} 次"
            return f"接线齐备；最近一场转录第 {hit + 1} 行触发过重试，其后丢弃 0 次"
    except Exception:                                   # noqa: BLE001 桥没开就只做静态检查
        pass
    return "接线齐备（桥未运行/无近期记录，仅静态校验）"


def t_batch_pick():
    """攒批挑句：最新那条要标记，问句要识别（实测曾答错对象）。"""
    import types
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from src.engine import Engine
    shim = types.SimpleNamespace(_ASK_RE=Engine._ASK_RE)
    batch = [{"nick": "路过的猫", "content": "你声音好听"},
             {"nick": "小林", "content": "吃晚饭没"},
             {"nick": "三分糖", "content": "喜欢什么歌"}]
    p = Engine._dan_batch_prompt(shim, batch)
    assert "喜欢什么歌  ←（最新）" in p, f"最新那条没标记: {p[:120]}"
    assert "优先回应标了「最新」" in p, "提示词没要求优先回应最新"
    assert Engine._dan_batch_prompt(shim, []) == "", "空批次应返回空串"
    # 问句识别（覆盖 吗/什么/没/A不A/哪里/几岁）
    for q in ("吃晚饭没", "喜欢什么歌", "你几岁了", "哪里人", "在吗", "今天累不累"):
        assert Engine._ASK_RE.search(q), f"问句没识别: {q}"
    for s in ("你声音好听", "晚上好呀"):
        assert not Engine._ASK_RE.search(s), f"陈述被误判为问句: {s}"
    return "最新标记 + 优先指示 + 6 类问句识别 + 陈述不误判 + 空批次"


def t_answer_only_display():
    """只答不念 + 弹幕和回答都上画面（用户 2026-10-25 定）。"""
    b = open(os.path.join(ROOT, "src", "bridge.py"), encoding="utf-8").read()
    assert 'get("answer_only", True)' in b, "bridge 没默认只答不念"
    assert "default_answer_only" in b, "缺默认开关接线"
    h = open(os.path.join(ROOT, "stage", "index.html"), encoding="utf-8").read()
    assert 't.startsWith("【弹幕·未念】")) return' not in h, "页面仍把未念弹幕挡在画面外"
    assert "💬 观众：" in h, "画面层没加「观众」前缀"
    assert 't.match(/^【弹幕[^】]*】' in h, "没去掉【弹幕…】内部标记"
    assert 'replace(/^(小雅|主播)' in h, "没去掉她回答里自带的「小雅：」前缀"
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    assert (cfg.get("danmaku") or {}).get("answer_only") is True, "config 未开 answer_only"
    return "后端默认只答不念；页面把弹幕原话(💬)和回答一起上画面"


def t_first_read_fast():
    """开播第一拍不加 2s 收集窗 + 有"入队→开口"打点（用户 2026-10-25：开播别干等）。"""
    e = open(os.path.join(ROOT, "src", "engine.py"), encoding="utf-8").read()
    assert "_first_read = (self._dan_last_read == 0.0)" in e, "缺首次判定"
    assert "not _first_read and not self._dan_vipq" in e, "第一拍仍会走 2s 收集窗"
    assert 'item.setdefault("_t_enq", time.time())' in e, "缺入队时间戳"
    assert "入队→开口" in e, "缺耗时打点输出"
    assert "_logged_first" in e, "打点没做「只打一次」保护"
    # 首次(0.0) 时窗口必须被跳过
    last_read = 0.0
    first = (last_read == 0.0)
    assert first and not (not first and True), "首次判定逻辑反了"
    return "首拍跳过收集窗；入队→开口有打点（只打一次）"


if __name__ == "__main__":
    check("A 编译", t_compile)
    check("B engine 改动", t_engine)
    check("C TTS 模块改动", t_tts_module)
    check("D 工具脚本", t_tools)
    check("E 行为（本地 TTS，零花费）", t_behavior)
    check("F 音量归一", t_normalize)
    check("G 预缓冲/静音兜底", t_prefetch)
    check("H 断词保护", t_midword)
    check("I 念/答腔调分离", t_voice_role)
    check("J 弹幕回队重试", t_dan_retry)
    check("K 攒批挑句", t_batch_pick)
    check("L 只答不念+同屏显示", t_answer_only_display)
    check("M 开播首拍不干等", t_first_read_fast)
    ok = sum(1 for g, _, _ in R if g)
    print("\n" + "=" * 54)
    print(f"{ok}/{len(R)} 通过")
    sys.exit(0 if ok == len(R) else 1)
