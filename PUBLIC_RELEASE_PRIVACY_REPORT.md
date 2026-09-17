# PUBLIC RELEASE PRIVACY REPORT

## 2026-09-17 public-copy addendum

The historical audit below concerns the original private development repository. Its full-history publication blocker remains valid for that repository. This public copy was exported from sanitized current content, with no original `.git`, and a new empty Git repository was initialized only after verification. Before staging, it had zero objects, no HEAD and no remotes. Old development commit hashes are provenance text only, not public history.

Public payload: 68 exported files plus the approved AGENTS.md. All 30 PUBLIC evidence files remain intact, including byte-identical T01 originals. Original LOCAL ONLY content was not copied. A fresh local virtual environment, caches, verification scripts and outputs were subsequently generated solely for testing and remain ignored, outside the public payload. Do not upload a whole working-directory ZIP.

Repeated scan found no actual credential signature, private UUID, email, IP or known machine/user identity in public file contents. Three AGENTS.md home-path examples are generic placeholders. Four phone-pattern occurrences are the previously reviewed synthetic generator/case input, not evidence of imported customer data. No claim is made that the number is reserved. Checks are bounded pattern and source reviews.

Fresh verification in this copy: 154 pytest tests passed in 56.85s; default 28 PASS; N02/T02 2 PASS; historical T01 FAIL/FIXED re-evaluation FAIL/PASS; Demo 28 PASS; replay 28 MATCH, no mismatches/errors; baseline no regression; three deterministic runs identical, each 28 PASS. Installation and pip check succeeded.

**BLOCKED BEFORE PUBLIC ROOT COMMIT**: the inherited Git commit identity includes a personal email whose publication has not been approved. It was neither changed nor committed. No public root commit, remote, push, license change or external publication was performed. This identity decision is separate from the original-history blocker, which this independent snapshot avoids.

## Public snapshot provenance

This public copy starts a new Git history from a sanitized Release Candidate. The original development history remains in the local private repository. All pre-snapshot commit hashes in these documents and technical evidence refer to private development records; they cannot be resolved in the new public repository. Historical evidence, including T01 FAIL/FIXED, is retained unchanged.


Date: 2026-09-17. Audit source: `225364857b746c25e9d42c838ec0e56bafe003c0`.

## Scope and method

- Initial tracked tree: **67 text files**; includes all product code, tests, data, configuration, Markdown and **30 evidence files**. This report adds one documentation file.
- Static search: `git grep -l -i -E` over credential, path, session and identity terms; `rg --files --hidden --no-ignore` for environment/key/certificate/dump/credential filenames.
- Independent standard-library scan: enumerate `git ls-files -z`, inspect every tracked text file, record category and line number without copying private values into this report.
- History check: `git rev-list --objects --all` and `git cat-file` inspected **118 unique file blobs reachable from 20 commits** at audit start. This is content scanning; commit author identities were inspected separately and not rewritten.
- Inspect untracked and ignored paths using `git ls-files --others --exclude-standard` and `git status --short --ignored`. No publish-eligible untracked file existed at audit start.
- No scanner installation or runtime dependency change. Pattern scanning and source review are bounded checks, not proof against every possible secret format or arbitrary real-world identity.

## Patterns and reviewed findings

| Category / searched patterns | Initial findings | Review |
| --- | --- | --- |
| `sk-`, API_KEY, TOKEN, SECRET, PASSWORD, Bearer, Authorization, Cookie, refresh/session token; private-key headers, provider token formats, JWT | 45 credential-keyword lines; 0 credential-value signature hits | Variable names, planned configuration names, order-ID token parsing, null token usage counters, and descriptions of key-free operation. No actual key, password, authentication token or cookie identified. |
| Drive paths, user home paths, UNC-like paths; Desktop, AppData, Temp/tmp, .codex | 58 broad path-pattern lines | Public HTTPS URLs and JSON-escaped relative/placeholder paths, not actual user absolute paths. No Windows account/home path identified in tracked contents. |
| Internal session/task fields and UUID format | 8 keyword lines, 2 UUID occurrences | One private task identifier repeated in Build Log and audit JSON; associated internal fields are unnecessary for public provenance. A determinism test function name is a regex false positive, not a turn identifier. |
| Email, IP, phone, known local account/author strings | 4 phone-format lines; no body email/IP/account match | One synthetic phone-format literal appears in two generator strings and two generated cases. It is hard-coded test input, not imported customer data; no real-person association found. Retained to avoid changing dataset behavior. No claim that the number is a reserved/unassigned telephone number. |
| Environment fingerprint | Exact OS build, Python compiler/build details, dependency mirror provider | Generalized/removed; Windows family, Python/package versions and reproducibility results retained. |
| Local-only files | Ignored artifacts, caches and a venv CA certificate bundle | CA bundle is third-party public trust material, not a private key. None is tracked or should be included in the public repository. |

