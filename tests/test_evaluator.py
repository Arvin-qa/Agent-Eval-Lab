"""Evaluator 反例测试：E01–E12 静态标注好坏 Trace + 合法变体防误杀（AC08/AC09/AC10）。

标注来源：ACCEPTANCE_CRITERIA §4 表格，人工核对后写死在断言里；
不是由 Evaluator 给自己标答案，也不把这些反例混入业务数据集。
"""
import copy
import json

import pytest

from order_eval.evaluator import evaluate
from order_eval.runner import run_trial
from order_eval.schemas import load_cases

FIXTURES = "datasets/fixtures.json"
CASES = "datasets/cases.jsonl"


def get_case(case_id):
    for case in load_cases(CASES):
        if case["case_id"] == case_id:
            return copy.deepcopy(case)
    raise KeyError(case_id)


def real_trace(case_id):
    case = get_case(case_id)
    return case, run_trial(case, FIXTURES, CASES)


def dim_status(evaluation, dim):
    return evaluation["dimensions"][dim]["status"]


# ---------------------------------------------------------------- 好 Trace：合法行为必须 PASS

class TestGoodTracesPass:
    def test_e01_n01_normal_answered(self):
        case, trace = real_trace("N01")
        ev = evaluate(case, trace)
        assert ev["overall"] == "PASS"
        for d in ["task_success", "tool_selection", "tool_argument",
                  "groundedness", "output_format", "constraint_following"]:
            assert dim_status(ev, d) == "PASS", (d, ev["dimensions"][d]["checks"])

    def test_e02_i02_legit_clarification_zero_tools(self):
        case, trace = real_trace("I02")
        ev = evaluate(case, trace)
        assert ev["overall"] == "PASS"
        assert dim_status(ev, "tool_argument") == "N/A"  # 无调用且无需调用

    def test_e03_t02_two_timeouts_legit_degrade(self):
        case, trace = real_trace("T02")
        ev = evaluate(case, trace)
        assert ev["overall"] == "PASS"
        assert dim_status(ev, "task_success") == "PASS"


# ---------------------------------------------------------------- 坏 Trace：评测器必须抓错

def make_e04_wrong_tool():
    case, trace = real_trace("N01")
    entry = trace["tool_calls"][0]
    entry["selected_tool"] = "get_shipment"  # 用 get_shipment 替代 get_order
    return case, trace


def make_e05_wrong_order_param():
    case, trace = real_trace("N01")
    entry = trace["tool_calls"][0]
    entry["arguments_raw"] = {"order_id": "ORD-1002"}
    entry["tool_arguments"] = {"order_id": "ORD-1002"}
    entry["tool_result"]["data"] = {
        "order_id": "ORD-1002", "status": "SHIPPED", "amount_cents": 25900, "currency": "CNY",
    }
    entry["tool_result_raw"] = copy.deepcopy(entry["tool_result"])
    trace["agent_output"]["facts"] = {"order_status": "SHIPPED"}
    trace["agent_output_raw"] = json.dumps(trace["agent_output"])
    return case, trace


def make_e06_missing_param():
    case, trace = real_trace("N01")
    entry = trace["tool_calls"][0]
    entry["arguments_raw"] = {}
    entry["tool_arguments"] = None
    entry["validation_result"] = "ARGUMENT_SCHEMA_ERROR"
    entry["error_code"] = "ARGUMENT_SCHEMA_ERROR"
    entry["tool_result_raw"] = None
    entry["tool_result"] = None
    trace["agent_output"] = {
        "status": "unavailable", "order_id": "ORD-1001", "facts": {},
        "reason_codes": ["TOOL_UNAVAILABLE"], "evidence": [],
    }
    trace["agent_output_raw"] = json.dumps(trace["agent_output"])
    return case, trace


def make_e07_fake_amount():
    case, trace = real_trace("H02")
    trace["agent_output"]["facts"]["amount_cents"] = 19900  # 假金额，引用指向真值 12900
    trace["agent_output_raw"] = json.dumps(trace["agent_output"])
    return case, trace


