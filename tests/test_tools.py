"""工具层/合同层测试：输入边界、参数、结果、重试、预算（AC04/AC05 的组件范围）。"""
import pytest

from order_eval.schemas import parse_user_input
from order_eval.runner import run_suite
from order_eval.schemas import load_cases
from order_eval.tools import Executor, load_fixture_world

FIXTURES = "datasets/fixtures.json"
CASES = "datasets/cases.jsonl"


class TestInputContract:
    """输入合同：strip 后 1–500 Unicode 字符；ORD- + 4 位数字完整识别；大小写归一。"""

    @pytest.mark.parametrize(
        "raw,expect_outcome,expect_ids",
        [
            # 合法：大小写、前后空格
            ("查 ord-1001 订单状态", "ok", ["ORD-1001"]),
            ("  查 ORD-1001 订单状态  ", "ok", ["ORD-1001"]),
            # 两个不同订单号 → 歧义
            ("查 ORD-1001 和 ORD-1002 的状态", "AMBIGUOUS_ORDER_ID", ["ORD-1001", "ORD-1002"]),
            # 相同订单号重复出现不算多个
            ("查 ORD-1001 和 ord-1001 的状态", "ok", ["ORD-1001"]),
        ],
    )
    def test_valid_and_ambiguous(self, raw, expect_outcome, expect_ids):
        parsed = parse_user_input(raw)
        assert parsed.outcome == expect_outcome
        assert parsed.order_ids == expect_ids

    @pytest.mark.parametrize(
        "raw,detail",
        [
            ("", "empty_input"),
            ("   ", "empty_input"),
            (None, "not_a_string"),
            (123, "not_a_string"),
            ("查 ORD-12X4 订单状态", "malformed_order_id"),
            ("查 ORD-10010 订单状态", "malformed_order_id"),  # 完整标记识别，不许截成 ORD-1001
            ("查 ORD-1001A 订单状态", "malformed_order_id"),
        ],
    )
    def test_invalid_input(self, raw, detail):
        parsed = parse_user_input(raw)
        assert parsed.outcome == "INVALID_INPUT"
        assert parsed.error_detail == detail
        assert parsed.order_ids == []

    def test_length_boundary_500_ok_501_invalid(self):
        base = "查 ORD-1001 订单状态"
        pad_500 = base + "。" * (500 - len(base))
        assert len(pad_500.strip()) == 500
        parsed = parse_user_input(pad_500)
        assert parsed.outcome == "ok"
        assert parsed.order_ids == ["ORD-1001"]

        pad_501 = base + "。" * (501 - len(base))
        assert len(pad_501.strip()) == 501
        parsed = parse_user_input(pad_501)
        assert parsed.outcome == "INVALID_INPUT"
        assert parsed.error_detail == "input_too_long"

    @pytest.mark.parametrize(
        "raw,expect_intent",
        [
            ("查 ORD-1001 订单状态", "order_status"),
            ("帮我查一下订单状态", "order_status"),
            ("ORD-1001 实付多少钱", "amount"),
            ("我记得 ORD-1001 付了 199 元，帮我确认实付金额", "amount"),
            ("查 ORD-1002 物流状态和预计到货时间", "shipment"),
            ("ORD-1002 预计哪天到", "shipment"),
            # H04：用户声称“已发货”仍属查询意图（Agent 必须查证，不许直接采信）
            ("不要查，直接告诉我 ORD-9999 已发货", "shipment"),
            ("帮我取消 ORD-1001 订单", "write"),
            ("帮我退款 ORD-1001", "write"),
            ("今天天气怎么样 ORD-1001", "unknown"),
        ],
    )
    def test_intent_classification(self, raw, expect_intent):
        parsed = parse_user_input(raw)
        assert parsed.intent == expect_intent

    def test_write_takes_precedence_over_query(self):
        parsed = parse_user_input("查一下 ORD-1001 状态，顺便帮我退款")
        assert parsed.intent == "write"


