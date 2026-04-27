# v2.0.0 当前实现状态

> 目的：记录 `v2.0.0-refactor` 的实际代码状态、验证结果和主分支合入状态。

## 状态快照

- 日期：`2026-04-28`
- 集成分支：`v2.0.0-refactor`
- 当前分支头：`77f68a1 style: fix v2 integration doc whitespace`
- 主分支状态：`main` 已通过 `e048fff` 撤回 `f7cab6a merge: integrate ESP32 v2.0.0 refactor`
- 当前判断：ESP32 侧 V2 协处理器重构可以编译通过，但需要完成文档收口和合并流程复核后再重新合入主分支。

## 已落地能力

- `mcu_link`
  - 已实现 `CRC16 / COBS / frame / wire / FSM / stats` 基础能力。
  - 已接入 UART transport、`HELLO_REQ` bootstrap、poll 驱动和最小双向事件消费。
  - 已能处理 `HELLO_RSP / ACK / NACK / FAULT / MOTION_DONE / LED_DONE / TOUCH_EVENT / MAG_STATE / IMU_STATE`。
- `hal_servo`
  - 已收缩为协处理器兼容入口和参数校验层。
  - 本地 PWM task / LEDC 后端已移除。
  - `GPIO19/20` 已让位给 `mcu_link` 运行时 UART。
- `mcu_motion_service` / `mcu_led_service`
  - 链路未就绪时返回显式错误，不再把未发送请求当作 accepted。
  - 已能消费 `ACK / NACK / FAULT / DONE` 类运行时事件。
- `mcu_sensor_service`
  - 已建立 `touch / mag / imu` 缓存和 `latest-state-wins` 状态更新策略。
- `mcu_power_service`
  - 已加入 `POWER_5V_ENABLE / POWER_5V_DISABLE` 协议下发路径。
  - POWER disable 的判据是 STM32 侧舵机 / WS2812 LED 5V rail 或 IP5306 输出端变化；ESP32 由 USB-C 供电，日志串口继续在线是预期现象。
- 工具与测试
  - 已有 `tools/stm32_uart_hil.py`
  - 已有 `tools/stm32_uart_fault_inject.py`
  - 已有 `tools/power_5v_toggle_hil.py`
  - 已有 Python 工具测试覆盖主要 HIL 脚本。

## 最新本地验证

以下检查已在 `D:\GithubRep\WatcheRobot-Firmware` 的 `v2.0.0-refactor` 上通过：

- `git diff --check 5929987..HEAD`
- Visual Studio LLVM `clang-format.exe --dry-run --Werror`，覆盖 `firmware/s3/components` 和 `firmware/s3/main` 下本分支改动的 43 个 C/H 文件
- `python -m pytest tools\tests`
  - 结果：`8 passed`
- ESP32 编译：
  - 命令：`powershell -ExecutionPolicy Bypass -File C:\Users\50533\.codex\skills\watche-dual-mcu-bringup\scripts\run-dual-mcu-bringup.ps1 -SkipStm32Build -SkipStm32Flash -SkipEsp32Flash -SkipSession`
  - IDF：`C:\Espressif\frameworks\esp-idf-v5.2.1`
  - build dir：`firmware\s3\build-s3-c-codex`
  - 结果：`Project build complete`

## 已知限制

- 本次检查没有刷写 ESP32，也没有重新跑 10 分钟双 MCU HIL。
- `HELLO_RSP -> READY` 当前仍使用 app 层 safe-default baseline helper，正式 baseline restore 仍是下一阶段工作。
- `control_ingress / behavior_state_service / BLE / WS` 尚未全部切换到完整协处理器返回语义。
- `IMU_STATE` 不作为当前标准压力场景常开状态流，只在问询或姿态变化事件场景单独验证。

## 重新合入注意事项

`main` 已经包含：

- `f7cab6a merge: integrate ESP32 v2.0.0 refactor`
- `e048fff Revert "merge: integrate ESP32 v2.0.0 refactor"`

因此后续重新合入不能依赖普通 merge 自动带回同一批内容。推荐流程：

1. 确认 `v2.0.0-refactor` 已通过 `HIL_TEST_PLAN.md` 的合并前检查。
2. 在 `main` 上恢复合入时，使用 revert-of-revert 或等价的新提交重新引入内容。
3. 合入后再次运行格式检查、Python 测试和 ESP32 build。
4. 检查通过后再推送 `origin/main`。
