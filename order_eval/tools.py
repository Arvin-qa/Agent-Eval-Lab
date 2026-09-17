"""两个 FixtureTools、受控执行器、故障注入与尝试记录（PROJECT_SPEC §3.2/§3.3）。

执行器负责：allowlist 校验、参数 schema 校验、物流前置条件、仅 TIMEOUT 重试一次、
总尝试预算；绝不动态 eval 工具名。每次 trial 构建独立 ToolWorld（深复制、计数归零）。
"""
import copy
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from jsonschema import Draft202012Validator

from order_eval.schemas import (
    ARGUMENT_SCHEMA_ERROR,
    BUDGET_EXCEEDED,
    INVALID_TOOL_RESULT,
    MAX_TOOL_ATTEMPTS,
    ORDER_STATUSES,
    PRECONDITION_FAILED,
    SHIPMENT_STATUSES,
    TIMEOUT,
    TIMEOUT_MAX_RETRIES,
    TOOL_ERROR,
    TOOL_SPECS,
    UNKNOWN_TOOL,
)


# ---------------------------------------------------------------- 工具世界

@dataclass
class ToolWorld:
    snapshot_id: str
    orders: dict
    shipments: dict
    faults: dict                      # tool -> 故障序列，如 ["timeout","timeout"]
    fault_idx: dict = field(default_factory=dict)
    total_attempts: int = 0           # 含被拒绝的请求（§3.3）


def _apply_mutation(world: ToolWorld, key: str, value) -> None:
    """mutation 键格式：`orders:ORD-1001.status` 或 `shipments:ORD-1002.eta`。"""
    container_name, path = key.split(":", 1)
    container = world.orders if container_name == "orders" else world.shipments
    parts = path.split(".")
    target = container
    for p in parts[:-1]:
        target = target[p]
    target[parts[-1]] = value


