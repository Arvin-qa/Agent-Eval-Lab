"""Runner：trial 隔离、Trace 组装、套件执行、报告与运行身份（PROJECT_SPEC §8/§9/§11）。"""
import hashlib
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from order_eval.agent import MockAgent, render_output_raw
from order_eval.evaluator import DIMENSIONS, EVALUATOR_VERSION, evaluate
from order_eval.schemas import (
    TOOL_SPECS,
    canonical_json,
    is_v2_case,
    load_cases,
    needs_context,
)
from order_eval.tools import Executor, build_world_from_state, load_fixture_world

TRACE_VERSION = "0.1"
SKIP_CONTEXT_REASON = "AGENT_NO_SESSION_STATE"  # MockAgent 无会话状态，多轮/记忆类暂不可执行


# ---------------------------------------------------------------- 身份与散列

def new_run_id(prefix="run") -> str:
    return f"{prefix}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex}"


def create_run_directory(out_dir, run_id):
    """Exclusively claim one child directory; never reuse existing evidence."""
    if not run_id or run_id in (".", "..") or any(c in run_id for c in ("/", "\\", ":")):
        raise ValueError("run_id must be a single directory name")
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    out = root / run_id
    out.mkdir(exist_ok=False)
    return out

def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def sha256_obj(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def tool_schema_hash() -> str:
    return sha256_obj(TOOL_SPECS)


def git_identity():
    """返回 (commit, dirty)；无 git 时 (None, None)。"""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=10).stdout.strip() or None
        status = subprocess.run(["git", "status", "--porcelain"],
                                capture_output=True, text=True, timeout=10).stdout.strip()
        return commit, bool(status)
    except (OSError, subprocess.SubprocessError):
        return None, None


# ---------------------------------------------------------------- Trace 组装

def _flatten_tool_calls(requests) -> list:
    entries = []
    for req in requests:
        for att in req.attempts:
            entries.append({
                "call_id": req.call_id,
                "parent_request_id": req.call_id,
                "selected_tool": req.tool,
                "arguments_raw": req.arguments_raw,
                "tool_arguments": req.tool_arguments,
                "validation_result": att["validation_result"],
                "attempt_index": att["attempt_index"],
                "tool_result_raw": att["tool_result_raw"],
                "tool_result": att["tool_result"],
                "error_code": att["error_code"],
                "duration_ms": att["duration_ms"],
            })
    return entries


def normalize_case(case: dict) -> dict:
    """v1 case 原样通过；v2 expansion case 映射为 runner/evaluator 内部表示。

    映射是纯引用级改名（不深复制）：v2 的 expected_tool→allowed_tools、
    expected_args→required_calls、user_input→input；expected_behavior/
    forbidden_behavior/expected_key_facts 两版同名同构。幂等：已 normalize
    的 v2 case（带 schema_version）原样通过。"""
    if not is_v2_case(case) or "schema_version" in case:
        return case
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "input": case["user_input"],
        "expected_behavior": case["expected_behavior"],
        "allowed_tools": case["expected_tool"],
        "required_calls": case["expected_args"],
        "forbidden_behavior": case["forbidden_behavior"],
        "expected_key_facts": case["expected_key_facts"],
        "expected_failure_mode": None,
        "critical": case["severity"] == "critical",
        "provenance": case["provenance"],
        "tool_state": case["tool_state"],
        "context": case["context"],
        "schema_version": "v2",
    }


