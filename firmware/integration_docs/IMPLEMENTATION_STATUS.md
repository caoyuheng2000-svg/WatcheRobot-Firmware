# v2.0.0 当前实现状态

> 目的：记录 `v2.0.0-refactor` 当前已经实际落地到哪一步，避免把“文档已冻结”和“代码已实现”混为一谈。

## 1. 状态快照

- 日期：`2026-04-15`
- 集成分支：`v2.0.0-refactor`
- 当前阶段：`ESP32 链路骨架已落地，动作链路开始接入`
- 当前板级串口：`COM28`

## 2. 已完成

### 2.1 文档基线

以下文档已冻结并作为当前实现依据：

- [STM32_COPROC_REFACTOR_PLAN.md](./STM32_COPROC_REFACTOR_PLAN.md)
- [STM32_UART_PROTOCOL.md](./STM32_UART_PROTOCOL.md)
- [TDD_EXECUTION_PLAN.md](./TDD_EXECUTION_PLAN.md)
- [RISK_REGISTER.md](./RISK_REGISTER.md)
- [HIL_TEST_PLAN.md](./HIL_TEST_PLAN.md)
- [BRANCH_WORKTREE_PLAN.md](./BRANCH_WORKTREE_PLAN.md)

### 2.2 关键实现提交

当前阶段的关键实现提交包括：

- `5fccecc`
  - 稳定 ESP32 音频路径并恢复板级启动 smoke
- `9af402d`
  - 增加 `mcu_link` 可配置 UART scaffold
- `8b134c6`
  - 增加 `mcu_link` 的 `HELLO_REQ` bootstrap runtime path
- `e4a650a`
  - `mcu_motion_service` 在 `mcu_link` ready 时镜像下发 `SERVO_MOVE / SERVO_STOP`

### 2.3 ESP32 已落地内容

- `mcu_link`
  - 已有 `CRC16 / COBS / frame / wire / FSM / stats` 骨架
  - 已有最小 UART transport scaffold
  - 已有 `HELLO_REQ` bootstrap 发送路径
- `mcu_motion_service`
  - 已从“仅缓存请求”推进到“链路进入 `link_ready` 时镜像下发 `SERVO_MOVE / SERVO_STOP`”
- `hal_servo`
  - 当前仍保留本地 PWM 后端
  - 当前仍保留兼容桥接路径，未切掉本地舵机控制
- Mock HIL 工具
  - 已有 `tools/stm32_uart_hil.py`
  - 已有 `tools/stm32_uart_fault_inject.py`

### 2.4 已验证

以下检查在当前代码上已通过：

- `idf.py -B build-v2-refactor build`
- `python tools/stm32_uart_hil.py --all-scenarios --transport mock`
- `COM28` 刷写成功
- `COM28` 启动 smoke 成功

关键板级日志样本：

- [monitor-com28-20260415-153042.log](</D:/GithubRep/WatcheRobot-Firmware/firmware/s3/build-v2-refactor/monitor-com28-20260415-153042.log>)

该日志确认：

- 存在 `MCU link scaffold ready`
- 存在 `after_ui_init`
- 存在 `WatcheRobot ready`
- 未发现 `panic`
- 未发现 `Guru Meditation`
- 未发现 `i2s_channel_disable`

## 3. 当前未完成

以下项目仍未进入“已实现”状态：

- `GPIO19/20` 尚未切到 STM32 运行时 UART
- 本地 `hal_servo` PWM 后端尚未移除
- `mcu_link` 尚未接入 RX、解帧与 `HELLO_RSP / ACK / FAULT` 处理
- `mcu_led_service` 尚未实际构帧下发
- `mcu_sensor_service` 尚未接入 STM32 上行缓存与 `latest-state-wins`
- `BLE / WS / control_ingress / behavior_state_service` 仍未完成全链路切换
- STM32 实机闭环联调尚未开始

## 4. 当前阶段判断

结合 [TDD_EXECUTION_PLAN.md](./TDD_EXECUTION_PLAN.md)，当前更准确的阶段判断是：

- 阶段 1：协议合同层，已完成
- 阶段 2：链路状态机层，已完成文档与骨架实现
- 阶段 3：动作与灯效服务层，动作部分已开始接入
- 阶段 4：ESP32 适配层，尚未真正切换到协处理器后端
- 阶段 5~7：尚未开始

因此当前不应宣称“协处理器链路已完成”，只能宣称：

- `mcu_link` 发送侧骨架已落地
- `mcu_motion_service` 已具备运行时镜像下发能力
- 现有板级功能未被破坏

## 5. 下一阶段入口

下一阶段不直接落实现，先以待办冻结为准：

- [IMPLEMENTATION_TODO.md](./IMPLEMENTATION_TODO.md)
