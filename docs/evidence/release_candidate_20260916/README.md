# Release Candidate evidence · 2026-09-16

Verified source commit: `23be999d02dc74bb5e205ea58eabee78a22db46b`.
Windows / PowerShell, Python 3.13.14; fresh local clone and fresh venv.

- [gate_summary.json](gate_summary.json): commands, exit codes, timings, 154 passing tests and scoped publication checks.
- [n02/report.md](n02/report.md): one complete demonstration run, alongside its original `run.json`, `traces.jsonl` and `report.json`.
- `default_report.json`: 28 PASS, 0 FAIL, 0 ERROR.
- `expansion_report.json`: 430 PASS, 70 skipped out of 500; no session/memory implementation.
- `replay_report.json`: 28 matching judgments.
- `baseline_report.json`: comparable, no case or dimension regressions.
- `determinism_report.json`: three independent successful runs, identical normalized results.

The initial final-diff check failed because the existing QA command reordered warnings in its generated summary. All other fields and the set of warnings were verified identical. The generated output was retained locally, that one file restored from the verified commit, and the final history/clean-state checks passed. The failed command remains in the record.

Source paths in the command record use portable placeholders. No production code or README changed after the verified commit; subsequent evidence/log commits only archive these results. These are local technical release checks, not a public URL, contest eligibility approval, or proof of real model accuracy.
