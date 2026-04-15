# v2.0.0 TDD 执行计划

> 目的：把 STM32 协处理器重构改写成可执行的 `Red -> Green -> Refactor` 节奏，避免先写实现再补测试。
>
> 关系说明：协议真源见 [STM32_UART_PROTOCOL.md](./STM32_UART_PROTOCOL.md)，系统分层真源见 [STM32_COPROC_REFACTOR_PLAN.md](./STM32_COPROC_REFACTOR_PLAN.md)。

## 1. TDD 总原则

- 先测试合同，再写实现。
- 先测试失败路径，再测试 happy path。
- 先测试纯函数和状态机，再接入任务、驱动、真机。
- 每个阶段只增加一类复杂度，不能协议、UART、外设同时推进。
- 每个阶段结束前，必须同时满足：
  - 当前阶段测试全绿
  - 真源文档未漂移
  - 现有外部 BLE / WS 语义未被破坏

## 2. 测试分层

### 2.1 L1 单元测试

目标：

- 协议编解码
- CRC / COBS
- 链路状态机
- service 纯逻辑

工具：

- ESP-IDF Unity
- CMock

### 2.2 L2 组件测试

目标：

- fake transport + FreeRTOS task
- `control_ingress` / `behavior_state_service` 的适配层
- 背压和优先级策略

### 2.3 L3 集成测试

目标：

- UART 驱动
- ring buffer
- 粘包/拆包/错帧恢复

### 2.4 L4 HIL 真机联调

目标：

- ESP32 + STM32 实板闭环
- 恢复、故障注入、速率压力测试

### 2.5 无 STM32 实机阶段的 Mock 策略

在没有 STM32 实机前，测试策略冻结为：

- 不直接依赖物理 UART
- 先验证协议、状态机、服务层和背压策略
- 真 UART 驱动与实板只在 `L3` 与 `L4` 再接入

Mock 分层冻结为：

- `M0 message-level mock`
  - 直接注入已解码消息对象
  - 用于验证状态机迁移、ACK/NACK/DONE/FAULT 处理和 service 逻辑
- `M1 byte-stream mock`
  - 注入 `COBS + CRC16 + 0x00 delimiter` 后的原始字节流
  - 用于验证解帧、重同步、坏帧恢复和粘包/拆包逻辑
- `M2 uart-driver mock`
  - 模拟 ring buffer、分块接收、驱动事件和发送返回值
  - 用于验证接近 ESP-IDF UART 驱动的集成行为

推荐顺序：

1. `L1` 先做 `M0` 与 `M1`
2. `L2` 再做 `fake transport + task` 级别的 `M0/M1`
3. `L3` 才做 `M2`
4. `L4` 最后接 STM32 实机

## 3. 目录与文件落点

建议新增：

- `components/protocols/mcu_link`
- `components/services/mcu_motion_service`
- `components/services/mcu_led_service`
- `components/services/mcu_sensor_service`

测试目录建议：

- `components/protocols/mcu_link/test`
- `components/services/mcu_motion_service/test`
- `components/services/mcu_led_service/test`
- `components/services/mcu_sensor_service/test`
- `components/services/control_ingress/test`
- `components/services/behavior_state_service/test`

Mock 支撑目录建议：

- `components/protocols/mcu_link/test/fakes`
  - `fake_transport.c`
  - `fake_clock.c`
  - `fake_event_sink.c`
  - `byte_stream_harness.c`
- `components/protocols/mcu_link/test/support`
  - `frame_builders.c`
  - `message_builders.c`
  - `uart_driver_mock.c`

HIL 工具建议：

- `tools/stm32_uart_hil.py`

## 4. 无 STM32 实机时的测试接口约束

为了支持 Mock 测试，`mcu_link_service` 与相关 service 在实现时必须先抽象以下接口：

- `transport_send_bytes(const uint8_t *data, size_t len)`
  - 负责真正发送字节流
