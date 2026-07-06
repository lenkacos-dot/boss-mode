<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT">
  <img src="https://img.shields.io/badge/python-3.8%2B-brightgreen" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/tests-152%2F152-passing-brightgreen" alt="152/152 tests passing">
  <img src="https://img.shields.io/badge/dependencies-zero-orange" alt="Zero dependencies">
  <img src="https://img.shields.io/badge/platform-Hermes%20%7C%20Claude%20%7C%20ChatGPT%20%7C%20OpenCode-lightgrey" alt="Cross-platform">
  <img src="https://img.shields.io/github/stars/lenkacos-dot/boss-mode?style=social" alt="Stars">
</p>

<br/>

<h1 align="center">
  👔 Boss Mode<br/>
  <sub>老板指令模式</sub>
</h1>

<p align="center">
  <strong>让 AI 学会理解老板，<br/>
  而不是反过来要求老板「说清楚」。</strong>
</p>

<p align="center">
  <em>Boss never says "please elaborate."<br/>
  Boss says <strong>"check the logs."</strong> And expects you to get it.</em>
</p>

<br/>

<div align="center">
  <table>
    <tr>
      <td align="center"><b>⚡ 3 分钟完成</b><br/>校准 → 生效</td>
      <td align="center"><b>📦 零依赖</b><br/>纯 Python stdlib</td>
      <td align="center"><b>🔄 越用越准</b><br/>反馈循环自动微调</td>
      <td align="center"><b>🔌 跨平台</b><br/>Hermes / Claude / ChatGPT</td>
    </tr>
  </table>
</div>

<br/>

---

## 🚀 安装

```bash
# 30 秒安装
git clone https://github.com/lenkacos-dot/boss-mode ~/.hermes/skills/boss-mode
```

然后在对话里跟 AI 说：**「启动 Boss Mode 校准」**

AI 会问你 6 道场景题 → 答完就生效了。

> 💡 也可以手动集成到 Claude / ChatGPT / OpenCode，只需复制生成好的 prompt 到 system prompt。

---

## 🎯 三种风格

| 风格 | 中文名 | 适合谁 | 行为特征 |
|------|--------|--------|----------|
| `efficiency_boss` | ⚡ **效率型** | 创业者、技术主管、时间紧张的人 | 先干再说，错了再纠 |
| `precise_boss` | 🎯 **严谨型** | 甲方、传统行业领导、对准确性要求高的人 | 问清楚再做，有据可依 |
| `casual_boss` | 😎 **随性型** | 表达风格不固定的人 | 看情况灵活处理 |

**校准结果不是硬编码的。** 同一套 6 道题，不同人答出不同 profile，AI 行为完全不同。

---

## 🏗 三层架构

```
                         Boss Mode
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   1️⃣ 校准（一次性）          2️⃣ Prompt注入（每次对话）       │
│   ┌────────────────────┐    ┌─────────────────────────┐    │
│   │ • 代词推断力度       │    │ • 核心原则注入           │    │
│   │ • 裸命令容忍度       │ ──→│ • 行为指南注入           │    │
│   │ • 纠正风格偏好       │    │ • 汇报格式规范           │    │
│   │ • 多意图处理方式     │    │ • 反馈循环指令           │    │
│   │ • 粘贴行为偏好       │    └─────────────────────────┘    │
│   └────────────────────┘                                     │
│                      ↓                                      │
│             3️⃣ 反馈循环（持续优化）                           │
│        ┌─────────────────────────────────────────┐          │
│        │  纠正 → 记录 → 参数 ±0.05 → 下次自动正确  │          │
│        └─────────────────────────────────────────┘          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1️⃣ 校准 — 了解你的风格

回答 6 道场景题，AI 根据你的选择计算 **6 个参数 + 1 个风格标签**。

问什么？比如：

| 场景 | 如果你选 | AI 会... |
|------|----------|----------|
| 「修好它」 | 「直接做」 | 推断+执行，不确认 |
| 「修好它」 | 「先问清楚」 | 列出选项等你确认 |
| 贴一段日志 | 「直接分析」 | 自动分析并报告 |
| 「把那个优化一下」 | 「按优先级推测」 | 默认优化最关键的环节 |

### 2️⃣ 注入 — 每次对话自动生效

校准后 AI 读取你的 profile，生成一段 **customized system prompt**，包含：

- **推断规则**：「用户说'这个'时，优先推断最近讨论的上下文」
- **汇报格式**：「效率型 → 结论先行；严谨型 → 先说思路」
- **反馈模式**：「纠正时直接说，AI 立即学习」

### 3️⃣ 反馈 — 越用越准

```text
你: 修好它
AI:  我理解你是想修复部署脚本的问题
你: 不是，是数据库连接的问题
AI:  ✅ 记住：下次类似指令优先推测数据库方向
     参数 pronoun_inference 已微调 +0.05
