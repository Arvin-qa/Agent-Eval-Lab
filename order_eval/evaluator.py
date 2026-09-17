"""六维 Rule-based Evaluator（PROJECT_SPEC §6/§7）。

顺序：Trace 完整性 → 输出格式 → 工具选择/参数 → 事实来源 → 业务结果 → 约束 → 聚合。
只读取冻结 Case 与完整 Trace；可共享 schema 定义，但不调用 Agent 的决策函数计算标准答案。
N/A 规则（§6.1）：输出解析失败时仅 task_success/groundedness 记 N/A（Case 仍 FAIL）；
零调用且无需调用时 tool_argument 记 N/A。
"""
import json

from jsonschema import Draft202012Validator

from order_eval.schemas import (
    FACT_SOURCE,
    MAX_TOOL_ATTEMPTS,
    TIMEOUT_MAX_RETRIES,
    TOOL_SPECS,
    canonical_json,
    parse_user_input,
    validate_agent_output,
)

EVALUATOR_VERSION = "0.2"

DIMENSIONS = [
    "task_success", "tool_selection", "tool_argument",
    "groundedness", "output_format", "constraint_following",
]
READ_ONLY_TOOLS = set(TOOL_SPECS)
_TRACE_REQUIRED_KEYS = [
    "trace_version", "case_id", "execution_status", "tool_calls",
    "agent_output_raw", "agent_output", "user_input",
]

