"""MockAgent：确定性规则参考实现（PROJECT_SPEC §2 offline 模式 / §4 AgentOutput）。

接口约束（AC07）：run(user_input, tool_executor)，不接收也不读取 case_id/expected/fixture_id；
不 import evaluator。意图识别为最小关键词规则，边界见 schemas.py 常量与 README。
"""
import json
import re
from typing import Callable, Optional

from order_eval.schemas import (
    AMBIGUOUS_ORDER_ID,
    FACT_SOURCE,
    INTENT_AMOUNT,
    INTENT_ORDER_STATUS,
    INTENT_SHIPMENT,
    INTENT_UNKNOWN,
    INTENT_WRITE,
    INVALID_TOOL_RESULT,
    ParsedInput,
    detect_conflicts,
    parse_user_input,
)
from order_eval.tools import (
    ARGUMENT_SCHEMA_ERROR,
    BUDGET_EXCEEDED,
    PRECONDITION_FAILED,
    RequestOutcome,
    TIMEOUT,
    TOOL_ERROR,
    UNKNOWN_TOOL,
)

_ETA_ASK_KEYWORDS = ["预计", "哪天", "几号", "到货时间", "eta"]
_ETA_FORMAT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REJECTED = (UNKNOWN_TOOL, ARGUMENT_SCHEMA_ERROR, PRECONDITION_FAILED, BUDGET_EXCEEDED)


def _ev(key: str, call_id: str) -> dict:
    tool, pointer = FACT_SOURCE[key]
    return {"target": f"facts.{key}", "call_id": call_id, "pointer": pointer}


