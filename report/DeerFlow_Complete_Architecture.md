# DeerFlow 2.0 架构全景文档

> **整合自**: report/ 目录下 8 份调研报告  
> **项目**: DeerFlow (Deep Exploration and Efficient Research Flow)  
> **版本**: 2.0（与 v1 无共享代码）  
> **开源组织**: 字节跳动 (ByteDance)  
> **许可证**: MIT  
> **整合日期**: 2026-03-30

---

## 目录

- [一、项目定位与核心理念](#一项目定位与核心理念)
- [二、整体架构概览](#二整体架构概览)
- [三、后端架构](#三后端架构)
  - [3.1 Monorepo 结构与双进程架构](#31-monorepo-结构与双进程架构)
  - [3.2 LangGraph 执行引擎](#32-langgraph-执行引擎)
  - [3.3 核心 Agent 系统](#33-核心-agent-系统)
  - [3.4 线程状态管理](#34-线程状态管理)
  - [3.5 中间件管道](#35-中间件管道)
  - [3.6 工具系统](#36-工具系统)
  - [3.7 子代理执行引擎](#37-子代理执行引擎)
  - [3.8 多 Agent 编排模式](#38-多-agent-编排模式)
  - [3.9 记忆系统](#39-记忆系统)
  - [3.10 模型提供商系统](#310-模型提供商系统)
  - [3.11 沙箱系统](#311-沙箱系统)
  - [3.12 安全护栏系统](#312-安全护栏系统)
  - [3.13 配置系统](#313-配置系统)
- [四、前端架构](#四前端架构)
- [五、技能系统](#五技能系统)
  - [5.1 Skill 系统架构](#51-skill-系统架构)
  - [5.2 deep-research Skill 实现](#52-deep-research-skill-实现)
  - [5.3 Claude Skills 2.0 能力对标](#53-claude-skills-20-能力对标)
  - [5.4 多模型兼容性分析](#54-多模型兼容性分析)
- [六、IM 频道集成](#六im-频道集成)
- [七、部署架构](#七部署架构)
- [八、嵌入式客户端](#八嵌入式客户端)
- [九、设计模式与最佳实践](#九设计模式与最佳实践)
- [十、系统提示词注入](#十系统提示词注入)
- [十一、消息流转示例](#十一消息流转示例)
- [十二、架构亮点与建议](#十二架构亮点与建议)
- [十三、竞品对比](#十三竞品对比)
- [附录：关键文件索引](#附录关键文件索引)

---

## 一、项目定位与核心理念

DeerFlow 2.0 定位为**超级智能体调度框架 (Super Agent Harness)**，基于 **LangGraph** 和 **LangChain** 构建，通过编排**子智能体**、**记忆**和**沙箱**执行复杂任务，由可扩展的**技能系统**驱动。

### 核心设计理念

| 理念 | 实现方式 |
|------|----------|
| **可插拔一切** | 模型、工具、搜索引擎、沙箱、护栏均通过 `use: package.module:ClassName` 动态加载 |
| **分离关注点** | Gateway API（辅助服务）与 LangGraph Server（Agent 执行）分离 |
| **技能即文档** | Skills 以 `SKILL.md` Markdown 为核心，配合脚本和参考资料 |
| **嵌入式优先** | `DeerFlowClient` 支持不启动服务器直接在 Python 中使用 |
| **上下文工程** | 16 个中间件构成处理管道，精细管控 Agent 上下文 |

### 核心组件

- **Lead Agent**：面向用户交互的主编排器
- **子代理（Subagents）**：并行任务执行（2-4 个并发，通用型/Bash 型）
- **ACP Agent**：外部集成（Codex、Claude Code）
- **中间件链**：16 层有序中间件，负责安全和上下文管理
- **工具系统**：4 个来源（内建 + 配置 + MCP + ACP）
- **记忆系统**：持久化对话上下文，支持 per-agent 隔离
- **沙箱执行**：基于 Docker 的代码执行，具备路径安全防护
- **技能系统**：18 个内置技能，渐进式加载

### 关键指标

| 指标 | 值 |
|------|-----|
| 最大并发子 Agent | 3 个（硬限制） |
| 通用 Subagent 最大轮数 | 50 轮 |
| Bash Subagent 最大轮数 | 20 轮 |
| 中间件层数 | 16 层 |
| 任务轮询间隔 | 5 秒 |
| 默认子 Agent 超时 | 900 秒（15 分钟） |
| 工具来源 | 4 种 |
| 内置技能 | 18 个 |
| 记忆最大事实数 | 100 条 |
| 记忆防抖延迟 | 30 秒 |

---

## 二、整体架构概览

### 顶层架构图

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

### 技术栈全景

| 层级 | 技术选型 | 版本要求 |
|------|----------|----------|
| **后端框架** | Python + LangGraph + FastAPI | Python ≥ 3.12 |
| **前端框架** | Next.js + React + TypeScript | Node.js ≥ 22, Next.js 16, React 19 |
| **UI 组件** | Radix UI + Tailwind CSS 4 | — |
| **状态管理** | TanStack Query + React Hooks | — |
| **流程可视化** | XYFlow (ReactFlow) | — |
| **包管理** | uv（后端）+ pnpm（前端） | — |
| **容器化** | Docker + Nginx + K8s（可选） | — |
| **AI 框架** | LangChain + LangGraph | LangGraph ≥1.0.6 |

### 三种请求入口方式

| 入口方式 | 说明 | 核心接口 |
|----------|------|----------|
| **Web 前端** | 浏览器通过 Nginx 访问 LangGraph Server | `POST /api/langgraph/threads/{id}/runs/stream` |
| **IM 频道** | 飞书/Slack/Telegram 通过 ChannelManager 调用 | `client.runs.stream()` / `client.runs.wait()` |
| **嵌入式客户端** | Python 直接调用，无需启动服务进程 | `DeerFlowClient.stream()` / `.chat()` |

---

## 三、后端架构

### 3.1 Monorepo 结构与双进程架构

后端采用 **uv workspace** 管理，核心框架作为独立包发布：

```
backend/
├── pyproject.toml          # 顶层项目 (deer-flow)
├── app/                    # 应用层
│   ├── gateway/            # FastAPI Gateway API (端口 8001)
│   └── channels/           # IM 集成层 (飞书/Slack/Telegram)
└── packages/
    └── harness/            # 核心框架包 (deerflow-harness)
        └── deerflow/       # 核心代码
            ├── agents/     # Agent 系统 (lead_agent + middlewares + memory)
            ├── subagents/  # 子 Agent 系统 (executor + builtins)
            ├── tools/      # 工具系统 (builtins + MCP)
            ├── skills/     # 技能系统 (loader + parser + installer)
            ├── sandbox/    # 沙箱系统
            ├── models/     # 模型适配
            └── config/     # 配置系统 (20 个独立模块)
```

**Gateway API 路由清单**（10 个路由模块）：

| 路由模块 | 功能 |
|----------|------|
| `agents.py` | Agent 管理（创建/列表/详情/更新/删除） |
| `artifacts.py` | 产物管理（文件预览/下载） |
| `channels.py` | IM 频道管理 |
| `mcp.py` | MCP 服务器配置管理 |
| `memory.py` | 长期记忆 API |
| `models.py` | 模型列表查询 |
| `skills.py` | 技能管理（列表/安装/卸载） |
| `suggestions.py` | 建议 API |
| `threads.py` | 对话线程管理 |
| `uploads.py` | 文件上传管理 |

### 3.2 LangGraph 执行引擎

**关键设计决策**：DeerFlow **没有使用** `StateGraph().add_node().add_edge()` 手动定义图，而是采用 `create_agent()` 高层 API 自动构建 **ReAct 风格的 LangGraph 图**，并通过 **16 个中间件** 实现所有自定义行为。

#### 图工厂函数

```python
# backend/packages/harness/deerflow/agents/lead_agent/agent.py
from langchain.agents import create_agent

def make_lead_agent(config: RunnableConfig):
    return create_agent(
        model=create_chat_model(name=model_name, thinking_enabled=thinking_enabled),
        tools=get_available_tools(model_name=model_name, subagent_enabled=subagent_enabled),
        middleware=_build_middlewares(config, model_name=model_name),
        system_prompt=apply_prompt_template(subagent_enabled=subagent_enabled, ...),
        state_schema=ThreadState,
    )
```

#### 自动生成的 ReAct 图结构

```
           ┌──────────────────────────┐
      ┌───►│     Agent 节点 (LLM)     │◄──────┐
      │    └──────────┬───────────────┘       │
      │               │                       │
      │     ┌─────────▼─────────┐             │
      │     │  条件边: 路由判断   │             │
      │     └───┬─────────┬────┘             │
      │        YES        NO                  │
      │         │         │                   │
      │         │         ▼                   │
      │         │    ┌─────────┐              │
      │         │    │   END   │              │
      │         │    └─────────┘              │
      │         ▼                             │
      │    ┌───────────────┐                  │
      └────│  Tools 节点    │──────────────────┘
           └───────────────┘
```

**条件路由规则**：
- LLM 返回包含 `tool_calls` → 进入 Tools 节点 → 回到 Agent 节点（循环）
- LLM 返回不含 `tool_calls` → 到达 END（结束）
- `ClarificationMiddleware` — 拦截 `ask_clarification` 工具，返回 `Command(goto=END)` 中断
- `LoopDetectionMiddleware` — 检测重复调用，强制剥离 `tool_calls` 终止循环

#### 完整请求执行链路

```
① 客户端请求 → ② Nginx 路由 → ③ LangGraph Server 调用 make_lead_agent()
→ ④ create_agent() 构建 ReAct 图
→ ⑤ Checkpointer 加载线程历史状态
→ ⑥ 中间件 before_agent 阶段
→ ⑦ ReAct 循环执行 (Agent ↔ Tools)
→ ⑧ 中间件 after_agent 阶段
→ ⑨ Checkpointer 持久化新状态
→ ⑩ SSE 流式返回
```

#### 与传统 LangGraph 用法的对比

| 维度 | 传统 LangGraph | DeerFlow |
|------|---------------|----------|
| **图定义** | 手动 `StateGraph()` | `create_agent()` 自动生成 |
| **节点实现** | 自定义函数 | 中间件链替代 |
| **条件路由** | `add_conditional_edges()` | 隐式路由 |
| **扩展方式** | 添加新节点和边 | 添加新中间件 |
| **控制流** | 自定义路由函数 | `Command(goto=END)` + 中间件拦截 |

### 3.3 核心 Agent 系统

#### Lead Agent（主编排器）

**入口文件**：`backend/packages/harness/deerflow/agents/lead_agent/agent.py:make_lead_agent`

**运行时配置**（来自 RunnableConfig）：
```python
thinking_enabled: bool               # 扩展推理模式
reasoning_effort: str | None         # 推理力度
model_name: str | None               # 覆盖默认模型
is_plan_mode: bool                   # 启用任务列表追踪
subagent_enabled: bool               # 启用并行任务委派
max_concurrent_subagents: int        # 限制并发任务调用数（2-4）
is_bootstrap: bool                   # Agent 创建模式
agent_name: str | None               # 自定义 Agent 人格覆盖
```

**模型解析优先级**：
1. 运行时参数中显式指定的模型
2. Agent 级别的模型覆盖（来自 AGENT.yaml）
3. 全局默认模型（config.yaml 中的第一个）

#### 子代理（并行任务执行器）

| 类型 | 位置 | 用途 | 最大轮次 |
|------|------|------|----------|
| **通用子代理** | `subagents/builtins/general_purpose.py` | 复杂多步骤研究、分析 | 50 |
| **Bash 子代理** | `subagents/builtins/bash_agent.py` | 命令执行（git、构建） | 20 |

**执行模型**：
- 通过 ThreadPoolExecutor 后台执行
- 基于轮询的结果获取（5 秒间隔）
- 流式发送 task_started/task_running 事件
- 硬性并发限制：每个响应最多 3 个并行 task 调用

#### ACP Agent（外部集成）

**支持**：Codex、Claude Code、任何 ACP 兼容 Agent

- 按线程隔离工作空间：`/acp-workspace/{thread_id}/`
- 自动批准沙箱权限
- MCP 服务器透传
- 结果可通过 `/mnt/acp-workspace/` 访问（只读）

### 3.4 线程状态管理

#### ThreadState Schema

```python
class ThreadState(AgentState):
    messages: Annotated[list[BaseMessage], add_messages]    # 所有消息
    sandbox: NotRequired[SandboxState | None]                # 沙箱信息
    thread_data: NotRequired[ThreadDataState | None]         # 路径映射
    title: NotRequired[str | None]                           # 自动生成标题
    artifacts: Annotated[list[str], merge_artifacts]         # 生成文件（去重）
    todos: NotRequired[list | None]                          # 任务追踪
    uploaded_files: NotRequired[list[dict] | None]           # 用户上传文件
    viewed_images: Annotated[dict, merge_viewed_images]      # 视觉数据
```

#### 虚拟路径映射

| 虚拟路径 | 物理路径 | 用途 |
|---------|---------|------|
| `/mnt/user-data/workspace` | `.deer-flow/threads/{thread_id}/user-data/workspace/` | 工作区 |
| `/mnt/user-data/uploads` | `.deer-flow/threads/{thread_id}/user-data/uploads/` | 上传文件 |
| `/mnt/user-data/outputs` | `.deer-flow/threads/{thread_id}/user-data/outputs/` | 输出文件 |
| `/mnt/skills` | `deer-flow/skills/` | 技能库 |
| `/mnt/acp-workspace` | `.deer-flow/acp-workspace/{thread_id}/` | ACP 工作空间 |

#### Checkpointer 状态持久化

| 后端 | 适用场景 |
|------|---------|
| `memory` (InMemorySaver) | 开发调试（非持久化） |
| `sqlite` (SqliteSaver) | 单机默认方案 |
| `postgres` (PostgresSaver) | 生产环境 |

### 3.5 中间件管道

DeerFlow 用 **中间件链替代手动图节点**，通过 5 个钩子点实现所有自定义行为：

| 钩子 | 执行时机 | 典型用途 |
|------|---------|----------|
| `before_agent` | Agent 节点执行前 | 初始化资源（线程路径、沙箱、上传文件） |
| `after_agent` | Agent 节点执行后 | 释放资源、触发异步任务（记忆、标题） |
| `before_model` | LLM 调用前 | 注入上下文、过滤工具 |
| `after_model` | LLM 调用后 | 生成标题、检测循环、限制子代理数量 |
| `wrap_tool_call` | 工具执行时 | 错误处理、拦截澄清请求、安全护栏 |

#### 16 层中间件完整执行顺序

```
── before_agent ──────────────────────────────
  ① ThreadDataMiddleware     初始化线程目录
  ② UploadsMiddleware        扫描上传文件
  ③ SandboxMiddleware        获取沙箱环境（lazy/eager）
  ④ DanglingToolCallMiddleware 修补缺失的 ToolMessage
  ⑤ GuardrailMiddleware      安全护栏检查（可选）

── before_model / after_model ────────────────
  ⑥ ToolErrorHandlingMiddleware  工具异常 → 错误消息
  ⑦ SummarizationMiddleware     Token 超限时自动摘要（可选）
  ⑧ TodoMiddleware              Plan Mode 任务管理（可选）
  ⑨ TokenUsageMiddleware        Token 用量追踪（可选）
  ⑩ TitleMiddleware             首次交互后生成标题
  ⑪ MemoryMiddleware            排队记忆更新任务
  ⑫ ViewImageMiddleware         注入 Base64 图片到消息（可选）
  ⑬ DeferredToolFilterMiddleware 隐藏延迟加载工具（可选）
  ⑭ SubagentLimitMiddleware     截断超限的子代理调用（可选）
  ⑮ LoopDetectionMiddleware     检测重复调用，强制终止
  ⑯ ClarificationMiddleware     拦截澄清请求 → Command(goto=END)

── wrap_tool_call ────────────────────────────
  ToolErrorHandlingMiddleware → 捕获异常
  GuardrailMiddleware         → 安全检查
  ClarificationMiddleware     → 拦截 ask_clarification
```

#### 关键中间件详解

**ThreadDataMiddleware**（必须排在首位）：初始化 `/mnt/user-data/{workspace,uploads,outputs}` 目录，缺少则所有路径操作失败。

**ClarificationMiddleware**（必须排在末位）：拦截 `ask_clarification` 工具调用，返回 `Command(goto=END)` 中断执行，等待用户响应后恢复。

**LoopDetectionMiddleware**：滑动窗口追踪近 20 次调用，同一哈希 ≥3 次注入警告，≥5 次强制剥离 tool_calls 终止循环。

**SubagentLimitMiddleware**：静默截断超出限制的 task 调用，记录警告日志。

**MemoryMiddleware**：过滤掉工具消息和文件上传块，保留用户问题和最终 AI 响应，异步排队更新。

### 3.6 工具系统

```
工具系统分层架构
├── 内置工具 (BUILTIN_TOOLS)
│   ├── present_file_tool      文件展示
│   ├── ask_clarification_tool 追问工具
│   ├── view_image_tool        图片查看（model.supports_vision=true）
│   ├── task_tool              子代理委托（subagent_enabled=true）
│   ├── setup_agent_tool       Agent 创建（仅 bootstrap 模式）
│   └── tool_search            工具搜索（tool_search.enabled=true）
│
├── 配置工具 (config.yaml)
│   ├── web_search / web_fetch / image_search
│   ├── bash / read_file / write_file / str_replace / ls
│
├── MCP 工具 (extensions_config.json)
│   ├── GitHub / Filesystem / PostgreSQL / Brave Search 等
│   └── 缓存加载，mtime 失效检查
│
├── ACP Agent 工具
│   └── invoke_acp_agent (Claude Code / Codex)
│
└── 延迟加载工具 (Tool Search)
    └── DeferredToolRegistry + DeferredToolFilterMiddleware
```

**工具加载流程**：
```
get_available_tools()
├─ 按组加载配置工具
├─ 添加内建工具
├─ 如模型支持视觉 → 添加 view_image
├─ 加载 MCP 工具（缓存，mtime 失效）
│  └─ 如启用 tool_search → 注册到延迟注册表
├─ 如有配置 → 添加 ACP Agent 工具
└─ 返回合并后的工具列表
```

### 3.7 子代理执行引擎

```python
class SubagentExecutor:
    def __init__(self, task_id, config, parent_config, parent_context):
        self.executor = ThreadPoolExecutor(max_workers=3)  # 调度线程

    async def _aexecute(self, task) -> SubagentResult:
        agent = make_lead_agent(self.config)
        ai_messages = []
        async for event in agent.astream({"messages": [HumanMessage(task)]}):
            if isinstance(event.get("messages"), AIMessage):
                ai_messages.append(event["messages"])
        return SubagentResult(task_id, status=COMPLETED, result=ai_messages[-1].content)

    def execute_async(self, task) -> str:
        future = self.executor.submit(self.execute, task)
        return self.task_id  # 立即返回
```

**执行状态生命周期**：`PENDING → RUNNING → COMPLETED / FAILED / TIMED_OUT`

**SubagentResult 数据结构**：
```python
@dataclass
class SubagentResult:
    task_id: str                    # 唯一执行 ID
    trace_id: str                   # 分布式追踪 ID
    status: SubagentStatus          # 执行状态
    result: str | None              # 最终结果文本
    error: str | None               # 错误信息
    ai_messages: list[dict]         # 捕获的所有 AI 消息
```

### 3.8 多 Agent 编排模式

#### 模式 1：Lead Agent 直接执行

**场景**：简单任务、单步操作、需要用户交互

```
Lead Agent（1 轮）→ 直接调用工具 → 生成响应 → 返回用户
```

#### 模式 2：子代理委派（单批次）

**场景**：2-3 个可并行的独立子任务

```
Lead Agent → 分解任务 → 并行调用 3 个 task() → 等待所有结果 → 综合回答
```

#### 模式 3：子代理委派（多批次）

**场景**：>3 个并行子任务（SubagentLimitMiddleware 强制截断）

```
第 1 轮：启动前 3 个任务 → 等待结果
第 2 轮：启动后 3 个任务 → 等待结果
第 3 轮：综合所有结果 → 返回完整回答
```

#### 模式 4：澄清中断

**场景**：用户意图不明确或信息缺失

```
第 1 轮：ask_clarification → ClarificationMiddleware → Command(goto=END) → 中断
用户回复 →
第 2 轮：完整上下文 → 执行任务 → 返回结果
```

#### 模式 5：ACP Agent 委派

**场景**：代码生成、IDE 任务

```
Lead Agent → invoke_acp_agent → 隔离工作空间执行 → 读取结果 → 展示给用户
```

#### 协调决策树

```
用户请求 → 是否需要澄清? → 是 → ask_clarification → 中断
                          → 否 → 是否复杂多步?
                                 → 否 → 直接工具调用（模式 1）
                                 → 是 → 任务数量?
                                        ├─ ≤3 → 单批次（模式 2）
                                        ├─ >3 → 多批次（模式 3）
                                        └─ 代码生成 → ACP 委托（模式 5）
```

### 3.9 记忆系统

#### 整体架构

```
用户对话 → Agent 执行 → after_agent 钩子
    ↓
MemoryMiddleware → 过滤消息（保留 Human + 最终 AI 回复）→ 加入 MemoryUpdateQueue
    ↓ 防抖 30s
MemoryUpdateQueue → 同 thread 多次触发只保留最新 → 批量调用 MemoryUpdater
    ↓
MemoryUpdater → 加载当前记忆 → 构造 MEMORY_UPDATE_PROMPT → 调用 LLM → 合并更新
    ↓
FileMemoryStorage → 原子写入（.tmp → rename）→ mtime 缓存
```

#### 数据模型

```json
{
  "version": "1.0",
  "user": {
    "workContext": { "summary": "当前工作/项目/技术栈", "updatedAt": "" },
    "personalContext": { "summary": "语言/偏好/兴趣", "updatedAt": "" },
    "topOfMind": { "summary": "当前多个并行关注点", "updatedAt": "" }
  },
  "history": {
    "recentMonths": { "summary": "近1-3个月活动", "updatedAt": "" },
    "earlierContext": { "summary": "3-12个月前模式", "updatedAt": "" },
    "longTermBackground": { "summary": "长期背景", "updatedAt": "" }
  },
  "facts": [
    { "id": "fact_xxx", "content": "...", "category": "knowledge", "confidence": 0.9 }
  ]
}
```

**Fact 分类体系**：`preference`（偏好）、`knowledge`（技能）、`context`（背景）、`behavior`（行为）、`goal`（目标）

#### 关键设计决策

1. **LLM 提取记忆**：语义理解 > 规则匹配，能判断信息时效性
2. **防抖队列**：30 秒内多轮对话只触发一次更新，降低 API 成本
3. **过滤文件上传引用**：正则清除临时路径，防止"幽灵引用"
4. **Token 预算管理**：tiktoken 精确计算，Facts 按置信度降序优先填入（≤2000 tokens）
5. **原子写入**：`.tmp` + `rename` 防止崩溃导致数据损坏

#### 配置参数

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `True` | 是否启用 |
| `debounce_seconds` | `30` | 防抖延迟 |
| `max_facts` | `100` | 最大事实数 |
| `fact_confidence_threshold` | `0.7` | 置信度阈值 |
| `max_injection_tokens` | `2000` | 注入 Token 上限 |

#### REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/memory` | 获取当前记忆 |
| `POST` | `/api/memory/reload` | 强制重新加载 |
| `GET` | `/api/memory/config` | 获取配置 |
| `GET` | `/api/memory/status` | 配置 + 数据合并视图 |

### 3.10 模型提供商系统

```
模型系统架构
├── 标准 LangChain 提供商
│   ├── langchain_openai:ChatOpenAI       ← OpenAI / OpenRouter
│   ├── langchain_anthropic:ChatAnthropic ← Claude
│   └── langchain_google_genai:ChatGoogleGenerativeAI ← Gemini
├── 适配/补丁提供商
│   ├── PatchedChatDeepSeek  ← thinking support
│   ├── PatchedChatOpenAI    ← Gemini via OpenAI 网关
│   └── PatchedChatMiniMax   ← MiniMax 适配
├── CLI 提供商
│   ├── ClaudeChatModel      ← Claude Code CLI (OAuth)
│   └── CodexChatModel       ← OpenAI Codex CLI
└── 凭证加载器 (credential_loader.py)
```

**支持 11 种模型供应商**：OpenAI、Anthropic、Google Gemini、DeepSeek、Kimi、MiniMax、Novita AI、OpenRouter、Volcengine（豆包）、Codex CLI、Claude Code CLI

### 3.11 沙箱系统

```
沙箱系统三级架构
├── Level 1: LocalSandboxProvider → 直接在主机执行（默认/开发）
├── Level 2: AioSandboxProvider   → Docker / Apple Container
└── Level 3: K8s Provisioner      → 管理 Pod 生命周期（生产级）
```

**沙箱工具**：`ls`、`read_file`、`write_file`、`str_replace`、`bash`

### 3.12 安全护栏系统

```
├── GuardrailsMiddleware → 每个工具调用前检查
├── AllowlistProvider（内置）→ denied_tools 黑名单
├── OAP Provider → Open Agent Passport 协议
└── Custom Provider → 自定义 evaluate/aevaluate
```

### 3.13 配置系统

20 个独立配置模块，配置版本管理 `config_version: 3`，支持 `make config-upgrade` 自动合并。

```yaml
# config.yaml 核心配置示例
config_version: 3
models:
  - name: gpt-4
    use: langchain_openai:ChatOpenAI
    supports_vision: true
tools:
  - name: web_search
    use: deerflow.tools:web_search_tool
    group: search
memory:
  enabled: true
  injection_enabled: true
sandbox:
  provider: aio  # Docker（生产）
```

---

## 四、前端架构

### 技术架构

```
前端分层架构
├── app/              # Next.js 16 App Router
│   ├── workspace/    # 主工作区（agents/ + chats/）
│   └── api/auth/     # Better Auth 认证
├── components/       # UI 组件层
│   ├── ai-elements/  # AI 交互元素（核心）
│   ├── workspace/    # 工作区组件
│   └── ui/           # 基础 UI 库（30+ Radix 组件）
├── core/             # 核心业务逻辑层
│   ├── api/          # API 客户端 + 流模式
│   ├── threads/      # 对话线程管理
│   ├── skills/       # 技能管理
│   ├── i18n/         # 国际化（en-US, zh-CN）
│   └── streamdown/   # 流式 Markdown
└── hooks/            # 全局 Hooks
```

### 核心 AI 交互组件

| 组件 | 大小 | 职责 |
|------|------|------|
| `prompt-input.tsx` | 36.93 KB | 提示输入（文件上传、模型选择、技能选择） |
| `message.tsx` | 10.57 KB | 消息渲染（Markdown/代码/图片/引用） |
| `context.tsx` | 9.53 KB | 上下文面板（思维链、推理过程） |
| `chain-of-thought.tsx` | 6.29 KB | 思维链可视化 |
| `queue.tsx` | 6.09 KB | 子任务队列展示 |
| `model-selector.tsx` | 4.72 KB | 模型选择器 |

### 数据流

```
用户输入 → InputBox → LangGraph SDK → SSE → StreamMode 解析
    → TanStack Query 缓存 → React 组件树（MessageList / ChainOfThought / ArtifactPanel）
```

---

## 五、技能系统

### 5.1 Skill 系统架构

```
skill-name/
├── SKILL.md              # 核心定义文件（YAML frontmatter + Markdown 工作流）
├── scripts/              # 可执行脚本（可选）
├── references/           # 参考资料（可选）
└── assets/               # 静态资源（可选）
```

**渐进式加载模式（3 层）**：
1. **Layer 1 - 元数据**：始终在上下文（name + description ~100 词）
2. **Layer 2 - Skill 主体**：触发时 `read_file()` 加载 SKILL.md（<500 行）
3. **Layer 3 - 捆绑资源**：按需加载 references/scripts/templates

**18 个内置技能**：

| 技能 | 功能 |
|------|------|
| `deep-research` | 系统化多角度网络研究 |
| `frontend-design` | 高质量前端界面设计 |
| `chart-visualization` | 数据可视化（20+ 图表类型） |
| `ppt-generation` | PPT 演示文稿生成 |
| `image-generation` | AI 图像生成 |
| `video-generation` | 视频生成 |
| `podcast-generation` | 播客音频生成 |
| `data-analysis` | 数据分析 |
| `consulting-analysis` | 咨询分析（最大技能 32.85 KB） |
| `github-deep-research` | GitHub 仓库深度研究 |
| `skill-creator` | 元技能（含 A/B 测试 + 自我迭代） |
| `bootstrap` | AI 个性化引导（生成 SOUL.md） |
| `find-skills` | 查找和安装技能 |
| `claude-to-deerflow` | Claude → DeerFlow 迁移 |
| `surprise-me` | 随机惊喜 |
| `vercel-deploy-claimable` | Vercel 部署 |
| `web-design-guidelines` | Web 设计规范审查 |

### 5.2 deep-research Skill 实现

**核心研究方法论（4 阶段）**：

1. **Phase 1 - 广泛探索**：初始调查 → 识别维度 → 映射领域（3-4 个初始搜索）
2. **Phase 2 - 深度挖掘**：精准查询 → 多措辞 → web_fetch 获取完整内容 → 跟踪引用
3. **Phase 3 - 多样性验证**：覆盖 6 种信息类型（事实/示例/专家/趋势/对比/挑战）
4. **Phase 4 - 综合检查**：5 项验证清单（角度 ≥3-5、完整源阅读、具体数据、双面探索、时效性）

**时间感知策略**（关键创新）：

| 用户意图 | 搜索精度 | 示例 |
|---------|---------|------|
| "today" | 月 + 日 + 年 | `"tech news February 28 2026"` |
| "this week" | 周范围 | `"releases week of Feb 24 2026"` |
| "recently" | 月 | `"AI breakthroughs February 2026"` |
| "trends" | 年 | `"software trends 2026"` |

**Skill 设计模式（7 种）**：渐进式加载、声明式触发条件（"pushy" 风格）、工作流分段化、包含反面模式、上下文感知、质量检查清单、多资源组织。

### 5.3 Claude Skills 2.0 能力对标

通过 `skill-creator` 技能实现：

| 特性 | 实现 | 状态 |
|------|------|------|
| A/B 测试 | `aggregate_benchmark.py`：with_skill vs without_skill | ✅ |
| 自我迭代 | `run_loop.py`：eval → improve → eval 循环 | ✅ |
| Train/Test 分割 | `split_eval_set()`，40% holdout | ✅ |
| 防过拟合 | holdout + 描述长度限制 + 泛化指导 | ✅ |
| 版本追踪 | `history.json` 记录每版 pass_rate | ✅ |
| 实时报告 | `generate_report.py` HTML 报告 | ✅ |

### 5.4 多模型兼容性分析

**结论**：A/B 测试 + 自我迭代机制**硬绑定 Claude Code CLI**，无法在其他模型直接使用。

**绑定点**：
- `run_eval.py`：`claude -p` CLI 调用、stream-json 事件解析、`.claude/commands/` 注入
- `improve_description.py`：`claude -p` CLI、prompt 措辞 "for a Claude Code skill"

**改造建议**：
1. 替换 `claude -p` → `DeerFlowClient` 或 LangChain 模型接口
2. 替换触发检测 → 检测 Agent 是否调用 `read_file` 读取 SKILL.md
3. 替换命令文件注入 → 动态修改 `extensions_config.json`
4. 替换 prompt 模板 → 通用描述
5. 适配 stream 解析 → LangChain 回调机制

---

## 六、IM 频道集成

| 平台 | 连接方式 | 代码量 |
|------|----------|--------|
| **飞书** | WebSocket | 24.38 KB |
| **Telegram** | 轮询（Polling） | 12.75 KB |
| **Slack** | Socket Mode | 8.88 KB |

**关键特性**：
- 所有频道使用**出站连接**，无需公网 IP
- 消息总线模式解耦 Agent 执行与消息投递
- 支持 per-channel 和 per-user 的会话配置覆盖

---

## 七、部署架构

### Docker Compose（5 个服务）

```
nginx (:2026) → frontend (Next.js)
     ├──────→ gateway (:8001) FastAPI
     └──────→ langgraph (:2024) Agent 引擎
provisioner (:8002) [可选，K8s 模式]
```

### Docker-in-Docker (DooD) 模式

Gateway 和 LangGraph 容器通过挂载 Docker Socket 实现容器沙箱：
```yaml
volumes:
  - ${DEER_FLOW_DOCKER_SOCKET}:/var/run/docker.sock
```

---

## 八、嵌入式客户端

`DeerFlowClient`（33.48 KB）支持无服务器直接使用：

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient()
response = client.chat("分析这篇论文", thread_id="my-thread")

for event in client.stream("你好"):
    print(event)
```

---

## 九、设计模式与最佳实践

### 核心设计模式

| 模式 | 实现 | 优点 |
|------|------|------|
| **反射式动态加载** | `use: package.module:ClassName` | 零代码切换提供商 |
| **中间件链** | 16 层有序处理 | 关注点分离、可插拔 |
| **Provider 抽象** | Sandbox/Guardrail/Checkpointer | 统一接口，多种实现 |
| **配置即代码** | YAML 驱动系统行为 | 无需重编译 |
| **批处理协调** | 超 3 个子任务分批执行 | 避免任务丢失 |
| **状态继承** | 子 Agent 继承父 Agent 配置 | 简化配置、一致环境 |

### 安全机制

1. **工具隔离**：子 Agent 禁止调用 task_tool（防无限递归）
2. **多层超时**：子 Agent 配置 + 线程池 + 轮询三层保护
3. **错误恢复**：工具异常转为 ToolMessage，不会崩溃
4. **循环检测**：滑动窗口哈希检测，≥5 次强制终止
5. **并发限制**：SubagentLimitMiddleware 硬限制 3 个
6. **沙箱隔离**：Docker 容器 + 虚拟路径映射
7. **路径安全**：agent_name 正则校验防路径穿越
8. **安装防护**：ZIP 炸弹、路径穿越、符号链接检查

---

## 十、系统提示词注入

**Lead Agent 系统提示词结构**（13 个 XML 段落）：

```xml
<role>Agent 身份定义</role>
<soul>Agent 人格（SOUL.md，可选）</soul>
<memory>长期记忆注入（置信度过滤）</memory>
<thinking_style>思维风格指导</thinking_style>
<clarification_system>澄清追问规则</clarification_system>
<skill_system>可用技能列表 + 渐进加载指引</skill_system>
<available-deferred-tools>延迟加载工具名录</available-deferred-tools>
<subagent_system>子代理编排策略（含并发限制）</subagent_system>
<working_directory>虚拟文件系统路径说明</working_directory>
<response_style>输出风格指导</response_style>
<citations>引用格式规范</citations>
<critical_reminders>关键提醒</critical_reminders>
<current_date>当前日期</current_date>
```

---

## 十一、消息流转示例

**场景**：用户发送消息（subagent_enabled=true，比较 5 家云服务商）

```
 1. 客户端 → POST /api/langgraph/threads/{id}/runs/stream
 2. LangGraph Server → make_lead_agent(config)
    → 构建 16 层中间件 → 执行 before_agent → 建立上下文
 3. Lead Agent → 模型处理消息
    思考："5 家云服务商，每次最多 3 个，先处理 AWS/Azure/GCP"
 4. 模型生成 3 个 task() 调用
 5. SubagentLimitMiddleware 检查：3 ≤ 3 ✓
 6. 每个 task() 启动 SubagentExecutor 后台线程
 7. task_tool() 轮询（5s 间隔），流式发送 task_started/running 事件
 8. Lead Agent 收到 3 个结果
 9. 模型："AWS/Azure/GCP 完成，启动阿里云和 Oracle"
10. 模型生成 2 个 task() 调用，检查：2 ≤ 3 ✓
11-13. 并行执行 → 收到结果
14. 模型综合所有结果生成对比报告
15. ClarificationMiddleware：无澄清调用 → 正常流程
16. 通过 SSE 流式返回响应
```

**事件类型**：`TaskStarted`、`TaskRunning`（推理步骤）、`TaskCompleted`（最终输出）、`TaskFailed`

**流式响应模式**：

| 模式 | 内容 | 用途 |
|------|------|------|
| `messages-tuple` | 消息增量更新 | AI 文本逐字、工具调用/结果 |
| `values` | 完整状态快照 | 标题、产物列表、任务列表同步 |
| `custom` | 自定义事件 | 子代理进度 |

---

## 十二、架构亮点与建议

### 架构亮点

1. **双进程分离**：Gateway（轻量辅助）与 LangGraph Server（重量执行）互不干扰
2. **中间件可组合**：16 个中间件按需开关，灵活组合
3. **三级沙箱**：本地 → Docker → K8s，按安全需求逐级升级
4. **嵌入式客户端**：无需部署服务即可使用完整 Agent 能力
5. **Skill = Markdown**：降低技能创建门槛
6. **Tool Search**：延迟加载 MCP 工具，减少 Context 占用
7. **IM 全通道**：飞书/Slack/Telegram 一站式接入

### 架构建议

| 时间段 | 建议 |
|--------|------|
| **短期（已实现）** | 多 Agent 并发限制、澄清优先、虚拟路径隔离、异步内存更新 |
| **中期** | 动态并发限制（根据负载 2-4）、Agent 性能监控、工具使用分析、多级缓存 |
| **长期** | Agent 学习系统、跨线程知识共享、Agent 联盟、成本优化 |
| **高优** | 将 eval/improve 脚本适配 DeerFlow 原生多模型架构（解除 Claude CLI 绑定） |

---

## 十三、竞品对比

| 特性 | DeerFlow 2.0 | AutoGPT | CrewAI | LangGraph Studio |
|------|-------------|---------|--------|-----------------|
| 子智能体编排 | ✅ 完整 | ✅ | ✅ | ✅ |
| 容器沙箱 | ✅ 三级 | ❌ | ❌ | ❌ |
| 技能系统 | ✅ 18+ 内置 | ❌ | ❌ | ❌ |
| 长期记忆 | ✅ | ✅ | ❌ | ❌ |
| IM 集成 | ✅ 3 平台 | ❌ | ❌ | ❌ |
| 嵌入式客户端 | ✅ | ❌ | ✅ | ❌ |
| 安全护栏 | ✅ | ❌ | ❌ | ❌ |
| MCP 支持 | ✅ | ❌ | ❌ | ✅ |
| ACP 支持 | ✅ | ❌ | ❌ | ❌ |
| 完整前端 | ✅ 专业级 | ✅ 基础 | ❌ | ✅ 基础 |

---

## 附录：关键文件索引

### Agent 核心

| 文件 | 用途 | 关键函数/类 |
|------|------|-------------|
| `agents/lead_agent/agent.py` | 主 Agent 工厂 | `make_lead_agent()`, `_build_middlewares()` |
| `agents/lead_agent/prompt.py` | 系统提示词构建 | `apply_prompt_template()`, `get_skills_prompt_section()` |
| `agents/thread_state.py` | 状态 Schema | `ThreadState` 类 |
| `agents/memory/` | 记忆系统 | `updater.py`, `storage.py`, `queue.py`, `prompt.py` |
| `agents/middlewares/` | 16 层中间件 | 各中间件类 |

### 子代理系统

| 文件 | 用途 |
|------|------|
| `subagents/executor.py` | `SubagentExecutor` 类 |
| `subagents/builtins/general_purpose.py` | 通用子代理配置 |
| `subagents/builtins/bash_agent.py` | Bash 子代理配置 |

### 工具系统

| 文件 | 用途 |
|------|------|
| `tools/__init__.py` | `get_available_tools()` |
| `tools/builtins/task_tool.py` | 子代理委派 |
| `tools/builtins/invoke_acp_agent_tool.py` | ACP Agent 调用 |
| `tools/builtins/clarification_tool.py` | `ask_clarification` 工具 |

### 技能系统

| 文件 | 用途 |
|------|------|
| `skills/parser.py` | SKILL.md 解析器 |
| `skills/loader.py` | 技能加载器 |
| `skills/installer.py` | 技能安装（含安全防护） |
| `skills/validation.py` | 格式验证 |

### 配置

| 文件 | 用途 |
|------|------|
| `/config.yaml` | 主配置（模型、工具、记忆等） |
| `/extensions_config.json` | MCP + Skills 扩展配置 |
| `config/app_config.py` | 全局配置管理（20 个模块） |

### 前端核心

| 文件 | 用途 |
|------|------|
| `components/ai-elements/prompt-input.tsx` | 提示输入（36.93 KB，最大组件） |
| `core/skills/` | 技能管理（API/类型/Hooks） |
| `core/api/` | API 客户端 + 流模式 |

### 部署

| 文件 | 用途 |
|------|------|
| `langgraph.json` | LangGraph 部署配置 |
| `docker/docker-compose.yaml` | Docker Compose（5 服务） |
| `backend/app/gateway/app.py` | FastAPI REST 网关 |

### 辅助资源

| 文件 | 说明 |
|------|------|
| `report/DeerFlow_Memory_Sequence.png` | Memory 模块时序图 |
| `report/DeerFlow_Memory_Sequence.svg` | Memory 模块时序图（矢量） |
| `report/gen_memory_sequence.py` | 时序图生成脚本 |

---

> **整合来源**：`AGENT_ARCHITECTURE_GUIDE.md`、`Agent_Design_Research.md`、`Agent_Design_Research_Report.md`、`Deep_Research_Skill_Implementation.md`、`DeerFlow_Architecture_Report.md`、`DeerFlow_LangGraph_Execution_Engine.md`、`DeerFlow_Memory_Design_Report.md`、`DeerFlow_Skills_System_Analysis.md`、`gen_memory_sequence.py`  
> **文档性质**: AI 辅助整合，供技术参考
