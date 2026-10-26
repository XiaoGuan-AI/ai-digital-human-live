# 项目总览（唯一技术路线）

> 更新：2026-10-25。**本文件是方向性约定，动代码前先读这里。**

## 一句话

只做一件事：用 **开源直播方案**（`ai-digital-human-live/ai-digital-human-live`）做数字人直播。
渲染在 Vidu 云端（S2），本机只负责舞台页 / LLM / TTS / 弹幕 / 计费闸门。

## 不再做什么（2026-10-25 已彻底删除）

| 已删除 | 为什么删 |
|---|---|
| `LiveStream` + `LiveTalking` + MuseTalk（本地换嘴） | 换嘴方案天花板低：下颌/托腮的手会被重绘、脸偏软；且要自己做动作帧序列补手部动作 |
| `ai-live-anchor`（自研导演层 + douyinLive + 推流窗口抓取） | 自拼方案，维护成本高、被现成方案覆盖 |
| MediaMTX / RTMP 中转 / OBS 抓窗口 | 本方案不需要：Vidu 直接把画面推给 RTC，舞台页订阅 |
| MuseTalk / wav2lip 权重、动作帧素材 | 随上面一起删 |
| edge-tts 替代 TTS | 播音腔、不自然；改用项目原版 **OmniVoice** |

**不要再引入上面任何一项**，也不要在本项目里"再拼一套"。

## 目录结构（所有相关文件都在本项目内）

```
D:\Projects\ai-digital-human-live\
├─ src\                 桥（FastAPI :8795）、引擎、LLM、TTS 适配层
├─ stage\index.html     舞台页（浏览器打开 http://127.0.0.1:8795/stage）
├─ config.json          唯一配置（vidu.api_key / avatar.avatar_id / tts.engine / llm）
├─ tools\               本项目工具（见下）
├─ docs\                文档（VIDU-SETUP.md、PLATFORM-COMPARISON.md、本文件）
├─ omnivoice-src\       OmniVoice 源码（TTS 模型工程，从 k2-fsa/OmniVoice 浅克隆）
├─ models\              OmniVoice 模型权重（放这里，不放 WSL /root、不放 C 盘）
├─ wheels\              离线 wheel（torch 2.8+cu128 等大件，断网也能重装）
├─ logs\                运行日志（bridge.log / cost_guard.log）
├─ shots\               舞台页截图取证
├─ .edge-profile\       带 --remote-debugging-port 的 Edge 专用配置目录
└─ audio\               点播/上传音频
```

> WSL 里 `/root` 只允许放**临时**东西；模型权重、源码、wheel、日志一律进本项目目录，
> 通过 `/mnt/d/Projects/ai-digital-human-live/...` 访问。

## 工具（tools/）

| 工具 | 作用 | 关键点 |
|---|---|---|
| `cost_guard.py` | **计费闸门**：只在 phase=live 时计时，到预算强制 `/api/live/stop` | Vidu 1 积分/秒，忘了关就是 ¥112.5/小时 |
| `create_subject.py` | 建形象：主体(`/ent/v2/subjects`) → 取 `image_uri` → 直播形象(`/live/v1/avatars`) → 写 `avatar_id` | **subjects ≠ 直播形象**，直接拿 subject id 开播会 404 |
| `stage_click.py` | 用舞台页自己的「开始连线」按钮开会话，并校验 `video.srcObject`/`videoWidth` | 用 API 开会话页面不会挂视频 → 用户"看不到画面" |
| `verify_cost_guard.py` | 计费闸门回归测试 4/4 | 假桥模拟 live，验证到预算自动停 |
| `start-vidu.cmd` | 一键：检查凭据 → 起桥 → 开舞台页 → 起计费闸门 | 缺凭据会明确报缺哪两项 |

## 必须知道的坑

1. **权重必须 sha256 校验，只看大小不够**（2026-10-25 实际踩过）。
   aria2 分段 + curl 续传混用会把 `model.safetensors` 拼成"大小完全正确、内容错位"的文件：
   模型能加载、不报错，但 TTS 输出**噪声**（听起来像电流声，听不清一个字）。
   一条命令定性：`.venv\Scripts\python.exe tools\verify_model.py`（3 个大文件全 ✅ 才算好）。
   下载只走**单流 curl + `-C -` 续传**，不要和 aria2 混用。
