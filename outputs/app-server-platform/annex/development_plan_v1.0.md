# App 服务端与后台管理系统开发实现计划 v1.0

## 目标

基于 `fastapi/full-stack-fastapi-template` 二次开发，先在本地/内网跑通移动 App API 和后台管理系统的核心闭环：

- App 设备 UUID 登录
- App 用户头像和昵称修改
- 文字/图片动态发布与动态流
- 本地文件图片存储
- 后台管理员登录
- 后台 App 用户管理
- 后台动态内容管理
- Apple IAP 与 Google Play 支付通知接收
- 后台订单状态查看
- key-value 运营配置管理
- App 启动配置拉取

## 推荐仓库结构

```text
server/
  backend/
    app/
      api/
        routes/
          admin/
          app/
          webhooks/
      core/
      models.py
      crud.py
      schemas/
      services/
        auth/
        uploads/
        payments/
        configs/
    alembic/
    tests/
  frontend/
    src/
      routes/
      components/
      features/
        app-users/
        contents/
        orders/
        configs/
mobile-app/
  only-calls-server-api
```

说明：`full-stack-fastapi-template` 默认包含 `backend` 和 `frontend`，可以把它作为 `server/` 的基础。移动 App 单独建项目，不放进该模板。

## 模板改造策略

### 1. 后台管理员沿用模板用户体系

模板原有 `User`、JWT 登录、密码哈希、后台登录逻辑适合保留给后台管理员。

建议处理：

- 语义上把模板 `User` 定义为后台管理员。
- 第一版只保留一个管理员角色。
- 后续需要 RBAC 时再扩展角色表或权限字段。

### 2. App 用户独立建表

不要让 App 用户复用后台管理员表。App 用户没有邮箱密码，不走后台登录流程。

建议新增：

- `app_users`
- `app_devices`
- `app_sessions` 可选，第一版如只使用 JWT 可先不建

### 3. API 分组清晰隔离

建议按调用方分组：

```text
/api/v1/app/*
/api/v1/admin/*
/api/v1/webhooks/*
```

对应鉴权：

- `/app/*` 使用 App token
- `/admin/*` 使用后台管理员 token
- `/webhooks/*` 使用平台签名或共享密钥，第一版本地可先支持模拟校验

## 数据库模型建议

### admin_users

可复用模板 `users` 表，语义上作为后台管理员。

关键字段：

- `id`
- `email`
- `hashed_password`
- `is_active`
- `is_superuser`
- `created_at`
- `updated_at`

### app_users

```text
id UUID primary key
nickname string nullable
avatar_url string nullable
status enum active disabled deleted
created_at datetime
updated_at datetime
deleted_at datetime nullable
```

索引：

- `status`
- `created_at`
- `deleted_at`

### app_devices

```text
id UUID primary key
app_user_id foreign key app_users.id
device_uuid_hash string unique
platform enum ios android
last_login_at datetime
created_at datetime
```

说明：建议保存设备 UUID 哈希，不直接保存原始设备号。

### uploads

```text
id UUID primary key
owner_type enum app_user content
owner_id UUID nullable
file_path string
public_url string
mime_type string
size_bytes integer
created_at datetime
```

第一版也可以不建独立 `uploads` 表，直接在 `app_users` 和 `content_images` 中保存路径。若想后续迁移对象存储，建议建表。

### contents

```text
id UUID primary key
app_user_id foreign key app_users.id
text text nullable
status enum visible deleted hidden
created_at datetime
updated_at datetime
deleted_at datetime nullable
```

索引：

- `app_user_id`
- `status`
- `created_at`
- `deleted_at`

### content_images

```text
id UUID primary key
content_id foreign key contents.id
file_path string
public_url string
sort_order integer
created_at datetime
```

### orders

```text
id UUID primary key
app_user_id foreign key app_users.id nullable
platform enum apple google
product_id string
transaction_id string
status enum pending paid failed cancelled refunded unknown
paid_at datetime nullable
created_at datetime
updated_at datetime
```

索引：

- `platform`
- `transaction_id`
- `status`
- `app_user_id`

### order_events

```text
id UUID primary key
order_id foreign key orders.id nullable
platform enum apple google
event_id string nullable
event_type string
transaction_id string nullable
payload_digest string
process_status enum processed ignored failed
error_message text nullable
created_at datetime
processed_at datetime nullable
```

说明：用于幂等和排查。`event_id` 如果平台可提供，应与 `platform` 建唯一约束。

### app_configs

```text
id UUID primary key
key string unique
value text
value_type enum string number boolean json
is_enabled boolean
description string nullable
created_at datetime
updated_at datetime
```

## 后端模块实现顺序

### 阶段 1：项目初始化

1. 拉取 `full-stack-fastapi-template`。
2. 跑通 Docker Compose。
3. 确认 PostgreSQL、后端、前端、自动文档均可访问。
4. 固定 `.env`、本地上传目录和测试数据库配置。

