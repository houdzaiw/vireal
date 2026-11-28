# Vireal iPhone 接口与登录适配

服务端已有面向 App 用户的账户、上传、生成、作品和金币接口，可以复用网页账户体系。当前原生 iPhone 登录仍需适配及真机验证，不能以路由名包含 `app` 判断为已经可用。

接口基线为本地候选源码 `work/launch-closure-integration-20261119`，提交 `1bcff9975f7b9ae6a32a186a4a6db10995e36104`。源码能力与线上部署分开验收：本次交付未修改或探测生产服务。

## 统一请求约定

API 基址使用各环境现有 HTTPS 边缘入口，统一前缀 `/api/v1/app`。预发布与生产独立配置，不能绕过地区验证直接访问后端源站，也不能由客户端伪造可信地区头。

个人接口使用 `Authorization: Bearer <Clerk session token>`。令牌由 Clerk SDK 获取和刷新，客户端不存 Clerk Secret Key，不自行签发令牌。业务身份由已验证的 `issuer + subject` 映射；不按设备 UUID 或客户端邮箱字符串重新创建或合并账户。

时间字段按带时区的 ISO 8601 解析，页面按设备时区显示。需要金额或金币的界面只读取服务端数据。失败响应通常带 `detail`，不能统一将所有 403 当作登录过期。

## 已有接口

| 操作与鉴权 | 请求 | 主要返回和客户端使用 |
| --- | --- | --- |
| 公共效果目录，无需登录 | `GET /effect-catalog` | `categories[]` 内嵌 `effects[]` 与 `variants[]`；支持 ETag，目录 304 时使用已有缓存 |
| 单个效果，无需登录 | `GET /effects/{slug}` | 效果、`input_image_count`、媒体 URL、时长与金币规格 |
| 可用性提示，可携带会话 | `GET /paypal/config` | 上传、生成、注册、地区和全站额度提示；个别内测模式有独立条件，不等于业务授权 |
| 公共配置 | `GET /configs` | 后端公开配置；只消费已定义字段，不自行猜测媒体保留期限键名 |
| 初始化业务会话，Clerk Bearer | `POST /auth/session`，无 JSON 体 | `app_user`、`is_new_user` 和内测能力字段；复用既有用户，登记当前会话 |
| 当前资料，App Bearer | `GET /users/me` | 含身份的用户资料 |
| 修改昵称，App Bearer | `PATCH /users/me`，`{"nickname":"新昵称"}` | 更新后的用户；首版不新增头像上传 |
| 退出当前会话，Clerk Bearer | `POST /auth/logout` | 本地会话撤销，并尝试撤销该 Clerk 会话；客户端随后完成 SDK 退出 |
| 上传照片，App Bearer | `POST /uploads/images`，multipart 的 `file` 字段 | `id`、`url`、`content_type`、`size`、`expires_at`；后续传上传 ID，不传任意 URL |
| 创建生成任务，App Bearer | `POST /video-tasks`，JSON 与 `Idempotency-Key` | HTTP 202，返回任务及可选余额与额度；已有标识返回原任务或冲突，不能换标识重扣 |
| 列出本人任务，App Bearer | `GET /video-tasks?skip=0&limit=50` | `data[]` 和 `count`；服务端当前按用户隔离 |
| 查询本人任务，App Bearer | `GET /video-tasks/{id}` | 状态、错误、播放链接、链接及媒体有效期、退币时间等 |
| 下载作品，App Bearer | `GET /video-tasks/{id}/download` | 受保护的视频流；文件名由响应头提供；过期 410，未完成 409 |
| 删除终态作品，App Bearer | `DELETE /video-tasks/{id}` | 删除结果；进行中任务返回 409 |
| 金币与额度，App Bearer | `GET /wallet` | `balance`、`ledger`、`daily_remaining`、`concurrent_remaining`、`resets_at`、支付审核和全站额度 |
| 历史订单，App Bearer | `GET /orders?skip=0&limit=20` | `data[]` 与 `count`；首版仅保留读取能力，不创建订单 |

### 生成请求

```http
POST /api/v1/app/video-tasks
Authorization: Bearer <session token>
Content-Type: application/json
Idempotency-Key: <本次确认尝试的 UUID>
```

```json
{
  "effect_id": "<目录返回的效果 UUID>",
  "variant_id": "<所选规格 UUID>",
  "upload_ids": ["<上传接口返回的 UUID>"]
}
```

双图效果发送两个本人、有效且顺序正确的上传 ID。原型中的 `dance-1` 等字符串只是展示标识，不可用于真实请求。首版走效果规格路径，不使用旧版 `template_id`、客户端价格或任意模型参数。

任务主要字段包含 `id`、`status`、`effect_id`、`variant_id`、`effect_title`、`duration`、`coin_cost`、`balance`、`error`、`playback_url`、`playback_url_expires_at`、`coin_refunded_at`、`expires_at`、`quota`；可空字段应按可空解码。

### 任务状态映射

| 服务端 status | 页面状态 | 提交或轮询行为 |
| --- | --- | --- |
| `submitting` | 正在提交 | 查询原任务 |
| `pending` | 排队等待 | 继续轮询 |
| `running` | AI 生成中 | 继续轮询，不显示虚构百分比 |
| `rendering_demo` | 正在生成演示 | 明确为演示，不冒充真实模型交付 |
| `saving` | 正在保存作品 | 继续轮询 |
| `succeeded` | 已完成 | 停止轮询，可播放和下载 |
| `failed` | 生成失败 | 停止轮询，读取退币时间与流水 |
| `canceled` | 已取消 | 停止轮询，读取实际金币处理结果 |
| `submission_unknown` | 正在确认 | 查询原任务，不开启新付费提交 |
| `expired` | 媒体已过期 | 停止播放、保存和分享，保留历史记录 |

