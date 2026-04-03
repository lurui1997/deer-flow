# DeerFlow 2.0 架构设计实现方案调研报告

> **项目名称**: DeerFlow (Deep Exploration and Efficient Research Flow)  
> **版本**: 2.0 (完全重写，与 v1 无共享代码)  
> **开源组织**: 字节跳动 (ByteDance)  
> **许可证**: MIT  
> **调研日期**: 2026-03-27  

---

## 一、项目定位与核心理念

### 1.1 项目定位

DeerFlow 2.0 定位为**超级智能体调度框架 (Super Agent Harness)**，通过编排**子智能体 (Sub-Agents)**、**记忆 (Memory)**和**沙箱 (Sandbox)**来执行复杂任务，由可扩展的**技能系统 (Skills)**驱动。

### 1.2 核心设计理念

| 理念 | 实现方式 |
|------|----------|
| **可插拔一切** | 模型、工具、搜索引擎、沙箱、护栏均通过 `use: package.module:ClassName` 动态加载 |
| **分离关注点** | Gateway API (辅助服务) 与 LangGraph Server (Agent执行) 分离 |
| **技能即文档** | Skills 以 `SKILL.md` Markdown 为核心，配合脚本和参考资料 |
| **嵌入式优先** | `DeerFlowClient` 支持不启动服务器直接在 Python 中使用 |
| **上下文工程** | 13 个中间件构成处理管道，精细管控 Agent 上下文 |

---

## 二、整体架构概览

### 2.1 顶层架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                         Nginx (端口 2026)                        │
│                        统一入口 · 反向代理                        │
└────────┬──────────────────┬─────────────────────┬────────────────┘
         │                  │                     │
    ┌────▼─────┐    ┌──────▼───────┐    ┌────────▼─────────┐
    │ Frontend  │    │  Gateway API │    │  LangGraph Server │
    │ Next.js 16│    │ FastAPI:8001 │    │  LangGraph:2024   │
    │ React 19  │    │  辅助服务层   │    │  Agent 执行引擎    │
    └──────────┘    └──────────────┘    └────────┬─────────┘
                                                  │
                         ┌────────────────────────┼──────────────┐
                         │                        │              │
                  ┌──────▼──────┐  ┌──────────────▼──┐  ┌───────▼───────┐
                  │  Sub-Agents  │  │  Sandbox System  │  │  Skills Engine │
                  │  子智能体执行  │  │  沙箱执行环境     │  │  技能加载系统   │
                  └─────────────┘  └─────────────────┘  └───────────────┘
```

### 2.2 技术栈全景

| 层级 | 技术选型 | 版本要求 |
|------|----------|----------|
| **后端框架** | Python + LangGraph + FastAPI | Python ≥ 3.12 |
| **前端框架** | Next.js + React + TypeScript | Node.js ≥ 22, Next.js 16, React 19 |
| **UI 组件** | Radix UI + Tailwind CSS 4 | — |
| **状态管理** | TanStack Query + React Hooks | — |
| **流程可视化** | XYFlow (ReactFlow) | — |
| **代码编辑器** | CodeMirror 6 | — |
| **包管理** | uv (后端) + pnpm (前端) | — |
| **容器化** | Docker + Nginx + K8s(可选) | — |
| **AI 框架** | LangChain + LangGraph | LangGraph ≥1.0.6 |
| **认证** | Better Auth | — |

---

## 三、后端架构详解

### 3.1 Monorepo Workspace 结构

后端采用 **uv workspace** 管理，核心框架作为独立包发布：

```
backend/
├── pyproject.toml          # 顶层项目 (deer-flow)
│   └── dependencies:
│       ├── deerflow-harness  ← workspace 内部依赖
│       ├── fastapi, uvicorn  ← API 服务
│       ├── lark-oapi         ← 飞书集成
│       ├── slack-sdk         ← Slack 集成
│       └── python-telegram-bot ← Telegram 集成
│
├── app/                    # 应用层 (Gateway + Channels)
│   ├── gateway/            # FastAPI Gateway API
│   └── channels/           # IM 集成层
│
└── packages/
    └── harness/            # 核心框架包 (deerflow-harness)
        ├── pyproject.toml  # 独立发布单元
        └── deerflow/       # 核心代码
