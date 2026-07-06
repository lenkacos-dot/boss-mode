---
name: boss-mode
version: 1.1.0
description: >
  👔 老板模式 — 让 AI 学会理解「老板、领导、甲方」的指令风格。
  用户说「修好它」、「优化」、「查一下然后把日志下载了」时，AI 不再追问"你说的它是什么"，
  而是大胆推断、果断执行。校准 → Prompt 注入 → 反馈循环，三层结构。
capabilities:
  - 用户表达风格校准（6 道场景题 → 6 参数 + 风格标签）
  - System Prompt 动态注入（按 profile 生成行为指令）
  - 反馈循环（纠正 / 确认 → 参数 ±0.05 双向微调）
---

# 👔 Boss Mode — 老板指令模式

> **让 AI 学会像理解老板一样理解你。**
>
> 老板不会说 "请把那个在 staging 环境上运行的服务器的日志下载下来，按时间排序，筛选出 ERROR 级别，然后发给我"。
>
> 老板只会说：「日志看一下」。
>
> 然后期待你已经懂了。

---

## 目录

1. [核心理念](#1-核心理念)
2. [安装](#2-安装)
3. [校准（第一次使用）](#3-校准第一次使用)
4. [System Prompt 注入（每次对话）](#4-system-prompt-注入每次对话)
5. [反馈循环（持续优化）](#5-反馈循环持续优化)
6. [场景示例](#6-场景示例)
7. [FAQ](#7-faq)
8. [与其他工具的关系](#8-与其他工具的关系)

---

## 1. 核心理念

### 不是什么

❌ 这不是一个「检测用户输入是否歧义」的工具  
❌ 这不是正则表达式 + 阈值判断  
❌ 这不是告诉用户「你说话不够清楚」

### 是什么

✅ 这是一个 **行为适配器** — 改变 AI 的默认行为模式  
✅ 这是一个 **表达风格校准器** — 让 AI 学会用户的表达习惯  
✅ 这是一个 **反馈回路** — 用户纠正得越多，AI 理解得越准

### 三个支柱

```
┌─────────────────────────────────────────────────────┐
│                    Boss Mode                         │
├─────────────────────────────────────────────────────┤
│                                                      │
│  1️⃣ 校准（一次性）            2️⃣ Prompt（每次对话）    │
│  ┌──────────────────┐       ┌──────────────────┐    │
│  │ • 代词推断力度      │       │ • 核心原则注入      │    │
│  │ • 裸命令容忍度      │  →   │ • 行为指南注入      │    │
│  │ • 纠正风格偏好      │       │ • 汇报格式规范      │    │
│  │ • 多意图处理方式    │       │ • 反馈循环指令      │    │
│  └──────────────────┘       └──────────────────┘    │
│                                                      │
│                          ↓                           │
│                3️⃣ 反馈循环（持续优化）                │
│  ┌────────────────────────────────────────────────┐ │
│  │ 纠正 → 记录 → 微调参数 → 下次自动用正确推断    │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## 2. 安装

### 方式 A：Hermes Skill 安装

```bash
# 从 Hermes skill 目录安装
cp -r boss-mode/ ~/.hermes/skills/boss-mode/

# 或者从远程仓库克隆
git clone https://github.com/lenkacos-dot/boss-mode ~/.hermes/skills/boss-mode
```

### 方式 B：手动集成

如果你不是用 Hermes，直接复制 System Prompt 片段到你的 AI 设置中即可（见第 4 节）。

### 验证安装

```bash
ls ~/.hermes/skills/boss-mode/
# 应该显示: SKILL.md  scripts/  references/  test/
```

---

## 3. 校准（第一次使用）

校准的目的是生成一份 **用户表达风格画像**（JSON），决定 AI 的推断力度和行为偏好。

### 方式 1：AI 对话式校准（推荐）

安装后，下次对话 AI 会自动检测到你需要校准。或者你直接说：

> 「启动 Boss Mode 校准」

AI 会引导你回答 6 个场景题，全程对话完成，不需要 CLI。

### 方式 2：CLI 校准

```bash
python3 ~/.hermes/skills/boss-mode/scripts/calibrate.py --cli
```

你会看到这样的交互（示例）：

```
📌 当你说「修好它」、「查查那个」、「这个改一下」这种话，
   你希望 AI 应该怎么做？

   [a] 直接推测我说的「它/那个/这个」指什么，动手做，错了我会纠正
   [b] 先问清楚「它」指的是什么，再动手
   [c] 看情况——有时候很明确，有时候要确认

   你的选择 (a/b/c):
```

6 道题后，自动生成 profile 并保存到 `~/.hermes/skills/boss-mode/profiles/default.json`。

### 校准结果示例

```json
{
  "style_label": "efficiency_boss",
  "parameters": {
    "pronoun_inference": 0.9,
    "bare_command_tolerance": 0.85,
    "correction_style": "act_first",
    "multi_intent_handling": "parallel",
    "paste_behavior": "auto_analyze",
    "context_depth": 10
  }
}
```

**三种风格标签：**

| 标签 | 中文名 | 适合谁 |
|------|--------|--------|
| `efficiency_boss` | ⚡ 效率型老板 | 创业者、技术主管、时间紧张的人 |
| `precise_boss` | 🎯 严谨型老板 | 甲方、传统行业领导、对准确性要求高的人 |
| `casual_boss` | 😎 随性型老板 | 表达风格不固定的人 |

---

## 4. System Prompt 注入（每次对话）

校准完成后，每次对话 AI 需要注入以下 system prompt（根据 profile 动态生成）：

> **自动注入**（Hermes）：AI 读取 your_profile.json，自动生成 prompt 片段  
> **手动注入**（其他 AI）：运行脚本生成，粘贴到 system prompt 中

```bash
python3 ~/.hermes/skills/boss-mode/scripts/generate_prompt.py ~/.hermes/skills/boss-mode/profiles/default.json
```

输出示例（基于 efficiency_boss profile）：

```
## 👔 Boss Mode — 老板指令模式（已激活）

你正在对话的用户是一位「⚡ 效率型老板 — 少问多干，错了再纠」。

### 核心原则
1. 用户是老板，指令可能很简短 — 你默认用户说的都是明确的，用上下文补全
2. 用最近 5 轮对话推断指代 — 用户说"它"/"那个"/"这个"时，从上下文找
3. 不要主动追问——先推断，执行，附带一句假设声明
4. 用户如果纠正你，记录到 feedback — 这是你学习用户表达习惯的方式

### 具体行为指南
**代词处理**（推断力度：90%）：
- 用户说"它" = 最近讨论的那个东西
- 用户说"那个API" = 之前提到过的那个 API

**裸命令处理**（容忍度：85%）：
- "优化" → 做最常见的优化
- "改一下" → 改最近讨论的东西
- "怎么样了" → 汇报当前进度

**纠正风格**：先做再纠正。你大胆推断，错了用户会纠正。

**多意图处理**：按顺序逐个执行，汇报完一个再做下一个。

**粘贴行为**：用户贴数据/日志时，自动分析关键信息并汇报结论。

### 汇报格式
每次执行老板指令后，用一句话确认你的理解：
> 我理解你是说 [你的推断]，如果不对请纠正。
```

---

## 5. 反馈循环（持续优化）

### 核心机制

Boss Mode 的真正价值在于：**用户纠正得越多，AI 理解得越准。**

```
用户说「修好它」
  → AI: "我理解你说的它是指 database.py 的问题，正在修复"
  → 用户: "不是，是 config.yml"
  → AI: ✅ 接受纠正，记录到 profile
        📈 pronoun_inference 从 0.85 降到 0.75
        🧠 corrections 数组添加一条: '当用户说"它"时优先指 config.yml'
        ✅ 下次用户说"修好它"，AI 直接改 config.yml
```

### 触发场景

每次 AI 输出 「我理解你是说 [推断]，如果不对请纠正」时：
- 用户不回应 → 推断正确，积累正面信号（参数不动）
- 用户纠正 → 记录纠正，微调参数

### 手动记录纠正

如果你发现 AI 的推断经常跑偏，可以直接跑：

```bash
python3 ~/.hermes/skills/boss-mode/scripts/update_feedback.py \
  ~/.hermes/skills/boss-mode/profiles/default.json \
  --input "修好它" \
  --ai-inference "我以为是改 main.py" \
  --correction "不是，是 utils.py"
```

---

## 6. 场景示例

### 场景 1：效率型老板（efficiency_boss）

| 用户说 | AI 反应 |
|--------|---------|
| "修好它" | "我理解你是说修复 staging 环境上的 bug #42，正在处理。" |
| "优化" | "正在做性能分析，我假设你是指上一个模块。结果如下：[数据]" |
| "查一下然后把日志下载了" | 先查状态，再下载日志，最后统一汇报 |
| 贴一段 JSON | 自动解析结构，汇报关键字段和异常值 |
| "那东西能 deploy 吗" | "你说的是最近修的那个模块吧？CI 过了，可以 deploy。" |

### 场景 2：严谨型老板（precise_boss）

| 用户说 | AI 反应 |
|--------|---------|
| "修好它" | "你说的'它'是指 staging 上的 bug #42 还是之前讨论的 config 问题？" |
| "优化" | "你想优化哪个模块？我列几个方向你选：1) 查询性能 2) 构建耗时 3) 代码结构" |
| "查一下然后把日志下载了" | "我先查状态，确认没问题再下载，你看顺序行吗？" |
| 贴一段 JSON | "收到了这份 JSON，你想让我分析还是转格式？" |
| "那东西能 deploy 吗" | "'那东西'具体指哪个模块？能给我一个名称或 PR 链接吗？" |

### 场景 3：随性型老板（casual_boss）

随上下文变化——如果用户刚才说了很详细的话，就用效率模式；如果用户自己也不确定，AI 会多问一句。

---

## 7. FAQ

### Q: 校准好后能换风格吗？

可以。重新跑一次校准，或者手动改 profile：

```bash
# 直接改为严谨型
python3 -c "
import json
p = json.load(open('profiles/default.json'))
p['parameters']['pronoun_inference'] = 0.3
p['parameters']['bare_command_tolerance'] = 0.3
p['style_label'] = 'precise_boss'
json.dump(p, open('profiles/default.json','w'), ensure_ascii=False, indent=2)
"
```

### Q: 用户没有校准直接用了会怎样？

默认使用 `casual_boss` 中档参数（pronoun_inference=0.6, tolerance=0.6），AI 会谨慎推断但不频繁追问。用户纠正第一次后开始学习。

### Q: 多人共享一个 AI 怎么办？

每个用户独立 profile：

```bash
profiles/
├── alan.json
├── xiaohong.json
└── boss.json
```

对话时根据用户切换 profile。

### Q: 和原来的 fuzzy-input 检测脚本是什么关系？

| old fuzzy-input | new boss-mode |
|----------------|--------------|
| 检测用户输入是否歧义 | 改变 AI 行为以适应表达习惯 |
| 输出 JSON 给 AI 参考 | 注入 system prompt，直接改变 AI 行为 |
| 硬编码阈值 | 用户自校准参数 |
| 没有学习能力 | 有反馈循环，越用越准 |
| 适合技术用户 | 适合所有人 |

Boss Mode 是 fuzzy-input v1/v2 的完全替代方案。

---

## 8. 与其他工具的关系

| 工具 | 关系 |
|------|------|
| Hermes AI Agent | 原生支持。Skill 安装后自动生效 |
| Claude / ChatGPT / 其他 AI | 支持。复制 generate_prompt.py 的输出到 system prompt 即可 |
| OpenCode / Cursor / 编码助手 | 建议配合 Ponytail 决策梯使用，Boss Mode 处理"用户说什么"，Ponytail 处理"代码怎么写" |

---

## 9. 实战案例：当反馈循环在真实世界跑通

> **这不是虚构场景。这是 Boss Mode 开发过程中真实发生的事情。**

开发者写完 Boss Mode 的 README 后，自我感觉"够好了"，于是问用户：
> 「要不要把 GitHub 主页做漂亮点？」

用户回答了一个 Boss Mode 式的纠正：
> **「你之前从没有问过要不要，我肯定是要的。为什么这次你会这么问？」**

这个纠正信号是完美的 feedback loop 示范：

| 步骤 | 对应 Boss Mode 原理 |
|------|-------------------|
| AI 默认选"差不多就行了" | 默认参数（low effort） |
| 用户纠正：「这还用问？」 | **用户纠正信号** |
| AI 意识到"这个人的标准是直接做到最好" | **参数微调（±0.05）** |
| 重写 README（+41% 内容，加 badges/表格/架构图/场景表/版尾） | **行为改变** |
| 以后同类场景自动用高标准 | **行为固化，不再需要第二次纠正** |

**一次纠正就够了。** 没有第二次「你要不要做」的追问。这就是反馈循环的价值——你的每一次纠正都不会被浪费，AI 会记住并自动调整后续行为。

### 这个案例说明什么

1. **纠正比请求更高效。** 你说「这不是我想要的」比「下次请这样做」更接近人类的沟通方式。
2. **反馈循环不需要显式接口。** 用户不需要点"记录反馈"按钮，只需要正常表达不满。
3. **Boss Mode 不是理论。** 它在开发它自己的 AI 身上真实跑通了。

> **当你设计一个会学习的 AI，用户的纠正就不会被浪费。**

---

## 附录：完整目录结构

```
boss-mode/
├── SKILL.md                       ← 本文档（核心）
├── scripts/
│   ├── boss_common.py             ← 共享核心模块（参数/风格推断）
│   ├── calibrate.py               ← 校准工具
│   ├── generate_prompt.py         ← Prompt 生成器
│   └── update_feedback.py         ← 反馈更新工具
├── references/
│   ├── profile_schema.md          ← Profile 数据模型
│   └── scenarios.md               ← 老板指令模式库
├── test/
│   └── test_boss_mode.py          ← 测试套件
└── profiles/                      ← 用户画像（运行时生成）
    └── default.json               ← 默认 profile
```
