# 本地适配说明（ai-digital-human-live 二次适配）

> 上游：https://github.com/ai-digital-human-live/ai-digital-human-live （AGPL-3.0，作者：）
> 本文件只记录**我们机器上为了让它在没有 OmniVoice / 有 Clash 代理 / 有 PYTHONPATH 污染的环境下跑起来**所做的改动。

## 一、跑起来了什么

| 组件 | 端口 | 状态 | 说明 |
|---|---|---|---|
| 桥 + 舞台页 | **8795** | ✅ | `python -m src.main`，`/stage` 200 |
| edge-tts 服务（替代 OmniVoice） | **18780** | ✅ | WSL 内跑，`/healthz` 返回 ok |
| 弹幕转发 | — | ✅ | `tools/douyin_relay.py` → `POST /api/dmcmd` 链路通 |
| LLM | — | ✅ | DeepSeek `deepseek-flash`，实测回复正常 |

## 二、改了什么（4 处，都可回滚）

| 文件 | 改动 | 原因 |
|---|---|---|
| `src/tts/edge_local.py` | **新增**：EdgeTTS 适配类（`synth_pcm` / `active_base`） | 上游只实现 OmniVoice（gradio_client 调 :9877）；OmniVoice 要 ~11GB 显存，edge-tts 零显存 |
| `src/engine.py` | `tts.engine == "edge"` 时用 EdgeTTS，否则仍 OmniVoice | 保留上游默认行为，只在我们这台机器切 |
| `src/llm.py` | `max_tokens` 用 `int(str(x or 300).strip() or 300)` | 上游模板 `"max_tokens": ""` 会让 `int("")` 崩溃 |
| `tools/douyin_relay.py` | `httpx(trust_env=False)` + `websockets.connect(proxy=None)` | websockets≥15 自动读代理变量，Clash 把 127.0.0.1 的 WS 握手也接管 → 服务端回 400 |

新增文件：`tools/edge_tts_server.py`（WSL 侧 HTTP TTS）、`tools/run_bridge.cmd`、`tools/run_tts.cmd`、
`tools/wsl_stop_tts.sh`、`tools/wait_port.py`、`start-stage.cmd`、`stop-stage.cmd`、`tools/verify_stack.py`。

## 三、踩过的坑（都会导致「看着正常其实不通」）

1. **PYTHONPATH 污染**：Hermes 把 `...\hermes-agent\venv\site-packages` 塞进 PYTHONPATH，
   子进程 import 到 Hermes 的 pydantic/websockets → `pydantic_core` 加载失败 / WS 握手 400。
   → 所有 `.cmd` 用 `set "PYTHONPATH="`（**带引号**；`set X= &&` 会把值设成一个空格，python 直接崩）。
2. **Clash 接管本地请求**：`httpx` / `websockets` 都会读 `HTTP_PROXY`，127.0.0.1 也被塞进代理 →
   `400 The plain HTTP request was sent to HTTPS port` / `InvalidStatus 400`。→ `trust_env=False`、`proxy=None`。
3. **多进程抢同一端口**：`SO_REUSEADDR` 在 Windows 允许两个进程同时 bind，连接被随机分配 → −10054 断流。
   → 用 `SO_EXCLUSIVEADDRUSE`（本项目 TTS 服务不涉及，但同类问题在数字人链路上踩过）。
4. **`.cmd` 里 `$(...)` 会被 cmd 吃掉**：WSL 循环写进 `.sh` 文件再 `wsl bash /path/x.sh` 调用。

## 四、还差什么才能真开播

| 项 | 现状 | 需要你做的 |
|---|---|---|
| **Vidu API Key** | 空 → 点「开始连线」会 401 | platform.vidu.cn 注册充值，余额 ≥45 积分，生成 `vda_...` 填 `config.json → vidu.api_key` |
| **形象 avatar_id** | 空 | Vidu 控制台建形象（上传正脸照/视频），把 id 填 `config.json → avatar.avatar_id` |
| **动作库 library_id** | `"0"`（平台默认库） | 想有「比心/戴墨镜」这类动作，自己在控制台建库，填 `action.library_id` |
| 推流到平台 | 未接 | 用场镜页 + OBS/直播伴侣；或复用 ai-live-anchor 的 `tools/push_rtmp.py` 抓舞台窗推 RTMP |

> ⚠️ **计费点**：点「开始连线」即开始按秒计费（Vidu 1 积分/秒）。只起桥、不连线 = 0 元。

## 五、一键启停

```bat
start-stage.cmd     :: 起 TTS(18780) + 桥(8795) + 打开舞台页
stop-stage.cmd      :: 全停（含 WSL 内 TTS 进程）
```

## 六、验收

```bat
.venv\Scripts\python.exe tools\verify_stack.py
```
检查：端口 8795/18780、`/stage` 200、TTS 合成出 PCM、LLM 返回非空、桥状态 idle（未计费）。
