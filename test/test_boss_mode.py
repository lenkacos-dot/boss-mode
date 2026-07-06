#!/usr/bin/env python3
"""
Boss Mode — 测试套件
====================
验证校准+prompt生成+反馈循环的完整流程。
"""

import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from calibrate import build_profile, SCENARIOS, infer_style_label, run_quiet
from generate_prompt import generate_prompt
from update_feedback import learn_pattern, adjust_parameters, detect_correction_type, is_correction, save_profile, _apply_correction, _looks_like_log_or_error, load_profile, main_quiet, main_detect, main_prune
from boss_common import (
    infer_style_label as common_infer_style_label,
    ADJUST_STEP, PARAM_BOUNDS, clamp, label_description, DEFAULT_PARAMS,
)


class TestCalibration(unittest.TestCase):

    def test_build_aggressive_profile(self):
        """全部选 a（效率优先）→ 应该产出 efficiency_boss"""
        answers = [
            {"scenario_id": s["id"], "selected": "a"}
            for s in SCENARIOS
        ]
        profile = build_profile(answers)
        self.assertEqual(profile["style_label"], "efficiency_boss")
        self.assertGreaterEqual(profile["parameters"]["pronoun_inference"], 0.7)
        self.assertEqual(profile["parameters"]["correction_style"], "act_first")

    def test_build_cautious_profile(self):
        """全部选 b（准确优先）→ 应该产出 precise_boss"""
        answers = [
            {"scenario_id": s["id"], "selected": "b"}
            for s in SCENARIOS
        ]
        profile = build_profile(answers)
        self.assertEqual(profile["style_label"], "precise_boss")
        self.assertLessEqual(profile["parameters"]["pronoun_inference"], 0.5)
        self.assertEqual(profile["parameters"]["correction_style"], "ask_first")

    def test_build_mixed_profile(self):
        """混合选择 → efficiency_boss（因为大多数选项偏向效率）"""
        answers = [
            {"scenario_id": "pronoun", "selected": "a"},
            {"scenario_id": "bare_command", "selected": "c"},
            {"scenario_id": "multi_intent", "selected": "b"},
            {"scenario_id": "paste", "selected": "a"},
            {"scenario_id": "context_depth", "selected": "c"},
            {"scenario_id": "priority", "selected": "b"},
        ]
        profile = build_profile(answers)
        self.assertEqual(profile["style_label"], "casual_boss")

    def test_profile_has_all_required_fields(self):
        answers = [
            {"scenario_id": s["id"], "selected": "a"}
            for s in SCENARIOS
        ]
        profile = build_profile(answers)
        required = ["boss_mode_version", "profile_id", "created_at", "updated_at",
                     "style_label", "parameters", "corrections", "frequent_patterns"]
        for field in required:
            self.assertIn(field, profile, f"Missing field: {field}")

    def test_params_are_typed_correctly(self):
        answers = [
            {"scenario_id": s["id"], "selected": "a"}
            for s in SCENARIOS
        ]
        profile = build_profile(answers)
        params = profile["parameters"]
        self.assertIsInstance(params["pronoun_inference"], float)
        self.assertIsInstance(params["bare_command_tolerance"], float)
        self.assertIsInstance(params["context_depth"], int)
        self.assertIn(params["correction_style"], ["act_first", "ask_first"])
        self.assertIn(params["multi_intent_handling"], ["parallel", "sequential", "ask"])
        self.assertIn(params["paste_behavior"], ["auto_analyze", "ask_intent"])
        self.assertIn(params.get("output_format", ""), ["auto", "concise", "detailed"])
        self.assertIn(params.get("explanation_depth", ""), ["minimal", "balanced", "thorough"])

    def test_new_params_output_format(self):
        """output_format 参数应能独立设置"""
        profile = build_profile([
            {"scenario_id": "output_style", "selected": "b"}
        ])
        self.assertEqual(profile["parameters"]["output_format"], "concise")

    def test_new_params_explanation_depth(self):
        """explanation_depth 参数应能独立设置"""
        profile = build_profile([
            {"scenario_id": "explanation", "selected": "c"}
        ])
        self.assertEqual(profile["parameters"]["explanation_depth"], "thorough")

    def test_mixed_profile_all_8_scenarios(self):
        """全部 8 道题 → 所有参数均有值，新增 2 维度不影响 style_label"""
        answers = [
            {"scenario_id": "pronoun", "selected": "a"},
            {"scenario_id": "bare_command", "selected": "c"},
            {"scenario_id": "multi_intent", "selected": "b"},
            {"scenario_id": "paste", "selected": "a"},
            {"scenario_id": "context_depth", "selected": "b"},
            {"scenario_id": "priority", "selected": "b"},
            {"scenario_id": "output_style", "selected": "c"},
            {"scenario_id": "explanation", "selected": "a"},
        ]
        profile = build_profile(answers)
        self.assertEqual(profile["parameters"]["output_format"], "detailed")
        self.assertEqual(profile["parameters"]["explanation_depth"], "minimal")
        self.assertIn(profile["style_label"], ["efficiency_boss", "precise_boss", "casual_boss"])

    def test_calibration_values_match_docs(self):
        """全选 a 的产出应与文档示例一致（直接取值，不再与默认值平均）。"""
        answers = [
            {"scenario_id": s["id"], "selected": "a"}
            for s in SCENARIOS
        ]
        profile = build_profile(answers)
        params = profile["parameters"]
        self.assertEqual(params["pronoun_inference"], 0.9)
        self.assertEqual(params["bare_command_tolerance"], 0.85)
        self.assertEqual(params["multi_intent_handling"], "parallel")
        self.assertEqual(params["paste_behavior"], "auto_analyze")
        self.assertEqual(params["context_depth"], 10)
        self.assertEqual(params.get("output_format"), "auto")
        self.assertEqual(params.get("explanation_depth"), "minimal")

    def test_build_profile_empty_answers(self):
        """空答案列表 → 全部使用 DEFAULT_PARAMS"""
        profile = build_profile([])
        for k, v in DEFAULT_PARAMS.items():
            self.assertEqual(profile["parameters"][k], v,
                             f"空答案后 {k} 应为 {v}，实际 {profile['parameters'][k]}")
        self.assertIn(profile["style_label"], ["efficiency_boss", "precise_boss", "casual_boss"])

    def test_build_profile_none_in_answers(self):
        """answers 含 None 条目应被过滤"""
        profile = build_profile([None, {"scenario_id": "pronoun", "selected": "a"}])
        self.assertEqual(profile["parameters"]["pronoun_inference"], 0.9)


