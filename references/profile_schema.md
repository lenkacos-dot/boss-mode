{
  "$schema": "boss-mode-profile-schema",
  "version": 1,
  "description": "用户表达风格画像 — Boss Mode 校准结果",

  "fields": {
    "profile_id": "string, 唯一标识（如 alan-boss）",
    "created_at": "ISO 8601 时间戳",
    "updated_at": "ISO 8601 时间戳",
    "last_calibration": "ISO 8601 时间戳",

    "style_label": {
      "description": "风格标签，由校准自动推断",
      "type": "enum",
      "values": [
        "efficiency_boss: 效率优先，少问多干，错了纠正就行。雷厉风行的老板 / 创业者",
        "precise_boss: 准确优先，问清楚再做。严谨的甲方 / 传统行业领导",
        "casual_boss: 随性风格，有时简短有时详细，AI 灵活适应"
      ]
    },

    "parameters": {
      "pronoun_inference": {
        "type": "float 0.0-1.0",
        "default": 0.7,
        "description": "代词推断力度。1.0=用户说'它'永远知道指什么，从不追问；0.0=任何代词都确认"
      },
      "bare_command_tolerance": {
        "type": "float 0.0-1.0",
        "default": 0.6,
        "description": "裸命令容忍度。1.0='优化'直接做最常见的优化；0.0='优化'必须问优化什么"
      },
      "correction_style": {
        "type": "enum",
        "values": ["act_first: 先做再纠正", "ask_first: 先问再做"],
        "default": "act_first",
        "description": "纠正偏好。老板一般选 act_first（时间就是金钱）"
      },
      "multi_intent_handling": {
        "type": "enum",
        "values": [
          "parallel: 同时做，不用确认",
          "sequential: 按顺序做，不用确认",
          "ask: 确认优先级再做"
        ],
        "default": "sequential",
        "description": "多意图处理。用户一句说多个任务时怎么处理"
      },
      "paste_behavior": {
        "type": "enum",
        "values": ["auto_analyze: 自动分析并汇报", "ask_intent: 先问用途"],
        "default": "auto_analyze",
        "description": "粘贴行为。用户贴数据/日志/代码时"
      },
      "context_depth": {
        "type": "integer 1-10",
        "default": 5,
        "description": "上下文追溯轮数。当前对话往前回溯多少轮来推断指代"
      }
    },

    "corrections": {
      "type": "array",
      "description": "用户纠正历史。每次用户纠正 AI 的推断时记录，用于持续优化",
      "items": {
        "timestamp": "ISO 8601",
        "input": "用户的原始输入",
        "ai_inference": "AI 当时的理解和操作",
        "user_correction": "用户的纠正内容",
        "pattern": "推断出的规则（AI 自动填充）",
        "applied": "bool，是否已应用到 profile 参数调整"
      }
    },

    "frequent_patterns": {
      "type": "object",
      "description": "用户常用的简写/黑话，AI 自动学习",
      "properties": {
        "shorthand_map": "dict, e.g. {'stg': 'staging', 'prd': 'production', 'dv': 'development'}",
        "preferred_refs": "dict, e.g. {'那个项目': '项目X', '那套方案': '方案Y'}",
        "common_phrases": "list, 用户常说的高频短语"
      }
    }
  },

  "example": {
    "profile_id": "alan-boss",
    "style_label": "efficiency_boss",
    "parameters": {
      "pronoun_inference": 0.85,
      "bare_command_tolerance": 0.75,
      "correction_style": "act_first",
      "multi_intent_handling": "sequential",
      "paste_behavior": "auto_analyze",
      "context_depth": 5
    },
    "corrections": [],
    "frequent_patterns": {
      "shorthand_map": {},
      "preferred_refs": {},
      "common_phrases": []
    }
  }
}
