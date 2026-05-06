# BLE 配网持久化与异常凭据验证

> 快速入口：详细自动化测试说明见 `BLE_WIFI_GUI_TESTER_GUIDE.md`。首次运行可执行 `.\run_gui_tester.ps1 -InstallDeps`，后续执行 `.\run_gui_tester.ps1`。

关联 issue: https://github.com/Ro-In-AI/WatcheRobot-Firmware/issues/31

## 测试目标

验证 ESP32-S3 固件在 BLE 配网场景下可以可靠完成：

- 通过 BLE 读取当前 Wi-Fi 状态。
- 通过 BLE 下发 Wi-Fi SSID 和密码。
- 正确凭据可保存，断电重启后自动恢复连接。
- 通过 BLE 清除已保存凭据。
- 错误密码或 AP 不可用时，系统不会重启、不会 WDT、不会进入假 `connected` 状态，BLE 仍可继续操作。

## 需要准备

- WatcheRobot ESP32-S3 设备。
- USB 数据线和串口日志环境。
- 可控 Wi-Fi AP，例如路由器或手机热点。
- 一组正确 Wi-Fi 凭据。
- 一组错误密码。
- BLE 调试工具，例如 nRF Connect 或 LightBlue。

## 可选工具

- ESP-IDF：需要本地编译或烧录时使用。
- Python `bleak`：后续需要自动化 BLE 写入时再安装。
- USB 串口驱动：电脑识别不到 COM 口时安装。

## BLE 命令

服务和特征：

- Service UUID: `0x00FF`
- Characteristic UUID: `0xFF01`
- 建议使用 write with response。
- 建议打开 notify，用于接收异步 Wi-Fi 状态。

读取状态：

```json
{"type":"cfg.wifi.get","data":{"command_id":"wifi-get-001"}}
```

下发凭据：

```json
{"type":"cfg.wifi.set","data":{"ssid":"YOUR_SSID","password":"YOUR_PASSWORD","command_id":"wifi-set-001"}}
```

清除凭据：

```json
{"type":"cfg.wifi.clear","data":{"command_id":"wifi-clear-001"}}
```

重点观察状态：

- `unconfigured`
- `connecting`
- `disconnected`
- `connected`

## 串口日志命令示例

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\firmware\s3
.\tools\flash-monitor.ps1 COM6 -MonitorSeconds 180 -MonitorLogPath D:\GithubRep\BLE配网持久化与异常凭据验证\logs\issue31-run01.log
```

如果固件已经烧录，只需要看日志，可在 ESP-IDF 环境里运行：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\firmware\s3
idf.py -p COM6 monitor
```

## 测试用例

| 编号 | 场景 | 步骤 | 预期结果 | 证据 |
|---|---|---|---|---|
| TC-01 | 初始状态读取 | 清除凭据，重启，连接 BLE，发送 `cfg.wifi.get`。 | 状态为 `unconfigured` 或未连接；无重启、无 WDT。 | BLE 响应、串口日志。 |
| TC-02 | 正确 BLE 配网 | 下发正确 SSID/PASS，保持 notify 打开。 | 返回 ack，状态从 `connecting` 到 `connected`，设备获取 IP。 | BLE 响应、`Got IP` 日志。 |
| TC-03 | 掉电持久化 | TC-02 成功后断电重启，不重新配网。 | 设备使用已保存凭据自动连接，最终 `connected`。 | 重启日志、状态通知。 |
| TC-04 | 清除凭据 | 发送 `cfg.wifi.clear`，重启，读取状态。 | 不再使用旧 SSID/PASS，状态变为 `unconfigured`。 | BLE ack/status、清除日志。 |
| TC-05 | 错误密码 | 下发正确 SSID 和错误密码。 | 不进入 `connected`，失败原因可观察，BLE 仍可继续 `get/clear/set`。 | 断连 reason 日志、BLE 后续响应。 |
| TC-06 | AP 不可达 | 保存正确凭据后关闭 AP，重启或等待重连。 | 保持 `disconnected/connecting` 可恢复状态；无重启、无 WDT、无假连接；AP 恢复后可连接。 | AP 关闭/恢复前后日志。 |

## 日志关键字

```text
BLE WiFi provisioning request received
Saved WiFi credentials
Saved WiFi credentials without immediate connect
Got IP
Disconnected from AP
reason=
Stored WiFi credentials cleared
WIFI_CONNECTED
WIFI_DISCONNECTED
WIFI_UNCONFIGURED
```

## 文件夹说明

- `README.md`：测试说明和用例清单。
- `execution-record-template.md`：执行记录模板。
- `ble_wifi_gui_tester.py`：Python GUI 半自动测试工具。
- `requirements.txt`：GUI 工具依赖。
- `run_gui_tester.ps1`：Windows 启动脚本。
- `records/`：存放填写后的测试记录。
- `logs/`：存放串口日志和 BLE 证据。

## Python GUI 半自动测试

这个测试可以用 Python 自动化一大部分：BLE 扫描、连接、写入 `cfg.wifi.*` 命令、接收 notify、串口日志抓取、生成 Markdown 执行记录都可以自动完成。

仍需人工配合的动作：

- 断电重启设备。
- 关闭或恢复 AP / 手机热点。
- 判断设备实际是否重启、屏幕/UI 是否异常。

首次运行前安装依赖：

```powershell
cd D:\GithubRep\BLE配网持久化与异常凭据验证
.\run_gui_tester.ps1 -InstallDeps
```

之后直接启动：

```powershell
cd D:\GithubRep\BLE配网持久化与异常凭据验证
.\run_gui_tester.ps1
```

推荐执行顺序：

1. 填写 Run ID、SSID、正确密码、错误密码。
2. 选择串口并点击“开始串口日志”。
3. 点击“扫描 BLE”，选择设备后点击“连接 BLE”。
4. 依次执行 TC-01 到 TC-06。
5. 每条用例完成后点击 PASS 或 FAIL。
6. 点击“生成记录”，结果会写入 `records/`，串口日志会写入 `logs/`。
