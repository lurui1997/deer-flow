# DeerFlow 2.0 — LangGraph 执行引擎深度解析

> **项目名称**: DeerFlow (Deep Exploration and Efficient Research Flow)  
> **版本**: 2.0  
> **文档类型**: 执行引擎技术专题  
> **分析日期**: 2026-03-28  

---

## 一、概述

DeerFlow 2.0 以 **LangGraph** 作为核心执行引擎，但并未直接使用 `StateGraph` 手动定义节点和边，而是采用 `langchain.agents.create_agent()` 高层 API 自动构建 **ReAct 风格的 LangGraph 图**，并通过 **16 个中间件** 实现所有自定义行为。本文档完整解析从用户请求到返回结果的全链路。

---

## 二、系统架构与请求入口

### 2.1 双进程架构

```
┌────────────────────────────────────────────────────────────────────┐
│                        Nginx (端口 2026)                            │
│                       统一入口 · 反向代理                            │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│   /api/langgraph/*  ──→  LangGraph Server (端口 2024)               │
│                          ■ Agent 核心执行引擎                       │
│                          ■ 对话线程管理                             │
│                          ■ SSE 流式响应                             │
│                          ■ Checkpoint 状态持久化                    │
│                                                                    │
│   /api/*            ──→  Gateway API (端口 8001)                    │
│                          ■ 模型/技能/MCP 配置管理                   │
│                          ■ 文件上传 / 产物下载                      │
│                                                                    │
│   /*                ──→  Frontend (端口 3000)                       │
│                          ■ Next.js 16 + React 19                   │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**关键分工**：LangGraph Server 专注于 Agent 执行和状态管理；Gateway API 处理辅助性 REST 操作。两个进程共享 `config.yaml` 和 `extensions_config.json` 配置文件。

### 2.2 请求入口方式

DeerFlow 提供三种方式触发 LangGraph 执行：

| 入口方式 | 说明 | 核心接口 |
|----------|------|----------|
| **Web 前端** | 浏览器通过 Nginx 直接访问 LangGraph Server | `POST /api/langgraph/threads/{id}/runs/stream` |
| **IM 频道** | 飞书/Slack/Telegram 通过 ChannelManager 调用 | `client.runs.stream()` / `client.runs.wait()` |
| **嵌入式客户端** | Python 直接调用，无需启动服务进程 | `DeerFlowClient.stream()` / `.chat()` |

---

## 三、完整请求链路

以下是用户发送一条消息到收到回复的完整链路：

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          完整请求执行链路                                  │
└──────────────────────────────────────────────────────────────────────────┘

  ① 客户端请求
     POST /api/langgraph/threads/{thread_id}/runs/stream
     {"input": {"messages": [{"role": "human", "content": "..."}]}}
         │
         ▼
  ② Nginx 路由 → LangGraph Server (端口 2024)
         │
         ▼
  ③ LangGraph Server 根据 langgraph.json 调用 make_lead_agent(config)
         │
         ▼
  ④ create_agent() 构建 ReAct 图
     ┌─────────────────────────────────────────────────────┐
     │  model       = ChatOpenAI / ChatAnthropic / ...     │
     │  tools       = [web_search, bash, task, ...]        │
     │  middleware   = [16 个中间件链]                       │
     │  system_prompt = 动态生成 (含 skills/memory/soul)    │
     │  state_schema = ThreadState                         │
     └─────────────────────────────────────────────────────┘
         │
         ▼
  ⑤ Checkpointer 加载线程历史状态 (SQLite/Postgres/Memory)
         │
         ▼
  ⑥ 中间件 before_agent 阶段
     ThreadData → Uploads → Sandbox → DanglingToolCall → Guardrail
         │
         ▼
  ⑦ ReAct 循环执行
     ┌─────────────────────────┐
     │  Agent 节点 (LLM 推理)   │◄────────────────────┐
     └───────────┬─────────────┘                      │
                 │                                    │
          有 tool_calls?                               │
           │          │                               │
          YES         NO → ⑧ END                     │
           │                                          │
           ▼                                          │
     ┌─────────────────────────┐                      │
     │   Tools 节点 (工具执行)   │──────────────────────┘
     │   中间件 wrap_tool_call  │
     └─────────────────────────┘
         │
         ▼
  ⑧ 中间件 after_agent 阶段
     Title → Memory → TokenUsage → Sandbox Release
         │
         ▼
  ⑨ Checkpointer 持久化新状态
         │
         ▼
  ⑩ SSE 流式返回 (messages-tuple / values / end)
```