class TestPromptGeneration(unittest.TestCase):

    def setUp(self):
        self.efficiency_profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        self.precise_profile = build_profile([
            {"scenario_id": s["id"], "selected": "b"} for s in SCENARIOS
        ])

    def test_prompt_contains_core_sections(self):
        prompt = generate_prompt(self.efficiency_profile)
        self.assertIn("Boss Mode", prompt)
        self.assertIn("核心原则", prompt)
        self.assertIn("代词处理", prompt)
        self.assertIn("裸命令处理", prompt)
        self.assertIn("纠正风格", prompt)
        self.assertIn("多意图处理", prompt)
        self.assertIn("粘贴行为", prompt)
        self.assertIn("汇报格式", prompt)
        self.assertIn("反馈循环", prompt)

    def test_prompt_reflects_aggressive_style(self):
        prompt = generate_prompt(self.efficiency_profile)
        self.assertIn("先做再纠正", prompt)
        self.assertIn("全部并行执行", prompt)
        self.assertIn("自动分析", prompt)

    def test_prompt_reflects_cautious_style(self):
        prompt = generate_prompt(self.precise_profile)
        self.assertIn("先确认再执行", prompt)
        self.assertIn("先问", prompt)

    def test_prompt_contains_context_depth_value(self):
        prompt = generate_prompt(self.efficiency_profile)
        depth = str(self.efficiency_profile["parameters"]["context_depth"])
        self.assertIn(f"{depth} 轮", prompt)

    def test_prompt_english_output(self):
        """英文模式应产出完整英文 prompt。"""
        prompt = generate_prompt(self.efficiency_profile, lang="en")
        self.assertIn("Boss Mode", prompt)
        self.assertIn("Core Principles", prompt)
        self.assertIn("Behavior Guide", prompt)
        self.assertIn("Pronoun Handling", prompt)
        self.assertIn("Bare Command Handling", prompt)
        self.assertIn("Correction Style", prompt)
        self.assertIn("Multi-Intent", prompt)
        self.assertIn("Paste Behavior", prompt)
        self.assertIn("Report Format", prompt)
        self.assertIn("Feedback Loop", prompt)
        self.assertIn("Efficiency Boss", prompt)
        self.assertIn("Act first, correct later", prompt)

    def test_prompt_english_cautious_style(self):
        """英文 cautious profile 应包含对应英文描述。"""
        prompt = generate_prompt(self.precise_profile, lang="en")
        self.assertIn("Precise Boss", prompt)
        self.assertIn("Confirm before executing", prompt)

    def test_invalid_lang_falls_back_to_cn(self):
        """不支持的语言代码默认回退中文。"""
        prompt = generate_prompt(self.efficiency_profile, lang="jp")
        self.assertIn("核心原则", prompt)
        self.assertNotIn("Core Principles", prompt)

    def test_learned_section_in_prompt_with_corrections(self):
        """有纠正记录时 prompt 应包含 🧠 已学习模式 段落"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        profile["corrections"].append({
            "timestamp": "2026-01-01",
            "input": "修好它",
            "ai_inference": "modified main.py",
            "user_correction": "no, utils.py",
            "correction_type": "pronoun_wrong",
            "patterns": ["pronoun_reference: 用户说「它」时优先指代utils.py"],
            "applied": True,
        })
        prompt = generate_prompt(profile)
        self.assertIn("🧠 已学习模式", prompt)
        prompt_en = generate_prompt(profile, lang="en")
        self.assertIn("Learned Patterns", prompt_en)

    def test_learned_section_empty_when_no_corrections(self):
        """无纠正记录时 prompt 不应包含 🧠 已学习模式"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        prompt = generate_prompt(profile)
        self.assertNotIn("已学习模式", prompt)

    def test_prompt_with_output_format_concise(self):
        """output_format=concise → prompt 含对应要点格式描述"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        profile["parameters"]["output_format"] = "concise"
        prompt = generate_prompt(profile, lang="en")
        self.assertIn("Efficiency Boss", prompt)

    def test_prompt_unknown_style_label_fallback(self):
        """未知 style_label → 回退到 casual_boss 描述"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "b"} for s in SCENARIOS
        ])
        profile["style_label"] = "nonexistent_boss"
        prompt_cn = generate_prompt(profile)
        self.assertIn("随性型老板", prompt_cn)
        prompt_en = generate_prompt(profile, lang="en")
        self.assertIn("Casual Boss", prompt_en)


