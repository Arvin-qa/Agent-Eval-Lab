"""Runner/回归层测试：分母、退出码、重复执行一致性（AC11/AC16 的本轮范围）。"""
import copy

from order_eval.evaluator import evaluate
from order_eval.runner import (
    classify_exit_code,
    compute_score,
    normalize_trace_for_compare,
    run_suite,
    run_trial,
)
from order_eval.schemas import load_cases

FIXTURES = "datasets/fixtures.json"
CASES = "datasets/cases.jsonl"


def _minimal_report(pass_count=0, fail=0, error=0):
    return {"pass": pass_count, "fail": fail, "error": error}


class TestScoreAndDenominator:
    """AC11：PASS/FAIL/ERROR 合计等于预定 trials；ERROR 保留在分母、不算成功。"""

    def test_denominator_sums_to_planned(self):
        cases = load_cases(CASES)
        report, traces = run_suite(cases, FIXTURES, CASES, run_id="test-denominator")
        assert report["planned_cases"] == report["pass"] + report["fail"] + report["error"]
        assert report["trials"] == len(cases)

    def test_ac11_example_25_2_1_of_28_is_89_29(self):
        # 验收文档要求的格式验算样例：28 planned，25 PASS、2 FAIL、1 ERROR → 89.29
        assert compute_score(25, 28) == 89.29
        assert 25 + 2 + 1 == 28

    def test_error_keeps_denominator_and_forces_exit_2(self):
        assert classify_exit_code(_minimal_report(pass_count=27, error=1)) == 2
        assert compute_score(27, 28) == 96.43  # ERROR 不算成功

    def test_exit_code_mapping(self):
        assert classify_exit_code(_minimal_report(pass_count=6)) == 0
        assert classify_exit_code(_minimal_report(pass_count=5, fail=1)) == 1


class TestOfflineDeterminism:
    """AC16 本轮范围：同版本重复执行，剥离易变字段后答案/调用/判定一致。"""

    def test_two_full_runs_structurally_identical(self):
        cases = load_cases(CASES)
        report1, traces1 = run_suite(cases, FIXTURES, CASES, run_id="run-A")
        report2, traces2 = run_suite(cases, FIXTURES, CASES, run_id="run-B")
        assert report1["pass"] == report2["pass"]
        n1 = [normalize_trace_for_compare(t) for t in traces1]
        n2 = [normalize_trace_for_compare(t) for t in traces2]
        assert n1 == n2

    def test_normalization_removes_volatile_keeps_business_fields(self):
        case = load_cases(CASES)[0]
        trace = run_trial(case, FIXTURES, CASES, run_id="run-X")
        norm = normalize_trace_for_compare(trace)
        assert "run_id" not in norm
        assert norm["started_at"] == "" and norm["ended_at"] == ""
        assert norm["metrics"]["total_duration_ms"] == 0
        # 业务字段必须保留：不得靠删除错误/参数制造假一致
        assert norm["tool_calls"][0]["arguments_raw"] == {"order_id": "ORD-1001"}
        assert norm["agent_output"] == trace["agent_output"]

    def test_single_case_subset_scope(self):
        cases = [c for c in load_cases(CASES) if c["case_id"] == "N02"]
        report, traces = run_suite(cases, FIXTURES, CASES, run_id="run-subset", scope="subset")
        assert report["scope"] == "subset"
        assert report["planned_cases"] == 1


class TestErrorNotMasked:
    """执行器中止（超预算）必须记 ERROR，不能装成业务降级（§6.1）。"""

    def test_aborted_execution_is_error(self):
        case = next(c for c in load_cases(CASES) if c["case_id"] == "N01")
        trace = run_trial(case, FIXTURES, CASES)
        assert trace["execution_status"] == "completed"  # 基线：种子数据不会中止

        # 构造一个 aborted trace：评测应判 ERROR（AC 第 2 节：框架错误 ≠ 业务 unavailable）
        aborted = copy.deepcopy(trace)
        aborted["execution_status"] = "aborted"
        ev = evaluate(case, aborted)
        assert ev["overall"] == "ERROR"

        broken = copy.deepcopy(trace)
        broken.pop("tool_calls")  # Trace 损坏
        ev2 = evaluate(case, broken)
        assert ev2["overall"] == "ERROR"