def run_trial(case: dict, fixtures_path: str, dataset_path: str,
              run_id: str = "local", trial_index: int = 1, config=None) -> dict:
    """一次 trial = 独立工具世界（深复制、计数归零）+ Agent + Trace。不读取 expected。

    v1 case 经 fixture_id 引用共享 fixtures.json；v2 case 用内嵌 tool_state
    构造世界（fixtures_hash 记 None，可比性由 dataset_hash 承担）。"""
    norm = normalize_case(case)
    fixtures_hash = None
    ex = None
    agent = MockAgent()
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    agent_error = None
    output = None
    output_raw = None
    model_requests = 0
    try:
        if is_v2_case(norm):
            world = build_world_from_state(norm["tool_state"])
        else:
            fixtures_hash = sha256_file(fixtures_path)
            world = load_fixture_world(fixtures_path, norm["fixture_id"])
        ex = Executor(world)
        result = agent.run(norm["input"], ex.execute)
        output = result["output"]
        output_raw = render_output_raw(output)
        model_requests = result["model_requests"]
        execution_status = "aborted" if ex.aborted else "completed"
    except Exception as exc:  # 环境级错误：ERROR，不是业务 unavailable
        execution_status = "error"
        agent_error = f"{type(exc).__name__}: {exc}"
    total_ms = int((time.perf_counter() - t0) * 1000)
    ended = datetime.now(timezone.utc)

    commit, dirty = git_identity()
    trace = {
        "trace_version": TRACE_VERSION,
        "run_id": run_id,
        "case_id": norm["case_id"],
        "trial_index": trial_index,
        "mode": "offline",
        "agent_version": agent.version,
        "prompt_hash": None,          # offline 无提示词
        "tool_schema_hash": tool_schema_hash(),
        "evaluator_version": EVALUATOR_VERSION,
        "dataset_hash": sha256_file(dataset_path),
        "fixtures_hash": fixtures_hash,
        "config_hash": sha256_obj(config or {}),
        "code_commit": commit,
        "dirty": dirty,
        "model": {
            "provider": "mock",
            "request_model": None,
            "response_model": None,
            "temperature": None,
            "seed": None,
        },
        "user_input": norm["input"],
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "execution_status": execution_status,
        "execution_error": agent_error,
        "model_steps": [],             # offline 无模型步骤
        "tool_calls": _flatten_tool_calls(ex.requests) if ex else [],
        "agent_output_raw": output_raw,
        "agent_output": output,
        "evaluation_result": None,     # 由 evaluate() 填充
        "failure_reasons": [],
        "metrics": {
            "total_duration_ms": total_ms,
            "model_duration_ms": 0,
            "tool_duration_ms": sum(
                att["duration_ms"] for req in ex.requests for att in req.attempts) if ex else 0,
            "model_requests": model_requests,
            "input_tokens": None,
            "output_tokens": None,
            "cost_estimate": None,
            "currency": None,
            "pricing_date": None,
        },
    }
    evaluation = evaluate(norm, trace)
    trace["evaluation_result"] = evaluation
    trace["failure_reasons"] = evaluation["failure_reasons"]
    return trace


# ---------------------------------------------------------------- 套件、报告与退出码

def compute_score(passed: int, planned: int) -> float:
    """Score = 100 × PASS / planned_cases；ERROR 不算成功，保留在分母（§6.1）。"""
    if planned <= 0:
        return 0.0
    return round(100.0 * passed / planned, 2)


def classify_exit_code(report: dict) -> int:
    """0=有效成功；1=业务 FAIL/ERROR；2=配置/基础设施或零执行。

    旧报告的 ERROR 均为基础设施错误；新报告显式标注 infrastructure_errors。
    """
    if report.get("run_errors") or report.get("infrastructure_errors", report.get("error", 0)):
        return 2
    if report.get("fail", 0) > 0 or report.get("error", 0) > 0:
        return 1
    if report.get("trials", report.get("pass", 0)) == 0:
        return 2
    return 0


