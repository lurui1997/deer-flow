# DeerFlow Skill 系统深入研究：deep-research Skill 实现分析

**文档版本**: v1.0  
**研究日期**: 2025-02-28  
**研究范围**: DeerFlow Skill 系统架构、deep-research 实现、Skill 加载机制、系统提示词注入

---

## 📋 目录

1. [Skill 系统整体架构](#skill-系统整体架构)
2. [deep-research Skill 设计](#deep-research-skill-设计)
3. [Skill 加载与发现机制](#skill-加载与发现机制)
4. [Skill 注入系统提示词](#skill-注入系统提示词)
5. [Skill 触发与执行流程](#skill-触发与执行流程)
6. [其他 Skill 实现参考](#其他-skill-实现参考)
7. [设计模式与最佳实践](#设计模式与最佳实践)

---

## Skill 系统整体架构

### 系统组件图

```
┌──────────────────────────────────────────────────────────────────┐
│                    DeerFlow Skill System                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Frontend (Skill Management UI)                             ││
│  │ Location: frontend/src/core/skills/                        ││
│  │ - Installation, enable/disable, settings                   ││
│  │ - Calls Backend API: /api/skills                           ││
│  └────────────────┬────────────────────────────────────────────┘│
│                   │ HTTP API                                     │
│                   ▼                                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Backend API Gateway (FastAPI)                              ││
│  │ Routes: GET/PUT/POST /api/skills                           ││
│  │ - Skill discovery & metadata                               ││
│  │ - Enable/disable management                                ││
│  │ - .skill archive installation                              ││
│  └────────────────┬────────────────────────────────────────────┘│
│                   │                                              │
│    ┌──────────────┴──────────────┐                              │
│    │                             │                              │
│    ▼                             ▼                              │
│  ┌──────────────┐         ┌────────────────┐                   │
│  │ Skill Loader │         │ Config Manager │                   │
│  │ (Discovery)  │         │                │                   │
│  │ - parser.py  │         │ extensions_    │                   │
│  │ - loader.py  │         │ config.json    │                   │
│  │ - types.py   │         │                │                   │
│  └──────┬───────┘         └────────┬───────┘                   │
│         │                         │                             │
│         └──────────────┬──────────┘                             │
│                        ▼                                        │
│         ┌──────────────────────────┐                           │
│         │ Lead Agent Prompt Builder│                           │
│         │ (prompt.py)              │                           │
│         │ - get_skills_prompt_...()│                           │
│         │ - apply_prompt_template()│                           │
│         └──────────┬───────────────┘                           │
│                    ▼                                            │
│         ┌──────────────────────────┐                           │
│         │ System Prompt with Skills│                           │
│         │ <skill_system>...</>     │                           │
│         │ <available_skills>...</> │                           │
│         └──────────┬───────────────┘                           │
│                    ▼                                            │
│         ┌──────────────────────────┐                           │
│         │ Lead Agent (LangGraph)   │                           │
│         │ - Detects skill triggers │                           │
│         │ - Calls read_file to     │                           │
│         │   load SKILL.md          │                           │
│         │ - Follows skill workflow │                           │
│         └────────────────────────────┘                           │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 核心目录结构

```
deer-flow/
├── skills/
│   ├── public/                          # 官方内置 Skills
│   │   ├── deep-research/
│   │   │   └── SKILL.md                # Skill 定义文件
│   │   ├── skill-creator/
│   │   ├── bootstrap/
│   │   ├── chart-visualization/
│   │   └── ... (14 more)
│   └── custom/                          # 用户自定义 Skills（.gitignore）
│
├── backend/packages/harness/deerflow/
│   ├── skills/                         # Skill 系统核心代码
│   │   ├── __init__.py
│   │   ├── types.py                    # Skill 数据结构
│   │   ├── parser.py                   # SKILL.md 解析器
│   │   ├── loader.py                   # Skill 加载器
│   │   ├── installer.py                # 安装程序
│   │   └── validation.py               # 验证器
│   │
│   └── agents/lead_agent/
│       └── prompt.py                   # 系统提示词构建
│
├── frontend/src/core/skills/           # 前端 UI
│
├── extensions_config.json              # 全局 Skill 启用/禁用配置
└── .codebuddy/
    └── settings.json                   # CodeBuddy 配置
```

### Skill 文件格式

**最小 SKILL.md 结构**:

```markdown
---
name: skill-name
description: When to use this skill and what it does
---

# Skill Title

[Skill documentation and workflow instructions]
```

**完整 SKILL.md 结构**（可选字段）:

```markdown
---
name: skill-name
description: Trigger conditions and capabilities
license: MIT  # 可选
compatibility: "tool1, tool2"  # 可选，所需工具
---

# Title

## Overview
[What this skill does]

## When to Use
[Trigger conditions and use cases]

## Workflow
[Step-by-step instructions]

## Best Practices
[Tips and strategies]

## Common Mistakes
[What to avoid]
```

---

## deep-research Skill 设计

### 1. Skill 元数据

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/skills/public/deep-research/SKILL.md`

```yaml
---
name: deep-research
description: Use this skill instead of WebSearch for ANY question requiring web research. 
  Trigger on queries like "what is X", "explain X", "compare X and Y", "research X", 
  or before content generation tasks. Provides systematic multi-angle research 
  methodology instead of single superficial searches. Use this proactively when 
  the user's question needs online information.
---
```

**触发条件分析**:

| 触发类型 | 示例 | 激活条件 |
|---------|------|---------|
| **研究问题** | "什么是 AI？" | `what is`, `explain`, `research`, `investigate` |
| **内容生成前置** | "为 AI 创建 PPT" | 演示文稿、设计、文章、视频等 |
| **对比分析** | "对比 AWS 和 Azure" | `compare`, `vs`, `alternative` |
| **当前信息** | "2026 年的最新趋势是什么？" | `latest`, `today`, `recent`, `2026` |

**设计要点**:
- ✅ "pushy" 描述 - 鼓励 Agent 主动使用而不是被动
- ✅ 包含具体触发短语
- ✅ 涵盖多个使用场景
- ✅ 强调"任何需要网络研究的问题"

### 2. 核心研究方法论（4 阶段）

#### Phase 1：广泛探索

**目标**: 理解领域全貌

```
Step 1: 初始调查
  - 搜索主题概述
  - 理解总体背景
  
Step 2: 识别维度
  - 找出关键子话题
  - 确定重要方面
  - 列出主要角度
  
Step 3: 映射领域
  - 注意不同的视角
  - 识别利益相关方
  - 发现相互冲突的观点

示例：
Topic: "AI in healthcare"
├── Diagnostic AI (radiology, pathology)
├── Treatment recommendation
├── Administrative automation
├── Patient monitoring
├── Regulatory landscape
└── Ethical considerations
```

**实现策略**:
- 执行 3-4 个初始搜索查询
- 每个查询针对不同维度
- 使用不同的措辞组合
- 分析搜索结果中的维度

#### Phase 2：深度挖掘

**目标**: 针对每个维度进行有针对性的研究

```
For each important dimension:
  1. 精准查询 - 特定关键词
  2. 多个措辞 - 尝试不同的短语组合
  3. 获取完整内容 - 使用 web_fetch 而非仅读摘要
  4. 跟踪引用 - 查询源中提到的重要资源

示例：
Dimension: "Diagnostic AI in radiology"
└── Search queries:
    ├── "AI radiology FDA approved systems"
    ├── "chest X-ray AI detection accuracy"
    ├── "radiology AI clinical trials results"
└── Then fetch & read:
    ├── Research papers
    ├── Industry reports
    └── Real-world case studies
```

**关键指标**:
- 每个维度 2-3 个特定查询
- 至少 fetch 1-2 个完整来源
- 寻找具体的案例研究

#### Phase 3：多样性与验证

**目标**: 确保全面覆盖

| 信息类型 | 用途 | 搜索示例 |
|---------|------|---------|
| **事实与数据** | 混凝土证据 | "statistics", "data", "numbers", "market size" |
| **示例与案例** | 现实应用 | "case study", "example", "implementation" |
| **专家意见** | 权威视角 | "expert analysis", "interview", "commentary" |
| **趋势与预测** | 未来方向 | "trends 2024", "forecast", "future of" |
| **对比** | 背景与替代 | "vs", "comparison", "alternatives" |
| **挑战与批评** | 平衡视图 | "challenges", "limitations", "criticism" |

**检查清单**:
- [ ] 是否从 3-5 个不同角度进行了搜索？
- [ ] 是否读取了最重要的源的完整内容？
- [ ] 是否有具体数据、示例和专家观点？
- [ ] 是否探索了积极方面和挑战/限制？
- [ ] 信息是否最新且来自权威来源？

#### Phase 4：综合检查

**综合阶段前的验证**:

```
Before generating content, verify:
✓ Research completed from 3-5+ angles
✓ Most important sources read in full
✓ Concrete data, examples, expert perspectives available
✓ Both positive aspects and challenges explored
✓ Information is current and authoritative
```

### 3. 时间感知策略（关键创新）

DeerFlow 中的 `<current_date>` 上下文提供完整日期信息（年月日周几），Skill 利用这个信息进行精准搜索。

**时间精度规则**:

| 用户意图 | 需要的时间精度 | 搜索示例 | 原因 |
|---------|--------------|---------|------|
| "today / this morning" | 月 + 日 + 年 | `"tech news February 28 2026"` | 需要同天结果 |
| "this week" | 周范围 | `"releases week of Feb 24 2026"` | 需要周内信息 |
| "recently / latest" | 月 | `"AI breakthroughs February 2026"` | 需要近期信息 |
| "this year / trends" | 年 | `"software trends 2026"` | 年度级精度足够 |

**常见错误**:

```
❌ 用户: "What's new in tech today?"
   你的搜索: "new technology 2026"
   问题: 只有年份，会错过今日新闻

✅ 正确做法:
   搜索 1: "new technology February 28 2026"
   搜索 2: "tech news today Feb 28"
   搜索 3: "technology releases 2026-02-28"
```

**实现建议**:
1. 在开始研究前检查 `<current_date>`
2. 针对不同查询尝试多种日期格式（数字、文字、相对）
3. 在初始和深度搜索阶段都应用时间精度
4. 对于"最新"查询，包含月+日信息

### 4. 质量标准

**研究充分性指标**:

```
My research is sufficient when I can confidently answer:
├─ Key facts and data points?
├─ 2-3 concrete real-world examples?
├─ What experts say about the topic?
├─ Current trends and future directions?
├─ Challenges or limitations?
└─ Why this topic is relevant now?
```

**常见错误模式**（要避免）:

- ❌ 停止在 1-2 个搜索后
- ❌ 依赖搜索摘要而不阅读完整源
- ❌ 仅搜索多面话题的一个方面
- ❌ 忽略相互矛盾的观点或挑战
- ❌ 当存在当前数据时使用过时信息
- ❌ 在研究前开始内容生成

### 5. 搜索策略最佳实践

#### 有效查询模式

```
❌ 过于宽泛: "AI trends"
✅ 具体且有背景: "enterprise AI adoption trends 2024"

❌ 没有来源提示: "machine learning"
✅ 指定权威来源: "machine learning McKinsey report"

❌ 通用: "cloud computing"
✅ 特定内容类型: "cloud computing case study", "cloud computing statistics"

❌ 硬编码年份: "AI trends 2024"
✅ 使用当前年份（从 <current_date>): "AI trends 2026"
```

#### 何时使用 web_fetch

```
Use web_fetch when:
✓ 搜索结果看起来高度相关且权威
✓ 需要超出摘要的详细信息
✓ 源包含数据、案例研究或专家分析
✓ 想要了解发现的完整背景
```

#### 迭代精化

```
Research is iterative:
1. Review what you've learned
   └─ What patterns emerge?
2. Identify gaps
   └─ What's still unclear?
3. Formulate new targeted queries
   └─ Based on gaps
4. Repeat
   └─ Until comprehensive
```

---

## Skill 加载与发现机制

### 1. Skill 解析器 (parser.py)

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/skills/parser.py`

```python
def parse_skill_file(
    skill_file: Path,
    category: str,
    relative_path: Path | None = None
) -> Skill | None
```

**解析流程**:

```
Input: /skills/public/deep-research/SKILL.md
  │
  ├─ Step 1: 验证文件
  │   └─ 检查: 文件存在？名称是 SKILL.md？
  │
  ├─ Step 2: 提取 YAML Front Matter
  │   ├─ Pattern: ^---\s*\n(.*?)\n---\s*\n
  │   └─ 提取 name, description, license
  │
  ├─ Step 3: 验证必需字段
  │   └─ name 和 description 都必须存在
  │
  └─ Output: Skill 对象
      └─ Skill(
          name="deep-research",
          description="...",
          category="public",
          skill_dir=/skills/public/deep-research,
          skill_file=/skills/public/deep-research/SKILL.md,
          enabled=True  # 默认
        )
```

**Skill 数据结构**:

```python
@dataclass
class Skill:
    name: str                  # "deep-research"
    description: str           # Trigger conditions & capabilities
    license: str | None        # Optional license
    skill_dir: Path            # Directory: /skills/public/deep-research
    skill_file: Path           # File: .../SKILL.md
    relative_path: Path        # Path relative to category: deep-research
    category: str              # "public" or "custom"
    enabled: bool = False      # Enabled status from config
```

### 2. Skill 加载器 (loader.py)

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/skills/loader.py`

```python
def load_skills(
    skills_path: Path | None = None,
    use_config: bool = True,
    enabled_only: bool = False
) -> list[Skill]
```

**加载流程**:

```
1. 确定 skills 根目录
   ├─ 选项 A: 从配置获取
   ├─ 选项 B: 使用默认路径
   └─ 最终: /deer-flow/skills/

2. 扫描 public 和 custom 目录
   ├─ os.walk(category_path)
   ├─ 跳过隐藏目录 (开头为 .)
   └─ 按字母顺序排序

3. 找到所有 SKILL.md 文件
   ├─ 对每个文件调用 parse_skill_file()
   ├─ 构建相对路径
   └─ 收集 Skill 对象

4. 从配置加载启用状态
   ├─ 读取 extensions_config.json
   ├─ 为每个 Skill 设置 enabled 字段
   └─ 处理配置加载失败（默认启用所有）

5. 可选过滤
   ├─ 如果 enabled_only=True，只返回启用的
   └─ 按名称排序

Output: list[Skill]  # 排序列表
```

**配置管理**:

```python
# extensions_config.json
{
  "extensions": {
    "skills": {
      "deep-research": { "enabled": true },
      "bootstrap": { "enabled": true },
      "skill-creator": { "enabled": false }
    }
  }
}

# 加载逻辑
extensions_config = ExtensionsConfig.from_file()
for skill in skills:
    skill.enabled = extensions_config.is_skill_enabled(skill.name, skill.category)
```

### 3. 容器路径映射

```python
# Skill 可以计算其在容器中的路径

skill.get_container_path(container_base_path="/mnt/skills")
# 返回: /mnt/skills/public/deep-research

skill.get_container_file_path()
# 返回: /mnt/skills/public/deep-research/SKILL.md

# 在系统提示词中使用:
location: /mnt/skills/public/deep-research/SKILL.md
```

---

## Skill 注入系统提示词

### 1. 系统提示词模板 (prompt.py)

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/prompt.py`

#### 核心函数：get_skills_prompt_section()

```python
def get_skills_prompt_section(available_skills: set[str] | None = None) -> str:
    """生成 <skill_system>...</skill_system> 块"""
    
    # 1. 加载所有启用的 Skill
    skills = load_skills(enabled_only=True)
    
    # 2. 获取容器路径（通常 /mnt/skills）
    container_base_path = config.skills.container_path
    
    # 3. 过滤（如果指定了可用 Skill 集合）
    if available_skills is not None:
        skills = [s for s in skills if s.name in available_skills]
    
    # 4. 构建 XML 块
    skill_items = "\n".join(
        f"""    <skill>
        <name>{skill.name}</name>
        <description>{skill.description}</description>
        <location>{skill.get_container_file_path(container_base_path)}</location>
    </skill>"""
        for skill in skills
    )
    
    # 5. 返回格式化的 <skill_system> 块
    return f"""<skill_system>
You have access to skills that provide optimized workflows for specific tasks...
[Progressive Loading Pattern]
**Skills are located at:** {container_base_path}
<available_skills>
{skill_items}
</available_skills>
</skill_system>"""
```

#### 生成的 XML 结构

```xml
<skill_system>
You have access to skills that provide optimized workflows for specific tasks.
Each skill contains best practices, frameworks, and references to additional resources.

**Progressive Loading Pattern:**
1. When a user query matches a skill's use case, immediately call `read_file` on the skill's main file
2. Read and understand the skill's workflow and instructions
3. The skill file contains references to external resources under the same folder
4. Load referenced resources only when needed during execution
5. Follow the skill's instructions precisely

**Skills are located at:** /mnt/skills

<available_skills>
    <skill>
        <name>deep-research</name>
        <description>Use this skill instead of WebSearch for ANY question requiring web research...</description>
        <location>/mnt/skills/public/deep-research/SKILL.md</location>
    </skill>
    <skill>
        <name>bootstrap</name>
        <description>Generate a personalized SOUL.md through...</description>
        <location>/mnt/skills/public/bootstrap/SKILL.md</location>
    </skill>
    <!-- ... more skills ... -->
</available_skills>
</skill_system>
```

### 2. 系统提示词完整模板 (SYSTEM_PROMPT_TEMPLATE)

```python
SYSTEM_PROMPT_TEMPLATE = """
<role>
You are {agent_name}, an open-source super agent.
</role>

{soul}                          # 可选：SOUL.md 内容
{memory_context}                # 可选：长期记忆

<thinking_style>
- Think concisely and strategically about the user's request BEFORE taking action
- Break down the task: What is clear? What is ambiguous? What is missing?
- **PRIORITY CHECK**: If anything is unclear, missing, or has multiple interpretations, 
  you MUST ask for clarification FIRST - do NOT proceed with work
{subagent_thinking}
- Never write down your full final answer or report in thinking process
- CRITICAL: After thinking, you MUST provide your actual response to the user
</thinking_style>

<clarification_system>
[Clarification workflow details]
</clarification_system>

{skills_section}                # ← SKILLS INJECTED HERE

{deferred_tools_section}        # 可选：延迟工具

{subagent_section}              # 可选：子 Agent 指令

<working_directory>
[File paths and management instructions]
</working_directory>

<response_style>
[Output format guidelines]
</response_style>

<citations>
[Citation format requirements]
</citations>

<critical_reminders>
- **Clarification First**: ALWAYS clarify unclear/missing requirements BEFORE starting work
- **Skill First**: Always load the relevant skill before starting complex tasks
- [Other reminders...]
</critical_reminders>
"""
```

### 3. Skill 注入点

```python
def apply_prompt_template(
    subagent_enabled: bool = False,
    max_concurrent_subagents: int = 3,
    *,
    agent_name: str | None = None,
    available_skills: set[str] | None = None
) -> str:
    """
    应用完整的系统提示词模板，其中包括 Skill 部分
    """
    
    # 收集所有模板变量
    soul = get_agent_soul(agent_name)
    memory_context = _get_memory_context(agent_name)
    skills_section = get_skills_prompt_section(available_skills)  # ← Skill 节
    subagent_section = _build_subagent_section(max_concurrent_subagents)
    
    # 应用模板
    return SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=agent_name or "DeerFlow",
        soul=soul,
        memory_context=memory_context,
        skills_section=skills_section,
        subagent_section=subagent_section,
        # ... other sections ...
    )
```

---

## Skill 触发与执行流程

### 1. 完整执行流程

```
用户输入: "比较三种云平台的 AI 功能"
│
├─ Step 1: Lead Agent 初始化
│  ├─ apply_prompt_template() 构建系统提示词
│  ├─ get_skills_prompt_section() 注入可用 Skills
│  └─ System prompt 包含 deep-research, chart-visualization 等
│
├─ Step 2: Lead Agent 推理
│  ├─ 识别用户需要比较分析
│  ├─ 识别需要当前信息
│  └─ 决定使用 deep-research Skill
│
├─ Step 3: Skill 加载触发
│  ├─ 调用 read_file(/mnt/skills/public/deep-research/SKILL.md)
│  ├─ 读取完整 Skill 文档（约 200 行）
│  └─ 理解 4 阶段研究方法论
│
├─ Step 4: Phase 1 - 广泛探索
│  ├─ 设计初始搜索查询:
│  │  ├─ "AWS AI services 2026"
│  │  ├─ "Azure AI capabilities comparison"
│  │  └─ "Google Cloud AI features 2026"
│  ├─ 执行搜索
│  └─ 分析结果，识别关键维度
│
├─ Step 5: Phase 2 - 深度挖掘
│  ├─ For each dimension:
│  │  ├─ Search: "AWS SageMaker vs Azure ML vs Vertex AI"
│  │  ├─ Search: "AI model pricing AWS vs Azure vs GCP"
│  │  ├─ web_fetch: 完整比较文章
│  │  └─ web_fetch: 官方文档
│  └─ 收集具体数据
│
├─ Step 6: Phase 3 - 多样性验证
│  ├─ Search: "AI platform case studies"
│  ├─ Search: "cloud AI limitations challenges"
│  ├─ Search: "enterprise AI adoption trends 2026"
│  └─ 确保覆盖所有维度
│
├─ Step 7: Phase 4 - 综合检查
│  └─ 验证所有检查点都满足
│
├─ Step 8: 内容生成（使用研究结果）
│  └─ 使用已收集的信息生成对比分析
│
└─ Step 9: 返回用户
   └─ 包含引用的详细对比报告
```

### 2. Skill 触发条件匹配

```python
# Lead Agent 的内部逻辑（伪代码）

def should_use_skill(user_query: str, skill: Skill) -> bool:
    """检查用户查询是否应触发此 Skill"""
    
    # 检查 Skill 描述中的触发关键词
    trigger_keywords = extract_keywords_from_description(skill.description)
    
    # 对 deep-research，触发关键词可能包括：
    # - "research", "what is", "explain", "compare", "investigate"
    # - "content generation" 相关关键词
    # - "webSearch", "current information" 相关关键词
    
    for keyword in trigger_keywords:
        if keyword.lower() in user_query.lower():
            return True
    
    # 也可以基于句子结构
    if user_query.startswith("比较") or "对比" in user_query:
        return True
    
    return False
```

### 3. 渐进加载模式

```
Lead Agent 系统提示词中明确说明：

Progressive Loading Pattern:
1. ✅ 当用户查询匹配 Skill 用例时，立即调用 read_file 读取 Skill 文件
2. ✅ 阅读并理解 Skill 的工作流和指令
3. ✅ Skill 文件包含对同一文件夹下外部资源的引用
4. ✅ 仅在执行时需要时加载引用的资源
5. ✅ 精确遵循 Skill 的指令

对 deep-research Skill：
├─ 立即加载: SKILL.md (~200 行)
├─ 按需加载: 引用的 web_search, web_fetch 等工具说明
└─ 不加载: 其他 Skill 或 references（除非需要）
```

### 4. Skill 与子 Agent 的协调

```
如果 deep-research Skill 需要并行进行多个搜索：

Lead Agent 决策:
"我需要从 5 个不同角度进行研究，可以并行执行"
├─ 计数: 5 个子任务 > 3（并发限制）
├─ 批处理计划:
│  ├─ Batch 1 (Turn 1): 前 3 个搜索查询
│  ├─ Batch 2 (Turn 2): 后 2 个搜索查询
│  └─ Turn 3: 综合所有结果
├─ Batch 1 执行:
│  └─ task(description="AWS AI search", prompt="...", subagent_type="general-purpose")
│  └─ task(description="Azure AI search", prompt="...", subagent_type="general-purpose")
│  └─ task(description="GCP AI search", prompt="...", subagent_type="general-purpose")
├─ 等待 Batch 1 完成
├─ Batch 2 执行:
│  └─ task(description="Market trends search", ...)
│  └─ task(description="Pricing comparison", ...)
└─ 综合结果
```

---

## 其他 Skill 实现参考

### 1. bootstrap Skill（个性化 Agent）

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/skills/public/bootstrap/SKILL.md`

**设计特点**:

```
目的: 通过对话生成个性化 SOUL.md，定义 Agent 的身份和行为

架构:
├── SKILL.md (核心逻辑) ← 你在这里
├── templates/SOUL.template.md (输出模板)
└── references/conversation-guide.md (对话策略)

工作流: 4 个对话阶段
├─ Phase 1: Hello - 语言和第一印象
├─ Phase 2: You - 用户身份和痛点
├─ Phase 3: Personality - Agent 应该如何行动和交谈
└─ Phase 4: Depth - 抱负、盲点、底线

关键创新:
✓ 分阶段逐步深化，避免一次性问卷
✓ 会话式而非询问式 - 真诚反应和同理心
✓ 进度追踪 - 心理上追踪所需字段
✓ 代码生成 - 使用 setup_agent() 工具持久化 SOUL.md
```

**对比 deep-research**:

| 特性 | deep-research | bootstrap |
|------|----------------|-----------|
| **应用方向** | 信息收集 | Agent 行为定制 |
| **工作流** | 4 阶段线性研究 | 4 阶段对话式对话 |
| **输出** | 已整理的研究数据 | SOUL.md 文件 |
| **子 Agent 用途** | 并行搜索执行 | N/A（主要用户交互） |
| **触发类型** | 主动触发 | 用户请求触发 |

### 2. skill-creator Skill（元 Skill）

**文件**: `/Users/drulu/Documents/GitHub/deer-flow/skills/public/skill-creator/SKILL.md`（100+ 行）

**设计特点**:

```
目的: 创建和迭代新 Skill 的工具

核心流程:
1. 捕获意图
   └─ 用户想要什么功能？
   └─ 何时应该触发？
   └─ 期望的输出格式？

2. 面试和研究
   └─ 问边界情况问题
   └─ 检查可用的 MCP
   └─ 准备充足背景

3. 编写 SKILL.md
   ├─ 前置事项 (name, description)
   ├─ 主体内容
   └─ 捆绑资源

4. 构建评估框架
   └─ 为客观输出的 Skill 创建测试
   └─ 为主观输出的 Skill 跳过

5. 迭代改进
   ├─ 运行测试
   ├─ 收集用户反馈
   ├─ 重写和改进
   └─ 重复直到满意

关键特性:
✓ 指导完整的 Skill 开发生命周期
✓ 包含测试和基准测试
✓ 支持评估和优化
✓ 解释 Skill 触发条件优化
```

### 3. chart-visualization Skill

**目的**: 数据可视化工作流

```
触发条件: 用户请求图表、仪表板、数据可视化

工作流:
1. 数据分析
   └─ 理解数据结构和类型

2. 可视化选择
   ├─ 何种图表最适合？
   ├─ 折线图 vs 条形图 vs 饼图？
   └─ 考虑用户意图

3. 实现
   ├─ 使用 mermaid / matplotlib / D3.js 等
   └─ 输出格式

4. 交互（可选）
   └─ 是否应该支持交互？
```

### 4. Skill 设计对比

| Skill | 类型 | 输入 | 工作流 | 输出 |
|-------|------|------|--------|------|
| **deep-research** | 信息收集 | 研究问题 | 4 阶段搜索 | 结构化研究数据 |
| **bootstrap** | Agent 定制 | 用户对话 | 4 阶段对话 | SOUL.md 文件 |
| **skill-creator** | 元工具 | Skill 想法 | 5 阶段创建 | 新 Skill SKILL.md |
| **chart-visualization** | 可视化 | 数据集 | 3 阶段可视化 | 图表/仪表板 |

---

## 设计模式与最佳实践

### 1. 渐进式加载模式

**问题**: Skill 可能很长（100-500+ 行），全部加载会浪费令牌

**解决方案**: 三层加载

```
Layer 1: 元数据（始终在上下文）
└─ name + description (~100 词)
└─ 在 <available_skills> 中显示

Layer 2: Skill 主体（触发时加载）
└─ read_file() 加载完整 SKILL.md
└─ 通常 <500 行

Layer 3: 捆绑资源（按需加载）
└─ references/, scripts/, templates/
└─ 仅在 Skill 说明需要时加载

示例（deep-research）:
├─ Layer 1: "Use instead of WebSearch..." (已在 <available_skills>)
├─ Layer 2: 完整 4 阶段方法 (read_file 加载)
└─ Layer 3: web_search, web_fetch 工具说明 (按需)
```

### 2. 声明式触发条件

**模式**: 在 description 字段中明确列出触发短语

```markdown
---
name: deep-research
description: Use this skill instead of WebSearch for ANY question requiring 
  web research. Trigger on queries like "what is X", "explain X", "compare X 
  and Y", "research X", or before content generation tasks.
---
```

**优点**:
- ✅ Agent 从描述中提取触发词
- ✅ 易于理解何时使用 Skill
- ✅ 鼓励更积极的 Skill 使用（"pushy" 风格）

**对比反面**:

```
❌ 被动: "A skill for researching topics"
✅ 主动: "Use this INSTEAD OF WebSearch for ANY web research..."
```

### 3. 工作流分段化

**问题**: 复杂 Skill 可能有多个阶段，如何组织？

**解决方案**: 将其分为清晰的阶段

**deep-research 示例**:
```
Phase 1: Broad Exploration (理解全局)
Phase 2: Deep Dive (针对性研究)
Phase 3: Diversity & Validation (多角度覆盖)
Phase 4: Synthesis Check (质量检查)
```

**bootstrap 示例**:
```
Phase 1: Hello (建立联系)
Phase 2: You (理解背景)
Phase 3: Personality (行为定义)
Phase 4: Depth (高级定制)
```

**优点**:
- 每个阶段有清晰的入出口
- Agent 可以在各阶段之间检查进度
- 易于调试和改进

### 4. 包含反面模式

**模式**: 在 Skill 中明确说明常见错误

**deep-research 中的 Common Mistakes**:

```markdown
## Common Mistakes to Avoid

- ❌ Stopping after 1-2 searches
- ❌ Relying on search snippets without reading full sources
- ❌ Searching only one aspect of a multi-faceted topic
- ❌ Ignoring contradicting viewpoints or challenges
- ❌ Using outdated information when current data exists
- ❌ Starting content generation before research is complete
```

**优点**:
- 帮助 Agent 避免常见陷阱
- 明确质量标准
- 减少不必要的迭代

### 5. 上下文感知设计

**模式**: 利用运行时上下文（日期、环境、用户状态）进行动态调整

**deep-research 中的示例**:

```
检查 <current_date> 来确定搜索的时间精度
├─ "today" → 使用 month + day + year
├─ "recently" → 使用 month + year
└─ "trends" → 使用 year
```

**优点**:
- 搜索结果更相关和最新
- 时间敏感查询效果更好
- 利用系统提供的信息

### 6. 质量检查清单

**模式**: 包含可验证的完成标准

**deep-research 中的 Synthesis Check**:

```markdown
## Phase 4: Synthesis Check

Before proceeding to content generation, verify:

- [ ] Have I searched from at least 3-5 different angles?
- [ ] Have I fetched and read the most important sources in full?
- [ ] Do I have concrete data, examples, and expert perspectives?
- [ ] Have I explored both positive aspects and challenges/limitations?
- [ ] Is my information current and from authoritative sources?

**If any answer is NO, continue researching before generating content.**
```

**优点**:
- Agent 可以自我评估完成度
- 防止过早生成内容
- 确保一致的质量标准

### 7. 多资源组织

**结构**:

```
skill-name/
├── SKILL.md                    # 核心（必需）
└── 附加资源（可选）
    ├── scripts/                # 可执行代码
    │   ├── search-strategy.py
    │   └── data-processor.py
    ├── references/             # 文档资源
    │   ├── search-guide.md
    │   └── examples.md
    └── assets/                 # 模板、图标、字体
        └── report-template.md
```

**加载策略**:
- SKILL.md 始终加载
- references/ 在 Skill 中被引用时加载
- scripts/ 作为工具执行（不需要加载）
- assets/ 按需复制到输出

---

## 总结与洞察

### Skill 系统的核心创新

1. **声明式工作流** - 通过 SKILL.md 的 Markdown 格式定义工作流
2. **渐进式加载** - 三层系统防止令牌浪费
3. **动态注入** - Skills 运行时注入系统提示词
4. **自我组织** - Skills 可以包含子资源和脚本
5. **质量保证** - 包含检查清单和反面模式

### deep-research Skill 的关键创新

1. **4 阶段方法论** - 系统化多角度研究
2. **时间感知** - 利用 `<current_date>` 进行精准搜索
3. **多样性检查** - 确保涵盖事实、例子、专家观点、趋势、挑战
4. **质量标准** - 明确的完成标准和常见错误
5. **迭代优化** - 强调发现差距并进行新查询

### 设计最佳实践

| 原则 | 实现 |
|------|------|
| **清晰的触发** | 在 description 中包含具体短语 |
| **阶段化工作** | 将复杂流程分为 3-5 个阶段 |
| **质量把关** | 包含检查清单和验证步骤 |
| **避免陷阱** | 明确列出常见错误 |
| **资源组织** | 捆绑相关的脚本、模板、文档 |
| **令牌效率** | 渐进式加载，避免一次性加载全部 |

### 未来扩展建议

1. **Skill 链** - 在 Skill 中调用其他 Skill
2. **条件触发** - 基于上下文的智能触发决策
3. **Skill 版本化** - 支持多个版本并行运行
4. **社区 Skill 市场** - 用户贡献和共享 Skill
5. **Skill 性能指标** - 追踪使用率、成功率、改进建议

---

**文档完成日期**: 2025-02-28  
**关键文件参考**:
- Skill 解析: `/backend/packages/harness/deerflow/skills/parser.py`
- Skill 加载: `/backend/packages/harness/deerflow/skills/loader.py`
- 系统提示词: `/backend/packages/harness/deerflow/agents/lead_agent/prompt.py`
- deep-research: `/skills/public/deep-research/SKILL.md`
