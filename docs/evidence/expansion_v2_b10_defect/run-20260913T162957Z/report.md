# OrderTrace Eval Report — run-20260913T162957Z

- mode/scope: `offline` / `full`（合成数据，Mock 参考实现，非模型准确率）
- planned/distinct/trials: 430 / 430 / 430
- PASS/FAIL/ERROR: **430 / 0 / 0**，Score = 100.0
- agent=mock-0.2 evaluator=0.1 commit=f562d55cabc6e676e21d875ed3502a381979aadc dirty=True
- dataset_hash=f98a4a6fb154… fixtures_hash=None（v2 内嵌世界，可比性由 dataset_hash 承担）

## 六维结果（PASS/(PASS+FAIL)，N/A 不计成功）

| 维度 | PASS | FAIL | N/A |
| --- | --- | --- | --- |
| task_success | 430 | 0 | 0 |
| tool_selection | 430 | 0 | 0 |
| tool_argument | 379 | 0 | 51 |
| groundedness | 430 | 0 | 0 |
| output_format | 430 | 0 | 0 |
| constraint_following | 430 | 0 | 0 |

## Category 汇总

| 类别 | pass | fail | error |
| --- | --- | --- | --- |
| Normal | 45 | 0 | 0 |
| Boundary | 40 | 0 | 0 |
| Abnormal | 30 | 0 | 0 |
| ToolError | 30 | 0 | 0 |
| ArgumentError | 30 | 0 | 0 |
| Timeout | 30 | 0 | 0 |
| DirtyData | 35 | 0 | 0 |
| Hallucination | 40 | 0 | 0 |
| InstructionConflict | 30 | 0 | 0 |
| PromptInjection | 35 | 0 | 0 |
| AgentLoop | 25 | 0 | 0 |
| Retry | 30 | 0 | 0 |
| Fallback | 30 | 0 | 0 |

## 工具统计（注入故障与参数拒绝分开）

| 工具 | attempts | argument_rejected | backend_faults(注入) | invalid_results |
| --- | --- | --- | --- | --- |
| get_order | 421 | 0 | 80 | 13 |
| get_shipment | 181 | 0 | 50 | 5 |

## 失败/错误 Case

无。

## Baseline 比较

未比较（本轮未请求 baseline）。

## 说明
- 合成数据（synthetic），来源为本项目业务合同，无真实客户/订单。
- offline 模式为确定性 MockAgent + 本地 FixtureTools，证明评测基础设施，不是语言模型能力基准。
- 工具后端故障为规格注入的测试条件，与 Agent 工具选择错误分开统计。
- 70 条依赖会话上下文（多轮/记忆）的 case 已跳过：当前 MockAgent 无会话状态（AGENT_NO_SESSION_STATE）；score 分母为可执行数。
