# 实现进度记录 v1.0

## 当前代码位置

```text
/Users/liqihui/Documents/Codex/2026-08-22/new-chat/server
```

## 已完成里程碑

### M0：准备

- 基于 FastAPI `full-stack-fastapi-template` 初始化项目。
- 后端依赖已同步，Python 虚拟环境已创建。
- Docker、Docker Compose、Bun 已验证可用。
- PostgreSQL 与 Mailpit 已启动。
- React 前端依赖已安装并完成一次构建。

### M1：App 身份体系

- 新增独立 App 用户表：`app_user`。
- 新增设备表：`app_device`。
- 新增设备号登录接口：`POST /api/v1/app/auth/device-login`。
- 新增 App token 签发与鉴权依赖。
- 后台管理员用户和 App 用户保持独立账号体系。

### M2：资料和图片上传

- 新增当前 App 用户资料接口：`GET /api/v1/app/users/me`。
- 新增昵称、头像修改接口：`PATCH /api/v1/app/users/me`。
- 新增本地图片上传接口：`POST /api/v1/app/uploads/images`。
- 图片上传支持基础类型校验和 5MB 大小限制。
- 本地上传目录通过 `/uploads` 静态路径访问。

### M3：动态内容

- 新增动态表：`app_content`。
- 新增动态图片表：`app_content_image`。
- 新增动态发布接口：`POST /api/v1/app/contents/`。
- 新增动态流接口：`GET /api/v1/app/contents/feed`。
- 新增动态详情接口：`GET /api/v1/app/contents/{content_id}`。
- App 端默认过滤已删除内容、禁用用户内容和已删除用户内容。

### M4：后台管理 API

- 新增 App 用户后台列表：`GET /api/v1/admin/app/users`。
- 新增 App 用户启用/禁用：`PATCH /api/v1/admin/app/users/{app_user_id}/status`。
- 新增 App 用户软删除：`DELETE /api/v1/admin/app/users/{app_user_id}`。
- 新增动态后台列表：`GET /api/v1/admin/app/contents`。
- 新增动态软删除：`DELETE /api/v1/admin/app/contents/{content_id}`。
- 后台接口沿用模板超级管理员 JWT 权限。

### M5：订单和支付通知

- 新增订单表：`app_order`。
- 新增订单事件表：`app_order_event`。
- 新增 App 创建订单：`POST /api/v1/app/orders`。
- 新增 App 订单列表：`GET /api/v1/app/orders`。
- 新增 App 订单详情：`GET /api/v1/app/orders/{order_id}`。
- 新增 Apple IAP 本地模拟回调：`POST /api/v1/webhooks/payments/apple-iap`。
- 新增 Google Play 本地模拟回调：`POST /api/v1/webhooks/payments/google-play`。
- 支付事件按 `provider + event_id` 幂等处理，重复事件不会重复更新订单。
- 支付成功回调会更新订单状态为 `paid` 并记录 `transaction_id`、`paid_at`。
- 新增后台订单列表：`GET /api/v1/admin/app/orders`。
- 新增后台订单详情：`GET /api/v1/admin/app/orders/{order_id}`。
- 新增后台订单事件列表：`GET /api/v1/admin/app/orders/{order_id}/events`。

### M6：运营配置

- 新增运营配置表：`app_config`。
- 新增后台配置列表：`GET /api/v1/admin/app/configs`。
- 新增后台配置创建：`POST /api/v1/admin/app/configs`。
- 新增后台配置详情：`GET /api/v1/admin/app/configs/{config_id}`。
- 新增后台配置编辑和启停：`PATCH /api/v1/admin/app/configs/{config_id}`。
- 新增 App 启动配置拉取：`GET /api/v1/app/configs`。
- App 端只返回启用配置，返回格式为简单 key-value map。

### M7：React 后台页面

- 已重新生成前端 OpenAPI client。
- 已新增后台 App 用户页面：`/app-users`。
- 已新增后台动态内容页面：`/app-contents`。
- 已新增后台订单页面：`/app-orders`。
- 已新增后台运营配置页面：`/app-configs`。
- 已在侧边栏增加 App Users、App Contents、App Orders、App Configs 入口。
- App 用户支持后台启用/禁用、软删除操作。
- 动态内容支持后台查看和软删除操作。
- 订单支持后台列表、详情和支付事件查看。
- 运营配置支持后台新增、编辑、启用/禁用操作。
- 已新增 React 后台 E2E 测试：`frontend/tests/app-admin.spec.ts`。

