# Vireal Web/H5 技术方案 v1.0

更新时间：2026-09-09  
状态：开发基线（尚未进行真实付费模型调用）

## 1. 技术结论

当前需求可以使用阿里云 Model Studio 新加坡区落地，模型路由如下：

| 场景 | 输入 | 模型 | 时长 | 音频 | 首期状态 |
|---|---|---|---|---|---|
| 拥抱 | 2 张独立单人全身照 | `wan2.7-r2v-2026-06-12` | 5/10/15 秒 | 模型生成环境声 | 开放，需 PoC 验收 |
| 牵手 | 2 张独立单人全身照 | `wan2.7-r2v-2026-06-12` | 5/10/15 秒 | 模型生成环境声 | 开放，需 PoC 验收 |
| 亲吻 | 2 张独立单人全身照 | `wan2.7-r2v-2026-06-12` | 5/10/15 秒 | 模型生成环境声 | 功能开关默认关闭 |
| 跳舞 | 1 张单人全身照 + 固定动作视频 | `wan2.2-animate-move` / `wan-std` | 由 5/10/15 秒动作视频决定 | 跟随动作视频 | 开放，需 PoC 验收 |
| 俯卧撑 | 1 张单人全身照 + 固定动作视频 | `wan2.2-animate-move` / `wan-std` | 由 5/10/15 秒动作视频决定 | 跟随动作视频 | 开放，需 PoC 验收 |

R2V 的具体 API 参数页规定：只含图片参考时 `duration` 可取 2–15 秒；含参考视频时只能取 2–10 秒。因此本产品双人两图路径无需续写。Model Studio 的模型总览仍显示 R2V 为 2–10 秒，两个官方页面存在口径差异；15 秒必须纳入上线前真实请求验收，并保留后台关闭该时长的开关。

官方依据：

