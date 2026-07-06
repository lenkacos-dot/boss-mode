#!/usr/bin/env python3
"""
Boss Mode — 用户风格校准工具
==============================
交互式校准，根据用户选择计算表达风格画像。
支持两种模式：
  1. 对话式（默认）：由 Hermes AI 引导用户完成
  2. CLI 模式（--cli）：直接在终端作答

用法：
  python3 calibrate.py              # 对话式（AI引导）
  python3 calibrate.py --cli        # 终端交互式
  python3 calibrate.py --quiet      # 静默模式，仅输出 JSON profile
"""

import json
import os
import sys
import datetime

# ── 校准场景 ──────────────────────────────────────────────

SCENARIOS = [
    {
        "id": "pronoun",
        "question": "当你说「修好它」、「查查那个」、「这个改一下」这种话，\n你希望 AI 应该怎么做？",
        "options": [
            {"key": "a", "text": "直接推测我说的「它/那个/这个」指什么，动手做，错了我会纠正", "score": {"pronoun_inference": 0.9, "correction_style": "act_first"}},
            {"key": "b", "text": "先问清楚「它」指的是什么，再动手", "score": {"pronoun_inference": 0.3, "correction_style": "ask_first"}},
            {"key": "c", "text": "看情况——有时候很明确，有时候要确认", "score": {"pronoun_inference": 0.6, "correction_style": "act_first"}},
        ]
    },
    {
        "id": "bare_command",
        "question": "当你说「优化」、「改一下」、「看看」这种只有动词没有宾语的命令，\n你希望 AI？",
        "options": [
            {"key": "a", "text": "直接做最可能的优化/改动，错了纠正", "score": {"bare_command_tolerance": 0.85, "correction_style": "act_first"}},
            {"key": "b", "text": "必须问清楚「优化什么」再做", "score": {"bare_command_tolerance": 0.3, "correction_style": "ask_first"}},
            {"key": "c", "text": "如果是常规操作（查状态/看进度）可以直接做，涉及修改的要确认", "score": {"bare_command_tolerance": 0.6, "correction_style": "act_first"}},
        ]
    },
    {
        "id": "multi_intent",
        "question": "当你说「查一下状态，然后把日志下载了整理成表格」这种一句话多个任务，\n你希望 AI？",
        "options": [
            {"key": "a", "text": "全部做完，回来统一汇报结果", "score": {"multi_intent_handling": "parallel"}},
            {"key": "b", "text": "按顺序做，做完一个汇报一个", "score": {"multi_intent_handling": "sequential"}},
            {"key": "c", "text": "先确认优先级，再做", "score": {"multi_intent_handling": "ask"}},
        ]
    },
    {
        "id": "paste",
        "question": "当你直接贴一段 JSON / 日志 / 报错信息给 AI（不说要做什么），\n你希望 AI？",
        "options": [
            {"key": "a", "text": "自动分析内容，直接汇报关键信息/结论", "score": {"paste_behavior": "auto_analyze"}},
            {"key": "b", "text": "先问「你想让我做什么」再处理", "score": {"paste_behavior": "ask_intent"}},
        ]
    },
    {
        "id": "context_depth",
        "question": "当你说「那东西怎么样了」——隔了多远的对话你还能接受 AI 自动推断？",
        "options": [
            {"key": "a", "text": "只要今天聊过的，都应该记得（10轮+）", "score": {"context_depth": 10}},
            {"key": "b", "text": "刚才聊的就够用了（3-5轮）", "score": {"context_depth": 5}},
            {"key": "c", "text": "最好是当前话题范围内（1-2轮）", "score": {"context_depth": 2}},
        ]
    },
    {
        "id": "priority",
        "question": "你最怕哪种情况？",
        "options": [
            {"key": "a", "text": "我怕 AI 一直追问打断思路，做错了我自己纠", "score": {"correction_style": "act_first"}},
            {"key": "b", "text": "我怕 AI 做错了浪费时间，多问一句确认更安心", "score": {"correction_style": "ask_first"}},
        ]
    },
]


def infer_style_label(params):
    """根据参数推断风格标签"""
    aggressive_count = 0
    cautious_count = 0

    if params.get("pronoun_inference", 0.5) >= 0.7:
        aggressive_count += 1
    else:
        cautious_count += 1

    if params.get("bare_command_tolerance", 0.5) >= 0.7:
        aggressive_count += 1
    else:
        cautious_count += 1

    if params.get("correction_style") == "act_first":
        aggressive_count += 1
    else:
        cautious_count += 1

    if params.get("multi_intent_handling") in ("parallel", "sequential"):
        aggressive_count += 1
    else:
        cautious_count += 1

    if params.get("paste_behavior") == "auto_analyze":
        aggressive_count += 1
    else:
        cautious_count += 1

    if aggressive_count >= 4:
        return "efficiency_boss"
    elif cautious_count >= 4:
        return "precise_boss"
    else:
        return "casual_boss"


