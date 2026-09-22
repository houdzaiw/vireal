# Vireal 双模式视频生成设计规格

状态：已由用户确认，可进入实施计划  
日期：2026-09-15  
适用版本：Vireal H5 v1.1  
基线：`outputs/vireal-wan-video-h5/prototype/prototype_v1.0.html` 与现有 FastAPI 视频任务链路

## 1. 目的

Vireal 在不替换现有 Wan 高级生成能力的前提下，引入 Replicate 免费集合中的 MiniMax Video-01 作为普通模式，面向真实用户验证图片上传、prediction 创建、Webhook、Worker、Cloudflare R2 私有转存和 H5 播放的完整闭环。

当第三方真实生成因用户额度、全站高级额度、余额或服务可用性无法执行时，系统使用自有 Railway Worker 根据用户原图生成简单动画 MP4。该结果复用真实视频的播放、下载和 24 小时清理链路，但必须标记为“演示结果”。

## 2. 已确认的产品规则

- 普通模式使用 `minimax/video-01`，上传图片作为 `first_frame_image`。
- 普通模式固定输出 5 秒；MiniMax 约 6 秒输出由 Worker 裁剪为 5 秒。
- 高级模式使用 `wan-video/wan-2.7-r2v`，支持 5 秒和 10 秒。
- 两种模式均固定为单人跳舞、9:16 竖屏、静音，不开放提示词编辑。
- 普通、高级和演示结果均不扣金币。
- 每位用户按 UTC 自然日最多创建 5 个真实 Replicate prediction，两种模式合并计数。
- Wan 高级模式全站按 UTC 自然日最多创建 3 个真实 prediction。
- 所有输入图片、真实视频和演示视频均存入私有 R2，并在 24 小时后清理。
- 上传区常驻显示非阻断式说明：“上传即表示你拥有图片使用权；图片可能由第三方 AI 服务处理。”

## 3. 范围与非目标

### 3.1 本期范围

- H5 普通/高级模式切换和时长联动；
- MiniMax 模型适配；
- 用户级与 Wan 全站真实生成额度；
- 自有 Worker 动画降级；
- 统一任务状态、播放、下载、过期和埋点；
- 中英文核心文案；
- 自动化测试和无费用集成测试。

### 3.2 非目标

- 正式金币账本、支付扣款或失败退款；
- 双人动作、音频、横屏、15 秒或用户自定义提示词；
- 将普通模式扩展为真正的 10 秒 MiniMax 生成；
- 使用相同公共样片冒充个性化演示结果；
- 自动重提任何结果不明确的外部 prediction；
- 在本期内替换 Wan 作为高级模式供应商。

## 4. H5 体验设计

### 4.1 视觉方向

采用用户确认的 A“分段切换”方案。v1.1 是现有创作页的局部扩展，不更换 Vireal 的墨绿色、薄荷绿、暖白色、圆角卡片和紧凑产品界面语言。

页面继续使用桌面双栏、移动端单栏结构。模式选择使用一行双段控件，避免价格卡式对比或多步骤向导增加操作长度。

### 4.2 创作页结构

1. Step 1：选择动作；本期真实后端模式只开放单人跳舞。
2. Step 2：上传一张单人全身照；上传卡下方显示权利与第三方处理说明。
3. Step 3：选择模式；默认普通模式，可切换高级模式。
4. Step 4：选择时长；普通模式锁定 5 秒，高级模式启用 5/10 秒。
5. 右侧或下方摘要：动作、模式、时长、720p、9:16、静音、24 小时、今日剩余真实次数和“免费体验”。
6. 主按钮根据选择显示“免费生成 5 秒视频”或“免费生成 10 秒视频”。

现有阻断式“确认授权”步骤从 v1.1 创作流程移除；权利声明改为上传区非阻断式常驻文案。现有金币扣除、余额不足和失败返币文案在双模式测试期隐藏，不修改本地金币余额。

### 4.3 模式和时长联动

