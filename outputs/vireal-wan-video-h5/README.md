# Vireal 双模式视频 H5 产品文档

当前开发基线：v1.1（产品评审已通过，尚未部署）

## 交付物

- `prd/prd_v1.1.html`：当前双模式最终产品需求文档，包含 Mermaid 流程图与 Focus 模式原型切片。
- `prd/prd_v1.0.html`：历史 Wan 单模式产品需求文档。
- `prototype/prototype_v1.1.html`：当前双模式单文件 Tailwind Web/H5 高保真交互原型。
- `prototype/prototype_v1.0.html`：历史参考版本，不再作为 Pages 构建入口。
- `flowcharts/*_v1.1.mmd`：双模式用户路径、生成时序、配额降级、任务状态、媒体生命周期与系统架构。
- `annex/requirements_baseline_v1.0.md`：经确认的需求基线。
- `annex/technical_design_v1.0.md`：与现有 FastAPI 项目对齐的系统、数据、接口和异步任务设计。
- `annex/wan_poc_plan_v1.0.md`：Wan 双人/单人动作的分阶段付费 PoC 计划与验收口径。
- `annex/implementation_backlog_v1.0.md`：可进入迭代排期的 Epic、故事、依赖和完成定义。
- `annex/unit_economics_v1.0.md`：按 2026-09-09 官方价格测算的单次模型成本和金币风险。
- `templates/prd_template.md`：后续版本的 PRD 结构模板。

## 原型路由

- `#home`：落地页
- `#login`：登录
- `#create`：创作
- `#generation`：生成进度
- `#works`：作品记录
- `#wallet`：PayPal 与金币
- `#account`：账户设置
- `#region-locked`：地区限制

## Cloudflare Pages 部署

生产构建会把 API Origin 注入页面，并默认启用真实后端模式。本地原型文件仍可继续使用查询参数覆盖配置。

> v1.1 已表达新的 `mode`、`upload_ids`、执行类型、额度和演示降级合同。在匹配的后端实现、数据库迁移和 Worker 完成并通过测试前，不得部署 v1.1；当前构建切换仅用于本地验收。

Cloudflare Pages 项目配置：

```text
Production branch: master
Root directory: /
Build command: bash scripts/build-vireal-pages.sh
Build output directory: dist/vireal-pages
Environment variable: VIREAL_API_BASE_URL=https://api.usevireal.com
```

本地验证生产构建：

```bash
VIREAL_API_BASE_URL=https://api.usevireal.com bash scripts/build-vireal-pages.sh
python3 -m http.server 5173 --directory dist/vireal-pages
```

打开 `http://localhost:5173` 时页面会使用构建时注入的 HTTPS API。Cloudflare Pages 绑定 `app.example.com` 后，需要把该完整 Origin 同时加入后端 `BACKEND_CORS_ORIGINS`。

使用 `?sandbox=true&focus=功能编号` 可进入专注模式。v1.1 的双模式评审入口为：

- `prototype_v1.1.html?sandbox=true&focus=mode#create`
- `prototype_v1.1.html?sandbox=true&focus=duration#create`
- `prototype_v1.1.html?sandbox=true&focus=generation#create`

## 版本规则

历史版本不得覆盖。v1.1 原型、Mermaid 流程图和最终 PRD 已完成；后续改动应新增版本文件，并同步更新实现计划、测试与版本记录。