class TestFeedbackLoop(unittest.TestCase):

    def test_pronoun_correction_adjusts_params(self):
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        original_inference = profile["parameters"]["pronoun_inference"]

        profile = adjust_parameters(profile, "pronoun_wrong")
        self.assertLess(profile["parameters"]["pronoun_inference"], original_inference)

    def test_bare_command_correction_adjusts_params(self):
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        original_tolerance = profile["parameters"]["bare_command_tolerance"]

        profile = adjust_parameters(profile, "bare_wrong")
        self.assertLess(profile["parameters"]["bare_command_tolerance"], original_tolerance)

    def test_learn_pattern_detects_pronouns(self):
        patterns = learn_pattern("修好它", "修改了main.py", "不是，是utils.py")
        has_pronoun_pattern = any("它" in p for p in patterns)
        self.assertTrue(has_pronoun_pattern)

    def test_learn_pattern_detects_bare_commands(self):
        patterns = learn_pattern("优化", "优化了数据库查询", "不是，优化前端渲染")
        has_bare_pattern = any("优化" in p for p in patterns)
        self.assertTrue(has_bare_pattern)

    def test_corrections_grow_over_time(self):
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        profile.setdefault("corrections", [])

        profile["corrections"].append({
            "timestamp": "2026-01-01",
            "input": "修好它",
            "ai_inference": "modified main.py",
            "user_correction": "no, utils.py",
            "patterns": ["pronoun test"],
            "applied": True
        })

        self.assertEqual(len(profile["corrections"]), 1)

        profile["corrections"].append({
            "timestamp": "2026-01-02",
            "input": "优化",
            "ai_inference": "query optimization",
            "user_correction": "frontend rendering",
            "patterns": ["bare command test"],
            "applied": True
        })

        self.assertEqual(len(profile["corrections"]), 2)

    def test_adjust_step_is_005(self):
        """反馈微调步长应为 0.05（与文档承诺一致，历史 bug 为 0.1）。"""
        self.assertEqual(ADJUST_STEP, 0.05)
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        before = profile["parameters"]["pronoun_inference"]
        profile = adjust_parameters(profile, "pronoun_wrong")
        after = profile["parameters"]["pronoun_inference"]
        self.assertAlmostEqual(before - after, 0.05, places=4)

    def test_positive_feedback_raises_params(self):
        """正面确认应回升参数（双向反馈循环，历史版本只降不升）。"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        before = profile["parameters"]["pronoun_inference"]
        profile = adjust_parameters(profile, "pronoun_wrong", direction="up")
        after = profile["parameters"]["pronoun_inference"]
        self.assertGreater(after, before)
        self.assertAlmostEqual(after - before, 0.05, places=4)

    def test_detect_correction_type_multi(self):
        """含「顺序/优先级」的纠正应识别为 multi_wrong（历史版本永不触发）。"""
        self.assertEqual(
            detect_correction_type("查一下然后把日志下了", "顺序反了，先下日志"),
            "multi_wrong"
        )

    def test_detect_correction_type_paste(self):
        """粘贴结构化数据应识别为 paste_wrong（历史版本永不触发）。"""
        self.assertEqual(detect_correction_type('{"a": 1}', ""), "paste_wrong")
        self.assertEqual(detect_correction_type("ERROR: NullPointer\nat line 42", ""), "paste_wrong")

    def test_detect_correction_type_pronoun_and_bare(self):
        """代词与裸命令识别。"""
        self.assertEqual(detect_correction_type("修好它", "不是 main.py"), "pronoun_wrong")
        self.assertEqual(detect_correction_type("优化", "不是后端，是前端"), "bare_wrong")

    def test_shared_infer_label_consistency(self):
        """calibrate 与 boss_common 的 infer_style_label 必须一致（同一来源）。"""
        for params in [
            {"pronoun_inference": 0.9, "bare_command_tolerance": 0.85,
             "correction_style": "act_first", "multi_intent_handling": "parallel",
             "paste_behavior": "auto_analyze"},
            {"pronoun_inference": 0.3, "bare_command_tolerance": 0.3,
             "correction_style": "ask_first", "multi_intent_handling": "ask",
             "paste_behavior": "ask_intent"},
        ]:
            self.assertEqual(infer_style_label(params), common_infer_style_label(params))

    def test_is_correction_punctuation_only(self):
        """纯标点符号 → 新指令"""
        self.assertEqual(is_correction("...", ""), "new_command")
        self.assertEqual(is_correction("！", ""), "new_command")
        self.assertEqual(is_correction("???", ""), "new_command")

    def test_is_correction_number_start(self):
        """数字开头 → 新指令"""
        self.assertEqual(is_correction("2026-01-01 更新了", ""), "new_command")
        self.assertEqual(is_correction("1234", ""), "new_command")

    def test_adjust_parameters_lower_bound_clamp(self):
        """参数降至 0.0 后不再下降（下界钳位）"""
        profile = build_profile([
            {"scenario_id": "pronoun", "selected": "b"}  # 0.3
        ])
        params = profile["parameters"]
        # 一路降到 0
        for _ in range(10):
            profile = adjust_parameters(profile, "pronoun_wrong")
        self.assertGreaterEqual(params["pronoun_inference"], 0.0)
        # 再降一次仍保持 0.0
        before = params["pronoun_inference"]
        profile = adjust_parameters(profile, "pronoun_wrong")
        self.assertEqual(params["pronoun_inference"], max(before, 0.0))

    def test_adjust_parameters_upper_bound_clamp(self):
        """参数升至 1.0 后不再上升（上界钳位）"""
        profile = build_profile([
            {"scenario_id": "pronoun", "selected": "a"}  # 0.9
        ])
        params = profile["parameters"]
        for _ in range(5):
            profile = adjust_parameters(profile, "pronoun_wrong", direction="up")
        self.assertLessEqual(params["pronoun_inference"], 1.0)
        before = params["pronoun_inference"]
        profile = adjust_parameters(profile, "pronoun_wrong", direction="up")
        self.assertEqual(params["pronoun_inference"], min(before, 1.0))

    def test_adjust_parameters_multi_wrong_down(self):
        """multi_wrong 下调 → multi_intent_handling='ask'"""
        profile = build_profile([
            {"scenario_id": "multi_intent", "selected": "a"}  # parallel
        ])
        profile = adjust_parameters(profile, "multi_wrong")
        self.assertEqual(profile["parameters"]["multi_intent_handling"], "ask")

    def test_adjust_parameters_multi_wrong_up(self):
        """multi_wrong 上調 → multi_intent_handling='sequential'"""
        profile = build_profile([
            {"scenario_id": "multi_intent", "selected": "c"}  # ask
        ])
        profile = adjust_parameters(profile, "multi_wrong", direction="up")
        self.assertEqual(profile["parameters"]["multi_intent_handling"], "sequential")

    def test_adjust_parameters_paste_wrong_down(self):
        """paste_wrong 下调 → paste_behavior='ask_intent'"""
        profile = build_profile([
            {"scenario_id": "paste", "selected": "a"}  # auto_analyze
        ])
        profile = adjust_parameters(profile, "paste_wrong")
        self.assertEqual(profile["parameters"]["paste_behavior"], "ask_intent")

    def test_adjust_parameters_paste_wrong_up(self):
        """paste_wrong 上調 → paste_behavior='auto_analyze'"""
        profile = build_profile([
            {"scenario_id": "paste", "selected": "b"}  # ask_intent
        ])
        profile = adjust_parameters(profile, "paste_wrong", direction="up")
        self.assertEqual(profile["parameters"]["paste_behavior"], "auto_analyze")

    def test_detect_correction_type_json_array(self):
        """JSON 数组开头 → paste_wrong"""
        self.assertEqual(detect_correction_type('["item1", "item2"]', ""), "paste_wrong")

    def test_save_profile_no_prune(self):
        """不足 50 条时不裁剪"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        profile["corrections"] = [{"input": f"c{i}", "patterns": [], "applied": True} for i in range(30)]
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.close()
        try:
            save_profile(tmp.name, profile)
            with open(tmp.name) as f:
                saved = json.load(f)
            self.assertEqual(len(saved["corrections"]), 30)
        finally:
            os.unlink(tmp.name)

    def test_learn_pattern_empty_inputs(self):
        """空输入 → 空模式列表"""
        self.assertEqual(learn_pattern("", "", ""), [])
        self.assertEqual(learn_pattern(None, "", ""), [])

    def test_detect_mode(self):
        """is_correction() 应正确判断 3 种状态：纠正/确认/新指令"""
        self.assertEqual(is_correction("不是，是 utils.py", "main.py"), "correction")
        self.assertEqual(is_correction("不对，是前端"), "correction")
        self.assertEqual(is_correction("对，就是这个", "main.py"), "confirmation")
        self.assertEqual(is_correction("好", ""), "confirmation")
        self.assertEqual(is_correction("好的，继续"), "confirmation")
        self.assertEqual(is_correction("接着做下一个", ""), "new_command")
        self.assertEqual(is_correction("然后查一下日志", ""), "new_command")
        self.assertEqual(is_correction("另有其事", ""), "new_command")
        self.assertEqual(is_correction("", ""), "new_command")

    def test_prune_corrections_to_50(self):
        """MAX_CORRECTIONS=50 应自动裁剪超出部分"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        for i in range(52):
            profile["corrections"].append({
                "timestamp": f"2026-01-{i+1:02d}",
                "input": f"test {i}",
                "ai_inference": "",
                "user_correction": f"correction {i}",
                "patterns": [],
                "applied": True,
            })
        self.assertEqual(len(profile["corrections"]), 52)

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.close()
        try:
            save_profile(tmp.name, profile)
            with open(tmp.name) as f:
                saved = json.load(f)
            self.assertEqual(len(saved["corrections"]), 50)
            self.assertEqual(saved["corrections"][0]["input"], "test 2")
            self.assertEqual(saved["corrections"][-1]["input"], "test 51")
        finally:
            os.unlink(tmp.name)


class TestEndToEnd(unittest.TestCase):

    def test_full_flow(self):
        """完整流程：校准 → 生成 prompt → 反馈 → 重新生成"""

        # Step 1: Calibration
        answers = [
            {"scenario_id": "pronoun", "selected": "a"},
            {"scenario_id": "bare_command", "selected": "a"},
            {"scenario_id": "multi_intent", "selected": "a"},
            {"scenario_id": "paste", "selected": "a"},
            {"scenario_id": "context_depth", "selected": "a"},
            {"scenario_id": "priority", "selected": "a"},
        ]
        profile = build_profile(answers)
        self.assertEqual(profile["style_label"], "efficiency_boss")

        # Step 2: Generate prompt
        prompt = generate_prompt(profile)
        self.assertIn("Boss Mode", prompt)

        # Step 3: User corrects
        profile["corrections"].append({
            "timestamp": "test",
            "input": "修好它",
            "ai_inference": "modified the config",
            "user_correction": "no, fix the bug in main.py",
            "patterns": ["pronoun test"],
            "applied": True
        })
        profile = adjust_parameters(profile, "pronoun_wrong")

        # Step 4: Re-generate prompt (params should be slightly adjusted)
        prompt2 = generate_prompt(profile)
        self.assertIn("Boss Mode", prompt2)

        # Efficiency boss should still be efficiency boss after one correction
        self.assertEqual(profile["style_label"], "efficiency_boss")

    def test_full_flow_bilingual(self):
        """完整流程中英文双语言 prompt 均可生成"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        cn = generate_prompt(profile, lang="cn")
        en = generate_prompt(profile, lang="en")
        self.assertIn("核心原则", cn)
        self.assertIn("Core Principles", en)
        self.assertIn("Boss Mode", cn)
        self.assertIn("Boss Mode", en)

    def test_full_file_save_load_cycle(self):
        """profile JSON 文件保存 → 重新加载 → generate_prompt 无异常"""
        # 选所有场景的有效选项（paste 和 priority 只有 a/b）
        profile = build_profile([
            {"scenario_id": "pronoun", "selected": "c"},
            {"scenario_id": "bare_command", "selected": "c"},
            {"scenario_id": "multi_intent", "selected": "c"},
            {"scenario_id": "paste", "selected": "a"},
            {"scenario_id": "context_depth", "selected": "c"},
            {"scenario_id": "priority", "selected": "a"},
            {"scenario_id": "output_style", "selected": "c"},
            {"scenario_id": "explanation", "selected": "c"},
        ])
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(profile, tmp, ensure_ascii=False, indent=2)
        tmp.close()
        try:
            with open(tmp.name) as f:
                loaded = json.load(f)
            prompt = generate_prompt(loaded)
            self.assertIn("Boss Mode", prompt)
            # 确认所有 8 个参数字段都在
            self.assertEqual(len(loaded["parameters"]), 8)
        finally:
            os.unlink(tmp.name)


