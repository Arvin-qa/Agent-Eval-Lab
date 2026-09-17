# OrderTrace Eval — 30 天实施任务

制定日期：2026-09-10。只规定实施任务、接口和验收，不提供完整代码。本计划依据同目录 PROJECT_SPEC.md 与 ACCEPTANCE_CRITERIA.md。

目标：完成本地可运行、无 Key 可评测的只读订单 Agent 作品集。核心技术：Python、pytest、JSON/JSONL、jsonschema；P1 可用 requests 接一个真实 LLM。顺序是逐个闭环，任何协助工具都不得自行扩大业务范围。

## 1. 执行假设与规则

- 每周 10–15 小时，30 天有效工作约 45–60 小时；照护或中断导致时间不足时，先交付 preview，不能以熬夜或补技术栈抵消超期。
- 先读两份合同再开工。本次交付仅为规格；不要把下面的示例命令当成已经存在的程序。
- 每次只推进一项可验证任务。先明确失败/成功输入与预期，再实现；一个模块验收失败就就地解决，不接着堆模块。
- 使用 AI 可以协助解释、写样板、查错；核心规则必须自己手写/仿写一遍并能改动。记录“独立写/参考改/AI生成后验证”，不把跑通视为掌握。
- Git 本地提交即可，不要求公共发布、云部署或第三方服务。任务完成时保留关键 commit 与真实运行证据。
- 不设置每半小时几十个自动化任务，不让不同执行工具同时修改同一文件。每天结束只写：完成什么、哪条未通过、下一步是什么。

## 2. Week 1：最小 Agent + Tools + Mock（约 12–15 小时）

**输入**：三份规格中业务合同、两个工具 schema、六条种子场景；本机 Python/pytest 环境。

### W1.1 固定合同、建可运行骨架

文件：README.md、requirements.txt、pytest.ini、.gitignore、order_eval/schemas.py、tests/test_tools.py。

- [ ] 确认一套实际可安装的 Python 小版本与依赖，写入 README；只装离线必要包。
- [ ] 定义输入、工具请求/返回、AgentOutput 的类型与枚举；金额用整数分，时间用固定快照。
- [ ] 用空输入、合法/错误 ID、0 金额、非法 status、额外参数验证合同；500/501 边界按 strip 后 Unicode 字符数。
- [ ] 初始化 Git，提交可运行的合同与测试。

产出：合法数据通过、非法结构被明确拒绝；用户能解释 required 字段与 null/0 的差别。对应 AC01、AC04。

### W1.2 两个本地工具与执行器

文件：order_eval/tools.py、datasets/fixtures.json、tests/test_tools.py。

输入：`tool_name + arguments` 和 Runner 预置的 Fixture 世界。输出：标准化 ToolResult、原始结果、尝试记录；每次尝试独立 call_id。

- [ ] 实现 get_order/get_shipment 的固定数据读取；先完成 F1/F2/F404。
- [ ] 实现 allowlist、参数校验、结果结构/订单号校验；禁止动态执行工具名。
- [ ] 加入 TIMEOUT→成功、两次 TIMEOUT、TOOL_ERROR 的注入序列。注入计数每次 trial 重置，不真实等待。
- [ ] 只对 TIMEOUT 重试一次，记录两次尝试。物流前置条件与总尝试上限由执行器保护。
- [ ] 验证正常、错工具、缺参、错 ID、空记录、重试耗尽；错误必须能被调用方区分。

产出：工具层独立于 Agent 可以测；异常不通过打印后忽略。对应 AC04/05。

### W1.3 最小 MockAgent 与六条贯通

文件：order_eval/agent.py、order_eval/runner.py、run_eval.py、datasets/cases.jsonl、tests/test_scenarios.py。

接口：Agent.run 只收到 `user_input, tool_executor`；Runner 持有 Case expected 与 fixture_id，永不传给 Agent。Agent 从可见输入选工具，从实际 ToolResult 组装结构化答案。