def make_e08_nonexistent_call_ref():
    case, trace = real_trace("N01")
    trace["agent_output"]["evidence"][0]["call_id"] = "call-999"
    trace["agent_output_raw"] = json.dumps(trace["agent_output"])
    return case, trace


def make_e09_cross_case_ref():
    case, trace = real_trace("N01")
    trace["agent_output"]["evidence"][0]["call_id"] = "call-OTHERCASE-1"
    trace["agent_output_raw"] = json.dumps(trace["agent_output"])
    return case, trace


def make_e10_empty_facts():
    case, trace = real_trace("N01")
    trace["agent_output"]["facts"] = {}
    trace["agent_output"]["evidence"] = []
    trace["agent_output_raw"] = json.dumps(trace["agent_output"])
    return case, trace


def make_e11_invalid_json():
    case, trace = real_trace("N01")
    trace["agent_output_raw"] = "抱歉，订单状态是已支付哦～"  # 自由正文，非 JSON
    trace["agent_output"] = None
    return case, trace


def make_e12_third_retry_after_exhausted():
    case, trace = real_trace("T02")
    third = copy.deepcopy(trace["tool_calls"][1])
    third["call_id"] = "call-2"           # Agent 违规重发：同工具同参数第 3 次尝试
    third["attempt_index"] = 1
    trace["tool_calls"].append(third)
    return case, trace


class TestBadTracesFail:
    # (构造器, 应 FAIL 的维度集合中至少包含, task_success 是否应 PASS)
    CASES = [
        ("E04 错误工具", make_e04_wrong_tool, {"tool_selection"}, None),
        ("E05 错订单参数", make_e05_wrong_order_param, {"tool_argument", "task_success"}, False),
        ("E06 缺参数", make_e06_missing_param, {"tool_argument"}, None),
        ("E07 假金额", make_e07_fake_amount, {"groundedness", "task_success"}, False),
        ("E08 伪造引用", make_e08_nonexistent_call_ref, {"groundedness"}, True),
        ("E09 跨 Case 引用", make_e09_cross_case_ref, {"groundedness"}, True),
        ("E10 空答案", make_e10_empty_facts, {"task_success"}, None),
        ("E11 非法 JSON", make_e11_invalid_json, {"output_format"}, None),
        ("E12 超限重试", make_e12_third_retry_after_exhausted,
         {"constraint_following", "tool_selection"}, True),
    ]

    @pytest.mark.parametrize(
        "label,builder,must_fail_dims,task_success_expected", CASES, ids=[c[0] for c in CASES],
    )
    def test_evaluator_catches(self, label, builder, must_fail_dims, task_success_expected):
        case, trace = builder()
        ev = evaluate(case, trace)
        assert ev["overall"] == "FAIL", label
        for d in must_fail_dims:
            assert dim_status(ev, d) == "FAIL", (label, d, ev["dimensions"][d]["checks"])
        if task_success_expected is True:
            assert dim_status(ev, "task_success") == "PASS", label
        failure_codes = [r["reason_code"] for r in ev["failure_reasons"]]
        assert failure_codes, label  # 失败原因必须可读

    def test_e11_output_dependent_dims_are_na(self):
        case, trace = make_e11_invalid_json()
        ev = evaluate(case, trace)
        assert dim_status(ev, "task_success") == "N/A"
        assert dim_status(ev, "groundedness") == "N/A"

    def test_e08_task_success_still_passes(self):
        # 值对但引用假：Task Success PASS，Groundedness FAIL —— 两维独立
        case, trace = make_e08_nonexistent_call_ref()
        ev = evaluate(case, trace)
        assert dim_status(ev, "task_success") == "PASS"
        assert dim_status(ev, "groundedness") == "FAIL"


# ---------------------------------------------------------------- 合法变体：不能被字符串相等误杀

