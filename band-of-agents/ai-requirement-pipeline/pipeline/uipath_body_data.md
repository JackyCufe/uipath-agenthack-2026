# UiPath Service Task Body Data — Copy & Paste Guide

Your ngrok URL: https://hula-removed-swung.ngrok-free.dev

---

## 1. KB Search History — Body
```
{"requirement_text": "Customer Acme Corp reported their reception bot cannot handle multi-language greetings. Sales confirmed the customer needs auto-detection of 5 languages (EN, CN, JP, KR, ES) with seamless switching. Expected outcome: customer satisfaction score increase by 30%."}
```

## 2. S1 AI Gatekeeping — Body
```
{"requirement_text": "Customer Acme Corp reported their reception bot cannot handle multi-language greetings. Sales confirmed the customer needs auto-detection of 5 languages (EN, CN, JP, KR, ES) with seamless switching. The customer's IT director James Park mentioned this in the Q2 business review meeting. Expected outcome: customer satisfaction score increase by 30%, reduce escalation tickets by 50%.", "requirement_id": "REQ-DEMO-001", "rounds": 1}
```

## 3. S2 AI Value Transform — Body
```
{"requirement_id": "REQ-DEMO-001", "pm_acceptance_criteria_raw": "The reception bot must auto-detect user language from first 2 messages and switch instantly. Support EN, CN, JP, KR, ES. If detection confidence <80%, prompt user to select. Log language distribution weekly.", "four_q": {"who": "Enterprise customers using reception bot (e.g. Acme Corp IT director James Park)", "scene": "Customer-facing reception desk, multi-national visitors", "problem": "Bot only supports single language, international visitors get frustrated", "expected": "Auto-detect 5 languages, seamless switch, 30% satisfaction increase, 50% less escalation tickets"}, "pm_core_value": "Eliminate language barriers in customer reception, improving first impressions for international visitors", "pm_feature_def": "Multi-language auto-detection engine with 5 language support and confidence-based fallback", "pm_priority": "P1"}
```

## 4. S3 AI Test Case Generation — Body
```
{"requirement_id": "REQ-DEMO-001", "schema_2": {"schema_version": "2.0", "stage": "pm_confirmed", "requirement_id": "REQ-DEMO-001", "core_value": "Eliminate language barriers in customer reception", "feature_definition": "Multi-language auto-detection engine with 5 language support", "priority": "P1", "acceptance_criteria": [{"id": "AC-1", "description": "Bot detects language from first 2 messages", "priority": "P0"}, {"id": "AC-2", "description": "Supports EN, CN, JP, KR, ES", "priority": "P0"}, {"id": "AC-3", "description": "Confidence <80% triggers language picker", "priority": "P1"}, {"id": "AC-4", "description": "Weekly language distribution report", "priority": "P2"}], "test_cases": [{"id": "TC-1", "scenario": "English user sends greeting", "expected": "Bot responds in English"}]}}
```

## 5. S4 AI Release Review — Body
```
{"schema_3_list": [{"requirement_id": "REQ-DEMO-001", "test_cases": [{"id": "TC-1", "scenario": "English user sends greeting", "expected": "Bot responds in English", "result": "passed", "priority": "P0"}, {"id": "TC-2", "scenario": "Japanese user sends greeting", "expected": "Bot responds in Japanese", "result": "passed", "priority": "P0"}, {"id": "TC-3", "scenario": "Mixed language input (EN+CN)", "expected": "Bot detects dominant language", "result": "passed", "priority": "P0"}, {"id": "TC-4", "scenario": "Low confidence input (ambiguous text)", "expected": "Language picker appears", "result": "passed", "priority": "P1"}, {"id": "TC-5", "scenario": "Korean user sends greeting", "expected": "Bot responds in Korean", "result": "passed", "priority": "P0"}], "test_summary": {"total": 5, "passed": 5, "failed": 0, "blocked": 0}}], "version": "v2.1.0"}
```

## 6. S5 AI Feedback Analysis — Body
```
{"schema_4": {"schema_version": "4.0", "stage": "release_approved", "version": "v2.1.0", "release_verdict": "approved", "core_value_statement": "Multi-language auto-detection eliminates reception language barriers for international visitors"}, "feedback_items": [{"customer": "Acme Corp", "contact": "James Park", "rating": 5, "comment": "The multi-language feature works flawlessly. Our international visitors no longer struggle with the reception bot."}, {"customer": "TechFlow Inc", "contact": "Sarah Chen", "rating": 4, "comment": "Great feature. Would love to see Vietnamese and Thai added in the next version."}, {"customer": "GlobalServe", "contact": "Mike Johnson", "rating": 5, "comment": "Escalation tickets dropped by 60% after this update. Exactly what we needed."}]}
```

## 7. S6 AI Retrospective + KB Write — Body
```
{"schema_5": {"schema_version": "5.0", "stage": "feedback_collected", "ai_analysis": {"satisfaction_rate": 0.93, "key_finding": "Multi-language auto-detection directly reduced escalation tickets by 55-60% across 3 enterprise customers", "recommendation": "Expand to Southeast Asian languages (Vietnamese, Thai) in next version based on customer demand"}}, "all_schemas": {"schema_1": {"requirement_id": "REQ-DEMO-001", "gatekeeping": {"verdict": "approved"}}, "schema_2": {"priority": "P1", "acceptance_criteria_count": 4}, "schema_3": {"test_summary": {"total": 5, "passed": 5}}, "schema_4": {"release_verdict": "approved", "version": "v2.1.0"}}}
```

---

## User Task SpecificContent

### S1 Gatekeeping Confirm — SpecificContent
```
{"requirement_text": "Customer Acme Corp reported reception bot cannot handle multi-language greetings. Needs auto-detection of 5 languages with seamless switching.", "customer_who": "Acme Corp IT director James Park", "usage_scenario": "Customer-facing reception desk, multi-national visitors", "problem": "Bot only supports single language, international visitors get frustrated", "expected_outcome": "Auto-detect 5 languages, 30% satisfaction increase, 50% less escalations", "verdict": ""}
```

### S2 PM Confirm — SpecificContent
```
{"structured_criteria": "AC-1: Detect language from first 2 messages (P0)\nAC-2: Support EN/CN/JP/KR/ES (P0)\nAC-3: Confidence <80% triggers picker (P1)\nAC-4: Weekly distribution report (P2)", "test_cases": "TC-1: English greeting -> English response\nTC-2: Japanese greeting -> Japanese response\nTC-3: Mixed language -> dominant detected", "pm_core_value": "Eliminate language barriers in customer reception", "pm_priority": "P1", "verdict": ""}
```

### S3 Dev Confirm — SpecificContent
```
{"test_cases": "TC-1: English greeting -> PASSED\nTC-2: Japanese greeting -> PASSED\nTC-3: Mixed language -> PASSED\nTC-4: Low confidence -> Picker shown -> PASSED\nTC-5: Korean greeting -> PASSED", "technical_plan": "NLP language detection model integrated with confidence scoring. Fallback UI component for language picker.", "test_result": "5/5 passed, 0 failed, 0 blocked", "verdict": ""}
```
