# BLE 配网持久化与异常凭据验证自动化测试说明

## 1. 脚本用途

本目录用于验证 WatcheRobot ESP32-S3 固件在 BLE Wi-Fi 配网场景下的稳定性、持久化能力和异常凭据恢复能力，关联 issue #31。

核心脚本是 `ble_wifi_gui_tester.py`，它提供一个 Windows GUI 半自动测试工具。脚本会自动完成 BLE 扫描、连接、GATT 写入、Notify 接收、串口日志采集、关键日志模式识别、测试结论建议和 Markdown 记录生成；断电重启、关闭/恢复 AP 这类物理动作仍需要人工配合。

## 2. 目录内容

- `ble_wifi_gui_tester.py`：主测试工具，Tkinter GUI，集成 BLE、串口和测试用例流程。
- `run_gui_tester.ps1`：Windows 启动脚本，可选择安装 Python 依赖后启动 GUI。
- `requirements.txt`：Python 依赖，目前包含 `bleak` 和 `pyserial`。
- `README.md`：测试目标、BLE 命令、用例设计和基础操作说明。
- `execution-record-template.md`：人工填写版执行记录模板。
- `logs/`：串口日志输出目录。
- `records/`：自动生成的 Markdown 测试记录目录。

## 3. 自动化脚本做了什么

### 3.1 BLE 自动化

脚本通过 `bleak` 操作 BLE：

- 扫描附近 BLE 设备，默认寻找名称为 `ESP_ROBOT` 的设备。
- 如果扫描结果中存在地址 `80:B5:4E:EF:B1:2A`，也会作为目标设备处理。
- 连接目标设备。
- 对特征 `0xFF01` 开启 Notify。
- 向 `0xFF01` 写入 JSON 命令，使用 write with response。
- 接收 Notify 数据并显示为 `RX ...` 日志。

BLE UUID：

- Service UUID：`0x00FF`
- Characteristic UUID：`0000ff01-0000-1000-8000-00805f9b34fb`

脚本会发送的主要命令：

```json
{"type":"cfg.wifi.get","data":{"command_id":"wifi-get-001"}}
```

```json
{"type":"cfg.wifi.set","data":{"ssid":"YOUR_SSID","password":"YOUR_PASSWORD","command_id":"wifi-set-001"}}
```

```json
{"type":"cfg.wifi.clear","data":{"command_id":"wifi-clear-001"}}
```

### 3.2 串口日志自动化

脚本通过 `pyserial` 操作串口：

- 自动枚举本机 COM 口。
- 默认优先选择 `COM6`，如果没有 `COM6` 则使用用户选择的串口。
- 默认波特率为 `115200`。
- 启动串口读取线程。
- 每行串口日志自动加本机时间戳。
- 日志写入 `logs/{Run ID}-serial.log`。
- GUI 右侧实时显示串口日志。
- 支持手动插入用例标记，便于回看日志时定位 TC-01 至 TC-06。

### 3.3 用例自动执行

点击 GUI 中的“自动执行今日计划”后，脚本会执行 issue #31 全量计划：

1. 自动启动串口日志。
2. 自动扫描并连接 `ESP_ROBOT`。
3. 执行 TC-04：先清除已有 Wi-Fi 凭据。
4. 执行 TC-01：断电重启后读取初始 Wi-Fi 状态。
5. 执行 TC-02：下发正确 SSID 和密码，等待连接成功或 Got IP。
6. 执行 TC-03：人工断电重启后读取 Wi-Fi 状态，验证凭据持久化。
7. 再次执行 TC-04：清除凭据并验证旧凭据不再被复用。
8. 执行 TC-05：下发错误密码，确认不会假连接、不会 WDT/Panic，BLE 仍可继续操作。
9. 执行 TC-06：验证 AP 不可达和恢复后的状态变化。
10. 自动生成 Markdown 测试记录。

其中，脚本会弹窗要求人工确认的动作包括：

- 手动断电重启设备。
- 再次断电重启以验证清除后的状态。
- 关闭指定 AP 或手机热点。
- 恢复 AP 或手机热点。

### 3.4 TC-02 专项排查

GUI 里有“只排查 TC-02”按钮，用于只验证正确配网链路：

- 启动串口日志。
- 连接 BLE。
- 先读取当前 Wi-Fi 状态作为 baseline。
- 下发正确 SSID 和密码。
- 等待 `WIFI_CONNECTED`、`"status":"connected"` 或 `GOT IP`。
- 结束后再次发送 `cfg.wifi.get`。
- 如果超时，会把结果标记为 `BLOCKED`，接手人需要结合 BLE 日志和串口日志判断是 AP、密码、固件状态机还是环境问题。

### 3.5 自动判定逻辑

脚本会监听 BLE 日志和串口日志中的关键字，并给出 PASS/FAIL/BLOCKED 建议：