- 初始状态：`mode=standard`、`duration=5`。
- 普通模式：10 秒控件处于禁用状态，并说明“高级模式支持 10 秒”。
- 高级模式：5 秒和 10 秒均可选择，默认保持 5 秒。
- 用户在高级模式选择 10 秒后切回普通模式：时长立即归位为 5 秒。
- 服务端重复执行相同规则；客户端伪造普通模式 10 秒时返回 422，且不创建任务。

### 4.4 进度和结果

进度页根据实际执行类型显示文案：

- MiniMax：正在生成普通模式视频；
- Wan：正在生成高级模式视频；
- 本地动画：正在制作演示结果；
- 保存阶段：正在安全保存到私人作品。

真实与演示结果使用同一播放器和下载按钮。演示结果在播放器上方和作品卡片上显示不可隐藏的“演示结果”标签，并说明“真实生成暂不可用，本视频由你的照片生成简单动画效果”。

## 5. 系统组成与职责

### 5.1 H5 客户端

- 保存模式、时长、上传 ID、任务 ID 和幂等键；
- 调用统一创建任务与查询任务接口；
- 每 3 秒查询状态，并在刷新后恢复当前任务；
- 根据 `is_demo`、`execution_type` 和 `fallback_reason` 显示准确状态；
- 签名地址过期时重新查询任务，不缓存长期播放地址；
- 不接收或保存 Replicate、Webhook、R2 密钥。

### 5.2 FastAPI API

- 验证 App Token、图片所有权、图片有效期、模式、时长和幂等键；
- 在数据库事务内创建任务并预留真实生成额度；
- 路由 MiniMax、Wan 或本地动画；
- 生成一小时有效的输入图片 R2 签名地址；
- 接收并验证 Replicate Webhook；
- 仅向任务所有者返回任务状态和五分钟播放地址。

### 5.3 Replicate 适配层

对上层暴露统一的 `create_prediction` 协议，模型构建器各自负责输入映射：

- MiniMax：`prompt`、`prompt_optimizer=true`、`first_frame_image`；
- Wan：`prompt`、`negative_prompt`、`reference_images`、`duration`、`resolution=720p`、`aspect_ratio=9:16`；
- 两者均使用带任务 ID 的 HTTPS Webhook URL；
- 输出统一规范化为单个可下载视频 URI；
- 保存 prediction ID、模型、错误和 metrics。

### 5.4 PostgreSQL Worker

- 使用 `FOR UPDATE SKIP LOCKED` 领取保存、转码、演示生成和清理任务；
- 下载 Replicate 输出并限制体积、超时和内容类型；
- MiniMax 输出裁剪为 5 秒并统一封装；
- 生成本地演示动画；
- 将结果上传到 `vireal/videos/{user_id}/{task_id}.mp4`；
- 只重试下载、裁剪、转码、R2 写入和清理，不创建 prediction。

### 5.5 Cloudflare R2

- Bucket 保持私有；
- 输入和输出只通过服务端签名地址访问；
- 输入签名地址默认一小时，播放签名地址默认五分钟；
- 未签名对象 URL 必须不可读；
- 应用 Worker 负责 24 小时清理，R2 生命周期规则可作为容灾兜底。

## 6. API 与数据模型

### 6.1 创建任务

`POST /api/v1/app/video-tasks`

请求：

```json
{
  "template_id": "dance",
  "upload_ids": ["<upload-id>"],
  "mode": "standard",
  "duration": 5
}
```

请求必须携带 `Idempotency-Key`。`mode` 仅允许 `standard` 或 `advanced`；普通模式仅允许 5 秒，高级模式仅允许 5 或 10 秒。

响应在现有任务字段上增加：

```json
{
  "mode": "standard",
  "execution_type": "minimax",
  "is_demo": false,
  "fallback_reason": null,
  "quota": {
    "user_real_remaining": 4,
    "wan_global_remaining": 3,
    "resets_at": "<next-utc-midnight>"
  }
}
```

### 6.2 查询任务

`GET /api/v1/app/video-tasks/{id}` 返回上述字段、公共状态、错误、过期时间及成功时的 `playback_url`。

公共状态扩展为：`submitting`、`pending`、`running`、`saving`、`rendering_demo`、`succeeded`、`failed`、`canceled`、`submission_unknown`、`expired`。

