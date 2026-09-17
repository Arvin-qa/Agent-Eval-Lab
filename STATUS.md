# STATUS

更新时间：2026-09-11（P0 补齐轮收尾）

## 当前阶段
**P0 TECHNICAL GATE = PASS（AC01–AC18 全部实测通过）**。AC19（用户独立演示）待用户按 README 走一遍，属验收人动作。

## 已完成（本轮）
- 阶段1：数据集 v1 冻结——28 条（七类各 4），expected 全部由规格 §5.3 蓝图展开；dataset_hash `55fef164…`（commit 6598f05）。
- 阶段2：产物合同补齐——run.json（元数据）/ traces.jsonl / report.json（报告）/ report.md（同一数据渲染）（f0f2a0e）。
- 阶段3：`--replay`——28/28 判定一致；dataset_hash 不匹配 exit 2；Trace 损坏记 ERROR；不执行 Agent/工具（monkeypatch 证明）。
- 阶段4：`--check-determinism 3`——三次全量结构化一致 identical=True。
- 阶段5：`--baseline`——可比路径 0 regression（exit 0）；dataset_hash 篡改 → NOT_COMPARABLE（exit 2）；未请求为 NOT_REQUESTED。
- 阶段6：**真实缺陷 B8 修复闭环**（优于受控注入）——executor 重试成功后 error_code 残留 → T01 FAIL（27/28，运行 run-20260910T162055Z）→ 根因定位 → 修复 commit ade0d4a → 单 Case 复测 → 全量 28/28 回归 → 证据 docs/evidence/t01_timeout_retry_defect/。
- 阶段7：AC02 网络拦截证据测试 3 个 + 存档 docs/evidence/ac02_network_intercept.md（f0b69e5）。
- 阶段8：最终 Gate 全过（干净 commit f0b69e5）：pytest 93 passed / exit 0；offline 28/28 / exit 0；replay 28 match / exit 0；baseline 可比 0 regression / exit 0；determinism 3× identical / exit 0。

## 已知记录在案的缺陷日志
B1–B9 见 BUGFIX_LOG.md；B8 为真实执行器缺陷并完成失败→修复→回归闭环；B3 修复早于首次提交，无可恢复旧状态，未采用受控注入。

## Blocker
无。

## 下一步（未开始，需另行决策）
1. 用户按 README 独立走 5–10 分钟演示（AC19）。
2. P1（真实 LLM 适配）按规格 W4.2 与验收 L01–L03 评估，仅在 P0 确认后另行启动。

---

# 扩展轮（数据工厂 Round 1 + v2 runner 接入，2026-09-14，用户直接指令）

## 已完成（本轮）
- 扩展数据集：15 维度 × 500 条（datasets/expansion/round_001.jsonl），expected 由合同推导 + 构建期 parse 自检；独立 QA 全绿（重复率 0.00%、类别 15/15、状态 8/8、原因码 13/13、30+ 逻辑一致性断言）。生成器/QA 在 data_factory/。
- v2 合同接入 runner：schemas.py 新增 V2_CASE_SCHEMA（12 字段 + 15 类别）与 load_cases 按行分派（v1 合同零改动）；tools.py 新增 build_world_from_state（case 内嵌工具世界）；runner.py normalize_case 幂等映射 + 多轮/记忆类跳过（skipped_cases 计入报告，score 分母=可执行数）；replay 同步适配。
- TDD：新增 19 项测试（tests/test_expansion_v2.py），全量 pytest 112 passed。
- 实测：v2 全量 430/430 PASS（70 条多轮/记忆类按设计跳过，AGENT_NO_SESSION_STATE）；v1 冒烟 28/28；v2 determinism 2× identical。
- 真实缺陷闭环：B10（MockAgent 脏 eta 写入输出，评测器发现 → 修复 mock-0.2 → 回归）+ B11（生成器 eta_ask 误用 note 文本），见 BUGFIX_LOG.md。
- v1 冻结基线未动：cases.jsonl / fixtures.json 原样，dataset_hash 不变。

## 已知边界
- 70 条多轮/记忆类 case 待 Agent 会话能力（P1）后启用；evaluation_rules 中 llm_judge 规则为 P1 前置，本轮不执行。
- expansion 数据集首次全量 PASS 运行 run-20260913T162957Z 可作为该数据集自身的 baseline 存档（与 v1 baseline 跨 dataset 天然 NOT_COMPARABLE，符合设计）。

## Blocker
无。

## 下一步（未开始，需另行决策）
1. AC19（用户演示）与 P1（真实 LLM）同 P0 收尾时的状态，待用户启动。
2. 扩展方向候选（用户逐项确认后启动）：真多轮 turns 结构（3/5/8 轮）、Failure Corpus（failure taxonomy + regression_suite）、对抗集扩展。
