#!/usr/bin/env python3
"""
Boss Mode — 反馈更新工具
=========================
当用户纠正 AI 的推断时，记录到 profile 中并微调参数。
也支持「正面确认」——用户确认推断正确时回升参数（双向反馈循环）。

用法（纠正）：
  python3 update_feedback.py <profile_path> \
    --input "修好它" \
    --ai-inference "修改了 main.py line 42" \
    --correction "不是 main.py，是 utils.py"

显式指定纠正类型（pronoun_wrong/bare_wrong/multi_wrong/paste_wrong/correction_wrong）：
  python3 update_feedback.py <profile_path> \
    --input "查一下顺便把日志下了" \
    --type multi_wrong \
    --correction "顺序反了，先下日志"

正面确认（回升参数）：
  python3 update_feedback.py <profile_path> \
    --input "修好它" --positive

检测模式（让脚本判断一段对话是否是纠正，不修改 profile）：
  echo '{"input": "不是，是 utils.py", "ai_inference": "main.py", "original_input": "修好它"}' \
    | python3 update_feedback.py <profile_path> --detect

静默模式（被 AI 调用）：
  echo '{"input": "...", "ai_inference": "...", "correction": "...", "type": "...", "positive": false}' \
    | python3 update_feedback.py <profile_path> --quiet
"""

import json
import os
import sys
import datetime
import re

from boss_common import infer_style_label, ADJUST_STEP, PARAM_BOUNDS, clamp

# 最多保留的纠正记录数（超过则裁剪最旧的）
MAX_CORRECTIONS = 50

# ── 纠正识别规则 ──────────────────────────────────────────

# 用户明确否定的开头词——视为纠正
CORRECTION_PREFIXES = ["不是", "不对", "错了", "不对", "错了", "no", "not", "wrong", "nope"]
# 用户确认推断的开头词——视为正面反馈
CONFIRMATION_PREFIXES = ["对", "好", "好的", "yes", "right", "correct", "exactly", "yeah"]
# 新指令的开头词——既不是纠正也不是确认
NEW_COMMAND_PREFIXES = ["还有", "另外", "接着", "然后", "下一步", "again", "next", "also"]


def is_correction(user_reply: str, ai_inference: str = "") -> str:
    """判断用户回复是否是纠正（而不是新指令或确认）。

    规则：
      1. 以否定词开头 → 纠正
      2. 回复内容包含 ai_inference 中特定名称/关键词的否定 → 纠正
      3. 以确认词开头 → 正面反馈（不是纠正但需要记录）
      4. 以新指令词开头 → 新指令
      5. 没有明确信号 → 按推断优先原则视为新指令

    返回：
      "correction"  — 用户纠正
      "confirmation" — 用户确认推断正确
      "new_command"  — 新指令（不触发反馈循环）
    """
    reply = (user_reply or "").strip().lower()
    infer = (ai_inference or "").strip().lower()

    if not reply:
        return "new_command"

    for prefix in CORRECTION_PREFIXES:
        if reply.startswith(prefix):
            return "correction"

    for prefix in CONFIRMATION_PREFIXES:
        if reply.startswith(prefix):
            return "confirmation"

    for prefix in NEW_COMMAND_PREFIXES:
        if reply.startswith(prefix):
            return "new_command"

    # 如果回复长度很短（< 5字）且包含否定词，视为纠正
    if len(reply) < 10 and any(w in reply for w in ["不", "错", "非", "no", "not"]):
        return "correction"

    return "new_command"


# ── 工具函数 ──────────────────────────────────────────────


