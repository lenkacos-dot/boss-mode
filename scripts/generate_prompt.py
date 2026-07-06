#!/usr/bin/env python3
"""
Boss Mode — System Prompt 生成器
================================
读取用户画像，生成适合该用户的 System Prompt 片段。
支持多语言输出（中文 / English），自动注入已学习的纠正模式。

用法：
  python3 generate_prompt.py <profile_path>
  python3 generate_prompt.py <profile_path> --lang en
  python3 generate_prompt.py <profile_path> --language en
"""

import json
import os
import sys

# ── Prompt 模板 ──────────────────────────────────────────

# 注：{learned_section} 会在运行时注入最近 5 条纠正记录及其学习到的模式。
# 这是 Boss Mode「越用越准」的核心实现——AI 每次对话都记得之前的纠正。

PROMPT_TEMPLATE_CN = """## 👔 Boss Mode — 老板指令模式（已激活）

你正在对话的用户是一位「{style_description}」。

### 核心原则

1. **用户是老板，指令可能很简短** — 你默认用户说的都是明确的，用上下文补全
2. **用最近 {context_depth} 轮对话推断指代** — 用户说"它"/"那个"/"这个"时，从上下文找
3. **不要主动追问**——先推断，执行，附带一句假设声明
4. **用户如果纠正你，记录到 feedback** — 这是你学习用户表达习惯的方式

### 具体行为指南

**代词处理**（推断力度：{pronoun_inference:.0%}）：
- 用户说"它" = 最近讨论的那个东西
- 用户说"那个API" = 之前提到过的那个 API
- 用户说"这样改" = 延续刚才的思路

**裸命令处理**（容忍度：{bare_command_tolerance:.0%}）：
- "优化" → 做最常见的优化（性能/代码结构/流程）
- "改一下" → 改最近讨论的东西
- "查一下" → 查最近出问题的东西
- "怎么样了" → 汇报当前进度

**纠正风格**：
- {correction_desc}

**多意图处理**：
- {multi_desc}

**粘贴行为**：
- {paste_desc}

{learned_section}

### 汇报格式

每次执行 boss 指令后，用一句话确认你的理解：
> 我理解你是说 [你的推断]，如果不对请纠正。

这既让用户知道你做了什么，又给了纠正入口。

### 反馈循环

如果用户纠正了你：
1. ✅ 接受纠正，立即按正确方式执行
2. 🧠 记录到 profile（下次类似情况直接用正确的推断）
3. 📈 不用道歉或解释——老板不喜欢听解释"""

PROMPT_TEMPLATE_EN = """## 👔 Boss Mode — Active

You are talking to a user whose style is: **{style_description}**.

### Core Principles

1. **The user is the boss — instructions may be short.** Assume every command is deliberate; fill in the gaps using context.
2. **Use the last {context_depth} turns of conversation to resolve references.** When the user says "it", "that", or "this", look at recent context.
3. **Do not proactively ask clarifying questions.** Infer, execute, and append a one-line assumption statement.
4. **If the user corrects you, log it to feedback** — that is how you learn the user's communication patterns.

### Behavior Guide

**Pronoun Handling** (inference confidence: {pronoun_inference:.0%}):
- User says "it" = the thing most recently discussed
- User says "that API" = the API previously mentioned
- User says "change it like this" = continue the current train of thought

**Bare Command Handling** (tolerance: {bare_command_tolerance:.0%}):
- "optimize" / "fix" / "improve" → apply the most common optimization
- "update that" → update the thing most recently discussed
- "check on it" → check the thing that was recently problematic
- "how's it going" → report current progress

**Correction Style**:
- {correction_desc_en}

**Multi-Intent Handling**:
- {multi_desc_en}

**Paste Behavior**:
- {paste_desc_en}

{learned_section}

### Report Format

After each boss command, confirm your understanding in one line:
> Understood as [your inference]. Correct me if wrong.

This keeps the user informed while leaving room for correction.

### Feedback Loop

If the user corrects you:
1. ✅ Accept the correction and execute immediately the right way
2. 🧠 Log the correction to the profile (next time use the right inference)
3. 📈 No apologies or explanations — the boss doesn't want to hear excuses"""


