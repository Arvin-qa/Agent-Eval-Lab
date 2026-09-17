# AI Agent Evaluation 数据工厂 — Round 1 数据集报告

- **产物**：`datasets/expansion/round_001.jsonl`（500 条，自包含工具状态，可直接用于 pytest / rule-based / LLM-as-Judge）
- **生成**：`python data_factory/generate_round1.py`（确定性生成，无随机数；构建期用仓库真实 `parse_user_input` 逐条自检解析结果）
- **QA**：`python data_factory/validate_round1.py` — **exit 0，全部通过**（独立校验器，与生成器逻辑解耦）
- **冻结基线**：v1（28 条）未改动；`python -m pytest` — **93 passed in 14.03s**
- **日期**：2026-09-14

---

## 1. Schema（12 必填字段 + 2 扩展）

| 字段 | 说明 |
| --- | --- |
| `case_id` | 唯一键，`R01-<类别码>-<序号>`，如 `R01-ICF-021` |
| `category` | 15 个测试维度之一（§3） |
| `difficulty` | easy / medium / hard |
| `user_input` | 原始用户输入（多轮场景为最后一轮；历史在 `context.prior_turns`） |
| `context` | `{prior_turns: [{role,content}], session_facts: {claims:[…]}}` |
| `tool_state` | 自包含工具世界：`orders/shipments/faults/injected`（含覆盖说明），每条独立可执行 |
| `expected_behavior` | `{status, reason_codes, required_fact_keys}`，与 v1 合同同源（§4 状态全集/原因码全集） |
| `forbidden_behavior` | 机器规则 ID（v1 七词 + 12 个扩展词，见 §5） |
| `expected_tool` | 期望调用的工具集合（零调用场景为 `[]`） |
| `expected_args` | 期望调用序列：工具、精确参数、min/max 尝试次数、前置条件（`requires`） |
| `evaluation_rules` | 判定规则集，`mode` ∈ `rule_based / llm_judge`；固定六维 + 场景专属（context_resolution / memory_authority / budget / llm_judge rubric） |
| `severity` | minor / major / critical |
| `expected_key_facts`（扩展） | 人工核定事实值；与 `required_fact_keys` 键一致 |
| `provenance`（扩展） | `synthetic` + 合同条款引用（§3/§4/§5.3） |

## 2. 查重结果

| 指标 | 值 |
| --- | --- |
| case_id 唯一 | 500/500 |
| user_input 精确唯一 | 500/500，**重复率 0.00%** |
| 规范化（去标点小写）唯一 | 500/500（豁免清单 `norm_dup_allowed.json`：500/501 字符填充案 2 条、空白变体 3 条、分隔符陷阱 3 条——同形即测试本意） |
| 模板集中度 | 每模板实例全局唯一；2 个 12-gram 被 >6 条共享（"帮我看看/帮我查下"类公共礼貌语），已评估为可接受 |

## 3. 覆盖率

**类别 × 数量（15/15）**：Normal 45 · Boundary 40 · Abnormal 30 · ToolError 30 · ArgumentError 30 · Timeout 30 · DirtyData 35 · Hallucination 40 · MultiTurnContext 40 · InstructionConflict 30 · PromptInjection 35 · AgentLoop 25 · Retry 30 · Fallback 30 · MemoryInconsistency 30

**难度**：easy 79 / medium 169 / hard 252　**严重度**：minor 84 / major 186 / critical 230

**期望状态（8/8 全覆盖）**：answered 295 · partial 67 · unavailable 51 · unsupported 31 · not_found 21 · clarification 16 · invalid_input 9 · conflict 10

**原因码（13/13 全覆盖）**：TOOL_UNAVAILABLE 62 · order_status 类 327 · ETA_NOT_AVAILABLE 24 · INVALID_TOOL_RESULT 18 · UNSUPPORTED_ACTION 17 · NOT_SHIPPED 14 · UNSUPPORTED_QUERY 14 · ORDER_NOT_FOUND 21 · MISSING_ORDER_ID 12 · DATA_CONFLICT 10 · AMBIGUOUS_ORDER_ID 4 · SHIPMENT_NOT_FOUND 6 · AMOUNT_NOT_AVAILABLE 8

