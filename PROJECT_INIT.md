# App Server Platform 初始化记录

## 初始化结果

本项目已基于 FastAPI 官方 `full-stack-fastapi-template` 初始化到当前工作区的 `server/` 目录。

```text
server/
  backend/
  frontend/
  compose.yml
  compose.override.yml
  compose.deploy.yml
  development.md
  PROJECT_INIT.md
```

## 模板来源

```text
remote: https://github.com/fastapi/full-stack-fastapi-template.git
commit: 68adb40
clone: shallow clone
```

## 已完成

- 已创建 `server/` 项目目录。
- 已拉取 FastAPI full-stack 模板。
- 已将 `.env` 中的 `PROJECT_NAME` 改为 `App Server Platform`。
- 已同步后端 Python 依赖。
- 已创建虚拟环境：`server/.venv`。
- 已验证 Docker、Docker Compose、Bun 可用。
- 已完成 `bun install` 和 `bun run build`。
- 已启动本地 PostgreSQL 与 Mailpit。
- 已运行 `scripts/prestart.sh`，完成初始化数据和 Alembic 迁移。
- 已实现 App 设备号登录、App token 鉴权。
- 已实现 App 资料查询/修改、本地图片上传、动态发布、动态流和动态详情。
- 已实现后台 App 用户列表、禁用、软删除，以及动态列表、软删除。
- 已实现 App 订单 API、后台订单查询 API、Apple IAP 与 Google Play 本地模拟回调。
- 已实现后台 key-value 运营配置 API 和 App 启动拉取接口。
- 已实现 React 后台 App 用户、动态、订单、运营配置页面。
- 已运行后端静态检查、类型检查、编译检查和完整测试。
- 已运行前端 OpenAPI client 生成、路由生成、lint、生产构建和页面冒烟测试。
- 已整理本地联调 runbook、模拟支付 curl 示例和手工验收清单。
- 已新增并通过 React 后台 E2E 验收测试。
- 已实现后台操作日志 API、日志表和 React App Logs 页面。
- 已抽象图片存储服务层，默认保持本地文件存储。
- 已实现支付回调 `local` / `shared_secret` 验证层。

## 当前本机环境

```text
uv: available
Python: 3.14.3
Docker: 29.7.2
Docker Compose: v5.4.0
Bun: 1.4.0
```

## 本地启动状态

数据库和 Mailpit 已通过 Docker Compose 启动：

```text
PostgreSQL: localhost:5432
Mailpit SMTP: localhost:1025
Mailpit Web: http://localhost:8025
```

后端已启动：

```text
Backend API: http://localhost:8000
Swagger Docs: http://localhost:8000/docs
```

常用启动命令：

```bash
cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server
docker compose up -d db mailpit

cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server/backend
uv run bash scripts/prestart.sh
uv run fastapi dev

cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server
bun install
bun run dev
```

常用地址：

```text
Frontend: http://localhost:5173
Backend API: http://localhost:8000
Swagger Docs: http://localhost:8000/docs
Mailpit: http://localhost:8025
```

## 与 PRD 的改造方向

### 后台管理员

沿用模板已有用户、密码哈希、JWT 登录和 React 后台基础能力。

### App 用户

已新增独立 App 用户体系，不与后台管理员共表：

- `app_user`
- `app_device`
- App token 鉴权依赖

### API 分组

已新增：

```text
/api/v1/app/*
/api/v1/admin/app/*
/api/v1/webhooks/payments/*
```

### 业务模块

已实现：

- 设备 UUID 登录
- 头像昵称修改
- 本地图片上传
- 文字/图片动态
- 后台用户和内容治理
- key-value 运营配置
- App 订单创建和订单状态查看
- Apple IAP、Google Play 本地模拟回调
- 支付事件幂等处理
- React 后台 App 用户、动态、订单、配置页面
- 后台操作日志 API 和 App Logs 页面
- 图片存储服务抽象，默认保持本地文件存储
- 支付回调 shared-secret 基础防护

## 下一步建议

进入下一阶段：

1. 准备生产化事项：Apple/Google 官方生产级验签或票据校验、对象存储适配器。
2. 接入真实移动 App 后，按输出目录中的 `annex/local_runbook_v1.0.md` 做设备端人工联调。