---

## 四、LangGraph 图构建机制

### 4.1 配置入口

**文件**: `backend/langgraph.json`

```json
{
  "graphs": {
    "lead_agent": "deerflow.agents:make_lead_agent"
  },
  "checkpointer": {
    "path": "./packages/harness/deerflow/agents/checkpointer/async_provider.py:make_checkpointer"
  }
}
```

LangGraph Server 启动时读取此配置，将 `make_lead_agent` 注册为可调用的图工厂函数。

### 4.2 图工厂函数

**文件**: `backend/packages/harness/deerflow/agents/lead_agent/agent.py`

```python
from langchain.agents import create_agent

def make_lead_agent(config: RunnableConfig):
    cfg = config.get("configurable", {})
    model_name = cfg.get("model_name")
    thinking_enabled = cfg.get("thinking_enabled", True)
    subagent_enabled = cfg.get("subagent_enabled", False)
    is_plan_mode = cfg.get("is_plan_mode", False)

    return create_agent(
        model=create_chat_model(name=model_name, thinking_enabled=thinking_enabled),
        tools=get_available_tools(model_name=model_name, subagent_enabled=subagent_enabled),
        middleware=_build_middlewares(config, model_name=model_name),
        system_prompt=apply_prompt_template(subagent_enabled=subagent_enabled, ...),
        state_schema=ThreadState,
    )
```

**核心设计决策**: DeerFlow **没有使用** `StateGraph().add_node().add_edge()` 手动定义图，而是通过 `create_agent()` 自动生成 **ReAct 循环图**。

### 4.3 自动生成的 ReAct 图结构

`create_agent()` 内部构建的 LangGraph 图：

```
                ┌──────────────────────────┐
           ┌───►│     Agent 节点 (LLM)     │◄──────┐
           │    │                          │       │
           │    │  ■ 调用 ChatModel        │       │
           │    │  ■ 系统提示注入          │       │
           │    │  ■ 消息历史传递          │       │
           │    └──────────┬───────────────┘       │
           │               │                       │
           │     ┌─────────▼─────────┐             │
           │     │  条件边: 路由判断   │             │
           │     │                   │             │
           │     │  有 tool_calls?   │             │
           │     └───┬─────────┬────┘             │
           │         │         │                   │
           │        YES        NO                  │
           │         │         │                   │
           │         │         ▼                   │
           │         │    ┌─────────┐              │
           │         │    │   END   │              │
           │         │    └─────────┘              │
           │         ▼                             │
           │    ┌───────────────┐                  │
           └────│  Tools 节点    │──────────────────┘
                │               │
                │  ■ 并行执行    │
                │    所有工具调用 │
                │  ■ 中间件包装  │
                │    wrap_tool   │
                └───────────────┘
```

**条件路由规则**:
- LLM 返回包含 `tool_calls` → 进入 Tools 节点 → 回到 Agent 节点（循环）
- LLM 返回不含 `tool_calls`（纯文本）→ 到达 END（结束）

**额外路由中断**:
- `ClarificationMiddleware` — 拦截 `ask_clarification` 工具，返回 `Command(goto=END)` 中断执行
- `LoopDetectionMiddleware` — 检测重复调用，强制剥离 `tool_calls` 终止循环

---

## 五、ThreadState — 图状态定义

### 5.1 状态 Schema

**文件**: `backend/packages/harness/deerflow/agents/thread_state.py`

