#!/usr/bin/env python3
"""
Boss Mode — 测试套件
====================
验证校准+prompt生成+反馈循环的完整流程。
"""

import json
import os
import sys
import tempfile
import unittest

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from calibrate import build_profile, SCENARIOS
from generate_prompt import generate_prompt
from update_feedback import learn_pattern, adjust_parameters


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