```

**设计优势**:
- `deerflow-harness` 可独立安装使用，不依赖 Gateway
- 清晰分离"框架"与"应用"两层关注点
- 便于社区扩展和独立版本管理

### 3.2 双进程架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        后端双进程架构                             │
├─────────────────────────────┬───────────────────────────────────┤
│                             │                                   │
│   Gateway API (FastAPI)     │    LangGraph Server               │
│   端口: 8001                │    端口: 2024                      │
│                             │                                   │
│   ◆ 模型列表查询            │    ◆ Agent 核心执行引擎             │
│   ◆ 长期记忆管理            │    ◆ 对话线程管理                   │
│   ◆ 技能管理 (CRUD)        │    ◆ 流式响应                      │
│   ◆ MCP 服务器配置          │    ◆ Checkpoint 状态持久化          │
│   ◆ 文件上传               │    ◆ 子智能体调度                   │
│   ◆ Agent 自定义管理        │                                   │
│   ◆ IM 频道服务             │                                   │
│   ◆ 建议 API               │                                   │
│                             │                                   │
│   入口: app.gateway.app:app │    入口: deerflow.agents:          │
│                             │          make_lead_agent           │
└─────────────────────────────┴───────────────────────────────────┘
```

**Gateway API 路由清单** (10 个路由模块):

| 路由模块 | 功能 |
|----------|------|
| `agents.py` | Agent 管理 (创建/列表/详情/更新/删除自定义 Agent) |
| `artifacts.py` | 产物管理 (文件预览/下载/产物 URL) |
| `channels.py` | IM 频道管理 |
| `mcp.py` | MCP 服务器配置管理 |
| `memory.py` | 长期记忆 API (查询/清除/导出) |
| `models.py` | 模型列表查询 |
| `skills.py` | 技能管理 (列表/安装/卸载/更新) |
| `suggestions.py` | 建议 API |
| `threads.py` | 对话线程管理 |
| `uploads.py` | 文件上传管理 |

### 3.3 Lead Agent 中间件管道

Lead Agent 的核心设计是 **13 个中间件** 构成的处理管道，每个中间件负责一个独立关注点：

```
用户请求
    │
    ▼
┌─────────────────────────────────────────────────┐
│            Lead Agent 中间件管道                   │
├─────────────────────────────────────────────────┤
│                                                 │
│  1. ThreadDataMiddleware     线程数据初始化       │
│  2. UploadsMiddleware        上传文件处理         │
│  3. MemoryMiddleware         长期记忆注入         │
│  4. ViewImageMiddleware      图片查看处理         │
│  5. ClarificationMiddleware  澄清追问处理         │
│  6. TodoMiddleware           TODO 列表管理        │
│  7. TitleMiddleware          自动标题生成         │
│  8. TokenUsageMiddleware     Token 用量追踪       │
│  9. LoopDetectionMiddleware  循环检测防护          │
│  10. SubagentLimitMiddleware 子智能体数量限制      │
│  11. DanglingToolCallMiddleware 悬挂工具调用处理   │
│  12. DeferredToolFilterMiddleware 延迟工具过滤     │
│  13. ToolErrorHandlingMiddleware 工具错误处理      │
│  14. SummarizationMiddleware 对话摘要 (LangChain) │
│                                                 │
│  + GuardrailsMiddleware (可选) 安全护栏           │
│                                                 │
└─────────────────────────────────────────────────┘
    │
    ▼
  LLM 推理 → 工具调用 → 子智能体执行 → 流式输出
```

**中间件职责详解**:

