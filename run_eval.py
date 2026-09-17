"""OrderTrace Eval CLI：argparse 入口、读配置、调用 Runner，不写业务判断（PROJECT_SPEC §11）。

退出码：0=全部 PASS 且可比 baseline 无 regression；1=存在 FAIL/regression/判定不一致；
2=配置/数据/运行基础设施 ERROR 或 NOT_COMPARABLE。无 Key、默认离线。
"""
import argparse
import sys

from order_eval.runner import (
    check_determinism,
    classify_exit_code,
    compare_runs,
    create_run_directory,
    load_run_artifacts,
    new_run_id,
    replay_eval,
    run_suite,
    write_artifacts,
)
from order_eval.schemas import load_cases

DEFAULT_DATASET = "datasets/cases.jsonl"
DEFAULT_FIXTURES = "datasets/fixtures.json"
DEFAULT_OUT = "artifacts"


def build_parser():
    p = argparse.ArgumentParser(
        prog="run_eval.py",
        description="只读订单查询 Agent 的离线评测（合成数据，Mock 参考实现）",
    )
    p.add_argument("--mode", choices=["offline", "llm"], default="offline",
                   help="offline=确定性 Mock（默认，无 Key）；llm=P1 未实现，明确报错")
    p.add_argument("--case", action="append", default=None, metavar="CASE_ID",
                   help="只跑指定 Case（可重复）；报告标记 subset，不替代全量验收")
    p.add_argument("--dataset", default=DEFAULT_DATASET, help="冻结的 cases.jsonl")
    p.add_argument("--fixtures", default=DEFAULT_FIXTURES, help="fixtures.json")
    p.add_argument("--out", default=DEFAULT_OUT, help="产物目录 artifacts/<run_id>/")
    p.add_argument("--repeat", type=int, default=1,
                   help="当前 Release 仅支持 --repeat 1；重复一致性使用 --check-determinism N")
    p.add_argument("--replay", default=None, metavar="TRACES_JSONL",
                   help="重放：只读旧 Trace 由相同 Evaluator 重评，不执行 Agent/工具")
    p.add_argument("--baseline", default=None, metavar="RUN_DIR",
                   help="已保存运行目录（含 run.json/report.json/traces.jsonl）；仅单 trial，不可比退出 2")
    p.add_argument("--check-determinism", type=int, default=None, metavar="N",
                   help="全量离线连续执行 N 次（N>=2），剥离易变字段后比较结构化一致性")
    return p


def _run_normal(args, cases, selected, scope, config) -> int:
    baseline_comparison = None
    baseline_traces = baseline_report = None
    if args.baseline:
        try:
            baseline_report, baseline_traces = load_run_artifacts(args.baseline)
        except (OSError, ValueError, KeyError) as exc:
            print(f"[配置错误] 无法加载 baseline：{exc}", file=sys.stderr)
            return 2

    report, traces = run_suite(selected, args.fixtures, args.dataset,
                               mode=args.mode, config=config, scope=scope)
    if args.baseline:
        current_for_compare = dict(report)
        baseline_comparison = compare_runs(baseline_traces, traces,
                                           baseline_report=baseline_report,
                                           current_report=current_for_compare)
        report["comparison"] = baseline_comparison

    out_dir = write_artifacts(args.out, report, traces, config=config)

    print(f"run_id={report['run_id']}  scope={report['scope']}  mode={report['mode']}")
    print(f"planned={report['planned_cases']} trials={report['trials']} "
          f"PASS={report['pass']} FAIL={report['fail']} ERROR={report['error']} "
          f"score={report['score']}")
    for fc in report["failure_cases"]:
        print(f"  失败 {fc['case_id']} [{fc['overall']}] {fc['reasons']}")
    for error in report.get("run_errors", []):
        print(f"[运行错误] {error}", file=sys.stderr)
    if baseline_comparison is not None:
        cmp = baseline_comparison
        if cmp["status"] == "NOT_COMPARABLE":
            print(f"  baseline 比较：NOT_COMPARABLE（{cmp['baseline_run_id']} vs {cmp['current_run_id']}）")
            for r in cmp["reasons"]:
                print(f"    - {r}")
        else:
            print(f"  baseline {cmp['baseline_run_id']}：regressions={len(cmp['new_regressions'])} "
                  f"improvements={len(cmp['improvements'])} "
                  f"unchanged_failures={len(cmp['unchanged_failures'])} "
                  f"维度退化={len(cmp['dimension_regressions'])}")
            for r in cmp["new_regressions"]:
                print(f"    - regression {r['case_id']}: {r['from']}→{r['to']}")
            for r in cmp["improvements"]:
                print(f"    - improvement {r['case_id']}: {r['from']}→{r['to']}")
    elif args.baseline is None:
        print("  baseline：NOT_REQUESTED（未请求比较，不构成“无回归”结论）")
    print(f"产物目录：{out_dir}（run.json / traces.jsonl / report.json / report.md）")
    if report["scope"] == "subset":
        print("注意：本次为 subset 运行，不能替代全量验收。")

    if baseline_comparison is not None and baseline_comparison["status"] == "NOT_COMPARABLE":
        return 2
    if baseline_comparison is not None and baseline_comparison.get("new_regressions"):
        return 1
    return classify_exit_code(report)