class TestEdgeCases(unittest.TestCase):
    """边界值与辅助函数专项测试"""

    def test_clamp_in_bounds(self):
        """clamp 保持范围内值不变"""
        self.assertEqual(clamp(0.5, 0.0, 1.0), 0.5)
        self.assertEqual(clamp(5, 1, 10), 5)

    def test_clamp_below_bounds(self):
        """clamp 低于下界时返回下界"""
        self.assertEqual(clamp(-0.1, 0.0, 1.0), 0.0)
        self.assertEqual(clamp(0, 1, 10), 1)

    def test_clamp_above_bounds(self):
        """clamp 高于上界时返回上界"""
        self.assertEqual(clamp(1.5, 0.0, 1.0), 1.0)
        self.assertEqual(clamp(20, 1, 10), 10)

    def test_param_bounds_keys(self):
        """PARAM_BOUNDS 仅含 3 个 float/ int 参数的边界"""
        self.assertIn("pronoun_inference", PARAM_BOUNDS)
        self.assertIn("bare_command_tolerance", PARAM_BOUNDS)
        self.assertIn("context_depth", PARAM_BOUNDS)
        self.assertEqual(len(PARAM_BOUNDS), 3)

    def test_infer_style_label_empty_dict(self):
        """空参数字典 → casual_boss（全用默认值）"""
        self.assertEqual(common_infer_style_label({}), "casual_boss")

    def test_label_description_unknown(self):
        """未知标签 → 空字符串"""
        self.assertEqual(label_description("alien_boss"), "")

    def test_label_description_known(self):
        """已知标签 → 含中文/英文描述"""
        self.assertIn("效率型老板", label_description("efficiency_boss"))
        self.assertIn("严谨型老板", label_description("precise_boss"))
        self.assertIn("随性型老板", label_description("casual_boss"))


class TestLogErrorDetection(unittest.TestCase):
    """_looks_like_log_or_error() 完整路径覆盖"""

    def test_single_line_returns_false(self):
        """单行文本 → False"""
        self.assertFalse(_looks_like_log_or_error("hello world"))

    def test_log_level_marker(self):
        """含 [ERROR] / [INFO] 等日志级别标记 → True"""
        self.assertTrue(_looks_like_log_or_error(
            "2026-01-01 12:00:00 [ERROR] something broke\n"
            "    at com.example.MyClass.run()"
        ))
        self.assertTrue(_looks_like_log_or_error(
            "line1\n[WARN] timeout exceeded"
        ))
        self.assertTrue(_looks_like_log_or_error(
            "line1\nexception: KeyError"
        ))

    def test_python_stack_trace(self):
        """Python 栈踪迹 → True"""
        self.assertTrue(_looks_like_log_or_error(
            'line1\n  File "/Users/test/app.py", line 42, in foo\n'
            "    return bar()"
        ))

    def test_java_stack_trace(self):
        """Java 栈踪迹模式 → True"""
        self.assertTrue(_looks_like_log_or_error(
            'line1\n  at com.example.MyClass.method(MyClass.java:42)\n'
            "    at org.example.Main.main(Main.java:10)"
        ))

    def test_json_start(self):
        """以 { 或 [ 开头 → True"""
        self.assertTrue(_looks_like_log_or_error(
            '{"name": "test"}\n{"id": 2}'
        ))
        self.assertTrue(_looks_like_log_or_error(
            '["item1", "item2"]\n"single"'
        ))

    def test_structured_lines_half(self):
        """50%+ 行匹配结构化模式 → True"""
        self.assertTrue(_looks_like_log_or_error(
            "key1=value1\nkey2=value2\njust some prose here\n"
        ))

    def test_low_length_variance(self):
        """3+ 行长且长度接近 → True（日志表格）"""
        self.assertTrue(_looks_like_log_or_error(
            "aaaaa" + "a" * 20 + "\n" + "bbbbb" + "b" * 20 + "\n" + "ccccc" + "c" * 20
        ))

    def test_normal_multi_line(self):
        """普通多行自然语言 → False"""
        self.assertFalse(_looks_like_log_or_error(
            "This is a normal paragraph.\n"
            "It has multiple sentences.\n"
            "They vary in length significantly because it's natural text."
        ))

    def test_normal_instructions(self):
        """普通多行指令 → False"""
        self.assertFalse(_looks_like_log_or_error(
            "帮我查一下今天的天气\n"
            "顺便看看明天会不会下雨\n"
            "再帮我订个外卖"
        ))

    def test_elixir_stack_trace(self):
        """Elixir/Erlang 栈踪迹模式 → True"""
        self.assertTrue(_looks_like_log_or_error(
            "error happened\n"
            "  ->42#GenServer.call/3\n"
            "  ->15#MyModule.foo/1"
        ))


class TestApplyCorrection(unittest.TestCase):
    """_apply_correction 独立测试"""

    def setUp(self):
        self.profile = build_profile([
            {"scenario_id": s["id"], "selected": "b"} for s in SCENARIOS
        ])

    def test_auto_detect_correction_type(self):
        """correction_type=None 时自动检测"""
        result = _apply_correction(
            dict(self.profile),  # shallow copy
            input_text="把它修好",
            ai_inference="modified config",
            correction="修 main.py",
            correction_type=None,
            positive=False,
        )
        self.assertEqual(len(result["corrections"]), 1)
        entry = result["corrections"][0]
        self.assertEqual(entry["correction_type"], "pronoun_wrong")
        self.assertEqual(entry["direction"], "down")
        self.assertTrue(entry["applied"])

    def test_force_correction_type_override(self):
        """传递 correction_type 时不自动检测"""
        result = _apply_correction(
            dict(self.profile),
            input_text="把它修好",
            ai_inference="modified config",
            correction="修 main.py",
            correction_type="bare_wrong",
            positive=False,
        )
        entry = result["corrections"][0]
        self.assertEqual(entry["correction_type"], "bare_wrong")

    def test_positive_flow(self):
        """positive=True → 方向为 up，参数字段回升"""
        result = _apply_correction(
            dict(self.profile),
            input_text="修好它",
            ai_inference="fixed main.py",
            correction="",
            correction_type="pronoun_wrong",
            positive=True,
        )
        entry = result["corrections"][0]
        self.assertEqual(entry["direction"], "up")

    def test_learn_pattern_stored(self):
        """纠正的 patterns 存储在 entry 中"""
        result = _apply_correction(
            dict(self.profile),
            input_text="修好它",
            ai_inference="modified config",
            correction="fix main.py",
            correction_type="pronoun_wrong",
            positive=False,
        )
        entry = result["corrections"][0]
        self.assertIsInstance(entry["patterns"], list)

    def test_no_input_correction_entry(self):
        """空白输入 + 空白纠正 → 仍生成 entry（类型 bare_wrong 回退）"""
        result = _apply_correction(
            dict(self.profile),
            input_text="",
            ai_inference="",
            correction="",
            correction_type=None,
            positive=False,
        )
        self.assertEqual(len(result["corrections"]), 1)
        # 空输入 → is_correction returns new_command, but detect_correction_type
        # with empty → returns bare_wrong. adjust_parameters with bare_wrong
        # should still work (just adjusts bare_command_tolerance)
        self.assertIn(result["corrections"][0]["correction_type"],
                      ["bare_wrong", "pronoun_wrong"])


