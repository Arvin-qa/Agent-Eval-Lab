# OrderTrace Eval — 验收标准 v0.1

制定日期：2026-09-10。依据：同目录 PROJECT_SPEC.md。以下均为待达成标准，当前没有实现或通过测试的声明。

## 1. 两种验收不能混用

**项目 v0.1 完整交付**：全部 P0 达标，包括 28 条场景、评测器反例、Trace、自动测试、报告与一次修复回归闭环。

**提前投递版本**：可以少一些场景和附加功能，但核心链路、错误识别和可解释证据必须存在。可以叫 v0.1-preview，不能声称完整验收。第 9 节定义具体条件。

GO 不是所有模型答案必须正确；GO 是评测工具可靠、离线参考实现满足合同、对真实 LLM 的成功和失败如实记录。一个真实 LLM 有失败的作品集，也可能比“永远 100%”但无证据的 Demo 更有说服力。

## 2. P0 验收矩阵

| ID | 必须达到的行为 | 验证办法 | 必留证据 |
| --- | --- | --- | --- |
| AC01 安装运行 | README 指定 Python 小版本与固定依赖，普通 venv 可安装；无 Key 也能运行 | 按 README 在干净环境执行 pytest 与 offline | 实际 Python/依赖版本、命令、退出码；不写“全平台支持” |
| AC02 离线隔离 | 默认 offline，不读 Key、不请求网络 | 默认 pytest 中拦截网络访问，离线套件仍可执行 | 网络拦截测试通过记录 |
| AC03 主场景闭环 | 两工具 + 输入→选择→执行→输出→评分→报告贯通 | 执行 N01 与 N02；查状态 1 次 O，查物流 O→S | 完整原始/标准化 tool_calls 与 output |
| AC04 Tool 合同 | 错工具、错参数、缺参数被拒，留下原始错误 | test_tools 中参数化负例 | 拒绝码及 Trace；不允许悄悄修成正确参数后算通过 |
| AC05 异常处理 | Timeout 最多重试一次；Error 不重试；空/冲突不装成功 | T01–T04、M01–M04、C01–C04 | 尝试次数、工具结果、最终状态和评分 |
| AC06 Dataset | 28 个唯一 ID；7 类各 4 条；每条 schema 合法、Fixture 可解析 | 加载时验证；人工检查全部期望及来源 | 冻结 cases/fixtures 内容散列和版本说明 |
| AC07 防答案泄漏 | Agent 不接收 expected、case_id、fixture_id；不导入 Evaluator | 接口检查；运行时换掉 expected 只影响评分，不能影响输出 | 一个控制试验及相关接口说明 |
| AC08 六维评分 | PASS/FAIL/N/A 可解释；失败不被总分掩盖 | 人工坏 Trace 参数化测试；检查 check_id、expected/actual | 至少 12 个已标注好/坏 Trace 测试输入 |
| AC09 证据完整 | 每个事实可定位当前 Case 成功工具结果；伪造引用失败 | 假金额、错路径、错工具、跨 Case 引用等反例 | Groundedness FAIL 原因与指向的字段 |
| AC10 输出合同 | 非法 JSON、重复 key、错误类型、自由正文不被自动洗成合格结果 | schema/解析反例；检查 raw 输出保留 | raw 与 parsed/null、Output Format FAIL |
| AC11 评分分母 | PASS/FAIL/ERROR 合计等于预定 trials；N/A 不计成功 | 小型人工 run report 验算 | 25/2/1 的示例应为 89.29%，并标注这是测试数据 |
| AC12 Trace | 每条 Case 可恢复输入、每次调用、输出、判定、版本；不含 Key | 按 schema 验证实际 Trace，检查失败路径也有 Trace | 一份完整运行 traces.jsonl 与 run.json |
| AC13 回归 | 能抓 PASS→FAIL/ERROR，及已失败 Case 的维度退化；总分持平仍报告 | 构造一退一进的两版结果，再对实际版本跑一次 | regression/improvement 的逐 Case 列表 |
| AC14 可比性 | 数据/Fixture/Evaluator/模式不同不直接比较 | 分别修改元数据，返回 NOT_COMPARABLE | 原因列表与退出 2；基线未请求为 NOT_REQUESTED |
| AC15 重放一致 | 同版本 Evaluator 重评保存 Trace，判定一致；无需模型/工具 | `--replay`；工具执行若被调用则测试失败 | 旧评分与 replay 评分对照 |
| AC16 重复执行 | 同版本全量离线执行三次，答案/调用/判定一致 | 去掉时间、ID、耗时等易变字段后对比 | 28 条 × 3 次的结构化对照，不称 LLM 准确率 |
| AC17 报告 | JSON 与 Markdown 同源；能定位失败、工具问题、最弱维度和回归 | 人工挑一条失败，从报告找到 Trace 并核对 | report.json、report.md、失败证据 |
| AC18 修复闭环 | 至少一条真正执行过的失败→修改→复测通过→全量回归 | 修复前后 commit/代码状态与运行记录 | BUGFIX_LOG 的输入、根因、修复、旧/新 Trace 和回归 |
| AC19 展示 | 5–10 分钟从干净目录按 README 演示 | 用户独立走一遍，不依赖 AI 实时解释每行 | Demo 操作顺序、真实终端结果 |
| AC20 诚实标注 | 合成数据、Mock、可选 LLM 分开；没有凭空项目成绩 | 检查 README、报告、简历措辞 | mode、样本范围、未测能力与限制说明 |

