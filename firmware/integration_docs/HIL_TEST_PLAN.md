# STM32 协处理器 HIL 与合并前检查计划

> 目的：统一 mock、格式、编译、bench 和真实串口联调的验证流程。

## 合并前本地检查

在 `v2.0.0-refactor` 上执行：

```powershell
git diff --check 5929987..HEAD
python -m pytest tools\tests
powershell -ExecutionPolicy Bypass -File C:\Users\50533\.codex\skills\watche-dual-mcu-bringup\scripts\run-dual-mcu-bringup.ps1 -SkipStm32Build -SkipStm32Flash -SkipEsp32Flash -SkipSession
```

对 CI 范围的 C/H 文件执行格式检查：

```powershell
$clang = 'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\Llvm\bin\clang-format.exe'
$files = git diff --name-only 5929987..HEAD -- firmware/s3/components firmware/s3/main | Where-Object { $_ -match '\.(c|h)$' }
& $clang --dry-run --Werror @files
```

CI 中对应的 Linux 检查使用 `clang-format-18 --dry-run --Werror`。

## Mock 与工具测试

必须保持以下工具可运行：

- `tools/stm32_uart_hil.py`
- `tools/stm32_uart_fault_inject.py`
- `tools/power_5v_toggle_hil.py`

最低 Python 回归入口：

```powershell
python -m pytest tools\tests
```

## ESP32 编译

推荐使用技能脚本，而不是手工拼 ESP-IDF 环境：

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\50533\.codex\skills\watche-dual-mcu-bringup\scripts\run-dual-mcu-bringup.ps1 -SkipStm32Build -SkipStm32Flash -SkipEsp32Flash -SkipSession
```

该命令只编译 ESP32，默认 build dir 为：

- `firmware\s3\build-s3-c-codex`

## 真实 bench 拓扑

```text
PC
 |\
 | \-- ESP32 log / flash port
 |
 +---- STM32 debug or CLI port

ESP32 <---- UART 921600 ----> STM32
```

默认设备别名：

- ESP32：`s3-c`
- STM32：`stm32-c`

## bench 固定顺序

1. 链路启动
   - ESP32 日志出现 `MCU link scaffold ready`
   - `HELLO_REQ` 发出
   - STM32 返回 `HELLO_RSP`
   - ESP32 进入 `READY`
2. 动作链路
   - 下发 `SERVO_MOVE`
   - 观察 `ACK`
   - 观察 `MOTION_DONE`
   - 下发 `SERVO_STOP`
3. 灯效链路
   - 下发 `LED_SET_STATIC` 或 `LED_SET_EFFECT`
   - 观察 `ACK`
   - 观察 `LED_DONE`
4. POWER 5V 链路
   - 下发 `POWER_5V_ENABLE / POWER_5V_DISABLE`
   - 判据是 STM32 侧舵机 / WS2812 LED 5V rail 或 IP5306 输出端变化
   - ESP32 USB-C 日志串口继续在线是预期现象
5. 传感器链路
   - 观察 `TOUCH_EVENT`
   - 观察 `MAG_STATE`
   - `IMU_STATE` 只在问询或姿态变化事件场景单独验证
6. 恢复链路
   - 复位 STM32
   - ESP32 回到 `READY`
   - 恢复后 motion / led / sensor 至少各跑通 1 条链路

## 标准压力场景

- 固定为 `SERVO_MOVE 5Hz + TOUCH_EVENT burst + MAG_STATE 2Hz`
- 当前标准压力场景不要求持续 `IMU_STATE`
- stress build 在 `READY` 后等待 `1s` settle 再开始发送
- 收尾必须出现 `MCU_OBS evt=stress_stats reason=drain_complete`
- `servo_submit_count / motion_ack_count / motion_done_count` 必须对齐

## 通过标准

- 连续运行 `10 min` 不出现未恢复卡死。
- 错帧注入后链路能自动重同步。
- `ACK timeout` 不持续上升。
- `dropped_state_count` 可增长，但 `ACK / DONE / FAULT` 不应明显丢失。
- STM32 复位后 ESP32 能重新回到 `READY`。

## 日志记录要求

每次真实 bench 至少记录：

- 日期、分支、commit
- ESP32 固件版本
- STM32 固件版本
- 设备别名和串口
- 成功链路
- 失败链路
- 对应日志目录
- 是否需要更新协议、风险或 TODO

## 最新已知通过样本

截至 `2026-04-19`，no-IMU 标准压力场景通过样本为：

- `D:\GithubRep\WatcheRobot-Firmware\.codex\local\logs\50533\stm32-uart2-stress-no-imu\s3-c--stm32-c\session-20260419T053521Z`

关键指标：

- `servo_submit_count=2969`
- `motion_ack_count=2969`
- `motion_done_count=2969`
- `touch_rx_count=1186`
- `mag_rx_count=1187`
- `ack_timeout_count=0`
- `crc_error_count=0`
- `motion_done_fault_count=0`
- `reconnect_count=0`
