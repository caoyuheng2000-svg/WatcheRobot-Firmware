# STM32 协处理器重构总体方案（v2.0.0 基线）

> 目的：冻结 `v2.0.0` 的总体重构边界，明确 ESP32 与 STM32 的职责分工、启动恢复口径、风险约束与实施阶段。
>
> 关系说明：本文是系统设计真源；板内串口协议的唯一真源见 `STM32_UART_PROTOCOL.md`。对外网络协议仍以 `../s3/docs/COMM_PROTOCOL_FREEZE.md` 与 `../s3/docs/BLE_GATT_PROTOCOL_BRIDGE.md` 为基线。

## 1. 目标与范围

### 1.1 重构目标

本轮重构将当前“ESP32 直接驱动舵机和部分输入设备”的结构，调整为“ESP32 主控 + STM32 实时协处理器”的双 MCU 架构。

STM32 接管以下能力：

- 2 路 PWM 舵机驱动
- TTP223 触摸输入采集与去抖
- 6 轴 IMU 采集与姿态/运动事件预处理
- 3 轴地磁传感器采集与状态预处理
- WS2812 灯珠驱动与效果执行

ESP32 保留以下能力：

- UI / 显示 / 输入框架
- BLE / WebSocket / Wi-Fi / 云连接
- 行为状态机与动作编排
- 业务状态流转
- 协处理器链路管理、故障恢复与降级处理

### 1.2 本轮不做

以下内容不属于 `v2.0.0` 第一轮冻结范围：

- STM32 固件升级协议
- 高速原始 IMU 连续数据流
- WS2812 像素级逐点推流
- STM32 本地高层自治行为编排
- 对外网络协议改版

## 2. 现状与问题

当前 ESP32 架构中，舵机控制仍是本地直连：

- `control_ingress -> hal_servo`
- `behavior_state_service -> hal_servo_move_sync()`
- `BLE / WS` 层直接围绕 `ctrl.servo.angle` 和单次动作提交语义构建

当前结构的问题：

- 动作执行与业务控制耦合过深，本地 HAL 默认“提交成功即本机可执行”
- 行为状态机、BLE、WS 都可能同时驱动舵机，取消与抢占语义仅在本地队列内成立
- 触摸、IMU、地磁、LED 尚未统一纳入一条板内设备链路，后续扩展容易继续散落在 ESP32 各模块
- 一旦引入 STM32，如果继续沿用“上层直接调用本地硬件 HAL”的心智模型，会把链路超时、远端拒绝、掉线恢复等复杂性泄漏到现有业务路径

## 3. 目标架构

目标架构如下：

```text
BLE / WS / UI / Cloud
        |
        v
  control_ingress
        |
        +----------------------+
        |                      |
        v                      v
behavior_state_service   mcu_sensor_service
        |                      |
        v                      v
 mcu_motion_service      latest-state cache / event dispatch
        |                      |
        +----------+-----------+
                   |
                   v
             mcu_link_service
                   |
             UART @ 921600
                   |
                   v
              STM32 协处理器
        +--------+--------+--------+--------+
        |                 |                 |
        v                 v                 v
     舵机驱动         传感器预处理         LED 驱动
```

核心原则：

- ESP32 负责“决策和编排”
- STM32 负责“执行和预处理”
- ESP32 不下发插值点，只下发目标命令
- STM32 不做高层状态机，只执行命令并回传结果/状态

## 4. 职责分层

### 4.1 ESP32 侧服务边界

以下服务边界在 `v2.0.0` 冻结：

- `mcu_link_init()`
  - 初始化 UART、接收缓冲、协议编解码、链路状态机
- `mcu_link_is_ready()`
  - 返回协处理器是否已完成握手、基线同步并可接收业务命令
- `mcu_motion_submit(...)`
  - 提交舵机动作命令，不等待执行完成
- `mcu_motion_stop(...)`
  - 提交动作停止/取消请求
- `mcu_led_submit(...)`
  - 提交 LED 静态颜色或效果命令
- `mcu_sensor_get_latest_*()`
  - 获取最新的 IMU / 地磁状态快照

冻结的设计要求：

- `control_ingress` 继续作为 BLE / WS / 上层业务的统一入口
- `hal_servo_*` 保留为兼容层，但内部只做参数校验、限幅和转发，不再直接做本地 PWM
- `behavior_state_service` 继续保留现有动作资源模型，但向下只提交“目标角度 + 时长”，不再直接假设本地硬件立即可达
- ESP32 内部需要区分 `coprocessor_link_ready` 与 `coprocessor_ready`
  - `coprocessor_link_ready` 表示握手完成、协议版本和能力位校验通过
  - `coprocessor_ready` 表示基线同步和恢复流程完成，可以放行业务命令

### 4.2 STM32 侧职责边界

STM32 在 `v2.0.0` 中的职责固定为：

- 舵机动作执行
  - 限幅、插值、完成回执、故障上报