| 中间件 | 核心职责 | 关键机制 |
|--------|----------|----------|
| **ThreadData** | 初始化线程工作目录和数据 | 确保 workspace/uploads/outputs 路径就绪 |
| **Uploads** | 处理用户上传的文件 | 文件转换、多模态输入处理 |
| **Memory** | 注入长期记忆到 System Prompt | 基于置信度阈值过滤，最大 Token 限制 |
| **ViewImage** | 将图片 Base64 注入消息 | 支持 Vision 模型的图片理解 |
| **Clarification** | 向用户追问澄清 | 当信息不足时主动追问 |
| **Todo** | 管理任务列表 | 追踪子任务进度 |
| **Title** | 自动生成对话标题 | 异步生成，不阻塞主流程 |
| **TokenUsage** | 追踪 Token 使用量 | 按模型统计 input/output tokens |
| **LoopDetection** | 检测和打破循环 | 防止 Agent 陷入无限循环 |
| **SubagentLimit** | 限制并发子智能体数量 | 防止资源耗尽 |
| **DanglingToolCall** | 处理悬挂的工具调用 | 清理未完成的工具调用状态 |
| **DeferredToolFilter** | 延迟工具加载过滤 | 减少 Context 中的工具定义 |
| **ToolErrorHandling** | 工具执行错误恢复 | 优雅降级，防止单工具失败导致整体失败 |
| **Summarization** | 对话历史摘要 | 在 Token 接近上限时自动触发 |

### 3.4 子智能体执行引擎

```python
# 子智能体状态机
class SubagentStatus(Enum):
    PENDING = "pending"       # 等待执行
    RUNNING = "running"       # 执行中
    COMPLETED = "completed"   # 执行完成
    FAILED = "failed"         # 执行失败
    TIMED_OUT = "timed_out"   # 执行超时
```

**执行架构**:
- 使用 `ThreadPoolExecutor` 并行执行子智能体
- 每个子智能体拥有独立的 `task_id` 和 `trace_id`
- 支持可配置的超时机制 (默认 900s = 15分钟)
- 支持 per-agent 超时覆盖

**内置子智能体**:
- `general-purpose`: 通用多步骤任务执行
- `bash`: 快速命令执行

### 3.5 工具系统

```
工具系统分层架构
├── 内置工具 (BUILTIN_TOOLS)
│   ├── present_file_tool    文件展示
│   └── ask_clarification_tool 追问工具
│
├── 子智能体工具 (SUBAGENT_TOOLS)
│   └── task_tool            任务分发
│
├── 配置工具 (config.yaml 定义)
│   ├── web_search           Web 搜索
│   ├── web_fetch            网页抓取
│   ├── image_search         图片搜索
│   ├── ls / read_file       文件读取
│   ├── write_file / str_replace 文件写入
│   └── bash                 Shell 执行
│
├── MCP 工具 (extensions_config.json 定义)
│   ├── filesystem MCP       文件系统
│   ├── github MCP           GitHub 操作
│   └── postgres MCP         数据库操作
│
├── ACP Agent 工具
│   ├── Claude Code ACP      代码实现/调试
│   └── Codex ACP            代码生成
│
└── 延迟加载工具 (Tool Search)
    └── 按需搜索和加载 MCP 工具
```

**动态加载机制**:
```yaml
# config.yaml 中的工具定义
tools:
  - name: web_search
    group: web
    use: deerflow.community.ddg_search.tools:web_search_tool  # 动态解析路径
    max_results: 5
```

所有工具通过 `use: package.module:ClassName` 路径动态解析加载，使用 `resolve_variable()` 反射机制实现。

### 3.6 模型提供商系统