The private identifier value and private email are deliberately not reproduced here.

## Minimal changes and reasons

| File | Change / reason |
| --- | --- |
| `ASTRA_BUILD_LOG.md` | Remove private task UUID, internal session field paths and precise private-session timestamps; retain dates, Astra contribution, files, tests and commit hashes. Remove mirror provider detail. |
| `docs/evidence/release_audit_20260916.json` | Replace private provenance fields with neutral model-participation verification; generalize OS/Python environment fingerprint. Mark the shortened runtime stdout as publicly redacted rather than presenting it as untouched output. Keep all test results and commands. |
| `CURRENT_STATE.md` | Remove OS build fingerprint and local dependency mirror provider; retain compatibility-relevant versions and installation result. |
| `docs/evidence/release_candidate_20260916/gate_summary.json` | Remove machine-specific dependency-index provider description; retain all gate outcomes, commands, failures and commit identity. |
| `.gitignore` | Ignore local environment/credential files, private key containers, local IDE/Codex configuration and crash dumps; keep example environment files eligible. Existing artifacts/cache/venv exclusions remain. This cannot remove already committed history. |
| `PUBLIC_RELEASE_PRIVACY_REPORT.md` | Record scope, real findings, false positives, evidence classification, regression verification and the remaining history blocker without repeating private values. |

No product logic, Agent behavior, evaluator/runner code, test semantics, dependencies, datasets, license or historical T01 evidence changed. Nothing required to reproduce technical behavior was deleted. No complete evidence JSON was discarded.

## Evidence classification

PUBLIC below refers to the **sanitized current file**, not every historical version. All 30 tracked evidence files retain public technical value:

| File under `docs/evidence/` | Classification | Why |
| --- | --- | --- |
| `ac02_network_intercept.md` | PUBLIC | Offline network-interception evidence |
| `determinism_3x_FINAL_GATE.json` | PUBLIC | Historical determinism result |
| `expansion_v2_b10_defect/README.md` | PUBLIC | Historical defect explanation |
| `expansion_v2_b10_defect/run-20260913T162730Z/report.json` | PUBLIC | Historical failure result |
| `expansion_v2_b10_defect/run-20260913T162730Z/report.md` | PUBLIC | Readable failure report |
| `expansion_v2_b10_defect/run-20260913T162730Z/run.json` | PUBLIC | Run identity |
| `expansion_v2_b10_defect/run-20260913T162957Z/report.json` | PUBLIC | Historical fixed result |
| `expansion_v2_b10_defect/run-20260913T162957Z/report.md` | PUBLIC | Readable fixed report |
| `expansion_v2_b10_defect/run-20260913T162957Z/run.json` | PUBLIC | Run identity |
| `release_audit_20260916.json` | PUBLIC, sanitized | Phase 1 tests and gap reproductions; private provenance removed |
| `release_candidate_20260916/README.md` | PUBLIC | Gate evidence interpretation |
| `release_candidate_20260916/baseline_report.json` | PUBLIC | Regression comparison |
| `release_candidate_20260916/default_report.json` | PUBLIC | 28-case result |
| `release_candidate_20260916/determinism_report.json` | PUBLIC | Three-run determinism |
| `release_candidate_20260916/expansion_report.json` | PUBLIC | 430 executed / 70 skipped |
| `release_candidate_20260916/gate_summary.json` | PUBLIC, sanitized | Gate commands and outcomes |
| `release_candidate_20260916/n02/report.json` | PUBLIC | Demonstration result |
| `release_candidate_20260916/n02/report.md` | PUBLIC | Readable demonstration |
| `release_candidate_20260916/n02/run.json` | PUBLIC | Demonstration run identity |
| `release_candidate_20260916/n02/traces.jsonl` | PUBLIC | Full synthetic task/tool/output evidence |
| `release_candidate_20260916/replay_report.json` | PUBLIC | Replay judgments |
| `release_hardening_baseline_20260916.json` | PUBLIC | Pre-change test baseline |
| `replay_FINAL_GATE.json` | PUBLIC | Historical replay result |
| `report_FINAL_GATE_run-20260910T163653Z.json` | PUBLIC | Historical full-suite result |
| `t01_timeout_retry_defect/report_FAIL_run-20260910T162055Z.json` | PUBLIC, unchanged | Original failure evidence |
| `t01_timeout_retry_defect/report_FAIL_run-20260910T162055Z.md` | PUBLIC, unchanged | Original readable failure |
| `t01_timeout_retry_defect/report_FIXED_run-20260910T162250Z.json` | PUBLIC, unchanged | Original fixed evidence |
| `t01_timeout_retry_defect/report_FIXED_run-20260910T162250Z.md` | PUBLIC, unchanged | Original readable fixed result |
| `t01_timeout_retry_defect/trace_FAIL_T01.json` | PUBLIC, unchanged | Original failed Trace |
| `t01_timeout_retry_defect/trace_FIXED_T01.json` | PUBLIC, unchanged | Original fixed Trace |