- 触摸预处理
  - 去抖、按压/释放/长按事件
- IMU 预处理
  - 姿态估计、运动事件判定
- 地磁预处理
  - 航向状态、扰动状态、变化事件
- LED 执行
  - 静态颜色与基础效果执行

STM32 明确不负责：

- BLE / Wi-Fi / WebSocket
- UI 状态逻辑
- 行为状态机
- 云端协议

## 5. 启动、恢复与降级

### 5.1 启动流程

`v2.0.0` 启动流程冻结为：

1. ESP32 启动基础系统、显示、BLE / Wi-Fi 等本地能力
2. `mcu_link_service` 初始化 UART 与收发缓冲
3. ESP32 发起握手请求
4. STM32 返回版本、能力位与传感器位图
5. ESP32 标记 `coprocessor_link_ready`
6. ESP32 执行基线同步与恢复
   - 若支持 `snapshot`，先发 `SNAPSHOT_REQ` 并恢复当前舵机位置、LED 模式与传感器健康位
   - 传感器流配置在 v1 中不单独下发命令，直接采用 `HELLO_RSP.default_stream_profile`
   - 若不支持 `snapshot` 且本地没有可信缓存，ESP32 必须下发固定安全基线，而不是依赖 STM32 上电默认态
   - 固定安全基线在 v1 中冻结为：舵机进入板级安全停泊位、LED 关闭、传感器流采用 `default_stream_profile`
   - ESP32 只在本地缓存与 STM32 快照不一致时补发舵机/LED 基线状态
7. ESP32 标记 `coprocessor_ready`
8. 业务层开始允许动作与灯效命令

### 5.2 恢复流程

运行中掉线后，ESP32 必须：

- 进入 `coprocessor_degraded`
- 拒绝新的舵机与 LED 控制命令
- 保留 UI、BLE、WS、云连接可用
- 自动重试链路恢复
- 链路恢复后重新走一轮握手、快照恢复与基线同步

### 5.3 降级口径

降级口径冻结为：

- 协处理器离线不拖垮主系统
- 舵机/LED/传感器能力按模块失效，不扩展成整机崩溃
- 业务层只能看到“能力不可用 / busy / failed”，不能直接感知底层串口细节

## 6. 风险与约束

### 6.1 STM32F1 资源边界

若协处理器使用 `STM32F103`：

- 可支持 2 路舵机、TTP223、基础 IMU 姿态、地磁状态与 WS2812 基础效果
- 不建议在 v1 同时承担高频原始流、复杂滤波、本地脚本化灯效和升级通道
- 无 FPU 是硬约束，因此协议中统一使用定点整数，不走浮点线传

### 6.2 ESP32 背压风险

ESP32 当前已有 BLE、WS、UI、行为状态机与相机路径，因此新增协处理器链路必须遵守：

- 控制优先于遥测
- 状态类上报使用 `latest-state-wins`
- ACK / NACK / DONE / FAULT 与传感器状态流分开处理
- 不能因为 IMU 或地磁周期状态上报而阻塞动作命令

### 6.3 命令风暴风险

行为状态机、BLE、WS 都可能同时提交舵机命令。为避免命令风暴：

- 业务层只提交粗粒度动作
- STM32 本地负责插值
- 取消与抢占语义必须通过协议显式表达
- ESP32 不允许通过高频小步命令模拟本地平滑动作

## 7. 分阶段实施

`v2.0.0` 第一阶段实施顺序冻结为：

1. 文档冻结
   - 冻结总体架构基线
   - 冻结 UART 协议真源
2. ESP32 链路骨架
   - 引入 `mcu_link_service`
   - 接入握手、心跳、ACK/NACK
3. STM32 协议骨架
   - 跑通 UART 收发、CRC、命令解析
4. 动作链路
   - 舵机动作、停止、完成事件
5. 传感器链路
   - 触摸、IMU、地磁状态与事件
6. LED 链路
   - 静态颜色与基础效果
7. 联调收口
   - 掉线恢复
   - 背压验证
   - 故障注入与回归

## 8. 验收口径

`v2.0.0` 第一轮文档和实现应满足：

- 实现者仅阅读本文与 `STM32_UART_PROTOCOL.md`，即可知道 ESP32 与 STM32 的职责和边界
- ESP32 侧接口名、状态名、错误口径在文档与实现中保持一致
- UART 协议不再依赖临时口头约定
- 后续代码实现不需要再重新设计握手、ACK/DONE、频率和背压策略

## 9. Source of Truth

本方案的本地真源如下：

- 当前外部通信基线：`../s3/docs/COMM_PROTOCOL_FREEZE.md`
- 当前 BLE 本地桥接语义：`../s3/docs/BLE_GATT_PROTOCOL_BRIDGE.md`
- 当前相机协处理器设计经验：`../s3/docs/COPROC_COMM_DEV_DESIGN.md`
- 本轮板内 UART 协议真源：`STM32_UART_PROTOCOL.md`
