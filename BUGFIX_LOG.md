# BUGFIX_LOG

只记录有学习或工程价值的问题（拼写/格式类仅在其造成功能缺陷时记录）。范围：P0 最小闭环轮（2026-09-10）。

## B1 意图关键词缺口：M03 的输入被分为 unknown

- **现象**：`tests/test_tools.py` 意图分类测试中，`ORD-1002 预计哪天到`（PROJECT_SPEC §5.3 M03 的输入）被判为 `unknown` 而非 `shipment`。
- **根因**：物流关键词表只有 `物流/快递/到货/送货/收货`，“预计哪天到”不含其中任何一个。TDD 先写的测试让它在实现前暴露。
- **修复**：关键词表补充 `预计哪天`、`哪天到`（schemas.py `_SHIPMENT_KEYWORDS`）。
- **教训**：意图关键词集必须从数据集输入反推；每条 Case 的 input 都应有对应意图断言，否则缺口要到 Week 2 才暴露。这也印证了规格“Mock 规则必须公开边界”的要求——规则表就是合同的一部分。

## B2 枚举列表与常量的双份维护导致 ImportError

- **现象**：`order_eval/agent.py` 导入 `AMBIGUOUS_ORDER_ID` 报 ImportError；该字符串只存在于 `REASON_CODES` 列表里，没有同名常量。
- **修复**：在 schemas.py 补齐全部 13 个原因码常量。
- **教训**：同一组枚举以“列表 + 常量”两份形式维护必然漂移。后续应让列表由常量派生（或反之），只留一份事实来源。

## B3 评测器控制流缺陷：输出解析失败会跳过与输出无关的维度

- **现象**：初版 evaluator 在 `parsed_ok=False` 时提前 return，工具选择/参数/约束三个只依赖 Trace 的维度被直接标 PASS。
- **风险**：一条“输出是自由正文 + 同时乱调工具”的 Trace 会在报告里只显示 Output Format FAIL，掩盖越界调用，违反 §6.1“允许多原因、不能掩盖关键错误”。
- **修复**：重写为单趟分层计算：格式失败只把 `task_success/groundedness` 置 N/A（§6.1 规则），其余维度照常判定后再聚合。
- **教训**：维度之间的依赖关系（哪些依赖输出、哪些只依赖 Trace）必须直接体现在控制流上；“提前返回”会把依赖关系隐藏掉。

## B4 `pass` 是 Python 关键字，不能作关键字参数

- **现象**：`test_regression.py` 中 `_minimal_report(pass=27)` 触发 SyntaxError，pytest 收集阶段即失败。
- **修复**：辅助函数改用 `pass_count` 形参。
- **教训**：报告字段用 `pass` 命名（贴合 JSON 报告习惯）时，测试侧构造辅助函数要预留映射，不要让 JSON 键名直接进 Python 调用。

## B5 AC07 防泄漏控制试验的测试设计错误

- **现象**：控制试验篡改了 `case["fixture_id"]` 后断言 Agent 输出不变，失败。原因是 fixture_id 属于 Runner 控制的**工具世界**，改它改变的是环境（超时注入），输出本就该变。
- **修复**：控制试验只篡改 `expected_key_facts/expected_behavior/critical` 等标准答案字段；fixture_id 语义在测试 docstring 中写明。
- **教训**：控制试验必须隔离“被测变量”。防泄漏针对的是答案（expected_*），不是环境；把两者混在一起测，测的是错误的假设。已由 test_scenarios.py::TestAnswerLeakagePrevention 固化。

## B6 用子串检查“Agent 不导入 evaluator”产生误报

- **现象**：`"evaluator" not in source` 被模块 docstring 里的中文说明（提及 evaluator 一词）误触发。
- **修复**：改用 AST 解析 import 语句集合做判断。
- **教训**：对源码做结构性质疑时，用 AST 而不是文本匹配；文本匹配测出的是“文档提到过”，不是“代码依赖了”。

## B7 report.md 表格分隔行前导空格破坏渲染

- **现象**：六维结果表的 `| --- |` 分隔行多一个前导空格，Markdown 表格不渲染（S7 验证抽查 report.md 时发现）。
- **修复**：runner.py `render_report_md` 修正；重跑 offline 验证。
- **教训**：报告渲染属于“用户直接看到的合同”，S7 的验证必须包含对产物的抽查，而不只看 CLI 摘要和 exit code。

## 记录在案的设计取舍（非缺陷）

- **Agent 在金额查询里额外输出有据 `order_status`**：规格允许“额外有据事实”（评测反例 V2 验证），初版测试按精确字典相等断言过严；改为按 `expected_key_facts` 子集断言。`expected_key_facts` 是子集合同，不是全等合同。

## B8（真实缺陷）执行器重试成功后 `RequestOutcome.error_code` 残留 TIMEOUT，Agent 误降级