```
模型系统架构
├── 标准 LangChain 提供商
│   ├── langchain_openai:ChatOpenAI          ← OpenAI / OpenRouter / 兼容网关
│   ├── langchain_anthropic:ChatAnthropic    ← Claude
│   └── langchain_google_genai:ChatGoogleGenerativeAI ← Gemini (原生)
│
├── 适配/补丁提供商 (deerflow.models)
│   ├── PatchedChatDeepSeek     ← DeepSeek (thinking support)
│   ├── PatchedChatOpenAI       ← Gemini via OpenAI 网关 (thought_signature)
│   └── PatchedChatMiniMax      ← MiniMax 适配
│
├── CLI 提供商
│   ├── ClaudeChatModel         ← Claude Code CLI (OAuth)
│   └── CodexChatModel          ← OpenAI Codex CLI
│
└── 凭证加载器 (credential_loader.py)
    └── 环境变量 / 文件 / CLI 凭证统一管理
```

**支持的模型供应商**:
OpenAI、Anthropic、Google Gemini、DeepSeek、Kimi (Moonshot)、MiniMax、Novita AI、OpenRouter、Volcengine (豆包)、Codex CLI、Claude Code CLI

### 3.7 长期记忆系统

```
记忆系统架构
├── MemoryUpdater (updater.py)
│   └── 从对话中提取事实并存储
│
├── MemoryQueue (queue.py)
│   └── 去抖动队列 (debounce 30s)
│
├── MemoryStorage (storage.py)
│   └── JSON 文件持久化 (memory.json)
│
├── MemoryPrompt (prompt.py)
│   └── 记忆提取 / 注入 Prompt 模板
│
└── MemoryMiddleware
    └── 在 System Prompt 中注入相关记忆
```

**关键参数**:
- `max_facts: 100` — 最多存储 100 条事实
- `fact_confidence_threshold: 0.7` — 置信度阈值
- `max_injection_tokens: 2000` — 注入 Token 上限
- `debounce_seconds: 30` — 去抖动延迟

### 3.8 沙箱系统

```
沙箱系统分层
├── SandboxProvider (抽象接口)
│   └── sandbox_provider.py
│
├── Option 1: LocalSandboxProvider
│   └── 直接在主机执行命令 (默认)
│
├── Option 2: AioSandboxProvider (容器沙箱)
│   ├── local_backend.py   ← Docker / Apple Container
│   └── remote_backend.py  ← K8s Provisioner
│
└── Option 3: K8s Provisioner (生产级)
    └── provisioner/app.py ← 管理 Pod 生命周期
        ├── 创建 Pod + Service
        ├── NodePort 端口映射
        └── 自动清理过期沙箱
```

**沙箱工具** (sandbox/tools.py, 34.19 KB — 最大单文件):
- `ls_tool` — 目录列表
- `read_file_tool` — 文件读取
- `write_file_tool` — 文件写入
- `str_replace_tool` — 文本替换
- `bash_tool` — Shell 执行

### 3.9 安全护栏系统

```
护栏系统
├── GuardrailsMiddleware
│   └── 每个工具调用前执行检查
│
├── Option 1: AllowlistProvider (内置)
│   └── denied_tools 黑名单
│
├── Option 2: OAP Provider (开放标准)
│   └── Open Agent Passport 协议
│
└── Option 3: Custom Provider
    └── 自定义 evaluate/aevaluate 方法
```

### 3.10 配置系统

配置系统采用 **高度模块化** 设计，20 个独立配置模块：

| 配置模块 | 职责 |
|----------|------|
| `app_config.py` | 主配置解析 (config.yaml) |
| `agents_config.py` | Agent 配置 |
| `acp_config.py` | ACP Agent 配置 |
| `checkpointer_config.py` | 状态持久化配置 |
| `extensions_config.py` | MCP + Skills 扩展配置 |
| `guardrails_config.py` | 安全护栏配置 |
| `memory_config.py` | 长期记忆配置 |
| `model_config.py` | 模型配置 |
| `paths.py` | 路径管理 |
| `sandbox_config.py` | 沙箱配置 |
| `skills_config.py` | 技能配置 |
| `subagents_config.py` | 子智能体配置 |
| `summarization_config.py` | 摘要配置 |
| `title_config.py` | 标题生成配置 |
| `token_usage_config.py` | Token 用量配置 |
| `tool_config.py` | 工具配置 |
| `tool_search_config.py` | 工具搜索配置 |
| `tracing_config.py` | LangSmith 追踪配置 |