**工具**：get_order 444 条 · get_shipment 174 条　**故障注入**：O timeout→ok 21 · O timeout×2 18 · O error 17 · S timeout→ok 16 · S error 14 · S timeout×2 10 · O 三连超时（预算耗尽）3

**事实键**：order_status 327 · shipment_status 129 · amount_cents/currency 各 35 · eta 15（tracking_no/delivered_at 按合同为"可有可无附加事实"，不作必需键，仅出现在 groundedness 附加断言中）

## 4. 逻辑一致性（校验器逐条断言，全绿）

1. **解析器交叉验证**：每条输入用仓库 `parse_user_input` 重解析；INVALID_INPUT/歧义/缺号/写关键词/超长 → 对应 expected 且零工具调用
2. **调用一致性**：`expected_tool` 与 `expected_args` 工具集相等；get_shipment 必带 `requires=get_order`；尝试次数 ∈ [1,2] 且与故障序列匹配（timeout 起=2，error/干净=1）
3. **事实合同**：required_fact_keys 与 expected_key_facts 键对齐；事实来源工具必须在 expected_tool 内；eta 必须格式合法且与世界状态一致；零事实状态不得携带事实
4. **世界状态一致**：not_found ⇔ 订单不存在；conflict ⇔ 触发 `detect_conflicts` 三规则之一（反向亦查）；PAID/CANCELED 订单不得调用 get_shipment
5. **预算**：最少尝试总和 ≤ 4（§3.3 执行预算）
6. **类别不变式**：幻觉/冲突/记忆类必禁编造或沿用记忆；注入类必禁 obey_*；AgentLoop 必含 budget 规则；多轮必含 context_resolution 且 prior_turns 非空；记忆矛盾场景的 claim 值必须与 expected 值不同（构成真矛盾）
7. **禁值校验**：groundedness 规则中的 forbidden_values 与 expected_key_facts 无交叠

## 5. 测试空间扩展说明（v1 七类之外新增 8 维）

expected 全部从既有合同推导，非虚构：

| 新维度 | 合同依据 |
| --- | --- |
| Abnormal | §3.1.7 关键词意图边界（写操作/未知意图/运单号直查） |
| ArgumentError | §3.1 严格 token 识别 + §3.2 参数 schema（additionalProperties=false） |
| Timeout / Retry | §3.3 故障语义（仅 TIMEOUT 重试一次、同参数、error 不可重试、data=null 非故障不重试） |
| AgentLoop | §3.3 总预算 4 + §3.2 前置条件（PRECONDITION_FAILED 回退） |
| Fallback | §4 partial 降级规则（物流层失败回落订单事实；订单层失败禁绕过） |
| MultiTurnContext | §3.1.6 指代消解后仍走完整查询合同（向前兼容，需 Runner 支持多轮注入） |
| InstructionConflict / PromptInjection | §5.3 H03/H04 蓝图泛化：用户侧伪指令与工具 note 注入均非事实/指令来源 |
| MemoryInconsistency | §4 事实唯一来源是当前工具快照（会话记忆不构成证据） |

扩展禁止词（12 个）：`fabricate_eta/amount/status/tracking_no/currency`、`obey_user_injection`、`precommit_unverified`、`skip_verification`、`adopt_memory_value`、`resolve_wrong_order`、`unbounded_retry`、`call_before_precondition`。

## 6. 与冻结基线的关系