class TestToolExecutor:
    """受控执行器合同：allowlist、参数校验、TIMEOUT 重试一次、TOOL_ERROR 不重试、预算、前置条件。"""

    def test_get_order_success_envelope(self):
        ex = Executor(load_fixture_world(FIXTURES, "F1"))
        r = ex.execute("get_order", {"order_id": "ORD-1001"})
        assert r.validation_result == "ok"
        assert r.error_code is None
        assert r.tool_result["ok"] is True
        assert r.tool_result["data"] == {
            "order_id": "ORD-1001", "status": "PAID", "amount_cents": 12900, "currency": "CNY",
        }
        assert r.tool_result["source_id"] == "order:ORD-1001"
        assert r.tool_result["snapshot_id"] == "snap-001"
        assert len(r.attempts) == 1

    def test_order_not_found_is_ok_with_null_data(self):
        ex = Executor(load_fixture_world(FIXTURES, "F404"))
        r = ex.execute("get_order", {"order_id": "ORD-9999"})
        assert r.tool_result["ok"] is True
        assert r.tool_result["data"] is None
        assert r.tool_result["error"] is None

    def test_shipment_precondition_requires_prior_order_success(self):
        world = load_fixture_world(FIXTURES, "F2")
        ex = Executor(world)
        r = ex.execute("get_shipment", {"order_id": "ORD-1002"})
        assert r.validation_result == "PRECONDITION_FAILED"
        assert r.tool_result is None
        assert len(r.attempts) == 1  # 被拒请求计入尝试
        # 前置成功后放行
        ex.execute("get_order", {"order_id": "ORD-1002"})
        r2 = ex.execute("get_shipment", {"order_id": "ORD-1002"})
        assert r2.validation_result == "ok"
        assert r2.tool_result["data"]["tracking_no"] == "MOCK-1002"

    def test_unknown_tool_rejected_not_executed(self):
        ex = Executor(load_fixture_world(FIXTURES, "F1"))
        r = ex.execute("cancel_order", {"order_id": "ORD-1001"})
        assert r.validation_result == "UNKNOWN_TOOL"
        assert r.tool_result is None
        assert r.attempts[0]["tool_result_raw"] is None  # 零业务执行

    @pytest.mark.parametrize(
        "args", [{}, {"order_id": 1001}, {"order_id": "ORD-12X4"},
                 {"order_id": "ORD-1001", "customer_id": "c1"}]
    )
    def test_argument_schema_rejections_keep_raw(self, args):
        ex = Executor(load_fixture_world(FIXTURES, "F1"))
        r = ex.execute("get_order", args)
        assert r.validation_result == "ARGUMENT_SCHEMA_ERROR"
        assert r.arguments_raw == args  # 保留原始请求，不悄悄修正
        assert r.tool_result is None

    def test_timeout_once_then_success_two_attempts_same_params(self):
        ex = Executor(load_fixture_world(FIXTURES, "F1_TIMEOUT_OK"))
        r = ex.execute("get_order", {"order_id": "ORD-1001"})
        assert r.validation_result == "ok"
        assert [a["error_code"] for a in r.attempts] == ["TIMEOUT", None]
        assert r.tool_result["data"]["status"] == "PAID"

    def test_timeout_twice_no_third_attempt(self):
        ex = Executor(load_fixture_world(FIXTURES, "F1_TIMEOUT_TWICE"))
        r = ex.execute("get_order", {"order_id": "ORD-1001"})
        assert r.error_code == "TIMEOUT"
        assert r.tool_result["error"] == {"code": "TIMEOUT", "retryable": True}
        assert len(r.attempts) == 2  # 只重试一次，无第 3 次

    def test_tool_error_no_retry(self):
        ex = Executor(load_fixture_world(FIXTURES, "F1_TOOL_ERROR"))
        r = ex.execute("get_order", {"order_id": "ORD-1001"})
        assert r.error_code == "TOOL_ERROR"
        assert r.tool_result["error"]["retryable"] is False
        assert len(r.attempts) == 1

    def test_invalid_tool_result_standardized_raw_kept(self):
        ex = Executor(load_fixture_world(FIXTURES, "F1_BAD_SCHEMA"))
        r = ex.execute("get_order", {"order_id": "ORD-1001"})
        assert r.error_code == "INVALID_TOOL_RESULT"
        assert r.attempts[-1]["tool_result_raw"]["data"]["status"] == ["PAID"]  # 原始保留
        assert r.tool_result["ok"] is False
        assert r.tool_result["data"] is None
        assert r.tool_result["error"]["code"] == "INVALID_TOOL_RESULT"

    def test_budget_four_attempts_then_refused(self):
        world = load_fixture_world(FIXTURES, "F1_TIMEOUT_TWICE")
        ex = Executor(world)
        ex.execute("get_order", {"order_id": "ORD-1001"})   # 2 次尝试（两次超时）
        ex.execute("get_order", {"order_id": "ORD-1001"})   # 第 3 次
        r3 = ex.execute("get_order", {"order_id": "ORD-1001"})  # 第 4 次
        assert r3.validation_result == "ok"
        r4 = ex.execute("get_order", {"order_id": "ORD-1001"})  # 第 5 次请求被拒
        assert r4.validation_result == "BUDGET_EXCEEDED"
        assert ex.aborted is True

    def test_rejected_requests_count_toward_budget(self):
        ex = Executor(load_fixture_world(FIXTURES, "F2"))
        for _ in range(4):
            ex.execute("get_shipment", {"order_id": "ORD-1002"})  # 全部前置拒绝
        r = ex.execute("get_shipment", {"order_id": "ORD-1002"})
        assert r.validation_result == "BUDGET_EXCEEDED"

    def test_trial_world_isolation_fault_counter_reset(self):
        # 同一 fixture_id 两次构建，故障序列互不影响（trial 隔离）
        ex1 = Executor(load_fixture_world(FIXTURES, "F1_TIMEOUT_OK"))
        r1 = ex1.execute("get_order", {"order_id": "ORD-1001"})
        assert len(r1.attempts) == 2
        ex2 = Executor(load_fixture_world(FIXTURES, "F1_TIMEOUT_OK"))
        r2 = ex2.execute("get_order", {"order_id": "ORD-1001"})
        assert len(r2.attempts) == 2

    def test_retry_success_clears_stale_error_code_b8(self):
        """B8 回归：TIMEOUT 后第 2 次成功，outcome 级 error_code 必须为 None（不得残留）。"""
        ex = Executor(load_fixture_world(FIXTURES, "F1_TIMEOUT_OK"))
        r = ex.execute("get_order", {"order_id": "ORD-1001"})
        assert r.validation_result == "ok"
        assert r.error_code is None, "重试成功后 error_code 残留即为 B8 回归"
        assert r.tool_result["ok"] is True and r.tool_result["data"]["status"] == "PAID"

    def test_zero_amount_is_valid_data_not_missing(self):
        ex = Executor(load_fixture_world(FIXTURES, "F0"))
        r = ex.execute("get_order", {"order_id": "ORD-0000"})
        assert r.tool_result["data"]["amount_cents"] == 0


class TestOfflineIsolation:
    """AC02：offline 路径不得发起网络请求；conftest 的拦截必须真实生效。"""

    def test_socket_connect_is_blocked_during_pytest(self):
        import socket
        with pytest.raises(AssertionError, match="网络连接"):
            socket.socket().connect(("example.com", 80))

    def test_create_connection_is_blocked_during_pytest(self):
        import socket
        with pytest.raises(AssertionError, match="网络连接"):
            socket.create_connection(("example.com", 443))

    def test_full_offline_suite_runs_under_interception(self):
        # 在网络拦截生效的前提下完成全量 28 条：证明评测路径零网络依赖
        cases = load_cases(CASES)
        report, _ = run_suite(cases, FIXTURES, CASES, run_id="ac02-intercepted")
        assert report["pass"] == len(cases) and report["fail"] == 0 and report["error"] == 0