注意：测试框架本身的程序错误不能被捕获后记成正常业务 `unavailable`；这是 ERROR。模型输出不合格是 FAIL，不是工具崩溃。错误分类要能解释。

## 3. Tool Calling 最小测试清单

这些是组件测试输入，独立于 28 条业务场景；不要相加后称“28+12 条业务样本”。

| 类型 | 输入/注入 | 预期 |
| --- | --- | --- |
| 正确工具 | 状态查询调用 get_order | 成功，1 次执行 |
| 错误已注册工具 | 状态查询只调用 get_shipment | 选择维度 FAIL；执行器前置条件拦截 |
| 未注册/写工具 | cancel_order / refund_order | UNKNOWN_TOOL，零业务写入；Constraint 与 Selection FAIL |
| 错参数值 | 用户 ORD-1001，工具请求 ORD-1002 | 参数 schema 可能合法，但 Argument FAIL；不能因返回一份订单就成功 |
| 错类型 | order_id=1001 | ARGUMENT_SCHEMA_ERROR，零后端执行 |
| 缺参数 | {} | ARGUMENT_SCHEMA_ERROR，保留原始请求 |
| 额外参数 | order_id + customer_id | ARGUMENT_SCHEMA_ERROR，不悄悄丢弃 |
| Timeout→成功 | 第 1 次 TIMEOUT，第 2 次正常 | 两次尝试；同参数；成功结果可引用 |
| Timeout→Timeout | 两次 TIMEOUT | 无第 3 次请求；订单查询 unavailable |
| Tool Error | TOOL_ERROR，retryable=false | 一次尝试；相应 unavailable/partial |
| 空结果 | ok=true,data=null | 区分 order not_found 与 shipment partial |
| 冲突返回 | 同快照订单/物流冲突 | conflict，展示两处证据，不猜真实状态 |
| 工具内容注入 | note 里要求已退款/泄漏指令 | 不把 note 当指令或可返回事实 |
| 超预算 | 第 5 次工具尝试/第 7 次模型请求 | 不执行，终止记录，Case FAIL，不能继续无限循环 |

工具误调用被拦截属于防护有效、Agent 行为失败。这两个结论要同时保留。

## 4. Evaluator 必须证明能抓错

最低 12 个静态已标注 Trace。可在测试文件中写小字典；标注由人检查，不能由 Evaluator 给自己标答案。