- `datasets/cases.jsonl`（v1，28 条，dataset_hash `55fef164…`）**未做任何改动**；pytest 93 项全绿，offline 基线不受影响。
- 本数据集为**独立新版本（expansion/round_001）**，遵守"加 Case 按新版本、不删旧 Case"规则。
- **尚未接入 runner**：当前 `order_eval/schemas.CASE_SCHEMA` 为 `additionalProperties: false` 且仅含 v1 七类，直接加载本数据集会失败。接入需要：① CASE_SCHEMA 迁移到 v2（新增字段/类别枚举）② Runner 支持 `context.prior_turns` 注入。按项目协议，该迁移属规格变更，需单独立项，本报告不擅自实施。
- MockAgent（offline 参考实现）在多轮/记忆类上预期 FAIL（其无会话状态）——这是数据集的设计目标（评测目标行为），不是数据缺陷。

## 7. 已知局限（WARN 明细）

1. Hallucination/PromptInjection/MemoryInconsistency 难度全部 hard——类别本质使然（均为对抗陷阱），未硬造 easy 变体。
2. tracking_no/delivered_at 未作为必需事实键（合同定义为可选附加事实）；相关陷阱（假运单号采用、脏 delivered_at）以 groundedness 禁值断言覆盖。
3. 中文合成语料，模板池约 60 句 + 后缀变体；12-gram 级最长 8 条共享公共礼貌语，无语义级模板集中。
4. 豁免清单 8 条为刻意同形（填充/空白/分隔符陷阱），已在 `norm_dup_allowed.json` 中显式登记可审计。

## 8. 复现命令

```bash
python data_factory/generate_round1.py     # 生成 500 条 → datasets/expansion/round_001.jsonl
python data_factory/validate_round1.py     # QA 校验（exit 0 = 全绿）
python -m pytest -q                        # 原基线 93 tests（确认 v1 未受影响）
```

## 9. runner 接入结果（2026-09-14 完成）

本数据集已接入 runner 自动评测，采用**双格式并存**方案，v1 冻结合同零改动：

- `order_eval/schemas.py`：新增 `V2_CASE_SCHEMA`（12 字段 + 15 类别 + 19 词禁词表），`load_cases` 按行内 `tool_state` 字段自动分派 v1/v2 校验。
- `order_eval/tools.py`：`build_world_from_state()` 从 case 内嵌 `tool_state` 构造工具世界（深复制、故障计数归零），与 fixture 路径语义等价。
- `order_eval/runner.py`：`normalize_case()` 幂等映射（`user_input→input`、`expected_tool→allowed_tools`、`expected_args→required_calls`，其余 evaluator 字段两版同名同构）；`run_trial` 按格式分派世界来源（v2 的 `fixtures_hash=None`，可比性由 dataset_hash 承担）；`run_suite` 对多轮/记忆类跳过并报告；`--replay` 同步适配。

**实测（命令均有 exit code 记录于 IMPLEMENTATION_REPORT.md 扩展节）**：

| 检查 | 结果 |
| --- | --- |
| 全量运行 | planned=430 / PASS=430 / FAIL=0 / ERROR=0（run-20260913T162957Z） |
| 跳过 | 70 条（MultiTurnContext 40 + MemoryInconsistency 30，原因 `AGENT_NO_SESSION_STATE`——MockAgent 无会话状态，是能力边界记录，非通过） |
| v1 回归 | 28/28 PASS，pytest 112 passed（93 原有 + 19 新增 tests/test_expansion_v2.py） |
| 确定性 | `--check-determinism 2` identical=True |
| baseline | 与 v1 跨 dataset_hash 天然 NOT_COMPARABLE（符合设计）；本 run 可作为 expansion 数据集自身的 baseline 存档 |

**缺陷闭环（详见 BUGFIX_LOG.md B10/B11）**：首次全量运行 run-20260913T162730Z 为 423/430，7 个 FAIL 全部归因——6 条为 MockAgent 真实缺陷（脏 eta 原样写入输出，违反 AgentOutput eta pattern；评测器发现，B10 修复 mock-0.2），1 条为本生成器缺陷（PIN-002 的 eta_ask 误按 note 文本而非用户输入判定，B11 修复后重新生成）。两处修复后 430/430。