class MockAgent:
    version = "mock-0.2"  # 0.2：脏 eta（格式非法）按缺失处理，见 BUGFIX_LOG B10

    def run(self, user_input, tool_executor: Callable[..., RequestOutcome]) -> dict:
        """返回 {"output": AgentOutput dict, "model_requests": int, "steps": list}。

        tool_executor(tool_name, arguments) 由 Runner 预置工具世界后注入。
        """
        parsed = parse_user_input(user_input)
        out = self._answer(parsed, tool_executor)
        return {
            "output": out,
            "model_requests": 1,  # offline Mock 单次决策；无真实模型请求
            "steps": [],
        }

    # ------------------------------------------------------------------

    def _answer(self, parsed: ParsedInput, tool_executor) -> dict:
        order_id = parsed.order_ids[0] if len(parsed.order_ids) == 1 else None

        def _out(status, facts, reasons, evidence, oid=order_id):
            return {
                "status": status,
                "order_id": oid,
                "facts": facts,
                "reason_codes": reasons,
                "evidence": evidence,
            }

        # ---- 输入合同分支（零工具调用）----
        if parsed.outcome == "INVALID_INPUT":
            return _out("invalid_input", {}, ["INVALID_INPUT"], [], oid=None)
        if parsed.outcome == "AMBIGUOUS_ORDER_ID":
            return _out("clarification", {}, ["AMBIGUOUS_ORDER_ID"], [], oid=None)
        if parsed.intent == INTENT_WRITE:
            return _out("unsupported", {}, ["UNSUPPORTED_ACTION"], [])
        if parsed.intent == INTENT_UNKNOWN:
            return _out("unsupported", {}, ["UNSUPPORTED_QUERY"], [])
        if not parsed.order_ids:
            return _out("clarification", {}, ["MISSING_ORDER_ID"], [], oid=None)

        # ---- 查询分支：先查订单（§3.1.6）----
        target = parsed.order_ids[0]
        order_req = tool_executor("get_order", {"order_id": target})
        branch = self._order_branch(order_req, target)
        if branch is not None:  # 订单层失败/缺失，直接定论
            return branch

        order_data = order_req.tool_result["data"]
        facts = {}
        evidence = [_ev("order_status", order_req.call_id)]
        facts["order_status"] = order_data["status"]

        if parsed.intent == INTENT_ORDER_STATUS:
            return _out("answered", facts, [], evidence)

        if parsed.intent == INTENT_AMOUNT:
            return self._amount_answer(order_data, order_req.call_id, evidence, _out)

        return self._shipment_answer(parsed, order_data, order_req.call_id, facts,
                                     evidence, target, tool_executor, _out)

    # ------------------------------------------------------------------

    def _order_branch(self, req: RequestOutcome, order_id: str) -> Optional[dict]:
        """get_order 失败/缺失时返回最终 AgentOutput；成功返回 None。"""
        if req.validation_result in _REJECTED:
            return {"status": "unavailable", "order_id": order_id, "facts": {},
                    "reason_codes": ["TOOL_UNAVAILABLE"], "evidence": []}
        code = req.error_code
        if code == TIMEOUT or code == TOOL_ERROR:
            return {"status": "unavailable", "order_id": order_id, "facts": {},
                    "reason_codes": ["TOOL_UNAVAILABLE"], "evidence": []}
        if code == INVALID_TOOL_RESULT:
            return {"status": "unavailable", "order_id": order_id, "facts": {},
                    "reason_codes": ["INVALID_TOOL_RESULT"], "evidence": []}
        if req.tool_result["data"] is None:  # ok=true,data=null：与故障区分
            return {"status": "not_found", "order_id": order_id, "facts": {},
                    "reason_codes": ["ORDER_NOT_FOUND"], "evidence": []}
        return None

    def _amount_answer(self, order_data: dict, call_id: str, evidence: list, _out) -> dict:
        # 显式区分 None 与 0：0 是合法金额，不是缺失
        amount = order_data.get("amount_cents")
        currency = order_data.get("currency")
        if amount is not None and currency is not None:
            facts = {
                "order_status": order_data["status"],
                "amount_cents": amount,
                "currency": currency,
            }
            ev = evidence + [_ev("amount_cents", call_id), _ev("currency", call_id)]
            return _out("answered", facts, [], ev)
        facts = {"order_status": order_data["status"]}
        ev = list(evidence)
        if currency is not None:
            facts["currency"] = currency
            ev.append(_ev("currency", call_id))
        return _out("partial", facts, ["AMOUNT_NOT_AVAILABLE"], ev)

    def _shipment_answer(self, parsed, order_data, order_call_id, facts, evidence,
                         target, tool_executor, _out) -> dict:
        order_status = order_data["status"]
        if order_status in ("PAID", "CANCELED"):
            # 未发货：已知订单状态 + NOT_SHIPPED，无物流调用（§3.1.6）
            return _out("answered", {"order_status": order_status}, ["NOT_SHIPPED"], evidence)

        ship_req = tool_executor("get_shipment", {"order_id": target})
        if ship_req.validation_result in _REJECTED or ship_req.error_code in (TIMEOUT, TOOL_ERROR):
            return _out("partial", {"order_status": order_status}, ["TOOL_UNAVAILABLE"], evidence)
        if ship_req.error_code == INVALID_TOOL_RESULT:
            return _out("partial", {"order_status": order_status}, ["INVALID_TOOL_RESULT"], evidence)
        ship_data = ship_req.tool_result["data"]
        if ship_data is None:
            return _out("partial", {"order_status": order_status}, ["SHIPMENT_NOT_FOUND"], evidence)

        conflicts = detect_conflicts(order_data, ship_data)
        if conflicts:
            conf_evidence = [_ev("order_status", order_call_id),
                             _ev("shipment_status", ship_req.call_id)]
            if any(c["rule"] == "in_transit_with_delivered_at" for c in conflicts):
                conf_evidence.append(_ev("delivered_at", ship_req.call_id))
            return _out("conflict", {}, ["DATA_CONFLICT"], conf_evidence)

        facts = {"order_status": order_status, "shipment_status": ship_data["status"]}
        ev = [_ev("order_status", order_call_id), _ev("shipment_status", ship_req.call_id)]
        eta = ship_data.get("eta")
        # eta 必须符合输出合同格式（§4 pattern ^\d{4}-\d{2}-\d{2}$）：脏值按缺失处理，
        # 否则输出必然违反 AgentOutput 合同（评测器在脏 eta 数据上发现的缺陷）
        eta_valid = eta is not None and _ETA_FORMAT_RE.fullmatch(str(eta))
        asked_eta = any(k in parsed.raw for k in _ETA_ASK_KEYWORDS)
        if eta_valid:
            facts["eta"] = eta
            ev.append(_ev("eta", ship_req.call_id))
            return _out("answered", facts, [], ev)
        if asked_eta:
            return _out("partial", facts, ["ETA_NOT_AVAILABLE"], ev)
        return _out("answered", facts, [], ev)


def render_output_raw(output: dict) -> str:
    """结构化答案的“可见最终响应”形式；解析失败场景由评测反例单独构造。"""
    return json.dumps(output, ensure_ascii=False)
