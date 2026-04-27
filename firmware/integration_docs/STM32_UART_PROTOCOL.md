# ESP32 <-> STM32 UART 协议定义（v2.0.0 / 协议真源）

> 目的：冻结 `ESP32 <-> STM32` 板内 UART 协议，作为后续 `mcu_link_service`、STM32 协议解析器、联调工具和回归测试的唯一真源。
>
> 范围：只覆盖运行时控制与状态同步，不覆盖 STM32 固件升级。
>
> 关系说明：系统分层和职责边界见 `STM32_COPROC_REFACTOR_PLAN.md`。对外网络协议仍以 `../s3/docs/COMM_PROTOCOL_FREEZE.md` 与 `../s3/docs/BLE_GATT_PROTOCOL_BRIDGE.md` 为基线。

## 1. 设计目标

本协议遵守以下设计目标：

- 低耦合：板内协议不复用 BLE / WS 的 JSON 格式
- 可重同步：任意错帧后都能在串口流中快速恢复同步
- 可扩展：支持后续增加消息类型，但 v1 不支持分片大包
- 控制优先：ACK、故障和执行完成事件优先于状态遥测
- 状态可丢：周期状态上报允许覆盖旧值，不积压长队列

## 2. 物理层

物理层冻结为：

- 介质：UART
- 速率：`921600`
- 格式：`8N1`
- 收发：ESP32 与 STM32 两侧均使用 DMA 或 ring buffer
- 方向：全双工

运行时协议明确不承担：

- STM32 固件升级
- 文本 shell
- 长日志流

## 3. 传输层

### 3.1 帧封装

链路上的完整发送单元为：

```text
COBS(encoded binary frame) + 0x00 delimiter
```

约束：

- `0x00` 只作为帧结束分隔符
- 接收端以 `0x00` 作为一帧边界
- 任意坏帧只影响当前帧，不影响后续重同步

### 3.2 校验

二进制帧使用：

- 校验算法：`CRC16-CCITT-FALSE`
- `poly = 0x1021`
- `init = 0xFFFF`
- `xorout = 0x0000`
- `refin = false`
- `refout = false`

CRC 覆盖范围：

- 从 `magic` 开始，到 `payload` 结束
- 不包含 COBS 包装和末尾 `0x00`

### 3.3 大小约束

v1 固定约束：

- `payload_len <= 128`
- 单帧总长度必须可在两侧静态缓冲区中一次容纳
- v1 不支持分片，不允许发送大于 128 bytes 的业务 payload

## 4. 二进制帧格式

内层二进制帧格式冻结为：

| 字段 | 长度 | 说明 |
| --- | --- | --- |
| `magic` | 2 | 固定 `0xA5 0x5A` |
| `proto_ver` | 1 | 固定 `0x01` |
| `msg_class` | 1 | 系统 / 动作 / 灯效 / 传感器 / 电源 |
| `msg_id` | 1 | 类内消息号 |
| `flags` | 1 | `ACK_REQ / RESP / FINAL` |
| `seq` | 4 | 发送端本地单调递增序号 |
| `payload_len` | 2 | 小端，`0..128` |
| `payload` | N | 业务负载 |
| `crc16` | 2 | 小端 |

字节序冻结为：

- 所有多字节整数均为小端

数据类型冻结为：

- v1 不允许在线路上传输 `float`
- 角度、姿态、角速度等统一用定点整数表达

## 5. 通用字段语义

### 5.1 `seq`

- `seq` 是发送端本地 32 位单调递增序号
- ESP32 和 STM32 各自维护自己的 `seq`
- `ACK / NACK / DONE` 通过 payload 中的 `ref_seq` 关联原命令

### 5.2 `flags`

`flags` 位定义冻结为：

- `0x01 = ACK_REQ`
- `0x02 = RESP`
- `0x04 = FINAL`

语义：

- `ACK_REQ`
  - 当前帧要求对端显式返回 `ACK` 或 `NACK`
- `RESP`
  - 当前帧是对之前请求的应答类消息
