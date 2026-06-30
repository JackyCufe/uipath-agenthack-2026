# Agent Pipeline — Schema 设计文档

> 版本：v2（最终确认版）
> 确认日期：2026-05-08
> 用途：定义6个Agent之间的JSON数据契约

---

## Schema 1 — 守门 → 价值转化

```json
{
  "schema_version": "1.0",
  "stage": "gatekeeping_approved",
  "requirement_id": "req_20260508_001",
  "original_text": "（原始需求原文，写入后不可修改）",
  "submitted_by": "售前姓名",
  "submitted_at": "2026-05-08T10:00:00+08:00",
  "requirement_source": "客户 | 售前 | 内部研发 | 老板/战略 | 合作伙伴",
  "gatekeeping": {
    "_note": "verdict / reject_reason / followup_questions 由守门Agent（AI）生成，非人工填写",
    "verdict": "approved | rejected | info_needed",
    "rounds": 1,
    "customer_who": "代理商",
    "usage_scenario": "代理商首次配置机器人接待后台首页时",
    "problem": "需要上门服务教客户配置，交付和售后成本高",
    "expected_outcome": "代理商通过飞书向龙虾机器人下达一句话指令完成配置，无需上门",
    "reject_reason": null,
    "followup_questions": []
  },
  "_note_rounds": "rounds记录追问轮次，超过3轮仍info_needed则自动转rejected，理由：信息不足暂不立项",
  "_note_source": "requirement_source为内部研发/老板战略时，守门Agent额外追问：这个需求的外部受益场景是什么？",
  "_note_confirmed": "confirmed_by是PM确认接收流转，不参与verdict判断",
  "confirmed_by": "PM姓名",
  "confirmed_at": "2026-05-08T11:00:00+08:00"
}
```

**字段溯源**
- `customer_who / usage_scenario / problem / expected_outcome`：「售前需明确客户是谁、在什么场景下使用、遇到什么问题以及期望达到什么结果」
- `requirement_source`：「销售需求不具体、偏概念且分散，源头信息缺失导致后续环节价值传递减弱」

---

## Schema 2 — 价值转化 → 场景测试

```json
{
  "schema_version": "1.0",
  "stage": "value_defined",
  "requirement_id": "req_20260508_001",
  "original_text": "（透传自Schema 1，不可修改）",
  "gatekeeping": {"_ref": "透传Schema 1 gatekeeping全部字段"},
  "requirement_source": "（透传Schema 1）",
  "product_line": "零售模式 | Agent商店 | 龙虾机器人",
  "value_type": "效率提升 | 体验优化 | 功能扩展 | 成本降低",
  "importance": "P0 | P1 | P2",
  "acceptance_criteria": [
    {
      "criterion_id": "ac_001",
      "description": "代理商可通过一句话指令完成首页配置",
      "metric": "配置成功率",
      "threshold": "≥ 95%",
      "measurement_method": "功能测试通过率统计"
    },
    {
      "criterion_id": "ac_002",
      "description": "操作步骤不超过3步",
      "metric": "用户操作步骤数",
      "threshold": "≤ 3步",
      "measurement_method": "用户操作路径录屏统计"
    }
  ],
  "_note": "acceptance_criteria草稿由价值转化Agent生成，pm_confirmed_by确认后方可流转",
  "pm_confirmed_by": ["PM姓名"],
  "pm_confirmed_at": "2026-05-08T14:00:00+08:00"
}
```

**字段溯源**
- `acceptance_criteria`：「要为每个需求定义从客户角度的验收标准，明确需求解决到何种程度才算完成」
- `product_line`：会议纪要三大主线（开箱即用/零售模式/Agent商店）映射至实际产品线

---

## Schema 3 — 场景测试 → 发版评审

```json
{
  "schema_version": "1.0",
  "stage": "testing_complete",
  "requirement_id": "req_20260508_001",
  "original_text": "（透传，不可修改）",
  "acceptance_criteria": ["（透传Schema 2全部验收标准）"],
  "dev_self_test": {
    "_note": "测试负责人在填test_cases前必须确认此项为true，否则流程不启动",
    "passed": true,
    "confirmed_by": ["研发负责人姓名"],
    "confirmed_at": "2026-05-09T09:00:00+08:00"
  },
  "test_cases": [
    {
      "case_id": "tc_001",
      "criterion_id": "ac_001",
      "actor": "代理商（首次使用）",
      "precondition": "已登录后台，首页配置为空",
      "steps": [
        "发送指令：帮我配置首页",
        "确认系统解析结果",
        "点击一键应用"
      ],
      "expected_output": "首页完成配置，配置步骤 ≤ 3步",
      "_note_verdict": "actual_result和verdict由测试负责人（人工）填写，非AI生成",
      "actual_result": "首页完成配置，共2步",
      "verdict": "pass | fail | blocked"
    }
  ],
  "_note_blocked": "blocked：测试用例因前置条件未就绪无法执行（如功能未部署、依赖接口故障），区别于fail（执行了但结果不符预期）",
  "test_summary": {
    "total": 3,
    "passed": 3,
    "failed": 0,
    "blocked": 0
  },
  "tester_confirmed_by": ["测试负责人姓名"],
  "tester_confirmed_at": "2026-05-09T16:00:00+08:00"
}
```

**字段溯源**
- `dev_self_test`：「研发自测不通过测试不接收 / 绝对禁区：将半成品传递给下一环节」
- `test_cases actor/steps`：「基于客户场景进行验证，而非仅关注功能bug和接口」

---

## Schema 4 — 发版评审 → 反馈收集