2. **舞台页刷新 = 重建会话 = 重新计费**。只开一个舞台页，别按 F5；多开几个页面会互相踢（旧会话 reason=reconnect）。
3. **重影**有两种，先分清：
   - **假重影（最常见）**：同一个舞台页开了**两个浏览器窗口**（比如主 Edge 窗口里还留着一个标签 + 另开一个 app 窗口），
     两个窗口叠在一起就是"一大一小两份画面、标题出现两次"。
     一条命令查：`.venv\Scripts\python.exe tools\stage_click.py --status` → 会打印 `窗口数`，>1 就关掉多余的。
   - **真叠层**：页面把「未连线底图 `#avatarStill`」和 `video` 叠在同一个 665×765 盒子里。
     已在 `poll()` 里加守卫：只要 `phase=live` 就强制隐藏底图。
4. **开始连线必须点页面按钮**（或用 `tools/stage_click.py`）；用 `/api/live/start` 开会话页面**不会挂视频**，表现为"桥说 live、页面没画面"。
5. 建形象只认 `image_uri`（必须是 http(s) URL 或 data URL，走 `tools/create_live_avatar.py`）；
   **形象原图必须是干净单人像**：不能带水印、不能是"画中画/套娃"截图。
   2026-10-25 踩过：原形象图（704×896）本身就是一张带水印的嵌套截图，Vidu 忠实渲染 →
   直播画面里的人一大一小"套娃"，查了半天以为是页面/双流问题，实际是源图脏。
   一条命令自查源图：`.venv\Scripts\python.exe tools\ask_vision.py shots\_avatar_source.jpg "图里有几个人？有嵌套小窗或水印吗？"`
6. 所有本地/国内请求一律 `trust_env=False` 或 `--noproxy '*'`，否则 Clash 会把 127.0.0.1 和 api.vidu.cn 一起劫走。
7. 大文件下载：**单流 curl + `-C -` 续传**最稳（hf-mirror 实测 1.2→10 MB/s；aria2 多连接反而被限速到几百 KB）；
   torch 走 `download.pytorch.org/whl/cu128/` 的 `manylinux_2_28` 文件名（阿里云镜像目录页没有直链）。

## TTS：用项目原版 OmniVoice

- 项目默认 `tts.engine = "omnivoice"`，走 **gradio 客户端**调 `omnivoice-demo` 的 `/_clone_fn`、`/_design_fn`。
- 服务端口 **9877**（`config.tts.omnivoice_base`），启动：
  `wsl -d Ubuntu-24.04 bash -lc '/root/omnivoice-venv/bin/omnivoice-demo --model /mnt/d/Projects/ai-digital-human-live/models/OmniVoice --ip 0.0.0.0 --port 9877 --no-asr'`
- 音色来自 `tts.voices_dir` 下每个子目录：
  | 目录内容 | 类型 | 说明 |
  |---|---|---|
  | `design.json` | 设计音色 | 用性别/年龄/音调/方言等枚举"设计"一把嗓子，无需录音 |
  | `ref_audio.*` + `omnivoice.txt` | **克隆音色** | 用 3~10 秒真人录音克隆，最像真人 |
- 现有音色：
  - `voices/xiaoya` — design 模式（自然女声，通用）
  - `voices/xiaoya_clone` — **克隆模式**：参考音频取自 `assets/demo-sound.mp4` 原声（6.0 秒），
    自动转写为「她说路远也别怕天亮了就有光。」→ 这就是"机车女生"那把嗓子，**直播用它**。
- 造克隆音色：`.venv\Scripts\python.exe tools\verify_clone.py` 会自检通路；
  实际生产用 `wsl ... /root/omnivoice-venv/bin/python tools/clone_voice.py --ref <录音> --name <名字>`。
- 显存约 4GB（本机实测），首次合成 2~3 秒延迟，之后 RTF 0.6~0.7。
- **交付试听一定用 MP3**：24kHz 单声道 WAV 在聊天内嵌播放器/部分播放器会被播成"杂音"，
  同一份音频转 `-ar 44100 -ac 2` 的 MP3 就正常（2026-10-25 踩过，别再让用户怀疑是 TTS 坏了）。
