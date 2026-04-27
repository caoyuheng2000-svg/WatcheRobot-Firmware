# ADR-0002：状态上报采用 latest-state-wins

## Status

Accepted

## Context

ESP32 当前同时承担：

- UI
- BLE
- WebSocket
- 行为状态机
- 视觉协处理器路径

STM32 接入后，IMU 和地磁会持续上报状态。如果为状态流维护长队列，容易导致：

- ACK 被饿死
- 内存被状态积压吞掉
- 延迟抬高但状态价值下降

## Decision

对周期状态帧采用：

- `latest-state-wins`

具体做法：

- `IMU_STATE` 与 `MAG_STATE` 不排长队列
- 新状态覆盖旧状态
- 事件、ACK、DONE、FAULT 走更高优先级通道

## Consequences

优点：

- 延迟受控
- 控制命令优先级清晰
- 非常适合姿态和状态类数据

代价：

- 不能保证每个状态采样点都被上层消费
- 需要额外维护 `dropped_state_count`

## Related

- `../STM32_UART_PROTOCOL.md`
- `../RISK_REGISTER.md`
- `../HIL_TEST_PLAN.md`