- `FINAL`
  - 当前帧是一个执行流程的最终结果，例如 `MOTION_DONE` 或 `LED_DONE`

v1 约束：

- `ACK` / `NACK` 必须带 `RESP`
- `HELLO_RSP` / `SNAPSHOT_RSP` 必须带 `RESP`
- `MOTION_DONE` / `LED_DONE` 必须带 `FINAL`
- `FAULT` 如果对应某个具体命令，必须同时带 `RESP | FINAL`

### 5.3 定点单位

v1 单位冻结为：

- 角度：`deg x10`
- 姿态：`deg x100`
- 地磁航向：`deg x100`
- 角速度：`dps x10`
- 加速度模长：`mg`
- 磁场模长：`uT`
- 时间：`ms`

## 6. 消息分类与消息号

### 6.1 `msg_class`

| 类别 | 值 |
| --- | --- |
| `SYS` | `0x01` |
| `MOTION` | `0x02` |
| `LED` | `0x03` |
| `SENSOR` | `0x04` |
| `POWER` | `0x05` |

### 6.2 `SYS` 类消息

| 名称 | `msg_id` | 方向 | ACK_REQ |
| --- | --- | --- | --- |
| `HELLO_REQ` | `0x01` | ESP32 -> STM32 | 是 |
| `HELLO_RSP` | `0x02` | STM32 -> ESP32 | 否 |
| `HEARTBEAT` | `0x03` | 双向 | 否 |
| `ACK` | `0x04` | 双向 | 否 |
| `NACK` | `0x05` | 双向 | 否 |
| `FAULT` | `0x06` | 双向 | 否 |
| `SNAPSHOT_REQ` | `0x07` | ESP32 -> STM32 | 是 |
| `SNAPSHOT_RSP` | `0x08` | STM32 -> ESP32 | 否 |

### 6.3 `MOTION` 类消息

| 名称 | `msg_id` | 方向 | ACK_REQ |
| --- | --- | --- | --- |
| `SERVO_MOVE` | `0x01` | ESP32 -> STM32 | 是 |
| `SERVO_STOP` | `0x02` | ESP32 -> STM32 | 是 |
| `MOTION_DONE` | `0x03` | STM32 -> ESP32 | 否 |
| `MOTION_STATE` | `0x04` | STM32 -> ESP32 | 否 |

### 6.4 `LED` 类消息

| 名称 | `msg_id` | 方向 | ACK_REQ |
| --- | --- | --- | --- |
| `LED_SET_STATIC` | `0x01` | ESP32 -> STM32 | 是 |
| `LED_SET_EFFECT` | `0x02` | ESP32 -> STM32 | 是 |
| `LED_OFF` | `0x03` | ESP32 -> STM32 | 是 |
| `LED_DONE` | `0x04` | STM32 -> ESP32 | 否 |
| `LED_STATE` | `0x05` | STM32 -> ESP32 | 否 |

### 6.5 `SENSOR` 类消息

| 名称 | `msg_id` | 方向 | ACK_REQ |
| --- | --- | --- | --- |
| `TOUCH_EVENT` | `0x01` | STM32 -> ESP32 | 否 |
| `MAG_STATE` | `0x02` | STM32 -> ESP32 | 否 |
| `MAG_EVENT` | `0x03` | STM32 -> ESP32 | 否 |
| `IMU_STATE` | `0x04` | STM32 -> ESP32 | 否 |
| `IMU_EVENT` | `0x05` | STM32 -> ESP32 | 否 |
| `SENSOR_HEALTH` | `0x06` | STM32 -> ESP32 | 否 |

### 6.6 `POWER` 类消息

| 名称 | `msg_id` | 方向 | ACK_REQ |
| --- | --- | --- | --- |
| `POWER_5V_ENABLE` | `0x01` | ESP32 -> STM32 | 是 |
| `POWER_5V_DISABLE` | `0x02` | ESP32 -> STM32 | 是 |

## 7. 关键 payload 定义

### 7.1 `HELLO_REQ`

字段语义：

- `host_role`
  - 固定为 `ESP32_HOST`