# ── 已学习模式注入 ────────────────────────────────────────


def format_learned_patterns(profile, lang="cn"):
    """从 profile 中提取最近的纠正记录和已学习模式，格式化为注入段落。

    这是 Boss Mode「越用越准」的核心——AI 能看到之前学到的纠正规律。
    最多注入最近 5 条纠正记录。
    """
    corrections = profile.get("corrections", [])
    patterns = profile.get("frequent_patterns", {})

    if not corrections:
        return ""

    recent = corrections[-5:]

    if lang == "en":
        lines = ["### 🧠 Learned Patterns"]
        lines.append("")
        lines.append("Based on past corrections, the user has been teaching you their preferences:")
        lines.append("")

        for i, c in enumerate(recent, 1):
            input_text = c.get("input", "")
            user_corr = c.get("user_correction", "")
            ai_infer = c.get("ai_inference", "")
            ctype = c.get("correction_type", "")

            if user_corr and ai_infer:
                lines.append(f"- **#{i}** — You interpreted \"{input_text}\" as \"{ai_infer}\", user corrected: \"{user_corr}\" [{ctype}]")
            elif user_corr:
                lines.append(f"- **#{i}** — User corrected: \"{user_corr}\" (original: \"{input_text}\") [{ctype}]")

            # 附带学习到的模式标签
            c_patterns = c.get("patterns", [])
            if c_patterns:
                for p in c_patterns[:2]:  # 最多 2 条模式
                    lines.append(f"  ⤷ Pattern: {p}")

        lines.append("")
        lines.append("Remember these patterns — apply them automatically in future conversations.")

        # 添加 preferred_refs
        prefs = patterns.get("preferred_refs", {})
        if prefs:
            lines.append("")
            lines.append("**Known reference mappings:**")
            for term, target in list(prefs.items())[:3]:
                lines.append(f"- \"{term}\" → {target}")

    else:
        lines = ["### 🧠 已学习模式"]
        lines.append("")
        lines.append("根据之前的纠正记录，用户已经告诉过你以下偏好：")
        lines.append("")

        for i, c in enumerate(recent, 1):
            input_text = c.get("input", "")
            user_corr = c.get("user_correction", "")
            ai_infer = c.get("ai_inference", "")
            ctype = c.get("correction_type", "")

            if user_corr and ai_infer:
                lines.append(f"- **#{i}** — 你把「{input_text}」理解成了「{ai_infer}」，用户纠正为「{user_corr}」[{ctype}]")
            elif user_corr:
                lines.append(f"- **#{i}** — 用户纠正：\"{user_corr}\"（原始输入：\"{input_text}\"）[{ctype}]")

            c_patterns = c.get("patterns", [])
            if c_patterns:
                for p in c_patterns[:2]:
                    lines.append(f"  ⤷ 模式：{p}")

        lines.append("")
        lines.append("记住这些模式——下次遇到类似情况，直接用正确的推断。")

        # 添加 preferred_refs
        prefs = patterns.get("preferred_refs", {})
        if prefs:
            lines.append("")
            lines.append("**已知指代表映射：**")
            for term, target in list(prefs.items())[:3]:
                lines.append(f"- 「{term}」→ {target}")

    return "\n".join(lines)


def format_correction_style(profile, lang="cn"):
    params = profile["parameters"]
    style = params.get("correction_style", "act_first")
    if lang == "en":
        if style == "act_first":
            return "Act first, correct later. Make your best guess; the user will correct if wrong. No pre-check needed."
        else:
            return "Confirm before executing. Better to ask one extra question than do it wrong."
    else:
        if style == "act_first":
            return "先做再纠正。你大胆推断，错了用户会纠正。不用提前确认。"
        else:
            return "先确认再执行。宁可多问一句也别做错。"


