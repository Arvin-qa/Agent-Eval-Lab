# Agent Eval Lab — 发布差距与最小发布清单

日期：2026-09-16。审查基线：`123d9f75a1c95d8bb9701f7da2972984a5508e13`。

**决策：演示能力已有，当前不直接发布；第二阶段只处理下面 5 个 P0。** 本文件是待确认的实施范围，本阶段没有实施修复。

依据：[CURRENT_STATE.md](CURRENT_STATE.md)、[本次验证摘要](docs/evidence/release_audit_20260916.json)。优先级按评测结果可信度、用户能否完成闭环、证据是否保留来定，不按代码规模定。

## 1. P0 必修问题（最多 5 项）

### P0-1：发布入口与实际能力不一致

**已验证问题**：README 首尾残留“6 条”“28 条尚未实现”“replay/baseline 未实现”；遗漏 `report.json` 并错误描述 Markdown 数据源；没有 clone 地址、明确 `cd`、完整 Demo、实际结果示例或 Astra 参与记录。CLI baseline 帮助写 `RUN_DIR_OR_REPORT`，实际只支持目录。本机默认 GBK 输出运行 QA 会因 `✓` 崩溃，`-X utf8` 已验证可用。

**最小处理**：仅改 README 和相应帮助文案，统一名称/定位/已验证数字，明确从仓库根目录运行、无 API Key、固定样本、仅 offline；Windows 使用虚拟环境解释器与 `-X utf8`，避免修改系统设置。基线使用现有目录语义，不为适配旧文案新增输入形式。记录 Astra 本轮实际参与；补真实公开仓库链接须等用户确认发布位置。

**验收**：新访客能找到全部 10 个 README 部分；每条命令在新 clone 中可复制执行；第一屏解释输入→调用→六维结果；声明与代码/报告逐项对应；不存在“模型准确率”或运行时 Astra 的误导。

### P0-2：评测器没有验证原始输出与 Trace 内部完整性

**最小复现**：取正常 N01 Trace，只把 `agent_output_raw` 改为 `THIS IS NOT JSON`，保留 `agent_output`。`evaluate()` 六维全 PASS，CLI replay 仍 MATCH/exit 0。另将 `tool_calls` 改成 `[{}]`，replay 抛 `KeyError: selected_tool`。

**根因位置**：`order_eval/evaluator.py:49` 仅检查顶层字段及 tool_calls 为 list；`:71` 只检查 raw 非空及 parsed 为 dict；后续直接下标访问工具条目。`order_eval/runner.py:473` 重评调用没有逐条异常收敛。

**最小处理**：验证 raw 可解析、与 parsed 对象语义一致；验证评分所需的 Trace/工具记录字段和类型。损坏记录明确记 ERROR 或按明确格式错误规则记 FAIL，不能 PASS；一条损坏不让其他可评记录消失。规则改变需更新 evaluator 版本和相应证据，旧新版本比较应 NOT_COMPARABLE。

**验收**：非 JSON raw、raw/parsed 不一致、缺字段/错类型 Trace 均有可读错误；正常 N01/N02 仍通过；“值对但引用假”仍为 groundedness FAIL；现有构造反例若 raw 与对象不同步，应修正反例构造，不放松完整性检查。新增针对这些真实缺陷的回归测试。

### P0-3：无有效评测和文件异常的退出语义不可靠

**已验证问题**：空 dataset、空 replay、全部跳过均 exit 0；缺 fixtures、缺 replay 文件、输出位置是文件时均 traceback/exit 1，与公布的基础设施 ERROR=2 冲突。正常错误降级 T02 是 PASS，不能与这些基础设施失败混淆。

**根因位置**：`order_eval/runner.py:195` 只看 fail/error 数，零执行会成功；Fixture 加载在 `run_trial` 的 try 之外；`run_eval.py` 只保护了部分加载步骤，未统一处理 replay/运行/写入错误。

**最小处理**：为零有效 trial 建立显式非成功结果；在现有 CLI/Runner 边界处理可预期配置、数据和 I/O 错误。能写报告时保留已完成结果和 ERROR；连输出目录都不能写时，stderr 明确原因并 exit 2。保留 T02 等合同内降级为 PASS 的逻辑，不进行架构重构。

