"""Agent 场景测试：六条种子路径端到端合同 + AC07 防答案泄漏控制试验。"""
import copy
import inspect
import json

import pytest

from order_eval.agent import MockAgent
from order_eval.schemas import load_cases, validate_agent_output
from order_eval.tools import Executor, load_fixture_world

FIXTURES = "datasets/fixtures.json"
CASES = "datasets/cases.jsonl"


def load_case(case_id):
    for case in load_cases(CASES):
        if case["case_id"] == case_id:
            return copy.deepcopy(case)
    raise KeyError(case_id)


def run_case(case):
    """按 Runner 的方式预置工具世界并运行 Agent；Agent 只拿 input 与 executor。"""
    world = load_fixture_world(FIXTURES, case["fixture_id"])
    ex = Executor(world)
    result = MockAgent().run(case["input"], ex.execute)
    return result, ex


class TestSeedScenarios:
    def test_n01_status_query_single_call_with_evidence(self):
        case = load_case("N01")
        result, ex = run_case(case)
        out = result["output"]
        assert out["status"] == "answered"
        assert out["facts"] == {"order_status": "PAID"}
        assert out["evidence"] == [
            {"target": "facts.order_status", "call_id": "call-1", "pointer": "/data/status"}
        ]
        assert ex.world.total_attempts == 1

    def test_n02_shipment_two_calls_in_order(self):
        case = load_case("N02")
        result, ex = run_case(case)
        out = result["output"]
        assert out["status"] == "answered"
        assert out["facts"] == {
            "order_status": "SHIPPED", "shipment_status": "IN_TRANSIT", "eta": "2026-09-12",
        }
        assert ex._request_seq == 2  # 先 get_order 后 get_shipment
        assert ex.world.total_attempts == 2
        assert validate_agent_output(out) == []

    def test_i02_missing_id_zero_tool_calls(self):
        case = load_case("I02")
        result, ex = run_case(case)
        out = result["output"]
        assert out["status"] == "clarification"
        assert out["reason_codes"] == ["MISSING_ORDER_ID"]
        assert out["facts"] == {}
        assert out["order_id"] is None
        assert ex._request_seq == 0

    def test_t02_timeout_exhausted_degrades_honestly(self):
        case = load_case("T02")
        result, ex = run_case(case)
        out = result["output"]
        assert out["status"] == "unavailable"
        assert out["reason_codes"] == ["TOOL_UNAVAILABLE"]
        assert out["facts"] == {}
        assert ex.world.total_attempts == 2  # 恰好两次超时尝试

    def test_m01_order_not_found(self):
        case = load_case("M01")
        result, ex = run_case(case)
        out = result["output"]
        assert out["status"] == "not_found"
        assert out["reason_codes"] == ["ORDER_NOT_FOUND"]
        assert out["order_id"] == "ORD-9999"  # 标准化请求 ID，不是编造
        assert out["facts"] == {}

    def test_h02_false_user_amount_not_parroted(self):
        case = load_case("H02")
        result, ex = run_case(case)
        out = result["output"]
        assert out["status"] == "answered"
        # 金额查询至少要求 amount_cents+currency；order_status 是额外有据事实，允许
        assert out["facts"]["amount_cents"] == 12900
        assert out["facts"]["currency"] == "CNY"
        assert "199" not in json.dumps(out, ensure_ascii=False)  # 不复读用户假金额

    def test_all_seed_outputs_pass_schema(self):
        for case_id in ["N01", "N02", "I02", "T02", "M01", "H02"]:
            result, _ = run_case(load_case(case_id))
            errors = validate_agent_output(result["output"])
            assert errors == [], (case_id, errors)


class TestAnswerLeakagePrevention:
    """AC07：Agent 不接收 expected/case_id；换掉 expected 只影响评分，不影响输出。

    注意：fixture_id 属于 Runner 控制的工具世界（环境），改它改变环境是正确行为；
    防泄漏针对的是标准答案（expected_*），对 Agent 永远不可见。
    """

    def test_agent_output_independent_of_expected_values(self):
        case = load_case("N01")
        baseline, _ = run_case(case)
        tampered = copy.deepcopy(case)
        tampered["expected_key_facts"] = {"order_status": "CANCELED"}
        tampered["expected_behavior"]["status"] = "not_found"
        tampered["critical"] = not tampered["critical"]
        after, _ = run_case(tampered)
        assert baseline["output"] == after["output"]

    def test_agent_run_signature_has_no_case_fields(self):
        sig = inspect.signature(MockAgent.run)
        assert list(sig.parameters) == ["self", "user_input", "tool_executor"]

    def test_agent_module_does_not_import_evaluator(self):
        import ast
        import order_eval.agent as agent_mod
        tree = ast.parse(inspect.getsource(agent_mod))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        assert not any(m.split(".")[0] == "evaluator" or m == "order_eval.evaluator"
                       for m in imported), imported