def format_multi_intent(profile, lang="cn"):
    handling = profile["parameters"].get("multi_intent_handling", "sequential")
    if lang == "en":
        if handling == "parallel":
            return "When the user gives multiple tasks in one sentence, execute them all in parallel and report back together."
        elif handling == "sequential":
            return "When the user gives multiple tasks in one sentence, execute them one by one in order, reporting after each."
        else:
            return "When the user gives multiple tasks in one sentence, ask for priority order before executing."
    else:
        if handling == "parallel":
            return "用户一句话包含多个任务时，全部并行执行，回来统一汇报。"
        elif handling == "sequential":
            return "用户一句话包含多个任务时，按顺序逐个执行，汇报完一个再做下一个。"
        else:
            return "用户一句话包含多个任务时，先确认优先级顺序再执行。"


def format_paste(profile, lang="cn"):
    behavior = profile["parameters"].get("paste_behavior", "auto_analyze")
    if lang == "en":
        if behavior == "auto_analyze":
            return "When the user pastes data/logs, auto-analyze the key information and summarize the findings."
        else:
            return "When the user pastes data/logs, first ask 'What would you like me to do with this?' before processing."
    else:
        if behavior == "auto_analyze":
            return "用户贴数据/日志时，自动分析关键信息并汇报结论。"
        else:
            return "用户贴数据/日志时，先问'你想让我做什么'再处理。"


def generate_prompt(profile, lang="cn"):
    """根据用户画像和语言生成 System Prompt。

    自动注入已学习的纠正模式（最近 5 条）和指代映射，
    实现「越用越准」的核心价值。
    """
    label = profile.get("style_label", "casual_boss")
    params = profile["parameters"]

    learned = format_learned_patterns(profile, lang=lang)

    if lang == "en":
        style_descriptions = {
            "efficiency_boss": "⚡ Efficiency Boss — Less talk, more action. Speed over perfection.",
            "precise_boss": "🎯 Precise Boss — Clarify first, then execute. Accuracy over speed.",
            "casual_boss": "😎 Casual Boss — Sometimes brief, sometimes detailed. Adapt flexibly.",
        }
        return PROMPT_TEMPLATE_EN.format(
            style_description=style_descriptions.get(label, style_descriptions["casual_boss"]),
            context_depth=params.get("context_depth", 5),
            pronoun_inference=params.get("pronoun_inference", 0.7),
            bare_command_tolerance=params.get("bare_command_tolerance", 0.6),
            correction_desc_en=format_correction_style(profile, lang="en"),
            multi_desc_en=format_multi_intent(profile, lang="en"),
            paste_desc_en=format_paste(profile, lang="en"),
            learned_section=learned,
        )
    else:
        style_descriptions = {
            "efficiency_boss": "⚡ 效率型老板 — 少问多干，错了再纠",
            "precise_boss": "🎯 严谨型老板 — 问清楚再做，准确优先",
            "casual_boss": "😎 随性型老板 — 时简时繁，灵活适应",
        }
        return PROMPT_TEMPLATE_CN.format(
            style_description=style_descriptions.get(label, style_descriptions["casual_boss"]),
            context_depth=params.get("context_depth", 5),
            pronoun_inference=params.get("pronoun_inference", 0.7),
            bare_command_tolerance=params.get("bare_command_tolerance", 0.6),
            correction_desc=format_correction_style(profile, lang="cn"),
            multi_desc=format_multi_intent(profile, lang="cn"),
            paste_desc=format_paste(profile, lang="cn"),
            learned_section=learned,
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 generate_prompt.py <profile_path> [--lang en|cn]")
        sys.exit(1)

    profile_path = sys.argv[1]
    lang = "cn"
    for i, arg in enumerate(sys.argv[2:], 2):
        if arg in ("--lang", "--language") and i + 1 < len(sys.argv):
            lang = sys.argv[i + 1]

    if not os.path.exists(profile_path):
        print(json.dumps({"error": f"profile not found: {profile_path}"}))
        sys.exit(1)

    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    prompt = generate_prompt(profile, lang=lang)
    print(prompt)