### 6.3 任务字段

在 `AppVideoTask` 中增加：

- `mode`：`standard|advanced`；
- `execution_type`：`minimax|wan|local_demo`；
- `is_demo`：布尔值；
- `fallback_reason`：受控枚举；
- `quota_user_date`、`quota_wan_date`：关联配额预留；
- `real_submission_counted_at`：确认外部 prediction 已创建的时间；
- `source_duration`：外部原始视频时长，用于记录 MiniMax 裁剪来源。

### 6.4 配额预留

新增按 UTC 日期聚合的配额记录，至少包含作用域、作用域 ID、日期、上限、预留数和已消费数。创建任务时：

1. 先依据幂等键复用或创建任务；
2. 在数据库事务中锁定用户配额行；
3. 高级模式同时锁定 Wan 全站配额行；
4. 若额度可用则预留，若不足则直接路由本地动画；
5. prediction 明确创建后将预留转为已消费；
6. 创建前明确失败时释放预留并路由本地动画；
7. `submission_unknown` 保持预留，直到人工或可靠回调确认，避免超额和重复付费。

已创建后失败或取消的 prediction 仍计入已消费次数。本地动画、幂等重复请求和创建前被拒绝的请求不计入真实生成次数。

## 7. 提示词与媒体处理

### 7.1 固定提示词

服务端使用英文受控提示词表达：一位成年人进行自然、有节奏的全身舞蹈；保持人物身份、服装和主要背景；动作连贯、镜头稳定、竖屏构图；不生成文字或水印。提示词不下发为用户可编辑字段。

### 7.2 本地动画规格

本地动画由 Worker 使用 FFmpeg 生成，不调用外部 AI：

- 输出：720×1280、25fps、H.264、`yuv420p`、MP4、无音轨；
- 普通模式 5 秒；高级模式使用用户选择的 5 秒或 10 秒；
- 原图以完整人物优先的 contain 方式放入竖屏画布；
- 背景使用同一原图放大、裁切和柔化填充，避免黑边；
- 动画只使用轻微推近、平移和缓动缩放，不模拟复杂舞蹈动作；
- 转码需限制 CPU 时间、输出体积和重试次数；
- Worker 镜像显式安装并健康检查 FFmpeg。

## 8. 路由与异常处理

### 8.1 进入本地动画的情况

- 用户当日 5 次真实生成额度耗尽；
- 高级模式全站当日 3 次 Wan 额度耗尽；
- Replicate 明确返回余额不足、免费额度不足、限流或可恢复服务错误；
- prediction 已创建后明确终态失败，且不会触发第二次外部调用；
- Replicate 认证或模型访问配置错误时允许向用户交付演示结果，但必须触发高优先级运维告警。

### 8.2 不进入本地动画的情况

- 图片格式、大小、有效期或所有权不符合要求；
- 用户身份无效；
- 输入或输出被明确安全拒绝；
- 相同幂等键对应不同请求参数；
- prediction 创建结果为 `submission_unknown`；
- 原图已删除或不可读取。

### 8.3 本地动画失败

本地生成失败只允许重试本地处理。达到 Worker 重试上限后任务进入 `failed`，H5 显示可理解错误和重新上传入口，不再调用 MiniMax、Wan 或另一套降级。

## 9. Webhook、幂等与状态一致性

- Webhook 使用原始请求体及 `webhook-id`、`webhook-timestamp`、`webhook-signature` 验证 HMAC；
- 时间容差默认 300 秒；
- Webhook ID 持久化防重放；
- 重复和终态后的乱序事件返回 2xx 并忽略；
- 成功回调只写入待保存状态并快速响应，不在 HTTP 请求内下载视频；
- 相同幂等键与相同参数返回原任务；相同键与不同参数返回 409；
- prediction ID 在任务维度唯一；Worker 重试不得触发适配器创建模型任务。

## 10. 隐私与结果真实性

