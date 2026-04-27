# v2.0.0 STM32 协处理器重构文档索引

> 目的：给 `v2.0.0` 重构建立统一的文档入口，明确每份文档的职责边界、阅读顺序与真源关系。

## 1. 阅读顺序

建议按以下顺序阅读：

1. [STM32_COPROC_REFACTOR_PLAN.md](./STM32_COPROC_REFACTOR_PLAN.md)
2. [STM32_UART_PROTOCOL.md](./STM32_UART_PROTOCOL.md)
3. [IMPLEMENTATION_STATUS.md](./IMPLEMENTATION_STATUS.md)
4. [IMPLEMENTATION_TODO.md](./IMPLEMENTATION_TODO.md)
5. [FIELD_REVIEW_TODO.md](./FIELD_REVIEW_TODO.md)
6. [TDD_EXECUTION_PLAN.md](./TDD_EXECUTION_PLAN.md)
7. [RISK_REGISTER.md](./RISK_REGISTER.md)
8. [HIL_TEST_PLAN.md](./HIL_TEST_PLAN.md)
9. [BRANCH_WORKTREE_PLAN.md](./BRANCH_WORKTREE_PLAN.md)
10. [adr/](./adr)

## 2. 文档职责

### 2.1 真源文档

- [STM32_COPROC_REFACTOR_PLAN.md](./STM32_COPROC_REFACTOR_PLAN.md)
  - 系统分层与职责边界唯一真源
- [STM32_UART_PROTOCOL.md](./STM32_UART_PROTOCOL.md)
  - 板内 UART 协议唯一真源

### 2.2 执行文档

- [IMPLEMENTATION_STATUS.md](./IMPLEMENTATION_STATUS.md)
  - 当前集成分支已经落到哪一步、哪些检查已经通过
- [IMPLEMENTATION_TODO.md](./IMPLEMENTATION_TODO.md)
  - 已冻结但尚未实施的下一阶段待办
- [FIELD_REVIEW_TODO.md](./FIELD_REVIEW_TODO.md)
  - 首次真实 STM32 串口调试前，ESP32 侧仍需完成的检查点和 bench 清单
- [TDD_EXECUTION_PLAN.md](./TDD_EXECUTION_PLAN.md)
  - 测试驱动实施节奏、阶段出口和测试文件落点
- [HIL_TEST_PLAN.md](./HIL_TEST_PLAN.md)
  - 真机联调、串口拓扑、脚本组织和回归矩阵

### 2.3 风险与管理文档

- [RISK_REGISTER.md](./RISK_REGISTER.md)
  - 风险编号、触发条件、缓解措施、退出条件
- [BRANCH_WORKTREE_PLAN.md](./BRANCH_WORKTREE_PLAN.md)
  - 分支策略、工作树规划、合并规则、并行开发边界

### 2.4 ADR

- [ADR-0001-cobs-crc16.md](./adr/ADR-0001-cobs-crc16.md)
  - 为什么使用 `COBS + CRC16`
- [ADR-0002-latest-state-wins.md](./adr/ADR-0002-latest-state-wins.md)
  - 为什么状态上报采用 `latest-state-wins`

## 3. 写作规则

- 只有 `STM32_UART_PROTOCOL.md` 可以定义协议字段、消息号、错误码、默认频率。
- 只有 `STM32_COPROC_REFACTOR_PLAN.md` 可以定义 ESP32 / STM32 职责边界和系统级启动恢复口径。
- `TDD_EXECUTION_PLAN.md` 只能引用协议与架构真源，不得重复定义协议字段。
- `RISK_REGISTER.md` 通过风险编号引用问题，不复制大段背景。
- `HIL_TEST_PLAN.md` 只定义怎么测，不重新定义为什么这么设计。
- ADR 只记录关键决策，不承担教程或计划职能。

## 4. 当前范围

本轮文档冻结覆盖：

- STM32 协处理器总体架构
- ESP32 <-> STM32 UART 协议
- 当前实现进度与下一阶段待办
- TDD 执行节奏
- 风险清单
- HIL 联调计划
- 分支与 Worktree 安排

本轮文档不覆盖：

- STM32 固件升级协议
- 具体 C 结构体布局
- 上位机 GUI 工具
- 对外 BLE / WS 协议改版

## 5. 当前实现里程碑

截至 `2026-04-15`，`v2.0.0-refactor` 已落到以下检查点：

- 文档真源、TDD 计划、风险清单、HIL 计划均已冻结
- ESP32 侧 `mcu_link` 已有协议骨架、UART scaffold、运行时 poll 和 `HELLO_RSP / ACK / NACK / FAULT` 最小消费路径
- `hal_servo` 已退化为协处理器兼容入口，本地 PWM 后端已移除，`GPIO19/20` 已切到运行时 UART
- `mcu_motion_service` / `mcu_led_service` 现在只在 `READY` 后放行业务帧，链路未就绪时返回显式错误
- 本地自动化检查、mock HIL、故障注入和 `COM28` 板级 smoke 已通过，详见 [IMPLEMENTATION_STATUS.md](./IMPLEMENTATION_STATUS.md)

## 6. 相关参考

- 当前外部协议基线：`../s3/docs/COMM_PROTOCOL_FREEZE.md`
- 当前 BLE 桥接语义：`../s3/docs/BLE_GATT_PROTOCOL_BRIDGE.md`
- 当前相机协处理器设计经验：`../s3/docs/COPROC_COMM_DEV_DESIGN.md`