def build_report(run_id, cases, traces, mode, scope, dataset_path, fixtures_path, config=None,
                 skipped_info=None, dataset_total=None):
    """cases 为实际执行的（normalized）case；skipped_cases 记录因能力边界未执行的 case。

    planned_cases = 可执行数（score 分母与 pass/fail/error 总和一致）；dataset_cases
    为数据集总量。v1 运行 skipped=0、planned=dataset_cases，行为不变。"""
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0}
    dim_summary = {d: {"pass": 0, "fail": 0, "na": 0} for d in
                   ["task_success", "tool_selection", "tool_argument",
                    "groundedness", "output_format", "constraint_following"]}
    category_summary: dict = {}
    tool_summary: dict = {}
    failure_cases = []
    case_by_id = {c["case_id"]: c for c in cases}
    for trace in traces:
        evaluation = trace["evaluation_result"]
        overall = evaluation["overall"]
        counts[overall] += 1
        case = case_by_id[trace["case_id"]]
        cat = category_summary.setdefault(
            case["category"], {"pass": 0, "fail": 0, "error": 0})
        cat[{"PASS": "pass", "FAIL": "fail", "ERROR": "error"}[overall]] += 1
        for dim, info in evaluation["dimensions"].items():
            key = {"PASS": "pass", "FAIL": "fail", "N/A": "na"}[info["status"]]
            dim_summary[dim][key] += 1
        for e in trace["tool_calls"]:
            ts = tool_summary.setdefault(e["selected_tool"], {
                "attempts": 0, "argument_rejected": 0, "backend_faults": 0, "invalid_results": 0})
            ts["attempts"] += 1
            if e["validation_result"] == "ARGUMENT_SCHEMA_ERROR":
                ts["argument_rejected"] += 1
            if e["error_code"] in ("TIMEOUT", "TOOL_ERROR"):
                ts["backend_faults"] += 1        # 注入故障，与 Agent 选错工具分开（§11）
            if e["error_code"] == "INVALID_TOOL_RESULT":
                ts["invalid_results"] += 1
        if overall in ("FAIL", "ERROR"):
            failure_cases.append({
                "case_id": trace["case_id"],
                "input": trace["user_input"],
                "overall": overall,
                "failed_dimensions": [d for d, info in evaluation["dimensions"].items()
                                      if info["status"] == "FAIL"],
                "reasons": [f"{r['dimension']}/{r['reason_code']}" for r in evaluation["failure_reasons"]],
            })
    skipped = skipped_info or {"count": 0, "reason": None, "case_ids": []}
    planned = len(cases)
    if traces:
        ident_fixtures_hash = traces[0].get("fixtures_hash")
    else:
        ident_fixtures_hash = None  # 未执行时不读取无关 Fixture
    report = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "scope": scope,  # "full" | "subset"
        "planned_cases": planned,
        "dataset_cases": dataset_total if dataset_total is not None else planned,
        "skipped_cases": skipped,
        "trials": len(traces),
        "distinct_cases": len({t["case_id"] for t in traces}),
        "pass": counts["PASS"],
        "fail": counts["FAIL"],
        "error": counts["ERROR"],
        "infrastructure_errors": counts["ERROR"],
        "run_errors": [] if traces else ["NO_EXECUTABLE_TRIALS: 没有完成有效评测（空数据或全部跳过）"],
        "score": compute_score(counts["PASS"], planned),
        "dimension_summary": dim_summary,
        "category_summary": category_summary,
        "tool_summary": tool_summary,
        "failure_cases": failure_cases,
        "comparison": None,
        "identity": {
            "agent_version": MockAgent.version,
            "evaluator_version": EVALUATOR_VERSION,
            "trace_version": TRACE_VERSION,
            "dataset_hash": sha256_file(dataset_path),
            "fixtures_hash": ident_fixtures_hash,
            "tool_schema_hash": tool_schema_hash(),
            "config_hash": sha256_obj(config or {}),
            "code_commit": traces[0]["code_commit"] if traces else None,
            "dirty": traces[0]["dirty"] if traces else None,
        },
        "notes": [
            "合成数据（synthetic），来源为本项目业务合同，无真实客户/订单。",
            "offline 模式为确定性 MockAgent + 本地 FixtureTools，证明评测基础设施，不是语言模型能力基准。",
            "工具后端故障为规格注入的测试条件，与 Agent 工具选择错误分开统计。",
        ],
    }
    if skipped["count"]:
        report["notes"].append(
            f"{skipped['count']} 条依赖会话上下文（多轮/记忆）的 case 已跳过：当前 "
            f"MockAgent 无会话状态（{SKIP_CONTEXT_REASON}）；score 分母为可执行数。")
    report["notes"].extend(f"ERROR: {error}" for error in report["run_errors"])
    return report