- `clock_now_ms()`
  - 负责超时和心跳计时
- `event_sink_publish(...)`
  - 负责对外发布状态和事件
- `stats_record_*()`
  - 负责统计计数更新

禁止：

- 在 `mcu_link_fsm` 或协议编解码逻辑里直接调用 ESP-IDF UART API
- 在 service 逻辑里直接依赖 ISR 或驱动事件结构

要求：

- 协议层必须能在“无 FreeRTOS、无 UART 驱动”的环境下测试
- 状态机必须能在 fake time 环境下推进
- service 层必须能通过 fake transport 观察发送结果和 inflight 状态

## 5. 分阶段 TDD 节奏

### 4.1 阶段 1：协议合同层

先写失败测试：

- `test_crc16_known_vector`
- `test_cobs_round_trip_with_zero_bytes`
- `test_encode_decode_round_trip_ack_req_frame`
- `test_decode_rejects_bad_crc`
- `test_decode_rejects_oversize_payload`
- `test_decoder_resyncs_after_garbage`

只允许实现：

- `mcu_crc16.c`
- `mcu_cobs.c`
- `mcu_frame_codec.c`

出口标准：

- 所有协议编解码测试全绿
- 不依赖 UART、FreeRTOS、任务

### 4.2 阶段 2：链路状态机层

先写失败测试：

- `test_boot_transitions_to_handshaking`
- `test_valid_hello_rsp_enters_link_ready`
- `test_baseline_sync_completion_enters_ready`
- `test_hello_timeout_retries`
- `test_three_missed_heartbeats_enter_degraded`
- `test_new_hello_rsp_recovers_link_ready`
- `test_proto_version_mismatch_blocks_ready`
- `test_ack_timeout_fails_command_without_resetting_link`

只允许实现：

- `mcu_link_fsm.c`
- `mcu_link_stats.c`
- fake `transport_send`
- fake `clock_now_ms`

出口标准：

- 握手、`link_ready -> ready`、心跳、超时、降级测试全绿
- 仍不接真实 UART

### 4.3 阶段 3：动作与灯效服务层

先写失败测试：

- `test_motion_submit_rejects_not_ready`
- `test_motion_submit_clamps_y_limit`
- `test_motion_submit_builds_servo_move_frame`
- `test_motion_stop_builds_stop_frame`
- `test_motion_done_clears_inflight`
- `test_motion_nack_busy_maps_to_busy`
- `test_led_static_builds_frame`
- `test_led_effect_builds_frame`
- `test_led_done_clears_inflight`

只允许实现：

- `mcu_motion_service.c`
- `mcu_led_service.c`

出口标准：

- 构帧正确
- `ACK/NACK/DONE/FAULT` 路径可离线验证

### 4.4 阶段 4：ESP32 适配层

先写失败测试：

- `test_control_ingress_servo_uses_mcu_motion_service`
- `test_behavior_action_dispatch_sends_coarse_move`
- `test_ble_busy_maps_to_sys_nack_busy`
- `test_ws_fault_maps_to_device_error`

改造范围：

- `control_ingress`
- `behavior_state_service`
- `hal_servo`
- BLE / WS 舵机路径

出口标准：

- 外部 `ctrl.servo.angle` 语义不变
- 内部动作链已切到 `mcu_motion_service`

### 4.5 阶段 5：传感器与背压层

先写失败测试：

- `test_touch_event_published_immediately`
- `test_imu_state_overwrites_previous_snapshot`
- `test_mag_state_overwrites_previous_snapshot`
- `test_ack_queue_prioritized_over_state_queue`
- `test_dropped_state_counter_increments`
- `test_high_rate_imu_does_not_starve_ack_processing`

实现范围：

- `mcu_sensor_service.c`
- latest-state cache
- `ack_queue / event_queue / state cache` 分层

出口标准：

- 高频 `IMU_STATE` 注入下，控制 ACK 仍稳定