### 错误处理

401 或凭据无效时，让 SDK 刷新令牌一次。403 必须区分会话撤销、账户停用、未初始化、注册关闭、地区与准入限制：只有可确认的身份失效才引导重新登录；业务关闭直接展示原因。

409 时重读效果或任务，不能简单重试创建。410 表示已退役登录或过期媒体，不自动重开设备登录。422 显示照片数量、规格或字段错误。429 按响应和重置时间退避。5xx 或网络超时时保留原始生成请求和幂等标识，不自动生成第二笔。

初次 POST 未返回任务 ID 时，同参数同幂等标识核对仍应先遵循服务可用性规则；无法确认就维持待确认并支持人工核对。不能用无限 POST 重试替代任务查询。

## 原生登录需要的适配

当前 `backend/app/services/clerk_auth.py` 的验证器强制要求 `iss/sub/sid/aud/azp/exp/nbf`，`azp` 必须是已配置的网页来源；`ClerkSessionClaims.authorized_party` 为必填字符串。旧 `/auth/device-login` 在 Clerk 模式返回 410，不能作为原生接入捷径。

Clerk 原生 SDK 支持邮箱登录、会话恢复及令牌获取。按官方流程，需要在对应 Clerk 环境核对 Native API、App ID Prefix、Bundle ID 和关联域名配置。[iOS 接入文档](https://clerk.com/docs/ios/getting-started/quickstart)

Clerk 说明 `azp` 可能缺失，官方手动验证流程允许在缺失时跳过该字段检查；存在时必须验证许可来源。[会话令牌](https://clerk.com/docs/guides/sessions/session-tokens)、[手动验证](https://clerk.com/docs/guides/sessions/manual-jwt-verification)

后续适配采用以下规则，当前交付仅记录设计，没有应用到服务器：

1. 同环境复用 Clerk 身份，原生会话令牌保持已有 API audience；核对其签名后的实际字段，不假定默认令牌自带当前自定义 audience。
2. 验证器保留 RS256/JWKS、issuer、audience、`sub/sid/exp/nbf` 和 `sts != pending` 校验。`azp` 缺失时允许；存在时要求非空字符串并匹配已有白名单，错误来源、null、空值或畸形值继续拒绝。
3. `ClerkSessionClaims.authorized_party` 改为可空值。网页专用预发布登录验收仍要求精确网页 origin，原生缺失值不能通过该专用条件，不新增绕过入口。
4. 原生 SDK 登录后调用现有 `/auth/session`，复用本地 `AppUserIdentity` 与 `AppUserSession`。不需要新建 `/ios/login` 路由。
5. 对普通认证请求继续使用现有本地会话检查，撤销后不能因令牌仍在有效期内恢复访问。权限、注册、地区、费用和额度判断保留在服务端。
6. 退出调用 `/auth/logout` 后 SDK 退出；遇到联网失败，也清除本地个人界面并记录远端撤销尚待确认，不能向用户宣称其他设备均已退出。

涉及的主要契约变化只有可空 `authorized_party` 和 `azp` 缺失兼容；请求路径及业务响应不变。验证用例需包含网页合法/错误来源、原生缺失来源、错误 audience、过期令牌、已撤销会话和同账号两会话隔离。

## 能力缺口与真实联调顺序

| 优先级 | 项目 | 完成标准 |
| --- | --- | --- |
| 接入前 | Clerk 原生配置与 `azp/aud` 兼容 | 预发布真机使用 SDK 登录；业务初始化后可读本人资料、钱包和作品 |
| 生成前 | 当前版本 API 与生成 Worker 可用 | 版本、数据结构与既有运行验收匹配，既有账户及地区准入有效 |
| 内测前 | 受保护视频播放与文件保存 | 真机可携带权限访问下载，刷新过期播放链接，拒绝相册权限时可分享 |
| 上架前 | 苹果内购 | 现有 `/orders` 创建仅允许 local，不能直接开启生产；需独立交易验证、到账去重、通知与退款处理 |
| 上架前 | 账户注销 | 当前用户接口只有读取与修改；需完整身份注销、会话撤销、数据删除及必要保留流程 |
| 后续版本 | 任务完成推送 | 当前没有客户端推送注册和通知交付链路；首版前台轮询即可 |

11 月 20—21 日最近验收记录仍列出生产生成 Worker 停止、公开注册未开放，以及运行环境相关阻断。该记录不构成本次实时状态核验。首轮使用已有获准内测身份，先验证登录和只读接口；完整生成必须先通过既有服务恢复与费用准入条件。

## 源码依据

- `backend/app/api/routes/app_auth.py` 与 `backend/app/api/deps.py`：初始化、设备登录退役、当前会话和注销。
- `backend/app/services/clerk_auth.py` 与 `backend/app/services/staging_login_acceptance.py`：令牌校验和网页来源专用条件。
- `backend/app/api/routes/app_catalog.py`、`app_uploads.py`、`app_video_tasks.py`、`app_wallet.py`、`app_orders.py`：目录、上传、生成、金币和订单契约；均相对上述候选源码目录。
- `output/launch-readiness-closeout-20261120/REVIEW.txt`：11 月 20—21 日服务验收记录。