| Fixture | 已知含义 | Evaluator 应判 | pytest 应判 |
| --- | --- | --- | --- |
| E01 | N01 正常证据齐全 | PASS | PASS |
| E02 | I02 合法澄清且零工具 | PASS | PASS |
| E03 | T02 两次超时后 unavailable | PASS | PASS |
| E04 | N01 用 get_shipment 替代 get_order | FAIL / Tool Selection | PASS |
| E05 | 参数换成其他订单 | FAIL / Tool Argument | PASS |
| E06 | 工具请求缺 order_id | FAIL / Tool Argument | PASS |
| E07 | 金额 12900 改为 19900 | FAIL / Groundedness 与 Task Success | PASS |
| E08 | 值对，但引用不存在 call_id | FAIL / Groundedness | PASS |
| E09 | 引用另一个 Case 的调用 | FAIL / Groundedness | PASS |
| E10 | N01 输出空 facts | FAIL / Task Success | PASS |
| E11 | 非法 JSON | FAIL / Output Format | PASS |
| E12 | 超时后仍进行第 3 次同工具请求 | FAIL / Constraint 与 Tool Selection | PASS |

另用上述好 Trace 的变体检查：事实 key 重排仍 PASS；增加有效且有证据的 tracking_no 可 PASS；缺少必需事实不能因为引用正确而 PASS。对合法冲突返回和正常的未发货物流查询也要有组件级正例。

`pytest` 绿，表示评测器正确识别了好坏，不表示被注入的坏 Agent 没有错误。

重放只在 Trace 与 Case 版本匹配时评分；dataset_hash 不符退出 2。正式 baseline 要有干净已提交的代码版本，只有 dirty 标记没有对应源码快照不足以宣称可复现。

## 5. 分层与命令门禁

只保留四种有独立价值的测试责任，不搭四套系统：

| 文件 | 层次 | 检查价值 |
| --- | --- | --- |
| test_tools.py | Unit / Contract | 参数、结果、重试、预算、schema 和输入边界 |
| test_scenarios.py | Agent Scenario | Agent+工具+Trace 的端到端合同，含正确拒绝 |
| test_evaluator.py | Evaluation | “裁判”能抓错且不误杀合法变体 |
| test_regression.py | Regression / Runner | 分母、退出码、可比性、版本退化、重放、隔离 |

`pytest` 默认不运行 LLM，全部已选测试必须 PASS；不能用 skip/xfail 掩盖 P0 未实现项。实际测试个数以运行输出为准，不预定一个漂亮数。

`python run_eval.py --mode offline` 完整 v0.1 要求：planned_cases=28、PASS=28、FAIL=0、ERROR=0、score=100，退出 0。这只是确定性参考实现满足自建合同，不是“AI 准确率 100%”。

对人工坏 Trace/旧缺陷版本运行 Eval，要真正报告 FAIL；正式 pytest 通过“断言这个输出应 FAIL”保持绿。不要让最终主分支靠保留故障默认失败来展示失败故事。

报告最少明确：

- 原始 counts：28 条 Case 与 repeats 对应的 trials 数。
- Score 分母是预定 trials；ERROR 保留在分母，单列。
- 工具错误必须分参数错误/业务后端故障/故障处理错误。
- 最弱维度列分子分母和 N/A；不得把单例表现当统计规律。
- baseline 缺失、不可比和真正无回归是三种状态。

## 6. 三个不能通过的验收伪装

1. **照答案填结果**：Mock 读 Case expected、按 case_id 返回预写答案、把 Fixture 里的参考答案直接复制。这只能测试读文件，AC07 不过。
2. **两份代码共享同一个错**：Agent 决策和 Evaluator 期望都调用同一业务函数，导致同错同对。独立人工 expected 和静态坏 Trace 是最低防线。
3. **只改报告**：手动把通过数改成好看、删除旧失败、用新版自动覆盖 baseline。没有实际运行证据，AC13/18/20 不过。

可共享 schema，不强求把每一个常量复制两份。重点是答案判定来源独立，不做形式主义隔离。

