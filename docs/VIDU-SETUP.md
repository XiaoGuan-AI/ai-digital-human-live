# Vidu 接入步骤（拿 api_key + avatar_id）

> 核对时间：2026-10-25，来源：platform.vidu.cn「产品价格」「Vidu S2 数字人」「创建与管理主体库」文档页（Playwright 渲染后抓取）。
> 价格与邀请码属活动信息，**以你登录后控制台显示为准**。

## 0. 先说钱（重要）

| 项 | 数值 |
|---|---|
| 积分单价（标准） | **1 积分 = ¥0.03125**（100 元 = 3,200 积分） |
| S2 数字人消耗 | 上游 README：**1 积分/秒** |
| 折算 | **¥1.875/分钟 ≈ ¥112.5/小时 ≈ ¥2,700/天** |
| 限时套餐 | 69 元 → 3,154 积分（≈0.0219 元/积分，约 52 分钟）；350 元 → 16,000 积分（约 4.4 小时）；700 元 → 32,000（约 8.9 小时） |
| **白嫖** | ~~文档页邀请码 KD2UQ5PWQK（5000 积分）~~ **已领完失效**；改走「积分申请 / 完善信息 / 商务咨询」，见第 2 节 |

> 结论：24 小时连播在标价下约 ¥2,700/天，**不现实**。路径建议：先走「积分申请/完善信息」争取免费额度；
> 拿不到就花 69 元买 52 分钟做**一次性效果验证 + 录 demo**，确认值得后再按小时买（4 小时/天 ≈ ¥450）。

## 1. 注册与实名

1. 打开 https://platform.vidu.cn ，右上角「开始接入 / 登录」
2. 手机号注册 → 进入**控制台**
3. 按提示完成实名（企业/个人），否则可能无法充值或调用

## 2. 免费积分入口（邀请码已失效，2026-10-25 实测）

`KD2UQ5PWQK` 与 `RG4JO9HIAQ` **都已领完**（文档页仍挂着，但实际提交报「邀请码使用次数超过限制」）。
文档站全站扫描后，剩余免费额度入口只有这三条，且都要登录：

| 入口 | 路径 | 说明 |
|---|---|---|
| **积分申请** | 页脚「积分申请」→ 登录后 `/retention` | 官方申请表单，按需审批 |
| **完善信息赢积分** | 文档页顶部横幅「开始填写」→ 控制台 | 填真实企业/个人信息后发放 |
| **商务/售前咨询** | `platform@vidu.cn` · 17813706491 | 可谈试用额度（企业口径） |

若都拿不到，最低成本验证方案：**69 元入门包 = 3,154 积分 ≈ 52 分钟**（限时 −30%）。

## 3. 拿 API Key（`vda_...`）

1. 控制台 → **API 密钥**（有的版本叫「密钥管理 / API Keys」）
2. 新建密钥 → 复制，形如 `vda_xxxxxxxxxxxx`
3. **只显示一次**，立刻存好

填进项目配置：

```json
"vidu": { "api_key": "vda_xxxx..." }
```

## 4. 建形象 → 拿 `avatar_id`（2026-10-25 实测修正）

⚠️ **关键：`/ent/v2/subjects` 建的不是直播形象。** 它建的是"图像/视频生成用的主体"，
拿它的 id 去开播会报 `404 avatar_id not found`。直播形象在**另一个接口**：`/live/v1/avatars`。

正确流程（两步）：

```bash
# 第 1 步：先把图片传上去，拿到一个 image_uri
#   最简单：用 /ent/v2/subjects 建一个主体，它返回的 images[0] 就是可用的 image_uri
curl -X POST 'https://api.vidu.cn/ent/v2/subjects' \
  -H 'Authorization: Token vda_xxx' -H 'Content-Type: application/json' \
  -d '{"name":"xiaoya-main","images":["data:image/png;base64,<b64>"],"videos":[],"voice_id":""}'
# → {"id":"101183812...","images":["https://prod-ss-vidu.s3.../prompt-01.jpeg?..."], "credits":5}

# 第 2 步：用 image_uri 建【直播形象】
curl -X POST 'https://api.vidu.cn/live/v1/avatars' \
  -H 'Authorization: Token vda_xxx' -H 'Content-Type: application/json' \
  -d '{"image_uri":"https://prod-ss-vidu.s3.../prompt-01.jpeg?..."}'
# → {"id":"1011839163005145088", "status":"processing", "image_uri":".../avatar/<id>/avatar.jpg?..."}
```

- 这个 `id` 才是填进 `config.json → avatar.avatar_id` 的值
- 状态 `processing` → `success` 约 **5 秒**（轮询 `GET /live/v1/avatars/{id}`）
- **建形象本身不额外扣积分**（实测：建主体 5 积分，建直播形象 0）
- ⚠️ 不要给它传 `data:image/...;base64,`——会报
  `failed to hash avatar image`；`image` / `images` / `avatar_image` 这些字段名也都报同一个错，
  **只认 `image_uri`（必须是 http(s) URL）**

### 一条命令搞定（已脚本化）

```bat
.venv\Scripts\python.exe tools\create_subject.py --image <图片路径> --name xiaoya-main
```

它会建主体 → 拿 image_uri → 建直播形象 → 轮询到 success → 直接把 avatar_id 写进 config.json。

## 4.5 一分钟试播（确认效果再决定）

```bat
:: 1) 起 TTS（WSL，18780）+ 桥（8795）
:: 2) 计费闸门：60 秒预算，到点自动停止
.venv\Scripts\python.exe tools\cost_guard.py --budget-min 1 --interval 1
:: 3) 浏览器开 http://127.0.0.1:8795/stage，然后
.venv\Scripts\python.exe -c "import httpx;print(httpx.post('http://127.0.0.1:8795/api/live/start',json={},trust_env=False,timeout=120).text)"
```

2026-10-25 实测：计时到 01:00 → 自动停止 → Vidu 记 `billed_seconds=54, credits_cost=54`（≈¥1.69）。
**看门狗按上限计（60）比实际（54）多算，方向是安全的。**

填进配置：

```json
"avatar": { "avatar_id": "1008580988239962112", "name": "xiaoya" }
```

## 5. 动作库 `library_id`（可选）

- 不建就填 `"0"`，用平台默认动作库
- 想做「比心 / 拿墨镜 / 换装」这类，在控制台建**动作库/主体库**，把库 id 填：

```json
"action": { "enabled": true, "library_id": "0" }
```

舞台页「🕹 快捷指令」里的动作要有对应库支持，否则点了没反应。

## 6. 自检（不花冤枉钱）

```bat
cd D:\Projects\ai-digital-human-live
.venv\Scripts\python.exe tools\verify_stack.py
```

- 「配置完整度」从「仅缺 Vidu 凭据」变为「全部配置就绪」= 可以开播
- 余额必须 **≥45 积分**，否则开不了场
- ⚠️ **点「开始连线」即开始按秒计费**；只起桥、不连线 = 0 元

## 7. 填完之后

把 `api_key` 和 `avatar_id` 给我（或自己填好告诉我），我会做：
1. 建/校验主体 → 落 `avatar_id`
2. 连通 S2 → 画面出在舞台页
3. 接弹幕 + LLM + edge TTS（已就绪）→ 跑一轮真实互动
4. 接推流（OBS 或 `push_rtmp.py --window-match AI 主播`）→ 本机 RTMP 先验，再对抖音