- [Wan Reference-to-Video API](https://www.alibabacloud.com/help/en/model-studio/wan-video-to-video-api-reference)
- [Wan Image-to-Action API](https://www.alibabacloud.com/help/en/model-studio/wan-animate-move-api)
- [Video generation overview](https://www.alibabacloud.com/help/en/model-studio/use-video-generation)
- [Model Studio pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing)

## 2. 总体架构

```mermaid
flowchart LR
    H5[Web/H5] --> API[FastAPI]
    API --> DB[(PostgreSQL)]
    API --> OSS[(Private OSS Singapore)]
    API --> Q[Task Queue / Outbox]
    Q --> W[Generation Worker]
    W --> MS[Model Studio Singapore]
    W --> OSS
    P[Task Poller] --> MS
    P --> DB
    P --> OSS
    PAY[PayPal Orders v2] --> WH[Verified Webhook]
    WH --> DB
```

部署建议：H5、API、Worker、PostgreSQL、Redis/队列和 OSS 均选择新加坡。Model Studio International 的静态数据归属新加坡，但推理算力可能在中国大陆以外动态调度；隐私声明应描述为“存储在新加坡、推理在阿里云国际服务范围内处理”，不要承诺推理只发生在新加坡。

## 3. 外部接口封装

### 3.1 双人 R2V

- 创建：`POST https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis`
- 查询：`GET https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/tasks/{task_id}`
- 必需请求头：`Authorization: Bearer ...`、`X-DashScope-Async: enable`。
- `media` 中两项均为 `reference_image`，提示词必须用 `Image 1`、`Image 2` 对应人物顺序。
- 固定 `resolution=720P`、`ratio=9:16`、`prompt_extend=true`；水印策略由合规评估决定，不由前端传入。
- 单张人物参考图只能包含一个人物；格式、尺寸和大小在上传阶段按官方限制预校验。

### 3.2 单人动作迁移

- 创建：`POST https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/services/aigc/image2video/video-synthesis`
- 查询：与 R2V 共用 `/api/v1/tasks/{task_id}`。
- `image_url` 是用户全身照，`video_url` 是平台预置并已获音乐/动作授权的模板视频。
- 首期固定 `mode=wan-std`，输出为 720P、15 fps；动作模板分别制作 5/10/15 秒版本。
- 输入视频有音频时输出保留音频；没有音频时输出静音。不得在生成后临时拼接未经授权的音乐。

### 3.3 异步任务

任务 ID 和结果 URL 都只保证 24 小时有效。Poller 按官方建议约每 15 秒查询一次：

`PENDING → RUNNING → SUCCEEDED | FAILED | CANCELED | UNKNOWN`

成功后由 Worker 立即下载临时结果并写入私有 OSS；客户端永远不直接访问 Model Studio 临时 URL，也不接触 API Key。

## 4. 业务 API 草案

| 方法 | 路径 | 用途 | 关键约束 |
|---|---|---|---|
| `GET` | `/api/v1/app/video-templates` | 获取模板、支持时长和金币 | 由服务端配置决定，不信任前端价格 |
| `POST` | `/api/v1/app/uploads/presign` | 获取私有 OSS 上传凭证 | 限图片类型、大小、用户目录和短时效 |
| `POST` | `/api/v1/app/generations` | 创建生成任务 | `Idempotency-Key` 必填；原子扣币 |
| `GET` | `/api/v1/app/generations/{id}` | 查询自己的任务 | 只能读取本人数据 |
| `GET` | `/api/v1/app/works` | 作品记录 | 仅本人；含处理中和失败任务 |
| `GET` | `/api/v1/app/works/{id}/play-url` | 获取短期播放地址 | OSS 签名 URL，不返回对象内部路径 |
| `GET` | `/api/v1/app/works/{id}/download-url` | 获取短期下载地址 | `Content-Disposition: attachment` |
| `DELETE` | `/api/v1/app/works/{id}` | 删除作品 | 立即不可访问，最迟 24 小时物理清除 |
| `GET` | `/api/v1/app/wallet` | 余额与最近流水 | 余额来自账本汇总或锁定行 |
| `POST` | `/api/v1/app/paypal/orders` | 创建 PayPal 金币订单 | 服务端写死商品和美元金额 |
| `POST` | `/api/v1/app/paypal/orders/{id}/capture` | 用户批准后捕获 | 捕获完成仍需幂等入账 |
| `POST` | `/api/v1/webhooks/paypal` | PayPal 事件 | 必须验证签名、事件 ID 去重 |

## 5. 数据模型增量

在现有 `AppUser`、`AppOrder` 基础上新增：

| 表 | 关键字段 | 唯一性/索引 |
|---|---|---|
| `app_auth_identity` | `app_user_id, provider, provider_subject, email` | `(provider, provider_subject)` 唯一 |
| `video_template` | `slug, subject_count, model, prompt_version, enabled` | `slug` 唯一 |
| `video_template_variant` | `template_id, duration, coin_cost, action_asset_key` | `(template_id, duration)` 唯一 |
| `wallet` | `app_user_id, balance, version` | `app_user_id` 唯一；乐观锁或行锁 |
| `coin_ledger` | `app_user_id, amount, type, business_key` | `business_key` 唯一 |
| `generation_task` | `template_id, duration, status, provider_task_id, debit_ledger_id, refund_ledger_id` | `(app_user_id, idempotency_key)` 唯一；`provider_task_id` 唯一 |
| `generation_asset` | `task_id, kind, oss_key, status, purge_after, purged_at` | `purge_after` 索引 |
| `consent_event` | `app_user_id, task_id, policy_version, accepted_at, ip_country` | `task_id` 索引 |
| `paypal_webhook_event` | `event_id, event_type, payload_hash, processed_at` | `event_id` 唯一 |
| `complaint_case` | `reporter, work_id, reason, status, audit_snapshot` | `work_id, status` 索引 |

不保存身份证或活体认证材料。用于追溯的同意记录、任务元数据、输入/输出哈希和投诉处理记录保留 180 天；媒体本体最多 24 小时。

## 6. 生成事务与幂等

1. 服务端验证登录、地区、模板开关、时长、图片数量、声明版本和 OSS 对象归属。
2. 在同一数据库事务中锁定钱包，写入任务、扣币账本和 Outbox 事件；`business_key=generation:{id}:debit`。
3. Worker 领取任务后只提交一次 Model Studio，保存 `provider_task_id` 和 `request_id`。
4. Poller 只查询已有任务 ID，绝不通过“再创建一次”来重试。
5. 终态失败时写返币账本，`business_key=generation:{id}:refund`；唯一键保证最多返还一次。
6. 成功但结果下载/OSS 转存失败也视为用户不可交付，返还金币；同时保留内部告警和补偿转存任务。

Model Studio 创建接口没有可依赖的业务幂等键。若请求已被服务商接收、但本地在保存 task ID 前崩溃，不能盲目重提；任务进入 `SUBMIT_UNKNOWN`，先按 request ID 排查，超时后向用户返币。这能避免同一用户意图产生两笔付费模型任务。

## 7. 媒体安全与生命周期

- 原图和结果使用私有 OSS Bucket，禁止匿名列举和公开读。
- 给 Model Studio 的输入签名 URL 建议 30 分钟有效；给用户播放/下载的签名 URL 建议 5 分钟有效。
- OSS Key 使用随机 UUID，不包含邮箱、昵称或原文件名。
- 上传完成后服务端重新探测 MIME、像素尺寸、文件大小，不能只信浏览器声明。
- 用户删除：数据库立即置 `deleted_at`，所有新签名请求返回 404；异步清理对象，最迟 24 小时完成。
- 自动过期：上传和生成时间起算 24 小时；清理任务可重复执行，`purged_at` 保证幂等。
- 日志禁止记录签名 URL、API Key、OAuth token、原图内容和 PayPal access token。

## 8. 登录、地区与支付

登录使用 Apple ID、Google 和邮箱验证码。移动端默认顺序仅由 User-Agent/平台能力决定，所有方式均可手动选择。OAuth 回调必须校验 `state`、PKCE、issuer、audience、nonce 和已验证邮箱。

中国大陆限制采用多层判断：CDN/边缘 IP 国家、后端 IP 国家、账户国家、PayPal 可用国家和明确用户声明。命中 `CN` 时禁止注册、登录后的生成和购买，展示“当前地区暂未开放服务”。IP 判断不是身份认证，不能承诺绝对阻断 VPN；需要配合服务条款和风控审计。

PayPal 使用服务端 Orders v2：创建订单 → 用户批准 → 服务端捕获。金币只能在捕获状态确认、金额/币种/商品匹配且未处理过时入账。Webhook 必须回传 PayPal 验证签名或进行等价本地验证，并以 PayPal event ID 去重。

官方依据：[PayPal Orders v2](https://developer.paypal.com/api/rest/integration/orders-api)、[PayPal Webhook verification](https://developer.paypal.com/api/rest/webhooks/rest/)。

## 9. 监控与告警

- 指标：提交成功率、终态成功率、各模板/时长 P50/P95 耗时、审核拒绝率、返币率、转存失败率、每成功视频模型成本。
- 告警：`SUBMIT_UNKNOWN`、Poller 24 小时未终态、余额不守恒、同一业务键冲突、OSS 清理超过 24 小时、PayPal 捕获后未入账。
- 追踪：本地 `generation_id`、Model Studio `request_id/task_id`、PayPal `order_id/capture_id/event_id` 分开存储并可关联查询。

## 10. 当前代码状态

现有 FastAPI 项目已新增 `app/services/model_studio.py`，实现：

- 新加坡 workspace 专属域名；
- 两图 R2V 创建；
- 图片到动作创建；
- 共用异步任务查询和两种结果结构归一化；
- 15 秒图片型 R2V 参数校验；
- API 错误码和 request ID 保留；
- 默认关闭开关，未配置凭证时不会产生付费调用。

尚未实现数据库任务编排、OSS、PayPal 和前台页面，这些按实施 Backlog 进入后续迭代。
