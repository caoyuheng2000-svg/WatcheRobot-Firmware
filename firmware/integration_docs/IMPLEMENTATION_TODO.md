# v2.0.0 下一阶段 TODO

> 目的：只记录当前仍未完成、会影响重新合入或后续联调的工作。

## 合并前必须完成

- `TODO-M001` 保持格式门禁通过
  - `git diff --check 5929987..HEAD`
  - CI 范围 C/H 文件必须通过 `clang-format --dry-run --Werror`
- `TODO-M002` 保持基础自动化通过
  - `python -m pytest tools\tests`
  - ESP32 `idf.py build` 通过
- `TODO-M003` 重新合入流程复核
  - 由于 `main` 已经 merge 后又 revert，重新合入需要使用 revert-of-revert 或等价新提交。
  - 合入后必须再次跑同一套检查。
- `TODO-M004` 文档状态一致
  - 当前状态只维护在 `IMPLEMENTATION_STATUS.md`。
  - bench 流程只维护在 `HIL_TEST_PLAN.md`。

## 下一阶段功能工作

### TODO-007：正式 baseline restore

目标：

- 替换当前 app 层 safe-default baseline helper。
- 明确冷启动和恢复时的基线来源。

最低验收：

- `READY` 的进入条件和协议/架构文档一致。
- `snapshot` capability 存在和不存在时都有清晰路径。
- STM32 复位后 ESP32 能重新恢复到可控状态。

### TODO-008：service 级观测闭环

目标：

- bring-up 期间可以从 ESP32 日志判断卡在 link、service 还是上层适配。

最低验收：

- motion / led / sensor 至少各有 1 条 accepted / rejected / done / fault 或状态摘要。
- `ack_timeout_count / reconnect_count / motion_done_fault_count / dropped_state_count` 可读。

### TODO-009：上层业务入口切换

目标：

- `control_ingress / behavior_state_service / BLE / WS` 消费协处理器返回语义。

最低验收：

- 手动控制和行为动作不再依赖本地舵机同步完成语义。
- 外部 BLE / WS 协议保持兼容。
- `busy / not_ready / fault / timeout` 有稳定错误映射。

### TODO-010：真实 STM32 UART 闭环联调

目标：

- 从 mock 和 build 验证推进到真实 ESP32 + STM32 bench 验证。

最低验收：

- 真实 UART 链路稳定握手。
- motion / led / sensor 至少各跑通 1 条真实闭环。
- POWER 5V 用例按硬件判据验证。

## 非目标

- STM32 固件升级协议
- STM32 端完整外设驱动实现
- BLE / WS 对外协议改版
- camera 协处理器接入
