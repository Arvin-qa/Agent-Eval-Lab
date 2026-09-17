# P0 实施计划（本轮：最小闭环）

制定日期：2026-09-10。依据：PROJECT_SPEC.md §13 P0 定义、ACCEPTANCE_CRITERIA.md §2 矩阵、IMPLEMENTATION_TASKS.md Week 1–3。
本轮边界由执行指令确定：**只做 P0 最小闭环，完成即停**。不进 P1/P2，不做 Web/云/框架。

## 0. 规格冲突检查

四份规格交叉核对，未发现阻断性冲突，不创建 ISSUES.md。已核对的疑点：

| 位置 | 差异 | 处理 |
| --- | --- | --- |
| PROJECT_SPEC §5.3 C01 vs IMPLEMENTATION_TASKS W2.1 | C01 的 delivered_at 前者只要求“非空”，后者固定 `2026-09-09T12:00:00Z` | 细化而非冲突（两者可同时满足）；C01 不在本轮范围，W2.1 展开时按固定值执行 |
| 执行指令 vs PROJECT_SPEC §13 | 指令要求本轮只做“P0 最小闭环”，规格 P0 含 28 Case | 按指令优先级执行：本轮 6 条种子 Case，28 条列为剩余 P0（规格 §5.3 本身规定“先做 N01/N02/I02/T02/M01/H02 六条贯通，再扩展”） |

## 1. P0 全量清单与本轮状态

| # | P0 项（来源：PROJECT_SPEC §13 / AC 矩阵） | 本轮动作 | 本轮状态 |
| --- | --- | --- | --- |
| P0-1 | 两个工具 + 受控执行器（allowlist、参数校验、TIMEOUT 重试一次、故障注入、尝试预算、前置条件） | 完整实现（order_eval/tools.py） | DONE |
| P0-2 | MockAgent（只收 user_input + tool_executor，不读 expected） | 完整实现（order_eval/agent.py），覆盖六条种子路径所需意图 | DONE |
| P0-3 | Eval Dataset 28 条 | 本轮冻结前 6 条种子（N01/N02/I02/T02/M01/H02），schema 按最终 28 条标准 | PARTIAL（6/28） |
| P0-4 | 六维 Rule-based Evaluator | 完整实现六个维度 + N/A 规则（order_eval/evaluator.py） | DONE |
| P0-5 | 评测器好坏反例 ≥12 个静态标注 Trace | 实现 E01–E12 + 合法变体防误杀测试（test_evaluator.py） | DONE |
| P0-6 | 结构化 Trace（§8 最小字段） | 完整实现（runner 组装，每次 trial 独立工具世界） | DONE |
| P0-7 | pytest 四类测试（tools/scenarios/evaluator/regression），默认不跑 LLM | 实现，llm marker 默认排除 + 网络拦截 | DONE |
| P0-8 | 离线回归：同版本三次执行结构化一致；`--replay`；`--baseline` 比较 | 本轮实现重复执行一致性测试与退出码/分母测试；`--replay`、`--baseline` CLI 延后 | PARTIAL |
| P0-9 | JSON/Markdown 报告（同源渲染）+ 退出码 0/1/2 | 完整实现（run.json + report.md 同源） | DONE |
| P0-10 | 一份真实故障修复证据（BUGFIX_LOG） | 本轮建立 BUGFIX_LOG.md 并记录真实实施问题；受控缺陷实验闭环属后续轮次 | PARTIAL |
| P0-11 | README（安装、离线一条命令、范围与限制） | 最小可用版（AC01/AC20 要求项） | DONE |

本轮收尾时 P0 总体状态预期为 PARTIAL（28 Case、replay/baseline、修复闭环三项未完）。

## 2. 本轮模块顺序（TDD：每模块先测试后实现，逐个实际运行验证）

| 步骤 | 模块 | 先写的测试 | 验证命令 |
| --- | --- | --- | --- |
| S1 | 骨架：requirements.txt、pytest.ini、.gitignore、包结构、git init | - | `python -m pytest --collect-only` |
| S2 | order_eval/schemas.py：输入合同（strip 后 1–500、ORD-\d{4} 完整匹配、大小写归一、意图分类）、ToolResult envelope、AgentOutput JSON Schema、Case Schema | test_tools.py 中输入边界参数化（500/501、ord-1001、ORD-12X4、ORD-10010、空串） | `python -m pytest tests/test_tools.py -k input` |
| S3 | order_eval/tools.py + datasets/fixtures.json：FixtureTools、执行器（校验/重试/预算/前置/故障注入） | test_tools.py 合同用例（正常/错工具/缺参/错类型/多余参数/超时×1/超时×2/TOOL_ERROR/空记录/预算第 5 次） | `python -m pytest tests/test_tools.py` |
| S4 | order_eval/agent.py + datasets/cases.jsonl（6 条）：MockAgent | test_scenarios.py：六条端到端 + AC07 防泄漏控制试验 | `python -m pytest tests/test_scenarios.py` |
| S5 | order_eval/evaluator.py：六维判定 + N/A 规则 | test_evaluator.py：E01–E12 + 变体（key 重排、额外有据事实、缺必需事实、未发货正例、冲突组件正例） | `python -m pytest tests/test_evaluator.py` |
| S6 | order_eval/runner.py + run_eval.py：trial 隔离、Trace 落盘、报告、退出码 | test_regression.py：分母验算（25/2/1→89.29）、重复执行一致性、退出码映射 | `python -m pytest tests/test_regression.py` |
| S7 | 全量验证 | tests/conftest.py 网络拦截 | `python -m pytest`；`python run_eval.py --mode offline`；`python run_eval.py --mode offline --case N02` |

## 3. 关键实现决策（局部细节，不改变规格合同）

1. **意图识别为最小关键词规则**（规格 §3.1.7 允许）：write 关键词 > 物流 > 金额 > 状态 > unknown→UNSUPPORTED_QUERY。规则与边界写入代码常量，公开可见。
2. **订单号识别**：宽松 token `ORD-[A-Za-z0-9]+`（词边界）存在而严格 token `ORD-\d{4}`（前后非数字/字母/连字符）不存在 → INVALID_INPUT，绝不截断。
3. **故障注入**：fixtures.json 按 case 声明故障序列（如 T02: `["timeout","timeout"]`），每次 trial 深复制工具世界并重置计数；超时用注入异常模拟，不真实睡眠。
4. **call_id 离线确定性**（`call-1`、`call-2`…），重复执行一致性对比时仍按规格剥离 run_id/时间戳/耗时等易变字段。
5. **冲突检测**：共享纯函数 `detect_conflicts(order_data, shipment_data)`（§3.2 三规则），Agent 与 Evaluator 共用 schema 级定义，但 Evaluator 不调用 Agent 决策函数。
6. **reason_code 的证据校验**本轮只覆盖“事实必须有合法 evidence”（§4 核心句）；指向 `/error/code` 的原因证据校验列入后续轮次。
7. **git**：本地仓库，按模块里程碑提交；Trace 记录 commit 与 dirty 标记。

## 4. 本轮明确不做

28 条剩余 22 条、`--replay`、`--baseline` CLI 比较链、受控缺陷修复闭环实验、P1 LLM、CSV、README 美化、INTERVIEW_STORY.md 修改。