```json
{
  "schema_version": "1.0",
  "stage": "release_approved",
  "_release_rubric": {
    "P0_fail": "release_verdict强制为blocked",
    "P1_fail": "生成warning写入bypass_log，不阻断发版，需approved_by人工确认",
    "P2_fail": "生成warning only，不写入bypass_log，不阻断"
  },
  "_note": "release_verdict由发版评审Agent（AI）按release_rubric规则生成，approved_by是产品负责人对本版本核心价值的人工确认（价值门控，非技术门控）",
  "version": "2.3.0",
  "release_date": "2026-05-10",
  "requirements": [
    {
      "requirement_id": "req_20260508_001",
      "importance": "P0",
      "acceptance_verdict": "pass | fail",
      "block_reason": null
    }
  ],
  "release_verdict": "approved | blocked",
  "core_value_statement": "本版本交付：代理商可通过一句话完成接待首页配置，已验证客户场景跑通",
  "bypass_log": [
    {
      "requirement_id": "（P1需求fail时自动写入）",
      "importance": "P1",
      "fail_reason": "",
      "bypass_approved_by": ["产品负责人姓名"]
    }
  ],
  "approved_by": ["产品负责人姓名"],
  "approved_at": "2026-05-10T09:00:00+08:00"
}
```

**字段溯源**
- `core_value_statement`：「验收通过后，应明确本版本的核心价值，发出已验证客户场景跑通、可以发布的通知」
- `release_verdict: blocked`：「未客户验收不发布」

---

## Schema 5 — 反馈收集 → 复盘分析

```json
{
  "schema_version": "1.0",
  "stage": "feedback_collected",
  "version": "2.3.0",
  "questionnaire": {
    "criteria_covered": ["ac_001", "ac_002"],
    "sent_count": 12,
    "response_count": 9,
    "sent_at": "2026-05-10T18:00:00+08:00",
    "closed_at": "2026-05-12T18:00:00+08:00"
  },
  "feedback_items": [
    {
      "requirement_id": "req_20260508_001",
      "criterion_id": "ac_001",
      "satisfied_count": 7,
      "unsatisfied_count": 2,
      "satisfied_comments": [
        "配置很顺，3步就完成了",
        "比以前快多了，代理商都说好用"
      ],
      "unsatisfied_comments": [
        "有一次识别不准，重发一次才好"
      ]
    }
  ],
  "ai_analysis": {
    "met_criteria": ["ac_001"],
    "unmet_criteria": [],
    "satisfaction_rate": 0.78,
    "key_finding": "2/9客户遇到指令识别偶发失败，其余7人顺利完成配置",
    "recommendation": "优化指令解析容错率，覆盖更多口语化表达"
  },
  "presentation_summary": "2.3版本核心交付「接待首页一句话配置」验证通过，满意率78%，1个改进点已识别，建议列入2.4排期。供产研周会/版本复盘会直接使用。",
  "collected_by": "反馈收集Agent",
  "collected_at": "2026-05-12T18:00:00+08:00"
}
```

**字段溯源**
- `satisfied_comments / unsatisfied_comments`：结构化分类确保AI分析可追溯
- `presentation_summary`：「用AI分析并呈现，在产研周会或版本复盘会中讨论」

---

## Schema 6 — 复盘分析输出（最终归档）

```json
{
  "schema_version": "1.0",
  "stage": "retrospective_complete",
  "version": "2.3.0",
  "retrospective_date": "2026-05-13T10:00:00+08:00",
  "requirements_summary": {
    "total": 4,
    "fully_met": 3,
    "partially_met": 1,
    "unmet": 0
  },
  "roi_verdict": {
    "criteria_met_rate": 0.92,
    "customer_satisfaction_rate": 0.78,
    "summary": "本版本核心价值交付达标，接待首页配置场景客户验收通过"
  },
  "next_version_suggestions": [
    {
      "suggestion_id": "s1",
      "source_requirement_id": "req_20260508_001",
      "type": "carry_forward | new | drop",
      "description": "优化指令解析稳定性，减少首次识别失败率",
      "priority": "P1",
      "rationale": "2/9客户反馈偶发识别失败",
      "evidence_from": {
        "criterion_id": "ac_001",
        "verbatim": "有一次识别不准，重发一次才好"
      }
    }
  ],
  "improvement_actions": [
    {
      "action_id": "a1",
      "target": "process | product | team",
      "description": "售前守门追问超3轮直接标记「信息不足暂不立项」",
      "owner": ["PM姓名"],
      "deadline": "2026-05-20",
      "evidence_from": {
        "stage": "gatekeeping",
        "observation": "需求B共经历2轮追问，边界仍模糊"
      }
    }
  ],
  "process_retrospective": {
    "avg_gatekeeping_rounds": 1.5,
    "stage_bottlenecks": [
      {
        "stage": "value_definition",
        "issue": "验收标准初稿含形容词，PM需二次修订",
        "frequency": 2
      }
    ],
    "ambiguity_leakage": [
      {
        "requirement_id": "req_20260508_002",
        "leaked_at_stage": "value_definition",
        "description": "守门通过后，价值转化阶段发现边界仍未明确，返回追问"
      }
    ],
    "process_health_score": 0.82
  },
  "archived_by": "复盘分析Agent",
  "archived_at": "2026-05-13T11:00:00+08:00"
}
```

**字段溯源**
- `process_retrospective`：「通过核心职责和禁区的把控，评估工作表现和绩效」/ 「实现迭代改进，形成闭环」
- `evidence_from`：确保每条建议和行动可溯源至具体客户反馈
