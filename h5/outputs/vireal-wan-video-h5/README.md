# Vireal 动态效果与 AI 视频 H5 产品文档

当前开发基线：v1.2（产品评审已通过，生产实现位于 `h5/src`）

## 交付物

- `prd/prd_v1.2.html`：当前最终产品需求文档，包含 Mermaid 流程图与 Focus 模式原型切片。
- `prd/prd_v1.0.html`：历史 Wan 单模式产品需求文档。
- `prototype/prototype_v1.2.html`：不可修改的最终视觉基准。
- `../../src/vireal-v1.2.html` 与 `../../src/vireal-app.js`：接入真实 API 与 Clerk 的生产 H5 源码。
- `prototype/prototype_v1.0.html`：历史参考版本，不再作为 Pages 构建入口。
- `flowcharts/*_v1.2.mmd`：目录浏览、生成提交、任务生命周期、钱包入口和后台发布流程。
- `annex/requirements_baseline_v1.0.md`：经确认的需求基线。
- `annex/technical_design_v1.0.md`：与现有 FastAPI 项目对齐的系统、数据、接口和异步任务设计。
- `annex/wan_poc_plan_v1.0.md`：Wan 双人/单人动作的分阶段付费 PoC 计划与验收口径。
- `annex/implementation_backlog_v1.0.md`：可进入迭代排期的 Epic、故事、依赖和完成定义。
- `annex/unit_economics_v1.0.md`：按 2026-09-09 官方价格测算的单次模型成本和金币风险。
- `templates/prd_template.md`：后续版本的 PRD 结构模板。

## 原型路由

- `#home`：落地页
- `#login`：登录
- `#generate?category=<slug>&video=<slug>`：效果详情与创作
- `#generation?id=<task-id>`：生成进度
- `#works`：作品记录
- `#wallet`：真实金币余额、额度与流水
- `#account`：账户设置
- `#region-locked`：地区限制

## Cloudflare Pages 部署

生产构建会把 API Origin 注入页面，并默认启用真实后端模式。本地原型文件仍可继续使用查询参数覆盖配置。

> 生产构建以 v1.2 源码为入口，并在 `dist/vireal-pages/fallback/v1.1/` 保留 v1.1 回退产物。回退只替换 H5，数据库增量结构和兼容 API 保留。

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
VIREAL_API_BASE_URL=https://api.usevireal.com \
VITE_CLERK_PUBLISHABLE_KEY=pk_live_replace-me \
bash scripts/build-vireal-pages.sh
python3 -m http.server 5173 --directory dist/vireal-pages
```

打开 `http://localhost:5173` 时页面会使用构建时注入的 HTTPS API。Cloudflare Pages 绑定 `app.example.com` 后，需要把该完整 Origin 同时加入后端 `BACKEND_CORS_ORIGINS`。

原型评审入口为：

- `prototype_v1.2.html?review=1#home`
- `prototype_v1.2.html?review=1#generate?category=kiss&video=kiss-1`
- `prototype_v1.2.html?review=1#wallet`

## 版本规则

历史版本和 v1.2 视觉基准不得覆盖。后续改动应新增版本文件，并同步更新实现、迁移、测试与版本记录。
