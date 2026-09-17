# Agent Eval Lab — Project Map and Constraints

## Product Boundary

Agent Eval Lab is a local, offline evaluation lab for an order-query Agent.
It evaluates tool selection, tool arguments, task result, evidence grounding,
output format, and constraint following.

The current release uses a rule-based `MockAgent`, two local read-only order
tools, JSON / JSONL cases and traces, six deterministic evaluation dimensions,
replay, baseline comparison, determinism checking, and local Markdown / JSON reports.

Keep the release narrow. The following expansions require an explicit user task:

- RAG, MCP, multi-agent orchestration, memory or multi-turn state;
- databases, web UI, authentication, cloud deployment, Docker;
- LLM Judge, runtime Astra integration, model routing;
- leaderboards, cost dashboards, new datasets, general-purpose plugin systems.

Public claims must stay within verified product capabilities. Do not present the
current release as a universal evaluator, production Agent runtime, model benchmark,
multi-agent system, LLM Judge system, or Astra-powered runtime. Do not advertise
100% model accuracy, production performance, universal hallucination detection,
arbitrary Agent compatibility, or implemented memory / multi-turn behavior without
implementation and verification supporting those claims.

## Project Map

| Task / question | Entry points |
| --- | --- |
| Quick Start, demos, limitations, public material | `README.md` |
| Audited capabilities and architecture boundaries | `CURRENT_STATE.md` |
| Historical release decisions | `RELEASE_GAPS.md`; old P0 gaps may already be fixed, so check current code / Git history before treating them as open |
| Astra contribution, Challenge material, release evidence | `ASTRA_BUILD_LOG.md` and relevant files under `docs/evidence/` |
| Evaluator behavior | `order_eval/evaluator.py`, `tests/test_evaluator.py`, `order_eval/schemas.py` |
| Runner / CLI behavior | `run_eval.py`, `order_eval/runner.py`, relevant runner / CLI tests under `tests/` |
| Release verification | README commands, relevant build log / evidence entries, current Git state |

## Evaluation Integrity and CLI Contract

Evaluation credibility takes priority over producing a PASS:

- Do not weaken assertions, delete failing cases to improve results, or change
  expected answers to hide regressions.
- Malformed or inconsistent traces / outputs must produce explicit non-success;
  do not silently ignore them or convert infrastructure errors into success.
- Preserve the distinction between Agent/task failure, evaluation failure,
  malformed trace/output, and configuration/infrastructure failure.

Preserve the existing exit semantics:

- Completed successful evaluation → success exit.
- Evaluated business FAIL / ERROR → evaluation failure exit.
- Invalid configuration/input, unsupported CLI usage, or infrastructure failure
  → configuration/infrastructure exit.

Zero effective evaluations must not look successful. Missing files must not end
only in a raw traceback; unwritable output paths must not masquerade as evaluation results.

## Historical Evidence and Trial Boundary

Stored T01 FAIL / FIXED evidence is historical: do not rewrite it, regenerate and
replace it, or alter it to match a newer evaluator. If evaluator behavior changes,
check compatibility explicitly while preserving the originals. Do not attribute
the original T01 fix to Astra or squash history to conceal its provenance.

The public release supports a single evaluation trial. `--repeat > 1` is
intentionally rejected; do not silently re-enable or partially implement it.
`--check-determinism` is separate from multi-trial evaluation. Full multi-trial
support requires an explicit future task.

## Artifact Safety

Preserve unique run directories and exclusive output creation: evaluation output
must not silently overwrite existing evidence. Changes to artifact generation
must verify rapid sequential runs, concurrent runs, replay output, and determinism
output, with existing run evidence left intact.

## Verification Entry Points

Full suite for changes to evaluator behavior, runner behavior, CLI exit semantics,
report generation, trace schema, or baseline / replay logic:

```bash
python -X utf8 -m pytest -q
```

For release-sensitive changes, exercise the affected flows using current README
commands. Representative scenarios: normal order query, shipment query, timeout
degradation, replay, baseline comparison, determinism, and malformed input / traces.
Default offline smoke test:

```bash
python -X utf8 run_eval.py --mode offline
```

Test counts, case counts, and evaluation results in public documentation must come
from actual executed results for the relevant checkout, not historical RC counts.

## Astra Attribution and Public Material

Astra is a development and release-hardening agent; the product does not currently
call Astra at runtime. Do not retroactively attribute earlier work to Astra.
Record actual Astra contributions in `ASTRA_BUILD_LOG.md` with date, task, files
changed, verification, actual result, and commit hash when committed. Planned work
must not be recorded as completed work.

Public material must use repository-relative paths and omit private Codex session
metadata, task UUIDs, machine usernames / local temporary paths, and real customer data.