- [ ] 完成状态、金额、物流三个意图；不做通用自然语言解析。
- [ ] 先贯通 N01、N02、I02、T02、M01、H02；输入→调用→结果→答案→初版 Trace 都能看到。
- [ ] 输出只用 facts/reason_codes/evidence；中文展示由模板渲染。
- [ ] 预留 mode 参数但只实现 offline；未实现 llm 时明确报错，不能伪装成功。
- [ ] 自己修改一个订单金额，说明为何只有读取该事实的输出应改变；此时先看结果，不追求全套分数。

**Week 1 完成定义**：无 Key 完成六条种子路径，工具/输入错误有可读原因，Agent 没有偷看 expected。

**Quality Gate**：AC01–05 的种子范围通过；手动跑 N02 能解释两次工具及证据。失败则 Week 2 开始先修，不加真实 LLM、Web 或其他框架。

## 3. Week 2：Dataset + Evaluator（约 12–15 小时）

**输入**：Week 1 的六条闭环、完整 28 条蓝图、六维定义。

### W2.1 人工完成并冻结 28 条数据

文件：datasets/cases.jsonl、datasets/fixtures.json、tests/test_scenarios.py、order_eval/schemas.py。

- [ ] 按 PROJECT_SPEC 的每行展开完整 schema；统一规则展开到每条 forbidden_behavior。
- [ ] 为各命名 Fixture 写完整覆盖值与故障序列；C01 的 delivered_at 固定为 2026-09-09T12:00:00Z，避免不明确字段。
- [ ] 明确每条允许工具、必需工具及尝试次数；零工具案例不是空白期望。
- [ ] 对每条手算预期状态/关键事实/原因/证据来源。先核定答案，再运行 Agent。
- [ ] 检查 28 个唯一 ID、七类各四条、500/501 字符、无真实隐私数据；冻结版本和内容散列。

产出：一套人能读懂、可以解释标注依据的数据，所有 Case 都有可满足的正确行为。对应 AC06。

### W2.2 六维 Rule-based Evaluator

文件：order_eval/evaluator.py、tests/test_evaluator.py。

输入：完整 Case 与 Trace；输出：每维 PASS/FAIL/N/A + check_id + expected/actual + failure_reasons + overall。

- [ ] 实现格式、工具集合/必需调用、参数、事实来源、结果完整性、约束六类判断。
- [ ] 完成 N/A 规则；缺必需调用与空答案不能绕过任务评分。
- [ ] 引用需要校验工具、当前 Case 的 call_id、JSON pointer、结果有效性与值，不能只检查“有 evidence 字段”。
- [ ] 正常、合法拒绝、合法降级必须能 PASS；故障场景不是天然 FAIL。
- [ ] 先写 E01–E12 的独立手工 Trace 标注，再确认 Evaluator 抓住每个错误；不要用 Agent 实时生成这些标准样本。
- [ ] 验证合法 key 顺序、额外有据事实不被误杀；确认 no facts 在正常请求中 FAIL。

产出：可解释的裁判，不依赖 LLM Judge。对应 AC08–10。

### W2.3 最小报告与 CLI 分母

文件：order_eval/runner.py、run_eval.py、tests/test_regression.py。

- [ ] 全量跑 28 条，生成 report.json 与由它渲染的 report.md。
- [ ] 实现 counts、Score、六维分母、Case 错误、category 汇总；后端故障与 Agent 错误分开。
- [ ] 退出码 0/1/2 与 PASS/FAIL/ERROR 含义保持一致；部分失败仍保存报告。
- [ ] 验证 25 PASS、2 FAIL、1 ERROR 的合成运行应为 89.29%；这是单元测试样例，不能写成实测成绩。

**Week 2 完成定义**：28 Case 都可执行评分；每条 FAIL 有具体理由，至少 12 个好坏 Trace 反例测试通过。

**Quality Gate**：AC06–11 通过；当周全量结果不要求强行 28/28，允许留下真实可定位缺陷进入 Week 3，禁止改 expected 迎合错误输出。

## 4. Week 3：pytest + Trace + Regression + Failure Cases（约 12–15 小时）

**输入**：Week 2 的完整评测运行与失败列表。

### W3.1 补齐运行身份与重放

文件：order_eval/runner.py、run_eval.py、tests/test_regression.py。