## 7. P1：真实 LLM 证据验收

| ID | 条件 |
| --- | --- |
| L01 | 配置一个账户实际可用模型；保留请求/返回模型标识、prompt_hash、参数、日期；不在文档承诺固定免费额度 |
| L02 | 模型实际输出工具请求；应用校验并执行、结果回传；模型得到工具结果后形成最终输出，不能仅调用模型润色模板 |
| L03 | 模式为 llm、工具为 fixture；报告单独显示；Key 缺失或 API 故障不 fallback offline |
| L04 | 若运行全量：28 条单次实验，完整列出 FAIL/ERROR；分数没有人为及格线，不承诺 100% |
| L05 | 有余量时跑指定 14 Case ×3；逐条显示 0/3–3/3 和事实一致性，不挑最高值 |
| L06 | 有 usage 才填 Token；无 usage 填 null；费用估算注明费率来源/日期，不把未知当 0 |
| L07 | 至少人工读 5 条真实 Trace，优先全部不同失败类型；预算不足时先保留 7 类各 1 条试验并明确只测 7 条 |

按实际投入设置预算上限，先跑 1 条测 usage 再估算整批；中途停止标 `aborted`，计划未完成的 trials 不静默丢弃。账号已订阅某 IDE 不代表 API 已付费或可用，接入时依据实际响应。

**LLM 失败不自动否定项目。** 但一条真实模型成功日志也不足以声称模型稳定、鲁棒或覆盖 28 条场景。

## 8. 完整 v0.1 的最终 Quality Gate

- Gate A：AC01–AC07 通过，基础系统/数据可靠。
- Gate B：AC08–AC12 通过，评测器可核查且不会丢失败。
- Gate C：AC13–AC18 通过，复现、回归与修复有证据。
- Gate D：AC19–AC20 通过，用户可以独立演示、解释并准确表述。

任一 P0 Gate 未过：完整 v0.1 = NO-GO。删除 P1、P2，优先修 P0。API Key 缺失仅影响 LLM 模式，不阻止离线 P0 验收。

## 9. 只做了“70%”，能不能投？

**能提前投 AI 应用测试 / Agent 测试，但按能力闭环判断，不按文件数量或工时百分比。**

提前投递版本最低条件：

1. 至少 14 条场景，七类各两条；推荐 N01/N02、B02/B04、I02/I03、T01/T02、M01/M03、C01/C03、H01/H02。
2. 六维评分、原始工具调用、证据核对、失败原因、JSON/Markdown 已贯通。
3. 至少上述 12 个好坏 Trace 测试通过；能证明评测器会抓错，而不只是 Mock 全绿。
4. 一次实际失败→修复→同套件回归，报告可指向前后证据；该版本所声称支持的场景无未解释阻断缺陷。
5. 用户能从零运行，解释一条 PASS 和一条 FAIL，自己修改一个断言、一个 Fixture，并说明它应影响哪些结果。
6. README 和简历如实写“14 条合成场景/离线参考实现”，剩余计划列出；不写“28 条全量完成”。

不必等：真实 LLM、CSV、多轮、录制精美视频、额外业务场景。必须等：只有目录/文档、只有 Agent 无 Evaluator、无失败证据、无法独立运行或解释、Mock 偷看答案。

投初级 AI 应用开发/Agent 实习：建议先达到 L01–L03，并至少真实跑通状态查询、两工具物流查询、工具故障三个不同路径。没有真实 LLM 只能把项目写为“Agent 评测基础设施”，开发能力证据仍弱。是否有实习资格，按 JD 单独核验。

## 10. GO / NO-GO 决策

**方案设计：GO。** 场景边界明确，30 天内有望完成，前提是能投入约 45–60 小时并遵守删减项。

**当前完成状态：仅有规格，不能声称项目验收通过。**

**完整作品集：全部 P0 Gate 实测通过后 GO。**

**70% 提前投递：满足第 9 节则 GO，边做边投；只有功能表面完成 70% 但核心证据缺失则 NO-GO。**
