# v2.0.0 下一阶段 TODO

> 目的：冻结已经确认、但尚未实施的下一阶段改动，避免实现过程中目标继续漂移。

## 1. 本文范围

本文只记录：

- 已确认的下一阶段工作项
- 每项工作的边界
- 每项工作的最低验收口径

本文不表示这些内容已经实现。

## 2. 下一阶段总目标

把当前“ESP32 已切到 STM32 UART 后端，但 live dispatch 和业务层切换尚未完成”的状态，推进到“ESP32 具备完整运行时事件分发与上层接入能力”的下一检查点。

## 3. 已冻结的待办

### 已完成：上一阶段待办

以下工作已完成，不再作为下一阶段待办：

- `GPIO19/20` 已切到运行时 UART
- 本地 `hal_servo` PWM 后端已移除
- `mcu_link` 已接入最小 RX / 解帧 / `HELLO_RSP / ACK / NACK / FAULT`
- `mcu_led_service` 已接入实际帧下发
- `mcu_sensor_service` 已接入缓存与 `latest-state-wins`

### TODO-006：把 `mcu_link` live frame 分发给业务服务

目标：

- 让 `mcu_link` 收到的运行时消息真正驱动 `mcu_motion_service / mcu_led_service / mcu_sensor_service`
- 不再停留在“只更新 FSM 和 stats”的层面

边界：

- 接入 `MOTION_DONE`
- 接入 `LED_DONE`
- 接入 `TOUCH_EVENT`
- 接入 `IMU_STATE`
- 接入 `MAG_STATE`
- `ACK / NACK / FAULT` 至少能进入 service 可消费接口

最低验收：

- mock 场景下，live frame 能进入对应 service
- service 层状态不再只依赖本地缓存 API 手动更新
- `motion_done_fault_count / dropped_state_count` 能在运行时闭环更新

### TODO-007：安排 `mcu_link` 运行时 poll / dispatch 调度

目标：

- 给 `mcu_link_poll()` 找到稳定的运行时执行点
- 避免只有 bootstrap 初始化，没有持续收包能力

边界：

- 不要求一开始就引入复杂新任务树
- 允许先用轻量 poll task / timer 驱动
- 不能阻塞现有 BLE / Wi-Fi / UI 主路径

最低验收：

- 运行时能持续处理 UART 上行
- 丢包 / CRC 错误后仍可继续同步
- 板级 smoke 下不引入新的启动阻塞

### TODO-008：切换上层业务入口到协处理器语义

目标：

- 让 `control_ingress / behavior_state_service / BLE / WS` 真正消费协处理器返回语义
- 保持外部协议尽量不变

边界：

- `control_ingress` 要能处理远端 busy / not_ready / fault
- `behavior_state_service` 要能处理 stop / interrupted / done
- BLE / WS 外部 `sys.ack / sys.nack` 语义不改版

最低验收：

- 手动控制和行为动作都不再依赖本地舵机语义
- 外部协议仍保持兼容
- 常见失败路径能给出稳定错误映射

### TODO-009：启动真实 STM32 UART 闭环联调

目标：

- 把当前 mock 闭环推进到真实协处理器联调
- 验证协议、恢复、频率和背压假设

边界：

- 最少覆盖 `HELLO / ACK / NACK / FAULT`
- 最少覆盖 motion / led / sensor 各 1 条真实链路
- 不在这一阶段展开 STM32 固件升级

最低验收：

- 真实 UART 链路可以稳定握手
- `MOTION_DONE / LED_DONE / sensor state` 至少有一条真实闭环
- HIL 脚本可以从 `mock` 切换到 `serial`

## 4. 顺序约束

下一阶段执行顺序冻结为：

1. `mcu_link` live frame -> service 分发
2. `mcu_link` 运行时 poll / dispatch 调度
3. 上层业务入口切换到协处理器语义
4. 真实 STM32 UART 闭环联调

不建议跳步直接做 BLE / WS 回归，因为当前最关键的缺口仍是：

- live frame 还没进入业务层
- 运行时收包调度还没固定
- mock 闭环还没切到真实 STM32

## 5. 非目标

下一阶段 TODO 不包含：

- STM32 固件升级
- STM32 真正外设驱动实现
- WS / BLE 外部协议改版
- camera 协议接入
- 像素级 WS2812 推流
