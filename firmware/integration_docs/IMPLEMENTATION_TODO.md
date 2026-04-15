# v2.0.0 下一阶段 TODO

> 目的：冻结已经确认、但尚未实施的下一阶段改动，避免实现过程中目标继续漂移。

## 1. 本文范围

本文只记录：

- 已确认的下一阶段工作项
- 每项工作的边界
- 每项工作的最低验收口径

本文不表示这些内容已经实现。

## 2. 下一阶段总目标

把当前“ESP32 本地舵机 + 协处理器链路骨架”的状态，推进到“ESP32 以 STM32 UART 协处理器为唯一运行时后端”的下一检查点。

## 3. 已冻结的待办

### TODO-001：GPIO19/20 切到运行时 UART

目标：

- ESP32 侧将 `GPIO19/20` 从当前本地舵机 PWM 释放出来
- 直接作为 `ESP32 <-> STM32` 的运行时 UART 引脚

边界：

- `GPIO19` / `GPIO20` 不再由本地 `hal_servo` LEDC 使用
- `mcu_link_uart` 成为这组引脚的唯一运行时占用方
- 当前本地双舵机控制模块从运行路径移除

最低验收：

- `hal_servo` 不再直接驱动 `GPIO19/20`
- `mcu_link_uart` 可在 `GPIO19/20` 上初始化成功
- 板级启动后，串口日志中能明确看到协处理器 UART runtime 已启用

### TODO-002：移除当前本地舵机控制模块

目标：

- 把当前 `hal_servo` 从“本地 PWM 驱动器”收缩为“兼容入口 / 参数校验层”
- 实际动作执行统一走 `mcu_motion_service -> mcu_link`

边界：

- 保留 `hal_servo_*` 对上兼容接口
- 去除本地舵机 task、LEDC PWM 运行路径
- 保留角度校验、Y 轴限幅、source 语义

最低验收：

- `control_ingress` 下发的舵机动作不再触发本地 PWM
- `behavior_state_service` 下发的舵机动作不再触发本地 PWM
- 现有 servo 控制入口仍可用，但实际执行统一走 `mcu_motion_service -> mcu_link`

### TODO-003：接入 `mcu_link` RX / 解帧 / `HELLO_RSP` / `ACK` / `FAULT`

目标：

- 让 `mcu_link` 从“只会发 `HELLO_REQ`”推进到“具备最小收包与状态推进能力”

边界：

- 接入 UART RX
- 以 `0x00 delimiter + COBS + CRC16` 完成解帧
- 至少处理：
  - `HELLO_RSP`
  - `ACK`
  - `NACK`
  - `FAULT`
- 能推进：
  - `DOWN -> HANDSHAKING -> LINK_READY`
  - 故障与错误统计更新

最低验收：

- 能在 mock 和真机上正确处理 `HELLO_RSP`
- `ACK / NACK / FAULT` 能进入统计和日志
- 收到错误 CRC 帧时能丢弃并继续同步

### TODO-004：接入 `mcu_led_service` 实际帧下发

目标：

- 把 `mcu_led_service` 从占位实现推进到真实协议下发

边界：

- 支持 `LED_SET_STATIC`
- 支持 `LED_SET_EFFECT`
- 支持 `LED_OFF`
- 通过 `mcu_link` 发送帧，不直接做本地灯效

最低验收：

- 能构出正确 `LED` 类消息
- `ACK / DONE / FAULT` 路径有接口位置
- 在 link 未 ready 时不破坏现有系统行为

### TODO-005：接入 sensor 上行缓存与 `latest-state-wins`

目标：

- 把 `mcu_sensor_service` 从本地缓存组件推进到 STM32 上行状态的实际消费端

边界：

- 接入 `TOUCH_EVENT`
- 接入 `IMU_STATE`
- 接入 `MAG_STATE`
- 对 `IMU_STATE / MAG_STATE` 使用 `latest-state-wins`
- 事件和状态分开处理

最低验收：

- 高频 `IMU_STATE` 不导致控制 ACK 饥饿
- `dropped_state_count` 可统计
- 上层能获取最新 touch / imu / mag 快照

## 4. 顺序约束

下一阶段执行顺序冻结为：

1. `GPIO19/20` 运行时 UART 切换
2. 本地舵机 PWM 后端移除
3. `mcu_link` RX / 解帧 / `HELLO_RSP / ACK / FAULT`
4. `mcu_led_service` 实际帧下发
5. sensor 上行缓存与 `latest-state-wins`

不建议跳步直接做 sensor 或 LED，因为当前最关键的架构切换点仍是：

- UART 引脚所有权
- 本地舵机后端退场
- `mcu_link` 从单向发送骨架进入双向链路

## 5. 非目标

下一阶段 TODO 不包含：

- STM32 固件升级
- STM32 真正外设驱动实现
- WS / BLE 外部协议改版
- camera 协议接入
- 像素级 WS2812 推流
