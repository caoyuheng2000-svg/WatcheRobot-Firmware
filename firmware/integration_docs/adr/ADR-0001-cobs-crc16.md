# ADR-0001：板内 UART 传输层采用 COBS + CRC16

## Status

Accepted

## Context

`ESP32 <-> STM32` 板内 UART 链路需要满足：

- 能在任意错帧后快速恢复同步
- 不依赖复杂分片
- 在 `STM32F103` 级资源上也能稳定实现

如果只用 `magic` 扫描，串口噪声、截断帧和粘包时重同步口径较弱。
如果直接上文本协议，可读性更强，但效率、字段约束和恢复性更差。

## Decision

传输层采用：

- `COBS`
- 末尾 `0x00 delimiter`
- `CRC16-CCITT-FALSE`

## Consequences

优点：

- 任何坏帧只影响当前帧
- 重同步简单
- 实现和测试成本低
- 对 F103 资源友好

代价：

- 抓包可读性不如文本协议
- 需要专门的编解码测试

## Related

- `../STM32_UART_PROTOCOL.md`
- `../TDD_EXECUTION_PLAN.md`