- 出现 `WIFI_UNCONFIGURED` 或 `"status":"unconfigured"`：TC-01 或 TC-04 倾向 PASS。
- 出现 `WIFI_CLEARED` 或 `Stored WiFi credentials cleared`：TC-04 倾向 PASS。
- 出现 `WIFI_CONNECTED`、`"status":"connected"` 或 `GOT IP`：TC-02、TC-03 或 TC-06 倾向 PASS。
- 出现 `WDT`、`PANIC`、`Guru Meditation` 或 `ASSERT`：当前用例倾向 FAIL。
- 出现认证失败、错误密码、AP 不可达相关日志：TC-05 可以作为异常凭据可恢复的证据，但需要确认 BLE 后续仍可用。
- 等待指定关键字超时：标记为 `BLOCKED`，表示需要人工复核环境或固件行为。

注意：自动判定只是建议，最终结论仍需要测试人员根据 BLE 响应、串口日志和现场现象确认。

### 3.6 记录生成

脚本会生成两类证据：

- 串口日志：`logs/{Run ID}-serial.log`
- Markdown 记录：`records/{Run ID}.md`

Markdown 记录会包含：

- 测试记录编号。
- 测试日期。
- BLE 设备名称和地址。
- SSID。
- 正确密码和错误密码脱敏显示为 `******`。
- 串口日志路径。
- 自动结论。
- TC-01 至 TC-06 的结果。
- BLE / 测试日志。
- 串口日志末尾摘录。

## 4. 需要的环境和工具

### 4.1 硬件

- WatcheRobot ESP32-S3 设备一台。
- USB 数据线，用于供电、烧录和串口日志。
- 可控 Wi-Fi AP，例如路由器或手机热点。
- 一组正确 Wi-Fi SSID 和密码。
- 一组错误密码，用于异常凭据测试。
- 可执行断电重启的供电方式，建议使用可拔插 USB 或可控电源。

### 4.2 PC 环境

- Windows 电脑。
- Python 3.9 或更新版本，建议 Python 3.11。
- 能访问 BLE 的 Windows 蓝牙适配器。
- USB 串口驱动已安装，设备能识别为 COM 口。
- PowerShell 可执行脚本。

### 4.3 Python 依赖

依赖写在 `requirements.txt`：

```text
bleak>=0.22.3
pyserial>=3.5
```

安装方式：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\tools\BLE配网持久化与异常凭据验证
.\run_gui_tester.ps1 -InstallDeps
```

也可以手动安装：

```powershell
python -m pip install -r requirements.txt
```

### 4.4 固件前置条件

设备固件需要支持以下 BLE Wi-Fi 配网协议：

- BLE 广播名称建议为 `ESP_ROBOT`。
- Service UUID：`0x00FF`。
- Characteristic UUID：`0xFF01`。
- 支持 write with response。
- 支持 notify 返回 Wi-Fi 状态。
- 支持 `cfg.wifi.get`。
- 支持 `cfg.wifi.set`。
- 支持 `cfg.wifi.clear`。
- 串口日志中最好能输出 Wi-Fi 状态、断连 reason、Got IP、WDT/Panic 等关键信息。

## 5. 启动方式

首次运行，安装依赖并启动 GUI：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\tools\BLE配网持久化与异常凭据验证
.\run_gui_tester.ps1 -InstallDeps
```

后续运行：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\tools\BLE配网持久化与异常凭据验证
.\run_gui_tester.ps1
```

如果 PowerShell 执行策略阻止脚本运行，可以临时使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_gui_tester.ps1
```

## 6. 推荐操作流程

1. 确认设备已烧录待测固件并正常上电。
2. 打开 AP 或手机热点，确认 SSID 和正确密码可用。
3. 进入本目录并启动 GUI。
4. 填写 Run ID、SSID、正确密码、错误密码。
5. 选择串口，通常为 `COM6`，波特率保持 `115200`。
6. 点击“开始串口日志”或直接点击“一键准备自动测试”。
7. 确认 GUI 能扫描并连接 `ESP_ROBOT`。
8. 如果做完整验证，点击“自动执行今日计划”。
9. 遇到弹窗时，按提示执行断电重启、关闭 AP、恢复 AP，然后点击继续。
10. 自动计划结束后，检查 TC-01 至 TC-06 的结果。
11. 打开 `records/` 查看 Markdown 记录。
12. 打开 `logs/` 查看完整串口日志。

## 7. 手动 BLE 模式

如果 Windows BLE 环境不稳定，或者 `bleak` 无法连接设备，可以勾选“手机 BLE 手动模式”：

- 脚本不会用电脑连接 BLE。
- 点击 TC 按钮时，脚本会把要发送的 JSON 复制到剪贴板。
- 测试人员用手机 BLE 工具，例如 nRF Connect 或 LightBlue，连接设备并写入 `0xFF01`。
- 收到 Notify 或响应后，把内容填到底部“手机 BLE 响应”，点击“记录响应”。
- 串口日志仍可由脚本继续采集。

## 8. 用例说明

### TC-01 初始状态读取

