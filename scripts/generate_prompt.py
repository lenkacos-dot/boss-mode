#!/usr/bin/env python3
"""
Boss Mode — System Prompt 生成器
=================================
读取用户画像，生成适合该用户的 System Prompt 片段。

用法：
  python3 generate_prompt.py <profile_path>
  python3 generate_prompt.py <profile_path> --language en
"""

import json
import os
import sys

# ── Prompt 模板 ──────────────────────────────────────────

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

### 汇报格式

每次执行老板指令后，用一句话确认你的理解：
> 我理解你是说 [你的推断]，如果不对请纠正。

这既让用户知道你做了什么，又给了纠正入口。

### 反馈循环

如果用户纠正了你：
1. ✅ 接受纠正，立即按正确方式执行
2. 🧠 记录到 profile（下次类似情况直接用正确的推断）
3. 📈 不用道歉或解释——老板不喜欢听解释"""


def format_correction_style(profile):
    params = profile["parameters"]
    style = params.get("correction_style", "act_first")
    if style == "act_first":
        return "先做再纠正。你大胆推断，错了用户会纠正。不用提前确认。"
    else:
        return "先确认再执行。宁可多问一句也别做错。"


def format_multi_intent(profile):
    handling = profile["parameters"].get("multi_intent_handling", "sequential")
    if handling == "parallel":
        return "用户一句话包含多个任务时，全部并行执行，回来统一汇报。"
    elif handling == "sequential":
        return "用户一句话包含多个任务时，按顺序逐个执行，汇报完一个再做下一个。"
    else:
        return "用户一句话包含多个任务时，先确认优先级顺序再执行。"


def format_paste(profile):
    behavior = profile["parameters"].get("paste_behavior", "auto_analyze")
    if behavior == "auto_analyze":
        return "用户贴数据/日志时，自动分析关键信息并汇报结论。"
    else:
        return "用户贴数据/日志时，先问'你想让我做什么'再处理。"


def generate_prompt(profile):
    label = profile.get("style_label", "casual_boss")
    params = profile["parameters"]

    # 风格描述
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
        correction_desc=format_correction_style(profile),
        multi_desc=format_multi_intent(profile),
        paste_desc=format_paste(profile),
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 generate_prompt.py <profile_path>")
        sys.exit(1)

    profile_path = sys.argv[1]
    if not os.path.exists(profile_path):
        print(json.dumps({"error": f"profile not found: {profile_path}"}))
        sys.exit(1)

    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    prompt = generate_prompt(profile)
    print(prompt)