```python
from langchain.agents import AgentState

class ThreadState(AgentState):
    # 继承自 AgentState 的核心字段
    # messages: Annotated[list[BaseMessage], add_messages]

    # DeerFlow 扩展字段
    sandbox: NotRequired[SandboxState | None]          # 沙箱环境信息
    thread_data: NotRequired[ThreadDataState | None]    # 工作目录路径
    title: NotRequired[str | None]                      # 自动生成标题
    artifacts: Annotated[list[str], merge_artifacts]    # 产出文件 (自定义去重 reducer)
    todos: NotRequired[list | None]                     # 任务列表 (Plan Mode)
    uploaded_files: NotRequired[list[dict] | None]      # 上传文件信息
    viewed_images: Annotated[dict, merge_viewed_images] # 图片缓存 (Vision)
```

### 5.2 辅助状态类型

```python
class SandboxState(TypedDict):
    sandbox_id: NotRequired[str | None]

class ThreadDataState(TypedDict):
    workspace_path: NotRequired[str | None]    # /mnt/user-data/workspace
    uploads_path: NotRequired[str | None]      # /mnt/user-data/uploads
    outputs_path: NotRequired[str | None]      # /mnt/user-data/outputs
```

### 5.3 自定义 Reducer

LangGraph 使用 `Annotated` + reducer 函数管理状态更新：

| 字段 | Reducer | 行为 |
|------|---------|------|
| `messages` | `add_messages`（AgentState 内置） | 追加消息到列表 |
| `artifacts` | `merge_artifacts` | 合并并去重文件路径 |
| `viewed_images` | `merge_viewed_images` | 合并字典，空 `{}` 表示清空 |

### 5.4 Checkpointer — 状态持久化

**文件**: `backend/packages/harness/deerflow/agents/checkpointer/`

| 后端 | 类 | 适用场景 |
|------|------|---------|
| `memory` | `InMemorySaver` | 开发调试 (非持久化) |
| `sqlite` | `SqliteSaver` / `AsyncSqliteSaver` | 单机默认方案 |
| `postgres` | `PostgresSaver` / `AsyncPostgresSaver` | 生产环境 |

Checkpointer 在每次图执行后自动保存 `ThreadState` 全量快照，下次请求时恢复历史状态，实现 **有状态多轮对话**。

---

## 六、中间件管道 — 图行为的核心扩展点

### 6.1 设计理念

DeerFlow 用 **中间件链替代手动图节点**。所有自定义行为通过中间件的钩子函数实现：

| 钩子 | 执行时机 | 典型用途 |
|------|---------|----------|
| `before_agent` | Agent 节点执行前 | 初始化资源（线程路径、沙箱、上传文件） |
| `after_agent` | Agent 节点执行后 | 释放资源（沙箱）、触发异步任务（记忆、标题） |
| `before_model` | LLM 调用前 | 注入上下文（图片数据）、过滤工具 |
| `after_model` | LLM 调用后 | 生成标题、检测循环、限制子代理数量 |
| `wrap_tool_call` | 工具执行时 | 错误处理、拦截澄清请求、安全护栏 |

### 6.2 中间件执行顺序

```
请求进入
    │
    ▼ ─── before_agent ────────────────────────────────
    │
    │  ① ThreadDataMiddleware     初始化线程目录 (workspace/uploads/outputs)
    │  ② UploadsMiddleware        扫描上传文件，注入 <uploaded_files> 到消息
    │  ③ SandboxMiddleware        获取沙箱环境 (lazy/eager 两种模式)
    │  ④ DanglingToolCallMiddleware 修补缺失的 ToolMessage
    │  ⑤ GuardrailMiddleware      安全护栏检查 (可选)
    │
    ▼ ─── before_model / after_model ──────────────────
    │
    │  ⑥ ToolErrorHandlingMiddleware  工具异常 → 错误消息
    │  ⑦ SummarizationMiddleware     Token 超限时自动摘要
    │  ⑧ TodoMiddleware              Plan Mode 任务管理
    │  ⑨ TokenUsageMiddleware        Token 用量追踪
    │  ⑩ TitleMiddleware             首次交互后生成标题
    │  ⑪ MemoryMiddleware            排队记忆更新任务
    │  ⑫ ViewImageMiddleware         注入 Base64 图片到消息
    │  ⑬ DeferredToolFilterMiddleware 隐藏延迟加载工具
    │  ⑭ SubagentLimitMiddleware     截断超限的子代理调用
    │  ⑮ LoopDetectionMiddleware     检测重复调用，强制终止
    │  ⑯ ClarificationMiddleware     拦截澄清请求 → Command(goto=END)
    │
    ▼ ─── wrap_tool_call ──────────────────────────────
    │
    │  ToolErrorHandlingMiddleware → 捕获异常，返回错误 ToolMessage
    │  GuardrailMiddleware         → 执行前安全检查
    │  ClarificationMiddleware     → 拦截 ask_clarification
    │
    ▼ ─── after_agent ─────────────────────────────────
    │
    │  SandboxMiddleware           释放沙箱
    │  MemoryMiddleware            入队记忆更新
    │
    ▼
  返回结果
```