- **发现方式**：自然发现。数据集从 6 条扩展到 28 条后，T01（TIMEOUT→成功）首次进入套件，全量运行报 27/28，T01 FAIL。**不是受控注入，也不是规格评审发现的。**
- **现象**：Trace 显示 `call-1#1 err=TIMEOUT`、`call-1#2 err=None`（执行器两次尝试行为正确），但 AgentOutput 为 `unavailable/TOOL_UNAVAILABLE`，与期望 `answered/order_status=PAID` 不符。
- **根因**：`tools.py Executor.execute` 的超时分支把 `outcome.error_code` 置为 `TIMEOUT` 后继续重试；第 2 次尝试成功时只更新了 `outcome.tool_result`，**没有把 `outcome.error_code` 复位为 None**。Agent 的 `_order_branch` 以最终 `error_code` 为准，读到残留的 TIMEOUT 误判为耗尽。
- **为什么此前没发现**：种子六条不含“超时后成功”路径；`test_tools` 的单测只断言了每次 attempt 的 error_code 与最终 data，没有断言 outcome 级 `error_code` 在重试成功后应为 None。组件测试绿 + 场景缺失 = 漏网。
- **影响**：把可恢复的一次性超时当成不可用，属于过度降级（假阴性成功）；若接入真实 LLM 会把模型正确答案错判为失败。
- **修复**：成功分支显式 `outcome.error_code = None`；新增回归单测断言“重试成功后 outcome.error_code 为 None 且 tool_result 可用”。
- **证据**：`docs/evidence/t01_timeout_retry_defect/`（失败运行报告 report_FAIL_run-20260910T162055Z.* 与 trace_FAIL_T01.json，T01 FAIL→修复后 PASS，全量 28/28）。

## B9（数据集缺陷）B03/I04 填充长度手工计算错误

- **发现方式**：28 条全量首次运行，B03 FAIL。手工数"查 ORD-1001 订单状态"的字符数时按 10 字符算（漏计空格），用 490 个句号填充得 505 字符（应为 485），B03 变成 505 字符被正确判为 invalid_input，导致 SEL-REQUIRED-MISSING + 全部 Task Success 失败。
- **根因**：生成脚本里硬编码填充数而不是从 `len(base)` 推导。
- **修复**：改用 `base + "。" * (500 - len(base))` 动态计算，断言 strip 后长度恰为 500/501。
- **教训**：边界构造必须程序化验证长度断言，不能手算；评测系统对数据集错误的反应（B03 FAIL 并给出可读原因）恰好证明门禁有效。
- **另记**：B3（评测器解析失败提前 return）修复于首次提交之前，Git 中不存在可恢复的修复前执行状态；AC18 闭环由 B8 真实缺陷承担，无需受控注入实验。

## 数据集 v1 冻结记录（2026-09-10，commit f0b69e5 实测）

- cases：`datasets/cases.jsonl`，28 条，七类各 4，dataset_hash = `55fef164107332777ddcac722fed47d3dfc40ad6ee93a1839222e4a675d49868`
- fixtures：`datasets/fixtures.json`，fixtures_hash = `a84544184c16bde948ffeae9a81638ad38d3fbe9f78715278ca880c1f51a0146`
- 冻结后修改任一文件都会改变散列，baseline 比较将返回 NOT_COMPARABLE；新增 Case 按新版本处理，不删除旧 Case 提分。

---

# 扩展轮缺陷（Round 1 数据工厂 + v2 runner 接入，2026-09-14）

## B10 MockAgent 把格式非法的 eta 直接写入输出（真实缺陷，评测器发现）

- **现象**：v2 扩展数据集 6 条 DirtyData 案例（eta 为空串/空白/`2026/09/25`/`明天下午`/缺前导零/尾部空格）运行 FAIL，全部 `output_format/OF-SCHEMA`——MockAgent 的 `eta is not None` 判定把脏值原样放进 `facts.eta`，违反 AgentOutput 合同的 eta pattern（§4 `^\d{4}-\d{2}-\d{2}$`）。首次暴露于运行 run-20260913T162730Z（423/430）。
- **根因**：v1 fixture 没有脏 eta 数据，`is not None` 判定在 v1 上正确；expansion 数据的脏 eta 组合让缺陷可见。这与 B8 同模式：数据空间扩大让已有实现的真实缺陷暴露。
- **修复**：agent.py 增加 `_ETA_FORMAT_RE` 校验，非法格式按缺失处理（询问时 → partial + `ETA_NOT_AVAILABLE`，未询问时省略）；版本 bump `mock-0.1` → `mock-0.2`。修复后 430/430 PASS（run-20260913T162957Z），v1 28/28 回归无变化。
- **教训**：`is not None` 只能判"键缺失"，不能判"值可用"；对有格式合同的字段，缺失与非法是两条不同的脏路径，参考实现必须都处理。

## B11 数据生成器把 note 注入文本误当作用户询问 ETA

- **现象**：v2 生成器首版 `PIN-002` 运行 FAIL（`task_success/TS-STATUS`）：expected=partial 但实际=answered。
- **根因**：生成器对注入 note 案例的 `eta_ask` 判定写成了"note 文本含『询问到货时间』"——但 §4 合同里"是否询问 ETA"只取决于**用户输入**（`_ETA_ASK_KEYWORDS` 扫描 parsed.raw），note 是工具返回的不可信文本，不构成询问。用户输入（物流模板）没问 ETA → 合同答案应为 answered 两事实。
- **修复**：生成器该分支固定 `eta_ask=False`（跟随用户输入语义），重新生成数据集并通过独立 QA；重跑 430/430 PASS。
- **教训**：eta_ask/asked_eta 这类"用户意图"标志的唯一合法来源是用户输入文本；把工具返回内容混入意图判定，等价于让不可信文本影响评测标准答案。
