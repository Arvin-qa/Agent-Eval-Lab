# OrderTrace Eval · Agent Eval Lab

## Public snapshot provenance

This public copy starts a new Git history from a sanitized Release Candidate. The original development history remains in the local private repository. All pre-snapshot commit hashes in these documents and technical evidence refer to private development records; they cannot be resolved in the new public repository. Historical evidence, including T01 FAIL/FIXED, is retained unchanged.


**用工具调用记录验证订单查询 Agent：查了什么、参数是否正确、答案有没有证据，以及失败时是否按合同降级。**

输入合成订单任务 → 规则 MockAgent 调用本地工具 → 保存 JSON/JSONL Trace → 六维规则评测 → PASS / FAIL / ERROR 与具体原因。

这是面向 Agent 开发者的本地 Evaluation Lab。当前完全 offline，不需要 API Key；安装后无需联网。默认 28 个场景，也能重评保存的 Trace、比较历史运行并检查确定性。**Mock 28/28 表示参考实现通过这些合同场景，不是模型准确率 100%。**

## Problem

最终答案看起来正确，不代表 Agent 完成了可靠的任务：它可能查错订单、凭空给出金额、引用不存在的工具调用，或在工具恢复后仍错误地降级。

普通 API test 常检查单个接口的请求与响应；这里检查一次任务的工具调用过程、最终结构化输出和证据之间的关系。pytest 用来测试这套评测代码，两者互补。规则和样本都可阅读，FAIL 可以追到具体 check，而不是只得到一个总分。

## What it does

- 两个只读工具：`get_order` 查询订单，`get_shipment` 查询物流；使用合成快照和可控故障。
- 一个确定性规则 `MockAgent`，每个 case 使用隔离的工具世界。
- 六维规则检查；验证原始输出可解析，raw 与 parsed 语义一致，评分依赖的 Trace 字段完整。
- 保存 `run.json`、`traces.jsonl`、`report.json`、`report.md`；Markdown 由同一 report 对象生成。
- replay 重新评分，不重新运行 Agent/工具；baseline 比较 case 与维度退化；determinism 实际运行 N 次并比较结构化内容。
- 每次运行使用唯一目录，已有目录不会被覆盖。Release 只支持每个 case 一个 trial。

## Architecture

```text
cases.jsonl + fixtures.json（或 v2 内嵌 tool_state）
    ├─ 用户输入 → MockAgent → Executor → get_order / get_shipment
    │                              └─ 调用、结果、错误 → Trace
    └─ 期望合同 ────────────────────────────────────┐
                                                  ↓
                             Trace → Evaluator 0.2 → report.json → report.md
```

期望答案用于评测，不传给 Agent。入口为 `run_eval.py`；合同、工具、Agent、评测和产物逻辑位于 `order_eval/`。无服务端启动步骤。

## Quick Start

验证环境：Windows / PowerShell、Python 3.13.14、Git。依赖固定在 [requirements.txt](requirements.txt)。其他 Python/操作系统组合未在本次发布门禁验证。

**打开 PowerShell，克隆公开仓库并安装依赖：**

```powershell
git clone https://github.com/Arvin-qa/Agent-Eval-Lab.git
cd Agent-Eval-Lab
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -X utf8 run_eval.py --mode offline
```

后续命令均从克隆后的仓库根目录运行。不需要激活脚本、不修改系统编码或环境变量。依赖下载需要网络；评测无需网络。`-X utf8` 只对当前 Python 进程生效，用于避免 Windows 中文/符号输出编码问题。

命令会打印本次产物目录。打开其中的 `report.md` 看汇总，`traces.jsonl` 看输入、调用、输出、每维 checks 和 `failure_reasons`；`run.json` 保存配置及版本/数据散列。

## Demo · 约 4 分钟

前提：已完成安装；下载依赖时间不计入演示。

1. **0:00–0:30**：展示 N02 输入“查 ORD-1002 物流状态和预计到货时间”。
2. **0:30–1:30**：运行下面的 N02/T02 命令并打开刚生成的报告与 Trace。N02 先查订单再查物流，答案的 ETA 引用实际工具返回值；T02 两次超时后正确返回 unavailable，仍是 PASS。
3. **1:30–2:30**：重评历史 T01 的 FAIL/FIXED 记录，展示 `TS-STATUS` 失败原因和修复后的 PASS。这是历史缺陷证据，不是本次重新制造或修复的缺陷。
4. **2:30–4:00**：跑默认 28 条，再 replay 保存的 Trace，展示 MATCH 与六维结果。说明 Mock 和合成数据的边界。

```powershell
.\.venv\Scripts\python.exe -X utf8 run_eval.py --case N02 --case T02 --out artifacts/demo-scenes
.\.venv\Scripts\python.exe -X utf8 -c "import json; from pathlib import Path; from order_eval.schemas import load_cases; from order_eval.evaluator import evaluate; c=next(c for c in load_cases('datasets/cases.jsonl') if c['case_id']=='T01'); print(json.dumps([{'trace':p.name, 'evaluation':evaluate(c,json.loads(p.read_text(encoding='utf-8')))} for p in sorted(Path('docs/evidence/t01_timeout_retry_defect').glob('trace_*_T01.json'))],ensure_ascii=False,indent=2))"
.\.venv\Scripts\python.exe -X utf8 run_eval.py --out artifacts/demo-full
```

将最后一条命令打印的目录复制给变量，再运行以下命令；示例占位符不能原样使用：