# ---------------------------------------------------------------- 阶段3：重放（AC15）

import json
import copy

from order_eval.runner import compare_runs, check_determinism, replay_eval, render_report_md
from order_eval import tools as tools_mod
from order_eval.agent import MockAgent


def _write_traces(tmp_path, traces):
    p = tmp_path / "traces.jsonl"
    p.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in traces) + "\n",
                 encoding="utf-8")
    return str(p)


class TestReplay:
    def test_replay_same_evaluator_all_match(self, tmp_path):
        cases = load_cases(CASES)
        _, traces = run_suite(cases, FIXTURES, CASES, run_id="replay-src")
        rep, stop = replay_eval(_write_traces(tmp_path, traces), CASES, str(tmp_path / "out"))
        assert stop is None
        assert rep["judgment_mismatch"] == 0 and rep["error"] == 0
        assert rep["judgment_match"] == len(cases)

    def test_replay_does_not_execute_agent_or_tools(self, tmp_path, monkeypatch):
        def boom_tools(self, *a, **k):
            raise AssertionError("replay 不得执行工具")
        def boom_agent(self, *a, **k):
            raise AssertionError("replay 不得执行 Agent")
        monkeypatch.setattr(tools_mod.Executor, "execute", boom_tools)
        monkeypatch.setattr(MockAgent, "run", boom_agent)
        cases = load_cases(CASES)
        _, traces = run_suite(cases, FIXTURES, CASES, run_id="replay-src2")
        rep, stop = replay_eval(_write_traces(tmp_path, traces), CASES, str(tmp_path / "out"))
        assert stop is None and rep["judgment_match"] == len(cases)

    def test_replay_dataset_hash_mismatch_stops(self, tmp_path):
        cases = load_cases(CASES)
        _, traces = run_suite(cases[:1], FIXTURES, CASES, run_id="replay-src3")
        traces[0]["dataset_hash"] = "deadbeef"
        rep, stop = replay_eval(_write_traces(tmp_path, traces), CASES, str(tmp_path / "out"))
        assert stop == "DATASET_HASH_MISMATCH"
        assert rep["status"] == "DATASET_HASH_MISMATCH"
        assert rep["mismatched_cases"] == ["N01"]

    def test_replay_corrupt_trace_is_error(self, tmp_path):
        p = tmp_path / "traces.jsonl"
        cases = load_cases(CASES)
        _, traces = run_suite(cases[:1], FIXTURES, CASES, run_id="replay-src4")
        p.write_text(json.dumps(traces[0], ensure_ascii=False) + "\n{broken json\n",
                     encoding="utf-8")
        rep, stop = replay_eval(str(p), CASES, str(tmp_path / "out"))
        assert stop == "TRACE_CORRUPT" and rep["corrupt_lines"] == [2]
        assert rep["judgment_match"] == 1 and rep["error"] == 1
        assert (tmp_path / "out" / rep["run_id"] / "report.json").exists()


# ---------------------------------------------------------------- 阶段5：Baseline 比较（AC13/AC14）

def _dims(failing=None):
    failing = failing or set()
    return {d: {"status": "FAIL" if d in failing else "PASS", "checks": []}
            for d in ["task_success", "tool_selection", "tool_argument",
                      "groundedness", "output_format", "constraint_following"]}


def _synth_trace(cid, overall):
    failing = {"task_success"} if overall == "FAIL" else set()
    return {"case_id": cid,
            "evaluation_result": {"overall": overall, "dimensions": _dims(failing)}}


def _synth_report(run_id, pairs):
    return {"run_id": run_id, "mode": "offline", "score": None,
            "identity": {"dataset_hash": "D", "fixtures_hash": "F",
                         "evaluator_version": "0.1", "tool_schema_hash": "T"}}


