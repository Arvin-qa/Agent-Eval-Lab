"""Release regressions: damaged evidence must never become a silent PASS."""
import copy
import json
import subprocess
import sys

import pytest

from order_eval.evaluator import EVALUATOR_VERSION, evaluate
from order_eval.runner import compare_runs, replay_eval, run_suite, run_trial
from order_eval.schemas import load_cases
from run_eval import main

CASES = "datasets/cases.jsonl"
FIXTURES = "datasets/fixtures.json"


@pytest.fixture
def n01():
    case = load_cases(CASES)[0]
    return case, run_trial(case, FIXTURES, CASES)


def test_invalid_raw_with_correct_parsed_is_error(n01):
    case, trace = n01
    trace["agent_output_raw"] = "THIS IS NOT JSON"
    ev = evaluate(case, trace)
    assert ev["overall"] == "ERROR"
    assert any(r["reason_code"] == "SYS-OUTPUT-INTEGRITY" for r in ev["failure_reasons"])


def test_raw_parsed_disagreement_is_error(n01):
    case, trace = n01
    raw = copy.deepcopy(trace["agent_output"])
    raw["facts"]["order_status"] = "SHIPPED"
    trace["agent_output_raw"] = json.dumps(raw)
    assert evaluate(case, trace)["overall"] == "ERROR"


@pytest.mark.parametrize("field,value", [
    ("tool_calls", [{}]), ("tool_calls", [None]),
    ("tool_calls", "bad"), ("trace_version", []),
    ("execution_status", {}), ("user_input", None),
])
def test_damaged_trace_fields_are_readable_errors(n01, field, value):
    case, trace = n01
    trace[field] = value
    ev = evaluate(case, trace)
    assert ev["overall"] == "ERROR"
    assert ev["failure_reasons"][0]["message"]


@pytest.mark.parametrize("field,value", [
    ("selected_tool", []), ("call_id", {}), ("tool_arguments", []),
    ("tool_result", {"ok": True, "data": []}),
    ("tool_result", {}), ("error_code", []), ("validation_result", "bogus"),
])
def test_damaged_tool_fields_are_readable_errors(n01, field, value):
    case, trace = n01
    trace["tool_calls"][0][field] = value
    ev = evaluate(case, trace)
    assert ev["overall"] == "ERROR"
    assert "tool_calls" in ev["failure_reasons"][0]["message"]


def test_json_whitespace_and_object_key_order_do_not_matter(n01):
    case, trace = n01
    trace["agent_output_raw"] = json.dumps(trace["agent_output"], indent=4, sort_keys=True)
    assert evaluate(case, trace)["overall"] == "PASS"


def test_replay_keeps_good_case_when_another_trace_is_damaged(tmp_path):
    _, traces = run_suite(load_cases(CASES)[:2], FIXTURES, CASES)
    traces[0]["tool_calls"] = [{}]
    source = tmp_path / "source.jsonl"
    source.write_text("\n".join(json.dumps(t) for t in traces), encoding="utf-8")
    report, stop = replay_eval(str(source), CASES, str(tmp_path / "out"))
    assert stop is None
    assert report["error"] == 1
    assert report["results"][0]["status"] == "ERROR"
    assert report["results"][1]["status"] == "MATCH"
    saved = (tmp_path / "out" / report["run_id"] / "traces.jsonl").read_text(encoding="utf-8")
    assert len(saved.splitlines()) == 2


def test_old_evaluator_baseline_is_not_comparable(n01):
    case, _ = n01
    report, traces = run_suite([case], FIXTURES, CASES)
    old = copy.deepcopy(report)
    old["identity"]["evaluator_version"] = "0.1"
    assert EVALUATOR_VERSION != "0.1"
    assert compare_runs(traces, traces, old, report)["status"] == "NOT_COMPARABLE"


@pytest.mark.parametrize("kind", ["empty_dataset", "empty_replay", "all_skipped",
                                  "missing_fixtures", "missing_replay", "output_file"])