**配置版本管理**: `config_version: 3`，支持 `make config-upgrade` 自动合并新字段。

---

## 四、前端架构详解

### 4.1 技术架构

```
前端分层架构
├── app/                    # Next.js 16 App Router (页面路由)
│   ├── layout.tsx          # 根布局
│   ├── page.tsx            # Landing 首页
│   ├── api/auth/           # Better Auth 认证
│   ├── mock/api/           # 开发用 Mock API
│   └── workspace/          # 主工作区
│       ├── agents/         # Agent 管理
│       └── chats/          # 对话页
│
├── components/             # UI 组件层
│   ├── ai-elements/        # AI 交互元素 (核心)
│   ├── workspace/          # 工作区组件
│   ├── landing/            # 首页组件
│   └── ui/                 # 基础 UI 库 (30+ Radix 组件)
│
├── core/                   # 核心业务逻辑层
│   ├── api/                # API 客户端 + 流模式
│   ├── threads/            # 对话线程管理
│   ├── agents/             # Agent API & hooks
│   ├── memory/             # 长期记忆
│   ├── skills/             # 技能管理
│   ├── mcp/                # MCP 配置
│   ├── artifacts/          # 产物管理
│   ├── uploads/            # 文件上传
│   ├── i18n/               # 国际化 (en-US, zh-CN)
│   ├── settings/           # 用户设置
│   ├── streamdown/         # 流式 Markdown
│   └── utils/              # 通用工具
│
├── hooks/                  # 全局 Hooks
├── server/                 # 服务端集成
└── lib/                    # 工具库
```

### 4.2 核心 AI 交互组件

前端最核心的是 `components/ai-elements/` 目录，包含所有 AI 交互元素：

| 组件 | 大小 | 职责 |
|------|------|------|
| `prompt-input.tsx` | 36.93 KB | 提示输入 (最大组件) — 文件上传、模型选择、技能选择等 |
| `message.tsx` | 10.57 KB | 消息渲染 — Markdown/代码/图片/引用 |
| `context.tsx` | 9.53 KB | 上下文面板 — 思维链、推理过程、信息源 |
| `chain-of-thought.tsx` | 6.29 KB | 思维链可视化展示 |
| `web-preview.tsx` | 6.55 KB | 网页预览 (沙箱产物) |
| `queue.tsx` | 6.09 KB | 子任务队列展示 |
| `reasoning.tsx` | 5.12 KB | 推理过程展示 |
| `model-selector.tsx` | 4.72 KB | 模型选择器 |
| `code-block.tsx` | 4.41 KB | 代码块渲染 (Shiki 语法高亮) |
| `plan.tsx` | 3.36 KB | 计划展示 |
| `artifact.tsx` | 3.28 KB | 产物展示 |
| `node.tsx` / `edge.tsx` | — | 流程图节点/边 (XYFlow) |

### 4.3 数据流架构

```
用户输入
    │
    ▼
InputBox → LangGraph SDK → SSE 流式连接 → LangGraph Server
                                │
                                ▼
                        StreamMode 解析
                        ├── messages → 消息更新
                        ├── values → 状态更新  
                        ├── updates → 增量更新
                        └── custom → 自定义事件
                                │
                                ▼
                     TanStack Query 缓存
                                │
                                ▼
                     React 组件树渲染
                     ├── MessageList
                     ├── ChainOfThought
                     ├── ArtifactPanel
                     └── TodoList
```

### 4.4 国际化方案