- 上传控件可见时，权利与第三方处理说明必须同时可见；
- 中文和英文表达同等明确，文案资源失败时使用内置英文兜底；
- 隐私政策说明图片可能由 Replicate 和对应模型供应商处理；
- 普通日志不记录原图、签名 URL、Token、Webhook Secret 或 R2 Secret；
- 演示结果不得使用 MiniMax/Wan 生成标签，不得隐藏“演示结果”；
- 只有任务所有者能够查询、播放或下载结果；
- 24 小时后 API 不再签发媒体地址，Worker 完成物理清理。

## 11. 配置与部署

API 与 Worker共享以下服务端配置：

```text
REPLICATE_ENABLED=True
REPLICATE_STANDARD_MODEL=minimax/video-01
REPLICATE_ADVANCED_MODEL=wan-video/wan-2.7-r2v
APP_USER_DAILY_REAL_SUBMISSIONS=5
APP_WAN_DAILY_GLOBAL_SUBMISSIONS=3
LOCAL_DEMO_ENABLED=True
LOCAL_DEMO_FFMPEG_PATH=/usr/bin/ffmpeg
R2_REPLICATE_URL_EXPIRE_SECONDS=3600
APP_PLAYBACK_URL_EXPIRE_SECONDS=300
```

Railway API 服务负责 HTTPS API 和 Webhook；Railway Worker 使用同一代码镜像并包含 FFmpeg；Neon 提供 PostgreSQL；Cloudflare Pages 承载 H5；Cloudflare R2 保持私有。

原有单次 PoC 配置 `REPLICATE_POC_MAX_SUBMISSIONS` 在 v1.1 中不再作为正式额度来源，部署时由新的用户级和全站级配置替代。

## 12. 可观测性

每个任务至少记录以下结构化维度：

- `task_id`、`prediction_id`、`mode`、`execution_type`、`duration`；
- prediction 是否创建、用户额度是否消费、Wan 全站额度是否消费；
- `fallback_reason` 与 `is_demo`；
- 提交、模型、Webhook、保存和端到端耗时；
- Worker 重试次数、错误分类和 R2 对象状态。

指标必须能回答：每天创建多少 MiniMax/Wan prediction、每种模式成功率、进入本地动画的数量与原因，以及是否超过用户或全站额度。

## 13. 测试设计

### 13.1 单元测试

- 模式与时长校验；
- MiniMax 和 Wan 参数构建；
- 输出 URI 规范化；
- 用户与 Wan 配额预留、消费、释放和 UTC 重置；
- 并发争抢最后额度；
- 幂等键复用和冲突；
- Webhook 签名、时间窗口、重放、重复和乱序；
- 状态映射和降级原因；
- 本地动画命令构建、失败重试和清理。

### 13.2 无费用集成测试

使用模拟 Replicate、Webhook 和 R2 覆盖：

1. 普通模式真实成功；
2. 高级模式 5 秒和 10 秒成功；
3. 用户额度耗尽后本地动画；
4. Wan 全站额度耗尽后本地动画；
5. Replicate 余额不足后本地动画；
6. `submission_unknown` 不重提也不降级；
7. Webhook 成功后 Worker 转存；
8. 本地动画生成、播放和下载；
9. 24 小时清理及过期访问拒绝。

### 13.3 H5 验收

- 桌面 1440px 与移动 390px；
- 普通/高级切换和时长联动；
- 上传、常驻告知、生成进度、刷新恢复；
- 真实结果和演示结果的正确标识；
- 播放地址续签、下载、过期和错误文案；
- 直接访问未签名 R2 对象失败。

自动化测试不得创建真实 prediction。生产真实验收由服务端配额限制，且每次执行前由操作人员确认账户状态和当前计数。

## 14. 实施边界与验收结果

实施应按以下独立边界推进：

1. 数据迁移与配额服务；
2. MiniMax 适配与统一模型路由；
3. Webhook 与任务状态扩展；
4. FFmpeg 本地动画和媒体保存；
5. H5 v1.1 交互与文案；
6. 自动化测试、部署配置和受控生产验收。

完成时必须同时满足：普通模式可在正式 H5 播放 MiniMax 结果；高级模式保持 Wan 5/10 秒；超过额度或明确服务不可用时交付带标识的本地动画；任何异常均不产生重复 prediction；所有媒体保持私有并在 24 小时后不可访问。
