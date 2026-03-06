# CoPaw 本地开发操作指南

## 项目结构速览

```
CoPaw/
├── src/copaw/          # Python 后端（FastAPI + CLI）
│   ├── cli/            # CLI 命令（copaw init / app / channels / cron ...）
│   ├── app/            # FastAPI 应用（_app.py 入口）
│   │   ├── channels/   # 多通道适配（DingTalk/Feishu/QQ/Discord/iMessage）
│   │   ├── crons/      # 定时任务
│   │   ├── routers/    # API 路由
│   │   ├── runner/     # Agent 运行器
│   │   └── mcp/        # MCP 客户端
│   ├── agents/         # Agent 逻辑 + Skills
│   ├── config/         # 配置加载/保存
│   ├── providers/      # LLM Provider 管理
│   └── envs/           # 环境变量管理
├── console/            # 前端 Console（React + Vite + Ant Design）
│   └── src/
│       ├── api/        # API 请求层
│       ├── components/ # 组件
│       ├── pages/      # 页面
│       └── locales/    # i18n
├── website/            # 官网（React + Vite，独立项目）
├── deploy/             # Docker 部署（Dockerfile + Makefile）
└── scripts/            # 安装/构建脚本
```

## 前置依赖

- Python 3.10+（推荐 3.12）
- Node.js 20+
- uv（Python 包管理器，`brew install uv`）
- npm（Console 前端用 npm）
- pnpm（Website 用 pnpm，可选）

---

## 一、后端启动

### 1. 安装 Python 依赖

```bash
cd /Users/evan/code/mazeai/CoPaw
uv pip install -e ".[dev]"
```

### 2. 初始化配置

```bash
copaw init
```

交互式引导你配置：
- LLM Provider（**必填**，选模型 + 填 API Key）
- Heartbeat 心跳间隔（默认 30m）
- Channels（iMessage/Discord/DingTalk/Feishu/QQ/Console）
- Skills（默认全部开启）
- 环境变量

配置文件落在 `~/.copaw/` 目录下。

> 快速跳过交互：`copaw init --defaults --accept-security`

### 3. 启动后端服务

```bash
copaw app
```

默认监听 `http://127.0.0.1:8088`。

常用参数：
```bash
copaw app --host 0.0.0.0 --port 3000    # 自定义地址
copaw app --reload                       # 开发模式热重载
copaw app --log-level debug              # 调试日志
```

---

## 二、Console 前端启动（开发模式）

Console 是 CoPaw 的聊天管理界面，技术栈：React 18 + Vite + Ant Design + TypeScript。

### 1. 安装依赖

```bash
cd /Users/evan/code/mazeai/CoPaw/console
npm install
```

### 2. 配置后端地址

在 `console/` 目录下创建 `.env` 文件：

```env
BASE_URL=http://127.0.0.1:8088
```

> 不配置的话，默认走同源（same-origin），只有在前后端分离开发时才需要设置。

### 3. 启动开发服务器

```bash
npm run dev
```

前端跑在 `http://localhost:5173`，热更新。

### 4. 构建生产版本

```bash
npm run build         # 输出到 console/dist/
```

构建产物会被后端 FastAPI 以静态文件形式服务，访问 `http://127.0.0.1:8088/` 即可看到 Console 界面。

---

## 三、Website 官网启动（独立项目，可选）

Website 是 CoPaw 的产品官网，和主应用无关。

```bash
cd /Users/evan/code/mazeai/CoPaw/website
pnpm install    # 或 npm install
pnpm dev        # 开发模式
pnpm build      # 构建到 website/dist/
```

---

## 四、Docker 一键部署

不想折腾本地环境，直接用 Docker（会自动构建 Console 前端 + 后端）：

```bash
cd /Users/evan/code/mazeai/CoPaw

# 构建镜像（多阶段：先 npm build Console，再装 Python 后端）
make build

# 启动容器
make run

# 查看日志
make logs

# 其他命令
make stop       # 停止
make restart    # 重启
make clean      # 清理镜像+数据卷
make update     # 拉最新代码 → 重建 → 重启
```

默认端口 8088，自定义：`make run PORT=3000`

设置认证（可选）：
```bash
docker run -d \
  -e COPAW_AUTH_USERNAME=myuser \
  -e COPAW_AUTH_PASSWORD=mypassword \
  -p 8088:8088 copaw-auth
```

---

## 五、日常开发速查

| 场景 | 命令 |
|------|------|
| 前后端联调 | 终端 1: `copaw app --reload`<br>终端 2: `cd console && npm run dev` |
| 只改后端 | `copaw app --reload` |
| 只改前端 | `cd console && npm run dev`（配好 `.env` 的 `BASE_URL`） |
| 跑测试 | `pytest`（后端）<br>`npm run lint`（前端） |
| 管理 LLM | `copaw models list` / `copaw models set` |
| 管理 Channels | `copaw channels list` / `copaw channels add` |
| 管理 Skills | `copaw skills list` / `copaw skills enable` |
| 管理环境变量 | `copaw env list` / `copaw env set` |
| 管理定时任务 | `copaw cron list` / `copaw cron add` |

---

## 六、关键环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `COPAW_WORKING_DIR` | 工作目录（配置/数据） | `~/.copaw` |
| `COPAW_LOG_LEVEL` | 日志级别 | `info` |
| `COPAW_CORS_ORIGINS` | CORS 允许域（逗号分隔） | 空（不启用） |
| `COPAW_OPENAPI_DOCS` | 开启 `/docs` Swagger UI | `false` |
| `COPAW_CONSOLE_STATIC_DIR` | Console 静态文件目录 | 自动检测 |
| `COPAW_ENABLED_CHANNELS` | 启用的 channels（逗号分隔） | 全部 |
| `COPAW_AUTH_USERNAME` | 认证用户名（Docker） | `copaw_admin` |
| `COPAW_AUTH_PASSWORD` | 认证密码（Docker） | 内置默认值 |

---

## 七、架构简图

```
浏览器 Console (React)
      │
      ▼ HTTP :5173 (dev) 或 :8088 (prod 同源)
┌─────────────────────────────────────┐
│  FastAPI (_app.py)                  │
│  ├── /api/*        API 路由         │
│  ├── /api/agent/*  AgentApp 路由    │
│  └── /*            Console 静态文件  │
│                                     │
│  AgentRunner (LLM 调用 + Skills)    │
│  ChannelManager (多通道收发消息)      │
│  CronManager (定时任务)              │
│  MCPClientManager (MCP 工具)        │
└─────────────────────────────────────┘
      │
      ▼ 消息推送
  DingTalk / Feishu / QQ / Discord / iMessage / Console
```

---
- [ ] 已读
