"""合同与验证：用户输入、工具请求/返回、AgentOutput、Eval Case（PROJECT_SPEC §3/§4/§5.1）。"""
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from jsonschema import Draft202012Validator

# ---------------------------------------------------------------- 枚举常量

ORDER_STATUSES = ["PAID", "SHIPPED", "DELIVERED", "CANCELED"]
SHIPMENT_STATUSES = ["IN_TRANSIT", "DELIVERED"]
ALLOWED_FACT_KEYS = [
    "order_status", "amount_cents", "currency",
    "shipment_status", "tracking_no", "eta", "delivered_at",
]
REASON_CODES = [
    "MISSING_ORDER_ID", "AMBIGUOUS_ORDER_ID", "INVALID_INPUT",
    "UNSUPPORTED_ACTION", "UNSUPPORTED_QUERY",
    "NOT_SHIPPED", "ORDER_NOT_FOUND", "TOOL_UNAVAILABLE",
    "INVALID_TOOL_RESULT", "SHIPMENT_NOT_FOUND", "ETA_NOT_AVAILABLE",
    "AMOUNT_NOT_AVAILABLE", "DATA_CONFLICT",
]
# 原因码常量（与上表一致，供 Agent/Evaluator 引用）
MISSING_ORDER_ID = "MISSING_ORDER_ID"
AMBIGUOUS_ORDER_ID = "AMBIGUOUS_ORDER_ID"
INVALID_INPUT = "INVALID_INPUT"
UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
UNSUPPORTED_QUERY = "UNSUPPORTED_QUERY"
NOT_SHIPPED = "NOT_SHIPPED"
ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
SHIPMENT_NOT_FOUND = "SHIPMENT_NOT_FOUND"
ETA_NOT_AVAILABLE = "ETA_NOT_AVAILABLE"
AMOUNT_NOT_AVAILABLE = "AMOUNT_NOT_AVAILABLE"
DATA_CONFLICT = "DATA_CONFLICT"
ALLOWED_STATUSES = [
    "answered", "partial", "clarification", "invalid_input",
    "not_found", "unavailable", "conflict", "unsupported",
]
FORBIDDEN_BEHAVIORS = [
    "invent_fact", "wrong_order", "extra_tool", "write_action",
    "excess_retry", "any_tool_call", "obey_tool_text",
]
CATEGORIES = [
    "Normal", "Boundary", "Invalid Input", "Tool Failure",
    "Missing Data", "Conflicting Data", "Hallucination Trap",
]

# 意图（最小关键词规则，公开边界；§3.1.7 不承诺任意自然语言覆盖）
INTENT_WRITE = "write"
INTENT_ORDER_STATUS = "order_status"
INTENT_AMOUNT = "amount"
INTENT_SHIPMENT = "shipment"
INTENT_UNKNOWN = "unknown"

_WRITE_KEYWORDS = ["取消", "退款", "退货"]
_SHIPMENT_KEYWORDS = ["物流", "快递", "到货", "送货", "收货", "预计哪天", "哪天到", "发货"]
_AMOUNT_KEYWORDS = ["多少钱", "实付", "金额", "付了", "价格", "费用"]
_STATUS_KEYWORDS = ["订单状态", "状态"]

# 订单号：完整标记识别。严格 token 前后不能是字母/数字；不许把 ORD-10010 截成 ORD-1001。
_STRICT_ID_RE = re.compile(r"(?<![A-Za-z0-9])[Oo][Rr][Dd]-[0-9]{4}(?![A-Za-z0-9])")
_LOOSE_ID_RE = re.compile(r"(?<![A-Za-z0-9])[Oo][Rr][Dd]-[A-Za-z0-9]+")

INPUT_MAX_CHARS = 500

# 工具定义（执行器据此做 allowlist 与参数/结果校验；禁止动态 eval 工具名）
TOOL_SPECS = {
    "get_order": {
        "args_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["order_id"],
            "properties": {"order_id": {"type": "string", "pattern": "^ORD-[0-9]{4}$"}},
        },
        "data_required": ["order_id", "status", "amount_cents", "currency"],
        "source_id_prefix": "order",
    },
    "get_shipment": {
        "args_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["order_id"],
            "properties": {"order_id": {"type": "string", "pattern": "^ORD-[0-9]{4}$"}},
        },
        "data_required": ["order_id", "status", "tracking_no", "eta", "delivered_at", "note"],
        "source_id_prefix": "shipment",
    },
}
UNKNOWN_TOOL = "UNKNOWN_TOOL"
ARGUMENT_SCHEMA_ERROR = "ARGUMENT_SCHEMA_ERROR"
PRECONDITION_FAILED = "PRECONDITION_FAILED"
BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
TIMEOUT = "TIMEOUT"
TOOL_ERROR = "TOOL_ERROR"
INVALID_TOOL_RESULT = "INVALID_TOOL_RESULT"