def test_invalid_cli_inputs_exit_two_without_traceback(tmp_path, kind):
    out = tmp_path / "out"
    args = ["--out", str(out)]
    if kind in ("empty_dataset", "empty_replay"):
        empty = tmp_path / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        args += ["--dataset" if kind == "empty_dataset" else "--replay", str(empty)]
    elif kind == "all_skipped":
        from order_eval.schemas import needs_context
        cases = load_cases("datasets/expansion/round_001.jsonl")
        source = tmp_path / "skipped.jsonl"
        source.write_text(json.dumps(next(c for c in cases if needs_context(c))), encoding="utf-8")
        args += ["--dataset", str(source)]
    elif kind == "missing_fixtures":
        args += ["--case", "N01", "--fixtures", str(tmp_path / "missing.json")]
    elif kind == "missing_replay":
        args += ["--replay", str(tmp_path / "missing.jsonl")]
    else:
        out.write_text("keep me", encoding="utf-8")
        args += ["--case", "N01"]
    proc = subprocess.run([sys.executable, "-X", "utf8", "run_eval.py", *args],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Traceback" not in proc.stderr
    assert "错误" in proc.stdout + proc.stderr or "ERROR" in proc.stdout + proc.stderr
    if kind == "output_file":
        assert out.read_text(encoding="utf-8") == "keep me"
    if kind in ("empty_dataset", "empty_replay", "all_skipped", "missing_fixtures"):
        reports = list(out.glob("*/report.json"))
        assert len(reports) == 1
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        assert report.get("run_errors") or report.get("error")


def test_unwritable_output_readable_stderr(tmp_path, monkeypatch, capsys):
    import run_eval
    def deny(*args, **kwargs):
        raise PermissionError("permission denied for output")
    monkeypatch.setattr(run_eval, "write_artifacts", deny)
    assert main(["--case", "N01", "--out", str(tmp_path)]) == 2
    assert "permission denied" in capsys.readouterr().err


def test_bad_fixture_keeps_previously_completed_case(tmp_path):
    from order_eval.runner import classify_exit_code, write_artifacts
    cases = load_cases(CASES)[:2]
    cases[1]["fixture_id"] = "missing-fixture"
    report, traces = run_suite(cases, FIXTURES, CASES)
    assert [t["evaluation_result"]["overall"] for t in traces] == ["PASS", "ERROR"]
    assert report["pass"] == 1 and report["error"] == 1
    assert classify_exit_code(report) == 2
    dest = write_artifacts(tmp_path, report, traces)
    assert len((dest / "traces.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_t02_timeout_degradation_still_exits_zero(tmp_path):
    assert main(["--case", "T02", "--out", str(tmp_path)]) == 0


def test_determinism_does_not_turn_identical_errors_into_success(tmp_path):
    assert main(["--fixtures", str(tmp_path / "missing"), "--check-determinism", "3",
                 "--out", str(tmp_path / "out")]) == 2


def test_replay_matched_business_failure_is_not_success(tmp_path, n01):
    case, trace = n01
    trace["agent_output"]["evidence"][0]["call_id"] = "missing"
    trace["agent_output_raw"] = json.dumps(trace["agent_output"])
    trace["evaluation_result"] = evaluate(case, trace)
    assert trace["evaluation_result"]["overall"] == "FAIL"
    path = tmp_path / "fail.jsonl"
    path.write_text(json.dumps(trace), encoding="utf-8")
    assert main(["--replay", str(path), "--out", str(tmp_path / "out")]) == 1


def test_same_clock_tick_still_produces_distinct_run_ids(monkeypatch):
    import order_eval.runner as runner
    from datetime import datetime, timezone
    class FrozenClock:
        @staticmethod
        def now(*args):
            return datetime(2026, 9, 16, tzinfo=timezone.utc)
    monkeypatch.setattr(runner, "datetime", FrozenClock)
    case = load_cases(CASES)[0]
    a, _ = run_suite([case], FIXTURES, CASES)
    b, _ = run_suite([case], FIXTURES, CASES)
    assert a["run_id"] != b["run_id"]


@pytest.mark.parametrize("replay", [False, True])
def test_existing_run_directory_is_never_overwritten(tmp_path, n01, replay):
    from order_eval.runner import write_artifacts, write_replay_artifacts
    case, trace = n01
    if replay:
        source = tmp_path / "source.jsonl"
        source.write_text(json.dumps(trace), encoding="utf-8")
        report, _ = replay_eval(str(source), CASES, str(tmp_path / "out"))
        writer = write_replay_artifacts
    else:
        report, traces = run_suite([case], FIXTURES, CASES)
        writer = write_artifacts
        writer(tmp_path / "out", report, traces)
    dest = tmp_path / "out" / report["run_id"]
    before = {p.name: p.read_bytes() for p in dest.iterdir()}
    with pytest.raises(FileExistsError):
        writer(tmp_path / "out", report, [])
    assert before == {p.name: p.read_bytes() for p in dest.iterdir()}


def test_concurrent_cli_keeps_two_complete_runs(tmp_path):
    procs = [subprocess.Popen(
        [sys.executable, "-X", "utf8", "run_eval.py", "--case", cid, "--out", str(tmp_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
    ) for cid in ("N01", "N02")]
    for proc in procs:
        stdout, stderr = proc.communicate(timeout=60)
        assert proc.returncode == 0, stdout + stderr
    runs = list(tmp_path.iterdir())
    assert len(runs) == 2
    ids = set()
    for dest in runs:
        assert {p.name for p in dest.iterdir()} == {"run.json", "traces.jsonl", "report.json", "report.md"}
        meta = json.loads((dest / "run.json").read_text(encoding="utf-8"))
        report = json.loads((dest / "report.json").read_text(encoding="utf-8"))
        traces = [json.loads(line) for line in (dest / "traces.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(traces) == report["trials"] == meta["trials"] == 1
        assert report["run_id"] == meta["run_id"] == traces[0]["run_id"] == dest.name
        assert report["pass"] == 1 and traces[0]["evaluation_result"]["overall"] == "PASS"
        assert dest.name in (dest / "report.md").read_text(encoding="utf-8")
        ids.add(traces[0]["case_id"])
    assert ids == {"N01", "N02"}


@pytest.mark.parametrize("repeat", [0, 2, 3])
def test_unsupported_repeat_is_rejected_before_execution(tmp_path, capsys, repeat):
    out = tmp_path / "out"
    assert main(["--case", "N01", "--repeat", str(repeat), "--out", str(out)]) == 2
    assert "--repeat" in capsys.readouterr().err
    assert not out.exists()


def test_run_suite_also_rejects_unsupported_repeat():
    with pytest.raises(ValueError, match="repeat"):
        run_suite(load_cases(CASES)[:1], FIXTURES, CASES, config={"repeat": 2})


def test_single_trial_index_is_one_for_each_case():
    _, traces = run_suite(load_cases(CASES)[:2], FIXTURES, CASES, config={"repeat": 1})
    assert [t["trial_index"] for t in traces] == [1, 1]


def test_duplicate_trials_never_report_no_regression(n01):
    case, _ = n01
    report, traces = run_suite([case], FIXTURES, CASES)
    baseline = traces + copy.deepcopy(traces)
    current = copy.deepcopy(baseline)
    current[1]["evaluation_result"]["overall"] = "FAIL"
    result = compare_runs(baseline, current, report, report)
    assert result["status"] == "NOT_COMPARABLE"
    assert any("single-trial" in r for r in result["reasons"])


def test_baseline_declaring_repeat_two_is_rejected(tmp_path, n01):
    from order_eval.runner import load_run_artifacts, write_artifacts
    case, _ = n01
    report, traces = run_suite([case], FIXTURES, CASES)
    out = write_artifacts(tmp_path, report, traces, config={"repeat": 2})
    with pytest.raises(ValueError, match="repeat"):
        load_run_artifacts(out)


def test_malformed_baseline_is_readable_error(tmp_path, capsys):
    (tmp_path / "report.json").write_text("[]", encoding="utf-8")
    (tmp_path / "traces.jsonl").write_text("{}", encoding="utf-8")
    assert main(["--baseline", str(tmp_path), "--case", "N01"]) == 2
    assert "baseline" in capsys.readouterr().err


def test_empty_baseline_not_comparable(n01):
    case, _ = n01
    report, _ = run_suite([case], FIXTURES, CASES)
    assert compare_runs([], [], report, report)["status"] == "NOT_COMPARABLE"
