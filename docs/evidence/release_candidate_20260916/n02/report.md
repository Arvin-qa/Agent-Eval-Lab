# OrderTrace Eval Report — run-20260916T121637166104Z-82928e9fcdaa485f9875533e663a58f5

- mode/scope: `offline` / `subset`（合成数据，Mock 参考实现，非模型准确率）
- planned/distinct/trials: 1 / 1 / 1
- PASS/FAIL/ERROR: **1 / 0 / 0**，Score = 100.0
- agent=mock-0.2 evaluator=0.2 commit=23be999d02dc74bb5e205ea58eabee78a22db46b dirty=False
- dataset_hash=55fef1641073… fixtures_hash=342fb6fe4d93…

## 六维结果（PASS/(PASS+FAIL)，N/A 不计成功）

| 维度 | PASS | FAIL | N/A |
| --- | --- | --- | --- |
| task_success | 1 | 0 | 0 |
| tool_selection | 1 | 0 | 0 |
| tool_argument | 1 | 0 | 0 |
| groundedness | 1 | 0 | 0 |
| output_format | 1 | 0 | 0 |
| constraint_following | 1 | 0 | 0 |

## Category 汇总

| 类别 | pass | fail | error |
| --- | --- | --- | --- |
| Normal | 1 | 0 | 0 |

## 工具统计（注入故障与参数拒绝分开）

| 工具 | attempts | argument_rejected | backend_faults(注入) | invalid_results |
| --- | --- | --- | --- | --- |
| get_order | 1 | 0 | 0 | 0 |
| get_shipment | 1 | 0 | 0 | 0 |

## 失败/错误 Case

无。

## Baseline 比较

未比较（本轮未请求 baseline）。

## 说明
- 合成数据（synthetic），来源为本项目业务合同，无真实客户/订单。
- offline 模式为确定性 MockAgent + 本地 FixtureTools，证明评测基础设施，不是语言模型能力基准。
- 工具后端故障为规格注入的测试条件，与 Agent 工具选择错误分开统计。