# 事实字段 → 唯一合法来源工具 + envelope 内 JSON Pointer（§4：不能引用另一工具的路径）
FACT_SOURCE = {
    "order_status": ("get_order", "/data/status"),
    "amount_cents": ("get_order", "/data/amount_cents"),
    "currency": ("get_order", "/data/currency"),
    "shipment_status": ("get_shipment", "/data/status"),
    "tracking_no": ("get_shipment", "/data/tracking_no"),
    "eta": ("get_shipment", "/data/eta"),
    "delivered_at": ("get_shipment", "/data/delivered_at"),
}

# 执行预算（§3.3）
MAX_TOOL_ATTEMPTS = 4
MAX_MODEL_REQUESTS = 6
TIMEOUT_MAX_RETRIES = 1  # 仅 TIMEOUT 可重试一次

# ---------------------------------------------------------------- 用户输入解析


@dataclass
class ParsedInput:
    raw: Any
    outcome: str  # "ok" | "INVALID_INPUT" | "AMBIGUOUS_ORDER_ID"
    intent: Optional[str] = None
    order_ids: list = field(default_factory=list)  # 严格合法、大写、去重、保序
    error_detail: Optional[str] = None  # empty_input / not_a_string / input_too_long / malformed_order_id


def classify_intent(text: str) -> str:
    if any(k in text for k in _WRITE_KEYWORDS):
        return INTENT_WRITE
    if any(k in text for k in _SHIPMENT_KEYWORDS):
        return INTENT_SHIPMENT
    if any(k in text for k in _AMOUNT_KEYWORDS):
        return INTENT_AMOUNT
    if any(k in text for k in _STATUS_KEYWORDS):
        return INTENT_ORDER_STATUS
    return INTENT_UNKNOWN


def parse_user_input(raw: Any) -> ParsedInput:
    """§3.1：非字符串/空/超长 → invalid_input；显式格式错误订单号 → invalid_input；
    写操作优先于查询（既含查询又要求写操作整体拒绝）。"""
    if not isinstance(raw, str):
        return ParsedInput(raw, "INVALID_INPUT", error_detail="not_a_string")
    text = raw.strip()
    if len(text) == 0:
        return ParsedInput(raw, "INVALID_INPUT", error_detail="empty_input")
    if len(text) > INPUT_MAX_CHARS:
        return ParsedInput(raw, "INVALID_INPUT", error_detail="input_too_long")

    # 显式订单号：宽松 token 存在而严格 token 缺失 → 格式错误（不截断）
    loose = _LOOSE_ID_RE.findall(text)
    strict = _STRICT_ID_RE.findall(text)
    if len(loose) > len(strict):
        return ParsedInput(raw, "INVALID_INPUT", error_detail="malformed_order_id")

    ids: list = []
    for m in _STRICT_ID_RE.finditer(text):
        norm = m.group(0).upper()
        if norm not in ids:
            ids.append(norm)

    if any(k in text for k in _WRITE_KEYWORDS):
        intent = INTENT_WRITE
    else:
        intent = classify_intent(text)

    if len(ids) > 1:
        return ParsedInput(raw, "AMBIGUOUS_ORDER_ID", intent=intent, order_ids=ids)
    return ParsedInput(raw, "ok", intent=intent, order_ids=ids)


# ---------------------------------------------------------------- AgentOutput 合同

AGENT_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "order_id", "facts", "reason_codes", "evidence"],
    "properties": {
        "status": {"enum": ALLOWED_STATUSES},
        "order_id": {"type": ["string", "null"], "pattern": "^ORD-[0-9]{4}$"},
        "facts": {
            "type": "object",
            "additionalProperties": False,
            "propertyNames": {"enum": ALLOWED_FACT_KEYS},
            "properties": {
                "order_status": {"enum": ORDER_STATUSES},
                "amount_cents": {"type": "integer", "minimum": 0},
                "currency": {"const": "CNY"},
                "shipment_status": {"enum": SHIPMENT_STATUSES},
                "tracking_no": {"type": "string"},
                "eta": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                "delivered_at": {"type": "string"},
            },
        },
        "reason_codes": {
            "type": "array",
            "items": {"enum": REASON_CODES},
            "uniqueItems": True,
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["target", "call_id", "pointer"],
                "properties": {
                    "target": {"type": "string", "pattern": "^facts\\.[a-z_]+$"},
                    "call_id": {"type": "string"},
                    "pointer": {"type": "string", "pattern": "^/"},
                },
            },
        },
    },
}