def load_fixture_world(fixtures_path: str, fixture_id: str) -> ToolWorld:
    with open(fixtures_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    registry = data["fixture_registry"]
    if fixture_id not in registry:
        raise KeyError(f"fixture_registry 中不存在 fixture_id={fixture_id}")
    entry = registry[fixture_id]
    world = ToolWorld(
        snapshot_id=data["snapshot_id"],
        orders=copy.deepcopy(data["orders"]),
        shipments=copy.deepcopy(data["shipments"]),
        faults=copy.deepcopy(entry.get("faults") or {}),
    )
    world.fault_idx = {tool: 0 for tool in world.faults}
    for key, value in (entry.get("mutations") or {}).items():
        _apply_mutation(world, key, value)
    return world


def build_world_from_state(state: dict) -> ToolWorld:
    """v2 expansion case 的内嵌工具世界：订单/物流/故障自包含，深复制隔离每次 trial。"""
    world = ToolWorld(
        snapshot_id=state.get("snapshot_id") or "expansion",
        orders=copy.deepcopy(state.get("orders") or {}),
        shipments=copy.deepcopy(state.get("shipments") or {}),
        faults=copy.deepcopy(state.get("faults") or {}),
    )
    world.fault_idx = {tool: 0 for tool in world.faults}
    return world


# ---------------------------------------------------------------- 结果校验

_ORDER_VALIDATORS = {t: Draft202012Validator(spec["args_schema"]) for t, spec in TOOL_SPECS.items()}


def validate_tool_data(tool_name: str, order_id: str, data: dict) -> Optional[str]:
    """成功数据的结构/枚举/订单号校验（§3.2）；返回错误码或 None。"""
    spec = TOOL_SPECS[tool_name]
    for k in spec["data_required"]:
        if k not in data:
            return INVALID_TOOL_RESULT
    if data["order_id"] != order_id:
        return INVALID_TOOL_RESULT
    if tool_name == "get_order":
        if data["status"] not in ORDER_STATUSES:
            return INVALID_TOOL_RESULT
    else:
        if data["status"] not in SHIPMENT_STATUSES:
            return INVALID_TOOL_RESULT
    return None


def _envelope(ok: bool, data, error_code: Optional[str], retryable: bool,
              source_id: str, snapshot_id: str) -> dict:
    return {
        "ok": ok,
        "data": data,
        "error": {"code": error_code, "retryable": retryable} if error_code else None,
        "source_id": source_id,
        "snapshot_id": snapshot_id,
    }


# ---------------------------------------------------------------- 受控执行器

@dataclass
class RequestOutcome:
    call_id: str
    tool: str
    arguments_raw: object
    tool_arguments: Optional[dict]
    validation_result: str          # "ok" = 已执行；否则为拒绝码
    tool_result: Optional[dict]     # 有效 envelope；拒绝时 None
    error_code: Optional[str]
    attempts: list = field(default_factory=list)  # 每次 attempt 一条记录


class Executor:
    """一个 trial 一个实例；记录所有逻辑请求与每次尝试。"""

    def __init__(self, world: ToolWorld):
        self.world = world
        self.aborted = False
        self._request_seq = 0
        self._successful_orders: set = set()
        self.requests: list = []  # 本 trial 全部逻辑请求（Runner 展平进 Trace）

    # -- 内部：登记一次尝试（被拒绝的请求同样占用预算）--
    def _attempt(self, attempts, validation_result, tool_result_raw, tool_result, error_code, started):
        attempts.append({
            "attempt_index": len(attempts) + 1,
            "validation_result": validation_result,
            "tool_result_raw": tool_result_raw,
            "tool_result": tool_result,
            "error_code": error_code,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        })
        self.world.total_attempts += 1

    def execute(self, tool_name: str, arguments_raw) -> RequestOutcome:
        self._request_seq += 1
        outcome = RequestOutcome(
            call_id=f"call-{self._request_seq}", tool=tool_name,
            arguments_raw=arguments_raw, tool_arguments=None,
            validation_result="ok", tool_result=None, error_code=None,
        )
        attempts = outcome.attempts
        self.requests.append(outcome)

        # 1) 总预算：第 5 次尝试请求直接拒绝并终止（不执行、不消耗）
        if self.world.total_attempts >= MAX_TOOL_ATTEMPTS:
            self.aborted = True
            outcome.validation_result = BUDGET_EXCEEDED
            outcome.error_code = BUDGET_EXCEEDED
            attempts.append({
                "attempt_index": len(attempts) + 1,
                "validation_result": BUDGET_EXCEEDED,
                "tool_result_raw": None, "tool_result": None,
                "error_code": BUDGET_EXCEEDED, "duration_ms": 0,
            })
            return outcome

        # 2) 注册表 allowlist（禁止动态执行工具名）
        if tool_name not in TOOL_SPECS:
            self._attempt(attempts, UNKNOWN_TOOL, None, None, UNKNOWN_TOOL, time.perf_counter())
            outcome.validation_result = UNKNOWN_TOOL
            outcome.error_code = UNKNOWN_TOOL
            return outcome

        # 3) 参数 schema 校验：缺参/错类型/多余参数一律拒绝并保留原始请求
        arg_errors = list(_ORDER_VALIDATORS[tool_name].iter_errors(arguments_raw))
        if arg_errors:
            self._attempt(attempts, ARGUMENT_SCHEMA_ERROR, None, None, ARGUMENT_SCHEMA_ERROR, time.perf_counter())
            outcome.validation_result = ARGUMENT_SCHEMA_ERROR
            outcome.error_code = ARGUMENT_SCHEMA_ERROR
            return outcome
        outcome.tool_arguments = copy.deepcopy(arguments_raw)
        order_id = arguments_raw["order_id"]

        # 4) 物流前置条件：须有同 trial 内成功的 get_order（执行器保护）
        if tool_name == "get_shipment" and order_id not in self._successful_orders:
            self._attempt(attempts, PRECONDITION_FAILED, None, None, PRECONDITION_FAILED, time.perf_counter())
            outcome.validation_result = PRECONDITION_FAILED
            outcome.error_code = PRECONDITION_FAILED
            return outcome

        # 5) 执行 + 故障注入；仅 TIMEOUT 可重试一次（§3.3）
        fault_seq = self.world.faults.get(tool_name, [])
        request_attempts = 0
        while True:
            if self.world.total_attempts >= MAX_TOOL_ATTEMPTS:
                self.aborted = True
                outcome.validation_result = BUDGET_EXCEEDED
                outcome.error_code = BUDGET_EXCEEDED
                return outcome
            idx = self.world.fault_idx.get(tool_name, 0)
            fault = fault_seq[idx] if idx < len(fault_seq) else "ok"
            self.world.fault_idx[tool_name] = idx + 1
            request_attempts += 1
            started = time.perf_counter()

            if fault == "timeout":
                env = _envelope(False, None, TIMEOUT, True, "", self.world.snapshot_id)
                self._attempt(attempts, "ok", env, env, TIMEOUT, started)
                outcome.tool_result, outcome.error_code = env, TIMEOUT
                if request_attempts <= TIMEOUT_MAX_RETRIES:
                    continue  # 同工具同参数重试一次
                return outcome
            if fault == "error":
                env = _envelope(False, None, TOOL_ERROR, False, "", self.world.snapshot_id)
                self._attempt(attempts, "ok", env, env, TOOL_ERROR, started)
                outcome.tool_result, outcome.error_code = env, TOOL_ERROR
                return outcome

            # 正常执行：查本地 Fixture 数据
            lookup = self.world.orders if tool_name == "get_order" else self.world.shipments
            data = copy.deepcopy(lookup.get(order_id))
            prefix = TOOL_SPECS[tool_name]["source_id_prefix"]
            raw = _envelope(True, data, None, False, f"{prefix}:{order_id}", self.world.snapshot_id)
            if data is not None:
                bad_code = validate_tool_data(tool_name, order_id, data)
                if bad_code:
                    eff = _envelope(False, None, bad_code, False, raw["source_id"], self.world.snapshot_id)
                    self._attempt(attempts, "ok", raw, eff, bad_code, started)
                    outcome.tool_result, outcome.error_code = eff, bad_code
                    return outcome
            self._attempt(attempts, "ok", raw, raw, None, started)
            outcome.tool_result = raw
            outcome.error_code = None  # 重试成功必须清除先前尝试的 TIMEOUT，不得残留（B8）
            if tool_name == "get_order" and data is not None:
                self._successful_orders.add(order_id)
            return outcome
