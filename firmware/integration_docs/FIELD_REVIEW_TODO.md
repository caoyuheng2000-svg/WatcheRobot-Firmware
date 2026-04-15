# STM32 首轮 Field Review TODO

> 目的：把“首次真实 STM32 串口 bring-up / bench 调试”前后，ESP32 侧需要完成和核对的事项整理成固定清单，避免现场口径漂移。

## 1. 范围

本文只关注：

- 首轮真实 STM32 串口联调前，ESP32 侧还必须完成什么
- 上台 bench 时，必须按什么顺序检查
- 哪些问题必须在现场记录回文档

本文不负责重新定义协议或系统分层，相关真源仍以：

- [STM32_COPROC_REFACTOR_PLAN.md](./STM32_COPROC_REFACTOR_PLAN.md)
- [STM32_UART_PROTOCOL.md](./STM32_UART_PROTOCOL.md)

为准。

## 2. 进入真实 STM32 调试前的 ESP32 必做项

### 已完成

- [x] `FR-001` 的最小 code path 已落地：`ACK / NACK / FAULT / MOTION_DONE / LED_DONE / TOUCH_EVENT / MAG_STATE / IMU_STATE` 已能进入对应 service
- [x] `HELLO_RSP -> READY` 已从 bootstrap 隐式推进改成 app 层显式 helper

### 未完成

### FR-001：`mcu_link` live frame 必须进入 service 层

- [x] `ACK / NACK / FAULT` 能被 motion / led / sensor 侧消费
- [x] `MOTION_DONE` 能进入 motion service
- [x] `LED_DONE` 能进入 led service
- [x] `TOUCH_EVENT / IMU_STATE / MAG_STATE` 能进入 sensor service

退出条件：

- mock 场景下可观察到 service 级状态变化，而不仅是 link 层日志

### FR-002：`READY` 必须来自正式 baseline restore

- [x] 去掉当前 `HELLO_RSP -> mark_baseline_synced()` 的 bootstrap 隐式兜底路径
- [ ] 冷启动时明确 `snapshot` / `safe-default` 的基线来源
- [ ] 恢复时明确 `snapshot` / `safe-default` 的基线来源

退出条件：

- 文档定义和代码行为一致，`READY` 不再依赖临时 helper 推进

### FR-003：串口 bring-up 期间必须有 service 级可观测性

- [ ] motion service 能输出 accepted / rejected / done / fault 关键信息
- [ ] led service 能输出 accepted / rejected / done / fault 关键信息
- [ ] sensor service 能输出最新 `touch / imu / mag` 观测摘要
- [ ] 统计项可读：`ack_timeout_count / reconnect_count / motion_done_fault_count / dropped_state_count`

退出条件：

- 现场只看 ESP32 日志即可判断“卡在 link、service 还是上层适配”

## 3. 首轮 bench 固定检查顺序

### Step 1：链路启动

- [ ] ESP32 上电日志出现 `MCU link scaffold ready`
- [ ] `HELLO_REQ` 发出
- [ ] STM32 返回 `HELLO_RSP`
- [ ] ESP32 进入 `READY`

### Step 2：动作链路

- [ ] 下发 `SERVO_MOVE`
- [ ] 观察 `ACK`
- [ ] 观察 `MOTION_DONE`
- [ ] 下发 `SERVO_STOP`
- [ ] 观察 interrupted / stopped 结果是否符合预期

### Step 3：灯效链路

- [ ] 下发 `LED_SET_STATIC` 或 `LED_SET_EFFECT`
- [ ] 观察 `ACK`
- [ ] 观察 `LED_DONE`

### Step 4：传感器链路

- [ ] 观察 `TOUCH_EVENT`
- [ ] 观察 `IMU_STATE`
- [ ] 观察 `MAG_STATE`
- [ ] 检查 `latest-state-wins` 统计是否合理

### Step 5：恢复链路

- [ ] 让 STM32 复位或断连
- [ ] 观察 ESP32 进入恢复路径
- [ ] 恢复后再次验证 motion / led / sensor 至少各 1 条链路

## 4. 可延后到首轮串口 bring-up 之后的项

以下项目不阻塞第一轮 bench 调试，但会阻塞后续完整业务联调：

- [ ] `control_ingress` 细化远端 `busy / not_ready / fault` 映射
- [ ] `behavior_state_service` 消费真实 `done / interrupted` 结果
- [ ] BLE / WS 外部 `sys.ack / sys.nack` 细节对齐
- [ ] UI 或更高层状态展示

## 5. 现场记录要求

每次 Field Review 至少记录：

- 日期 / 分支 / commit
- ESP32 固件版本
- STM32 固件版本
- 串口参数
- 成功链路
- 失败链路
- 对应日志片段
- 是否需要补协议文档 / 风险清单 / TODO

若出现新的链路问题，必须同步回：

- [IMPLEMENTATION_STATUS.md](./IMPLEMENTATION_STATUS.md)
- [IMPLEMENTATION_TODO.md](./IMPLEMENTATION_TODO.md)
- [RISK_REGISTER.md](./RISK_REGISTER.md)