- `host_proto_ver`
- `expected_capability_bitmap`
- `boot_session_id`

### 7.2 `HELLO_RSP`

字段语义：

- `device_role`
  - 固定为 `STM32_COPROC`
- `fw_version_major/minor/patch`
- `hw_version`
- `capability_bitmap`
- `sensor_bitmap`
- `boot_reason`
- `default_stream_profile`
  - 类型：`uint8 profile_id`
  - 语义：STM32 默认采用的传感器上报档位
  - 本字段只覆盖 `touch / imu / magnetometer / sensor_health` 的板内上报策略
  - 与 camera 抓拍、BLE、WS 无关

`capability_bitmap` 冻结位定义：

- `bit0 = motion`
- `bit1 = led`
- `bit2 = touch`
- `bit3 = imu`
- `bit4 = magnetometer`
- `bit5 = runtime_state_snapshot`
  - `snapshot` 在本文中专指“运行时状态快照能力”
  - 不表示 camera 抓拍或图片快照
- `bit6 = power`
  - 表示 STM32 可通过板上电源管理通路控制 5V Boost 输出

`sensor_bitmap` 冻结位定义：

- `bit0 = touch`
- `bit1 = imu`
- `bit2 = magnetometer`

`default_stream_profile` 冻结如下：

- `0x00 = reserved`
- `0x01 = v1_default`
- `0x80..0xFF = vendor_reserved`

v1 中仅允许 `0x01 = v1_default`，其语义固定为：

- `TOUCH_EVENT = 开启，边沿即时上报`
- `IMU_EVENT = 开启，变化即时上报`
- `IMU_STATE = 开启，20 Hz`
- `MAG_EVENT = 开启，变化即时上报`
- `MAG_STATE = 开启，2 Hz`
- `SENSOR_HEALTH = 开启，变化上报`
- `MOTION_STATE = 关闭，调试构建才允许开启`
- `LED_STATE = 命令后或故障后上报`

兼容性规则：

- ESP32 收到未知 `default_stream_profile` 时，不得进入 `coprocessor_ready`
- 已冻结的 `profile_id` 语义后续不得重定义，只能新增新的 `profile_id`

### 7.3 `ACK`

字段语义：

- `ref_seq`
- `status_code`

v1 中 `status_code = 0` 表示 accepted。

### 7.4 `NACK`

字段语义：

- `ref_seq`
- `status_code`
- `reason_code`

`reason_code` 冻结如下：

- `0x0001 = invalid_payload`
- `0x0002 = unsupported_msg`
- `0x0003 = unsupported_version`
- `0x0004 = busy`
- `0x0005 = not_ready`
- `0x0006 = invalid_state`
- `0x0007 = out_of_range`
- `0x0008 = capability_missing`
- `0x0009 = crc_error`
- `0x000A = internal_error`

### 7.5 `FAULT`

字段语义：

- `ref_seq`
  - 对应触发本次故障的原命令序号
  - 若故障不对应某个具体命令，例如链路级或后台健康检查故障，则固定为 `0`
- `fault_source`
- `fault_code`
- `detail`

`fault_source` 冻结如下：

- `0x01 = motion`
- `0x02 = led`
- `0x03 = touch`
- `0x04 = imu`
- `0x05 = magnetometer`
- `0x06 = link`
- `0x07 = power`

### 7.6 `SERVO_MOVE`

字段语义：

- `axis_mask`
  - `bit0 = X`
  - `bit1 = Y`
- `x_deg_x10`
- `y_deg_x10`
- `duration_ms`
- `motion_profile`
- `source_tag`

约束：

- 至少一个轴有效
- `duration_ms > 0`
- v1 `motion_profile` 只允许 `0 = linear`

`source_tag` 冻结如下：

- `0 = unknown`
- `1 = behavior`
- `2 = ble`
- `3 = ws`
- `4 = recovery`

### 7.7 `SERVO_STOP`

字段语义：

- `stop_scope`
  - `0 = current_motion`
  - `1 = all_pending_motion`
- `source_tag`

### 7.8 `MOTION_DONE`

字段语义：

