B10 缺陷闭环证据（MockAgent 脏 eta 写入输出，mock-0.1→mock-0.2）
修复前 run-20260913T162730Z：430 可执行 / 423 PASS / 7 FAIL（6×output_format/OF-SCHEMA 脏 eta + 1×B11 生成器缺陷）
修复后 run-20260913T162957Z：430/430 PASS；v1 28/28 无回归；pytest 112 passed；determinism 2× identical