def load_profile(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_profile(path, profile):
    # 自动裁剪：保留最近 MAX_CORRECTIONS 条
    if len(profile.get("corrections", [])) > MAX_CORRECTIONS:
        profile["corrections"] = profile["corrections"][-MAX_CORRECTIONS:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def learn_pattern(input_text, ai_inference, correction):
    """从纠正中推断出可学习的模式"""
    patterns = []

    # 1. 代词指代纠正：用户说"它"但 AI 猜错了对象
    vague_words = ['它', '那', '这个', '那个', '这', 'its', 'that', 'this']
    for word in vague_words:
        if word in (input_text or ""):
            patterns.append(f"pronoun_reference: 用户说「{word}」时优先指代{correction}而非{ai_inference}")

    # 2. 裸命令纠正：用户说"优化"但 AI 优化错了东西
    bare_verbs = ['优化', '改', '修', '查', '看', '做', '弄']
    for verb in bare_verbs:
        if verb in (input_text or "") and len(input_text or "") < 30:
            patterns.append(f"bare_command: 用户说「{verb}」时指{correction}")

    return patterns


# ── 日志结构特征检测 ──────────────────────────────────────

_LOG_LEVELS = ["[ERROR]", "[WARN]", "[INFO]", "[DEBUG]", "[FATAL]",
               "ERROR:", "WARNING:", "FATAL:", "exception:", "traceback:"]
_STACK_TRACE_PATTERNS = [
    r"at\s+\S+\.\w+\(.*\)",         # Java: at com.example.MyClass.method()
    r"File\s+\".*\",\s+line\s+\d+",   # Python: File "x.py", line 42
    r"\s+->\d+#",                     # Elixir/Erlang stack traces
]
_JSON_LIKE_START = ("{", "[", "[")
_STRUCTURED_PATTERNS = [
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}",  # ISO datetime
    r"^\s*[\w.-]+\s*=",                     # key=value
    r"^\s*[\w.-]+\s*:",                     # YAML/JSON key: value
]


def _looks_like_log_or_error(text: str) -> bool:
    """判断文本看起来像日志/报错/结构化数据（vs 普通多行指令）。"""
    # 空行分割，检查每一段的特征
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) < 2:
        return False

    # 如果包含日志级别标记
    for level in _LOG_LEVELS:
        if level.lower() in text.lower():
            return True

    # 如果包含栈踪迹模式
    for pat in _STACK_TRACE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True

    # 如果以 JSON 开头
    stripped = text.strip()
    if stripped.startswith(_JSON_LIKE_START):
        return True

    # 如果 50%+ 的行包含结构化模式
    struct_count = 0
    for line in lines:
        for pat in _STRUCTURED_PATTERNS:
            if re.match(pat, line):
                struct_count += 1
                break
    if struct_count / len(lines) >= 0.5:
        return True

    # 如果 > 80% 的行长度接近（表格/日志列）
    if len(lines) >= 3:
        lengths = [len(l) for l in lines]
        avg = sum(lengths) / len(lengths)
        variance = sum((l - avg) ** 2 for l in lengths) / len(lengths)
        if variance < 100:  # 行间长度变化小 → 日志表格
            return True

    return False


# ── 纠正类型检测 ──────────────────────────────────────────


def detect_correction_type(input_text, correction=""):
    """从用户输入与纠正内容推断纠正类型。

    优先级：
      1. multi_wrong      — 纠正提到「顺序 / 优先级 / 先后」
      2. paste_wrong      — 输入像结构化数据（JSON / 日志 / 多行列日志）
      3. pronoun_wrong    — 输入含代词（它/那/这个）
      4. bare_wrong       — 输入含裸命令（优化/改/修/查）

    历史版本只检测 pronoun 与 bare，导致 multi_wrong / paste_wrong
    永远不会触发——已补全。v1.1 的 paste 检测过于激进（仅按换行符判断），
    现改进为多层 heuristics：日志级别 / 栈踪迹 / JSON / 结构化行 / 行长度方差。
    """
    text = input_text or ""
    corr = correction or ""

    if any(w in corr for w in ["顺序", "优先级", "先后", "顺序错", "先做", "先下", "先查"]):
        return "multi_wrong"

    # paste 检测：多层 heuristics
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        return "paste_wrong"
    if "\n" in text and _looks_like_log_or_error(text):
        return "paste_wrong"

    if any(w in text for w in ["它", "那", "这个", "那个", "这"]):
        return "pronoun_wrong"

    if any(w in text for w in ["优化", "改", "修", "查", "看", "做", "弄"]):
        return "bare_wrong"

    return "bare_wrong"


# ── 参数调整 ──────────────────────────────────────────────


def adjust_parameters(profile, correction_type, direction="down"):
    """根据纠正类型微调参数（双向）。

    direction="down"：用户纠正（负面信号），降低对应推断力度。
    direction="up"  ：用户确认正确（正面信号），回升推断力度。
    每次调整 ADJUST_STEP（0.05），受 PARAM_BOUNDS 约束。

    历史版本硬编码 0.1 且只降不升，与文档承诺的 ±0.05 不一致、
    且无正面反馈通道——已修正为双向 ±0.05。
    """
    params = profile["parameters"]
    step = ADJUST_STEP if direction == "down" else -ADJUST_STEP

    if correction_type == "pronoun_wrong":
        lo, hi = PARAM_BOUNDS["pronoun_inference"]
        params["pronoun_inference"] = round(clamp(params["pronoun_inference"] - step, lo, hi), 4)
    elif correction_type == "bare_wrong":
        lo, hi = PARAM_BOUNDS["bare_command_tolerance"]
        params["bare_command_tolerance"] = round(clamp(params["bare_command_tolerance"] - step, lo, hi), 4)
    elif correction_type == "multi_wrong":
        params["multi_intent_handling"] = "ask" if direction == "down" else "sequential"
    elif correction_type == "paste_wrong":
        params["paste_behavior"] = "ask_intent" if direction == "down" else "auto_analyze"

    profile["style_label"] = infer_style_label(params)
    profile["updated_at"] = datetime.datetime.now().isoformat()
    return profile