目标：验证清除凭据并重启后，设备不会使用旧凭据，状态应为 `unconfigured`。

脚本动作：

- 发送 `cfg.wifi.get`。
- 等待 `WIFI_UNCONFIGURED` 或 `"status":"unconfigured"`。

### TC-02 正确 BLE 配网

目标：验证正确 SSID/密码可以通过 BLE 下发并连接成功。

脚本动作：

- 发送 `cfg.wifi.set`，使用 GUI 中填写的正确密码。
- 等待 `WIFI_CONNECTED`、`"status":"connected"` 或 `GOT IP`。
- 再发送 `cfg.wifi.get` 读取状态。

### TC-03 掉电持久化

目标：验证 TC-02 成功后，断电重启仍能使用已保存凭据自动连接。

脚本动作：

- 弹窗提示人工断电重启。
- 重启后重新连接 BLE。
- 发送 `cfg.wifi.get`。
- 等待 connected/Got IP。

### TC-04 清除凭据

目标：验证 BLE 清除凭据后，设备重启不会复用旧 SSID/密码。

脚本动作：

- 发送 `cfg.wifi.clear`。
- 等待 `WIFI_CLEARED`、`WIFI_UNCONFIGURED` 或 `"status":"unconfigured"`。
- 弹窗提示人工重启。
- 重启后再次发送 `cfg.wifi.get`。

### TC-05 错误密码

目标：验证错误密码不会导致假连接、WDT、Panic，并且 BLE 后续仍可继续操作。

脚本动作：

- 发送 `cfg.wifi.set`，使用 GUI 中填写的错误密码。
- 等待 disconnected、connecting、AUTH、FAIL、NO AP 等异常状态证据。
- 如果出现 connected，则判定为失败风险。
- 如果出现 WDT/Panic，则判定为失败。

### TC-06 AP 不可达

目标：验证 AP 关闭和恢复时设备状态可恢复，不假连接、不崩溃。

脚本动作：

- 先下发正确 Wi-Fi 凭据。
- 等待 connected/Got IP。
- 弹窗提示人工关闭 AP。
- 发送 `cfg.wifi.get`，等待 disconnected/connecting。
- 弹窗提示人工恢复 AP。
- 再发送 `cfg.wifi.get`，等待 connected/Got IP。

## 9. 当前已知结果和注意事项

已有记录 `records/issue31-20260505-160335.md` 显示：

- TC-01：PASS。
- TC-04：PASS。
- TC-05：PASS。
- TC-02：BLOCKED，正确配网等待 connected/Got IP 超时。
- TC-03：BLOCKED，断电持久化后没有稳定观察到 connected/Got IP。
- TC-06：BLOCKED，AP 不可达和恢复流程等待状态变化超时。

接手人继续测试时建议优先确认：

- AP 是否真的可用，SSID/密码是否正确。
- 测试设备是否为同一台，避免多个 `ESP_ROBOT` 或多个 BLE 地址混淆。
- 串口 COM 口是否对应当前设备。
- 设备是否刚刷过固件，NVS/Wi-Fi 凭据是否处于预期状态。
- BLE 连接期间固件是否暂停 Wi-Fi/WS background activity，导致配网连接时序和预期不同。
- 串口日志是否出现 Wi-Fi reason code、WDT、Panic、assert 或重启。

## 10. 常见问题

### 找不到 ESP_ROBOT

- 确认设备上电并处于 BLE advertising 状态。
- 确认 Windows 蓝牙开启。
- 确认没有手机或其他电脑已经连接该 BLE 设备。
- 尝试重启设备后重新扫描。

### 串口打不开

- 确认 COM 口选择正确。
- 关闭其他正在占用串口的软件，例如 IDF monitor、串口助手。
- 在设备管理器中确认 USB 串口驱动正常。

### TC-02 一直 BLOCKED

- 优先确认 AP 名称和密码。
- 查看串口日志中的 Wi-Fi disconnect reason。
- 确认 AP 是否为 2.4GHz，ESP32-S3 不支持普通 5GHz Wi-Fi 连接。
- 尝试先执行 TC-04 清除凭据并重启，再重新跑 TC-02。

### TC-03 不通过

- 确认 TC-02 已经真正 connected/Got IP。
- 确认断电是完整断电，而不是仅软复位或串口重新连接。
- 查看重启后是否读取到旧 SSID，但状态停留在 disconnected。

### TC-06 不通过

- 确认 AP 关闭动作真实生效。
- 确认 AP 恢复后 SSID 和密码没有变化。
- 给 AP 恢复预留足够时间，有些手机热点恢复较慢。

## 11. 交接结论

这个目录已经具备 issue #31 的半自动化验证能力，可以作为 BLE 配网回归工具继续使用。当前工具本身能够完成 BLE 指令、Notify、串口日志和记录生成；后续重点不是补工具框架，而是继续用它复测并记录 TC-02、TC-03、TC-06 的阻塞现象和证据。