- 支持 `en-US` 和 `zh-CN` 两种语言
- 基于 Cookie 的语言偏好持久化
- 服务端渲染语言检测
- 类型安全的翻译键 (TypeScript 类型定义 6.78 KB)

---

## 五、技能系统设计

### 5.1 技能标准结构

```
skill-name/
├── SKILL.md              # 技能定义文件 (核心, 含 Prompt + 执行指令)
├── scripts/              # 执行脚本 (Python/JS/Shell)
├── references/           # 参考资料 (Markdown 文档)
├── templates/            # 模板文件
├── agents/               # 子 Agent 定义 (部分技能)
└── assets/               # 静态资源
```

### 5.2 内置技能清单 (18 个)

| 技能 | SKILL.md 大小 | 功能 |
|------|-------------|------|
| **bootstrap** | 4.67 KB | 引导对话 |
| **chart-visualization** | 3.28 KB | 图表可视化 (30+ 图表类型) |
| **claude-to-deerflow** | 6.71 KB | Claude → DeerFlow 迁移 |
| **consulting-analysis** | 32.85 KB | 咨询分析 (最大技能) |
| **data-analysis** | 8.66 KB | 数据分析 (Python) |
| **deep-research** | 7.69 KB | 深度研究 |
| **find-skills** | 4.79 KB | 技能发现与安装 |
| **frontend-design** | 7.24 KB | 前端设计 |
| **github-deep-research** | 4.94 KB | GitHub 深度研究 |
| **image-generation** | 8.70 KB | 图片生成 |
| **podcast-generation** | 7.22 KB | 播客生成 |
| **ppt-generation** | 27.69 KB | PPT 生成 |
| **skill-creator** | 32.39 KB | 技能创建器 (Meta-Skill) |
| **surprise-me** | 2.58 KB | 惊喜模式 |
| **vercel-deploy-claimable** | 3.10 KB | Vercel 部署 |
| **video-generation** | 4.65 KB | 视频生成 |
| **web-design-guidelines** | 1.20 KB | Web 设计规范 |
| **frontend-design** | 7.24 KB | 前端设计 |

### 5.3 技能加载系统

```
技能生命周期
├── loader.py    → 从目录扫描和加载技能
├── parser.py    → 解析 SKILL.md 文件结构
├── types.py     → 技能类型定义
├── validation.py → 技能格式验证
└── installer.py → 技能安装/卸载 (从归档包)
```

---

## 六、IM 频道集成

### 6.1 支持的平台

| 平台 | 连接方式 | 代码量 |
|------|----------|--------|
| **飞书 (Feishu)** | WebSocket | 24.38 KB |
| **Telegram** | 轮询 (Polling) | 12.75 KB |
| **Slack** | Socket Mode | 8.88 KB |

### 6.2 频道架构

```
频道系统
├── base.py          # 频道基类 (抽象接口)
├── manager.py       # 频道管理器 (27.94 KB, 最大模块)
├── message_bus.py   # 消息总线 (发布/订阅)
├── service.py       # 频道服务 (生命周期管理)
├── store.py         # 频道存储 (线程映射)
├── feishu.py        # 飞书实现
├── slack.py         # Slack 实现
└── telegram.py      # Telegram 实现
```

**关键特性**:
- 所有频道使用**出站连接** (WebSocket/轮询)，无需公网 IP
- 支持 per-channel 和 per-user 的会话配置覆盖
- 消息总线模式解耦 Agent 执行与消息投递

---

## 七、部署架构

### 7.1 生产环境 (Docker Compose)

```
docker-compose.yaml (5 个服务)
┌──────────────────────────────────────────────┐
│                                              │
│  nginx (:2026)  ────→  frontend (Next.js)    │
│       │                                      │
│       ├─────────→  gateway (:8001)           │
│       │               FastAPI                │
│       │                                      │
│       └─────────→  langgraph (:2024)         │
│                       Agent 引擎             │
│                                              │
│  provisioner (:8002) [可选, K8s 模式]         │
│       Pod 生命周期管理                         │
│                                              │
│  deer-flow (bridge network)                  │
└──────────────────────────────────────────────┘
```

