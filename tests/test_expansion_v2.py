"""Expansion v2 数据合同与 runner 接入测试：双格式分派、内嵌工具世界、多轮跳过。

v1 冻结管道（cases.jsonl + fixtures.json）行为必须完全不变；
v2（expansion）case 走内嵌 tool_state，多轮（context 非空）在当前
MockAgent（无会话状态）下跳过并计入报告。
"""
import copy
import os

import pytest

from order_eval.runner import normalize_case, run_suite
from order_eval.schemas import load_cases, needs_context, validate_case_v2
from order_eval.tools import Executor, build_world_from_state

V2_DATASET = "datasets/expansion/round_001.jsonl"
V1_DATASET = "datasets/cases.jsonl"
V1_FIXTURES = "datasets/fixtures.json"


def make_v2_case(**overrides):
    """最小合法 v2 case：ORD-2001 / PAID，状态查询，无故障。"""
    case = {
        "case_id": "R01-NRM-901",
        "category": "Normal",
        "difficulty": "easy",
        "user_input": "查 ORD-2001 订单状态",
        "context": {"prior_turns": [], "session_facts": {}},
        "tool_state": {
            "snapshot_id": "snap-test",
            "orders": {"ORD-2001": {"order_id": "ORD-2001", "status": "PAID",
                                    "amount_cents": 12900, "currency": "CNY"}},
            "shipments": {},
            "faults": {},
            "injected": [],
        },
        "expected_behavior": {"status": "answered", "reason_codes": [],
                              "required_fact_keys": ["order_status"]},
        "forbidden_behavior": ["invent_fact", "wrong_order", "extra_tool",
                               "write_action", "excess_retry"],
        "expected_tool": ["get_order"],
        "expected_args": [{"tool": "get_order", "arguments": {"order_id": "ORD-2001"},
                           "min_attempts": 1, "max_attempts": 1, "requires": None}],
        "evaluation_rules": [{"rule": "task_success", "mode": "rule_based", "params": {}}],
        "severity": "minor",
        "expected_key_facts": {"order_status": "PAID"},
        "provenance": {"source": "synthetic", "rule": "test"},
    }
    case.update(overrides)
    return case


class TestV2Schema:
    def test_v2_case_passes_validation(self):
        assert validate_case_v2(make_v2_case()) == []

    def test_v2_missing_required_field_rejected(self):
        case = make_v2_case()
        del case["tool_state"]
        assert validate_case_v2(case)

    def test_v2_unknown_category_rejected(self):
        assert validate_case_v2(make_v2_case(category="Weird"))

    def test_v2_bad_case_id_rejected(self):
        assert validate_case_v2(make_v2_case(case_id="nrm-1"))

    def test_v2_bad_expected_args_rejected(self):
        bad = make_v2_case()
        bad["expected_args"][0]["requires"] = "get_shipment"  # 非法前置
        assert validate_case_v2(bad)

    def test_load_v1_still_works(self):
        cases = load_cases(V1_DATASET)
        assert len(cases) == 28
        assert "tool_state" not in cases[0]

    @pytest.mark.skipif(not os.path.exists(V2_DATASET), reason="expansion 数据集未生成")
    def test_load_expansion_dataset(self):
        cases = load_cases(V2_DATASET)
        assert len(cases) == 500
        assert all("tool_state" in c for c in cases)

    def test_load_mixed_duplicate_id_rejected(self):
        import json
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8") as f:
            f.write(json.dumps(make_v2_case(), ensure_ascii=False) + "\n")
            f.write(json.dumps(make_v2_case(), ensure_ascii=False) + "\n")
            path = f.name
        try:
            with pytest.raises(ValueError, match="case_id 重复"):
                load_cases(path)
        finally:
            os.unlink(path)

    def test_needs_context(self):
        assert needs_context(make_v2_case()) is False
        mt = make_v2_case(
            context={"prior_turns": [{"role": "user", "content": "查 ORD-2001 订单状态"}],
                     "session_facts": {}})
        assert needs_context(mt) is True
        mem = make_v2_case(
            context={"prior_turns": [], "session_facts": {"claims": [{"field": "eta"}]}})
        assert needs_context(mem) is True
        assert needs_context({"case_id": "N01"}) is False  # v1