**验收**：缺文件、损坏数据、不可写输出、零执行路径不冒充通过；默认 28 条及 v2 430 执行/70 跳过仍可正常通过；全跳过显式非成功；声明的 0/1/2 语义与实测一致。

### P0-4：`--repeat` 承诺的试验数和多 trial 回归不存在

**已验证问题**：`--case N02 --repeat 2` 只执行 1 trial，并与 repeat=1 baseline 显示可比、无回归。构造同 case 两次 trial，仅第二次退化，`compare_runs` 漏报。

**根因位置**：`run_eval.py:171` 将 repeat 存入 config；`order_eval/runner.py:315` 只枚举 executable case 一次；`trial_index` 实际是用例遍历序号；`:622` 和 `:632` 只比较每个 case 的 `[0]`。仅补循环还会引入分数分母和 baseline 问题，不能做半修复。

**推荐的最小处理**：本次公开版本限定单 trial，明确拒绝 `--repeat > 1`，帮助说明当前限制，并拒绝把含重复 trial 的历史 baseline 当作支持的比较输入；修正单 trial 的序号含义。保留现有独立且已验证的 `--check-determinism 3`。

这不删掉真实已有能力，因为 repeat>1 目前并未实现。完整重复采样、分母与逐 trial 统计放到发布后，避免两天内扩大实现范围。

**验收**：`--repeat 1` 正常；`--repeat 2` 清楚拒绝并 exit 2，不静默少跑；重复 trial baseline 不得报告“无回归”；三次确定性检查仍真实执行三次。

### P0-5：秒级运行 ID 会覆盖已有证据

**最小复现**：两个独立 CLI 同时跑 N01 和 N02，使用同一个 `--out`。本次两者都生成 `run-20260916T065102Z`，都 exit 0，最后只有 N01 Trace，N02 证据丢失。

**根因位置**：`order_eval/runner.py:306`、`:492` 和 `run_eval.py:146` 用秒级时间命名；`write_artifacts` 使用 `exist_ok=True`，后续无条件写入同名文件。Replay/确定性报告也使用秒级目录，需要一并检查。

**最小处理**：运行目录使用更强的唯一标识并以独占方式创建；遇到已有目录明确拒绝或分配新 ID，不覆盖旧文件。无需数据库、锁服务或新依赖。

**验收**：同一输出根目录快速/并发启动两次，两个 run 均完整保留；四件产物各自一致；显式复用已有 run_id 不可静默覆盖；baseline 原件不变。

## 2. P1 可选优化（最多 5 项；不阻塞本次窄范围发布）

| 项目 | 可以做的最小改善 | 不做什么 |
| --- | --- | --- |
| P1-1 报告阅读体验 | 失败项直接展示 expected/actual、Trace 位置和一句理由 | 不做仪表盘、数据库或 Web 服务 |
| P1-2 能力覆盖展示 | CLI/报告顶部显示 dataset/executed/skipped；列出未运行的 Judge/扩展规则 | 不实现多轮、记忆或 LLM Judge；限制文案属 P0 必须准确 |
| P1-3 环境复现 | 保存传递依赖快照，按实际可用环境补一个平台验证或轻量 CI | 不承诺所有 Python/OS，不升级技术栈 |
| P1-4 英文材料与截图 | 在准确第一屏之外补更完整英文 README、1–2 张真实结果截图 | 不建新前端，不编造效果或用户数据 |
| P1-5 历史证据索引 | 标明旧计划/面试稿为历史；索引 T01 和 B10；完整 baseline 与摘要分开标注 | 不改写历史贡献，不伪造缺失 Trace，不重新扩数据 |

## 3. 建议 README 的最小结构

| 部分 | 应写的真实内容 | 对应验证 |
| --- | --- | --- |
| Problem | 答案值正确仍可能没有可靠依据，失败处理也属于任务合同 | E08 反例、T02 |
| What it does | 订单场景离线 Mock、工具 Trace、六维规则、重放和比较 | 本次正常 smoke |
| Architecture | 用例/工具世界 → MockAgent → Trace → Evaluator → 报告；期望不传给 Agent | 模块、接口、防泄漏测试 |
| Quick Start | clone、cd、venv、安装、运行；Windows 直接解释器；无 Key | 新克隆已验证安装，远程链接待发布 |
| Demo | 下节约 4 分钟步骤 | N02/T02、T01 历史前后记录 |
| Evaluation dimensions | 六维检查、N/A、PASS/FAIL/ERROR 含义 | evaluator 与报告 |
| Example result | 28/28 与一个真实 FAIL 理由；500 中执行 430/跳过 70 | 当前结果及历史 T01 |
| Test | `python -X utf8 -m pytest -q`；本次 112 passed；补修后更新真实数字 | 全量测试日志 |
| Limitations | Mock、中文关键词、合成样本、非通用适配、Judge 未执行、上下文跳过 | agent/runner/schema |
| Built with GPT-6 Astra | 链接构建日志，明确本次审查/之后实际修复，不追认旧代码 | 本次任务元数据及未来实际 diff |