class TestCompareRuns:
    def test_pass_to_fail_is_regression(self):
        base = [_synth_trace("A", "PASS"), _synth_trace("B", "PASS")]
        cur = [_synth_trace("A", "PASS"), _synth_trace("B", "FAIL")]
        cmp = compare_runs(base, cur, _synth_report("b1", None), _synth_report("c1", None))
        assert cmp["comparable"] and cmp["status"] == "OK"
        assert cmp["new_regressions"] == [{"case_id": "B", "from": "PASS", "to": "FAIL"}]

    def test_fail_to_pass_is_improvement(self):
        base = [_synth_trace("A", "FAIL")]
        cur = [_synth_trace("A", "PASS")]
        cmp = compare_runs(base, cur, _synth_report("b1", None), _synth_report("c1", None))
        assert cmp["improvements"] == [{"case_id": "A", "from": "FAIL", "to": "PASS"}]

    def test_same_total_score_still_reports_case_regression(self):
        # 一条变好、一条变坏、总分不变：仍必须列出 Case 级 regression（§9）
        base = [_synth_trace("A", "FAIL"), _synth_trace("B", "PASS")]
        cur = [_synth_trace("A", "PASS"), _synth_trace("B", "FAIL")]
        cmp = compare_runs(base, cur, _synth_report("b1", None), _synth_report("c1", None))
        assert len(cmp["improvements"]) == 1 and len(cmp["new_regressions"]) == 1

    def test_dimension_regression_listed_even_if_case_already_failed(self):
        base = [_synth_trace("A", "FAIL")]
        cur = [_synth_trace("A", "FAIL")]
        # Case 整体两版都 FAIL，但 tool_selection 从 PASS 退化为 FAIL
        cur[0]["evaluation_result"]["dimensions"]["tool_selection"] = {
            "status": "FAIL", "checks": []}
        cmp = compare_runs(base, cur, _synth_report("b1", None), _synth_report("c1", None))
        assert {"case_id": "A", "dimension": "tool_selection"} in cmp["dimension_regressions"]

    def test_not_comparable_on_dataset_change(self):
        base_report = _synth_report("b1", None)
        cur_report = _synth_report("c1", None)
        cur_report["identity"]["dataset_hash"] = "D2"
        cmp = compare_runs([_synth_trace("A", "PASS")], [_synth_trace("A", "PASS")],
                           base_report, cur_report)
        assert cmp["status"] == "NOT_COMPARABLE" and not cmp["comparable"]
        assert any("dataset_hash" in r for r in cmp["reasons"])

    def test_not_comparable_on_mode_change(self):
        base_report = _synth_report("b1", None)
        cur_report = _synth_report("c1", None)
        cur_report["mode"] = "llm"
        cmp = compare_runs([_synth_trace("A", "PASS")], [_synth_trace("A", "PASS")],
                           base_report, cur_report)
        assert cmp["status"] == "NOT_COMPARABLE"
        assert any("mode" in r for r in cmp["reasons"])

    def test_report_without_comparison_says_not_requested(self):
        cases = load_cases(CASES)
        report, traces = run_suite(cases, FIXTURES, CASES, run_id="no-baseline")
        assert report["comparison"] is None
        assert "未比较" in render_report_md(report)
        assert "无回归" not in render_report_md(report)


# ---------------------------------------------------------------- 阶段4：三次执行确定性（AC16）

class TestDeterminismThreeRuns:
    def test_three_full_runs_identical(self):
        cases = load_cases(CASES)
        result = check_determinism(cases, FIXTURES, CASES, repeats=3)
        assert result["identical"] is True, result["first_difference"]
        assert result["repeats"] == 3
        assert all(r["pass"] == len(cases) for r in result["runs"])

    def test_call_id_normalization_rewrites_evidence_refs(self):
        case = load_cases(CASES)[1]  # N02：两个 call + 3 条 evidence
        trace = run_trial(case, FIXTURES, CASES, run_id="norm-check")
        trace["tool_calls"][0]["call_id"] = "xyz-random-9"  # 模拟随机 id
        for ev in trace["agent_output"]["evidence"]:
            if ev["call_id"] == "xyz-random-9":
                pass
        norm = normalize_trace_for_compare(trace)
        # 规范化后 call_id 重编号且 evidence 引用同步
        first = norm["tool_calls"][0]["call_id"]
        assert first == "call-1"
        refs = {ev["call_id"] for ev in norm["agent_output"]["evidence"]}
        assert refs <= {"call-1", "call-2"}
