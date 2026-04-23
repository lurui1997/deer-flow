# Agent 任务完成判定机制

> 状态：已评审 | 更新日期：2026-04-21

## 1. 核心原则

DeerFlow Agent **没有显式的"任务完成检测器"**——它完全依赖 LLM 的行为信号（是否产出 `tool_calls`）作为主判据，中间件链做的是**防止误判**（提前退出）和**兜底保护**（死循环/超限）。

## 2. 判定层级

### 2.1 第一层：LLM 自主决策（LangGraph 标准 ReAct 循环）

```
LLM 返回 AIMessage → 有 tool_calls？
  ├─ 有 → 继续执行工具 → 工具结果回流 → 再次调用 LLM（循环继续）
  └─ 没有 → 视为 agent 已产出最终回答 → 循环结束（goto END）
```

`create_agent` 构建的 LangGraph 图内部使用标准的 `should_continue` 条件路由：
- **最后一条 `AIMessage` 没有 `tool_calls`** → 路由到 `__end__`，任务完成
- **最后一条 `AIMessage` 包含 `tool_calls`** → 路由到 `tools` 节点执行工具

**本质：LLM 自己决定"我不需要再调用工具了"来标志任务完成。**

### 2.2 第二层：中间件增强防护

在中间件链中叠加了多个修正和增强逻辑：

#### 2.2.1 TodoMiddleware — 防止过早退出

当 Plan 模式启用时，即使 LLM 认为"不需要调用工具了"（没有 `tool_calls`），如果 **todo list 中还有未完成项**，中间件会：

1. 注入一条提醒消息：*"You have incomplete todo items that must be finished"*
2. 通过 `jump_to: "model"` 强制让 LLM 继续工作
3. 最多重试 **2 次**（`_MAX_COMPLETION_REMINDERS = 2`），防止无限循环

```python
todos: list[Todo] = state.get("todos") or []
if not todos or all(t.get("status") == "completed" for t in todos):
    return None
```

#### 2.2.2 ClarificationMiddleware — 主动中断等待人工

当 LLM 调用 `ask_clarification` 工具时，通过 `Command(goto=END)` **主动中断**执行。这不算"完成"，而是"挂起"——后续通过 `Command(resume=...)` 恢复。

```python
return Command(
    update={"messages": [tool_message]},
    goto=END,
)
```

#### 2.2.3 LoopDetectionMiddleware — 强制终止死循环

两层检测策略：

| 检测层 | 触发条件 | 行为 |
|--------|---------|------|
| Hash 匹配 | 同一组 tool_calls 重复 ≥3 次 | 注入警告消息 |
| Hash 匹配 | 同一组 tool_calls 重复 ≥5 次 | **强制清空 tool_calls**，迫使 LLM 输出最终答案 |
| 频率检测 | 同一工具类型调用 ≥30 次 | 注入警告消息 |
| 频率检测 | 同一工具类型调用 ≥50 次 | **强制终止** |

强制终止的方式：直接把 AIMessage 的 `tool_calls` 清空，使下一轮 `should_continue` 判断走到 `__end__`。

```python
last_msg = messages[-1]
content = self._append_text(last_msg.content, warning or _HARD_STOP_MSG)
stripped_msg = last_msg.model_copy(update=self._build_hard_stop_update(last_msg, content))
return {"messages": [stripped_msg]}
```

#### 2.2.4 外部中止 — abort_event

外部（用户/平台）可以设置 `abort_event` 来中止任务：

```python
if record.abort_event.is_set():
    logger.info("Run %s abort requested — stopping", run_id)
    break
```

支持两种策略：
- **rollback**：回滚到执行前的检查点
- **interrupt**：标记为中断状态

## 3. 判定流程图

```
                    ┌─────────────────┐
                    │ LLM 生成 AIMessage │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
              ┌─────┤  有 tool_calls？  ├─────┐
              │否   └─────────────────┘   是│
              │                               │
    ┌─────────▼─────────┐         ┌──────────▼──────────┐
    │ TodoMiddleware：   │         │ LoopDetection：     │
    │ 有未完成 todo？     │         │ 检测到死循环？       │
    └─────────┬─────────┘         └──────────┬──────────┘
         有 │ 无                    是│ 仅警告│ 否
    ┌──────┴──────┐           ┌───────┼───────┐
    │ 提醒<2次？   │           │       │       │
    │ 注入+跳转    │     ┌────┴──┐ ┌──┴───┐ ┌─┴──┐
    │ (最多2次)    │     │ Hard  │ │ 注入  │ │ ask│
    └──────┬──────┘     │ limit │ │ 警告  │ │ clar│
           │            └────┬──┘ └──┬───┘ └─┬──┘
           ▼                 │       │       │
      ┌────────┐             ▼       ▼       ▼
      │  继续   │      清空tool  执行工具   中断
      │ 执行LLM │      _calls    +回流      挂起
      └────┬───┘                  │
           │                     ┌┴┐
           │                     ▼ │
           └───────────────────────┘
                    │
                    ▼
            ┌──────────────┐
            │ ✅ 任务完成   │
            │   → END       │
            └──────────────┘
```

## 4. 完成方式总结

| 完成方式 | 触发者 | 状态 |
|---------|--------|------|
| LLM 不再调用工具 | LLM 自主决定 | `success` |
| Todo 全部完成后 LLM 停止 | LLM + TodoMiddleware 协作 | `success` |
| 循环检测强制终止 | LoopDetectionMiddleware | `success`（被迫的） |
| 澄清中断 | ClarificationMiddleware | `interrupted`（等待恢复） |
| 外部中止 | 用户/平台 | `interrupted` 或 `error`(rollback) |
| 异常崩溃 | 运行时异常 | `error` |

## 5. 关键文件

- `backend/packages/harness/deerflow/agents/middlewares/todo_middleware.py`
- `backend/packages/harness/deerflow/agents/middlewares/clarification_middleware.py`
- `backend/packages/harness/deerflow/agents/middlewares/loop_detection_middleware.py`
- `backend/packages/harness/deerflow/runtime/runs/worker.py`