- `ref_seq`
- `result_code`
- `final_x_deg_x10`
- `final_y_deg_x10`
- `exec_time_ms`

`motion result_code` 冻结如下：

- `0 = success`
- `1 = stopped`
- `2 = interrupted`
- `3 = fault`

### 7.9 `LED_SET_STATIC`

字段语义：

- `r`
- `g`
- `b`
- `brightness`
- `hold_ms`

### 7.10 `LED_SET_EFFECT`

字段语义：

- `effect_id`
- `primary_r/g/b`
- `secondary_r/g/b`
- `brightness`
- `period_ms`
- `repeat_count`

`effect_id` 冻结如下：

- `1 = blink`
- `2 = breathing`
- `3 = rainbow`
- `4 = status_pulse`

### 7.11 `LED_DONE`

字段语义：

- `ref_seq`
- `result_code`

执行结果沿用 `motion result_code` 语义。

### 7.12 `TOUCH_EVENT`

字段语义：

- `touch_id`
- `event_code`
- `ts_ms`

`sensor event_code` 冻结如下：

- `TOUCH`
  - `1 = press`
  - `2 = release`
  - `3 = long_press`

### 7.13 `MAG_STATE`

字段语义：

- `heading_deg_x100`
- `field_norm_uT`
- `quality`
- `status_bits`

### 7.14 `MAG_EVENT`

字段语义：

- `event_code`
- `value`

`MAG` 事件码冻结如下：

- `1 = heading_sector_changed`
- `2 = disturbance_on`
- `3 = disturbance_off`

### 7.15 `IMU_STATE`

字段语义：

- `roll_deg_x100`
- `pitch_deg_x100`
- `yaw_deg_x100`
- `acc_norm_mg`
- `gyro_norm_dps_x10`
- `motion_flags`

### 7.16 `IMU_EVENT`

字段语义：

- `event_code`
- `value`

`IMU` 事件码冻结如下：

- `1 = motion_start`
- `2 = motion_stop`
- `3 = shake`
- `4 = pose_changed`

### 7.17 `SENSOR_HEALTH`

字段语义：

- `sensor_bitmap`
- `health_bitmap`
- `error_count`

### 7.18 `POWER_5V_ENABLE`

字段语义：

- `source_tag`

语义：

- STM32 通过 IP5306 KEY 控制通路发出一次短按脉冲，打开、唤醒或重新打开 5V Boost 输出。
- 该命令控制的是“按键模拟动作”，不是持续电平型 `5V_EN`。

### 7.19 `POWER_5V_DISABLE`

字段语义：

- `source_tag`

语义：

- STM32 通过 IP5306 KEY 控制通路发出双击短按脉冲，关闭 5V Boost 输出。
- 若板上接入充电输入，实际输出状态仍以 IP5306 硬件行为为准。

## 8. 默认速率与上报策略

v1 默认速率冻结为：

- `HEARTBEAT = 1 Hz`
- `TOUCH_EVENT = 边沿即时上报`
- `MAG_EVENT = 变化即时上报`
- `MAG_STATE = 2 Hz`
- `IMU_EVENT = 变化即时上报`
- `IMU_STATE = 20 Hz`
- `MOTION_STATE = 仅调试构建启用`
- `LED_STATE = 命令后或故障后上报`

上报原则冻结为：

- 事件优先于周期状态
- 周期状态只保留最新值
- 不传原始 IMU 连续流
- 不传 WS2812 像素流

## 9. ACK、完成事件与超时

### 9.1 ACK 语义

以下命令必须设置 `ACK_REQ`：

- `HELLO_REQ`
- `SNAPSHOT_REQ`
- `SERVO_MOVE`
- `SERVO_STOP`
- `LED_SET_STATIC`
- `LED_SET_EFFECT`
- `LED_OFF`
- `POWER_5V_ENABLE`
- `POWER_5V_DISABLE`

控制命令语义冻结为：

- `ACK` 表示“对端已接收并接受处理”
- `NACK` 表示“对端拒绝处理”
- `DONE` / `FAULT` 表示“执行结果”