### 4.6 阶段 6：UART 驱动集成

先写失败测试：

- `test_uart_rx_handles_back_to_back_frames`
- `test_uart_rx_handles_split_frame`
- `test_uart_rx_discards_bad_crc_and_accepts_next_frame`
- `test_uart_tx_keeps_single_inflight_ack_req`

实现范围：

- ESP-IDF UART 驱动接入
- ring buffer
- dispatch task

出口标准：

- 粘包、拆包、错帧恢复全绿

### 4.7 阶段 7：HIL 真机联调

先写失败用例，再接真机：

- `hello_heartbeat_smoke`
- `servo_move_ack_done`
- `servo_stop_interrupt`
- `led_effect_ack_done`
- `touch_press_release`
- `imu_state_rate_20hz`
- `coproc_reset_recovery`
- `crc_fault_injection`

出口标准：

- 真机场景可重复跑通
- 有统计输出，不靠手工串口观察

## 6. Mock 数据注入矩阵

无 STM32 实机时，至少要覆盖以下注入场景：

- 握手成功
  - `HELLO_REQ -> ACK -> HELLO_RSP`
- 握手拒绝
  - `HELLO_REQ -> NACK`
- 握手超时
  - `HELLO_REQ -> timeout`
- 恢复成功
  - `HELLO_REQ -> ACK -> HELLO_RSP -> [SNAPSHOT_REQ -> ACK -> SNAPSHOT_RSP]`
- 无 snapshot 恢复
  - `HELLO_REQ -> ACK -> HELLO_RSP(capability without snapshot) -> baseline restore`
- 动作 accepted + done
  - `SERVO_MOVE -> ACK -> MOTION_DONE`
- 动作 accepted + fault
  - `SERVO_MOVE -> ACK -> FAULT(ref_seq != 0)`
- 灯效 accepted + done
  - `LED_SET_EFFECT -> ACK -> LED_DONE`
- 状态流压力
  - 高频 `IMU_STATE` + 间歇 `MAG_STATE`
- 坏帧恢复
  - 错 CRC
  - 截断帧
  - 随机垃圾字节
  - back-to-back 多帧
  - chunked 分片输入

这些场景必须按层落地：

- `M0`
  - 关注状态机、service、映射逻辑
- `M1`
  - 关注字节流、解帧、重同步
- `M2`
  - 关注驱动集成、接收分块、发送路径

## 7. 无实机阶段的完成标准

在进入真 UART 或 STM32 实机前，必须满足：

- `L1` 和 `L2` 全绿
- `L3` 的 UART mock 集成测试全绿
- `ACK/NACK/DONE/FAULT` 全链路可通过 mock 场景重复验证
- `snapshot` 和 `no-snapshot` 两条恢复路径都已通过 mock
- 高频 `IMU_STATE` 注入下，`ACK` 处理不会被饿死
- 所有关键统计字段都能在 mock 场景中被触发和断言

只有满足这些条件，才进入真 UART 驱动联调和 STM32 实机 HIL。

## 8. 每阶段提交规则

- 一阶段至少两个提交：
  - `test:` 先引入失败测试
  - `feat:` 最小实现让测试转绿
- Refactor 只能发生在该阶段测试已经全绿之后
- 不允许把多个阶段混在一个提交里

推荐提交前缀：

- `test:`
- `feat:`
- `refactor:`
- `docs:`

## 9. 观察指标

开发过程中必须持续统计：

- `ack_timeout_count`
- `crc_error_count`
- `reconnect_count`
- `dropped_state_count`
- `motion_done_fault_count`

这些指标的定义必须同时出现在：

- 实现代码统计结构
- HIL 输出
- 回归记录

## 10. 非目标

本计划不包含：

- STM32 固件升级 TDD
- 上位机 GUI 自动化
- 对外 WebSocket 协议回归脚本
- 在没有完成 `L1-L3 mock` 前直接上 STM32 实机调协议