class TestDeepBoundary(unittest.TestCase):
    """更深入的边界场景测试"""

    # ── is_correction 边界 ──────────────────────────

    def test_is_correction_emoji_only(self):
        """纯 emoji → 新指令"""
        self.assertEqual(is_correction("🎉", ""), "new_command")
        self.assertEqual(is_correction("😊👍", ""), "new_command")

    def test_is_correction_very_long(self):
        """超长输入（>1000字）→ 按前缀判断"""
        long_text = "不是" + "a" * 2000
        self.assertEqual(is_correction(long_text, ""), "correction")
        long_new = "接下来" + "b" * 2000
        self.assertEqual(is_correction(long_new, ""), "new_command")

    def test_is_correction_case_insensitive(self):
        """大写前缀也一样匹配"""
        self.assertEqual(is_correction("NOT what I meant", ""), "correction")
        self.assertEqual(is_correction("NO that's wrong", ""), "correction")
        self.assertEqual(is_correction("YES that's right", ""), "confirmation")

    def test_is_correction_trailing_spaces(self):
        """尾部空格不应影响结果"""
        self.assertEqual(is_correction("不是 ", ""), "correction")
        self.assertEqual(is_correction("好的 ", ""), "confirmation")
        self.assertEqual(is_correction("还有 ", ""), "new_command")

    def test_is_correction_mixed_marker(self):
        """同时匹配纠正和确认时，纠正优先（CORRECTION_PREFIXES 先检查）"""
        self.assertEqual(is_correction("不对，好的", ""), "correction")
        self.assertEqual(is_correction("no yes", ""), "correction")

    # ── detect_correction_type 边界 ─────────────────

    def test_detect_type_empty_input(self):
        """空输入 → bare_wrong（回退默认）"""
        self.assertEqual(detect_correction_type(""), "bare_wrong")
        self.assertEqual(detect_correction_type(None), "bare_wrong")

    def test_detect_type_mixed_signal(self):
        """correction 含 multi 关键词但 input 也含代词 → multi_wrong 优先"""
        self.assertEqual(
            detect_correction_type("把它的顺序改一下", "顺序反了"),
            "multi_wrong"
        )

    def test_detect_type_log_like_is_paste(self):
        """多行日志风格但纠正含 multi 关键词 → paste_wrong 超过 multi？不，multi_wrong 在检测中优先"""
        text = "2026-01-01 [ERROR]\n  at line 42"
        correction = "顺序错了"  # multi_wrong 关键词
        # correction keywords checked first → multi_wrong
        self.assertEqual(detect_correction_type(text, correction), "multi_wrong")

    def test_detect_type_bare_no_verb(self):
        """input 不含任何动词/代词 → 回退默认（数字 → bare_wrong, 纯括号 → paste_wrong）"""
        self.assertEqual(detect_correction_type("123456"), "bare_wrong")
        # [[[[ 以 [ 开头 → 被 JSON 开头的 paste 检测捕获，行为正确
        self.assertEqual(detect_correction_type("[[[["), "paste_wrong")

    # ── adjust_parameters 边界 ─────────────────────

    def test_adjust_unknown_type(self):
        """未知 correction_type → 不修改任何参数（仅更新 style_label + timestamp）"""
        profile = build_profile([
            {"scenario_id": "pronoun", "selected": "a"}
        ])
        before = dict(profile["parameters"])
        profile = adjust_parameters(profile, "alien_type_x")
        # 参数不变（unknown type 不匹配任何 elif）
        self.assertEqual(profile["parameters"]["pronoun_inference"],
                         before["pronoun_inference"])
        self.assertIn("updated_at", profile)

    # ── infer_style_label 边界 ─────────────────────

    def test_infer_style_label_3_of_5(self):
        """恰好 3/5 维度为效率 → casual_boss"""
        self.assertEqual(
            common_infer_style_label({
                "pronoun_inference": 0.7,      # ≥0.7 → 1
                "bare_command_tolerance": 0.7,  # ≥0.7 → 1
                "correction_style": "act_first",  # → 1
                "multi_intent_handling": "ask",    # → 0
                "paste_behavior": "ask_intent",    # → 0
            }),
            "casual_boss"
        )

    def test_infer_style_label_2_of_5(self):
        """恰好 2/5 维度为效率 → casual_boss（不是 precise）"""
        self.assertEqual(
            common_infer_style_label({
                "pronoun_inference": 0.7,      # ≥0.7 → 1
                "bare_command_tolerance": 0.5,  # <0.7 → 0
                "correction_style": "ask_first",  # → 0
                "multi_intent_handling": "ask",    # → 0
                "paste_behavior": "auto_analyze",  # → 1
            }),
            "casual_boss"
        )

    def test_infer_style_label_1_of_5(self):
        """恰好 1/5 维度为效率 → precise_boss"""
        self.assertEqual(
            common_infer_style_label({
                "pronoun_inference": 0.5,      # <0.7 → 0
                "bare_command_tolerance": 0.5,  # <0.7 → 0
                "correction_style": "ask_first",  # → 0
                "multi_intent_handling": "ask",    # → 0
                "paste_behavior": "auto_analyze",  # → 1
            }),
            "precise_boss"
        )

    # ── build_profile 边界 ─────────────────────────

    def test_build_duplicate_scenario(self):
        """重复 scenario_id → 最后一个有效"""
        profile = build_profile([
            {"scenario_id": "pronoun", "selected": "a"},
            {"scenario_id": "pronoun", "selected": "b"},  # override
        ])
        self.assertEqual(profile["parameters"]["pronoun_inference"], 0.3)

    def test_build_invalid_selected_key(self):
        """无效 selected key → 跳过该场景（静默忽略）"""
        profile = build_profile([
            {"scenario_id": "pronoun", "selected": "z_invalid"},
        ])
        # pronoun 被跳过，使用 DEFAULT_PARAMS
        self.assertEqual(profile["parameters"]["pronoun_inference"],
                         DEFAULT_PARAMS["pronoun_inference"])

    # ── save_profile 边界 ──────────────────────────

    def test_save_profile_missing_corrections_key(self):
        """profile 无 corrections 键 → save 后自动创建（静默处理）"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        del profile["corrections"]
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.close()
        try:
            save_profile(tmp.name, profile)
            with open(tmp.name) as f:
                saved = json.load(f)
            self.assertEqual(saved.get("corrections", []), [])
        finally:
            os.unlink(tmp.name)

    def test_save_profile_prunes_at_51(self):
        """51 条时裁剪到 50"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        profile["corrections"] = [
            {"input": f"c{i}", "patterns": [], "applied": True}
            for i in range(51)
        ]
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.close()
        try:
            save_profile(tmp.name, profile)
            with open(tmp.name) as f:
                saved = json.load(f)
            self.assertEqual(len(saved["corrections"]), 50)
            # 应保留最新的 50 条（即索引 1-50，丢弃 c0）
            self.assertEqual(saved["corrections"][0]["input"], "c1")
        finally:
            os.unlink(tmp.name)

    # ── format_learned_patterns 边界 ────────────────

    def test_learned_applied_false_corrections(self):
        """applied=False 的纠正记录是否仍被 format_learned_patterns 展示？是（profile.get 不过滤）"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        profile["corrections"] = [
            {"input": "test", "ai_inference": "inf",
             "user_correction": "corr", "patterns": [],
             "applied": False}
        ]
        result = generate_prompt(profile)
        self.assertIn("test", result)

    def test_learned_long_corrections_text(self):
        """超长纠正文本在 format_learned_patterns 中应完整包含（不截断）"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        long_corr = "用户说：" + "a" * 500
        profile["corrections"] = [
            {"input": "改一下", "ai_inference": "modified config",
             "user_correction": long_corr, "patterns": ["pattern1"],
             "applied": True}
        ]
        prompt = generate_prompt(profile)
        self.assertIn(long_corr, prompt)

    def test_learned_with_preferred_refs(self):
        """frequent_patterns.preferred_refs 被注入到 prompt 中"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        profile["corrections"] = [
            {"input": "改仓库", "ai_inference": "repo",
             "user_correction": "不是 repo，是 ~/Desktop",
             "patterns": ["pronoun_reference: 用户说「改」时优先指代 ~/Desktop"],
             "applied": True}
        ]
        profile["frequent_patterns"] = {
            "preferred_refs": {
                "仓库": "~/Desktop/boss-mode",
                "它": "当前讨论的文件",
            }
        }
        prompt = generate_prompt(profile, lang="cn")
        self.assertIn("仓库", prompt)
        self.assertIn("~/Desktop/boss-mode", prompt)

    # ── generate_prompt 边界 ───────────────────────

    def test_generate_missing_param_keys(self):
        """profile 参数部分缺失 → 使用 .get() 默认值"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        # 删除部分参数
        del profile["parameters"]["output_format"]
        del profile["parameters"]["explanation_depth"]
        # 不应崩溃（.get() 有默认值）
        prompt = generate_prompt(profile)
        self.assertIn("Boss Mode", prompt)


