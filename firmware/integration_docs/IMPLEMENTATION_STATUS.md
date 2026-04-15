# v2.0.0 当前实现状态

> 目的：记录 `v2.0.0-refactor` 当前已经实际落地到哪一步，避免把“文档已冻结”和“代码已实现”混为一谈。

## 1. 状态快照

- 日期：`2026-04-15`
- 集成分支：`feat/v2-runtime-integration`
- 当前阶段：`ESP32 运行时后端已切到 STM32 UART，最小双向链路与缓存能力已落地`
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
- `b778b2c`
  - `GPIO19/20` 切到 `mcu_link` 运行时 UART，本地 `hal_servo` PWM 后端退场
- `eece532`
  - `mcu_link` 增加最小 RX/poll 路径，处理 `HELLO_RSP / ACK / NACK / FAULT`
- `d46a7ee`
  - `mcu_led_service` 通过 `mcu_link` 实际构帧下发 `LED` 类消息
- `28bc162`
  - `mcu_sensor_service` 接入 `touch / imu / mag` 缓存与 `latest-state-wins`

### 2.3 ESP32 已落地内容

- `mcu_link`
  - 已有 `CRC16 / COBS / frame / wire / FSM / stats` 骨架
  - 已有最小 UART transport scaffold
  - 已有 `HELLO_REQ` bootstrap 发送路径
  - 已有 `mcu_link_poll()` / `mcu_link_bootstrap_poll()`
  - 已可解 `HELLO_RSP / ACK / NACK / FAULT`
- `mcu_motion_service`
  - 已从“仅缓存请求”推进到“链路进入 `link_ready` 时镜像下发 `SERVO_MOVE / SERVO_STOP`”
- `mcu_led_service`
  - 已支持 `MCU_LED_MODE_STATIC / EFFECT / OFF` 构帧并通过 `mcu_link` 下发
  - `link` 未 ready 时仅缓存，不引入外部副作用
- `hal_servo`
  - 已收缩为协处理器兼容入口 / 参数校验层
  - 本地 PWM task / LEDC 运行路径已移除
  - `GPIO19/20` 已让位给 `mcu_link` 运行时 UART
- `mcu_sensor_service`
  - 已建立 `touch / mag / imu` 缓存
  - 已增加 `mcu_sensor_service_apply_frame()` 作为上行 frame 消费入口
  - `IMU_STATE / MAG_STATE` 已采用 `latest-state-wins`
- Mock HIL 工具
  - 已有 `tools/stm32_uart_hil.py`
  - 已有 `tools/stm32_uart_fault_inject.py`

### 2.4 已验证

以下检查在当前代码上已通过：

- `idf.py build`
- `python tools/stm32_uart_hil.py --all-scenarios --transport mock`
- `git diff --check`
- `COM28` 刷写成功
- `COM28` 启动 smoke 成功

关键板级日志样本：

- [monitor-com28-20260415-164805.log](</D:/GithubRep/worktrees/watcher-v2-runtime-integration/firmware/s3/monitor-com28-20260415-164805.log>)

该日志确认：

- 存在 `MCU link scaffold ready`
- 存在 `after_ui_init`
- 存在 `WatcheRobot ready`
- 未发现 `panic`
- 未发现 `Guru Meditation`
- `i2s_channel_disable` 仍然存在，但属于已知既有噪声，不是本轮协处理器改动引入

## 3. 当前未完成

以下项目仍未进入“已实现”状态：

- `mcu_link_poll()` 还没有被长期调度到运行时任务中
- `mcu_link` 的 `ACK / NACK / FAULT / sensor state` 还没有分发到 motion / led / sensor 服务层
- `MOTION_DONE / LED_DONE / TOUCH_EVENT / IMU_STATE / MAG_STATE` 的 live dispatch 还未接上
- `BLE / WS / control_ingress / behavior_state_service` 仍未完成全链路切换
- 基于真实 STM32 的 UART 闭环联调尚未开始

## 4. 当前阶段判断

结合 [TDD_EXECUTION_PLAN.md](./TDD_EXECUTION_PLAN.md)，当前更准确的阶段判断是：

- 阶段 1：协议合同层，已完成
- 阶段 2：链路状态机层，已完成最小运行时双向链路
- 阶段 3：动作与灯效服务层，已完成 motion / led 的最小下行接入
- 阶段 4：ESP32 适配层，已完成 `hal_servo -> mcu_motion_service` 的后端切换
- 阶段 5：sensor 缓存层，已完成缓存与 `latest-state-wins` 基础能力
- 阶段 5~7：尚未开始

因此当前不应宣称“协处理器链路已完成”，更准确的说法是：

- `ESP32` 侧已完成引脚切换和最小双向链路骨架
- motion / led / sensor 已具备最小协议接入点
- 还缺 live dispatch、上层业务切换和 STM32 实机闭环

## 5. 下一阶段入口

下一阶段不直接落实现，先以待办冻结为准：

- [IMPLEMENTATION_TODO.md](./IMPLEMENTATION_TODO.md)
