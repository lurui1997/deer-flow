# DeerFlow Memory 机制设计与实现调研报告

> **项目**: DeerFlow (Deep Exploration and Efficient Research Flow)
> **调研范围**: `backend/packages/harness/deerflow/agents/memory/` 及相关模块
> **文档版本**: v1.0

---

## 目录

1. [概述](#1-概述)
2. [整体架构](#2-整体架构)
3. [数据模型设计](#3-数据模型设计)
4. [核心模块详解](#4-核心模块详解)
   - 4.1 [Storage — 存储层](#41-storage--存储层)
   - 4.2 [Updater — 更新层](#42-updater--更新层)
   - 4.3 [Queue — 队列层](#43-queue--队列层)
   - 4.4 [Prompt — 提示词层](#44-prompt--提示词层)
5. [集成机制](#5-集成机制)
   - 5.1 [MemoryMiddleware — 中间件](#51-memorymiddleware--中间件)
   - 5.2 [Prompt Injection — 注入到系统提示词](#52-prompt-injection--注入到系统提示词)
6. [配置系统](#6-配置系统)
7. [API 接口](#7-api-接口)
8. [关键设计决策](#8-关键设计决策)
9. [文件索引](#9-文件索引)

---

## 1. 概述

DeerFlow 的 Memory 模块为 AI Agent 提供了**跨会话的长期用户记忆能力**。其核心思路是：

- 每次对话结束后，利用 LLM 将对话内容提炼为结构化记忆（用户上下文 + 历史 + 事实）
- 记忆持久化存储在本地 JSON 文件中
- 下次对话时，将记忆注入到系统提示词，使 Agent 能理解用户背景、偏好和当前关注点

这种设计让 Agent 在多轮、多会话交互中表现出类似"了解用户"的个性化能力，而不是每次都"失忆重启"。

---

## 2. 整体架构

```
用户对话
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                     Agent 执行                           │
│  ┌─────────────────────────────────────────────────┐    │
│  │  系统提示词 (含注入的 Memory 内容)               │    │
│  │  "User Context: Work: ... Facts: ..."           │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
    │
    ▼ after_agent 钩子
┌─────────────────────────────────────────────────────────┐
│              MemoryMiddleware                            │
│  1. 过滤消息（只保留 Human + 最终 AI 回复）              │
│  2. 丢弃 uploaded_files 等会话级内容                     │
│  3. 加入 MemoryUpdateQueue                              │
└─────────────────────────────────────────────────────────┘
    │
    ▼ 防抖 30s
┌─────────────────────────────────────────────────────────┐
│              MemoryUpdateQueue                           │
│  同一 thread 多次触发只保留最新一条                       │
│  防抖后批量调用 MemoryUpdater                            │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│              MemoryUpdater                               │
│  1. 加载当前记忆 (FileMemoryStorage)                     │
│  2. 构造 MEMORY_UPDATE_PROMPT                            │
│  3. 调用 LLM 生成更新 JSON                               │
│  4. 合并新事实、更新摘要、清除过期事实                    │
│  5. 过滤上传文件相关内容                                  │
│  6. 保存到 memory.json                                   │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│              FileMemoryStorage                           │
│  原子写入（先写 .tmp，再 rename）                         │
│  mtime 缓存，避免重复 I/O                                │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 数据模型设计

Memory 数据以 JSON 格式存储，结构如下（`storage.py:18-34`）：

```json
{
  "version": "1.0",
  "lastUpdated": "2025-01-15T10:30:00Z",
  "user": {
    "workContext": {
      "summary": "当前工作职位、核心项目、技术栈（2-3句）",
      "updatedAt": "2025-01-15T10:30:00Z"
    },
    "personalContext": {
      "summary": "语言能力、沟通偏好、兴趣爱好（1-2句）",
      "updatedAt": ""
    },
    "topOfMind": {
      "summary": "当前多个并行关注点（3-5句详细段落）",
      "updatedAt": ""
    }
  },
  "history": {
    "recentMonths": {
      "summary": "近1-3个月活动详述（4-6句或1-2段）",
      "updatedAt": ""
    },
    "earlierContext": {
      "summary": "3-12个月前的历史模式（3-5句）",
      "updatedAt": ""
    },
    "longTermBackground": {
      "summary": "长期不变的背景信息（2-4句）",
      "updatedAt": ""
    }
  },
  "facts": [
    {
      "id": "fact_a1b2c3d4",
      "content": "用户主要使用 Python 和 TypeScript",
      "category": "knowledge",
      "confidence": 0.9,
      "createdAt": "2025-01-15T10:30:00Z",
      "source": "thread_xyz"
    }
  ]
}
```

### 数据层次说明

| 层次 | 字段 | 内容 | 更新频率 |
|------|------|------|----------|
| 用户上下文 | `user.workContext` | 职业、项目、技术栈 | 低 |
| 用户上下文 | `user.personalContext` | 个性、语言、偏好 | 低 |
| 用户上下文 | `user.topOfMind` | 当前多个并行关注点 | **高** |
| 历史 | `history.recentMonths` | 近期活动详述 | 中 |
| 历史 | `history.earlierContext` | 稍早的历史模式 | 低 |
| 历史 | `history.longTermBackground` | 长期背景 | 极低 |
| 事实 | `facts[]` | 具体可量化的事实 | 中（增量） |

### Fact 分类体系

| category | 含义 | 示例 |
|----------|------|------|
| `preference` | 偏好/厌恶 | "偏好 TypeScript 而非 JavaScript" |
| `knowledge` | 专业知识/技能 | "熟练掌握 LangGraph" |
| `context` | 背景事实 | "任职于某公司，担任高级工程师" |
| `behavior` | 行为模式 | "习惯在深夜工作" |
| `goal` | 目标/意图 | "希望将项目开源并获得 1k star" |

---

## 4. 核心模块详解

### 4.1 Storage — 存储层

**文件**: `backend/packages/harness/deerflow/agents/memory/storage.py`

#### 抽象基类 `MemoryStorage`

定义了三个接口方法（`storage.py:37-53`）：

| 方法 | 说明 |
|------|------|
| `load(agent_name)` | 加载记忆（带缓存） |
| `reload(agent_name)` | 强制从文件重新加载 |
| `save(memory_data, agent_name)` | 保存记忆 |

设计上支持**全局记忆**（`agent_name=None`）和**per-agent 记忆**（指定 `agent_name`），为未来多智能体场景预留扩展。

#### `FileMemoryStorage` 实现

核心特性（`storage.py:56-160`）：

**1. mtime 缓存机制**

```python
# storage.py:105-121
def load(self, agent_name=None):
    current_mtime = file_path.stat().st_mtime if file_path.exists() else None
    cached = self._memory_cache.get(agent_name)
    if cached is None or cached[1] != current_mtime:
        memory_data = self._load_memory_from_file(agent_name)
        self._memory_cache[agent_name] = (memory_data, current_mtime)
    return cached[0]
```

通过比较文件修改时间（mtime）判断缓存是否有效，避免每次访问都读磁盘。

**2. 原子写入**

```python
# storage.py:144-148
temp_path = file_path.with_suffix(".tmp")
with open(temp_path, "w", encoding="utf-8") as f:
    json.dump(memory_data, f, indent=2, ensure_ascii=False)
temp_path.replace(file_path)  # 原子替换
```

先写入 `.tmp` 临时文件，再 rename，防止写入过程中崩溃导致文件损坏。

**3. 可插拔存储后端**

通过配置 `storage_class` 字段（默认为 `FileMemoryStorage`），支持动态加载自定义存储实现（`storage.py:177-203`）。

**4. 路径安全校验**

对 `agent_name` 使用 `AGENT_NAME_PATTERN` 正则校验（`storage.py:65-76`），防止路径穿越攻击。

---

### 4.2 Updater — 更新层

**文件**: `backend/packages/harness/deerflow/agents/memory/updater.py`

`MemoryUpdater` 是核心 LLM 调用组件，负责将对话提炼为结构化记忆（`updater.py:112-193`）。

#### 更新流程

```
1. get_memory_data()          ← 读取当前记忆
2. format_conversation_for_update(messages)  ← 格式化对话
3. MEMORY_UPDATE_PROMPT.format(...)          ← 构建提示词
4. model.invoke(prompt)                      ← LLM 推理
5. json.loads(response_text)                 ← 解析 JSON
6. _apply_updates(current_memory, update_data)  ← 合并更新
7. _strip_upload_mentions_from_memory(...)   ← 清理上传文件引用
8. storage.save(updated_memory)              ← 持久化
```

#### `_apply_updates` 核心逻辑（`updater.py:195-271`）

- **更新摘要**: 仅当 LLM 返回 `shouldUpdate=true` 且有内容时才更新对应字段
- **去重事实**: 基于内容字符串的精确匹配避免重复存储同一事实
- **置信度过滤**: 低于阈值（默认 0.7）的事实不写入
- **容量控制**: 超过 `max_facts`（默认 100）时，按置信度降序保留最高的

#### 文件上传过滤

这是一个细节但关键的设计（`updater.py:66-100`）：

上传的文件存在于 `/mnt/user-data/uploads/` 等临时路径，仅在当前会话有效。如果将"用户上传了 xxx.pdf"记入长期记忆，下次对话中 Agent 会试图访问不存在的文件。因此：

```python
_UPLOAD_SENTENCE_RE = re.compile(
    r"[^.!?]*\b(?:upload(?:ed|ing)?.*?(?:file|document)|/mnt/user-data/uploads/|<uploaded_files>)[^.!?]*[.!?]?\s*",
    re.IGNORECASE,
)
```

使用正则从所有摘要和事实中清除上传相关句子。

---

### 4.3 Queue — 队列层

**文件**: `backend/packages/harness/deerflow/agents/memory/queue.py`

`MemoryUpdateQueue` 实现了**防抖（debounce）+ 批处理**的异步更新队列（`queue.py:22-165`）。

#### 防抖机制

```python
# queue.py:37-63
def add(self, thread_id, messages, agent_name=None):
    # 同一 thread 的新对话替换旧的（去重）
    self._queue = [c for c in self._queue if c.thread_id != thread_id]
    self._queue.append(context)
    # 每次 add 都重置计时器
    self._reset_timer()

def _reset_timer(self):
    if self._timer is not None:
        self._timer.cancel()
    self._timer = threading.Timer(config.debounce_seconds, self._process_queue)
    self._timer.daemon = True
    self._timer.start()
```

**效果**: 在 30 秒内无论产生多少次对话，只触发一次 LLM 更新，大幅降低 API 调用成本。

#### 并发安全

- 使用 `threading.Lock` 保护队列状态
- `_processing` 标志防止重入
- 多线程环境下安全（`queue.py:30-35, 88-130`）

#### 批处理间隔

多条记忆同时处理时，每条之间 sleep 0.5s，避免触发 LLM API 频率限制（`queue.py:124-125`）。

---

### 4.4 Prompt — 提示词层

**文件**: `backend/packages/harness/deerflow/agents/memory/prompt.py`

包含两个方向的提示词：

#### MEMORY_UPDATE_PROMPT（对话 → 记忆）

指令 LLM 分析对话，输出结构化 JSON：

```json
{
  "user": {
    "workContext": { "summary": "...", "shouldUpdate": true },
    ...
  },
  "history": { ... },
  "newFacts": [
    { "content": "...", "category": "preference", "confidence": 0.9 }
  ],
  "factsToRemove": ["fact_id_1"]
}
```

提示词包含详细的字段长度指引、更新时机判断、多语言处理等要求（`prompt.py:15-117`）。

#### format_memory_for_injection（记忆 → 系统提示词）

将记忆格式化为紧凑的文本片段（`prompt.py:186-294`）：

```
User Context:
- Work: 核心贡献者，负责 DeerFlow 项目...
- Personal: 双语（中英文）...
- Current Focus: 正在实现 Memory 模块，同时关注...

History:
- Recent: 近期探索了 LangGraph、LangChain...

Facts:
- [knowledge | 0.95] 熟练掌握 Python 和 TypeScript
- [preference | 0.90] 偏好简洁的代码风格
```

**Token 预算管理**（`prompt.py:246-275`）：

使用 `tiktoken` 精确计算 token 数量（非简单字符估算），Facts 按置信度排序后依次填入，直到达到 `max_injection_tokens`（默认 2000）为止，保证最高价值的信息优先注入。

---

## 5. 集成机制

### 5.1 MemoryMiddleware — 中间件

**文件**: `backend/packages/harness/deerflow/agents/middlewares/memory_middleware.py`

```python
class MemoryMiddleware(AgentMiddleware[MemoryMiddlewareState]):
    def after_agent(self, state, runtime):
        # 1. 从 runtime.context 获取 thread_id
        # 2. 过滤消息：只保留 human + 最终 AI 回复（去掉 tool calls）
        # 3. 检查是否有有效的用户-助手对话
        # 4. 加入 MemoryUpdateQueue
```

`after_agent` 是 LangGraph 的 Agent 执行后钩子，确保**每次对话结束后自动触发记忆更新**，对业务逻辑完全透明。

消息过滤逻辑（`memory_middleware.py:20-83`）：

| 消息类型 | 处理方式 |
|----------|----------|
| Human 消息（含 `<uploaded_files>`） | 清除上传块后保留（若全为上传内容则丢弃） |
| Human 消息（普通） | 保留 |
| AI 消息（含 `tool_calls`） | 丢弃（中间步骤） |
| AI 消息（最终回复） | 保留 |
| Tool 消息 | 丢弃 |

### 5.2 Prompt Injection — 注入到系统提示词

在 Agent 初始化时，调用 `format_memory_for_injection()` 将当前记忆内容注入系统提示词头部，使 Agent 在生成回复时自然地利用用户背景知识。

相关集成点：`backend/packages/harness/deerflow/agents/lead_agent/agent.py:10`（Lead Agent 导入 memory 模块）

---

## 6. 配置系统

**文件**: `backend/packages/harness/deerflow/config/memory_config.py`

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `True` | 是否启用记忆机制 |
| `storage_path` | `""` | 存储路径（空=使用默认路径） |
| `storage_class` | `FileMemoryStorage` | 存储后端类路径（可替换） |
| `debounce_seconds` | `30` | 防抖等待秒数（1-300） |
| `model_name` | `None` | 更新用的 LLM（None=使用默认模型） |
| `max_facts` | `100` | 最大事实条数（10-500） |
| `fact_confidence_threshold` | `0.7` | 事实置信度阈值（0.0-1.0） |
| `injection_enabled` | `True` | 是否将记忆注入系统提示词 |
| `max_injection_tokens` | `2000` | 注入时最大 token 数（100-8000） |

使用 Pydantic `BaseModel` 进行校验，通过 `get_memory_config()` / `set_memory_config()` 全局单例访问（`memory_config.py:64-83`）。

---

## 7. API 接口

**文件**: `backend/app/gateway/routers/memory.py`

提供 4 个 REST 端点供前端/外部系统访问记忆：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/memory` | 获取当前全局记忆数据 |
| `POST` | `/api/memory/reload` | 强制从文件重新加载记忆 |
| `GET` | `/api/memory/config` | 获取记忆系统配置 |
| `GET` | `/api/memory/status` | 获取配置 + 数据合并视图 |

所有接口均使用 Pydantic 模型进行请求/响应校验，保证数据类型安全。

---

## 8. 关键设计决策

### 8.1 为什么用 LLM 而不是规则提取记忆？

LLM 能理解上下文语义，从自由格式对话中提炼结构化信息，同时判断信息的时效性（哪些应更新 topOfMind，哪些进 longTermBackground），这是规则系统难以处理的。

### 8.2 为什么使用防抖队列而非即时更新？

LLM 调用有延迟和成本，且单次对话可能在短时间内产生多轮。防抖确保在用户停止对话后才触发一次更新，避免为每条消息都调用 LLM，显著降低延迟感知和 API 费用。

### 8.3 为什么过滤文件上传引用？

上传文件路径是会话级临时资产（如 `/mnt/user-data/uploads/xxx.pdf`），写入长期记忆后，后续会话中 Agent 会尝试访问不存在的路径，造成错误。通过正则过滤从根本上消除此类幽灵引用。

### 8.4 token 预算与信息优先级

注入系统提示词时，Facts 按置信度降序排列，确保最确定的事实优先占用 token 预算。这在 token 受限的场景下保证了信息质量，而非简单截断。

### 8.5 原子写入保证数据完整性

使用 `.tmp` + `rename` 的原子写入方式，即使进程中途崩溃，也不会产生半写入的损坏文件，记忆数据始终处于有效状态。

---

## 9. 文件索引

| 文件 | 职责 |
|------|------|
| `agents/memory/__init__.py` | 模块入口，统一导出所有公共 API |
| `agents/memory/storage.py` | 抽象存储接口 + FileMemoryStorage 实现 |
| `agents/memory/updater.py` | LLM 驱动的记忆更新逻辑 |
| `agents/memory/queue.py` | 防抖异步更新队列 |
| `agents/memory/prompt.py` | 更新提示词模板 + 注入格式化工具 |
| `agents/middlewares/memory_middleware.py` | Agent 执行后自动触发的中间件 |
| `config/memory_config.py` | 记忆系统配置（Pydantic 模型） |
| `app/gateway/routers/memory.py` | REST API 端点 |

---

*本文档基于源码阅读生成，描述截至当前代码状态。*
