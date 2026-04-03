# DeerFlow Agent 设计与实现调研文档

**文档版本**: v1.0  
**更新时间**: 2025-02-28  
**研究范围**: DeerFlow 2.0 Agent 系统架构、设计模式、实现细节

---

## 📋 目录

1. [项目概述](#项目概述)
2. [Agent 系统架构](#agent-系统架构)
3. [核心 Agent 类型](#核心-agent-类型)
4. [状态管理与通信](#状态管理与通信)
5. [工具系统](#工具系统)
6. [子 Agent 执行引擎](#子-agent-执行引擎)
7. [中间件管道](#中间件管道)
8. [记忆系统](#记忆系统)
9. [设计模式与最佳实践](#设计模式与最佳实践)
10. [安全机制](#安全机制)

---

## 项目概述

**DeerFlow 2.0** 是一个开源的**超级 Agent 框架**，基于 **LangGraph** 和 **LangChain** 构建，用于协调复杂的多 Agent 任务。

### 核心特性

- ✅ **Lead Agent 主协调器** - 中央指挥，具备工具委托能力
- ✅ **并行子 Agent** - 专业化任务执行器（通用、Bash）
- ✅ **持久化记忆系统** - 每个 Agent 独立的长期记忆存储
- ✅ **14 阶段中间件管道** - 工具执行、记忆更新、状态管理
- ✅ **多层工具生态** - 内置工具 + 配置工具 + MCP + ACP

### 项目结构

```
backend/packages/harness/deerflow/
├── agents/
│   ├── lead_agent/              # Lead Agent 实现
│   │   ├── agent.py            # Lead Agent 工厂函数
│   │   └── prompt.py           # 系统提示词构建
│   ├── middlewares/             # 14 阶段中间件管道
│   ├── memory/                  # 记忆系统
│   └── thread_state.py         # 对话状态架构
├── subagents/                   # 子 Agent 系统
│   ├── executor.py             # 子 Agent 执行引擎
│   ├── config.py               # 子 Agent 配置
│   └── builtins/               # 内置子 Agent（通用、Bash）
├── tools/                       # 工具系统
│   ├── tools.py                # 工具解析
│   └── builtins/               # 内置工具（任务、澄清）
└── config/                      # 配置管理
    ├── agents_config.py        # 自定义 Agent 加载
    └── subagents_config.py     # 子 Agent 超时配置
```

---

## Agent 系统架构

### 系统设计图

```
┌──────────────────────────────────────────────────────────────┐
│                    User Input                                 │
└──────────────────────────────────────┬───────────────────────┘
                                      │
                                      ▼
        ┌─────────────────────────────────────────────────────┐
        │            Lead Agent (LangGraph)                    │
        │  ┌─────────────────────────────────────────────────┐ │
        │  │  System Prompt (11 Components Dynamic Build)    │ │
        │  │  - Agent Role + Soul (Personality)             │ │
        │  │  - Memory Context (Per-agent Long-term)        │ │
        │  │  - Skills Configuration                        │ │
        │  │  - Subagent Instructions & Batching Strategy   │ │
        │  │  - Tool Availability                           │ │
        │  └─────────────────────────────────────────────────┘ │
        │                      │                               │
        │                      ▼                               │
        │         ┌────────────────────────┐                  │
        │         │  Tool Orchestration    │                  │
        │         │  (50+ Available Tools) │                  │
        │         └────────────────────────┘                  │
        │              │              │                       │
        │    ┌─────────┘              └──────────┬──────────┐ │
        │    │                                    │          │  │
        │    ▼                                    ▼          ▼  │
        │  Built-in                         External      MCP   │
        │  Tools                             Tools        Tools │
        │  - task()                    (Config-defined)  (Discovery)
        │  - ask_clarification()            │              │   │
        │  - present_file()                 │              │   │
        │                                    │              │   │
        └────────────────────────────────────┼──────────────┼───┘
                                            │              │
                    ┌──────────────────────┘  │              │
                    │         ┌───────────────┘              │
                    ▼         │                              ▼
            ┌──────────────┐  │                    ┌─────────────────┐
            │ Subagent    │  │                    │   MCP Server    │
            │ (Parallel)  │  │                    │   (Tool Search) │
            │             │  │                    │                 │
            │ - Execute   │  │                    │ - Deferred      │
            │ - Monitor   │  │                    │   Tool Schemas  │
            │ - Report    │  │                    └─────────────────┘
            └──────────────┘  │
                              │
                    ┌─────────┘
                    │
                    ▼
        ┌─────────────────────────────────────────┐
        │      14-Stage Middleware Pipeline        │
        │  (Thread Data → Sandbox → Uploads → ... │
        │   ... → Memory → Title → Clarification) │
        └─────────────────────────────────────────┘
                    │
                    ▼
        ┌─────────────────────────────────────────┐
        │           Output to User                 │
        │  (Messages + Artifacts + Memory Update) │
        └─────────────────────────────────────────┘
```

### 系统交互流程

```
User Query
  │
  ├─→ ThreadDataMiddleware (工作区初始化)
  │
  ├─→ SandboxMiddleware (沙箱环境)
  │
  ├─→ UploadsMiddleware (文件列表)
  │
  ├─→ Lead Agent Decision
  │     │
  │     ├─→ 使用内置工具 (ask_clarification, present_file)
  │     │
  │     ├─→ 调用子 Agent (task_tool)
  │     │     │
  │     │     └─→ SubagentExecutor
  │     │         ├─ 创建子 Agent 实例
  │     │         ├─ 流式执行 (astream)
  │     │         ├─ 实时捕获 AI 消息
  │     │         ├─ 超时控制 (900s 默认)
  │     │         └─ 返回结果
  │     │
  │     └─→ 调用外部工具 (MCP/Config-defined)
  │
  ├─→ MemoryMiddleware (记忆更新队列)
  │
  ├─→ ClarificationMiddleware (澄清拦截)
  │
  └─→ 返回结果给用户
```

---

## 核心 Agent 类型

### 1. Lead Agent（主协调器）

**文件位置**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/agent.py`

#### 工厂函数

```python
def make_lead_agent(config: RunnableConfig) -> Runnable
```

#### 核心功能

| 功能 | 说明 |
|------|------|
| **模型选择** | 3 层优先级：运行时 → Agent 配置 → 全局默认 |
| **扩展思考** | o1/Claude Opus 风格推理支持 |
| **计划模式** | TodoList 中间件，任务追踪 |
| **Bootstrap 模式** | 自定义 Agent 创建流程 |
| **个性注入** | 从 SOUL.md 注入个性化指令 |

#### 系统提示词构建

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/prompt.py`

系统提示词由 **11 个动态组件** 构建：

| 序号 | 组件 | 来源 | 用途 |
|------|------|------|------|
| 1 | Agent Role | 硬编码 | "你是 DeerFlow 2.0..." |
| 2 | Soul (个性) | SOUL.md | 自定义个性化指令 |
| 3 | Memory Context | 记忆系统 | 长期记忆注入 |
| 4 | Skills 配置 | 配置文件 | 可用技能列表 |
| 5 | Deferred Tools | MCP 服务 | 动态工具发现 |
| 6 | Subagent 指令 | 内置 | 任务分解与批处理策略 |
| 7 | Working Directory | 运行时 | `/mnt/user-data/{uploads,workspace,outputs}` |
| 8 | 响应风格 | 硬编码 | 清晰、行动导向 |
| 9 | 引用格式 | 硬编码 | 源码引用规范 |
| 10 | 关键提醒 | 硬编码 | 澄清优先、技能加载、输出处理 |
| 11 | 批处理策略 | 内置 | 并发限制解决方案 |

**示例提示词片段**:

```xml
You are DeerFlow 2.0, an open-source super agent harness.

<soul>
[SOUL.md 的内容 - 自定义个性]
</soul>

<memory_context>
[Long-term memory from storage - if enabled]
</memory_context>

<available_skills>
[列出所有可用技能及其文件路径]
</available_skills>

<subagent_instructions>
如果任务中有多个独立子任务：
1. 计数：我需要完成 N 个子任务
2. 批处理：如果 N > 3，规划批次
3. 执行：使用 task() 工具启动当前批次（≤3 个）
4. 重复：下一轮启动下一批
5. 综合：所有完成后，综合结果
</subagent_instructions>
```

### 2. 子 Agent（并行任务执行器）

**位置**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/subagents/`

#### 2.1 通用子 Agent (General-Purpose)

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/subagents/builtins/general_purpose.py`

**配置特性**:
- **最大回合数**: 50
- **超时时间**: 900 秒（15 分钟，可配置）
- **模型继承**: 默认继承父 Agent 的模型
- **工具**：继承父 Agent 的所有工具，除了 `task_tool`（防止嵌套）
- **用途**：研究、分析、代码探索、数据收集

**使用示例**:

```python
# Lead Agent 中调用通用子 Agent
result = await task_tool(
    description="研究项目代码结构",
    prompt="分析 src/ 目录下的文件组织，找出核心模块",
    subagent_type="general-purpose",
    max_turns=20  # 可选，超过默认值
)
```

#### 2.2 Bash 子 Agent

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/subagents/builtins/bash_agent.py`

**配置特性**:
- **专用工具**: Bash 命令执行
- **用途**：Git 操作、编译构建、部署
- **超时**：同样遵循全局配置（可在子 Agent 级别覆盖）

**使用示例**:

```python
result = await task_tool(
    description="构建项目并运行测试",
    prompt="运行 npm install，然后 npm test",
    subagent_type="bash"
)
```

#### 子 Agent 配置模式

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/subagents/config.py`

```python
@dataclass
class SubagentConfig:
    name: str                      # "general-purpose", "bash"
    description: str               # 用途描述
    model: str = "inherit"         # "inherit" 继承父模型
    max_turns: int = 50            # 最大回合数
    timeout_seconds: int = 900     # 超时时间
    tools_filter: list[str] | None = None  # 工具过滤
```

---

## 状态管理与通信

### ThreadState 架构

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/agents/thread_state.py`

```python
class ThreadState(AgentState):
    # 执行环境
    sandbox: SandboxState | None              # 沙箱上下文
    thread_data: ThreadDataState | None       # 工作区路径
    
    # 对话内容
    messages: list[BaseMessage]               # 对话历史
    
    # 元数据
    title: str | None                         # 自动生成的线程标题
    artifacts: list[str]                      # 生成的可交付物
    
    # 任务追踪（仅在计划模式）
    todos: list | None                        # 任务列表
    
    # 文件管理
    uploaded_files: list[dict] | None         # 会话上传的文件
    viewed_images: dict                       # 查看过的图像
```

### 消息流

```
用户输入
  │
  ├─→ HumanMessage(content="...")            [输入消息]
  │
  ├─→ Lead Agent 思考
  │
  ├─→ AIMessage(tool_calls=[...])            [工具调用]
  │     │
  │     └─→ [工具1, 工具2, 工具3]
  │
  ├─→ ToolMessage(tool_name, result)         [工具结果]
  │     │
  │     └─→ [结果1, 结果2, 结果3]
  │
  └─→ AIMessage(content="最终回应")          [最终响应]
```

### 中间件可拦截点

中间件可以在以下关键点拦截执行流程：

1. **澄清拦截** - 停止执行并请求用户输入
2. **记忆更新** - 异步更新长期记忆
3. **标题生成** - 自动生成对话标题
4. **令牌计数** - 跟踪消耗的令牌数

---

## 工具系统

### 工具分类

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/tools/tools.py`

#### 1. 始终可用工具

| 工具 | 签名 | 用途 |
|------|------|------|
| `present_file_tool` | `(file_path: str) → None` | 向用户展示文件内容 |
| `ask_clarification_tool` | `(questions: list[dict]) → dict` | 请求用户输入 |

#### 2. 条件可用工具

| 工具 | 条件 | 用途 |
|------|------|------|
| `view_image_tool` | 模型支持视觉 | 查看和分析图像 |
| `task_tool` | subagent_enabled=True | 子 Agent 委托 |
| `tool_search` | tool_search_enabled=True | MCP 工具发现 |
| `invoke_acp_agent` | ACP 配置 | ACP Agent 集成 |

#### 3. 工具解析策略 (`get_available_tools()`)

**优先级顺序**:
1. 配置定义的工具（按分组过滤）
2. 内置工具（条件判断）
3. MCP 工具（从缓存加载）
4. ACP 工具
5. 延迟工具（如果启用工具搜索）

```python
def get_available_tools(config: Config) -> list[Tool]:
    tools = []
    
    # 1. Config-defined tools
    tools.extend(config.tool_groups[selected_group])
    
    # 2. Builtin tools
    tools.append(task_tool)                      # if subagent_enabled
    tools.append(view_image_tool)                # if model supports vision
    tools.extend([ask_clarification, present_file])  # always
    
    # 3. MCP tools (cached discovery)
    tools.extend(mcp_cache.get_tools())
    
    # 4. ACP tools
    tools.extend(acp_registry.get_tools())
    
    # 5. Deferred tools (if tool_search enabled)
    if config.tool_search_enabled:
        tools.append(tool_search)
    
    return tools
```

### Task 工具（子 Agent 接口）

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/tools/builtins/task_tool.py`

#### 函数签名

```python
async def task_tool(
    description: str,           # 任务简短描述，e.g. "分析代码结构"
    prompt: str,                # 完整任务指令
    subagent_type: Literal["general-purpose", "bash"],
    max_turns: int | None = None  # 可选：覆盖默认值
) -> str
```

#### 执行流程

```
1. 加载子 Agent 配置
   ├─ name: "general-purpose" 或 "bash"
   ├─ model: 继承父 Agent 模型
   └─ max_turns: 使用提供的值或默认值
   
2. 提取父 Agent 上下文
   ├─ Model configuration
   ├─ Sandbox state
   ├─ Thread data (工作区路径)
   ├─ Trace ID (分布式追踪)
   └─ Memory (如果启用)
   
3. 获取可用工具
   └─ 排除 task_tool（防止嵌套）
   
4. 创建 SubagentExecutor 实例
   
5. 启动后台执行（返回 task_id）
   
6. 轮询等待完成（每 5 秒）
   
7. 流式传输进度事件
   ├─ task_started
   ├─ task_running
   └─ task_completed
   
8. 返回最终结果或错误
```

#### 使用场景

**场景 1: 简单单个子任务**
```python
result = await task_tool(
    description="分析项目依赖",
    prompt="使用 pip list 或 npm list 列出所有依赖",
    subagent_type="general-purpose"
)
```

**场景 2: 多个并行子任务（批处理）**
```python
# Turn 1: 启动 3 个并行任务
results = []
for task in [task1, task2, task3]:
    result = await task_tool(
        description=task.title,
        prompt=task.instruction,
        subagent_type="general-purpose"
    )
    results.append(result)

# Turn 2: 综合结果
final = "任务 1 结果: ...\n任务 2 结果: ...\n任务 3 结果: ..."
```

---

## 子 Agent 执行引擎

### SubagentExecutor 实现

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/subagents/executor.py`

#### 核心类结构

```python
class SubagentExecutor:
    """子 Agent 执行引擎"""
    
    def __init__(
        self,
        task_id: str,
        config: SubagentConfig,
        parent_config: RunnableConfig,
        parent_context: ExecutionContext
    ):
        self.task_id = task_id
        self.config = config
        self.executor = ThreadPoolExecutor(
            max_workers=3,  # 调度线程
            factory=thread_pool_with_3_execution_workers
        )
```

#### 关键方法

**1. 异步执行 (`_aexecute`)**

```python
async def _aexecute(self, task: str) -> SubagentResult:
    """异步执行子任务"""
    
    # 创建 Agent 实例
    agent = make_lead_agent(self.config)
    
    # 流式执行并实时捕获消息
    ai_messages = []
    async for event in agent.astream({"messages": [HumanMessage(task)]}):
        if isinstance(event.get("messages"), AIMessage):
            ai_messages.append(event["messages"])
    
    # 提取最终消息
    final_message = ai_messages[-1].content if ai_messages else ""
    
    return SubagentResult(
        task_id=self.task_id,
        trace_id=self.parent_context.trace_id,
        status=SubagentStatus.COMPLETED,
        result=final_message,
        ai_messages=ai_messages
    )
```

**2. 同步包装 (`execute`)**

```python
def execute(self, task: str) -> SubagentResult:
    """同步执行（在新事件循环中）"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(self._aexecute(task))
    finally:
        loop.close()
```

**3. 后台执行 (`execute_async`)**

```python
def execute_async(self, task: str) -> str:
    """后台执行，立即返回 task_id"""
    
    # 提交到线程池
    future = self.executor.submit(
        self.execute,
        task,
        timeout=self.config.timeout_seconds
    )
    
    # 存储 future 以供后续查询
    self._futures[self.task_id] = future
    
    # 立即返回（不阻塞）
    return self.task_id
```

#### 执行状态生命周期

```
        ┌────────────────────────────────────┐
        │ PENDING (初始状态)                 │
        └────────┬─────────────────────┬────┘
                 │                     │
             (execute)            (execute)
                 │                     │
                 ▼                     ▼
        ┌─────────────────┐   ┌──────────────────┐
        │ RUNNING         │   │ RUNNING          │
        │ (同步阻塞)      │   │ (后台轮询)       │
        └────────┬────────┘   └────────┬─────────┘
                 │                     │
            (完成)                 (完成或超时)
                 │                     │
                 ▼                     ▼
        ┌──────────────────────────────────────┐
        │ COMPLETED (成功)                     │
        │ FAILED (错误)                        │
        │ TIMED_OUT (超时 - 900s 默认)         │
        └──────────────────────────────────────┘
```

#### SubagentResult 数据结构

```python
@dataclass
class SubagentResult:
    task_id: str                          # 唯一执行 ID
    trace_id: str                         # 分布式追踪 ID
    status: SubagentStatus                # 执行状态
    result: str | None                    # 最终结果文本
    error: str | None                     # 错误信息
    started_at: datetime | None           # 开始时间
    completed_at: datetime | None         # 完成时间
    ai_messages: list[dict]               # 捕获的所有 AI 消息
```

#### 并发执行示例

```python
# Lead Agent 代码
async def execute_multiple_tasks():
    """并行执行 3 个子任务"""
    
    results = await asyncio.gather(
        task_tool("任务 1", "...", "general-purpose"),
        task_tool("任务 2", "...", "general-purpose"),
        task_tool("任务 3", "...", "general-purpose")
    )
    
    # 所有 3 个任务同时执行
    return results
```

---

## 中间件管道

### 14 阶段中间件架构

**位置**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/agents/middlewares/`

中间件按**严格顺序**执行，每个中间件可以拦截、修改或中止执行流程。

#### 执行顺序与功能

| 阶段 | 中间件 | 文件 | 职责 | 关键操作 |
|------|--------|------|------|---------|
| 1 | ThreadDataMiddleware | thread_data_middleware.py | 工作区初始化 | 提取 thread_id，设置 `/mnt/user-data/{uploads,workspace,outputs}` |
| 2 | SandboxMiddleware | (sandbox module) | 沙箱初始化 | 初始化容器执行环境 |
| 3 | UploadsMiddleware | uploads_middleware.py | 文件列表 | 列出用户上传的文件，注入到上下文 |
| 4 | DanglingToolCallMiddleware | dangling_tool_call_middleware.py | 工具调用修复 | 修补缺失的 ToolMessage（恢复不完整响应） |
| 5 | SummarizationMiddleware (可选) | (LangChain 内置) | 上下文压缩 | 总结早期消息减少令牌使用 |
| 6 | TodoListMiddleware (可选) | todo_middleware.py | 任务追踪 | 启用 `todos` 字段用于任务列表（plan_mode） |
| 7 | TokenUsageMiddleware (可选) | token_usage_middleware.py | 令牌计数 | 追踪消耗的令牌数 |
| 8 | TitleMiddleware | title_middleware.py | 标题生成 | 根据消息自动生成线程标题 |
| 9 | MemoryMiddleware | memory_middleware.py | 记忆队列 | 过滤消息并排队异步更新 |
| 10 | ViewImageMiddleware (可选) | view_image_middleware.py | 图像注入 | 注入 base64 编码的图像数据 |
| 11 | DeferredToolFilterMiddleware (可选) | deferred_tool_filter_middleware.py | 工具隐藏 | 隐藏延迟工具的完整架构（减少令牌） |
| 12 | SubagentLimitMiddleware (可选) | subagent_limit_middleware.py | 并发限制 | 强制执行 `max_concurrent_subagents`（硬限制） |
| 13 | LoopDetectionMiddleware | loop_detection_middleware.py | 无限循环检测 | 打破无限工具调用循环 |
| 14 | ClarificationMiddleware | clarification_middleware.py | **澄清拦截** | 拦截 `ask_clarification`，中止执行待用户输入 |

### 重要中间件实现细节

#### MemoryMiddleware - 消息过滤

```python
class MemoryMiddleware:
    """记忆更新中间件"""
    
    def filter_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
        """只保留记忆相关的消息"""
        
        filtered = []
        for msg in messages:
            # ✅ 保留：HumanMessage
            if isinstance(msg, HumanMessage):
                filtered.append(msg)
            
            # ✅ 保留：AIMessage（仅当无工具调用）
            elif isinstance(msg, AIMessage) and not msg.tool_calls:
                filtered.append(msg)
                
            # ❌ 丢弃：ToolMessage（工具执行中间步骤）
            elif isinstance(msg, ToolMessage):
                continue
            
            # 特殊处理：删除会话临时数据
            if "<uploaded_files>" in msg.content:
                msg.content = remove_xml_block(msg.content, "uploaded_files")
        
        return filtered
```

**关键特性**:
- ✅ 保留用户消息和最终 AI 响应
- ❌ 删除所有工具中间步骤（减少记忆体积）
- 🧹 删除 `<uploaded_files>` 等会话临时数据

#### ClarificationMiddleware - 澄清拦截

```python
class ClarificationMiddleware:
    """澄清工具拦截中间件"""
    
    def process(state: ThreadState) -> ThreadState:
        """检查是否有澄清请求，如有则拦截"""
        
        # 检查最后的 AIMessage 是否调用了 ask_clarification
        last_msg = state.messages[-1]
        
        if last_msg.tool_calls and any(
            call.name == "ask_clarification" for call in last_msg.tool_calls
        ):
            # 1. 停止执行流程
            state.interrupt = True
            
            # 2. 格式化澄清问题
            questions = extract_questions(last_msg.tool_calls)
            
            # 3. 向用户展示问题
            return {
                "state": state,
                "interrupt_reason": "clarification_needed",
                "questions": questions
            }
        
        return state
```

#### SubagentLimitMiddleware - 并发硬限制

```python
class SubagentLimitMiddleware:
    """子 Agent 并发限制中间件"""
    
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.active_count = 0
    
    def process(state: ThreadState) -> ThreadState:
        """监控 task() 调用"""
        
        last_msg = state.messages[-1]
        task_calls = [
            call for call in last_msg.tool_calls 
            if call.name == "task_tool"
        ]
        
        # 计数当前活跃的子 Agent
        self.active_count += len(task_calls)
        
        if self.active_count > self.max_concurrent:
            # 警告：丢弃超出限制的任务！
            print(f"⚠️  WARNING: Discarding {self.active_count - self.max_concurrent} task calls!")
            
            # 只保留前 N 个
            task_calls = task_calls[:self.max_concurrent - (self.active_count - len(task_calls))]
        
        return state
```

**⚠️ 重要警告**: 此中间件会**静默丢弃**超出限制的任务，导致工作丢失！

### 中间件交互示例

```
Input: User Query + Tool Calls
  │
  ├─→ ThreadDataMiddleware
  │   修改: 添加 thread_data 到状态
  │
  ├─→ SandboxMiddleware
  │   修改: 初始化沙箱环境
  │
  ├─→ MemoryMiddleware
  │   修改: 队列异步记忆更新
  │
  ├─→ SubagentLimitMiddleware ⚠️
  │   可能动作: 丢弃超过 3 个的 task() 调用
  │
  ├─→ ClarificationMiddleware
  │   可能动作: 拦截执行，请求用户输入
  │
  └─→ 返回处理后的状态
```

---

## 记忆系统

### 架构设计

**文件位置**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/agents/memory/`

```
┌─────────────────────────────────────────────┐
│          Memory System Architecture          │
├─────────────────────────────────────────────┤
│                                             │
│  ┌───────────────────────────────────────┐ │
│  │ MemoryMiddleware                      │ │
│  │ - 过滤消息                            │ │
│  │ - 排队异步更新                        │ │
│  │ - 移除临时数据                        │ │
│  └───────────────┬───────────────────────┘ │
│                  │                         │
│                  ▼                         │
│  ┌───────────────────────────────────────┐ │
│  │ MemoryQueue (线程安全)                │ │
│  │ - 消息队列                            │ │
│  │ - 处理并发更新                        │ │
│  └───────────────┬───────────────────────┘ │
│                  │                         │
│                  ▼                         │
│  ┌───────────────────────────────────────┐ │
│  │ MemoryUpdater (后台线程)              │ │
│  │ - 消费队列消息                        │ │
│  │ - 计算摘要                            │ │
│  │ - 写入存储                            │ │
│  └───────────────┬───────────────────────┘ │
│                  │                         │
│                  ▼                         │
│  ┌───────────────────────────────────────┐ │
│  │ FileMemoryStorage (持久化)            │ │
│  │ - agents/{agent_name}/memory.json     │ │
│  │ - 支持每个 Agent 独立记忆             │ │
│  └───────────────────────────────────────┘ │
│                  │                         │
│                  ▼                         │
│  ┌───────────────────────────────────────┐ │
│  │ PromptMemory (注入系统提示)           │ │
│  │ - 格式化记忆为提示词片段              │ │
│  │ - 在 Lead Agent 初始化时注入          │ │
│  └───────────────────────────────────────┘ │
│                                             │
└─────────────────────────────────────────────┘
```

### 记忆存储结构

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/agents/memory/storage.py`

```json
{
  "version": "1.0",
  "lastUpdated": "2025-02-28T10:30:00Z",
  "user": {
    "workContext": {
      "summary": "用户正在开发 DeerFlow 项目，专注于 Agent 架构设计",
      "updatedAt": "2025-02-28T10:30:00Z"
    },
    "personalContext": {
      "summary": "用户倾向于深度技术分析，关注系统设计模式",
      "updatedAt": "2025-02-27T15:00:00Z"
    },
    "topOfMind": {
      "summary": "当前研究子 Agent 并发控制机制",
      "updatedAt": "2025-02-28T10:30:00Z"
    }
  },
  "history": {
    "recentMonths": {
      "summary": "过去 3 个月内讨论的主要话题：Agent 架构、工具系统、中间件设计",
      "updatedAt": "2025-02-28T10:00:00Z"
    },
    "earlierContext": {
      "summary": "更早期的项目背景和决策历史",
      "updatedAt": "2025-02-20T00:00:00Z"
    },
    "longTermBackground": {
      "summary": "长期的背景信息和项目历史",
      "updatedAt": "2025-01-01T00:00:00Z"
    }
  },
  "facts": [
    "DeerFlow 2.0 基于 LangGraph 构建",
    "Lead Agent 支持 50+ 工具",
    "默认最大并发子 Agent 数为 3"
  ]
}
```

### 每个 Agent 独立记忆

```
agents/
├── lead_agent/
│   └── memory.json                 # Lead Agent 的独立记忆
├── researcher/
│   └── memory.json                 # Researcher Agent 的独立记忆
└── code_analyzer/
    └── memory.json                 # Code Analyzer Agent 的独立记忆
```

### 消息过滤与更新流程

```
1. Lead Agent 执行对话
   │
   ├─→ HumanMessage: "分析项目代码"
   │
   ├─→ AIMessage (tool_calls=[task(...)])
   │   └─→ MemoryMiddleware: ✅ 保留（有内容）
   │
   ├─→ ToolMessage (task() 执行结果)
   │   └─→ MemoryMiddleware: ❌ 丢弃（中间步骤）
   │
   ├─→ AIMessage (最终响应): "代码分析完成..."
   │   └─→ MemoryMiddleware: ✅ 保留（最终响应）
   │
   └─→ 过滤后的消息列表 → MemoryQueue
   
2. MemoryUpdater 后台处理
   │
   ├─→ 消费过滤的消息
   ├─→ 计算 LLM 摘要
   ├─→ 更新相关的记忆段落
   └─→ 写入 agents/{agent_name}/memory.json

3. 下次对话初始化
   │
   └─→ PromptMemory 格式化记忆
       └─→ 注入系统提示词（见上文"系统提示词构建"第 3 项）
```

### 记忆更新器

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/agents/memory/updater.py`

```python
class MemoryUpdater:
    """后台异步记忆更新处理器"""
    
    async def process_queue(self):
        """不断消费队列中的消息"""
        while True:
            messages = await self.queue.get_batch(timeout=5)
            
            if not messages:
                continue
            
            # 为每个消息生成摘要
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    # 更新 topOfMind
                    summary = await llm.summarize(msg.content)
                    memory.user.topOfMind.summary = summary
                    
                elif isinstance(msg, AIMessage):
                    # 更新 workContext
                    summary = await llm.summarize(msg.content)
                    memory.user.workContext.summary = summary
            
            # 持久化更新
            storage.save(memory)
```

---

## 设计模式与最佳实践

### 1. 中间件链模式

**模式描述**: 将复杂的处理逻辑分解为可组合的中间件，按严格顺序执行。

**优点**:
- ✅ 清晰的职责分离
- ✅ 易于添加/移除中间件
- ✅ 便于测试和维护
- ✅ 支持条件启用

**实现**:
```python
middlewares = [
    ThreadDataMiddleware(),
    SandboxMiddleware(),
    UploadsMiddleware(),
    # ... 其他中间件
    ClarificationMiddleware()
]

for middleware in middlewares:
    state = middleware.process(state)
```

### 2. 工具流式处理模式

**模式描述**: 在后台执行长时间任务时，使用 `astream()` 实时捕获 AI 消息。

**优点**:
- ✅ 实时反馈用户
- ✅ 支持中断和取消
- ✅ 更好的用户体验

**实现**:
```python
ai_messages = []
async for event in agent.astream({"messages": input_messages}):
    if "messages" in event:
        ai_messages.append(event["messages"])
        # 实时处理消息（日志、UI 更新等）
```

### 3. 状态继承模式

**模式描述**: 子 Agent 继承父 Agent 的状态（模型、沙箱、工作区）。

**优点**:
- ✅ 简化子 Agent 配置
- ✅ 一致的执行环境
- ✅ 支持嵌套任务

**实现**:
```python
# Lead Agent 中
subagent_context = ExecutionContext(
    model=parent_agent.model,           # 继承模型
    sandbox=parent_agent.sandbox,       # 继承沙箱
    thread_data=parent_agent.thread_data,  # 继承工作区
    trace_id=generate_trace_id()        # 新的追踪 ID
)

executor = SubagentExecutor(..., context=subagent_context)
```

### 4. 批处理协调模式

**模式描述**: 当子任务过多时，将其分批执行，避免超出并发限制。

**优点**:
- ✅ 避免任务丢失
- ✅ 可预测的资源使用
- ✅ 更好的错误处理

**实现**:
```python
# Lead Agent 中
tasks = [task1, task2, task3, task4, task5, task6]  # 6 个任务，限制 3 个

# Batch 1
batch1_results = await asyncio.gather(
    task_tool(tasks[0], ...),
    task_tool(tasks[1], ...),
    task_tool(tasks[2], ...)
)

# Batch 2
batch2_results = await asyncio.gather(
    task_tool(tasks[3], ...),
    task_tool(tasks[4], ...),
    task_tool(tasks[5], ...)
)

# 综合结果
final_result = synthesize([...batch1_results, ...batch2_results])
```

### 5. 可配置性模式

**模式描述**: 通过配置文件和运行时参数实现高度可配置。

**优点**:
- ✅ 无需重新编译
- ✅ 支持多种场景
- ✅ 便于实验

**实现**:
```yaml
# agents/my_agent/config.yaml
name: my-agent
description: "自定义分析 Agent"
model: gpt-4-turbo              # 特定模型
tool_groups:
  - research
  - code_analysis

# SOUL.md - 个性化指令
您是一个专业的代码审查专家...
```

### 6. 性能优化模式

**模式描述**: 在不同层级应用缓存和异步处理。

**优点**:
- ✅ 减少延迟
- ✅ 降低资源消耗
- ✅ 提高吞吐量

**实现**:
```python
# MCP 工具缓存
mcp_tools_cache = {}

def get_available_tools():
    if "mcp_tools" not in mcp_tools_cache:
        # 首次发现 MCP 工具
        mcp_tools_cache["mcp_tools"] = discover_mcp_tools()
    
    return mcp_tools_cache["mcp_tools"]

# 异步记忆更新
async def process_memory_queue():
    # 后台异步处理，不阻塞主流程
    while True:
        await memory_updater.process()
```

---

## 安全机制

### 1. 工具隔离

**机制**: 子 Agent 无法调用 `task_tool`，防止无限嵌套。

```python
# SubagentExecutor 中
available_tools = parent_tools.copy()
available_tools.remove("task_tool")  # 防止嵌套

agent = make_lead_agent(config, tools=available_tools)
```

**优点**:
- ✅ 防止递归循环
- ✅ 控制资源消耗
- ✅ 简化错误处理

### 2. 超时控制

**机制**: 多层次超时保护。

```python
# 第 1 层：子 Agent 配置
subagent_config.timeout_seconds = 900  # 15 分钟

# 第 2 层：线程池执行
future = executor.submit(run_subagent, timeout=900)

# 第 3 层：轮询超时
while True:
    if time.time() - start_time > 900:
        raise TimeoutError("子 Agent 超时")
```

### 3. 错误恢复

**机制**: 工具异常不会导致 Agent 崩溃，而是转换为 ToolMessage。

```python
try:
    result = await tool_execution()
except Exception as e:
    # 不抛出异常，而是返回错误消息
    return ToolMessage(
        name="tool_name",
        content=f"工具执行失败：{str(e)}",
        is_error=True
    )
```

### 4. 无限循环检测

**机制**: LoopDetectionMiddleware 跟踪工具调用模式。

```python
class LoopDetectionMiddleware:
    def __init__(self, max_identical_calls: int = 3):
        self.max_identical_calls = max_identical_calls
        self.call_history = []
    
    def detect_loop(self, tool_calls: list) -> bool:
        # 如果最后 3 次调用相同，可能是无限循环
        if len(self.call_history) >= self.max_identical_calls:
            recent = self.call_history[-self.max_identical_calls:]
            if all(call == recent[0] for call in recent):
                return True
        
        return False
```

### 5. 并发限制

**机制**: SubagentLimitMiddleware 强制执行硬限制。

```python
max_concurrent_subagents = 3  # 硬限制

# 虽然这会导致任务丢失（不理想），
# 但防止了资源耗尽
```

**⚠️ 建议**: 使用批处理模式而非依赖硬限制。

### 6. 权限隔离

**机制**: 沙箱环境隔离文件系统和网络。

```
┌─────────────────────────────────┐
│    Sandbox Container            │
│  ┌──────────────────────────┐   │
│  │ /mnt/user-data/          │   │
│  │ ├── uploads/             │   │
│  │ ├── workspace/           │   │
│  │ └── outputs/             │   │
│  │                          │   │
│  │ (受限的网络访问)         │   │
│  │ (受限的文件权限)         │   │
│  └──────────────────────────┘   │
└─────────────────────────────────┘
```

---

## 总结与启示

### Agent 设计核心原则

| 原则 | 实现 |
|------|------|
| **分离关注** | 中间件链模式、工具隔离 |
| **可扩展性** | 插件式工具系统、自定义 Agent 配置 |
| **可靠性** | 超时控制、错误恢复、无限循环检测 |
| **性能** | 流式处理、异步记忆更新、缓存 |
| **用户体验** | 澄清拦截、实时反馈、任务追踪 |
| **灵活性** | 动态系统提示词、模型继承、批处理 |

### 关键文件速查

| 功能 | 文件路径 |
|------|---------|
| Lead Agent 核心 | `/agents/lead_agent/agent.py` |
| 系统提示词构建 | `/agents/lead_agent/prompt.py` |
| 子 Agent 执行 | `/subagents/executor.py` |
| 任务工具接口 | `/tools/builtins/task_tool.py` |
| 14 阶段中间件 | `/agents/middlewares/` |
| 记忆存储与更新 | `/agents/memory/` |
| 状态架构 | `/agents/thread_state.py` |
| 工具解析 | `/tools/tools.py` |

### 扩展建议

1. **监控与可观测性** - 添加详细的日志和指标
2. **更好的批处理** - 在系统提示词中自动生成批处理计划
3. **动态优先级** - 基于任务重要性调整调度顺序
4. **分布式执行** - 支持跨多台机器的子 Agent 执行
5. **高级内存** - 向量数据库支持语义相似度查询

---

**文档完成日期**: 2025-02-28  
**版本**: 1.0  
**维护**: DeerFlow 研究团队