### 7.2 关键环境变量

| 变量 | 用途 |
|------|------|
| `DEER_FLOW_HOME` | 运行时数据目录 |
| `DEER_FLOW_CONFIG_PATH` | config.yaml 路径 |
| `DEER_FLOW_EXTENSIONS_CONFIG_PATH` | 扩展配置路径 |
| `DEER_FLOW_DOCKER_SOCKET` | Docker socket (DooD 模式) |
| `DEER_FLOW_REPO_ROOT` | 仓库根目录 |
| `BETTER_AUTH_SECRET` | 前端认证密钥 |
| `LANGCHAIN_TRACING_V2` | LangSmith 追踪开关 |

### 7.3 Docker-in-Docker (DooD) 模式

生产环境中，Gateway 和 LangGraph 容器通过挂载 Docker Socket 实现容器沙箱：

```yaml
volumes:
  - ${DEER_FLOW_DOCKER_SOCKET}:/var/run/docker.sock
```

配合路径翻译变量：
- `DEER_FLOW_HOST_BASE_DIR` — 主机数据目录
- `DEER_FLOW_HOST_SKILLS_PATH` — 主机技能目录
- `DEER_FLOW_SANDBOX_HOST` — 沙箱访问主机名

---

## 八、嵌入式客户端

### 8.1 DeerFlowClient

`deerflow.client.DeerFlowClient` (33.48 KB) 是 DeerFlow 的核心客户端，支持无服务器直接使用：

```python
from deerflow.client import DeerFlowClient

# 创建客户端
client = DeerFlowClient()

# 同步聊天
response = client.chat("分析这篇论文", thread_id="my-thread")

# 流式输出
for event in client.stream("你好"):
    print(event)
```

**客户端功能**:
- 完整的 Agent 执行管道 (包括所有中间件)
- 文件上传和产物管理
- 技能安装/卸载
- MCP 服务器配置管理
- 多线程对话管理
- Checkpoint 状态持久化

---

## 九、核心设计模式总结

### 9.1 反射式动态加载

所有可插拔组件通过 `use: package.module:ClassName` 路径动态加载：

```python
# reflection/resolvers.py
def resolve_variable(path: str, expected_type: type) -> Any:
    """解析 'package.module:ClassName' 路径并返回实例"""
```

**应用场景**: 模型、工具、搜索引擎、沙箱提供商、护栏提供商

### 9.2 中间件链模式

LangChain Agent 的中间件链模式，每个中间件独立可拔插：

```python
middlewares = [
    ThreadDataMiddleware(),
    UploadsMiddleware(),
    MemoryMiddleware(),
    # ... 按顺序组装
]
agent = create_agent(model, tools, middlewares=middlewares)
```

### 9.3 Provider 抽象模式

所有外部依赖通过 Provider 接口抽象：

| Provider 接口 | 实现 |
|--------------|------|
| `SandboxProvider` | Local / AioSandbox / Provisioner |
| `GuardrailProvider` | Allowlist / OAP / Custom |
| `CheckpointerProvider` | Memory / SQLite / PostgreSQL |

### 9.4 配置即代码

通过 YAML 配置文件驱动整个系统行为，支持：
- 环境变量引用 (`$OPENAI_API_KEY`)
- 版本化升级 (`config_version: 3`)
- 零代码切换提供商

---

## 十、代码量统计

| 模块 | 文件数 | 说明 |
|------|--------|------|
| **后端核心** (deerflow-harness) | ~90 个 .py | Agent/工具/沙箱/模型/配置 |
| **后端应用** (app/) | ~28 个 .py | Gateway + Channels |
| **前端** (src/) | ~296 个文件 | 138 .tsx, 87 .ts |
| **技能** (skills/) | ~79 个文件 | 54 .md, 16 .py |
| **总计** | **~650+ 文件** | — |