def main(argv=None) -> int:
    try:
        return _main(argv)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"[配置/数据/基础设施错误] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.mode == "llm":
        print("[配置错误] mode=llm 属于 P1，本轮未实现；不做静默 fallback。", file=sys.stderr)
        return 2
    if args.repeat != 1:
        print("[配置错误] 当前 Release 仅支持 --repeat 1；多 trial 未实现。", file=sys.stderr)
        return 2

    try:
        cases = load_cases(args.dataset)
    except (OSError, ValueError, KeyError) as exc:
        print(f"[数据错误] 无法加载数据集：{exc}", file=sys.stderr)
        return 2

    # ---- 重放：不执行 Agent/工具 ----
    if args.replay:
        report, stop = replay_eval(args.replay, args.dataset, args.out)
        if stop is not None:
            print(f"[重放停止] {stop}：mismatched={report['mismatched_cases']} "
                  f"corrupt_lines={report['corrupt_lines']}；不猜测旧标准答案。", file=sys.stderr)
            return 2
        print(f"replay run_id={report['run_id']}  cases={report['cases']}  "
              f"match={report['judgment_match']} mismatch={report['judgment_mismatch']} "
              f"error={report['error']}")
        for r in report["results"]:
            if r["status"] != "MATCH":
                print(f"  {r['case_id']} {r['status']} {r.get('detail', r.get('message'))}")
        if report["error"] > 0 or report.get("run_errors"):
            print(f"[重放错误] ERROR={report['error']} {report.get('run_errors', [])}", file=sys.stderr)
            return 2
        return 1 if report["judgment_mismatch"] > 0 or report["fail"] > 0 else 0

    # ---- 三次执行确定性验证 ----
    if args.check_determinism is not None:
        if args.check_determinism < 2:
            print("[配置错误] --check-determinism 需要 N>=2。", file=sys.stderr)
            return 2
        result = check_determinism(cases, args.fixtures, args.dataset,
                                   repeats=args.check_determinism)
        import json
        out = create_run_directory(args.out, new_run_id("determinism"))
        (out / "report.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"determinism repeats={result['repeats']} identical={result['identical']} "
              f"runs={[(r['pass'], r['fail'], r['error']) for r in result['runs']]}")
        if result["first_difference"]:
            print(f"  first_difference={result['first_difference']}")
        print(f"  产物：{out / 'report.json'}")
        return result["exit_code"]

    # ---- 常规运行（可带 baseline）----
    if args.case:
        known = {c["case_id"] for c in cases}
        missing = [cid for cid in args.case if cid not in known]
        if missing:
            print(f"[配置错误] 数据集中不存在 Case: {missing}", file=sys.stderr)
            return 2
        selected = [c for c in cases if c["case_id"] in set(args.case)]
        scope = "subset"
    else:
        selected = cases
        scope = "full"

    config = {"mode": args.mode, "repeat": args.repeat}
    return _run_normal(args, cases, selected, scope, config)


if __name__ == "__main__":
    sys.exit(main())
