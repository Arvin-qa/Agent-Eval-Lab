"""Round 1 扩展数据集独立 QA 校验器（与生成器逻辑解耦）。

检查四层：
  1. 格式（schema）：12 必填字段、类型、枚举、case_id/输入唯一性、模式匹配
  2. 查重：精确重复 + 规范化近重复率 + 模板集中度
  3. 覆盖率：类别 × 难度 × 状态 × 原因码 × 工具 × 故障 × 事实键 × 禁止行为矩阵
  4. 逻辑一致性：交叉重推导（解析器/冲突规则/尝试次数/事实可产生性/记忆矛盾等）

用法：python data_factory/validate_round1.py
Exit 0 = 全绿；exit 1 = 存在失败项（明细打印）。
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from order_eval.schemas import parse_user_input, detect_conflicts  # noqa: E402

DATA = REPO / "datasets" / "expansion" / "round_001.jsonl"

REQUIRED_FIELDS = ["case_id", "category", "difficulty", "user_input", "context",
                   "tool_state", "expected_behavior", "forbidden_behavior",
                   "expected_tool", "expected_args", "evaluation_rules", "severity"]
CATEGORIES = {"Normal", "Boundary", "Abnormal", "ToolError", "ArgumentError", "Timeout",
              "DirtyData", "Hallucination", "MultiTurnContext", "InstructionConflict",
              "PromptInjection", "AgentLoop", "Retry", "Fallback", "MemoryInconsistency"}
DIFFICULTIES = {"easy", "medium", "hard"}
SEVERITIES = {"minor", "major", "critical"}
STATUSES = {"answered", "partial", "clarification", "invalid_input",
            "not_found", "unavailable", "conflict", "unsupported"}
REASON_CODES = {"MISSING_ORDER_ID", "AMBIGUOUS_ORDER_ID", "INVALID_INPUT",
                "UNSUPPORTED_ACTION", "UNSUPPORTED_QUERY", "NOT_SHIPPED",
                "ORDER_NOT_FOUND", "TOOL_UNAVAILABLE", "INVALID_TOOL_RESULT",
                "SHIPMENT_NOT_FOUND", "ETA_NOT_AVAILABLE", "AMOUNT_NOT_AVAILABLE",
                "DATA_CONFLICT"}
FORBIDDEN_VOCAB = {"invent_fact", "wrong_order", "extra_tool", "write_action",
                   "excess_retry", "any_tool_call", "obey_tool_text",
                   "fabricate_eta", "fabricate_amount", "fabricate_status",
                   "fabricate_tracking_no", "fabricate_currency", "obey_user_injection",
                   "precommit_unverified", "skip_verification", "adopt_memory_value",
                   "resolve_wrong_order", "unbounded_retry", "call_before_precondition"}
TOOLS = {"get_order", "get_shipment"}
FACT_KEYS = {"order_status", "amount_cents", "currency",
             "shipment_status", "tracking_no", "eta", "delivered_at"}
FACT_TOOL = {"order_status": "get_order", "amount_cents": "get_order", "currency": "get_order",
             "shipment_status": "get_shipment", "tracking_no": "get_shipment",
             "eta": "get_shipment", "delivered_at": "get_shipment"}
RULE_NAMES = {"task_success", "tool_selection", "tool_argument", "groundedness",
              "output_format", "constraint_following", "context_resolution",
              "memory_authority", "budget", "llm_judge"}
RULE_MODES = {"rule_based", "llm_judge"}
OID_RE = re.compile(r"^ORD-[0-9]{4}$")
ETA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ZERO_FACT_STATUSES = {"invalid_input", "clarification", "unsupported",
                      "not_found", "unavailable", "conflict"}

errors = []
warns = []


def err(cid, msg):
    errors.append(f"[{cid}] {msg}")


def check(case):
    cid = case.get("case_id", "<missing>")
    # ---------- 1. 格式 ----------
    for f in REQUIRED_FIELDS:
        if f not in case:
            err(cid, f"缺少必填字段 {f}")
            return
    extra = set(case) - set(REQUIRED_FIELDS) - {"expected_key_facts", "provenance"}
    if extra:
        err(cid, f"未知多余字段 {extra}")
    if not re.match(r"^R01-[A-Z]{3}-\d{3}$", cid):
        err(cid, f"case_id 格式不合法: {cid}")
    if case["category"] not in CATEGORIES:
        err(cid, f"category 非法: {case['category']}")
    if case["difficulty"] not in DIFFICULTIES:
        err(cid, f"difficulty 非法: {case['difficulty']}")
    if case["severity"] not in SEVERITIES:
        err(cid, f"severity 非法: {case['severity']}")
    if not isinstance(case["user_input"], str):
        err(cid, "user_input 必须是字符串")
    ctx = case["context"]
    if not isinstance(ctx, dict) or "prior_turns" not in ctx or "session_facts" not in ctx:
        err(cid, "context 必须含 prior_turns/session_facts")
    for t in ctx.get("prior_turns", []):
        if set(t) != {"role", "content"} or t["role"] not in ("user", "assistant"):
            err(cid, f"prior_turn 结构非法: {t}")
    ts = case["tool_state"]
    for k in ("snapshot_id", "orders", "shipments", "faults", "injected"):
        if k not in ts:
            err(cid, f"tool_state 缺少 {k}")
    for tool, seq in ts.get("faults", {}).items():
        if tool not in TOOLS:
            err(cid, f"faults 工具名非法: {tool}")
        if not seq or any(f not in ("timeout", "error", "ok") for f in seq):
            err(cid, f"faults 序列非法: {tool} {seq}")
    eb = case["expected_behavior"]
    if set(eb) != {"status", "reason_codes", "required_fact_keys"}:
        err(cid, f"expected_behavior 字段集非法: {sorted(eb)}")
    if eb["status"] not in STATUSES:
        err(cid, f"status 非法: {eb['status']}")
    for r in eb["reason_codes"]:
        if r not in REASON_CODES:
            err(cid, f"原因码非法: {r}")
    if len(set(eb["reason_codes"])) != len(eb["reason_codes"]):
        err(cid, "reason_codes 有重复")
    for k in eb["required_fact_keys"]:
        if k not in FACT_KEYS:
            err(cid, f"required_fact_keys 非法: {k}")
    for f in case["forbidden_behavior"]:
        if f not in FORBIDDEN_VOCAB:
            err(cid, f"forbidden_behavior 词表外: {f}")
    if len(set(case["forbidden_behavior"])) != len(case["forbidden_behavior"]):
        err(cid, "forbidden_behavior 有重复")
    for t in case["expected_tool"]:
        if t not in TOOLS:
            err(cid, f"expected_tool 非法: {t}")
    for c in case["expected_args"]:
        if set(c) != {"tool", "arguments", "min_attempts", "max_attempts", "requires"}:
            err(cid, f"expected_args 条目字段集非法: {sorted(c)}")
            continue
        if c["tool"] not in TOOLS:
            err(cid, f"expected_args 工具非法: {c['tool']}")
        if not OID_RE.match(c["arguments"].get("order_id", "")):
            err(cid, f"expected_args order_id 非法: {c['arguments']}")
        if c["tool"] == "get_shipment" and c.get("requires") != "get_order":
            err(cid, f"get_shipment 缺前置 requires=get_order: {cid}")
        if c["tool"] == "get_order" and c.get("requires") is not None:
            err(cid, f"get_order 不应有前置: {cid}")
        if not (0 <= c["min_attempts"] <= c["max_attempts"] <= 2):
            err(cid, f"尝试次数越界: {c['tool']} {c['min_attempts']}-{c['max_attempts']}")
    for rule in case["evaluation_rules"]:
        if rule.get("rule") not in RULE_NAMES or rule.get("mode") not in RULE_MODES:
            err(cid, f"evaluation_rules 条目非法: {rule.get('rule')}/{rule.get('mode')}")
    if not isinstance(case.get("provenance"), dict) or "rule" not in case["provenance"]:
        err(cid, "provenance 需含 rule 引用")

    # ---------- 4. 逻辑一致性（独立重推导） ----------
    text = case["user_input"]
    status = eb["status"]
    reasons = set(eb["reason_codes"])
    keys = eb["required_fact_keys"]
    facts = case["expected_key_facts"]
    calls = case["expected_args"]
    exp_tools = set(case["expected_tool"])
    parsed = parse_user_input(text)

    # 4.1 解析器交叉验证
    if parsed.outcome == "INVALID_INPUT":
        if status != "invalid_input" or "INVALID_INPUT" not in reasons:
            err(cid, "解析 INVALID_INPUT 但 expected 不是 invalid_input")
        if calls:
            err(cid, "invalid_input 场景不应有工具调用")
    elif len(parsed.order_ids) > 1:
        if status != "clarification" or "AMBIGUOUS_ORDER_ID" not in reasons:
            err(cid, "解析到多个订单号但 expected 不是 AMBIGUOUS clarification")
        if calls:
            err(cid, "歧义场景不应有工具调用")
    # 含写关键词必须 unsupported
    if any(k in text for k in ("取消", "退款", "退货")) and status != "unsupported":
        err(cid, "输入含写关键词但 expected 不是 unsupported")
    # >500 字符必须 invalid_input
    if len(text.strip()) > 500 and status != "invalid_input":
        err(cid, "输入超 500 字符但 expected 不是 invalid_input")
    # 有唯一合法订单号的查询场景必须有 get_order
    if (parsed.outcome == "ok" and len(parsed.order_ids) == 1
            and status in ("answered", "partial", "conflict", "not_found", "unavailable")):
        if "get_order" not in exp_tools or not calls:
            err(cid, "有唯一订单号的查询场景缺少 get_order 调用")
        target = parsed.order_ids[0].upper()
        for c in calls:
            if c["arguments"]["order_id"] != target:
                err(cid, f"调用参数订单号 {c['arguments']['order_id']} ≠ 输入解析值 {target}")
    # 零事实状态
    if status in ZERO_FACT_STATUSES and (keys or facts):
        err(cid, f"status={status} 不应携带事实 keys={keys} facts={facts}")
    # required 与 key_facts 对齐
    if status in ("answered", "partial"):
        if sorted(keys) != sorted(facts.keys()):
            err(cid, f"required_fact_keys {keys} 与 expected_key_facts {sorted(facts)} 不一致")
    # 事实可产生性：来源工具必须在 expected_tool 内
    for k in keys:
        if FACT_TOOL[k] not in exp_tools:
            err(cid, f"事实 {k} 的来源工具 {FACT_TOOL[k]} 不在 expected_tool")
    # expected_tool 与 expected_args 一致
    if exp_tools != {c["tool"] for c in calls}:
        err(cid, f"expected_tool {exp_tools} 与 expected_args 工具集不一致")

    # 4.2 故障注入与尝试次数
    faults = ts.get("faults", {})
    if set(faults) - exp_tools:
        err(cid, f"faults 含未期望的工具: {set(faults) - exp_tools}")
    for c in calls:
        seq = faults.get(c["tool"], [])
        if not seq or seq[0] == "ok":
            want = 1
        elif seq[0] == "error":
            want = 1
        else:  # timeout 起
            want = 2
        if c["max_attempts"] != want:
            err(cid, f"{c['tool']} 故障序列 {seq} 与 max_attempts={c['max_attempts']} 不符")
    total_min = sum(c["min_attempts"] for c in calls)
    if total_min > 4:
        err(cid, f"最少尝试总和 {total_min} 超出预算 4")

    # 4.3 世界状态与期望一致
    oid = next((c["arguments"]["order_id"] for c in calls if c["tool"] == "get_order"), None)
    order = ts["orders"].get(oid) if oid else None
    ship = ts["shipments"].get(oid) if oid else None
    if status == "not_found":
        if order is not None:
            err(cid, "expected not_found 但工具状态中订单存在")
    elif order is not None and "order_id" not in str(ts.get("injected")):
        # 订单存在且未被错单覆盖
        if "order_status" in facts and facts["order_status"] != order["status"]:
            if f".status" not in str(ts.get("injected")):
                err(cid, f"expected order_status={facts['order_status']} 与世界 {order['status']} 不符")
        if "amount_cents" in facts and facts["amount_cents"] != order["amount_cents"]:
            err(cid, f"expected amount_cents={facts['amount_cents']} 与世界 {order['amount_cents']} 不符")
        if "currency" in facts and facts["currency"] != order["currency"]:
            err(cid, f"expected currency={facts['currency']} 与世界 {order['currency']} 不符")
    # get_shipment 调用的前提：订单已发货
    if any(c["tool"] == "get_shipment" for c in calls) and order is not None:
        if order["status"] in ("PAID", "CANCELED") and status != "unavailable":
            err(cid, f"PAID/CANCELED 订单不应调用 get_shipment（order={order['status']}）")
    # eta 事实必须来自合法 eta 且世界一致
    if "eta" in facts:
        if ship is None or ship.get("eta") != facts["eta"] or not ETA_RE.match(str(facts["eta"])):
            err(cid, f"expected eta={facts.get('eta')} 与物流记录不一致或格式非法")
    if "shipment_status" in facts and ship is not None:
        if ship["status"] != facts["shipment_status"] and ".status" not in str(ts.get("injected")):
            err(cid, f"expected shipment_status={facts['shipment_status']} 与世界 {ship['status']} 不符")
    # 冲突场景必须真的冲突
    if status == "conflict":
        if not detect_conflicts(order, ship):
            err(cid, "expected conflict 但世界状态不触发任何冲突规则")
    elif detect_conflicts(order, ship) and status not in ("unavailable",):
        err(cid, "世界存在冲突但 expected 不是 conflict/unavailable")

    # 4.4 类别专属不变式
    cat = case["category"]
    forb = set(case["forbidden_behavior"])
    gparams = [r["params"] for r in case["evaluation_rules"] if r["rule"] == "groundedness"]
    forbidden_vals = {}
    for p in gparams:
        forbidden_vals.update(p.get("forbidden_values", {}) or {})
    for k, vals in forbidden_vals.items():
        if k in facts and facts[k] in vals:
            err(cid, f"expected_key_facts[{k}]={facts[k]} 撞上禁值 {vals}")
    if cat in ("Hallucination", "MemoryInconsistency"):
        if not any(f.startswith("fabricate_") or f in ("adopt_memory_value",) for f in forb):
            err(cid, "幻觉/记忆类应禁编造或禁沿用记忆")
    if cat == "InstructionConflict" and status in ("answered", "partial"):
        if not any(f.startswith("fabricate_") or f == "skip_verification" for f in forb):
            err(cid, "指令冲突的查证执行类应禁编造/禁跳过验证")
    if cat == "PromptInjection" and not ({"obey_tool_text", "obey_user_injection"} & forb):
        err(cid, "注入类应禁 obey_tool_text/obey_user_injection")
    if cat == "AgentLoop" and not any(r["rule"] == "budget" for r in case["evaluation_rules"]):
        err(cid, "AgentLoop 应含 budget 规则")
    if cat == "MultiTurnContext":
        if not ctx["prior_turns"]:
            err(cid, "多轮场景 prior_turns 为空")
        if not any(r["rule"] == "context_resolution" for r in case["evaluation_rules"]):
            err(cid, "多轮场景应含 context_resolution 规则")
    if cat == "MemoryInconsistency":
        if not ctx["session_facts"].get("claims"):
            err(cid, "记忆矛盾场景 session_facts.claims 为空")
        if not any(r["rule"] == "memory_authority" for r in case["evaluation_rules"]):
            err(cid, "记忆矛盾场景应含 memory_authority 规则")
        for claim in ctx["session_facts"]["claims"]:
            k = claim["field"]
            if k in facts and facts[k] == claim["value"]:
                err(cid, f"记忆 claim[{k}] 与 expected 值相同，不构成矛盾")
    if cat == "ArgumentError":
        if any(c for c in calls) and status in ("clarification", "invalid_input"):
            err(cid, "参数错误场景澄清/拒绝时不应有调用")
    if cat in ("Abnormal",) and status == "unsupported":
        if calls:
            err(cid, "unsupported 场景不应有工具调用")
        if "any_tool_call" not in forb:
            err(cid, "unsupported 场景应禁 any_tool_call")


def main():
    raw = DATA.read_text(encoding="utf-8")
    cases = []
    seen_ids = set()
    for lineno, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"[line {lineno}] JSON 解析失败: {e}")
            continue
        if case.get("case_id") in seen_ids:
            errors.append(f"[line {lineno}] case_id 重复: {case.get('case_id')}")
        seen_ids.add(case.get("case_id"))
        cases.append(case)

    # ---------- 2. 查重 ----------
    inputs = [c["user_input"] for c in cases]
    dup_exact = [t for t, n in Counter(inputs).items() if n > 1]
    if dup_exact:
        for t in dup_exact[:10]:
            errors.append(f"[dedup] user_input 精确重复: {t[:40]}")
    norm = lambda s: re.sub(r"[^\w]", "", s).lower()
    allowed_norm_dup = set()
    manifest = REPO / "datasets" / "expansion" / "norm_dup_allowed.json"
    if manifest.exists():
        allowed_norm_dup = set(json.loads(manifest.read_text(encoding="utf-8")))
    # 规范化同形组：任一成员在豁免清单（长度填充/空白变体/分隔符陷阱）即放行
    by_norm = defaultdict(list)
    for t in inputs:
        if norm(t) and len(t.strip()) <= 490:
            by_norm[norm(t)].append(t)
    for _, group in by_norm.items():
        if len(group) > 1 and not any(t in allowed_norm_dup for t in group):
            errors.append(f"[dedup] 规范化后重复: {group[0][:40]}")
    # 6-gram 近重检测（轻量近似）
    grams = defaultdict(set)
    near_dup_pairs = 0
    for c in cases:
        g = norm(c["user_input"])
        for i in range(max(0, len(g) - 11)):
            grams[g[i:i + 12]].add(c["case_id"])
    template_hot = [(k, len(v)) for k, v in grams.items() if len(v) > 6]
    if template_hot:
        warns.append(f"存在 {len(template_hot)} 个 12-gram 被 >6 条共享（模板化风险），最长共享 "
                     f"{max(n for _, n in template_hot)} 条")

    # ---------- 3. 覆盖率 ----------
    cov = {
        "category": Counter(), "difficulty": Counter(), "severity": Counter(),
        "status": Counter(), "reason": Counter(), "tool": Counter(),
        "fact_key": Counter(), "forbidden": Counter(), "fault": Counter(),
        "cat_diff": defaultdict(Counter),
    }
    for c in cases:
        cov["category"][c["category"]] += 1
        cov["difficulty"][c["difficulty"]] += 1
        cov["severity"][c["severity"]] += 1
        cov["status"][c["expected_behavior"]["status"]] += 1
        for r in c["expected_behavior"]["reason_codes"]:
            cov["reason"][r] += 1
        for t in c["expected_tool"]:
            cov["tool"][t] += 1
        for k in c["expected_behavior"]["required_fact_keys"]:
            cov["fact_key"][k] += 1
        for f in c["forbidden_behavior"]:
            cov["forbidden"][f] += 1
        for tool, seq in c["tool_state"].get("faults", {}).items():
            cov["fault"][f"{tool}:{'+'.join(seq)}"] += 1
        cov["cat_diff"][c["category"]][c["difficulty"]] += 1

    for c in cases:
        check(c)

    missing_reason = REASON_CODES - set(cov["reason"])
    if missing_reason:
        warns.append(f"未覆盖原因码: {sorted(missing_reason)}")
    missing_fact = {"tracking_no", "delivered_at"} - set(cov["fact_key"])
    if missing_fact:
        warns.append(f"未作为必需事实覆盖: {sorted(missing_fact)}（合同中属可有可无附加事实）")
    for cat in CATEGORIES:
        if cov["category"][cat] < 20:
            warns.append(f"类别 {cat} 仅 {cov['category'][cat]} 条（<20）")
        d = cov["cat_diff"][cat]
        if len(d) < 2:
            warns.append(f"类别 {cat} 难度分布单一: {dict(d)}")

    # ---------- 输出 ----------
    summary = {
        "total": len(cases),
        "unique_case_ids": len(seen_ids),
        "unique_inputs": len(set(inputs)),
        "exact_dup_inputs": len(inputs) - len(set(inputs)),
        "dup_rate": round((len(inputs) - len(set(inputs))) / max(1, len(inputs)), 6),
        "coverage": {k: dict(v) for k, v in cov.items() if isinstance(v, Counter)},
        "cat_diff": {k: dict(v) for k, v in cov["cat_diff"].items()},
        "errors": errors,
        "warnings": warns,
    }
    out = REPO / "datasets" / "expansion" / "qa_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"总数: {len(cases)} | case_id 唯一: {len(seen_ids)} | 输入唯一: {len(set(inputs))}")
    print(f"精确重复: {summary['exact_dup_inputs']} | 重复率: {summary['dup_rate']:.2%}")
    print(f"覆盖: 类别 {len(cov['category'])}/15 | 状态 {len(cov['status'])}/8 | "
          f"原因码 {len(cov['reason'])}/13 | 难度 {len(cov['difficulty'])}/3")
    for w in warns:
        print(f"WARN: {w}")
    if errors:
        print(f"\nFAIL: {len(errors)} 项")
        for e in errors[:40]:
            print("  " + e)
        sys.exit(1)
    print("\nQA 全部通过 ✓")


if __name__ == "__main__":
    main()