### M8：本地联调和验收文档

- 已新增本地联调 runbook：`annex/local_runbook_v1.0.md`。
- 已补充本地启动顺序、管理员初始化说明、App token 获取方式。
- 已补充设备登录、资料修改、图片上传、动态发布、配置拉取 curl 示例。
- 已补充 Apple IAP、Google Play 本地模拟支付回调和幂等验证示例。
- 已补充后台用户治理、内容删除、订单事件查看的 curl 示例。
- 已整理 React 后台页面验收项、自动验证命令和手工验收清单。
- 已补充 React 后台自动化验收，覆盖配置、用户治理、内容删除、订单事件和权限拦截。

### v1.1-01：后台操作日志

- 新增后台操作日志表：`app_admin_operation_log`。
- 新增日志查询接口：`GET /api/v1/admin/app/operation-logs`。
- 后台 App 用户启用/禁用、软删除会记录操作日志。
- 后台动态内容软删除会记录操作日志。
- 后台运营配置创建、更新、启停会记录操作日志。
- 新增 React 后台日志页面：`/app-operation-logs`。
- 侧边栏新增 App Logs 入口。
- 后台 E2E 已覆盖 App Logs 页面和详情弹窗。

### v1.1-02：图片存储抽象

- 新增图片存储服务层：`app/services/storage.py`。
- 上传路由从“直接写文件”调整为调用 `ImageStorage` 抽象。
- 默认存储后端仍为本地文件：`APP_IMAGE_STORAGE_BACKEND=local`。
- 本地图片保存路径、URL 结构、大小限制和类型校验保持兼容。
- 新增 `LocalImageStorage`，后续可替换为 S3、OSS、R2 等对象存储适配器。
- 新增图片类型检测、上传校验和本地写入的服务测试。
- 动态发布图片 URL 校验已收口到 storage helper。

### v1.1-03：支付回调验证层

- 新增支付回调验证服务：`app/services/payment_webhook_verification.py`。
- 新增配置项：`PAYMENT_WEBHOOK_VERIFICATION_MODE`，默认 `local`，保持本地模拟回调兼容。
- 新增 `shared_secret` 模式，通过 `X-App-Payment-Webhook-Secret` 请求头校验共享密钥。
- 新增配置项：`PAYMENT_WEBHOOK_SHARED_SECRET`，启用 `shared_secret` 时必须配置。
- Apple IAP 和 Google Play 回调在写入支付事件、更新订单状态前先执行验证。
- 共享密钥缺失或错误时返回 403，订单状态不会被更新。
- 该层是本地/内网/代理场景的基础防护，不等同于 Apple/Google 官方生产级 JWS、Pub/Sub 或票据校验。

## 已验证

```text
uv run ruff check app tests: pass
uv run mypy app: pass
uv run python -m compileall app tests: pass
uv run pytest: 110 passed
uv run pytest tests/services/test_storage.py tests/api/routes/test_app_users_contents.py: 17 passed
uv run pytest tests/services/test_payment_webhook_verification.py tests/api/routes/test_app_orders_payments.py: 15 passed
curl -s http://127.0.0.1:8000/api/v1/openapi.json -o frontend/openapi.json: pass
bun run generate-client: pass
bunx @tanstack/router-cli generate: pass
bun run lint: pass
bun run build: pass
Playwright React 后台页面冒烟测试: pass
bunx playwright test tests/app-admin.spec.ts --project=chromium: 7 passed
curl -I http://127.0.0.1:8000/docs: 200 OK
curl http://localhost:5173/app-users: 200 OK
HTTP 配置冒烟测试: pass
HTTP 订单支付冒烟测试: pass
HTTP 支付回调 shared-secret 冒烟测试: pass
HTTP 图片上传存储冒烟测试: pass
Runbook API 抽样验收: pass
```

## 当前本地服务

```text
Frontend: http://localhost:5173
Backend API: http://localhost:8000
Swagger Docs: http://localhost:8000/docs
PostgreSQL: localhost:5432
Mailpit: http://localhost:8025
```

## 下一阶段建议

1. 继续补 Apple/Google 官方生产级 JWS、Pub/Sub 或票据校验。
2. 增加 S3、OSS 或 R2 对象存储适配器。
3. 根据 App 首版真实字段补齐动态、订单和运营配置的业务校验。