def run_suite(cases, fixtures_path, dataset_path, mode="offline", config=None, run_id=None,
              scope="full"):
    """run_suite(cases, mode, config) → (report, traces)。每次 trial 独立工具世界。

    依赖会话上下文的 v2 case（多轮/记忆）不执行、不计入分母，单独报告为 skipped。"""
    if mode != "offline":
        raise ValueError(f"模式 {mode!r} 未实现：P0 只支持 offline（无 Key 离线）")
    if (config or {}).get("repeat", 1) != 1:
        raise ValueError("当前 Release 仅支持 repeat=1（single-trial）")
    run_id = run_id or new_run_id()
    normalized = [normalize_case(c) for c in cases]
    executable = [c for c in normalized if not needs_context(c)]
    skipped_ids = sorted(c["case_id"] for c in normalized if needs_context(c))
    skipped_info = {
        "count": len(skipped_ids),
        "reason": SKIP_CONTEXT_REASON if skipped_ids else None,
        "case_ids": skipped_ids,
    }
    traces = [run_trial(case, fixtures_path, dataset_path, run_id=run_id,
                        trial_index=1, config=config)
              for case in executable]
    report = build_report(run_id, executable, traces, mode, scope, dataset_path,
                          fixtures_path, config, skipped_info=skipped_info,
                          dataset_total=len(cases))
    return report, traces


# ---------------------------------------------------------------- 重复执行一致性（§9）

_VOLATILE_METRICS = ("total_duration_ms", "model_duration_ms", "tool_duration_ms")


def normalize_trace_for_compare(trace: dict) -> dict:
    """剥离易变字段（run_id、时间、耗时），规范化随机 call_id（按出现顺序，同步替换
    evidence 引用），保留答案、调用参数/结果/错误码、判定的结构化内容（§9）。"""
    t = json.loads(json.dumps(trace, ensure_ascii=False))
    t.pop("run_id", None)
    t["started_at"] = ""
    t["ended_at"] = ""
    for k in _VOLATILE_METRICS:
        t["metrics"][k] = 0
    # call_id 规范化：按 tool_calls 首次出现顺序重编号，并同步替换 evidence 引用
    mapping = {}
    for e in t.get("tool_calls", []):
        old = e.get("call_id")
        if old not in mapping:
            mapping[old] = f"call-{len(mapping) + 1}"
        e["call_id"] = mapping[old]
    output = t.get("agent_output")
    if isinstance(output, dict):
        for ev in output.get("evidence", []):
            if ev.get("call_id") in mapping:
                ev["call_id"] = mapping[ev["call_id"]]
    return t


# ---------------------------------------------------------------- 产物落盘

def render_report_md(report: dict) -> str:
    """Markdown 从同一 report JSON 渲染，不各算一遍（§11）。"""
    ident = report["identity"]
    fx = ident["fixtures_hash"]
    fx_text = f"{fx[:12]}…" if fx else "None（v2 内嵌世界，可比性由 dataset_hash 承担）"
    lines = [
        f"# OrderTrace Eval Report — {report['run_id']}",
        "",
        f"- mode/scope: `{report['mode']}` / `{report['scope']}`（合成数据，Mock 参考实现，非模型准确率）",
        f"- planned/distinct/trials: {report['planned_cases']} / {report['distinct_cases']} / {report['trials']}",
        f"- PASS/FAIL/ERROR: **{report['pass']} / {report['fail']} / {report['error']}**，Score = {report['score']}",
        f"- agent={ident['agent_version']} evaluator={ident['evaluator_version']} commit={ident['code_commit']} dirty={ident['dirty']}",
        f"- dataset_hash={ident['dataset_hash'][:12]}… fixtures_hash={fx_text}",
        "",
        "## 六维结果（PASS/(PASS+FAIL)，N/A 不计成功）",
        "",
        "| 维度 | PASS | FAIL | N/A |",
        "| --- | --- | --- | --- |",
    ]
    for dim, s in report["dimension_summary"].items():
        lines.append(f"| {dim} | {s['pass']} | {s['fail']} | {s['na']} |")
    lines += ["", "## Category 汇总", "", "| 类别 | pass | fail | error |", "| --- | --- | --- | --- |"]
    for cat, s in report["category_summary"].items():
        lines.append(f"| {cat} | {s['pass']} | {s['fail']} | {s['error']} |")
    lines += ["", "## 工具统计（注入故障与参数拒绝分开）", "",
              "| 工具 | attempts | argument_rejected | backend_faults(注入) | invalid_results |",
              "| --- | --- | --- | --- | --- |"]
    for tool, s in report["tool_summary"].items():
        lines.append(f"| {tool} | {s['attempts']} | {s['argument_rejected']} | "
                     f"{s['backend_faults']} | {s['invalid_results']} |")
    lines += ["", "## 失败/错误 Case", ""]
    if not report["failure_cases"]:
        lines.append("无。")
    else:
        for fc in report["failure_cases"]:
            lines.append(f"- `{fc['case_id']}` [{fc['overall']}] input={fc['input']!r} "
                         f"维度={fc['failed_dimensions']} 原因={fc['reasons']}")
    lines += ["", "## Baseline 比较", ""]
    lines.append("未比较（本轮未请求 baseline）。" if report["comparison"] is None
                 else str(report["comparison"]))
    lines += ["", "## 说明"] + [f"- {n}" for n in report["notes"]]
    return "\n".join(lines) + "\n"


