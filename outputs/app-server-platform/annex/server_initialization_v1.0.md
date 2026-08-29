# server 项目初始化记录 v1.0

## 项目位置

```text
/Users/liqihui/Documents/Codex/2026-08-22/new-chat/server
```

## 初始化来源

```text
remote: https://github.com/fastapi/full-stack-fastapi-template.git
commit: 68adb40
clone: shallow clone
```

## 已完成

- 已创建 `server/` 项目目录。
- 已拉取 FastAPI full-stack 模板。
- 已将项目名改为 `App Server Platform`。
- 已同步后端依赖。
- 已创建 Python 虚拟环境 `server/.venv`。
- 已验证 Docker、Docker Compose、Bun 可用。
- 已完成前端依赖安装和构建。
- 已启动本地 PostgreSQL 与 Mailpit。
- 已完成数据库初始化和 Alembic 迁移。
- 已实现 App 设备号登录、资料修改、本地图片上传、动态发布/动态流、后台用户和内容治理 API。
- 已实现 App 订单 API、后台订单查询 API、Apple IAP 与 Google Play 本地模拟回调。
- 已实现后台 key-value 运营配置 API 和 App 启动拉取接口。
- 已实现 React 后台 App 用户、动态、订单、运营配置页面。
- 已运行后端 `ruff`、`mypy`、编译检查和完整测试。
- 已运行前端 OpenAPI client 生成、路由生成、lint、生产构建和页面冒烟测试。
- 已整理本地联调 runbook、模拟支付 curl 示例和手工验收清单。
- 已新增并通过 React 后台 E2E 验收测试。
- 已实现后台操作日志 API、日志表和 React App Logs 页面。
- 已抽象图片存储服务层，默认保持本地文件存储。
- 已实现支付回调 `local` / `shared_secret` 验证层，默认保持本地模拟兼容。

## 验证结果

```text
uv sync: pass
bun install: pass
bun run build: pass
docker compose up -d db mailpit: pass
uv run bash scripts/prestart.sh: pass
uv run alembic upgrade head: pass
uv run ruff check app tests: pass
uv run mypy app: pass
uv run python -m compileall app tests: pass
uv run pytest: 110 passed
uv run pytest tests/services/test_storage.py tests/api/routes/test_app_users_contents.py: 17 passed
uv run pytest tests/services/test_payment_webhook_verification.py tests/api/routes/test_app_orders_payments.py: 15 passed
bun run generate-client: pass
bunx @tanstack/router-cli generate: pass
bun run lint: pass
bun run build: pass
Playwright React 后台页面冒烟测试: pass
bunx playwright test tests/app-admin.spec.ts --project=chromium: 7 passed
HTTP 图片上传存储冒烟测试: pass
HTTP 支付回调 shared-secret 冒烟测试: pass
Runbook API 抽样验收: pass
```

## 当前本地服务

```text
PostgreSQL: localhost:5432
Mailpit: http://localhost:8025
Backend API: http://localhost:8000
Swagger Docs: http://localhost:8000/docs
Frontend: http://localhost:5173
```

## 启动命令

```bash
cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server
docker compose up -d db mailpit

cd backend
uv run bash scripts/prestart.sh
uv run fastapi dev
```

另开终端启动前端：

```bash
cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server
bun install
bun run dev
```

## 下一步

进入下一阶段。

优先实现：

- v1.1 生产化评估：Apple/Google 官方生产级验签或票据校验、对象存储适配器。
- 接入真实移动 App 后，按 `annex/local_runbook_v1.0.md` 做设备端人工联调。
