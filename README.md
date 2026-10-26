# AI 数字人直播助手 · 本地全链路

一套**能真开播**的 AI 数字人直播方案：数字人出镜、实时读弹幕、开口答观众、嘴型同步，
支持自定义形象与音色克隆，本地跑语音、云端跑渲染，成本可控。

> 技术支持 / 部署咨询：**QQ 1909561302**

![直播画面](assets/live-on-douyin.jpg)

---

## 这套东西能做什么

| 能力 | 说明 |
|---|---|
| 数字人出镜 | 上传一张干净单人肖像，云端渲染成可实时驱动的数字人 |
| 读弹幕 + 回答 | 弹幕进队列，攒批挑选问题，LLM 生成回答，TTS 说话，画面同步出字幕 |
| 只答不念 / 念了再答 | 两种模式可切（`danmaku.answer_only`） |
| 音色克隆 | 本地 OmniVoice 克隆，一段 4 秒参考音即可，支持念/答两套语速 |
| 嘴型同步 | 预缓冲 + 空档补静音，避免"画面在动、嘴不动" |
| 同屏字幕 | 弹幕原话（💬 观众：…）和主播回答一起显示在画面里，推流可见 |
| 成本闸门 | `cost_guard.py` 按时长兜底，到点自动停播，防止忘关烧钱 |

## 架构

```
抖音/视频号 ──弹幕──> 本地桥(8795, FastAPI) ──> LLM 生成回答
                          │                        │
                          │                        └─> 本地 TTS(WSL, 9877) → PCM
                          │                                                 │
                          └──────────── 音频帧/字幕 ────────────────────────┘
                                                     │
                                          云端渲染(WebRTC) ──> 舞台页(9334) ──OBS──> 直播平台
```

四件套：**本地桥**（业务/排队/推音频）、**本地 TTS**（音色克隆）、**舞台页**（订阅画面、上字幕）、**计费看门狗**。

## 快速开始

### 1. 环境

- Windows 10/11 + Python 3.11（建议独立 venv）
- WSL2（Ubuntu 24.04）用于跑 OmniVoice TTS，NVIDIA 显卡 8G 显存以上
- Microsoft Edge（舞台页用 `--app` 模式）

### 2. 装依赖

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.json config.json    # 然后填入你自己的 key
```

`config.json` 至少填两处：
- `vidu.api_key`：云端渲染平台 API Key
- `llm.key_file`：DeepSeek（或任意 OpenAI 兼容服务）的 key 文件路径

### 3. 启动

```bash
tools\start-vidu.cmd      # 拉起全部（TTS 服务 + 本地桥 + 舞台页）
tools\stop-vidu.cmd       # 全部停止
```

开播：在舞台页点「**开始连线**」，再点一下画面打开声音（默认静音）。

### 4. 验收（不花钱，先跑这个）

```bash
.venv\Scripts\python.exe tools\verify_all.py
```

全部通过再谈开播。语音/弹幕链路的 13 项细验收：

```bash
.venv\Scripts\python.exe tools\verify_sentence.py
```

### 5. 开播（带成本闸门）

```bash
.venv\Scripts\python.exe tools\cost_guard.py --budget-min 5
```

> ⚠️ **路径说明**：`tools\start-vidu.cmd` 等脚本默认项目在 `D:\Projects\ai-digital-human-live`。
> 放到别的盘/目录时，把脚本里的这个路径批量替换成你的实际路径即可（WSL 侧对应 `/mnt/<盘符>/...`）。

到点自动停，实测 1 分钟约 ¥1.88（云端渲染单价 ¥0.03125/秒）。

### 6. 喂弹幕

```python
import httpx
c = httpx.Client(trust_env=False)      # 本地请求要绕代理
c.post("http://127.0.0.1:8795/api/danmaku",
       json={"nick": "小林", "text": "你几岁啦", "content": "你几岁啦", "platform": "douyin"})
```

> ⚠️ 别用 curl 传中文（会编码坏），用 httpx 的 `json=`。

## 实测数据（省时间的部分）

| 指标 | 实测值 |
|---|---|
| 弹幕 → 开口 | **约 10 秒**（LLM 2 秒 + TTS 8 秒），瓶颈在 TTS |
| 单条回答音频 | 3–5 秒（一句话策略） |
| 1 分钟直播成本 | ¥1.88 |
| 读弹幕/回答腔调 | 念得快 25%、起伏小；回答正常语速 |

想进一步压开口时间，换更快的 TTS（如 CosyVoice2 级别，单次约 1 秒）。

## 五个坑（我们都踩过）

1. **画面套娃/重影**：形象源图本身带画中画或水印会被忠实渲染 → 用干净单人像；另外别同时开两个舞台页窗口。
2. **声音像说唱**：克隆用的参考音本身拖腔（基音乱跳）会被一起学走 → 换正常朗读的 4 秒语料。
3. **嘴型对不上**：播放队列空转不发音频帧 → 已内置 3 秒预缓冲 + 空档补静音。
4. **开播半天不说话**：TTS 预热没真正跑（函数只调用未定义，异常被吞）→ 已改为桥启动时预热。
5. **第一条弹幕被吞**：会话刚就绪时的抢占会取消首条 → 已内置"回队重试一次"。

## 目录

```
src/            本地桥、渲染引擎、弹幕路由、LLM、TTS 适配
stage/          舞台页（订阅画面、字幕覆盖层、操作面板）
tools/          启动/停止、计费看门狗、验收脚本、诊断工具
docs/           技术路线、平台比价、部署说明
config.example.json   配置模板（无密钥）
```

## 合规与许可

- 本项目基于开源项目 [cyber-xiaoya-live](https://github.com/cyber-xiaoya/cyber-xiaoya-live)（AGPL-3.0）修改而来，
  **按 AGPL-3.0 要求保留原许可证与来源说明**，见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
- 使用数字人形象、声音素材请确保**已获授权**（自有肖像或商用授权），并遵守直播平台的数字人相关规范。
- 本项目提供的是**技术方案与部署服务**，不承诺任何收益。

---

**需要远程部署 / 调优 / 推流联调？** 加 **QQ 1909561302**（备注：数字人）。