def write_artifacts(out_dir, report, traces, config=None):
    """产物合同（§10）：run.json（运行元数据）、traces.jsonl、report.json（报告）、report.md。

    report.md 由 report.json 同一结构化数据渲染，不存在第二套计算逻辑（§11）。
    """
    out = create_run_directory(out_dir, report["run_id"])
    run_meta = {
        "run_id": report["run_id"],
        "created_at": report["created_at"],
        "mode": report["mode"],
        "scope": report["scope"],
        "config": config or {},
        "identity": report["identity"],
        "planned_cases": report["planned_cases"],
        "trials": report["trials"],
        "artifacts": ["run.json", "traces.jsonl", "report.json", "report.md"],
    }
    (out / "run.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(out / "traces.jsonl", "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    (out / "report.md").write_text(render_report_md(report), encoding="utf-8")
    return out


# ---------------------------------------------------------------- 重放（§8 / AC15）

def _judgment_of(evaluation: dict) -> dict:
    return {
        "overall": evaluation.get("overall"),
        "dims": {d: (evaluation.get("dimensions", {}).get(d, {}) or {}).get("status")
                 for d in DIMENSIONS},
    }


def replay_eval(traces_path: str, dataset_path: str, out_dir: str, config=None):
    """--replay：只读旧 Trace 与匹配 Case，由相同 Evaluator 重评。

    不执行 Agent、不执行工具；dataset_hash 不匹配立即停止（exit 2 由 CLI 决定）；
    Trace 缺失/损坏记 ERROR。返回 (report|None, stop_reason|None)。
    """
    current_hash = sha256_file(dataset_path)
    cases = {c["case_id"]: c for c in load_cases(dataset_path)}
    old_traces, corrupt_lines = [], []
    with open(traces_path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                decoded = json.loads(line)
                if not isinstance(decoded, dict):
                    corrupt_lines.append(lineno)
                else:
                    old_traces.append(decoded)
            except json.JSONDecodeError:
                corrupt_lines.append(lineno)

    mismatched = sorted({str(t.get("case_id", "<unknown>")) for t in old_traces
                         if t.get("dataset_hash") != current_hash})
    stop_reason = ("DATASET_HASH_MISMATCH" if mismatched else
                   "TRACE_CORRUPT" if corrupt_lines else None)

    results, new_traces = [], []
    counts = {"match": 0, "mismatch": 0, "error": len(corrupt_lines), "fail": 0}
    for lineno in corrupt_lines:
        results.append({"case_id": "<unknown>", "status": "ERROR",
                        "message": f"TRACE_CORRUPT: line {lineno} is not a JSON object"})
    for t in old_traces:
        cid = t.get("case_id", "<unknown>")
        if not isinstance(cid, str):
            cid = "<unknown>"
        if t.get("dataset_hash") != current_hash:
            counts["error"] += 1
            results.append({"case_id": cid, "status": "ERROR",
                            "message": "DATASET_HASH_MISMATCH: 未猜测旧标准答案"})
            continue
        prev_ev = t.get("evaluation_result") or {}
        case = cases.get(cid)
        if (case is None or not isinstance(prev_ev, dict)
                or prev_ev.get("overall") not in ("PASS", "FAIL", "ERROR")
                or not isinstance(prev_ev.get("dimensions"), dict)
                or any(not isinstance(prev_ev["dimensions"].get(d), dict) for d in DIMENSIONS)):
            counts["error"] += 1
            results.append({"case_id": cid, "status": "ERROR",
                            "message": "数据集中无此 Case 或旧 Trace 无判定"})
            continue
        new_ev = evaluate(normalize_case(case), t)
        if new_ev["overall"] == "FAIL":
            counts["fail"] += 1
        prev_j, new_j = _judgment_of(prev_ev), _judgment_of(new_ev)
        match = prev_j == new_j
        counts["match" if match else "mismatch"] += 1
        entry = {"case_id": cid, "status": "MATCH" if match else "MISMATCH",
                 "previous": prev_j, "replayed": new_j}
        if new_ev["overall"] == "ERROR":
            counts["error"] += 1
            entry["status"] = "ERROR"
            entry["message"] = new_ev["failure_reasons"]
        if not match:
            entry["detail"] = [
                f"{d}: {prev_j['dims'][d]} -> {new_j['dims'][d]}"
                for d in DIMENSIONS if prev_j["dims"][d] != new_j["dims"][d]]
            if prev_j["overall"] != new_j["overall"]:
                entry["detail"].append(f"overall: {prev_j['overall']} -> {new_j['overall']}")
        results.append(entry)
        t2 = json.loads(json.dumps(t, ensure_ascii=False))
        t2["evaluation_result"] = new_ev
        t2["failure_reasons"] = new_ev["failure_reasons"]
        t2["replay"] = {"previous_overall": prev_j["overall"],
                        "replayed_overall": new_j["overall"], "match": match}
        new_traces.append(t2)

    run_id = new_run_id("replay")
    report = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "replay",
        "scope": "full" if len(new_traces) == len(cases) else "subset",
        "source_traces": traces_path,
        "dataset_hash": current_hash,
        "cases": len(new_traces),
        "judgment_match": counts["match"],
        "judgment_mismatch": counts["mismatch"],
        "error": counts["error"],
        "fail": counts["fail"],
        "run_errors": [] if new_traces else ["NO_EXECUTABLE_TRIALS: 没有可重评的 Trace"],
        "status": stop_reason or "COMPLETED",
        "mismatched_cases": mismatched,
        "corrupt_lines": corrupt_lines,
        "results": results,
        "evaluator_version": EVALUATOR_VERSION,
        "notes": [
            "重放不执行 Agent 与工具，只做 Evaluator 重评（§8）。",
            "同一 Evaluator 版本下判定应完全一致；MISMATCH 属发现缺陷，不是重新运行。",
        ],
    }
    write_replay_artifacts(out_dir, report, new_traces)
    return report, stop_reason


def render_replay_md(report: dict) -> str:
    lines = [
        f"# Replay Report — {report['run_id']}",
        "",
        f"- source: `{report['source_traces']}`",
        f"- cases={report['cases']} match={report['judgment_match']} "
        f"mismatch={report['judgment_mismatch']} error={report['error']}",
        f"- evaluator={report['evaluator_version']} dataset_hash={report['dataset_hash'][:12]}…",
        "",
    ]
    for r in report["results"]:
        if r["status"] == "MATCH":
            lines.append(f"- `{r['case_id']}` MATCH overall={r['previous']['overall']}")
        else:
            lines.append(f"- `{r['case_id']}` {r['status']} detail={r.get('detail', r.get('message'))}")
    lines += [""] + [f"- {n}" for n in report["notes"]]
    lines += [f"- ERROR: {n}" for n in report.get("run_errors", [])]
    return "\n".join(lines) + "\n"


def write_replay_artifacts(out_dir, report, new_traces):
    out = create_run_directory(out_dir, report["run_id"])
    (out / "run.json").write_text(json.dumps(
        {"run_id": report["run_id"], "mode": "replay", "source": report["source_traces"],
         "artifacts": ["run.json", "traces.jsonl", "report.json", "report.md"]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(out / "traces.jsonl", "w", encoding="utf-8") as f:
        for t in new_traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    (out / "report.md").write_text(render_replay_md(report), encoding="utf-8")
    return out


# ---------------------------------------------------------------- 重复执行一致性（§9 P0 三次离线）

def check_determinism(cases, fixtures_path, dataset_path, repeats=3, config=None):
    """同一版本全量离线执行 N 次，剥离易变字段后比较答案/调用/判定（§9/AC16）。"""
    if repeats < 2:
        raise ValueError("check_determinism 需要 repeats>=2")
    runs, signatures = [], []
    for i in range(repeats):
        report, traces = run_suite(cases, fixtures_path, dataset_path,
                                   run_id=f"det-run{i + 1}", config=config)
        runs.append({"run_id": report["run_id"], "pass": report["pass"],
                     "fail": report["fail"], "error": report["error"], "score": report["score"],
                     "run_errors": report["run_errors"], "exit_code": classify_exit_code(report)})
        signatures.append([normalize_trace_for_compare(t) for t in traces])
    identical = all(signatures[0] == s for s in signatures[1:])
    first_diff = None
    if not identical:
        for i, s in enumerate(signatures[1:], 1):
            for j, (a, b) in enumerate(zip(signatures[0], s)):
                if a != b:
                    first_diff = {"run": i + 1, "case_index": j,
                                  "case_id_a": a.get("case_id"), "case_id_b": b.get("case_id")}
                    break
            if first_diff:
                break
    return {"repeats": repeats, "identical": identical, "runs": runs,
            "exit_code": max([r["exit_code"] for r in runs] + [0 if identical else 1]),
            "first_difference": first_diff,
            "comparison_fields": ["agent_output", "tool_calls", "evaluation_result"]}


# ---------------------------------------------------------------- Baseline 比较（§9 / AC13/AC14）

def compare_runs(baseline_traces, current_traces,
                 baseline_report=None, current_report=None):
    """compare_runs(baseline, current) → Comparison。

    可比性：dataset_hash / fixtures_hash / evaluator_version / tool_schema_hash / mode /
    Case 集合与 trials 方案必须一致，否则 NOT_COMPARABLE（不写"无回归"）。
    未调用即 NOT_REQUESTED，由调用方以 comparison=None 表达。
    """
    base_id = (baseline_report or {}).get("identity", {})
    cur_id = (current_report or {}).get("identity", {})
    checks = [
        ("dataset_hash", base_id.get("dataset_hash"), cur_id.get("dataset_hash")),
        ("fixtures_hash", base_id.get("fixtures_hash"), cur_id.get("fixtures_hash")),
        ("evaluator_version", base_id.get("evaluator_version"), cur_id.get("evaluator_version")),
        ("tool_schema_hash", base_id.get("tool_schema_hash"), cur_id.get("tool_schema_hash")),
        ("mode", (baseline_report or {}).get("mode"), (current_report or {}).get("mode")),
    ]
    reasons = [f"{name}: baseline={b!r} current={c!r}" for name, b, c in checks if b != c]

    def by_case(traces):
        out = {}
        for t in traces:
            if not isinstance(t, dict) or not isinstance(t.get("case_id"), str):
                reasons.append("Trace 缺少合法 case_id")
                continue
            ev = t.get("evaluation_result")
            if (not isinstance(ev, dict) or ev.get("overall") not in ("PASS", "FAIL", "ERROR")
                    or not isinstance(ev.get("dimensions"), dict)
                    or any(not isinstance(ev["dimensions"].get(d), dict)
                           or ev["dimensions"][d].get("status") not in ("PASS", "FAIL", "N/A")
                           for d in DIMENSIONS)):
                reasons.append(f"{t['case_id']}: evaluation_result 合同损坏")
                continue
            if t.get("trial_index", 1) != 1:
                reasons.append(f"{t['case_id']}: 当前仅支持 single-trial，trial_index 必须为 1")
            out.setdefault(t["case_id"], []).append(t)
        if not out:
            reasons.append("没有可比较的有效 trial")
        if any(len(items) != 1 for items in out.values()):
            reasons.append("当前仅支持 single-trial；重复 trial 不可比较")
        return out

    base_map, cur_map = by_case(baseline_traces), by_case(current_traces)
    if set(base_map) != set(cur_map):
        reasons.append(f"case 集合不同: baseline_only={sorted(set(base_map) - set(cur_map))} "
                       f"current_only={sorted(set(cur_map) - set(base_map))}")
    else:
        for cid in sorted(base_map):
            if len(base_map[cid]) != len(cur_map[cid]):
                reasons.append(f"trials 方案不同: {cid} baseline={len(base_map[cid])} "
                               f"current={len(cur_map[cid])}")
    if reasons:
        return {"status": "NOT_COMPARABLE", "comparable": False, "reasons": reasons,
                "baseline_run_id": (baseline_report or {}).get("run_id"),
                "current_run_id": (current_report or {}).get("run_id")}

    regressions, improvements, unchanged_fail, dim_regressions = [], [], [], []
    unchanged_pass = 0
    for cid in sorted(base_map):
        b = base_map[cid][0]["evaluation_result"]["overall"]
        c = cur_map[cid][0]["evaluation_result"]["overall"]
        if b == "PASS" and c in ("FAIL", "ERROR"):
            regressions.append({"case_id": cid, "from": b, "to": c})
        elif b in ("FAIL", "ERROR") and c == "PASS":
            improvements.append({"case_id": cid, "from": b, "to": c})
        elif b == "PASS":
            unchanged_pass += 1
        else:
            unchanged_fail.append(cid)
        b_dims = base_map[cid][0]["evaluation_result"]["dimensions"]
        c_dims = cur_map[cid][0]["evaluation_result"]["dimensions"]
        for d in DIMENSIONS:
            if b_dims[d]["status"] == "PASS" and c_dims[d]["status"] == "FAIL":
                # 维度退化即使 Case 整体原本已失败也要列出（§9）
                dim_regressions.append({"case_id": cid, "dimension": d})
    return {
        "status": "OK", "comparable": True, "reasons": [],
        "baseline_run_id": (baseline_report or {}).get("run_id"),
        "current_run_id": (current_report or {}).get("run_id"),
        "new_regressions": regressions,
        "improvements": improvements,
        "unchanged_failures": unchanged_fail,
        "unchanged_pass": unchanged_pass,
        "dimension_regressions": dim_regressions,
        "baseline_score": (baseline_report or {}).get("score"),
        "current_score": (current_report or {}).get("score"),
    }


def load_run_artifacts(run_dir):
    """从完整运行目录加载单 trial baseline；不接受仅报告摘要。"""
    run_dir = Path(run_dir)
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    if not isinstance(report, dict) or not isinstance(report.get("identity"), dict):
        raise ValueError("baseline report 必须包含 identity 对象")
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if not isinstance(meta, dict) or not isinstance(meta.get("config", {}), dict):
        raise ValueError("baseline run.json 合同损坏")
    if meta.get("config", {}).get("repeat", 1) != 1:
        raise ValueError("baseline repeat 不受支持；当前仅支持 repeat=1")
    traces = [json.loads(line) for line in
              (run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if meta.get("run_id") != report.get("run_id") or any(
            not isinstance(t, dict) or t.get("run_id") != report.get("run_id") for t in traces):
        raise ValueError("baseline 产物 run_id 不一致")
    if report.get("trials") != len(traces) or meta.get("trials") != len(traces):
        raise ValueError("baseline trial 数量与 Trace 不一致")
    return report, traces