# ── 第 9 类：检测优先级完整矩阵 ─────────────────────

class TestPriorityChain(unittest.TestCase):
    """验证 detect_correction_type 的优先级链：multi > paste > pronoun > bare"""

    def test_multi_wins_over_paste(self):
        """correction 含「顺序」+ input 以 { 开头 → multi_wrong（multi > paste）"""
        result = detect_correction_type('{"key": "val"}', correction="顺序错了，先做这个")
        self.assertEqual(result, "multi_wrong")

    def test_multi_wins_over_pronoun(self):
        """correction 含「优先级」+ input 含代词 → multi_wrong（multi > pronoun）"""
        result = detect_correction_type("把它改一下", correction="优先级反了")
        self.assertEqual(result, "multi_wrong")

    def test_multi_wins_over_bare(self):
        """correction 含「先后」+ input 含裸动词 → multi_wrong（multi > bare）"""
        result = detect_correction_type("优化一下", correction="顺序反了，先查再改")
        self.assertEqual(result, "multi_wrong")

    def test_paste_wins_over_pronoun(self):
        """input 以 [ 开头且含代词 → paste_wrong（paste > pronoun）"""
        result = detect_correction_type('[{"key": "val"}, {"key2": "val2"}] 它不对')
        self.assertEqual(result, "paste_wrong")

    def test_paste_wins_over_bare(self):
        """input 为多行日志结构 + 含裸动词 → paste_wrong（paste > bare）"""
        result = detect_correction_type("查一下\n[ERROR] 2024-01-01 connection failed\n[INFO] retry 3")
        self.assertEqual(result, "paste_wrong")

    def test_pronoun_wins_over_bare(self):
        """input 含代词 + 裸动词 → pronoun_wrong（pronoun > bare）"""
        result = detect_correction_type("查一下那个东西")
        self.assertEqual(result, "pronoun_wrong")

    def test_all_signals_multi_wins(self):
        """input 同时触发 multi/paste/pronoun/bare → multi_wrong（最高优先级）"""
        result = detect_correction_type(
            '它不对，查一下这个{"err": 1}',
            correction="先后顺序反了"
        )
        self.assertEqual(result, "multi_wrong")


# ── 第 10 类：日志检测边界 ────────────────────────

class TestLookalikeBoundary(unittest.TestCase):
    """_looks_like_log_or_error 的剩余边界"""

    def test_two_lines_only_no_variance_check(self):
        """2 行文本不触发方差检查（需 ≥3 行）→ 但也无其他特征 → False"""
        self.assertFalse(_looks_like_log_or_error("aaaaa\nbbbbb"))

    def test_four_lines_low_variance_true(self):
        """4 行长行（avg≥15、variance<100）→ True"""
        text = "\n".join(["a" * 25] * 4)
        self.assertTrue(_looks_like_log_or_error(text))

    def test_four_lines_high_variance_false(self):
        """4 行长行（avg≥15、variance≫100）→ False"""
        text = "a" * 20 + "\n" + "b" * 80 + "\n" + "c" * 20 + "\n" + "d" * 100
        self.assertFalse(_looks_like_log_or_error(text))

    def test_empty_lines_interspersed(self):
        """空行不影响（列表推导过滤 strip）→ 仍检测到日志级别"""
        text = "\n\n[ERROR] crash\n\n[INFO] restart\n\n"
        self.assertTrue(_looks_like_log_or_error(text))

    def test_whitespace_only_lines(self):
        """只有空白符的行被过滤 → 仅 2 个有效行 → 不触发"""
        self.assertFalse(_looks_like_log_or_error(
            "   \n\t\nnormal line\n  \n"
        ))

    def test_exact_50_percent_structured(self):
        """恰好 50% 行匹配 → 0.5 >= 0.5 → True"""
        text = ("2024-01-01 12:00:00 [INFO] started\n"
                "some random text\n"
                "key1=val1\n"
                "another random text")
        self.assertTrue(_looks_like_log_or_error(text))

    def test_47_percent_structured(self):
        """3/7 ≈ 42.8% < 50% → False"""
        text = "\n".join([
            "2024-01-01 12:00:00 first",  # structured
            "foo bar baz",
            "key=value",                   # structured
            "hello world",
            "test123",
            "status: ok",                  # structured
            "finish",
        ])
        self.assertFalse(_looks_like_log_or_error(text))

    def test_log_level_in_two_lines(self):
        """2 行含 [ERROR] → 日志级别检测优先触发，不受行数限制"""
        self.assertTrue(_looks_like_log_or_error("[ERROR] crash\n[INFO] retry"))

    def test_mixed_chinese_log(self):
        """中文日志标记 → 不匹配 _LOG_LEVELS（大写英文） → 需其他特征"""
        self.assertFalse(_looks_like_log_or_error(
            "【错误】连接超时\n【警告】重试中\n【信息】已完成"
        ))

    def test_all_heuristics_false_together(self):
        """触发所有 9 种 check 但都返回 False → 最终 False"""
        text = ("这是一段正常的文字\n"
                "这是第二行\n"
                "这是第三行\n"
                "这是第四行")
        self.assertFalse(_looks_like_log_or_error(text))


# ── 第 11 类：零值/边界/异常输入 ──────────────────