## 4. 推荐 Demo Flow：约 4 分钟

**前提**：已经完成 clone/安装，打开仓库根目录和文本编辑器。安装下载时间取决于网络，不计入“3–5 分钟 Demo”承诺。本次测试全套约 88 秒，扩展评测约 43 秒，均不应占用主 Demo 时间。

| 时间 | 操作 | 观众应理解什么 |
| --- | --- | --- |
| 0:00–0:30 | 读定位，展示 N02 的真实输入“查 ORD-1002 物流状态和预计到货时间” | 本地合成订单查询；输入不只是任意聊天 |
| 0:30–1:15 | 执行 N02 + T02 subset，打开本次 `report.md` 和 `traces.jsonl` | N02 先订单后物流；T02 两次超时后 unavailable 仍 PASS |
| 1:15–2:00 | 展示 N02 的事实、call_id 和 `/data/eta`，指向工具返回值 | 证据来自实际记录，六维独立，不只核对最后一句话 |
| 2:00–3:00 | 对存档 T01 的失败/修复 Trace 重新评分，展示 TS-STATUS 的 expected/actual | 历史真实缺陷：重试成功仍误降级；前后 FAIL→PASS。明确是历史记录重评 |
| 3:00–3:40 | 跑默认 28 条，再对保存 Trace 执行 replay | 全套可重复执行；replay 是重新评分，不是重新调用 Agent |
| 3:40–4:10 | 展示“正确事实 + 假引用”的已验证反例结果及限制 | `task_success=PASS`、`groundedness=FAIL`；当前不证明模型能力 |

安装后、仓库根目录中的示例命令（`python` 指本项目虚拟环境；Windows 可替换为 `.\.venv\Scripts\python.exe`）：

```powershell
python -X utf8 run_eval.py --mode offline --case N02 --case T02 --out artifacts/demo-scenes
python -X utf8 run_eval.py --mode offline --out artifacts/demo-full
```

从第二条输出复制实际生成的目录名，再执行下面模板；`<实际run_id>` 必须替换，不能原样运行：

```text
python -X utf8 run_eval.py --replay artifacts/demo-full/<实际run_id>/traces.jsonl --out artifacts/demo-replay
```

每次打开当前命令刚打印的目录，避免误展示旧报告；P0-5 完成前不要并发写同一输出目录。

T01 历史前后重新评分命令（本次已执行成功，不需要新增产品功能）：

```powershell
python -X utf8 -c "import json; from pathlib import Path; from order_eval.schemas import load_cases; from order_eval.evaluator import evaluate; c=next(c for c in load_cases('datasets/cases.jsonl') if c['case_id']=='T01'); paths=sorted(Path('docs/evidence/t01_timeout_retry_defect').glob('trace_*_T01.json')); es=[(p.name,evaluate(c,json.loads(p.read_text(encoding='utf-8')))) for p in paths]; print(json.dumps([{'trace':n,'overall':e['overall'],'dimensions':{k:v['status'] for k,v in e['dimensions'].items()},'failure_reasons':e['failure_reasons']} for n,e in es],ensure_ascii=False,indent=2))"
```

预期可读结果：

```text
trace_FAIL_T01.json   FAIL
TS-STATUS: expected='answered' actual='unavailable'
trace_FIXED_T01.json  PASS
```

这条命令只读取旧记录并评分，不切换 Git 历史、不重新注入旧代码、不声称本次修复了 B8。评测器版本变化后需重新核验该演示。

“正确事实 + 假引用”的现有测试入口：

```powershell
python -X utf8 -m pytest tests/test_evaluator.py::TestBadTracesFail::test_e08_task_success_still_passes -q
```