```

**不需要重新校准。** 每次纠正都是一个学习信号，参数自动 ±0.05 调整。

---

## 📁 文件结构

```
boss-mode/
├── SKILL.md                  ← 完整文档（必读！）
├── README.md                 ← 本文件
├── scripts/
│   ├── boss_common.py        ← 共享核心模块
│   ├── calibrate.py          ← 校准工具
│   ├── generate_prompt.py    ← Prompt 生成器
│   └── update_feedback.py    ← 反馈更新器
├── references/
│   ├── profile_schema.md     ← 数据模型文档
│   └── scenarios.md          ← 指令模式库
├── test/
│   └── test_boss_mode.py     ← 22 个单元测试 ✅
└── profiles/                 ← 用户画像（运行时生成）
    └── default.json
```

---

## 🔬 谁在用 Boss Mode？

| 场景 | 效果 |
|------|------|
| 🐍 **Hermes AI Agent** | skill 安装后自动生效 |
| 🤖 **Claude / ChatGPT** | 复制生成的 prompt 到 system prompt |
| 💻 **OpenCode / Cursor** | 配合 Ponytail 决策梯使用 |
| 📱 **AI 工具链** | 任何支持自定义 system prompt 的平台 |

---

## 🧪 测试

```bash
cd scripts/..
python3 -m pytest test/test_boss_mode.py -v

# > 22/22 passed ✅
```

---

## 📖 更多文档

| 文档 | 内容 |
|------|------|
| `SKILL.md` | 完整技能文档（安装/使用/FAQ） |
| `references/profile_schema.md` | 6 个参数的完整解释 |
| `references/scenarios.md` | 4 大类老板指令模式 |
| `scripts/calibrate.py --help` | CLI 校准模式 |

---

## 🤝 贡献

PR 欢迎。觉得有用的话给个 ⭐ 就行～

**TODO:**
- [ ] Web UI 校准界面
- [ ] 多语言 prompt 模板（日语/韩语）
- [ ] 更多校准场景题

---

## 📜 License

MIT — 自由使用、修改、分发。

<br/><br/>

---

<p align="center">
  <strong>👔 Boss Mode v1.0.0</strong><br/>
  <sub>Made by <a href="https://github.com/lenkacos-dot">@lenkacos-dot</a></sub>
</p>

<br/><br/><br/>

---

<h1 align="center">👔 Boss Mode — Boss Instruction Mode</h1>

<p align="center">
  <strong>Make AI understand bosses, instead of telling bosses to "be more specific."</strong><br/>
  <em>A boss never says "please download the logs from staging, sort by timestamp, filter for ERROR."<br/>
  A boss just says <strong>"check the logs."</strong> And expects you to get it.</em>
</p>

---

## 🚀 Quick Start

```bash
git clone https://github.com/lenkacos-dot/boss-mode ~/.hermes/skills/boss-mode
```

Then tell your AI: **"Start Boss Mode calibration"** → answer 8 questions → done.

**Zero dependencies** — pure Python stdlib, no pip install.

---

## 🎯 Three Style Labels

| Style | Who It Fits | Behavior |
|-------|-------------|----------|
| `efficiency_boss` ⚡ | Founders, tech leads, time-pressed | Act first, correct later |
| `precise_boss` 🎯 | Clients, traditional managers, accuracy-first | Ask first, execute with evidence |
| `casual_boss` 😎 | Flexible expression style | Context-dependent |

---

## 🏗 Architecture (3-layer)

1. **Calibration (once):** Answer 8 scenario questions → AI computes 8 parameters + 1 style label.
2. **Prompt Injection (every session):** AI reads your profile → generates a customized system prompt.
3. **Feedback Loop (continuous):** You correct → AI logs → parameters ±0.05 → next time it's right.

---

## 📦 What's Inside

| File | Purpose |
|------|---------|
| `SKILL.md` | Full documentation (read this first) |
| `scripts/calibrate.py` | Calibration tool — CLI or conversational |
| `scripts/generate_prompt.py` | Profile → system prompt generator |
| `scripts/update_feedback.py` | Feedback loop — learns from corrections |
| `references/profile_schema.md` | 8-parameter data model |
| `references/scenarios.md` | Boss command pattern library |
| `test/test_boss_mode.py` | 152 unit tests ✅ |

---

## 🧪 Tests

```bash
cd scripts/..
python3 -m pytest test/test_boss_mode.py -v
# 152/152 passed ✅
```

---

## 📜 License

MIT — free to use, modify, distribute. PRs welcome.
