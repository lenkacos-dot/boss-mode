#!/usr/bin/env python3
"""
Boss Mode — 共享核心模块
========================
校准与反馈循环共用的常量、参数边界、风格推断逻辑。
集中在此，避免 calibrate.py 与 update_feedback.py 各写一份
导致 infer_style_label 不同步（历史 bug 来源）。
"""

# ── 参数取值边界 ──────────────────────────────────────────
PARAM_BOUNDS = {
    "pronoun_inference": (0.0, 1.0),
    "bare_command_tolerance": (0.0, 1.0),
    "context_depth": (1, 10),
}

# 默认参数（未校准 / casual_boss 中档值）
# 新增 output_format / explanation_depth 为可选校准维度（#8），
# 不参与 style_label 计算，独立控制输出风格。
DEFAULT_PARAMS = {
    "pronoun_inference": 0.6,
    "bare_command_tolerance": 0.6,
    "correction_style": "act_first",
    "multi_intent_handling": "sequential",
    "paste_behavior": "auto_analyze",
    "context_depth": 5,
    # 可选高级校准维度（修复 #8：校准题目偏少）
    "output_format": "auto",
    "explanation_depth": "balanced",
}

# 反馈循环每次微调步长 —— 与文档承诺的 ±0.05 保持一致
ADJUST_STEP = 0.05

# 风格标签 → 中文描述
LABEL_DESCRIPTIONS = {
    "efficiency_boss": "⚡ 效率型老板 — 少问多干，错了再纠。时间比准确更重要。",
    "precise_boss": "🎯 严谨型老板 — 问清楚再做，准确比速度更重要。",
    "casual_boss": "😎 随性型老板 — 时简时繁，AI 灵活适应就好。",
}


def clamp(value, low, high):
    """限制数值在 [low, high] 区间。"""
    return max(low, min(high, value))


def infer_style_label(params):
    """根据参数推断风格标签（单一事实来源，校准与反馈共用）。

    统计 5 个维度的「激进」倾向数：
      1. pronoun_inference      >= 0.7
      2. bare_command_tolerance >= 0.7
      3. correction_style       == act_first
      4. multi_intent_handling  in (parallel, sequential)
      5. paste_behavior         == auto_analyze

      >= 4 → efficiency_boss
      <= 1 → precise_boss
      其余 → casual_boss
    """
    aggressive = sum([
        params.get("pronoun_inference", 0.5) >= 0.7,
        params.get("bare_command_tolerance", 0.5) >= 0.7,
        params.get("correction_style", "act_first") == "act_first",
        params.get("multi_intent_handling", "sequential") in ("parallel", "sequential"),
        params.get("paste_behavior", "auto_analyze") == "auto_analyze",
    ])
    if aggressive >= 4:
        return "efficiency_boss"
    if aggressive <= 1:
        return "precise_boss"
    return "casual_boss"


def label_description(label):
    """风格标签 → 描述文案。"""
    return LABEL_DESCRIPTIONS.get(label, "")