def label_descriptions(label):
    descriptions = {
        "efficiency_boss": "⚡ 效率型老板 — 少问多干，错了再纠。时间比准确更重要。",
        "precise_boss": "🎯 严谨型老板 — 问清楚再做，准确比速度更重要。",
        "casual_boss": "😎 随性型老板 — 时简时繁，AI 灵活适应就好。",
    }
    return descriptions.get(label, "")


def build_profile(answers):
    """根据答案计算完整用户画像"""
    params = {
        "pronoun_inference": 0.6,
        "bare_command_tolerance": 0.6,
        "correction_style": "act_first",
        "multi_intent_handling": "sequential",
        "paste_behavior": "auto_analyze",
        "context_depth": 5,
    }

    for answer in answers:
        if answer:
            scenario_id = answer["scenario_id"]
            selected = answer["selected"]
            scenario = next(s for s in SCENARIOS if s["id"] == scenario_id)
            option = next(o for o in scenario["options"] if o["key"] == selected)

            for key, value in option["score"].items():
                if key in params:
                    if isinstance(params[key], float) and isinstance(value, float):
                        # Average with existing value
                        params[key] = (params[key] + value) / 2
                    else:
                        params[key] = value

    style_label = infer_style_label(params)

    profile = {
        "boss_mode_version": "1.0",
        "profile_id": "default",
        "created_at": datetime.datetime.now().isoformat(),
        "updated_at": datetime.datetime.now().isoformat(),
        "style_label": style_label,
        "style_description": label_descriptions(style_label),
        "parameters": params,
        "corrections": [],
        "frequent_patterns": {
            "shorthand_map": {},
            "preferred_refs": {},
            "common_phrases": []
        }
    }

    return profile


# ── CLI 模式 ──────────────────────────────────────────────

def run_cli():
    print("\n" + "=" * 60)
    print("   👔 Boss Mode — 用户风格校准工具")
    print("=" * 60)
    print()

    answers = []
    for scenario in SCENARIOS:
        print(f"\n📌 {scenario['question']}")
        print()
        for opt in scenario["options"]:
            print(f"   [{opt['key']}] {opt['text']}")
        print()

        while True:
            choice = input("  你的选择 (a/b/c): ").strip().lower()
            valid_keys = [o["key"] for o in scenario["options"]]
            if choice in valid_keys:
                break
            print(f"   ⚠️ 请输入 {', '.join(valid_keys)}")

        answers.append({
            "scenario_id": scenario["id"],
            "selected": choice
        })
        print(f"   ✅ 已记录")

    # 计算 profile
    profile = build_profile(answers)

    # 输出结果
    print("\n" + "=" * 60)
    print("   📊 校准完成！你的 Boss 风格：")
    print("=" * 60)
    print(f"\n   🏷️  {profile['style_description']}")
    print()
    print(f"   代词推断力度：      {profile['parameters']['pronoun_inference']:.0%}")
    print(f"   裸命令容忍度：      {profile['parameters']['bare_command_tolerance']:.0%}")
    print(f"   纠正偏好：          {'先做再纠正' if profile['parameters']['correction_style'] == 'act_first' else '先问再做'}")
    print(f"   多意图处理：        {'全部并行' if profile['parameters']['multi_intent_handling'] == 'parallel' else '逐个顺序' if profile['parameters']['multi_intent_handling'] == 'sequential' else '先确认'}")
    print(f"   粘贴行为：          {'自动分析' if profile['parameters']['paste_behavior'] == 'auto_analyze' else '先问用途'}")
    print(f"   上下文深度：        {profile['parameters']['context_depth']} 轮")
    print()

    # 保存
    save_path = input("  保存路径 (回车默认 ~/.hermes/skills/boss-mode/profiles/default.json): ").strip()
    if not save_path:
        save_dir = os.path.expanduser("~/.hermes/skills/boss-mode/profiles")
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, "default.json")

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

    print(f"   ✅ 已保存到 {save_path}")
    print()


def run_quiet():
    """静默模式 — 从 stdin 读取 JSON 答案，输出 JSON profile 到 stdout"""
    try:
        raw = sys.stdin.read()
        answers = json.loads(raw)
        profile = build_profile(answers)
        print(json.dumps(profile, ensure_ascii=False, indent=2))
    except (json.JSONDecodeError, KeyError) as e:
        print(json.dumps({"error": str(e), "hint": "stdin 需要 JSON 数组，格式： [{\"scenario_id\": \"pronoun\", \"selected\": \"a\"}, ...]"}))
        sys.exit(1)


if __name__ == "__main__":
    if "--quiet" in sys.argv:
        run_quiet()
    elif "--cli" in sys.argv:
        run_cli()
    else:
        print(json.dumps(SCENARIOS, ensure_ascii=False, indent=2))