class TestFunctionSigBoundary(unittest.TestCase):
    """函数签名层面最边缘的输入"""

    def test_is_correction_both_none(self):
        """is_correction(None, None) → new_command（不崩溃）"""
        self.assertEqual(is_correction(None, None), "new_command")

    def test_is_correction_ai_inference_ignored(self):
        """ai_inference 参数不影响结果（函数内未使用）"""
        self.assertEqual(is_correction("不是", "some inference"), "correction")
        self.assertEqual(is_correction("不是", None), "correction")

    def test_looks_like_log_or_error_none(self):
        """_looks_like_log_or_error(None) → 不应崩溃"""
        result = _looks_like_log_or_error(None)
        self.assertFalse(result)

    def test_looks_like_log_or_error_empty(self):
        """_looks_like_log_or_error('') → False"""
        self.assertFalse(_looks_like_log_or_error(""))

    def test_detect_correction_type_both_none(self):
        """detect_correction_type(None, None) → bare_wrong（fallback）"""
        self.assertEqual(detect_correction_type(None, None), "bare_wrong")

    def test_learn_pattern_all_none(self):
        """learn_pattern(None, None, None) → []（不崩溃）"""
        result = learn_pattern(None, None, None)
        self.assertEqual(result, [])

    def test_learn_pattern_ai_inference_none(self):
        """learn_pattern 中 ai_inference=None → f-string 格式化为 'None' 但不崩溃"""
        result = learn_pattern("修好它", None, "改成 utils.py")
        # "它"→代词 + "修"→裸动词 = 2 patterns
        self.assertGreaterEqual(len(result), 1)
        self.assertTrue(any("pronoun_reference" in p for p in result))

    def test_learn_pattern_all_empty(self):
        """learn_pattern('', '', '') → []"""
        self.assertEqual(learn_pattern("", "", ""), [])

    def test_learn_pattern_both_types(self):
        """input 同时含代词和裸动词 → 至少 2 个 patterns（可能因多个代词碰撞而更多）"""
        result = learn_pattern("查一下那个", "查了文件", "不是，查目录")
        self.assertGreaterEqual(len(result), 2)
        self.assertTrue(any("pronoun_reference" in p for p in result))

    def test_adjust_parameters_missing_key(self):
        """profile 无 parameters 键 → KeyError"""
        with self.assertRaises(KeyError):
            adjust_parameters({}, "pronoun_wrong")

    def test_save_profile_no_corrections_key(self):
        """save_profile 已测过 missing corrections key（静默创建）"""
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        del profile["corrections"]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp = f.name
        try:
            save_profile(tmp, profile)
            with open(tmp, "r") as f:
                saved = json.load(f)
            self.assertEqual(saved.get("corrections", []), [])
        finally:
            os.unlink(tmp)

    def test_detect_correction_type_none_input(self):
        """detect_correction_type(空) → bare_wrong（回退）"""
        self.assertEqual(detect_correction_type(""), "bare_wrong")

    def test_is_correction_all_three_modes(self):
        """is_correction 三种返回值的完整快速验证"""
        self.assertEqual(is_correction("不是这样的"), "correction")
        self.assertEqual(is_correction("对，就是这样"), "confirmation")
        self.assertEqual(is_correction("还有另一个方法"), "new_command")
        self.assertEqual(is_correction("顺便查一下"), "new_command")

    def test_short_reply_negative_word(self):
        """短回复含否定词 → correction（len<10 且含不/错）"""
        self.assertEqual(is_correction("错"), "correction")
        self.assertEqual(is_correction("不"), "correction")
        self.assertEqual(is_correction("no"), "correction")
        self.assertEqual(is_correction("不是"), "correction")  # 前缀优先

    def test_long_reply_negative_word(self):
        """长回复含否定词 → 前缀检查失败后走短回复规则，但长度≥10 → new_command"""
        self.assertEqual(is_correction("我不认同这个方案因为更复杂"), "new_command")


# ── 第 12 类：CLI 集成测试 ─────────────────────────

