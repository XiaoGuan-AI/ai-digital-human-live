# tools/legacy — 已废弃的验收脚本（保留存档，不参与 verify_all）

这些脚本针对的是**已删除**的技术栈，留着只为回溯历史，不要指望能跑绿。

| 脚本 | 为什么废弃 |
|---|---|
| `verify_adapt.py` | 测 `D:\Projects\ai-live`（已删）、`mock_server.py`（已删）、edge-tts 服务端口 18780（已换成 OmniVoice 9877）。2026-10-25 从 `tools/` 移出。 |

## 现状对应的替代

| 老检查 | 现在的去处 |
|---|---|
| 端口/TTS/舞台页/LLM/计费 | `tools/verify_stack.py`（已改为读 `config.json`，不再硬编码端口） |
| 语音管线（分句/音量/预缓冲/断词/腔调/弹幕重试） | `tools/verify_sentence.py`（A–J，10 项） |
| 模型权重要求和克隆通路 | `tools/verify_model.py`、`tools/verify_tts.py`、`tools/verify_clone.py` |

## 恢复某个脚本前先确认

1. 它引用的文件/端口今天是否仍然存在；
2. 是否需要真实计费（`verify_action_scheduler.py` 这类要交互确认，非交互环境会 SKIP）。