def _apply_correction(profile, input_text, ai_inference, correction, correction_type, positive):
    """记录纠正条目并微调参数，返回更新后的 profile。"""
    if correction_type is None:
        correction_type = detect_correction_type(input_text, correction)

    direction = "up" if positive else "down"

    correction_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "input": input_text,
        "ai_inference": ai_inference,
        "user_correction": correction,
        "correction_type": correction_type,
        "direction": direction,
        "patterns": learn_pattern(input_text, ai_inference, correction),
        "applied": True,
    }
    profile.setdefault("corrections", []).append(correction_entry)
    profile = adjust_parameters(profile, correction_type, direction)
    return profile


# ── CLI 模式 ──────────────────────────────────────────────


def main_cli(args):
    profile_path = args[0]
    profile = load_profile(profile_path)

    input_text = ""
    ai_inference = ""
    correction = ""
    correction_type = None
    positive = False

    for i, arg in enumerate(args[1:], 1):
        if arg == "--input" and i + 1 < len(args):
            input_text = args[i + 1]
        elif arg == "--ai-inference" and i + 1 < len(args):
            ai_inference = args[i + 1]
        elif arg == "--correction" and i + 1 < len(args):
            correction = args[i + 1]
        elif arg == "--type" and i + 1 < len(args):
            correction_type = args[i + 1]
        elif arg == "--positive":
            positive = True

    if not input_text:
        print("❌ 需要 --input 参数")
        sys.exit(1)

    if correction_type is None:
        correction_type = detect_correction_type(input_text, correction)

    profile = _apply_correction(profile, input_text, ai_inference, correction, correction_type, positive)
    save_profile(profile_path, profile)

    print(f"✅ 已记录{'正面确认' if positive else '纠正'}")
    print(f"   输入: {input_text}")
    print(f"   AI 推断: {ai_inference}")
    print(f"   纠正: {correction}")
    print(f"   类型: {correction_type}")
    print(f"   方向: {'回升 +0.05' if positive else '下调 -0.05'}")
    print(f"   当前风格: {profile['style_label']}")
    print(f"   累计记录数: {len(profile['corrections'])}")


def main_quiet(args):
    """从 stdin 读取 JSON 并更新 profile"""
    profile_path = args[0]
    profile = load_profile(profile_path)

    raw = sys.stdin.read()
    data = json.loads(raw)

    profile = _apply_correction(
        profile,
        input_text=data.get("input", ""),
        ai_inference=data.get("ai_inference", ""),
        correction=data.get("correction", ""),
        correction_type=data.get("type"),
        positive=data.get("positive", False),
    )
    save_profile(profile_path, profile)
    print(json.dumps({
        "status": "ok",
        "style_label": profile["style_label"],
        "total_corrections": len(profile["corrections"])
    }))


def main_detect(args):
    """从 stdin 读取 JSON，判断是否是纠正，不修改 profile。

    stdin 需要 JSON:
      {"input": "不是，是 utils.py", "ai_inference": "main.py"}

    输出：
      {"type": "correction", "reason": "starts with否定词"}
      或 {"type": "confirmation", ...}
      或 {"type": "new_command", ...}
    """
    raw = sys.stdin.read()
    data = json.loads(raw)

    user_input = data.get("input", "")
    ai_inference = data.get("ai_inference", "")

    result = is_correction(user_input, ai_inference)
    print(json.dumps({"type": result, "input": user_input, "ai_inference": ai_inference}))


# ── Prune 模式 ────────────────────────────────────────────


def main_prune(args):
    """裁剪 profile 中的 corrections 记录到 MAX_CORRECTIONS 条。"""
    profile_path = args[0]
    profile = load_profile(profile_path)

    before = len(profile.get("corrections", []))
    save_profile(profile_path, profile)  # save 内自带 pruning
    after = len(profile.get("corrections", []))

    print(json.dumps({
        "status": "ok",
        "before": before,
        "after": after,
        "pruned": before - after,
        "limit": MAX_CORRECTIONS,
    }))


# ── 入口 ──────────────────────────────────────────────────


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 update_feedback.py <profile_path> [--quiet | --detect | --prune | --input ...]")
        sys.exit(1)

    if "--detect" in sys.argv:
        main_detect([a for a in sys.argv[1:] if a != "--detect"])
    elif "--prune" in sys.argv:
        main_prune([a for a in sys.argv[1:] if a != "--prune"])
    elif "--quiet" in sys.argv:
        main_quiet([a for a in sys.argv[1:] if a != "--quiet"])
    else:
        main_cli(sys.argv[1:])
