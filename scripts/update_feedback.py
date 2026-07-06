#!/usr/bin/env python3
"""
Boss Mode — 反馈更新工具
=========================
当用户纠正 AI 的推断时，记录到 profile 中并微调参数。

用法：
  python3 update_feedback.py <profile_path> \
    --input "修好它" \
    --ai-inference "修改了 main.py line 42" \
    --correction "不是 main.py，是 utils.py"

静默模式（被 AI 调用）：
  echo '{"input": "...", "ai_inference": "...", "correction": "..."}' \
    | python3 update_feedback.py <profile_path> --quiet
"""

import json
import os
import sys
import datetime
import re


def load_profile(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_profile(path, profile):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def learn_pattern(input_text, ai_inference, correction):
    """从纠正中推断出可学习的模式"""
    patterns = []

    # 1. 代词指代纠正：用户说"它"但AI猜错了对象
    vague_words = ['它', '那', '这个', '那个', '这', 'its', 'that', 'this']
    for word in vague_words:
        if word in input_text:
            patterns.append(f"pronoun_reference: 用户说「{word}」时优先指代{correction}而非{ai_inference}")

    # 2. 裸命令纠正：用户说"优化"但AI优化错了东西
    bare_verbs = ['优化', '改', '修', '查', '看', '做', '弄']
    for verb in bare_verbs:
        if verb in input_text and len(input_text) < 30:
            patterns.append(f"bare_command: 用户说「{verb}」时指{correction}")

    # 3. 缩写纠正
    en_abbrev = re.findall(r'\b[a-zA-Z]{2,8}\b', input_text)
    cn_abbrev = re.findall(r'[\u4e00-\u9fff]{1,3}', input_text)
    # 只是简单的模式识别，实际由 AI 人工匹配

    return patterns


def adjust_parameters(profile, correction_type):
    """根据纠正类型微调参数"""
    params = profile["parameters"]

    if correction_type == "pronoun_wrong":
        # 代词搞错了 → 降低 pronoun_inference
        params["pronoun_inference"] = max(0.2, params["pronoun_inference"] - 0.1)

    elif correction_type == "bare_wrong":
        # 裸命令猜错了 → 降低 bare_command_tolerance
        params["bare_command_tolerance"] = max(0.2, params["bare_command_tolerance"] - 0.1)

    elif correction_type == "multi_wrong":
        # 多意图顺序错了 → 改为 ask
        params["multi_intent_handling"] = "ask"

    elif correction_type == "paste_wrong":
        # 粘贴猜错了 → 改为 ask_intent
        params["paste_behavior"] = "ask_intent"

    # 重新计算风格标签
    profile["style_label"] = infer_style_label(params)
    profile["updated_at"] = datetime.datetime.now().isoformat()

    return profile


def infer_style_label(params):
    """同 calibrate.py 中的推断逻辑"""
    aggressive = sum([
        params.get("pronoun_inference", 0.5) >= 0.7,
        params.get("bare_command_tolerance", 0.5) >= 0.7,
        params.get("correction_style", "act_first") == "act_first",
        params.get("multi_intent_handling", "sequential") in ("parallel", "sequential"),
        params.get("paste_behavior", "auto_analyze") == "auto_analyze",
    ])
    if aggressive >= 4:
        return "efficiency_boss"
    elif aggressive <= 1:
        return "precise_boss"
    else:
        return "casual_boss"


def main_cli(args):
    profile_path = args[0]
    profile = load_profile(profile_path)

    # Parse args
    input_text = ""
    ai_inference = ""
    correction = ""

    for i, arg in enumerate(args[1:], 1):
        if arg == "--input" and i + 1 < len(args):
            input_text = args[i + 1]
        elif arg == "--ai-inference" and i + 1 < len(args):
            ai_inference = args[i + 1]
        elif arg == "--correction" and i + 1 < len(args):
            correction = args[i + 1]

    if not input_text:
        print("❌ 需要 --input 参数")
        sys.exit(1)

    # 记录纠正
    correction_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "input": input_text,
        "ai_inference": ai_inference,
        "user_correction": correction,
        "patterns": learn_pattern(input_text, ai_inference, correction),
        "applied": True
    }
    profile.setdefault("corrections", []).append(correction_entry)

    # 推断纠正类型并微调参数
    if any(w in input_text for w in ['它', '那', '这个', '那个']):
        profile = adjust_parameters(profile, "pronoun_wrong")
    elif any(w in input_text for w in ['优化', '改', '修', '查']):
        profile = adjust_parameters(profile, "bare_wrong")

    save_profile(profile_path, profile)

    print(f"✅ 已记录纠正")
    print(f"   输入: {input_text}")
    print(f"   AI 推断: {ai_inference}")
    print(f"   纠正: {correction}")
    print(f"   当前风格: {profile['style_label']}")
    print(f"   累计纠正数: {len(profile['corrections'])}")


def main_quiet(args):
    """从 stdin 读取 JSON 并更新 profile"""
    profile_path = args[0]
    profile = load_profile(profile_path)

    raw = sys.stdin.read()
    data = json.loads(raw)

    correction_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "input": data.get("input", ""),
        "ai_inference": data.get("ai_inference", ""),
        "user_correction": data.get("correction", ""),
        "patterns": learn_pattern(
            data.get("input", ""),
            data.get("ai_inference", ""),
            data.get("correction", "")
        ),
        "applied": True
    }
    profile.setdefault("corrections", []).append(correction_entry)

    # 参数微调
    input_text = data.get("input", "")
    if any(w in input_text for w in ['它', '那', '这个', '那个']):
        profile = adjust_parameters(profile, "pronoun_wrong")
    elif any(w in input_text for w in ['优化', '改', '修', '查']):
        profile = adjust_parameters(profile, "bare_wrong")

    save_profile(profile_path, profile)
    print(json.dumps({
        "status": "ok",
        "style_label": profile["style_label"],
        "total_corrections": len(profile["corrections"])
    }))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 update_feedback.py <profile_path> [--quiet | --input ...]")
        sys.exit(1)

    if "--quiet" in sys.argv:
        main_quiet([a for a in sys.argv[1:] if a != "--quiet"])
    else:
        main_cli(sys.argv[1:])