**最大文件 TOP 5**:

| 文件 | 大小 | 模块 |
|------|------|------|
| `prompt-input.tsx` | 36.93 KB | 前端提示输入 |
| `sandbox/tools.py` | 34.19 KB | 沙箱工具 |
| `client.py` | 33.48 KB | 嵌入式客户端 |
| `input-box.tsx` | 32.34 KB | 前端输入框 |
| `aio_sandbox_provider.py` | 28.94 KB | 容器沙箱提供商 |

---

## 十一、架构亮点与设计决策

### 11.1 亮点

1. **双进程分离**: Gateway 处理辅助请求（轻量），LangGraph Server 专注 Agent 执行（重量），互不干扰
2. **中间件可组合**: 13 个中间件可按需开关，灵活组合不同能力
3. **三级沙箱**: 本地 → Docker → K8s，按安全需求逐级升级
4. **嵌入式客户端**: 无需部署服务即可使用完整 Agent 能力
5. **Skill = Markdown**: 降低技能创建门槛，用自然语言定义技能
6. **Tool Search**: 延迟加载 MCP 工具，减少 Context 占用
7. **IM 全通道**: 飞书/Slack/Telegram 一站式接入

### 11.2 关键设计决策

| 决策 | 理由 |
|------|------|
| **Python 3.12+** | 类型系统改进、性能提升、`TypedDict` 支持 |
| **uv workspace** | 比 pip/poetry 更快，支持 monorepo |
| **Next.js 16 + React 19** | Server Components, Turbopack, 性能最优 |
| **LangGraph ≥1.0.6** | 成熟的 Agent 编排框架，原生支持状态图 |
| **Radix UI** | 无样式 Headless 组件，完全可定制 |
| **SQLite checkpointer** | 默认持久化方案，零配置即用 |
| **JSON 记忆存储** | 简单场景无需数据库，生产可切换 PostgreSQL |

---

## 十二、与竞品对比

| 特性 | DeerFlow 2.0 | AutoGPT | CrewAI | LangGraph Studio |
|------|-------------|---------|--------|-----------------|
| **子智能体编排** | ✅ 完整 | ✅ | ✅ | ✅ |
| **容器沙箱** | ✅ 三级 | ❌ | ❌ | ❌ |
| **技能系统** | ✅ 18+ 内置 | ❌ | ❌ | ❌ |
| **长期记忆** | ✅ | ✅ | ❌ | ❌ |
| **IM 集成** | ✅ 3 平台 | ❌ | ❌ | ❌ |
| **嵌入式客户端** | ✅ | ❌ | ✅ | ❌ |
| **安全护栏** | ✅ | ❌ | ❌ | ❌ |
| **MCP 支持** | ✅ | ❌ | ❌ | ✅ |
| **ACP 支持** | ✅ | ❌ | ❌ | ❌ |
| **完整前端** | ✅ 专业级 | ✅ 基础 | ❌ | ✅ 基础 |

---

## 十三、总结

DeerFlow 2.0 是一个**架构精良、功能完整**的超级智能体调度框架：

- **后端**以 LangGraph 为核心，通过中间件管道模式实现高度可扩展的 Agent 执行引擎
- **前端**以 Next.js 16 为基础，提供专业级的 AI 交互体验
- **技能系统**以 Markdown 为核心，极大降低了扩展门槛
- **沙箱系统**提供三级安全隔离，满足从开发到生产的不同需求
- **部署方案**从单机到 K8s 集群，覆盖完整的部署场景

整体代码质量高，模块化设计清晰，是当前开源 Agent 框架中**功能最完整、架构最成熟**的项目之一。

---

> **报告生成**: AI 辅助调研，仅供技术参考  
> **项目地址**: https://github.com/bytedance/deer-flow