LOCAL ONLY: all ignored `artifacts/` contents (temporary audit scripts/logs, raw metadata probes, prior unsanitized clones and their venvs), pytest/Python caches, and private Codex task records outside the repository. Retain locally; do not upload a whole working-directory ZIP or use force-add. No tracked evidence file requires wholesale removal.

## Current tree versus Git history

- Sanitized current tree: no actual credential, private task/session identifier, user absolute path or personal identity identified in file contents within the stated scan scope. Synthetic phone-format input is explicitly disclosed above.
- **History blocker:** commit `c8cb348` introduced private Codex task identity in `ASTRA_BUILD_LOG.md` and `docs/evidence/release_audit_20260916.json`. Subsequent ancestors retain it, including `2253648`. A new sanitization commit does not erase those blobs. Pushing this branch with its ancestry would publish them.
- The existing Git author/committer metadata contains one non-noreply personal email identity. It was not copied into file bodies or rewritten, as explicitly excluded from mandatory history rewriting by the user. It remains visible if original history is published and requires an informed publication choice; it is not treated as an additional mandatory blocker in this audit.
- No history rewriting, orphan branch, public repository, remote configuration, push, license change or external upload was performed. Removing the history blocker requires a separately approved publication strategy, such as a sanitized public snapshot with private history retained locally, or carefully scoped history sanitation. This audit does not execute either option.

## Regression verification

- Post-redaction verification enumerated **68 tracked files**, including this report. No private identifier value, credential signature, body email or user absolute path remained in the current tree in the stated checks. All 30 evidence files are explicitly classified above.
- `python -X utf8 -m pytest -q`: **154 passed in 64.56s (0:01:04)**, exit 0. Test count unchanged.
- `python -X utf8 run_eval.py --mode offline --out artifacts/privacy_audit/default`: **28 PASS / 0 FAIL / 0 ERROR**, score 100.0, exit 0.
- JSON semantic comparison against audit source verified that all original audit/gate commands, timings, exit codes and evaluation results are unchanged, excluding only the explicitly identified environment/provenance redactions.
- `git diff 2253648 -- order_eval run_eval.py tests datasets requirements.txt README.md docs/evidence/t01_timeout_retry_defect`: empty.
- `git check-ignore --no-index` confirmed new local-secret/IDE/dump exclusions while `.env.example` and `.env.template` remain eligible. No real credential files were added to test the rules.
- `git diff --cached --check`: passed. The dedicated privacy commit is named `chore: sanitize public release metadata`; its hash and post-commit worktree status are reported in the handoff, not fabricated as a self-referential hash inside this file.

## Conclusion

**BLOCKED FOR PUBLIC GITHUB**

Exact blocker: reachable Git history still contains the private Codex task identifier. Current-file sanitation is complete but is not sufficient for a full-history push. The technical Release Gate remains a separate result and does not override this privacy decision.