### 6.3 关键中间件详解

#### ClarificationMiddleware — 执行中断

```python
class ClarificationMiddleware(AgentMiddleware):
    def _handle_clarification(self, request: ToolCallRequest) -> Command:
        formatted_message = self._format_clarification_message(args)
        tool_message = ToolMessage(content=formatted_message, ...)
        return Command(
            update={"messages": [tool_message]},
            goto=END,  # 中断执行，等待用户回复
        )
```

这是 LangGraph `Command` 原语的典型应用——通过 `goto=END` 直接跳转到图的结束节点。

#### LoopDetectionMiddleware — 循环打破

```
检测策略:
1. 哈希每次工具调用 (name + args)
2. 滑动窗口追踪近 20 次调用
3. 同一哈希出现 ≥3 次 → 注入警告消息
4. 同一哈希出现 ≥5 次 → 强制剥离 tool_calls → Agent 被迫生成文本回答
```

#### SandboxMiddleware — 懒初始化

```python
class SandboxMiddleware(AgentMiddleware):
    def __init__(self, lazy_init: bool = True):
        self._lazy_init = lazy_init  # 默认延迟到首次工具调用时获取沙箱

    def before_agent(self, state, runtime):
        if self._lazy_init:
            return  # 跳过，等工具调用时再获取
        # eager 模式立即获取沙箱
        sandbox_id = self._acquire_sandbox(thread_id)
        return {"sandbox": {"sandbox_id": sandbox_id}}
```

---

## 七、工具系统 — Tools 节点的内容

### 7.1 工具聚合

**文件**: `backend/packages/harness/deerflow/tools/tools.py`

```python
def get_available_tools(groups=None, include_mcp=True, model_name=None, subagent_enabled=False):
    # 1. 配置工具 (config.yaml)
    loaded_tools = [resolve_variable(tool.use) for tool in config.tools]

    # 2. 内建工具
    builtin_tools = [present_file_tool, ask_clarification_tool]
    if subagent_enabled:
        builtin_tools.append(task_tool)
    if model_config.supports_vision:
        builtin_tools.append(view_image_tool)

    # 3. MCP 工具 (extensions_config.json)
    mcp_tools = get_cached_mcp_tools()

    # 4. ACP Agent 工具
    acp_tools = [build_invoke_acp_agent_tool(acp_agents)]

    return loaded_tools + builtin_tools + mcp_tools + acp_tools
```

### 7.2 工具分类

```
┌─────────────────────────────────────────────────────────────────────┐
│                           工具全景图                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  配置工具 (config.yaml)          内建工具 (builtins/)                │
│  ├── web_search                  ├── present_file     文件展示      │
│  ├── web_fetch                   ├── ask_clarification 追问澄清     │
│  ├── image_search                ├── view_image       图片查看      │
│  ├── bash                        ├── task             子代理委托     │
│  ├── read_file                   ├── setup_agent      Agent 创建    │
│  ├── write_file                  └── tool_search      工具搜索      │
│  ├── str_replace                                                    │
│  └── ls                         MCP 工具 (extensions_config.json)   │
│                                  ├── GitHub MCP                     │
│  ACP Agent 工具                  ├── Filesystem MCP                 │
│  ├── invoke_acp_agent            ├── PostgreSQL MCP                 │
│  │   (Claude Code / Codex)       └── Brave Search MCP               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.3 Tool Search — 延迟加载机制

当 MCP 工具数量多时，全部加入 Context 会消耗大量 Token。DeerFlow 通过 `DeferredToolFilterMiddleware` + `tool_search` 实现延迟加载：

1. MCP 工具注册到 `DeferredToolRegistry`（仅名称和描述）
2. `DeferredToolFilterMiddleware` 在 `before_model` 时从工具列表中移除已注册的延迟工具
3. Agent 在需要时调用 `tool_search` 按名称搜索和加载

---

## 八、子代理系统 — task 工具的执行机制

### 8.1 架构

```
Lead Agent
    │
    │  调用 task(description, prompt, subagent_type)
    ▼