- [ ] 补齐 Trace 字段、原始/标准化工具结果、模型步骤空数组、配置和内容散列、版本与 dirty 标记。
- [ ] 每次 trial 重建工具世界，确保故障计数无残留；不要让 pytest 的可变参数共享产生串扰。
- [ ] 实现 --replay：只读旧 Trace 与匹配 Case，由相同 Evaluator 重评；不执行 Agent/工具。
- [ ] 重放前核对 dataset_hash；版本不符明确停止。正式 baseline 来自干净已提交代码，单独交付证据时保留匹配的合成 Case/Fixture 与配置。
- [ ] 同一离线版本全量执行三次，过滤易变元数据后比较答案、调用与评分。
- [ ] 对随机调用 ID 按本 Trace 顺序规范化并同步改引用；保留全部业务参数/结果，防止“过滤掉错误”造成假一致。
- [ ] Trace 缺失/损坏、Case 未完成记 ERROR；报告 counts 不丢 Case。

产出：可追溯且能重评的执行证据。对应 AC12/15/16。

### W3.2 基线比较与故障修复

文件：order_eval/runner.py、tests/test_regression.py、docs/BUGFIX_LOG.md、docs/evidence/。

- [ ] 选择 Week 2 一次真实运行作为 baseline；保持内容不变，并记录指向。
- [ ] 实现 Case regression/improvement、维度退化；metadata 不可比返回 NOT_COMPARABLE。
- [ ] 用“一条变好、一条变坏、总分不变”的人工结果测试比较器，确保仍能抓回归。
- [ ] 从实际失败中选一条，定位输入、工具、输出或 Evaluator；记录为什么不是另一个层的问题。
- [ ] 先保留失败运行，再修改；单 Case 复测后全量回归；保存旧/新报告与 commit。
- [ ] 如果碰巧没有自然失败，可显式做一次受控缺陷实验，例如错误地用 `if amount_cents` 把 0 当缺失。必须真实执行，并标记“人为注入验证”，不能编成偶然发现的生产事故。

产出：一个能展示且如实标注来源的失败→根因→修复→回归闭环。对应 AC13/14/18。

### W3.3 完成默认 pytest 门禁

文件：tests/test_tools.py、tests/test_scenarios.py、tests/test_evaluator.py、tests/test_regression.py、pytest.ini。

- [ ] 默认 pytest 覆盖四类实际责任，离线执行，P0 不用 skip/xfail 掩盖。
- [ ] 加入网络拦截验证 offline；检查错误工具被拦仍判行为 FAIL。
- [ ] 对真实风险补测试：跨 Case 引用、zero amount、缺必需调用、重复 key、重试超限、不可比基线。
- [ ] 报告的工具统计可回算到 Trace；失败 Case 一键/一条命令可重跑。
- [ ] 全量 offline 参考实现达到 28 PASS、0 FAIL、0 ERROR；任何仍存在的失败先归因，不靠删除数据达标。

**Week 3 完成定义**：全部 P0 技术链路完整，pytest 通过；旧缺陷版本能被检出，修复版无新增离线回归。

**Quality Gate**：AC01–18 全部通过。此时满足提前投递条件就可以投，不等漂亮展示或真实 LLM。

## 5. Week 4：报告 + README + Demo + 简历（约 9–15 小时）

**输入**：可验收的 P0、精选失败/修复证据、真实执行统计。

### W4.1 让别人能自己运行

文件：README.md、docs/evidence/、docs/BUGFIX_LOG.md、INTERVIEW_STORY.md 的个人填写副本。

- [ ] README 写明用途、只读边界、安装、pytest、offline Eval、重跑 Case、baseline 比较、Trace 重放。
- [ ] 在干净 venv 按 README 走一次；记录实测系统，不声称未测试的平台兼容。
- [ ] 选正常、工具故障、无证据输出、修复回归四个展示片段，确保 5–10 分钟可走完。
- [ ] 用当前真实报告填简历数据；尚未跑过的项目指标继续留空/不写。
- [ ] 完成十个追问的口头或文字答案；不看 AI 提词，至少解释一个关键函数和一个断言。

产出：别人可运行，自己能解释。对应 AC19/20。

