# STM32 协处理器 HIL 联调计划

> 目的：定义 `ESP32 + STM32` 真机联调的最小拓扑、脚本入口、测试矩阵和通过标准。

## 1. 目标

HIL 测试只回答三件事：

- 协议在真 UART 链路上是否稳定
- ESP32 在状态流压力下是否仍可控
- 掉线、恢复、故障注入是否符合文档定义

## 2. 测试拓扑

推荐拓扑：

```text
PC
 |\
 | \-- UART / log capture -> ESP32
 |
 +---- control script -> ESP32 / STM32 pair

ESP32 <---- UART 921600 ----> STM32
```

建议同时保留：

- ESP32 日志串口
- STM32 调试串口或半主机输出

若只能保留一路日志，则优先保留 ESP32 侧日志，并在 STM32 端回传关键错误码。

## 3. 工具与脚本

建议新增：

- `tools/stm32_uart_hil.py`
  - 主联调脚本
- `tools/stm32_uart_fault_inject.py`
  - 可选故障注入工具

脚本输出统一结构：

- `scenario`
- `result`
- `ack_timeout_count`
- `crc_error_count`
- `dropped_state_count`
- `reconnect_count`
- `motion_done_fault_count`
- `notes`

## 4. 用例矩阵

### 4.1 冒烟用例

- `hello_heartbeat_smoke`
  - 验证握手、心跳、能力位
- `servo_move_ack_done`
  - 验证动作 accepted 和完成事件
- `led_effect_ack_done`
  - 验证灯效 accepted 和完成事件
- `touch_press_release`
  - 验证触摸事件链路

### 4.2 回归用例

- `servo_stop_interrupt`
- `imu_state_rate_20hz`
- `mag_state_rate_2hz`
- `coproc_reset_recovery`
- `snapshot_restore`
  - 仅在 `capability_bitmap.bit5(snapshot) = 1` 时执行
- `baseline_restore_without_snapshot`
  - 仅在 `capability_bitmap.bit5(snapshot) = 0` 时执行

### 4.3 故障注入用例

- `crc_fault_injection`
- `truncated_frame_injection`
- `ack_timeout_simulation`
- `heartbeat_loss_simulation`
- `busy_nack_path`

## 5. 通过标准

### 5.1 协议稳定性

- 连续运行 `10 min` 不出现未恢复卡死
- 错帧注入后链路能自动重同步
- `ACK timeout` 不出现持续上升趋势

### 5.2 背压稳定性

- `IMU_STATE 20Hz` 下，动作命令的 accepted 延迟保持稳定
- 状态流拥塞时，`dropped_state_count` 可增长，但 `ACK/DONE/FAULT` 不应明显丢失

### 5.3 恢复能力

- STM32 复位后，ESP32 能回到 `READY`
- 恢复后能重新执行动作和灯效命令

## 6. 测试节奏

建议节奏：

- 每日开发：跑冒烟用例
- 阶段合并前：跑回归用例
- 协议或链路层改动后：跑故障注入用例

## 7. 从 mock 切到真实 serial 前的前置条件

切到真实 STM32 串口 HIL 之前，ESP32 侧至少需要满足：

- `mcu_link` live frame 已能进入 motion / led / sensor service
- `READY` 已来自正式 baseline restore，而不是临时 bootstrap 兜底
- `ack_timeout_count / reconnect_count / motion_done_fault_count / dropped_state_count` 可稳定输出
- bench 执行顺序已冻结，参见 [FIELD_REVIEW_TODO.md](./FIELD_REVIEW_TODO.md)

## 8. 日志要求

ESP32 日志至少包含：

- `seq`
- `msg_class`
- `msg_id`
- `ref_seq`
- `reason_code`
- `fault_source`

HIL 日志输出中不得只写“失败”，必须带可定位字段。

## 9. 非目标

本计划不覆盖：

- BLE / WS 端到端云联调
- STM32 固件升级联调
- 视觉协处理器链路