┌────────────────────────────────────────────────────┐
│                    task_tool.py                      │
│                                                     │
│  1. 获取子代理配置 (SubagentConfig)                  │
│  2. 创建 SubagentExecutor                           │
│  3. executor.execute_async(prompt) → task_id        │
│  4. 轮询等待完成，通过 stream_writer 发送进度         │
│                                                     │
└──────────────────────┬─────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────┐
│               SubagentExecutor                      │
│                                                     │
│  ┌──────────────────┐  ┌──────────────────┐        │
│  │  scheduler_pool   │  │  execution_pool  │        │
│  │  (3 workers)     │  │  (3 workers)     │        │
│  │  调度任务         │  │  执行子代理       │        │
│  └──────────────────┘  └──────────────────┘        │
│                                                     │
│  子代理同样通过 create_agent() 创建:                  │
│  ■ 更简化的中间件链 (无 Todo/Uploads/Title)          │
│  ■ 不包含 task_tool (防止递归嵌套)                   │
│  ■ 继承父代理的模型、沙箱、线程数据                   │
│                                                     │
└────────────────────────────────────────────────────┘
```

### 8.2 执行流程

```python
# task_tool.py 核心流程
task_id = executor.execute_async(prompt, task_id=tool_call_id)
writer({"type": "task_started", "task_id": task_id, "description": description})

while True:
    result = get_background_task_result(task_id)

    # 发送进度消息
    for new_message in result.ai_messages[last_count:]:
        writer({"type": "task_running", "task_id": task_id, "message": new_message})

    if result.status == SubagentStatus.COMPLETED:
        writer({"type": "task_completed", "task_id": task_id})
        return f"Task Succeeded. Result: {result.result}"
    elif result.status == SubagentStatus.FAILED:
        return f"Task failed. Error: {result.error}"
    elif result.status == SubagentStatus.TIMED_OUT:
        return f"Task timed out."

    time.sleep(5)  # 每 5 秒轮询
```

### 8.3 内置子代理类型

| 类型 | 工具集 | 用途 |
|------|--------|------|
| `general-purpose` | 全部工具 (除 task) | 复杂多步骤研究/分析/代码任务 |
| `bash` | 仅 bash | Git、构建、部署等命令操作 |

---

## 九、流式响应机制

### 9.1 LangGraph Server 原生 SSE

LangGraph Server 内置 SSE (Server-Sent Events) 流式支持，客户端通过 `stream_mode` 参数选择流模式：

| 流模式 | 内容 | 用途 |
|--------|------|------|
| `messages-tuple` | 每条消息的增量更新 | AI 文本逐字输出、工具调用/结果 |
| `values` | 完整状态快照 | 标题、产物列表、任务列表同步 |
| `custom` | 自定义事件 | 子代理进度 (task_started/running/completed) |

### 9.2 IM 频道流式

```python
# ChannelManager 流式调用
async for chunk in client.runs.stream(
    thread_id, assistant_id,
    input={"messages": [{"role": "human", "content": msg.text}]},
    stream_mode=["messages-tuple", "values"],
):
    event = chunk.event
    data = chunk.data
    # 累积文本并定期推送到 IM
```

### 9.3 嵌入式客户端流式

```python
# DeerFlowClient.stream()
for chunk in self._agent.stream(state, config=config, stream_mode="values"):
    for msg in chunk.get("messages", []):
        if isinstance(msg, AIMessage):
            yield StreamEvent(type="messages-tuple", data={"type": "ai", "content": text})
        elif isinstance(msg, ToolMessage):
            yield StreamEvent(type="messages-tuple", data={"type": "tool", ...})
    yield StreamEvent(type="values", data={"title": ..., "artifacts": ...})