_output_validator = Draft202012Validator(AGENT_OUTPUT_SCHEMA)


def validate_agent_output(output: Any) -> list:
    """返回 jsonschema 错误消息列表；空列表 = 合法。"""
    return [e.message for e in sorted(_output_validator.iter_errors(output), key=lambda e: e.path)]


# ---------------------------------------------------------------- Eval Case 合同

CASE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "case_id", "category", "input", "fixture_id", "expected_behavior",
        "allowed_tools", "required_calls", "forbidden_behavior",
        "expected_key_facts", "expected_failure_mode", "critical", "provenance",
    ],
    "properties": {
        "case_id": {"type": "string", "pattern": "^[A-Z]+[0-9]{2}$"},
        "category": {"enum": CATEGORIES},
        "input": {"type": "string"},
        "fixture_id": {"type": "string"},
        "expected_behavior": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "reason_codes", "required_fact_keys"],
            "properties": {
                "status": {"enum": ALLOWED_STATUSES},
                "reason_codes": {"type": "array", "items": {"enum": REASON_CODES}, "uniqueItems": True},
                "required_fact_keys": {"type": "array", "items": {"enum": ALLOWED_FACT_KEYS}, "uniqueItems": True},
            },
        },
        "allowed_tools": {"type": "array", "items": {"enum": list(TOOL_SPECS)}, "uniqueItems": True},
        "required_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tool", "arguments", "min_attempts", "max_attempts"],
                "properties": {
                    "tool": {"enum": list(TOOL_SPECS)},
                    "arguments": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["order_id"],
                        "properties": {"order_id": {"type": "string", "pattern": "^ORD-[0-9]{4}$"}},
                    },
                    "min_attempts": {"type": "integer", "minimum": 0},
                    "max_attempts": {"type": "integer", "minimum": 1},
                    "requires": {"enum": [None, "get_order"]},
                },
            },
        },
        "forbidden_behavior": {"type": "array", "items": {"enum": FORBIDDEN_BEHAVIORS}, "uniqueItems": True},
        "expected_key_facts": {"type": "object"},
        "expected_failure_mode": {"type": ["string", "null"]},
        "critical": {"type": "boolean"},
        "provenance": {"type": "object"},
    },
}

_case_validator = Draft202012Validator(CASE_SCHEMA)


def validate_case(case: Any) -> list:
    return [e.message for e in sorted(_case_validator.iter_errors(case), key=lambda e: e.path)]


def load_cases(path) -> list:
    cases = []
    seen = set()
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            if is_v2_case(case):
                errors = validate_case_v2(case)
                kind = "v2"
            else:
                errors = validate_case(case)
                kind = "v1"
            if errors:
                raise ValueError(f"cases.jsonl 第 {lineno} 行 {kind} schema 不合法: {errors}")
            if case["case_id"] in seen:
                raise ValueError(f"cases.jsonl 第 {lineno} 行 case_id 重复: {case['case_id']}")
            seen.add(case["case_id"])
            cases.append(case)
    return cases


# ---------------------------------------------------------------- 冲突检测（§3.2，Agent 与评测共享的纯函数）


def detect_conflicts(order_data: Optional[dict], shipment_data: Optional[dict]) -> list:
    """同一快照下的合成业务冲突规则；返回冲突描述列表。"""
    conflicts = []
    if order_data and shipment_data:
        o, s = order_data.get("status"), shipment_data.get("status")
        if o == "SHIPPED" and s == "DELIVERED":
            conflicts.append({"rule": "order_shipped_vs_shipment_delivered",
                              "fields": ["order_status", "shipment_status"]})
        if o == "DELIVERED" and s == "IN_TRANSIT":
            conflicts.append({"rule": "order_delivered_vs_shipment_in_transit",
                              "fields": ["order_status", "shipment_status"]})
        if s == "IN_TRANSIT" and shipment_data.get("delivered_at"):
            conflicts.append({"rule": "in_transit_with_delivered_at",
                              "fields": ["shipment_status", "delivered_at"]})
    return conflicts


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------- Expansion v2 数据合同
# 独立扩展数据集（datasets/expansion/）的 12 字段 schema；与 v1 CASE_SCHEMA 并存，
# 由 load_cases 按行内字段自动分派。v1 冻结合同不受影响。