# Validate the fields consumed by scoring, including nested call records. Raw
# rejected arguments are deliberately unrestricted: they are business evidence.
_CALL_SCHEMA = {
    "type": "object",
    "required": ["call_id", "selected_tool", "arguments_raw", "tool_arguments",
                 "validation_result", "tool_result", "error_code"],
    "properties": {
        "call_id": {"type": "string", "minLength": 1},
        "selected_tool": {"type": "string", "minLength": 1},
        "tool_arguments": {"type": ["object", "null"],
                           "properties": {"order_id": {"type": "string"}}},
        "validation_result": {"enum": ["ok", "UNKNOWN_TOOL", "ARGUMENT_SCHEMA_ERROR",
                                        "PRECONDITION_FAILED", "BUDGET_EXCEEDED"]},
        "error_code": {"type": ["string", "null"]},
        "tool_result": {
            "type": ["object", "null"], "required": ["ok", "data"],
            "properties": {"ok": {"type": "boolean"},
                           "data": {"type": ["object", "null"]}},
        },
    },
    "allOf": [{
        "if": {"properties": {"validation_result": {"const": "ok"}}},
        "then": {"properties": {
            "tool_arguments": {"type": "object", "required": ["order_id"]},
            "tool_result": {"type": "object"},
        }},
    }],
}
_trace_validator = Draft202012Validator({
    "type": "object", "required": _TRACE_REQUIRED_KEYS,
    "properties": {
        "trace_version": {"const": "0.1"},
        "case_id": {"type": "string"}, "user_input": {"type": "string"},
        "execution_status": {"enum": ["completed", "error", "aborted"]},
        "tool_calls": {"type": "array", "items": _CALL_SCHEMA},
        "agent_output_raw": {"type": ["string", "null"]},
    },
})


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def evaluate(case: dict, trace: dict) -> dict:
    """evaluate(case, trace) → CaseEvaluation dict（每维 PASS/FAIL/N/A + checks + failure_reasons）。"""
    dims = {d: {"status": None, "checks": []} for d in DIMENSIONS}
    reasons: list = []

    def check(dim, check_id, ok, expected, actual, message=None, refs=None):
        dims[dim]["checks"].append(
            {"check_id": check_id, "ok": bool(ok), "expected": expected, "actual": actual})
        if not ok:
            dims[dim]["status"] = "FAIL"
            reasons.append({
                "dimension": dim,
                "reason_code": check_id,
                "message": message or f"{check_id}: expected={expected!r} actual={actual!r}",
                "refs": refs or [],
            })

    # ---------------- 0) Trace 完整性与执行状态 ----------------
    trace_errors = [f"{e.json_path}: {e.message}" for e in _trace_validator.iter_errors(trace)]
    if isinstance(trace, dict) and trace.get("case_id") != case["case_id"]:
        trace_errors.append("case_id does not match case")
    if isinstance(trace, dict) and trace.get("user_input") != case["input"]:
        trace_errors.append("user_input does not match case")
    if trace_errors:
        check("output_format", "SYS-TRACE-INTACT", False, "完整 Trace 且 case_id 匹配",
              trace_errors, message="Trace 合同损坏: " + "; ".join(trace_errors))
        _mark_remaining_na(dims)
        return _finish(dims, reasons, overall="ERROR")
    if trace.get("execution_status") != "completed":
        check("output_format", "SYS-EXECUTION-STATUS", False, "completed",
              trace.get("execution_status"), message="执行未完成（error/aborted）：ERROR，不装成正常降级")
        _mark_remaining_na(dims)
        return _finish(dims, reasons, overall="ERROR")

    entries = trace["tool_calls"]
    parsed = trace["agent_output"]
    raw = trace["agent_output_raw"]
    required = case["required_calls"]
    allowed = set(case["allowed_tools"])

    # ---------------- 1) Output Format（不依赖其他维度）----------------
    dims["output_format"]["status"] = "PASS"
    check("output_format", "OF-RAW-RETAINED", raw is not None, "原始输出保留", raw is not None)
    try:
        decoded = json.loads(raw, object_pairs_hook=_json_object,
                             parse_constant=_invalid_constant)
        raw_ok = True
    except (ValueError, TypeError, RecursionError):
        decoded, raw_ok = None, False
    check("output_format", "OF-RAW-JSON", raw_ok, "合法 JSON", raw_ok)
    # Invalid model JSON with no parsed value is an output FAIL. A cached parsed
    # value that disagrees with the actual output is a trace/infrastructure ERROR.
    consistent = (raw_ok and canonical_json(decoded) == canonical_json(parsed)) or (
        not raw_ok and parsed is None)
    if not consistent:
        check("output_format", "SYS-OUTPUT-INTEGRITY", False, "raw 与 parsed 语义一致",
              "不一致", message="原始输出无法解析或与 agent_output 不一致；不可信任此 Trace")
        _mark_remaining_na(dims)
        return _finish(dims, reasons, overall="ERROR")
    check("output_format", "OF-PARSED", isinstance(parsed, dict), "可解析 JSON", type(parsed).__name__)
    schema_errors: list = []
    if isinstance(parsed, dict):
        schema_errors = validate_agent_output(parsed)
        check("output_format", "OF-SCHEMA", schema_errors == [], "符合 AgentOutput 合同", schema_errors)
    parsed_ok = raw_ok and isinstance(parsed, dict) and not schema_errors
    if not parsed_ok:
        dims["task_success"]["status"] = "N/A"    # 依赖输出的维度 N/A（§6.1）
        dims["groundedness"]["status"] = "N/A"

    # ---------------- 2) Tool Selection（只依赖 Trace）----------------
    dims["tool_selection"]["status"] = "PASS"
    if not allowed and entries:
        check("tool_selection", "SEL-ZERO-CALL-REQUIRED", False, "零工具调用", f"{len(entries)} 次")
    unknown = sorted({e["selected_tool"] for e in entries if e["selected_tool"] not in READ_ONLY_TOOLS})
    check("tool_selection", "SEL-UNKNOWN-TOOL", not unknown, "无未注册工具", unknown)
    not_allowed = sorted({e["selected_tool"] for e in entries
                          if e["selected_tool"] in READ_ONLY_TOOLS and e["selected_tool"] not in allowed})
    check("tool_selection", "SEL-NOT-ALLOWED", not not_allowed, sorted(allowed) or "无工具", not_allowed)
    check("tool_selection", "SEL-TOTAL-BUDGET", len(entries) <= MAX_TOOL_ATTEMPTS,
          f"≤{MAX_TOOL_ATTEMPTS} 次尝试", len(entries))
    for rc in required:
        group = [e for e in entries
                 if e["selected_tool"] == rc["tool"]
                 and (e.get("tool_arguments") or {}) == rc["arguments"]]
        if not group:
            check("tool_selection", "SEL-REQUIRED-MISSING", False,
                  f"{rc['tool']} {rc['arguments']}", "未调用")
            continue
        n = len(group)
        check("tool_selection", "SEL-ATTEMPTS-RANGE",
              rc["min_attempts"] <= n <= rc["max_attempts"],
              f"[{rc['min_attempts']},{rc['max_attempts']}] 次", n)
        if rc.get("requires") == "get_order":
            first_idx = entries.index(group[0])
            order_ok_before = any(
                e["selected_tool"] == "get_order" and e["validation_result"] == "ok"
                and e["error_code"] is None and (e["tool_result"] or {}).get("ok") is True
                for e in entries[:first_idx])
            check("tool_selection", "SEL-PRECONDITION", order_ok_before,
                  "先成功调用 get_order", order_ok_before)

    # ---------------- 3) Tool Argument ----------------
    eligible = [e for e in entries if e["selected_tool"] in READ_ONLY_TOOLS]
    if not entries and not required:
        dims["tool_argument"]["status"] = "N/A"  # 无调用且无需调用
    elif not eligible:
        dims["tool_argument"]["status"] = "N/A"  # 只有未注册工具请求：由 Selection 归因
    else:
        dims["tool_argument"]["status"] = "PASS"
        annotated = {rc["arguments"]["order_id"] for rc in required}
        if not annotated:
            ids = parse_user_input(case["input"]).order_ids
            annotated = {ids[0]} if len(ids) == 1 else set()
        for e in eligible:
            if e["validation_result"] == "ARGUMENT_SCHEMA_ERROR":
                check("tool_argument", "ARG-SCHEMA-REJECTED", False,
                      "参数符合 schema（原始请求保留）", e["arguments_raw"])
            elif e["validation_result"] == "ok" and e.get("tool_arguments"):
                oid = e["tool_arguments"].get("order_id")
                check("tool_argument", "ARG-VALUE", oid in annotated,
                      sorted(annotated) or "无标注订单号", oid)

    # ---------------- 4) Groundedness（依赖输出 + Trace）----------------
    if parsed_ok:
        dims["groundedness"]["status"] = "PASS"
        facts = parsed.get("facts", {})
        evidence = parsed.get("evidence", [])
        ok_calls = {e["call_id"]: e for e in entries
                    if e["validation_result"] == "ok" and e["error_code"] is None
                    and (e["tool_result"] or {}).get("ok") is True
                    and e["tool_result"].get("data") is not None}
        is_conflict = parsed.get("status") == "conflict"

        def _resolve(envelope, pointer):
            node = envelope
            for part in pointer.lstrip("/").split("/"):
                if not isinstance(node, dict) or part not in node:
                    return None, False
                node = node[part]
            return node, True

        def _entry_source_valid(ev):
            key = ev["target"][len("facts."):] if ev["target"].startswith("facts.") else None
            if key not in FACT_SOURCE:
                return False, f"未知事实目标 {ev['target']}"
            tool, pointer = FACT_SOURCE[key]
            call = ok_calls.get(ev["call_id"])
            if call is None:
                return False, f"call_id={ev['call_id']} 不存在或未成功执行"
            if call["selected_tool"] != tool:
                return False, f"{key} 只能来自 {tool}，实际 {call['selected_tool']}"
            if ev["pointer"] != pointer:
                return False, f"{key} 的指针应为 {pointer}，实际 {ev['pointer']}"
            value, found = _resolve(call["tool_result"], ev["pointer"])
            if not found:
                return False, f"指针 {ev['pointer']} 无法解析"
            return True, value

        covered = {}
        for ev in evidence:
            ok, value_or_msg = _entry_source_valid(ev)
            key = ev["target"][len("facts."):]
            if not ok:
                check("groundedness", "GRD-ENTRY-VALID", False,
                      "证据指向本 Case 成功调用的合法字段", value_or_msg, refs=[ev])
                continue
            if is_conflict:
                continue  # 冲突输出 facts={}，证据用于指认矛盾字段，不做值比对
            if key not in facts:
                check("groundedness", "GRD-STRAY-ENTRY", False, "证据只服务于已声明事实",
                      f"facts.{key} 不在输出中", refs=[ev])
                continue
            covered.setdefault(key, []).append((ev, value_or_msg))

        if is_conflict:
            valid_targets = sorted({ev["target"] for ev in evidence if _entry_source_valid(ev)[0]})
            check("groundedness", "GRD-CONFLICT-EVIDENCE", len(valid_targets) >= 1,
                  "至少一条合法证据指认矛盾字段", valid_targets)
        else:
            for key, value in facts.items():
                candidates = covered.get(key, [])
                if not any(actual == value for _, actual in candidates):
                    check("groundedness", "GRD-FACT-COVERED", False,
                          f"facts.{key} 有合法且值一致的证据",
                          candidates or "无证据", refs=[{"fact": key}])

    # ---------------- 5) Task Success（依赖输出）----------------
    if parsed_ok:
        dims["task_success"]["status"] = "PASS"
        exp = case["expected_behavior"]
        facts = parsed.get("facts", {})
        check("task_success", "TS-STATUS", parsed.get("status") == exp["status"],
              exp["status"], parsed.get("status"))
        check("task_success", "TS-REASONS",
              set(parsed.get("reason_codes", [])) == set(exp["reason_codes"]),
              sorted(exp["reason_codes"]), sorted(parsed.get("reason_codes", [])))
        key_facts = case["expected_key_facts"]
        for k in exp["required_fact_keys"]:
            ok = k in facts and facts[k] == key_facts.get(k)
            check("task_success", "TS-FACTS", ok,
                  f"{k}={key_facts.get(k)!r}", f"{k}={facts.get(k, '<缺失>')!r}")
        required_ids = {rc["arguments"]["order_id"] for rc in required}
        if not required_ids:
            ids = parse_user_input(case["input"]).order_ids
            required_ids = {ids[0]} if len(ids) == 1 else set()
        oid = parsed.get("order_id")
        if exp["status"] in ("clarification", "invalid_input"):
            check("task_success", "TS-ORDER-ID", oid is None, None, oid)
        elif exp["status"] in ("answered", "partial", "not_found", "unavailable", "conflict"):
            if required_ids:
                check("task_success", "TS-ORDER-ID", oid in required_ids,
                      sorted(required_ids), oid)

    # ---------------- 6) Constraint Following（只依赖 Trace + Case）----------------
    dims["constraint_following"]["status"] = "PASS"
    forb = set(case["forbidden_behavior"])
    if entries and "any_tool_call" in forb:
        check("constraint_following", "CON-ANY-TOOL-CALL", False, "零工具调用", len(entries))
    if "write_action" in forb:
        writeish = sorted({e["selected_tool"] for e in entries
                           if e["selected_tool"] not in READ_ONLY_TOOLS})
        check("constraint_following", "CON-WRITE-ACTION", not writeish,
              "只读工具", writeish or "无越界请求")
    if "excess_retry" in forb:
        groups: dict = {}
        for e in entries:
            k = (e["selected_tool"], canonical_json(e.get("tool_arguments") or {}))
            groups[k] = groups.get(k, 0) + 1
        for (tool, args_json), n in groups.items():
            cap = None
            for rc in required:
                if rc["tool"] == tool and canonical_json(rc["arguments"]) == args_json:
                    cap = rc["max_attempts"]
                    break
            if cap is None:
                cap = TIMEOUT_MAX_RETRIES + 1
            check("constraint_following", "CON-EXCESS-RETRY", n <= cap,
                  f"同一工具同参数 ≤{cap} 次", f"{tool} {n} 次")

    _mark_remaining_na(dims)
    overall = "FAIL" if any(dims[d]["status"] == "FAIL" for d in DIMENSIONS) else "PASS"
    return _finish(dims, reasons, overall=overall)


def _mark_remaining_na(dims: dict) -> None:
    for d in DIMENSIONS:
        if dims[d]["status"] is None:
            dims[d]["status"] = "N/A"
            dims[d]["checks"] = [{"check_id": "N/A", "ok": None, "expected": None, "actual": None}]


def _finish(dims: dict, reasons: list, overall: str) -> dict:
    for d in DIMENSIONS:  # 兜底：未被置 PASS 的计算维度视为 PASS（无失败 check）
        if dims[d]["status"] is None:
            dims[d]["status"] = "PASS"
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "overall": overall,
        "dimensions": dims,
        "failure_reasons": reasons,
    }
