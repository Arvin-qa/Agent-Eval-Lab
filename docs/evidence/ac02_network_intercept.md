# AC02 证据：offline 网络拦截实际验证

日期：2026-09-11。环境：Windows 10，Python 3.13.14，pytest 9.0.3。

## 拦截机制

`tests/conftest.py` 对整个 pytest 进程注入 autouse fixture：把 `socket.socket.connect` 与
`socket.create_connection` 替换为直接抛 `AssertionError` 的函数。因此**任何**测试代码
（含 Agent、执行器、评测器、Runner）在默认 `pytest` 下发起外部连接都会立即失败并使测试变红。

## 实际验证结果（2026-09-11 运行）

命令：`python -m pytest tests/test_tools.py::TestOfflineIsolation -v`

```
tests/test_tools.py::TestOfflineIsolation::test_socket_connect_is_blocked_during_pytest PASSED
tests/test_tools.py::TestOfflineIsolation::test_create_connection_is_blocked_during_pytest PASSED
tests/test_tools.py::TestOfflineIsolation::test_full_offline_suite_runs_under_interception PASSED
============================== 3 passed in 1.67s ==============================
```

三条证据的含义：

1. `test_socket_connect_is_blocked_during_pytest`：在测试中直接尝试
   `socket().connect(("example.com", 80))`，被拦截抛出 AssertionError —— 证明拦截真实生效，
   而非摆设。
2. `test_create_connection_is_blocked_during_pytest`：同上，覆盖高层 API
   `socket.create_connection`。
3. `test_full_offline_suite_runs_under_interception`：在拦截生效前提下跑完
   `run_suite`（28 条全量、含工具执行与评测），28/28 PASS —— 证明评测全链路零网络依赖。

全量门禁（同一拦截下）：`python -m pytest` → **93 passed**，exit 0（2026-09-11 实测）。

## 结论

offline 模式（默认 `pytest` 与 `python run_eval.py --mode offline`）在套件级网络拦截下完整运行，
无法发生外部网络请求。满足 AC02「默认 pytest 中拦截网络访问，离线套件仍可执行」。
