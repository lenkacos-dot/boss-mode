# 👔 Boss Mode — 老板指令模式

> **让 AI 学会理解老板，而不是反过来要求老板「说清楚」。**

老板不会说 *"请把 staging 环境上那个服务器日志下载下来，按时间排序，筛选 ERROR 级别，然后发给我"*。
老板只会说：**「日志看一下。」** 然后期待你已经懂了。

Boss Mode 是一个 AI 行为适配器。它通过 **校准 → Prompt 注入 → 反馈循环** 三层结构，让 AI 自动适应用户的表达习惯——你说得越简短，它推断得越准。

[English](#-boss-mode-boss-instruction-mode)

---

## 快速开始（30 秒）

```bash
# 安装到 Hermes
cp -r boss-mode/ ~/.hermes/skills/boss-mode/

# 启动校准
# 跟 AI 说：「启动 Boss Mode 校准」
# 回答 6 道场景题，完成！
```

**零依赖** — 纯 Python 标准库，不需要 pip install。

---

## 三种风格标签

| 标签 | 中文名 | 适合谁 |
|------|--------|--------|
| `efficiency_boss` | ⚡ 效率型老板 | 创业者、技术主管、时间紧张的人 |
| `precise_boss` | 🎯 严谨型老板 | 甲方、传统行业领导、对准确性要求高的人 |
| `casual_boss` | 😎 随性型老板 | 表达风格不固定的人 |

---

## 三层架构

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

## 文件结构

```
boss-mode/
├── SKILL.md                       ← 完整文档
├── README.md                      ← 本文件
├── scripts/
│   ├── calibrate.py               ← 校准工具（6 道场景题）
│   ├── generate_prompt.py         ← Prompt 生成器
│   └── update_feedback.py         ← 反馈更新工具
├── references/
│   ├── profile_schema.md          ← Profile 数据模型
│   └── scenarios.md               ← 老板指令模式库
├── test/
│   └── test_boss_mode.py          ← 测试套件（15 个测试）
└── profiles/                      ← 用户画像（运行时生成）
    └── default.json               ← 默认 profile
```

---

## 工作原理

### 校准（一次性）

回答 6 道场景题——AI 根据你的选择，计算 8 个参数和 1 个风格标签。

问什么？比如：
- 「修好它」、「查查那个」——你希望 AI 直接推测还是先问清楚？
- 「优化」、「改一下」、「怎么样了」——AI 应该默认做什么？
- 你贴一段 JSON/日志——AI 应该自动分析还是先问你想干嘛？

### Prompt 注入（每次对话）

校准后，AI 读取你的 profile，自动生成一个 customized system prompt 片段，注入到每次对话的上下文。

### 反馈循环（持续优化）

你纠正 → AI 记录 → 参数微调 → 下次自动用正确推断。

```
你: 「修好它」
AI:  我理解你是想修复部署脚本的问题
你: 「不是，是数据库连接的问题」
AI:  ✅ 接受纠正，pronoun_inference 微调
     ✅ 下次类似指令自动知道指什么
```

---

## 兼容性

| 平台 | 支持 | 方式 |
|------|------|------|
| Hermes AI Agent | ✅ 原生 | skill 安装后自动生效 |
| Claude / ChatGPT | ✅ | 复制 prompt 片段到 system prompt |
| OpenCode / Cursor | ✅ 建议配合 | Ponytail 决策梯 + Boss Mode |

---

## 许可证

MIT — 自由使用、修改、分发。欢迎 PR。

---

<br/>

# 👔 Boss Mode — Boss Instruction Mode

> **Make AI understand bosses, instead of telling bosses to "be more specific."**

A boss never says *"Please download the logs from the staging server, sort by timestamp, filter for ERROR level, and send them to me."*
A boss just says: **"Check the logs."** And expects you to get it.

Boss Mode is an AI **behavior adapter** with a 3-layer architecture: **Calibration → Prompt Injection → Feedback Loop**.

---

## Quick Start (30 seconds)

```bash
# Install to Hermes
cp -r boss-mode/ ~/.hermes/skills/boss-mode/

# Start calibration
# Tell your AI: "Start Boss Mode calibration"
# Answer 6 scenario questions — done!
```

**Zero dependencies** — pure Python stdlib, no pip install needed.

---

## Three Style Labels

| Label | Who It Fits |
|-------|-------------|
| `efficiency_boss` ⚡ | Founders, tech leads, time-pressed people |
| `precise_boss` 🎯 | Clients, traditional managers, accuracy-first people |
| `casual_boss` 😎 | Flexible expression style, context-dependent |

---

## How It Works

1. **Calibration (once):** Answer 6 scenarios. AI computes 8 parameters + 1 style label.
2. **Prompt Injection (every session):** AI reads your profile, generates a customized system prompt.
3. **Feedback Loop (continuous):** You correct → AI logs → parameters tweaked → next time it's right.

---

## License

MIT — free to use, modify, distribute. PRs welcome.
