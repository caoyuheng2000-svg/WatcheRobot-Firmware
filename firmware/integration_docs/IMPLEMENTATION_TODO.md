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
- `mcu_link_poll()` 已接入主循环持续调度
- motion / led 已改成仅在 `READY` 后放行业务帧
- `hal_servo_init()` 失败已升级为启动期 halt

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

### TODO-007：把最小 safe-default bootstrap 替换成正式 baseline restore

目标：

- 让 `HELLO_RSP -> READY` 的推进不再依赖当前的最小 safe-default bootstrap
- 明确首次启动和恢复场景到底依据 `snapshot` 还是安全默认基线

边界：

- 优先覆盖 `no-snapshot` 的安全默认基线
- 若 `snapshot` capability 存在，则至少保留清晰的接入点
- 不在这一阶段扩展成 STM32 固件升级或复杂脚本机制

最低验收：

- `READY` 的进入条件和文档定义一致
- 冷启动与恢复路径都能解释“基线从哪里来”
- 不再需要在 bootstrap 层直接调用“最小兜底”推进 ready

### TODO-008：补齐串口 bring-up 期间的 service 级观测和 bench 清单

目标：

- 让首次真实 STM32 串口调试时，ESP32 侧能明确看见 service 级 accepted / rejected / done / fault
- 把 bench 期间必须执行的检查项固定下来，避免现场调试口径漂移

边界：

- 至少覆盖 motion / led / sensor 各 1 条 service 观测路径
- 至少覆盖 `HELLO / ACK / NACK / FAULT / DONE`
- 允许先通过日志和统计暴露，不要求一步到位做 UI 展示

最低验收：

- 串口 bring-up 期间可以从 ESP32 日志判断“卡在哪一层”
- 每次 bench 调试都能按固定 checklist 执行
- `motion_done_fault_count / ack_timeout_count / reconnect_count` 能用于现场判断

### TODO-009：切换上层业务入口到协处理器语义

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

### TODO-010：启动真实 STM32 UART 闭环联调

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
2. 正式 baseline restore
3. 串口 bring-up 期间的 service 级观测和 bench checklist
4. 上层业务入口切换到协处理器语义
5. 真实 STM32 UART 闭环联调

不建议跳步直接做 BLE / WS 回归，因为当前最关键的缺口仍是：

- live frame 还没进入业务层
- 正式 baseline restore 还没替换当前最小兜底策略
- mock 闭环还没切到真实 STM32

## 5. 非目标

下一阶段 TODO 不包含：

- STM32 固件升级
- STM32 真正外设驱动实现
- WS / BLE 外部协议改版
- camera 协议接入
- 像素级 WS2812 推流