V2_CATEGORIES = [
    "Normal", "Boundary", "Abnormal", "ToolError", "ArgumentError", "Timeout",
    "DirtyData", "Hallucination", "MultiTurnContext", "InstructionConflict",
    "PromptInjection", "AgentLoop", "Retry", "Fallback", "MemoryInconsistency",
]
V2_DIFFICULTIES = ["easy", "medium", "hard"]
V2_SEVERITIES = ["minor", "major", "critical"]
V2_FORBIDDEN_BEHAVIORS = FORBIDDEN_BEHAVIORS + [
    "fabricate_eta", "fabricate_amount", "fabricate_status", "fabricate_tracking_no",
    "fabricate_currency", "obey_user_injection", "precommit_unverified",
    "skip_verification", "adopt_memory_value", "resolve_wrong_order",
    "unbounded_retry", "call_before_precondition",
]

V2_CASE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "case_id", "category", "difficulty", "user_input", "context", "tool_state",
        "expected_behavior", "forbidden_behavior", "expected_tool", "expected_args",
        "evaluation_rules", "severity",
    ],
    "properties": {
        "case_id": {"type": "string", "pattern": "^R01-[A-Z]{3}-[0-9]{3}$"},
        "category": {"enum": V2_CATEGORIES},
        "difficulty": {"enum": V2_DIFFICULTIES},
        "severity": {"enum": V2_SEVERITIES},
        "user_input": {"type": "string"},
        "context": {
            "type": "object",
            "additionalProperties": False,
            "required": ["prior_turns", "session_facts"],
            "properties": {
                "prior_turns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["role", "content"],
                        "properties": {
                            "role": {"enum": ["user", "assistant"]},
                            "content": {"type": "string"},
                        },
                    },
                },
                "session_facts": {"type": "object"},
            },
        },
        "tool_state": {
            "type": "object",
            "additionalProperties": False,
            "required": ["snapshot_id", "orders", "shipments", "faults", "injected"],
            "properties": {
                "snapshot_id": {"type": "string"},
                "orders": {"type": "object"},
                "shipments": {"type": "object"},
                "faults": {
                    "type": "object",
                    "propertyNames": {"enum": list(TOOL_SPECS)},
                    "additionalProperties": {
                        "type": "array",
                        "items": {"enum": ["timeout", "error", "ok"]},
                    },
                },
                "injected": {"type": "array", "items": {"type": "string"}},
            },
        },
        "expected_behavior": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "reason_codes", "required_fact_keys"],
            "properties": {
                "status": {"enum": ALLOWED_STATUSES},
                "reason_codes": {"type": "array", "items": {"enum": REASON_CODES}, "uniqueItems": True},
                "required_fact_keys": {"type": "array", "items": {"enum": ALLOWED_FACT_KEYS}, "uniqueItems": True},
            },
        },
        "forbidden_behavior": {"type": "array", "items": {"enum": V2_FORBIDDEN_BEHAVIORS}, "uniqueItems": True},
        "expected_tool": {"type": "array", "items": {"enum": list(TOOL_SPECS)}, "uniqueItems": True},
        "expected_args": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tool", "arguments", "min_attempts", "max_attempts"],
                "properties": {
                    "tool": {"enum": list(TOOL_SPECS)},
                    "arguments": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["order_id"],
                        "properties": {"order_id": {"type": "string", "pattern": "^ORD-[0-9]{4}$"}},
                    },
                    "min_attempts": {"type": "integer", "minimum": 0},
                    "max_attempts": {"type": "integer", "minimum": 1},
                    "requires": {"enum": [None, "get_order"]},
                },
            },
        },
        "evaluation_rules": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["rule", "mode", "params"],
                "properties": {
                    "rule": {"type": "string"},
                    "mode": {"enum": ["rule_based", "llm_judge"]},
                    "params": {"type": "object"},
                },
            },
        },
        "expected_key_facts": {"type": "object"},
        "provenance": {"type": "object"},
    },
}

_v2_case_validator = Draft202012Validator(V2_CASE_SCHEMA)


def validate_case_v2(case: Any) -> list:
    return [e.message for e in sorted(_v2_case_validator.iter_errors(case), key=lambda e: e.path)]


def is_v2_case(case: Any) -> bool:
    """行内判别：v2 expansion case 内嵌 tool_state；v1 用 fixture_id 引用。"""
    return isinstance(case, dict) and "tool_state" in case


def needs_context(case: dict) -> bool:
    """该 case 是否依赖会话上下文（多轮/记忆）。当前 MockAgent 无会话状态，
    此类 case 由 runner 跳过并计入报告，不伪装成执行失败。"""
    if not is_v2_case(case):
        return False
    ctx = case.get("context") or {}
    return bool(ctx.get("prior_turns") or ctx.get("session_facts"))
