# 版本迭代规范

## 适用范围

本规范适用于 `app-server-platform` 后续从 v1.0 升级到 v1.1、v1.2 等版本时的 PRD、原型和流程图管理。

## 核心原则

1. 不直接覆盖历史版本。
2. 每次版本迭代先复制上一版文件，再在新文件中修改。
3. PRD、原型、流程图版本必须一一对应。
4. PRD 内的 iframe 原型路径必须指向同版本原型。
5. PRD 版本记录必须写清新增、修改、下线和风险点。

## v1.1 迭代步骤

### 1. 复制文件

```text
prd/prd_final_v1.0.html -> prd/prd_final_v1.1.html
prototype/prototype_v1.0.html -> prototype/prototype_v1.1.html
flowcharts/flowcharts_v1.0.html -> flowcharts/flowcharts_v1.1.html
flowcharts/flowcharts_v1.0.md -> flowcharts/flowcharts_v1.1.md
```

如有单独 Mermaid 源文件，也按功能复制：

```text
flowcharts/app_device_login_v1.0.mmd -> flowcharts/app_device_login_v1.1.mmd
```

### 2. 更新 PRD 内版本信息

需要修改：

- 页面标题
- 文档版本
- 版本记录表
- 右上角版本切换器
- 附件路径
- 所有 iframe 原型路径

iframe 示例：

```html
<iframe src="../prototype/prototype_v1.1.html?focus=app-compose#app-compose"></iframe>
```

### 3. 更新原型版本信息

需要修改：

- 页面版本标识
- 新增或变更的页面和交互状态
- focus 模式支持的功能 ID
- 与 PRD 切片一致的 hash 路由

### 4. 更新流程图

每个发生业务逻辑变化的模块都要同步更新 Mermaid。

优先更新：

- 用户主流程变化
- 后台操作变化
- 支付状态变化
- 异常分支变化
- 配置下发规则变化

### 5. 验证

每次版本交付前至少检查：

- PRD 能打开
- Mermaid 能渲染
- iframe 能加载对应版本原型
- focus 模式能锁定无关交互
- 版本切换器能跳转历史版本和当前版本
- 不存在指向旧版本原型的 iframe

## 版本记录模板

| 版本 | 日期 | 类型 | 变更说明 | 影响范围 | 风险 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| v1.1 | YYYY-MM-DD | 新增 | 说明新增功能 | PRD、原型、后端 API | 待评估 | 草稿 |

## 变更类型

- 新增：新增功能、页面、接口、流程。
- 修改：调整已有规则、字段、交互、状态。
- 下线：移除功能、入口、接口、字段。
- 修复：修正文档错误、流程遗漏、原型问题。
- 技术：仅涉及技术实现或工程结构。