```powershell
$runDir = 'artifacts/demo-full/<实际run_id>'
.\.venv\Scripts\python.exe -X utf8 run_eval.py --replay "$runDir/traces.jsonl" --out artifacts/demo-replay
.\.venv\Scripts\python.exe -X utf8 run_eval.py --baseline "$runDir" --out artifacts/demo-compare
.\.venv\Scripts\python.exe -X utf8 run_eval.py --check-determinism 3 --out artifacts/demo-determinism
```

baseline 参数接受**完整运行目录**，需有 `run.json`、`report.json`、`traces.jsonl`。数据/Fixture/工具合同/evaluator 版本、模式和 case/trial 方案必须可比；旧 evaluator 0.1 与 0.2 返回 `NOT_COMPARABLE`，不能声称“无回归”。未提供 baseline 时为 `NOT_REQUESTED`。历史 Trace 可单独调用 evaluator 重评，原件不修改。

## Evaluation dimensions

| 维度 | 检查内容 |
| --- | --- |
| `task_success` | 输出状态、原因码、订单号、必需事实是否符合 case 期望 |
| `tool_selection` | 工具是否允许、必需调用、调用次数和物流前置条件 |
| `tool_argument` | 参数是否被 schema 拒绝、订单号是否符合任务 |
| `groundedness` | 每条事实的 call_id、来源工具、JSON Pointer 和值是否有实际依据 |
| `output_format` | raw JSON、parsed 一致性和 AgentOutput 合同 |
| `constraint_following` | 禁止调用、写操作和超额重试等现有约束 |

事实正确但引用不存在时：`task_success=PASS`，`groundedness=FAIL`，整体 FAIL。对应回归见 `tests/test_evaluator.py::TestBadTracesFail::test_e08_task_success_still_passes`。

维度为 PASS / FAIL / N/A；无法评分的维度不计成功。Trace 合同损坏、raw/parsed 不一致、执行中止记整体 ERROR；单纯 Agent 输出格式或业务违反合同记 FAIL。工具超时本身是注入的业务测试条件，按合同正确降级仍可 PASS。

退出码：

- `0`：实际完成有效评测且无失败/错误；请求的比较也通过。
- `1`：业务评测 FAIL（业务 ERROR 同样非成功）、regression 或 replay 判定不一致。重放一个匹配的 FAIL 仍为 1。
- `2`：配置、输入/Trace、基础设施错误、零有效 trial 或 `NOT_COMPARABLE`。当前 evaluator 的 ERROR 均属于这些基础设施/记录完整性问题。

replay 若遇到坏行，会尽可能保存可评记录和错误说明，仍非成功退出；MATCH 只表示判定一致，不能代替业务 PASS。确定性相同也不能把相同失败当成成功。

## Example result

默认套件的实际输出：

```text
planned=28 trials=28 PASS=28 FAIL=0 ERROR=0 score=100.0
```

历史 T01 原件重新评分：

```text
trace_FAIL_T01.json   FAIL   TS-STATUS: expected='answered' actual='unavailable'
trace_FIXED_T01.json  PASS
```

`score = 100 × PASS / 可执行 case 数`，ERROR 保留在分母。扩展集有 500 条、15 个场景类别，实际执行 430 条，70 条因依赖多轮/记忆而跳过，原因为 `AGENT_NO_SESSION_STATE`。跳过不算 PASS；全部跳过 exit 2。场景类别数量不是新增的评测维度。

```powershell
.\.venv\Scripts\python.exe -X utf8 run_eval.py --dataset datasets/expansion/round_001.jsonl --out artifacts/expansion
.\.venv\Scripts\python.exe -X utf8 data_factory/validate_round1.py
```

QA 使用 UTF-8；存在模板共享等 warning，不应宣称数据质量没有任何限制。该 QA 命令会重写生成的 `datasets/expansion/qa_summary.json`。

## Tests

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_release_hardening.py -q
```

本轮加固后全量 **154 passed**，其中新增 **42 项回归**（含参数化）。覆盖 raw/parsed、嵌套 Trace 损坏、零执行、文件错误、T02、replay/确定性失败语义、并发防覆盖、repeat 和 baseline。既有业务断言未降低，历史 T01 证据未改写。pytest 进程中的网络连接由 `tests/conftest.py` 拦截。

## Limitations

- 当前 Agent 是中文关键词规则 MockAgent，只覆盖合同内的订单查询；这不是通用 Agent 平台，也不证明真实语言模型能力。
- 没有 LLM runtime、新模型接入、Astra API runtime 或 LLM Judge。扩展数据中的 `evaluation_rules` 元数据未动态执行；评分仍使用固定六维规则，标有 `llm_judge` 的项目没有运行 Judge。
- 多轮/会话记忆未实现，70 条相关数据仅保留并明确跳过；其他 v2 禁止行为名称不等于新增了专门规则。
- 仅 `--repeat 1`；完整 multi-trial 未实现。`--check-determinism 3` 是三次独立套件执行，不是模型采样统计。
- Trace 校验可以发现合同损坏和不一致，不提供密码学防篡改证明。baseline 需要完整兼容产物，不能用旧报告摘要代替。
- 第一阶段报告及原有规划文档是历史记录；当前可运行能力以本 README、代码和发布门禁证据为准。

## Built with GPT-6 Astra

GPT-6 Astra 通过 Codex 参与本轮发布审查、release hardening、回归测试和发布准备。产品运行时使用本地 MockAgent，不调用 Astra API。

[ASTRA_BUILD_LOG.md](ASTRA_BUILD_LOG.md) 记录实际修改、验证命令、结果和本地 commit。第一阶段以前的项目实现与历史 T01 修复不追溯归功于 Astra，不声称有未发生的 API/token 使用记录。