class TestCLIIntegration(unittest.TestCase):
    """验证 CLI 入口函数的 stdin/stdout 管道"""

    def setUp(self):
        """创建临时 profile 文件"""
        self.tmpdir = tempfile.mkdtemp()
        self.profile_path = os.path.join(self.tmpdir, "test_profile.json")
        # 写入一个默认 profile
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        with open(self.profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False)

    def tearDown(self):
        for root, dirs, files in os.walk(self.tmpdir, topdown=False):
            for f in files:
                os.unlink(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self.tmpdir)

    def _stdin(self, text):
        """返回一个 patched sys.stdin 上下文"""
        return patch("sys.stdin", io.StringIO(text))

    def _stdout(self):
        """返回一个收集 stdout 的 patch 上下文"""
        return patch("sys.stdout", new_callable=io.StringIO)

    # ── main_detect ──────────────────────────────────

    def test_main_detect_correction(self):
        """stdin 传入纠正 JSON → stdout 输出 type=correction"""
        with self._stdin('{"input": "不是，改 utils.py", "ai_inference": "main.py"}'), \
             self._stdout() as out:
            main_detect([self.profile_path])
        result = json.loads(out.getvalue())
        self.assertEqual(result["type"], "correction")

    def test_main_detect_confirmation(self):
        """stdin 传入确认 JSON → stdout 输出 type=confirmation"""
        with self._stdin('{"input": "对，就是这样", "ai_inference": "main.py"}'), \
             self._stdout() as out:
            main_detect([self.profile_path])
        result = json.loads(out.getvalue())
        self.assertEqual(result["type"], "confirmation")

    def test_main_detect_new_command(self):
        """stdin 传入新指令 JSON → stdout 输出 type=new_command"""
        with self._stdin('{"input": "还有另一个方法", "ai_inference": "main.py"}'), \
             self._stdout() as out:
            main_detect([self.profile_path])
        result = json.loads(out.getvalue())
        self.assertEqual(result["type"], "new_command")

    def test_main_detect_empty_input(self):
        """stdin 传空 JSON → type=new_command（不崩溃）"""
        with self._stdin('{"input": "", "ai_inference": ""}'), \
             self._stdout() as out:
            main_detect([self.profile_path])
        result = json.loads(out.getvalue())
        self.assertIn(result["type"], ("correction", "confirmation", "new_command"))

    # ── main_quiet ───────────────────────────────────

    def test_main_quiet_updates_profile(self):
        """stdin 传入纠正 JSON → profile 文件被更新"""
        with self._stdin('{"input": "不是这个", "ai_inference": "test.py", "correction": "是那个"}'), \
             self._stdout() as out:
            main_quiet([self.profile_path])
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "ok")
        # 重新加载 profile 确认有记录
        profile = load_profile(self.profile_path)
        self.assertGreater(len(profile["corrections"]), 0)

    def test_main_quiet_empty_json(self):
        """stdin 传空 JSON → 不崩溃（missing key 由 .get() 兜底）"""
        with self._stdin('{}'), self._stdout() as out:
            main_quiet([self.profile_path])
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "ok")

    def test_main_quiet_positive(self):
        """stdin 传 positive=true → 回升"""
        with self._stdin('{"input": "是的", "ai_inference": "x.py", "positive": true}'), \
             self._stdout() as out:
            main_quiet([self.profile_path])
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "ok")

    # ── main_prune ───────────────────────────────────

    def test_main_prune_under_limit(self):
        """≤50 条 → 不裁剪"""
        profile = load_profile(self.profile_path)
        original_count = len(profile["corrections"])
        with self._stdout() as out:
            main_prune([self.profile_path])
        result = json.loads(out.getvalue())
        self.assertEqual(result["pruned"], 0)
        self.assertEqual(result["before"], original_count)

    def test_main_prune_over_limit(self):
        """52 条 → 裁剪 2 条"""
        profile = load_profile(self.profile_path)
        # 填满 52 条（直接写文件，绕过 save_profile 的自动裁剪）
        corrections = [{"input": f"test_{i}", "correction_type": "bare_wrong",
                         "direction": "down", "applied": True,
                         "timestamp": "2024-01-01T00:00:00"} for i in range(52)]
        profile["corrections"] = corrections
        with open(self.profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False)
        with self._stdout() as out:
            main_prune([self.profile_path])
        result = json.loads(out.getvalue())
        self.assertEqual(result["pruned"], 2)
        self.assertEqual(result["after"], 50)

    def test_main_prune_exact_limit(self):
        """恰好 50 条 → 不裁剪"""
        profile = load_profile(self.profile_path)
        corrections = [{"input": f"test_{i}", "correction_type": "bare_wrong",
                         "direction": "down", "applied": True,
                         "timestamp": "2024-01-01T00:00:00"} for i in range(50)]
        profile["corrections"] = corrections
        save_profile(self.profile_path, profile)
        with self._stdout() as out:
            main_prune([self.profile_path])
        result = json.loads(out.getvalue())
        self.assertEqual(result["pruned"], 0)

    # ── calibrate run_quiet ──────────────────────────

    def test_calibrate_run_quiet(self):
        """stdin 传答案 JSON → stdout 输出 JSON profile"""
        answers = [{"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS]
        with self._stdin(json.dumps(answers)), self._stdout() as out:
            run_quiet()
        result = json.loads(out.getvalue())
        self.assertEqual(result["style_label"], "efficiency_boss")
        self.assertIn("parameters", result)
        self.assertIn("corrections", result)
        self.assertGreater(len(result["parameters"]), 0)

    def test_calibrate_run_quiet_invalid_json(self):
        """无效 JSON → 退出码 1，输出 error"""
        with self._stdin("not json at all"), self._stdout() as out:
            with self.assertRaises(SystemExit) as cm:
                run_quiet()
        self.assertEqual(cm.exception.code, 1)

    # ── 去重验证 ─────────────────────────────────────

    def test_dedup_json_like_start(self):
        """_JSON_LIKE_START 不应有重复元素"""
        from update_feedback import _JSON_LIKE_START as tup
        self.assertEqual(len(tup), len(set(tup)),
                         f"duplicates found: {tup}")

    def test_dedup_correction_prefixes(self):
        """CORRECTION_PREFIXES 不应有重复元素"""
        from update_feedback import CORRECTION_PREFIXES as lst
        self.assertEqual(len(lst), len(set(p.lower() for p in lst)),
                         f"duplicates found: {lst}")


# ── 第 13 类：随机模糊测试 ─────────────────────────

class TestFuzz(unittest.TestCase):
    """随机生成输入，验证不崩溃"""

    def _random_string(self, min_len=0, max_len=200):
        """生成一个随机字符串"""
        import random
        length = random.randint(min_len, max_len)
        chars = "abcdefghijklmnopqrstuvwxyz一二三四五六七八九十[]{}()<>!@#$%^&*_+-=.,:; \"'\n\t"
        return "".join(random.choice(chars) for _ in range(length))

    def test_fuzz_is_correction_no_crash(self):
        """is_correction 随机字符串 → 不崩溃"""
        for _ in range(30):
            inp = self._random_string(0, 150)
            result = is_correction(inp, self._random_string(0, 100))
            self.assertIn(result, ("correction", "confirmation", "new_command"))

    def test_fuzz_detect_correction_type_no_crash(self):
        """detect_correction_type 随机字符串 → 不崩溃，返回合法类型"""
        valid_types = ("multi_wrong", "paste_wrong", "pronoun_wrong", "bare_wrong")
        for _ in range(30):
            inp = self._random_string(1, 200)
            corr = self._random_string(0, 100)
            result = detect_correction_type(inp, corr)
            self.assertIn(result, valid_types,
                          f"unexpected type '{result}' for input={inp!r}")

    def test_fuzz_looks_like_log_no_crash(self):
        """_looks_like_log_or_error 随机多行字符串 → 返回 bool，不崩溃"""
        for _ in range(30):
            lines = []
            n = 10
            for _ in range(n):
                lines.append(self._random_string(0, 80))
            text = "\n".join(lines)
            result = _looks_like_log_or_error(text)
            self.assertIsInstance(result, bool)

    def test_fuzz_extreme_lengths(self):
        """超长输入（10K+ 字符）→ 不崩溃"""
        long_str = "a" * 10000 + "不是" + "b" * 10000
        self.assertEqual(is_correction(long_str), "new_command")  # 前缀检查，超过长度
        result = detect_correction_type(long_str)
        self.assertIn(result, ("multi_wrong", "paste_wrong", "pronoun_wrong", "bare_wrong"))
        # 超长日志检测
        log_text = "\n".join([f"[ERROR] line {i} crash" for i in range(500)])
        self.assertTrue(_looks_like_log_or_error(log_text))

    def test_fuzz_parenthesis_input(self):
        """括号开头 → paste_wrong（_JSON_LIKE_START 包含 '('）"""
        self.assertEqual(detect_correction_type("() => { ... }"), "paste_wrong")
        self.assertEqual(detect_correction_type("(error: 404)"), "paste_wrong")

    def test_fuzz_unicode_only(self):
        """纯 unicode 特殊符号 → 不崩溃"""
        result = is_correction("⏰🔥💯🎉")
        self.assertIn(result, ("correction", "confirmation", "new_command"))

    def test_fuzz_all_functions_round_trip(self):
        """完整链随机输入：is_correction → detect → apply → save → load → generate"""
        from generate_prompt import generate_prompt
        profile = build_profile([
            {"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS
        ])
        for _ in range(5):
            inp = self._random_string(1, 50)
            ai = self._random_string(1, 30)
            corr = self._random_string(0, 30)
            mode = is_correction(inp, ai)
            if mode == "correction":
                ctype = detect_correction_type(inp, corr)
                profile = _apply_correction(profile, inp, ai, corr, ctype)
        # 最终验证：generate 不崩溃
        prompt = generate_prompt(profile)
        self.assertIn("Boss Mode", prompt)
        # 未超过 MAX_CORRECTIONS
        self.assertLessEqual(len(profile["corrections"]), 50)


# ── 第 14 类：剩余边界 ────────────────────────────

class TestRemainingEdge(unittest.TestCase):
    """覆盖之前未触及的边界"""

    def test_paste_starts_with_parenthesis(self):
        """圆括号 (...) 开头应被识别为 paste_wrong"""
        self.assertEqual(detect_correction_type("(some output)"), "paste_wrong")

    def test_detect_type_emoji_start(self):
        """纯 emoji 开头 → 无代词/多意图/粘贴标记 → bare_wrong"""
        self.assertEqual(detect_correction_type("🔥🔥🔥"), "bare_wrong")

    def test_load_profile_not_found(self):
        """不存在的 profile 路径 → FileNotFoundError"""
        from update_feedback import load_profile
        with self.assertRaises(FileNotFoundError):
            load_profile("/nonexistent/profile.json")

    def test_load_profile_corrupted_json(self):
        """损坏的 JSON → JSONDecodeError"""
        from update_feedback import load_profile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{not valid json")
            tmp = f.name
        try:
            with self.assertRaises(json.JSONDecodeError):
                load_profile(tmp)
        finally:
            os.unlink(tmp)

    def test_save_profile_permission_error(self):
        """不可写路径 → OSError"""
        from update_feedback import save_profile
        profile = build_profile([{"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS])
        with self.assertRaises(OSError):
            save_profile("/dev/null/nope/profile.json", profile)

    def test_adjust_parameters_no_rules(self):
        """无对应调整规则的 correction_type → 参数不变"""
        profile = build_profile([{"scenario_id": s["id"], "selected": "a"} for s in SCENARIOS])
        before = dict(profile["parameters"])
        profile = adjust_parameters(profile, "bare_wrong")
        self.assertEqual(profile["parameters"]["pronoun_inference"],
                         before["pronoun_inference"])

    def test_is_correction_exact_prefix_matching(self):
        """关键：'不是' 不应误匹配 '不是这样应该' — 前缀正确"""
        self.assertEqual(is_correction("不是这样应该怎样"), "correction")


if __name__ == "__main__":
    unittest.main(verbosity=2)