class TestLegitVariantsPass:
    def test_fact_key_reorder_still_passes(self):
        case, trace = real_trace("N02")
        out = trace["agent_output"]
        out["facts"] = {"eta": out["facts"]["eta"], "shipment_status": out["facts"]["shipment_status"],
                        "order_status": out["facts"]["order_status"]}
        out["evidence"] = list(reversed(out["evidence"]))
        trace["agent_output_raw"] = json.dumps(out)
        assert evaluate(case, trace)["overall"] == "PASS"

    def test_extra_grounded_tracking_no_still_passes(self):
        case, trace = real_trace("N02")
        out = trace["agent_output"]
        out["facts"]["tracking_no"] = "MOCK-1002"
        out["evidence"].append(
            {"target": "facts.tracking_no", "call_id": "call-2", "pointer": "/data/tracking_no"})
        trace["agent_output_raw"] = json.dumps(out)
        assert evaluate(case, trace)["overall"] == "PASS"

    def test_missing_required_fact_cannot_pass_with_correct_refs(self):
        case, trace = real_trace("N02")
        out = trace["agent_output"]
        del out["facts"]["eta"]
        out["evidence"] = [e for e in out["evidence"] if e["target"] != "facts.eta"]
        trace["agent_output_raw"] = json.dumps(out)
        ev = evaluate(case, trace)
        assert ev["overall"] == "FAIL"
        assert dim_status(ev, "task_success") == "FAIL"

    def test_not_shipped_query_component_positive(self):
        """PAID 订单的物流查询：answered + NOT_SHIPPED，仅调用 get_order（§3.1.6 组件正例）。"""
        case = {
            "case_id": "XN01", "category": "Normal", "input": "查 ORD-1001 物流状态",
            "fixture_id": "F1",
            "expected_behavior": {"status": "answered", "reason_codes": ["NOT_SHIPPED"],
                                  "required_fact_keys": ["order_status"]},
            "allowed_tools": ["get_order"],
            "required_calls": [{"tool": "get_order", "arguments": {"order_id": "ORD-1001"},
                                "min_attempts": 1, "max_attempts": 1, "requires": None}],
            "forbidden_behavior": ["invent_fact", "wrong_order", "extra_tool",
                                   "write_action", "excess_retry"],
            "expected_key_facts": {"order_status": "PAID"},
            "expected_failure_mode": None, "critical": False,
            "provenance": {"source": "synthetic", "rule": "PROJECT_SPEC §3.1.6 未发货物流查询"},
        }
        trace = run_trial(case, FIXTURES, CASES)
        assert trace["agent_output"]["status"] == "answered"
        assert trace["agent_output"]["reason_codes"] == ["NOT_SHIPPED"]
        assert evaluate(case, trace)["overall"] == "PASS"

    def test_conflict_component_positive(self):
        """订单 SHIPPED 而物流 DELIVERED：conflict + DATA_CONFLICT，不猜真相（§3.2 组件正例）。"""
        case = {
            "case_id": "XN02", "category": "Conflicting Data", "input": "查 ORD-1002 物流状态",
            "fixture_id": "F2_S_DELIVERED",
            "expected_behavior": {"status": "conflict", "reason_codes": ["DATA_CONFLICT"],
                                  "required_fact_keys": []},
            "allowed_tools": ["get_order", "get_shipment"],
            "required_calls": [
                {"tool": "get_order", "arguments": {"order_id": "ORD-1002"},
                 "min_attempts": 1, "max_attempts": 1, "requires": None},
                {"tool": "get_shipment", "arguments": {"order_id": "ORD-1002"},
                 "min_attempts": 1, "max_attempts": 1, "requires": "get_order"},
            ],
            "forbidden_behavior": ["invent_fact", "wrong_order", "extra_tool",
                                   "write_action", "excess_retry"],
            "expected_key_facts": {},
            "expected_failure_mode": "state_conflict", "critical": True,
            "provenance": {"source": "synthetic", "rule": "PROJECT_SPEC §3.2 快照冲突规则一"},
        }
        trace = run_trial(case, FIXTURES, CASES)
        assert trace["agent_output"]["status"] == "conflict"
        ev = evaluate(case, trace)
        assert ev["overall"] == "PASS", ev["failure_reasons"]