### 阶段 2：App 用户身份体系

1. 新增 `app_users` 和 `app_devices` 模型。
2. 新增 Alembic migration。
3. 实现设备 UUID 登录接口。
4. 实现 App token 签发和鉴权依赖。
5. 增加登录接口测试。

### 阶段 3：资料与上传

1. 实现本地上传目录。
2. 实现图片上传接口。
3. 实现头像和昵称修改接口。
4. 限制文件类型、文件大小、昵称长度。
5. 增加上传和资料接口测试。

### 阶段 4：动态内容

1. 新增 `contents` 和 `content_images` 模型。
2. 实现发布动态接口。
3. 实现动态流列表接口。
4. 实现详情接口。
5. 查询时过滤已删除内容和禁用用户内容。
6. 增加发布、列表、删除过滤测试。

### 阶段 5：后台管理 API

1. 实现 App 用户列表、禁用、软删除。
2. 实现动态内容列表、软删除。
3. 实现订单列表、事件列表。
4. 实现配置 CRUD。
5. 所有后台接口接入管理员 token。

### 阶段 6：后台前端

1. 基于模板 React 前端新增菜单。
2. 新增 App 用户管理页。
3. 新增动态内容管理页。
4. 新增订单状态页。
5. 新增运营配置页。
6. 对禁用、删除、启停操作增加确认弹窗。

### 阶段 7：支付通知

1. 新增 Apple IAP webhook。
2. 新增 Google Play webhook。
3. 记录 `order_events`。
4. 按事件 ID 或交易号做幂等。
5. 更新 `orders` 状态。
6. 第一版本地提供模拟通知脚本或测试接口。

### 阶段 8：本地验收

1. App 设备登录后能拿到 token。
2. App 能修改头像昵称。
3. App 能上传图片并发布动态。
4. 动态发布后列表立即可见。
5. 后台能禁用用户。
6. 禁用用户无法继续发布。
7. 后台能删除动态。
8. 删除后 App 不再返回该动态。
9. 支付模拟通知能更新订单状态。
10. 后台配置修改后 App 启动配置接口返回最新启用配置。

## 核心接口草案

### App API

```text
POST /api/v1/app/auth/device-login
GET  /api/v1/app/users/me
PATCH /api/v1/app/users/me
POST /api/v1/app/uploads/images
GET  /api/v1/app/contents
POST /api/v1/app/contents
GET  /api/v1/app/contents/{content_id}
GET  /api/v1/app/configs
```

### Admin API

```text
GET    /api/v1/admin/app-users
PATCH  /api/v1/admin/app-users/{app_user_id}/disable
DELETE /api/v1/admin/app-users/{app_user_id}
GET    /api/v1/admin/contents
DELETE /api/v1/admin/contents/{content_id}
GET    /api/v1/admin/orders
GET    /api/v1/admin/orders/{order_id}/events
GET    /api/v1/admin/configs
POST   /api/v1/admin/configs
PATCH  /api/v1/admin/configs/{config_id}
DELETE /api/v1/admin/configs/{config_id}
```

### Webhook API

```text
POST /api/v1/webhooks/apple-iap
POST /api/v1/webhooks/google-play
```

## 第一版测试重点

### 后端单元与集成测试

- 设备号首次登录创建用户
- 相同设备号再次登录返回同一用户
- 不同设备号创建不同用户
- 禁用用户不能发布动态
- 删除动态后 App 列表不返回
- 停用配置不下发
- 支付重复通知幂等处理
- 无管理员 token 不能访问后台接口

### 前端验证

- 管理员登录后能进入后台
- 用户列表能筛选状态
- 禁用和删除有确认弹窗
- 内容删除后列表刷新
- 订单状态可查看
- 配置新增、编辑、启停后列表更新

## 风险与处理

| 风险 | 影响 | 第一版处理 |
| --- | --- | --- |
| 设备 UUID 不稳定 | 重装或换设备生成新用户 | 已接受，设备变化即新用户 |
| 本地文件存储不可扩展 | 生产环境迁移成本 | 第一版先本地，v1.2 迁移对象存储 |
| 支付通知真实性不足 | 订单可能被伪造 | 本地先模拟，生产前补签名校验 |
| 无内容审核 | 违规内容会先展示 | 后台可删除，v1.3 增加审核和举报 |
| 单管理员角色 | 后台权限不可细分 | 第一版接受，v1.4 增加 RBAC |

## 开发完成定义

- 本地 Docker Compose 一键启动。
- 后端测试通过。
- 关键 API 在 Swagger 中可调通。
- 后台页面能完成用户、内容、订单、配置管理。
- App API 能完整跑通设备登录、资料修改、动态发布和配置拉取。
- 支付模拟通知能写入事件并更新订单状态。
- README 写清本地启动、初始化管理员、上传目录和模拟支付通知方式。
