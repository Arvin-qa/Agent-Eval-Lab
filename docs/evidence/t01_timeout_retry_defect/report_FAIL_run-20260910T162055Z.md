# OrderTrace Eval Report — run-20260910T162055Z

- mode/scope: `offline` / `full`（合成数据，Mock 参考实现，非模型准确率）
- planned/distinct/trials: 28 / 28 / 28
- PASS/FAIL/ERROR: **27 / 1 / 0**，Score = 96.43
- agent=mock-0.1 evaluator=0.1 commit=54df40cfb61a939f5b91ea0da3c9d065ef545304 dirty=True
- dataset_hash=55fef1641073… fixtures_hash=a84544184c16…

## 六维结果（PASS/(PASS+FAIL)，N/A 不计成功）

| 维度 | PASS | FAIL | N/A |
| --- | --- | --- | --- |
| task_success | 27 | 1 | 0 |
| tool_selection | 28 | 0 | 0 |
| tool_argument | 23 | 0 | 5 |
| groundedness | 28 | 0 | 0 |
| output_format | 28 | 0 | 0 |
| constraint_following | 28 | 0 | 0 |

## Category 汇总

| 类别 | pass | fail | error |
| --- | --- | --- | --- |
| Normal | 4 | 0 | 0 |
| Boundary | 4 | 0 | 0 |
| Invalid Input | 4 | 0 | 0 |
| Tool Failure | 3 | 1 | 0 |
| Missing Data | 4 | 0 | 0 |
| Conflicting Data | 4 | 0 | 0 |
| Hallucination Trap | 4 | 0 | 0 |

## 工具统计（注入故障与参数拒绝分开）

| 工具 | attempts | argument_rejected | backend_faults(注入) | invalid_results |
| --- | --- | --- | --- | --- |
| get_order | 25 | 0 | 3 | 2 |
| get_shipment | 10 | 0 | 1 | 0 |

## 失败/错误 Case

- `T01` [FAIL] input='查 ORD-1001 订单状态' 维度=['task_success'] 原因=['task_success/TS-STATUS', 'task_success/TS-REASONS', 'task_success/TS-FACTS']

## Baseline 比较

未比较（本轮未请求 baseline）。

## 说明
- 合成数据（synthetic），来源为本项目业务合同，无真实客户/订单。
- offline 模式为确定性 MockAgent + 本地 FixtureTools，证明评测基础设施，不是语言模型能力基准。
- 工具后端故障为规格注入的测试条件，与 Agent 工具选择错误分开统计。
