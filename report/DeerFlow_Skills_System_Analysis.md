# DeerFlow Skills 系统分析报告

> **生成时间**: 2026-03-28  
> **分析范围**: DeerFlow 项目 Skills 系统架构、Claude Skills 2.0 能力对标、多模型兼容性  
> **文档性质**: AI 辅助分析，供人工审核参考

---

## 目录

1. [Skills 系统概览](#1-skills-系统概览)
2. [内置技能清单](#2-内置技能清单)
3. [架构设计详解](#3-架构设计详解)
4. [Claude Skills 2.0 能力对标](#4-claude-skills-20-能力对标)
5. [多模型兼容性分析](#5-多模型兼容性分析)
6. [结论与建议](#6-结论与建议)

---

## 1. Skills 系统概览

DeerFlow 项目**完整支持 Skills 系统**，这是项目的核心特性之一。README 中明确写道：

> *"Skills are what make DeerFlow do almost anything."*

Skills 是结构化的能力模块，每个 Skill 由一个 Markdown 文件定义工作流、最佳实践和引用资源。DeerFlow 采用**渐进式加载（Progressive Loading）**模式 — 只在任务需要时加载，而非一次性全部加载，保持上下文窗口精简。

### 核心特性

- **双分类体系**: `skills/public/`（内置）和 `skills/custom/`（用户自定义）
- **渐进式加载**: Agent 按需通过 `read_file` 加载技能文件
- **安装机制**: 支持 `.skill` ZIP 压缩包安装 + `npx skills` CLI 生态
- **启用/禁用管理**: 通过 `extensions_config.json` 管理状态
- **前端管理 UI**: 设置页面可视化管理（分类筛选、开关启用、创建入口）
- **沙箱路径映射**: `/mnt/skills/` 虚拟路径映射到宿主机实际目录

---

## 2. 内置技能清单

项目内置 **18 个 Public Skills**：

| 技能名称 | 功能描述 |
|---------|---------|
| `deep-research` | 系统化多角度网络研究 |
| `frontend-design` | 高质量前端界面设计 |
| `chart-visualization` | 数据可视化图表生成（20+ 图表类型） |
| `ppt-generation` | PPT 演示文稿生成 |
| `image-generation` | AI 图像生成 |
| `video-generation` | 视频生成 |
| `podcast-generation` | 播客音频生成 |
| `data-analysis` | 数据分析 |
| `consulting-analysis` | 咨询分析 |
| `github-deep-research` | GitHub 仓库深度研究 |
| `claude-to-deerflow` | Claude Code 与 DeerFlow 集成 |
| `skill-creator` | 创建新技能的元技能（含 A/B 测试 + 自我迭代） |
| `find-skills` | 查找和安装技能 |
| `bootstrap` | AI 个性化引导（生成 SOUL.md） |
| `surprise-me` | 随机惊喜 |
| `vercel-deploy-claimable` | Vercel 部署 |
| `web-design-guidelines` | Web 设计规范审查 |
| `frontend-design` | 前端界面设计 |

---

## 3. 架构设计详解

### 3.1 技能定义格式

每个技能由以下结构组成：

```
skill-name/
├── SKILL.md              # 核心定义文件（YAML frontmatter + Markdown 工作流）
├── scripts/              # 可执行脚本（可选）
├── references/           # 参考资料（可选）
└── assets/               # 静态资源（可选）
```

YAML frontmatter 支持字段：`name`、`description`、`license`、`allowed-tools`、`metadata`、`compatibility`、`version`、`author`

### 3.2 后端实现

#### 核心模块: `backend/packages/harness/deerflow/skills/`

| 文件 | 功能 |
|------|------|
| `types.py` | `Skill` 数据类定义（name, description, license, skill_dir, category, enabled 等） |
| `parser.py` | 解析 SKILL.md 的 YAML frontmatter |
| `loader.py` | 扫描 `public/` 和 `custom/` 目录加载所有技能 |
| `installer.py` | 从 `.skill` 压缩包安全安装技能（含路径穿越、ZIP 炸弹防护） |
| `validation.py` | frontmatter 验证逻辑（名称格式、必填字段、长度限制） |

#### API 路由: `backend/app/gateway/routers/skills.py`

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/skills` | GET | 列出所有技能 |
| `/api/skills/{skill_name}` | GET | 获取技能详情 |
| `/api/skills/{skill_name}` | PUT | 启用/禁用技能 |
| `/api/skills/install` | POST | 从 `.skill` 压缩包安装新技能 |

#### Agent Prompt 注入: `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`

`get_skills_prompt_section()` 函数生成 `<skill_system>` 提示块，注入到 lead agent 的系统 prompt 中。只加载 `enabled_only=True` 的技能，指导 Agent 使用渐进式加载模式。

#### 配置系统

- `config.yaml` → `skills.path` 和 `skills.container_path`
- `extensions_config.json` → 技能启用状态映射（默认为空 = 全部启用）
- `SkillsConfig` 类管理路径解析
- `ExtensionsConfig.is_skill_enabled()` 方法判断技能是否启用

### 3.3 前端实现

| 文件 | 功能 |
|------|------|
| `frontend/src/core/skills/type.ts` | `Skill` 接口定义 |
| `frontend/src/core/skills/api.ts` | 3 个 API 调用函数（loadSkills, enableSkill, installSkill） |
| `frontend/src/core/skills/hooks.ts` | React 查询 hooks（useSkills, useEnableSkill） |
| `skill-settings-page.tsx` | 技能设置页面（public/custom 分类筛选、开关启用、创建入口） |
| `skills-section.tsx` | 落地页技能展示区 |
| `progressive-skills-animation.tsx` | 渐进式技能动画组件 |

### 3.4 整体架构图

```
                    ┌──────────────┐
                    │  SKILL.md    │  ← 技能定义文件（YAML frontmatter + Markdown 工作流）
                    │  + scripts/  │  ← 可执行脚本
                    │  + references│  ← 参考资料
                    └──────┬───────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    skills/public/    skills/custom/    .skill 压缩包
    (内置技能)        (用户自定义)     (通过 API 安装)
         │                 │                 │
         └────────┬────────┘                 │
                  │                          │
    ┌─────────────▼──────────────┐  ┌───────▼────────┐
    │    Backend: loader.py      │  │  installer.py   │
    │   (扫描+解析 SKILL.md)     │  │ (安全解压安装)   │
    └─────────────┬──────────────┘  └────────────────┘
                  │
    ┌─────────────▼──────────────┐
    │   prompt.py: 注入 agent    │  ← 生成 <skill_system> XML 块
    │   系统 prompt              │    只加载 enabled 的技能
    └─────────────┬──────────────┘
                  │
    ┌─────────────▼──────────────┐
    │   Agent 运行时:            │
    │   匹配用户查询 → read_file │  ← 渐进式加载
    │   → 执行 skill workflow    │
    └────────────────────────────┘
                  │
    ┌─────────────▼──────────────┐
    │   Gateway API + 前端 UI    │  ← 列表/详情/启用/禁用/安装
    └────────────────────────────┘
```

---

## 4. Claude Skills 2.0 能力对标

### 4.1 DeerFlow 已具备的 Skills 2.0 能力

DeerFlow 通过内置的 `skill-creator` 技能（`skills/public/skill-creator/`），实现了与 Claude Skills 2.0 同源的 **A/B 测试**和**自我迭代**能力。

#### A/B 测试

**`run_eval.py`** — 触发评估引擎：
- 对一组查询并行测试技能描述是否正确触发
- 支持多次运行取平均（`runs_per_query`），消除随机性
- 输出 pass/fail、trigger_rate 等量化指标

**`aggregate_benchmark.py`** — A/B 对比分析：
- 支持 `with_skill` vs `without_skill` 两组配置的对比
- 计算 pass_rate、时间、token 的均值/标准差/min/max
- 生成 delta 对比表

#### 自我迭代

**`improve_description.py`** — 基于评估结果自动优化描述：
- 分析失败的触发/误触发 case
- 调用 LLM 生成改进后的描述
- 防过拟合设计：限制描述长度 ≤1024 字符，鼓励泛化而非枚举

**`run_loop.py`** — 核心迭代循环：
- **Train/Test 分割**（默认 holdout=40%），防止过拟合
- 循环：评估 → 分析失败 → LLM 生成新描述 → 再评估
- 最多 `max_iterations` 轮（默认5轮）
- 追踪历史版本（v0, v1, v2...），最终选择得分最高的描述
- 实时生成 HTML 报告

#### 完整工作流

```
用户创建/修改 Skill
       ↓
  编写 eval set（测试用例）
       ↓
  ┌──────────────────────────┐
  │  run_loop.py 迭代循环     │
  │                          │
  │  1. run_eval.py 评估     │ ← Train set + Test set
  │  2. 分析失败 case         │
  │  3. improve_description  │ ← LLM 自动生成新描述
  │  4. 回到 1（直到收敛）    │
  │                          │
  │  输出：最优描述 + 历史记录  │
  └──────────────────────────┘
       ↓
  aggregate_benchmark.py     ← A/B 对比统计
       ↓
  generate_report.py         ← HTML 可视化报告
```

### 4.2 特性对照表

| Claude Skills 2.0 特性 | DeerFlow 对应实现 | 状态 |
|---|---|---|
| A/B 测试 | `aggregate_benchmark.py`：with_skill vs without_skill 对比 | ✅ 已实现 |
| 自我迭代 | `run_loop.py`：eval → improve → eval 循环 | ✅ 已实现 |
| Train/Test 分割 | `split_eval_set()` 函数，stratified holdout | ✅ 已实现 |
| 防过拟合 | 40% holdout + 描述长度限制 + 泛化指导 | ✅ 已实现 |
| 版本追踪 | `history.json`：记录每个版本的 pass_rate 和最佳版本 | ✅ 已实现 |
| 实时报告 | `generate_report.py`：浏览器自动刷新的 HTML 报告 | ✅ 已实现 |

---

## 5. 多模型兼容性分析

### 5.1 结论

**当前 A/B 测试 + 自我迭代机制硬绑定了 Claude Code CLI，无法在其他大模型上直接使用。**

### 5.2 具体绑定点

#### `run_eval.py` — 评估脚本

```python
# 第70-78行：硬编码调用 claude CLI
cmd = [
    "claude",
    "-p", query,
    "--output-format", "stream-json",
    "--verbose",
    "--include-partial-messages",
]
```

绑定内容：
- 通过 `.claude/commands/` 目录注入技能定义（Claude Code 特有机制）
- 解析 Claude 特有的 `stream-json` 事件格式（`content_block_start`、`tool_use`）
- 检测 Claude 特有的 `Skill`/`Read` 工具调用来判断是否触发

#### `improve_description.py` — 优化脚本

```python
# 第26行：硬编码调用 claude CLI
cmd = ["claude", "-p", "--output-format", "text"]
```

绑定内容：
- prompt 中明确写着 *"for a Claude Code skill"*
- 依赖 Claude Code 的会话认证，不使用独立 API Key

### 5.3 绑定项汇总

| 绑定项 | 说明 | 影响范围 |
|--------|------|----------|
| **CLI 工具** | 依赖 `claude -p` 命令行 | `run_eval.py`, `improve_description.py` |
| **触发检测** | 通过 Claude 的 `tool_use` stream 事件检测技能调用 | `run_eval.py` |
| **命令文件** | 利用 `.claude/commands/` 目录机制注入临时技能 | `run_eval.py` |
| **认证方式** | 使用 Claude Code 会话认证 | 两个脚本 |
| **prompt 措辞** | "for a Claude Code skill" | `improve_description.py` |

### 5.4 模型无关 vs 模型绑定的部分

| 层次 | 模型依赖 | 说明 |
|------|---------|------|
| **算法设计** | ✅ 模型无关 | eval loop、train/test split、description optimization 的设计理念 |
| **数据格式** | ✅ 模型无关 | eval set JSON、history.json、benchmark 报告格式 |
| **防过拟合策略** | ✅ 模型无关 | holdout 分割、泛化指导、长度限制 |
| **脚本实现** | ❌ Claude 绑定 | `claude -p` CLI 调用、stream 事件解析、命令文件注入 |
| **prompt 模板** | ❌ Claude 绑定 | 措辞面向 "Claude Code skill" |

### 5.5 改造建议

如果要让这套机制适配 DeerFlow 自身的多模型架构（GPT-4、DeepSeek、Gemini 等），需要：

1. **替换 `claude -p` 调用** → 改用 DeerFlow 自身的 `DeerFlowClient` 或直接调用 LangChain 模型接口
2. **替换触发检测逻辑** → 利用 DeerFlow 的 `lead_agent` prompt 中的 `<skill_system>` 机制，检测 Agent 是否调用了 `read_file` 读取 SKILL.md
3. **替换命令文件注入** → 动态修改 `extensions_config.json` 的技能启用状态
4. **替换 prompt 模板** → 将 "Claude Code skill" 相关措辞改为通用描述
5. **适配 stream 解析** → 使用 LangChain 的回调机制替代 Claude 特有的 stream-json 事件

---

## 6. 结论与建议

### 6.1 总体评价

DeerFlow 的 Skills 系统是一个**成熟且功能完整**的技能框架：

- ✅ **基础架构完备**: 加载、解析、验证、安装、管理的全链路实现
- ✅ **API + UI 齐全**: 4 个 REST 端点 + 前端设置页面
- ✅ **安全防护到位**: ZIP 炸弹、路径穿越、符号链接等安全检查
- ✅ **Claude Skills 2.0 核心能力已具备**: A/B 测试 + 自我迭代
- ❌ **A/B 测试/自我迭代机制绑定 Claude Code CLI**: 无法在其他模型上直接使用

### 6.2 建议

| 优先级 | 建议 | 说明 |
|--------|------|------|
| **高** | 将 eval/improve 脚本适配 DeerFlow 原生多模型架构 | 解除 Claude CLI 绑定，使 A/B 测试和自我迭代能力可用于任何配置的 LLM |
| **中** | 在 DeerFlow Gateway 中暴露 eval/improve API | 允许前端 UI 触发技能优化流程 |
| **低** | 补充 `skills/custom/` 目录的示例和文档 | 降低用户创建自定义技能的门槛 |

---

## 附录: 关键文件索引

| 文件路径 | 功能 |
|---------|------|
| `skills/public/` | 18 个内置技能目录 |
| `backend/packages/harness/deerflow/skills/` | 后端核心模块（加载/解析/验证/安装） |
| `backend/app/gateway/routers/skills.py` | REST API 路由 |
| `backend/packages/harness/deerflow/agents/lead_agent/prompt.py` | Agent prompt 技能注入 |
| `backend/packages/harness/deerflow/config/skills_config.py` | 技能配置 |
| `backend/packages/harness/deerflow/config/extensions_config.py` | 扩展配置（含技能启用状态） |
| `backend/packages/harness/deerflow/sandbox/tools.py` | 沙箱路径映射 |
| `frontend/src/core/skills/` | 前端核心模块（API/类型/Hooks） |
| `frontend/src/components/workspace/settings/skill-settings-page.tsx` | 技能设置页面 |
| `skills/public/skill-creator/scripts/run_eval.py` | 触发评估引擎 |
| `skills/public/skill-creator/scripts/improve_description.py` | 描述自动优化 |
| `skills/public/skill-creator/scripts/run_loop.py` | 迭代循环主程序 |
| `skills/public/skill-creator/scripts/aggregate_benchmark.py` | A/B 对比统计 |
| `skills/public/skill-creator/scripts/generate_report.py` | HTML 报告生成 |
| `config.example.yaml` | 技能配置示例（第420-433行） |
| `extensions_config.example.json` | 扩展配置示例 |
| `docs/SKILL_NAME_CONFLICT_FIX.md` | 技能名称冲突修复文档 |