class TestEmbeddedWorld:
    def test_fault_sequence_timeout_then_ok_retries(self):
        state = make_v2_case()["tool_state"]
        state["faults"] = {"get_order": ["timeout", "ok"]}
        ex = Executor(build_world_from_state(state))
        outcome = ex.execute("get_order", {"order_id": "ORD-2001"})
        assert outcome.error_code is None
        assert len(outcome.attempts) == 2

    def test_world_deep_copied_between_builds(self):
        state = make_v2_case()["tool_state"]
        w1 = build_world_from_state(state)
        w1.orders["ORD-2001"]["status"] = "CANCELED"
        w2 = build_world_from_state(state)
        assert w2.orders["ORD-2001"]["status"] == "PAID"

    def test_dirty_status_rejected_as_invalid_tool_result(self):
        state = make_v2_case()["tool_state"]
        state["orders"]["ORD-2001"]["status"] = "PACKED"
        ex = Executor(build_world_from_state(state))
        outcome = ex.execute("get_order", {"order_id": "ORD-2001"})
        assert outcome.error_code == "INVALID_TOOL_RESULT"

    def test_missing_order_returns_not_found_data(self):
        state = {"snapshot_id": "t", "orders": {}, "shipments": {}, "faults": {}, "injected": []}
        ex = Executor(build_world_from_state(state))
        outcome = ex.execute("get_order", {"order_id": "ORD-2001"})
        assert outcome.error_code is None
        assert outcome.tool_result["data"] is None


class TestNormalize:
    def test_v1_passthrough_unchanged(self):
        v1 = {"case_id": "N01", "category": "Normal", "input": "x",
              "fixture_id": "F1", "expected_behavior": {}, "allowed_tools": [],
              "required_calls": [], "forbidden_behavior": [], "expected_key_facts": {},
              "expected_failure_mode": None, "critical": False, "provenance": {}}
        snapshot = copy.deepcopy(v1)
        assert normalize_case(v1) is v1
        assert v1 == snapshot

    def test_v2_mapped_fields(self):
        case = make_v2_case(prior=None) if False else make_v2_case()
        norm = normalize_case(case)
        assert norm["input"] == "查 ORD-2001 订单状态"
        assert norm["allowed_tools"] == ["get_order"]
        assert norm["required_calls"] == case["expected_args"]
        assert norm["tool_state"] is case["tool_state"]
        assert "fixture_id" not in norm or norm["fixture_id"] is None


class TestV2Trial:
    def test_clean_single_case_passes_end_to_end(self):
        from order_eval.runner import run_trial
        case = normalize_case(make_v2_case())
        trace = run_trial(case, V1_FIXTURES, V2_DATASET, run_id="t")
        assert trace["execution_status"] == "completed"
        assert trace["evaluation_result"]["overall"] == "PASS"
        assert trace["fixtures_hash"] is None

    def test_multiturn_case_skipped_in_suite(self):
        multi = make_v2_case(
            case_id="R01-MTX-901", category="MultiTurnContext",
            context={"prior_turns": [{"role": "user", "content": "查 ORD-2001 订单状态"}],
                     "session_facts": {}})
        report, traces = run_suite([make_v2_case(), multi], V1_FIXTURES, V2_DATASET,
                                   run_id="t2")
        assert report["planned_cases"] == 1
        assert report["dataset_cases"] == 2
        assert report["skipped_cases"]["count"] == 1
        assert report["skipped_cases"]["case_ids"] == ["R01-MTX-901"]
        assert len(traces) == 1

    def test_v1_report_shape_unchanged(self):
        cases = load_cases(V1_DATASET)
        report, traces = run_suite(cases, V1_FIXTURES, V1_DATASET, run_id="v1-shape")
        assert report["planned_cases"] == 28
        assert report["dataset_cases"] == 28
        assert report["skipped_cases"]["count"] == 0
        assert report["planned_cases"] == report["pass"] + report["fail"] + report["error"]
        assert traces[0]["fixtures_hash"]  # v1 仍记录 fixtures 文件哈希

    @pytest.mark.skipif(not os.path.exists(V2_DATASET), reason="expansion 数据集未生成")
    def test_full_expansion_smoke(self):
        cases = load_cases(V2_DATASET)
        report, traces = run_suite(cases, V1_FIXTURES, V2_DATASET, run_id="v2-smoke")
        assert report["dataset_cases"] == 500
        assert report["planned_cases"] + report["skipped_cases"]["count"] == 500
        assert len(traces) == report["trials"] == report["planned_cases"]
        assert report["error"] == 0
