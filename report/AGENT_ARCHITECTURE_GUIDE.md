# DeerFlow Agent 架构 — 完整指南

## 快速导航

- [概述](#概述)
- [1. 核心 Agent 总览](#1-核心-agent-总览)
- [2. 线程状态管理](#2-线程状态管理)
- [3. 中间件链](#3-中间件链执行管道)
- [4. 工具系统](#4-工具系统架构)
- [5. 多 Agent 编排](#5-多-agent-编排模式)
- [6. 关键文件索引](#6-关键文件及其位置)

---

## 概述

DeerFlow 是基于 **LangGraph** 构建的生产级多 Agent AI 系统，具备成熟的编排、中间件链、记忆管理和工具集成能力。

**核心组件**：
- **Lead Agent**：面向用户交互的主编排器
- **子代理（Subagents）**：并行任务执行（2-4 个并发，通用型/Bash 型）
- **ACP Agent**：外部集成（Codex、Claude Code）
- **中间件链**：13 层有序中间件，负责安全和上下文管理
- **工具系统**：3 个来源（内建、配置、MCP）
- **记忆系统**：持久化对话上下文，支持 per-agent 隔离
- **沙箱执行**：基于 Docker 的代码执行，具备路径安全防护

---

## 1. 核心 Agent 总览

### Lead Agent（主编排器）

**入口文件**：`backend/packages/harness/deerflow/agents/lead_agent/agent.py:make_lead_agent`

**职责**：
- 通过中间件链处理用户消息
- 协调工具执行
- 将复杂任务委派给子代理
- 管理线程状态（消息、产物、记忆）
- 注入记忆和技能上下文
- 处理用户澄清请求

**运行时配置**（来自 RunnableConfig）：
```python
thinking_enabled: bool               # 扩展推理模式（如模型支持）
reasoning_effort: str | None         # GPT-5 类模型的推理力度
model_name: str | None               # 覆盖默认模型
is_plan_mode: bool                   # 启用任务列表追踪
subagent_enabled: bool               # 启用并行任务委派
max_concurrent_subagents: int        # 限制并发任务调用数（2-4）
is_bootstrap: bool                   # 特殊模式，用于 Agent 创建
agent_name: str | None               # 自定义 Agent 人格覆盖
```

**模型解析优先级**：
1. 运行时参数中显式指定的模型
2. Agent 级别的模型覆盖（来自 agent 配置）
3. 全局默认模型（config.yaml 中的第一个）

### 子代理（并行任务执行器）

**两种内置类型**：

**通用子代理（General-Purpose）**
- 位置：`backend/packages/harness/deerflow/subagents/builtins/general_purpose.py`
- 用途：复杂多步骤研究、分析、探索
- 最大轮次：50
- 限制：禁止嵌套任务调用（防止无限递归）

**Bash 子代理**
- 位置：`backend/packages/harness/deerflow/subagents/builtins/bash_agent.py`
- 用途：命令执行（git、构建、部署）
- 最大轮次：20
- 输出：详细的命令执行结果

**执行模型**：
- 通过 ThreadPoolExecutor 后台执行
- 基于轮询的结果获取（5 秒间隔）
- 流式发送 task_started/task_running 事件
- 硬性并发限制：每个响应最多 3 个并行 task 调用（由 SubagentLimitMiddleware 强制执行）
- 支持多批次执行：超过 3 个子任务时分批跨轮次执行

### ACP Agent（外部集成）

**工具文件**：`backend/packages/harness/deerflow/tools/builtins/invoke_acp_agent_tool.py`

**支持**：Codex、Claude Code，以及任何 ACP 兼容的 Agent

**执行方式**：
- 按线程隔离工作空间：`/acp-workspace/{thread_id}/`
- 自动批准沙箱权限
- MCP 服务器透传
- 结果可通过 `/mnt/acp-workspace/` 访问（只读）

---

## 2. 线程状态管理

### ThreadState Schema

**文件**：`backend/packages/harness/deerflow/agents/thread_state.py`

继承 LangGraph 的 `AgentState`：

```python
class ThreadState(AgentState):
    # LangGraph 核心字段
    messages: list[BaseMessage]                          # 所有消息

    # DeerFlow 扩展字段
    sandbox: SandboxState | None                         # 沙箱信息
    thread_data: ThreadDataState | None                  # 路径映射
    title: str | None                                    # 自动生成的标题
    artifacts: list[str]                                 # 生成的文件
    todos: list | None                                   # 任务追踪
    uploaded_files: list[dict] | None                   # 用户上传的文件
    viewed_images: dict[str, ViewedImageData]            # 视觉数据
```

### 虚拟路径映射

所有工具执行使用虚拟路径，映射到按线程隔离的物理目录：

| 虚拟路径 | 物理路径 |
|---------|----------|
| `/mnt/user-data/workspace` | `.deer-flow/threads/{thread_id}/user-data/workspace/` |
| `/mnt/user-data/uploads` | `.deer-flow/threads/{thread_id}/user-data/uploads/` |
| `/mnt/user-data/outputs` | `.deer-flow/threads/{thread_id}/user-data/outputs/` |
| `/mnt/skills` | `deer-flow/skills/` |

---

## 3. 中间件链（执行管道）

### 中间件顺序与职责

**文件**：`backend/packages/harness/deerflow/agents/lead_agent/agent.py:_build_middlewares()`（第 208-265 行）

按以下顺序执行（从最早到最晚）：

```
1.  ThreadDataMiddleware               - 初始化线程工作空间路径
    └─ 必须排在最前面，确保 thread_id 可用

2.  UploadsMiddleware                  - 列出/注入已上传的文件
    └─ 依赖 ThreadDataMiddleware

3.  SandboxMiddleware                  - 获取沙箱环境
    └─ 为工具执行设置 sandbox_state

4.  [SummarizationMiddleware]          - 上下文压缩（可选）
    └─ 仅在 summarization.enabled=true 时启用

5.  [TodoMiddleware]                   - 任务追踪系统（可选）
    └─ 仅在 is_plan_mode=true 时启用

6.  TokenUsageMiddleware               - 追踪 LLM Token 用量（可选）
    └─ 仅在 token_usage.enabled=true 时启用

7.  TitleMiddleware                    - 生成对话标题
    └─ 在首次对话交互后运行

8.  MemoryMiddleware                   - 排队记忆更新
    └─ 在 TitleMiddleware 之后运行

9.  [ViewImageMiddleware]              - 视觉模型支持（可选）
    └─ 仅在 model.supports_vision=true 时启用

10. DeferredToolFilterMiddleware        - 隐藏延迟加载工具（可选）
    └─ 仅在 tool_search.enabled=true 时启用

11. [SubagentLimitMiddleware]           - 强制限制最大 task 调用数（可选）
    └─ 仅在 subagent_enabled=true 时启用

12. LoopDetectionMiddleware             - 检测并打破重复循环
    └─ 始终启用

13. ClarificationMiddleware             - 用户澄清请求处理
    └─ 始终排在最后，中断执行等待用户输入
```

### 关键中间件详解

**ThreadDataMiddleware**（必须排在首位）
- 初始化 `/mnt/user-data/{workspace,uploads,outputs}` 目录
- 如果缺少此中间件，所有基于路径的操作都会失败
- 在状态中设置 `sandbox_state` 和 `thread_data`

**ClarificationMiddleware**（必须排在末位）
- 拦截 `ask_clarification` 工具调用
- 返回 `Command(goto=END)` 中断执行
- 等待用户响应后再恢复执行
- 确保澄清发生在开始工作之前

**SubagentLimitMiddleware**（subagent_enabled=true 时启用）
- 统计模型最终消息中的 `task` 工具调用数量
- 静默截断超出限制的调用
- 记录警告日志："Truncated N excess task tool call(s)"

**MemoryMiddleware**
- 将对话排队等待异步更新
- 过滤掉工具消息和文件上传块
- 保留用户问题和最终 AI 响应

---

## 4. 工具系统架构

### 三大工具来源

**文件**：`backend/packages/harness/deerflow/tools/__init__.py:get_available_tools()`

```python
def get_available_tools(
    groups: list[str] | None = None,        # 工具分组过滤
    include_mcp: bool = True,               # 是否包含 MCP 工具
    model_name: str | None = None,          # 视觉能力检查
    subagent_enabled: bool = False,         # 是否包含 task 工具
) -> list[BaseTool]
```

**工具来源**（合并为单一列表）：

**1. 内建工具**（始终可用）
- `present_file` — 向用户展示生成的文件
- `ask_clarification` — 中断执行，向用户追问
- `view_image` — 视觉模型图片处理（如模型支持视觉）
- `task` — 委派给子代理（如 subagent_enabled=true）
- `setup_agent` — 创建自定义 Agent（仅引导模式）

**2. 配置工具**（来自 config.yaml）
- `web_search` — 搜索引擎集成
- `web_fetch` — HTTP GET，HTML 转 Markdown
- `bash` — Shell 命令执行
- `read_file` / `write_file` — 文件操作
- `str_replace` — 文件补丁
- `ls` — 目录列表

**3. MCP 工具**（来自 extensions_config.json）
- GitHub、Filesystem、PostgreSQL、Brave Search、Puppeteer 等
- 通过 `get_cached_mcp_tools()` 加载，带文件修改时间缓存失效
- 如启用 tool_search：注册到延迟注册表，可通过 `tool_search` 工具按需发现

**4. ACP Agent 工具**（如有配置）
- `invoke_acp_agent` — 调用外部 Agent（Codex、Claude Code）

### 工具加载流程

```
get_available_tools()
├─ 按分组加载配置工具（如提供了分组参数）
├─ 添加内建工具
├─ 如模型支持视觉，添加 view_image
├─ 加载 MCP 工具（缓存，带修改时间失效机制）
│  └─ 如启用 tool_search，注册到延迟注册表
├─ 如有配置，添加 ACP Agent 工具
└─ 返回合并后的工具列表
```

---

## 5. 多 Agent 编排模式

### 模式 1：Lead Agent 直接执行

**适用场景**：简单任务、单步操作、需要用户交互

```
Lead Agent（1 轮）
├─ 处理用户消息
├─ 直接调用工具（bash、read_file、web_search）
├─ 生成响应
└─ 返回给用户
```

### 模式 2：子代理委派（单批次）

**适用场景**：2-3 个可并行的独立子任务

```
Lead Agent（第 1 轮）
├─ 分解任务
├─ 并行调用 3 个 task()
│  ├─ task(description="研究...", subagent_type="general-purpose")
│  ├─ task(description="分析...", subagent_type="general-purpose")
│  └─ task(description="对比...", subagent_type="general-purpose")
├─ 等待所有结果
└─ 返回综合回答

Lead Agent（第 2 轮）
└─ 用户收到完整回答
```

### 模式 3：子代理委派（多批次）

**适用场景**：超过 3 个并行子任务（分批跨轮次执行）

```
Lead Agent（第 1 轮）
├─ 分解为 6 个子任务
├─ 启动前 3 个：task() x 3
└─ 等待第 1 批结果

Lead Agent（第 2 轮）
├─ 启动后 3 个：task() x 3
└─ 等待第 2 批结果

Lead Agent（第 3 轮）
├─ 收到所有结果
├─ 综合第 1 批 + 第 2 批结果
└─ 返回完整回答
```

**强制执行**：SubagentLimitMiddleware 会截断超过 3 个的 task 调用

### 模式 4：澄清中断

**适用场景**：用户意图模糊或信息缺失

```
Lead Agent（第 1 轮）
├─ 接收用户消息
├─ 思考："信息缺失？是 → 需要澄清"
├─ 调用：ask_clarification(question="...", type="missing_info")
└─ ClarificationMiddleware 拦截
   └─ 返回 Command(goto=END)

执行中断。用户看到澄清问题。

用户回复澄清内容

Lead Agent（第 2 轮）
├─ 消息历史中包含用户的澄清回复
├─ 现在拥有完整上下文
├─ 继续执行工作
└─ 返回结果
```

### 模式 5：ACP Agent 委派

**适用场景**：代码生成、IDE 任务、文件操作

```
Lead Agent
├─ 调用：invoke_acp_agent(agent="codex", prompt="...")
├─ ACP Agent 在隔离工作空间中运行：/acp-workspace/{thread_id}/
├─ 结果写入 /acp-workspace/{thread_id}/
└─ Lead Agent 可以：
   ├─ 读取结果：read_file(/mnt/acp-workspace/...)
   ├─ 复制到输出目录：bash("cp /mnt/acp-workspace/* /mnt/user-data/outputs/")
   └─ 展示给用户：present_file()
```

---

## 6. 关键文件及其位置

### Agent 核心文件

| 文件 | 用途 | 关键函数 |
|------|------|----------|
| `backend/packages/harness/deerflow/agents/lead_agent/agent.py` | 主 Agent 工厂 | `make_lead_agent()` |
| `backend/packages/harness/deerflow/agents/lead_agent/prompt.py` | 系统提示词构建 | `apply_prompt_template()` |
| `backend/packages/harness/deerflow/agents/thread_state.py` | 状态 Schema | `ThreadState` 类 |
| `backend/packages/harness/deerflow/agents/memory/` | 记忆系统 | `updater.py`、`storage.py`、`queue.py` |

### 中间件文件（位于 `backend/packages/harness/deerflow/agents/middlewares/`）

| 文件 | 中间件 | 用途 |
|------|--------|------|
| `tool_error_handling_middleware.py` | `ToolErrorHandlingMiddleware` | 将工具错误转为 ToolMessage |
| `thread_data_middleware.py` | `ThreadDataMiddleware` | 初始化线程路径 |
| `uploads_middleware.py` | `UploadsMiddleware` | 列出已上传文件 |
| `clarification_middleware.py` | `ClarificationMiddleware` | 拦截澄清请求 |
| `subagent_limit_middleware.py` | `SubagentLimitMiddleware` | 强制限制最大 task 调用数 |
| `view_image_middleware.py` | `ViewImageMiddleware` | 视觉模型支持 |
| `title_middleware.py` | `TitleMiddleware` | 生成标题 |
| `memory_middleware.py` | `MemoryMiddleware` | 排队记忆更新 |

### 工具文件

| 文件 | 用途 |
|------|------|
| `backend/packages/harness/deerflow/tools/__init__.py` | `get_available_tools()` |
| `backend/packages/harness/deerflow/tools/builtins/task_tool.py` | 子代理委派 |
| `backend/packages/harness/deerflow/tools/builtins/invoke_acp_agent_tool.py` | ACP Agent 调用 |
| `backend/packages/harness/deerflow/tools/builtins/clarification_tool.py` | `ask_clarification` 工具 |

### 子代理系统

| 文件 | 用途 |
|------|------|
| `backend/packages/harness/deerflow/subagents/executor.py` | `SubagentExecutor` 类 |
| `backend/packages/harness/deerflow/subagents/builtins/general_purpose.py` | 通用子代理配置 |
| `backend/packages/harness/deerflow/subagents/builtins/bash_agent.py` | Bash 子代理配置 |
| `backend/packages/harness/deerflow/config/subagents_config.py` | 配置加载 |

### 配置系统

| 文件 | 用途 |
|------|------|
| `/config.yaml` | 主配置（模型、工具、记忆等） |
| `/extensions_config.json` | MCP 服务器定义 |
| `backend/packages/harness/deerflow/config/agents_config.py` | Per-agent 配置加载 |
| `backend/packages/harness/deerflow/config/app_config.py` | 全局配置管理 |

### 入口文件

| 位置 | 用途 |
|------|------|
| `langgraph.json` | LangGraph 部署配置（定义 `make_lead_agent`） |
| `backend/app/gateway/app.py` | FastAPI REST 网关 |
| `backend/app/gateway/routers/agents.py` | 自定义 Agent CRUD API |

---

## 7. 消息流转示例

### 用户发送消息（subagent_enabled=true）：

```
1. 客户端 → POST /api/langgraph/threads/{thread_id}/runs
   {
     "input": {"messages": [{"role": "user", "content": "对比 5 家云服务商"}]},
     "config": {
       "configurable": {
         "model_name": "gpt-4",
         "subagent_enabled": true,
         "max_concurrent_subagents": 3,
         "is_plan_mode": false
       }
     }
   }

2. LangGraph Server → make_lead_agent(config)
   a. 构建中间件链（13 层）
   b. 执行 ThreadDataMiddleware → 创建路径
   c. 执行其余中间件 → 建立上下文

3. Lead Agent → 模型处理消息
   "我需要对比 5 家云服务商。
    由于每次最多并行 3 个任务，我先处理 AWS、Azure、GCP，
    然后下一批处理阿里云和 Oracle。
    现在启动第一批。"

4. 模型生成 3 个 task() 调用：
   - task(description="AWS 研究", ...)
   - task(description="Azure 研究", ...)
   - task(description="GCP 研究", ...)

5. SubagentLimitMiddleware 检查：3 个 task 调用 ≤ 3 限制 ✓

6. 每个 task() 在后台线程中启动 SubagentExecutor
   - 子代理 1：AWS 分析（通用子代理）
   - 子代理 2：Azure 分析（通用子代理）
   - 子代理 3：GCP 分析（通用子代理）

7. task_tool() 轮询每个子代理（5 秒间隔）
   - 流式发送 task_started 事件
   - 流式发送 task_running 事件（子代理的每条 AI 消息）
   - 收集最终结果

8. Lead Agent 在一个批次中收到全部 3 个结果

9. Lead Agent → 模型处理子代理结果
   "很好！AWS、Azure、GCP 已完成。现在启动后续 2 个..."

10. 模型生成 2 个 task() 调用：
    - task(description="阿里云研究", ...)
    - task(description="Oracle Cloud 研究", ...)

11. SubagentLimitMiddleware 检查：2 个 task 调用 ≤ 3 限制 ✓

12. 两个子代理并行执行

13. Lead Agent 收到两个结果

14. Lead Agent → 模型处理所有结果
    "完美！现在我可以综合一份全面的对比报告了..."

15. 模型生成包含对比矩阵的最终响应

16. ClarificationMiddleware 检查：无 ask_clarification 调用 → 正常流程

17. 通过 SSE 流式返回响应给客户端
```

---

## 8. 系统提示词注入示例

**Lead Agent 的最终系统提示词包含**：

```markdown
<role>
你是 DeerFlow 2.0，一个开源超级智能体。
</role>

<subagent_system>
你正在以子代理能力启用模式运行。
你的角色是任务编排器：
1. 分解：将复杂任务拆分为并行子任务
2. 委派：同时启动多个子代理
3. 综合：收集并整合结果

硬性并发限制：每个响应最多 3 个 `task` 调用。
- 每个响应中最多包含 3 个 `task` 工具调用
- 超出的调用会被系统静默丢弃
</subagent_system>

<skill_system>
你可以使用以下技能提供的优化工作流：
<available_skills>
    <skill>
        <name>PDF 处理</name>
        <description>高效处理 PDF 文档</description>
        <location>/mnt/skills/pdf-processing/SKILL.md</location>
    </skill>
    ...
</available_skills>
</skill_system>

<memory>
来自长期记忆的当前事实：
- 用户偏好详细的技术分析
- 用户从事数据管道和云基础设施工作
</memory>

<working_directory>
用户上传目录：`/mnt/user-data/uploads`
用户工作空间：`/mnt/user-data/workspace`
输出文件目录：`/mnt/user-data/outputs`
</working_directory>

<critical_reminders>
- 澄清优先：开始工作之前务必先澄清不清楚的需求
- 技能优先：执行复杂任务前先加载相关技能
- 输出文件：最终交付物必须放在 `/mnt/user-data/outputs`
</critical_reminders>
```

---

## 9. 配置示例：启用所有功能

```yaml
# config.yaml

config_version: 3
log_level: info

# 模型配置
models:
  - name: gpt-4
    display_name: GPT-4
    use: langchain_openai:ChatOpenAI
    model: gpt-4
    api_key: $OPENAI_API_KEY
    supports_thinking: false
    supports_vision: true

# 工具配置 - 定义可用工具
tools:
  - name: web_search
    use: deerflow.tools:web_search_tool
    group: search
  - name: bash
    use: deerflow.tools:bash_tool
    group: execution

# Token 用量追踪
token_usage:
  enabled: true

# 记忆系统
memory:
  enabled: true
  injection_enabled: true

# 子代理配置
subagents:
  timeout_seconds: 900  # 默认 15 分钟

# 沙箱配置
sandbox:
  provider: aio  # 基于 Docker（生产环境）
  #provider: local  # 直接执行（仅开发环境）
```

```json
// extensions_config.json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "$GITHUB_TOKEN"
      }
    }
  }
}
```

```yaml
# agents/my-researcher/AGENT.yaml
model: gpt-4
tool_groups:
  - search
  - web
  - analysis
```

```markdown
# agents/my-researcher/SOUL.md
你是一个专注于市场分析的专业研究型 Agent。

**专长领域**：
- 市场趋势分析
- 竞争对手研究
- 行业报告

**需要澄清的场景**：
- 未指定地理范围
- 时间段模糊
- 未定义具体指标
```

---

## 总结：关键要点

| 维度 | 详情 |
|------|------|
| **架构** | 基于 LangGraph，中间件驱动的编排体系 |
| **主 Agent** | Lead Agent 处理消息，委派任务 |
| **并行执行** | 子代理支持 2-4 个并发任务（硬性限制） |
| **工具来源** | 内建（5 个）+ 配置（7 个）+ MCP（不限数量） |
| **状态管理** | ThreadState 继承 LangGraph 的 AgentState |
| **中间件** | 13 层有序中间件，可定制，注重安全 |
| **记忆** | 异步更新，per-agent 隔离，注入到提示词 |
| **沙箱** | Docker（生产环境）或本地（开发环境），按线程隔离路径 |
| **技能** | 渐进式加载模式，避免上下文膨胀 |
| **配置** | YAML（主配置）+ JSON（MCP）+ per-agent YAML |
| **澄清** | 中间件拦截，中断执行等待用户输入 |
| **请求流程** | 中间件 → 模型 → 工具 →（循环或完成） |

---

**文档生成日期**：2026 年 3 月 28 日  
**所属项目**：DeerFlow (deer-flow)  
**基于**：Agent 系统完整架构探索