### W4.2 P1 可选：接一个真实 LLM

仅在 P0 已通过且还有约 4–6 小时时做；否则整个任务后移。

文件：order_eval/agent.py、requirements-llm.txt、run_eval.py、README.md；如需要集成测试新建 tests/test_llm.py 并标记默认排除。

- [ ] 核验供应商工具调用协议和账户模型；不假定 IDE 订阅可提供 API。
- [ ] 用 requests 实现一个供应商兼容的工具循环；保留可见模型步骤；禁止无限重试和静默 fallback。
- [ ] 首次先跑 N01，确认实际模型提出工具请求、获得结果后输出结构化答案。
- [ ] 逐步跑 N02、T02；有预算跑全量 28；再考虑指定 14 条 ×3。所有运行分开报告，真实 API 故障记 ERROR。
- [ ] 使用 API usage 记录 Token，费用缺费率就写 null；模型输出格式失败也作为结果保留。
- [ ] 人工阅读实际失败 Trace，确认 Evaluator 没误判，至少归纳一种模型/提示词/执行器的责任差异。

产出：真实工具调用链路证据；是否及格依据诚实、完整，而不是模型必须高分。对应 L01–L07 的实际完成部分。

### W4.3 P1 可选：CSV

只有确实需要筛选失败 Case 时，从 report.json 导出一行一个 trial 的 CSV；包含 case_id、category、overall、失败维度、reason、trace 路径。没有这个需求就不做，Markdown 已能交付。

**Week 4 完成定义**：完整 P0 可展示，简历数字来自真实产物，用户独立解释失败闭环。LLM/CSV 完成了多少写多少。

**Quality Gate**：AC19/20 通过；未完成 P1 不影响完整离线 v0.1；若宣称真实 LLM 集成，则至少 L01–L03 要有证据。

## 6. 工期风险与删减顺序

| 触发条件 | 动作 |
| --- | --- |
| Day 7 六条种子仍不通 | 停止扩数据，解决单条输入→工具→输出；删除所有 P1 时间安排 |
| Day 14 评测器仍靠“答案包含某词” | 优先输出合同与证据核验，报告只做必要字段；不得加 Judge 掩盖问题 |
| Day 21 无失败修复证据 | 做一次明确标注的受控缺陷实验并实际回归；不写虚构经历 |
| 总可用时间只剩 20–30 小时 | 使用 14 条 preview 集完成闭环，完整 28 条后补；所有数字按真实范围改 |
| LLM 频繁限流/输出失败 | 保留结果，停止扩大实验；offline 照常演示，不把 API 排障拖成主项目 |
| 觉得项目太简单想加框架 | 先回答“能否独立解释一条失败及其回归证据”；不新建 RAG/LangGraph/UI |

## 7. 学习与实现的最低独立性

必须自己解释并改动的五件事：

1. 从输入拿到标准化订单号，为什么不能截取更长 ID。
2. get_order 的入参/返回，以及 null、0、TIMEOUT 的差异。
3. 一条 pytest 断言的 expected/actual，失败时从哪里读证据。
4. Groundedness 如何从 facts 追到工具结果，为什么有引用仍可能是假引用。
5. regression 为什么按 Case 比，为什么总分不变也可能变坏。

AI 可协助的重复工作：生成 JSONL 初稿、CLI 样板、Markdown 表格、普通类型定义；用户逐条核验数据与核心规则。面试说“使用 AI 辅助实现，我负责合同、样本复核、失败定位和验收”，前提是确实如此。

## 8. 最终交付检查

- [ ] 同一提交包含可运行代码、数据、测试、README 与必要依赖。
- [ ] 精选 Trace/报告、修复前后证据可用；无真实隐私、Key、无意义大量运行文件。
- [ ] P0 Gate 实测结果写入验收记录；P1 的未完成项明确。
- [ ] 简历未编造样本量、通过率、性能、成本、线上效果。
- [ ] 5–10 分钟演示已亲自走通；3–5 分钟故事能不背技术名词讲清楚。

**执行决策：GO。先做 W1.1–W1.3，随后按 Gate 推进；任何一步都不需要先搭 Web、云服务或复杂 Agent 框架。**