该测试 PASS 表示它成功断言了坏 Trace 的 groundedness FAIL；不能把测试通过误说成坏 Trace 通过。演示时同时展示评估 JSON 中这两个维度。

## 5. Product Hunt 发布前 checklist

### 仓库与可用性

- [x] 仓库扫描、干净本地 clone 和全新 venv 安装。
- [x] 当前基线 112 项测试、28 条默认评测、430 条扩展评测、重放及三次确定性验证。
- [x] T01 历史失败/修复证据可重新评分；普通 FAIL 路径能落盘。
- [ ] 完成 P0-1～P0-5，并为真实缺陷补针对性回归测试。
- [ ] 对最终发布 commit 重新执行全量门禁，记录实际测试数、退出码、散列、工作区状态。
- [ ] 保存一套完整、匹配版本的精选 Trace/报告，不只保存 report 摘要；确保不会被 artifacts 忽略规则意外排除。
- [ ] 准备公开可访问仓库/下载地址，从访客环境验证 clone → 安装 → 运行 → 查看报告。
- [ ] 用户选择许可方式；当前没有 LICENSE，不在本次审查中替用户添加授权声明。
- [ ] 检查准备公开的文件和发布 diff 中无凭据、真实客户数据或不必要的本机路径。当前源码检索未发现常见 Key/环境变量读取，不等于通用秘密扫描保证。

### 产品展示

- [ ] README 具备上列 10 部分，首屏 30 秒内说明是什么/输入/过程/输出/价值。
- [ ] 产品名称、简短英文介绍、受众与限制一致；不把订单样例宣传为通用 Agent 平台。
- [ ] 录制/排练一次 3–5 分钟 Demo，包含 Trace、PASS、FAIL 和具体失败理由。
- [ ] 配真实截图或报告片段；不把 Mock 100% 写成 AI 准确率。
- [ ] 由未参与开发的人或用户本人照 Quick Start 独立完成一次；本次代理验证不代替该体验验收。
- [ ] Astra 构建日志与本次/后续实际改动一致，最终 commit 补真实值。

### 比赛与发布动作

- [x] 已核验官方页面日期与公告要求在 2026-09-18 发布：[比赛页](https://www.producthunt.com/contests/gpt-6-astra-challenge)、[官方公告](https://www.producthunt.com/p/producthunt/product-hunt-teams-up-with-openaidevs-for-the-gpt-6-astra-challenge)。
- [ ] 登录比赛提交入口，核对资格、准确时区、截止时间、Astra 使用证据和项目链接要求。本次指南 404、表单需登录，不能写“已确认符合所有规则”。
- [ ] 在 Product Hunt 安排 2026-09-18 的发布并核对时区；不能直接按本机北京时间猜测。
- [ ] 核验草稿中的产品链接、视频、图片及参赛关联。
- [ ] 用户确认后才进行远程推送、公开仓库、对外发布等操作；本阶段均未执行。
- [ ] 上线当天用访客视角打开发布页和产品链接，确认能访问且版本对应。

## 6. 绝对不要在此次发布前扩展

- 不新增 RAG、MCP、多 Agent、数据库、登录、云部署、Docker 或无必要前端框架。
- 不临时接 Astra/其他 LLM API，不新增模型选择、排行榜、成本看板或 LLM Judge。若官方最终提出明确不同要求，单独评估发布资格与范围，不悄悄加功能。
- 不启动多轮/记忆实现，不继续生成更多数据，不通过删除失败用例或修改标准答案提高分数。
- 不把订单场景重构成通用插件平台；保持两个工具、现有模块和 JSON/JSONL 产物。
- 不改写旧实施计划、旧缺陷证据或既有贡献归属，不大规模重命名。
- 不为发布重新设计 UI、组织系统或增加无法在两天内稳定验证的能力。

## 7. 距离可发布版本还缺什么

**缺的是可信的评测边界、可靠的输出保护、准确的 Quick Start 和一次可独立复现的发布演示。业务主链路已经存在。**

建议第二阶段只完成 5 个 P0，优先顺序：评测完整性 → 错误/零执行语义 → run_id 防覆盖 → 单 trial 边界 → README/Demo。之后冻结代码、重跑门禁，再准备公开材料和确认比赛提交条件。P1 全部可以不做。

本阶段到此停止，等待用户确认第二阶段；本报告中的缺陷仍然存在，不能把审查结果当作修复完成记录。
