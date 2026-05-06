# BLE 配网持久化与异常凭据验证执行记录

## 基本信息

| 字段 | 内容 |
|---|---|
| 测试记录编号 | issue31-runXX |
| 固件 commit | |
| 固件版本 | |
| 设备 / 板卡 | |
| 串口号 | |
| BLE 工具 / 版本 | |
| AP / 路由器 | |
| 测试人员 | |
| 测试日期 | |
| 结论 | PASS / FAIL / BLOCKED |

## 测试环境

| 项目 | 内容 |
|---|---|
| 正确 SSID | |
| 正确密码 | 不建议把真实共享密码写入会提交的记录。 |
| 错误密码形式 | |
| AP 控制方式 | 路由器开关 / 手机热点 / 其他 |
| 串口日志文件 | |
| BLE 证据文件 | |

## 用例结果

| 编号 | 结果 | BLE 请求 | BLE 响应 / Notify | 串口证据 | 备注 |
|---|---|---|---|---|---|
| TC-01 初始状态读取 | PASS / FAIL / BLOCKED | | | | |
| TC-02 正确 BLE 配网 | PASS / FAIL / BLOCKED | | | | |
| TC-03 掉电持久化 | PASS / FAIL / BLOCKED | | | | |
| TC-04 清除凭据 | PASS / FAIL / BLOCKED | | | | |
| TC-05 错误密码 | PASS / FAIL / BLOCKED | | | | |
| TC-06 AP 不可达 | PASS / FAIL / BLOCKED | | | | |

## 详细记录

### TC-01 初始状态读取

步骤：

1. 清除已保存 Wi-Fi 凭据。
2. 重启设备。
3. 连接 BLE。
4. 打开 notify。
5. 发送 `cfg.wifi.get`。

BLE 观察：

```text

```

串口日志：

```text

```

结论：

### TC-02 正确 BLE 配网

步骤：

1. 连接 BLE。
2. 打开 notify。
3. 发送正确 `cfg.wifi.set`。
4. 等待 Wi-Fi 状态和 IP 获取。

BLE 观察：

```text

```

串口日志：

```text

```

结论：

### TC-03 掉电持久化

步骤：

1. TC-02 成功后，断电重启设备。
2. 不重新下发配网命令。
3. 观察串口日志和 BLE Wi-Fi 状态。

BLE 观察：

```text

```

串口日志：

```text

```

结论：

### TC-04 清除凭据

步骤：

1. 连接 BLE。
2. 发送 `cfg.wifi.clear`。
3. 重启设备。
4. 发送 `cfg.wifi.get`。

BLE 观察：

```text

```

串口日志：

```text

```

结论：

### TC-05 错误密码

步骤：

1. 连接 BLE。
2. 下发正确 SSID 和错误密码。
3. 观察连接失败。
4. 发送 `cfg.wifi.get` 或 `cfg.wifi.clear`，确认 BLE 仍可用。

BLE 观察：

```text

```

串口日志：

```text

```

结论：

### TC-06 AP 不可达

步骤：

1. 保存正确凭据。
2. 关闭 AP 或让 AP 不可达。
3. 重启设备或等待重连。
4. 恢复 AP 并验证可恢复连接。

BLE 观察：

```text

```

串口日志：

```text

```

结论：

## 最终结论

总结：

遗留问题：

附件：