禁止把“执行完成”折叠进同步 ACK。

请求-应答合同冻结为：

- `HELLO_REQ`
  - 成功路径：必须先收到 `ACK`，随后再收到 `HELLO_RSP`
  - 失败路径：收到 `NACK` 后，本轮握手结束，不再等待 `HELLO_RSP`
- `SNAPSHOT_REQ`
  - 成功路径：必须先收到 `ACK`，随后再收到 `SNAPSHOT_RSP`
  - 失败路径：收到 `NACK` 后，本轮快照请求结束，不再等待 `SNAPSHOT_RSP`
- 对于所有设置了 `ACK_REQ` 的控制命令：
  - `ACK` / `NACK` 只表示接收与受理结果
  - 后续的 `DONE` / `FAULT` 才表示执行结果

### 9.2 超时

超时口径冻结为：

- `ACK timeout = 30 ms`
- `HELLO timeout = 200 ms`
- `SNAPSHOT timeout = 100 ms`
- `HEARTBEAT miss >= 3` 判定链路失联

控制类命令在 v1 中：

- 不做自动重发
- 超时由上层视为失败
- 由恢复流程决定是否重新同步基线状态

## 10. 背压与优先级

ESP32 与 STM32 两侧都必须遵守以下背压策略：

- `ACK / NACK / DONE / FAULT` 优先级最高
- `TOUCH_EVENT / IMU_EVENT / MAG_EVENT` 次高
- `IMU_STATE / MAG_STATE` 为最低优先级

状态类数据固定采用：

- `latest-state-wins`

具体要求：

- 周期状态不重传
- 旧状态允许被新状态覆盖
- 不允许为状态流维护无界历史队列

## 11. 恢复与快照

链路恢复后，ESP32 必须：

1. 重新发 `HELLO_REQ`
2. 收到 `HELLO_RSP` 后校验版本与能力位
3. 若 `capability_bitmap.bit5(runtime_state_snapshot) = 1`，发 `SNAPSHOT_REQ`
4. 若支持 `runtime_state_snapshot`，用 `SNAPSHOT_RSP` 恢复当前动作/LED/传感器健康基线
5. 若不支持 `snapshot`，ESP32 使用本地缓存的最后已知基线状态或默认安全基线重新同步 STM32
6. 待快照恢复或本地基线恢复完成后，再允许新业务命令

`SNAPSHOT_RSP` 仅在 `capability_bitmap.bit5(runtime_state_snapshot) = 1` 时出现，且至少应包含：

- 当前舵机位置
- 当前 LED 模式
- 当前传感器健康位

`SNAPSHOT_RSP` 在 v1 中不承载 camera 状态，不承载图片或视频快照。

## 12. 与现有外部协议的映射

本协议不直接暴露到 BLE / WS。ESP32 侧映射规则冻结为：

- 外部 `command_id` 不上线路
- ESP32 内部把外部 `command_id` 映射到 UART `seq`
- 板内 `ACK / NACK / DONE / FAULT` 再由 ESP32 翻译为现有 `sys.ack / sys.nack / device_error / state event`

映射约束：

- 对外 `ctrl.servo.angle` 仍保持当前 JSON 语义
- 板内 `reason_code` 由 ESP32 转成对外 `reason`
- STM32 不直接参与 BLE / WS 文本协议

## 13. 非目标与保留项

以下内容在 v1 保留但不冻结：

- 更复杂的 `motion_profile`
- 运行时动态订阅不同传感器频率
- 更细的 LED effect 参数模型
- STM32 升级通道
- 板内多节点总线扩展

## 14. Source of Truth

本文的相关参考如下：

- 当前外部协议基线：`../s3/docs/COMM_PROTOCOL_FREEZE.md`
- 当前 BLE 桥接语义：`../s3/docs/BLE_GATT_PROTOCOL_BRIDGE.md`
- 当前协处理器设计经验：`../s3/docs/COPROC_COMM_DEV_DESIGN.md`
- 本轮系统边界真源：`STM32_COPROC_REFACTOR_PLAN.md`