yield StreamEvent(type="end", data={"usage": cumulative_usage})
```

---

## 十、System Prompt 动态生成

### 10.1 模板结构

**文件**: `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`

```
SYSTEM_PROMPT_TEMPLATE 结构:
├── <role>                     Agent 身份定义
├── <soul>                     Agent 人格 (SOUL.md, 可选)
├── <memory>                   长期记忆注入 (置信度过滤)
├── <thinking_style>           思维风格指导
├── <clarification_system>     澄清追问规则
├── <skill_system>             可用技能列表 + 加载指引
├── <available-deferred-tools> 延迟加载工具名录
├── <subagent_system>          子代理编排策略 (含并发限制)
├── <working_directory>        虚拟文件系统路径说明
├── <response_style>           输出风格指导
├── <citations>                引用格式规范
├── <critical_reminders>       关键提醒
└── <current_date>             当前日期
```

### 10.2 动态内容注入

| 动态部分 | 来源 | 触发条件 |
|----------|------|---------|
| `soul` | `agents/{name}/SOUL.md` | 自定义 Agent 时 |
| `memory_context` | `memory.json` → LLM 提取 | 记忆系统启用时 |
| `skills_section` | `skills/*/SKILL.md` | 有启用的技能时 |
| `subagent_section` | 模板生成 | `subagent_enabled=True` |
| `deferred_tools_section` | MCP 工具注册表 | `tool_search.enabled` |
| `acp_section` | ACP 配置 | 有 ACP Agent 配置时 |

---

## 十一、LangGraph 在架构中的作用总结

```
┌─────────────────────────────────────────────────────────────────────┐
│                    LangGraph 的七大核心职责                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. 图运行时        自动构建 ReAct 循环 (Agent ↔ Tools)             │
│                     管理节点间状态传递和条件路由                      │
│                                                                     │
│  2. 状态管理        ThreadState + Checkpointer                      │
│                     实现有状态多轮对话                                │
│                                                                     │
│  3. 流式传输        SSE 原生支持                                     │
│                     messages-tuple / values / custom 三种模式        │
│                                                                     │
│  4. 线程隔离        每个对话一个 thread_id                           │
│                     隔离状态、文件系统、沙箱                          │
│                                                                     │
│  5. 中间件扩展      before/after_agent, before/after_model          │
│                     wrap_tool_call — 5 个钩子点                     │
│                                                                     │
│  6. 控制流          Command(goto=END) 实现执行中断                   │
│                     支持澄清追问、错误恢复等场景                      │
│                                                                     │
│  7. 服务化部署      LangGraph Server 提供标准化 HTTP API             │
│                     线程 CRUD、运行管理、SSE 流式                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 十二、与传统 LangGraph 用法的对比

| 维度 | 传统 LangGraph 用法 | DeerFlow 的用法 |
|------|---------------------|----------------|
| **图定义** | 手动 `StateGraph().add_node().add_edge()` | `create_agent()` 自动生成 |
| **节点实现** | 自定义函数作为节点 | 中间件链替代节点 |
| **条件路由** | `add_conditional_edges()` | 隐式 (有 tool_calls → Tools, 无 → END) |
| **状态 Schema** | 自定义 `TypedDict` | 继承 `AgentState` + 扩展字段 |
| **扩展方式** | 添加新节点和边 | 添加新中间件 |
| **控制流** | 自定义路由函数 | `Command(goto=END)` + 中间件拦截 |

**DeerFlow 的设计优势**:
- 中间件可独立开关，无需修改图结构
- 中间件间解耦，不同关注点完全隔离
- 新增功能只需编写一个中间件类，不影响已有逻辑

---

> **文档生成**: AI 辅助分析，基于源码阅读，仅供技术参考  
> **项目地址**: https://github.com/bytedance/deer-flow  
> **关联文档**: [DeerFlow 2.0 架构设计实现方案调研报告](./DeerFlow_Architecture_Report.md)
