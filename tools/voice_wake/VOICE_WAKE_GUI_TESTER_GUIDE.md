# 语音唤醒自动化测试工具说明

## 1. 目录用途

`tools/voice_wake` 用于保存 WatcheRobot 语音唤醒词测试工具、默认配置、测试音频素材和历史测试结果。

这个目录主要服务于 Jarvis / 你好小智等唤醒词测试，目标是用电脑自动播放指定 WAV 音频，同时读取 ESP32-S3 串口日志，判断设备是否识别到唤醒词，并统计不同音量、距离、语速和角度下的唤醒成功率。

## 2. 两个核心文件

### 2.1 `voice_wake_tester/wake_gui.py`

这是主自动化测试脚本，提供一个 Windows GUI。

脚本主要做这些事情：

- 枚举本机串口，连接 ESP32-S3 串口日志。
- 枚举本机音频输出设备。
- 加载一个或多个 WAV 测试音频。
- 按配置自动播放音频。
- 支持按音量、语速、距离、角度、重复次数组合批量测试。
- 支持设置 Windows 主音量或软件播放音量。
- 从串口日志中识别唤醒关键字，例如 `Wake word detected`、`Jarvis detected`、`wakeup`。
- 从串口日志中识别待唤醒恢复关键字，例如 `wake_idle frame=`、`HAL_WAKE_WORD: Wake word detection started`。
- 统计每轮是否唤醒成功、唤醒延迟、恢复状态、RMS/Peak 音频指标。
- 支持 wake-only 唤醒率测试、dialog 对话链路测试、issue33/issue34 预设测试模式。
- 自动保存 CSV 结果和原始串口日志。
- 支持生成 Markdown 测试报告。
- 支持保存成功率图表和 Peak/RMS 图表。
- 支持静音误唤醒测试。

### 2.2 `voice_wake_tester/wake_gui_config.json`

这是 GUI 的默认配置文件。

当前配置包含：

- 串口：`COM6`
- 波特率：`115200`
- 默认 WAV：`jarvis_tts_male.wav`
- 音量列表：`10` 到 `100`
- 语速：`1.0`
- 每档次数：`10`
- 检测等待时间：`8s`
- 轮次间隔：`5s`
- 唤醒关键字：`Wake word detected`、`Jarvis detected`、`wakeup`
- 恢复待唤醒关键字：`wake_idle frame=`
- 测试模式：`wake-only: wake rate`
- 音量模式：`windows`
- 距离：`5cm`
- 环境备注：`quiet room wake-only #34`

当前 `wake_gui.py` 已改为根据脚本所在目录自动定位仓库内资源：

- 测试素材：`tools\voice_wake\voice_wake_test_assets`
- 测试结果：`tools\voice_wake\voice_wake_test_assets\results`
- 配置文件：`tools\voice_wake\voice_wake_tester\wake_gui_config.json`

## 3. 测试素材和结果目录

测试音频目录：

- `voice_wake_test_assets/jarvis_tts_female.wav`
- `voice_wake_test_assets/jarvis_tts_male.wav`
- `voice_wake_test_assets/nihao_xiaozhi_tts_female.wav`
- `voice_wake_test_assets/nihao_xiaozhi_tts_male.wav`

历史结果目录：

- `voice_wake_test_assets/results/`

结果文件类型：

- `wake_live_log_*.txt`：测试运行时实时串口日志。
- `wake_raw_log_*.txt`：自动保存的原始串口日志。
- `wake_results_*.csv`：每轮测试明细结果。
- `wake_report_*.md`：测试报告。
- `wake_success_rate_*.png`：唤醒成功率图表，脚本支持生成。
- `wake_peak_rms_*.png`：Peak/RMS 音频指标图表，脚本支持生成。

## 4. 唤醒词测试素材生成和转换

当前目录中没有单独保存素材生成脚本；接手人需要复现或新增测试素材时，可以按下面的命令流程生成。

整体流程是：

1. 用 TTS 工具生成原始语音文件，通常先生成 `.mp3`。
2. 用 FFmpeg 转成测试工具使用的 `.wav`。
3. 统一 WAV 格式，建议使用 16kHz、mono、16-bit PCM。
4. 放入 `voice_wake_test_assets/`。
5. 在 `wake_gui.py` 中添加 WAV 并执行测试。

### 4.1 需要安装的环境

Windows 环境：

- Python 3.9 或更新版本，建议 Python 3.11。
- PowerShell。
- FFmpeg，需要命令行可直接执行 `ffmpeg -version`。
- Python TTS 命令行工具，这里使用 `edge-tts`。

安装 Python 依赖：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\tools\voice_wake
python -m pip install -r requirements.txt
```

安装 FFmpeg 的方式之一：

```powershell
winget install Gyan.FFmpeg
```

安装后重新打开 PowerShell，确认：

```powershell
ffmpeg -version
edge-tts --help
```

如果 `ffmpeg` 找不到，需要把 FFmpeg 的 `bin` 目录加入 Windows `PATH`。

### 4.2 建议的目录准备

```powershell
$assetDir = "D:\GithubRep\WatcheRobot-Firmware\tools\voice_wake\voice_wake_test_assets"
$tmpDir = Join-Path $assetDir "_source_mp3"
New-Item -ItemType Directory -Force -Path $assetDir, $tmpDir
```

`_source_mp3` 只用于临时保存 TTS 原始文件，最终测试使用的是 `.wav`。

### 4.3 生成 Jarvis 男声/女声素材

男声 Jarvis：

```powershell
edge-tts `
  --voice en-US-GuyNeural `
  --text "Jarvis" `
  --write-media "$tmpDir\jarvis_tts_male.mp3"
```

女声 Jarvis：

```powershell
edge-tts `
  --voice en-US-JennyNeural `
  --text "Jarvis" `
  --write-media "$tmpDir\jarvis_tts_female.mp3"
```

转换成测试 WAV：

```powershell
ffmpeg -y -i "$tmpDir\jarvis_tts_male.mp3" `
  -ac 1 -ar 16000 -sample_fmt s16 `
  "$assetDir\jarvis_tts_male.wav"

ffmpeg -y -i "$tmpDir\jarvis_tts_female.mp3" `
  -ac 1 -ar 16000 -sample_fmt s16 `
  "$assetDir\jarvis_tts_female.wav"
```

### 4.4 生成“你好小智”男声/女声素材

男声“你好小智”：

```powershell
edge-tts `
  --voice zh-CN-YunxiNeural `
  --text "你好小智" `
  --write-media "$tmpDir\nihao_xiaozhi_tts_male.mp3"
```

女声“你好小智”：

```powershell
edge-tts `
  --voice zh-CN-XiaoxiaoNeural `
  --text "你好小智" `
  --write-media "$tmpDir\nihao_xiaozhi_tts_female.mp3"
```

转换成测试 WAV：

```powershell
ffmpeg -y -i "$tmpDir\nihao_xiaozhi_tts_male.mp3" `
  -ac 1 -ar 16000 -sample_fmt s16 `
  "$assetDir\nihao_xiaozhi_tts_male.wav"

ffmpeg -y -i "$tmpDir\nihao_xiaozhi_tts_female.mp3" `
  -ac 1 -ar 16000 -sample_fmt s16 `
  "$assetDir\nihao_xiaozhi_tts_female.wav"
```

### 4.5 可选：去静音和响度归一化

如果生成的 TTS 前后空白较长，或者不同素材响度差异较大，可以用 FFmpeg 做去静音和响度归一化。

示例：

```powershell
ffmpeg -y -i "$tmpDir\jarvis_tts_male.mp3" `
  -af "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,loudnorm=I=-18:TP=-3:LRA=7" `
  -ac 1 -ar 16000 -sample_fmt s16 `
  "$assetDir\jarvis_tts_male.wav"
```

说明：

- `silenceremove` 用于裁剪前后静音。
- `loudnorm` 用于响度归一化。
- `-ac 1` 表示单声道。
- `-ar 16000` 表示 16kHz 采样率。
- `-sample_fmt s16` 表示 16-bit PCM。

如果目的是比较不同音量下的唤醒率，建议固定一套生成参数，不要每次用不同归一化策略，否则结果不容易横向比较。

### 4.6 检查 WAV 参数

生成后用 FFmpeg 检查：

```powershell
ffmpeg -i "$assetDir\jarvis_tts_male.wav"
```

期望看到类似：

```text
Audio: pcm_s16le, 16000 Hz, mono
```

也可以用 Python 检查：

```powershell
python -c "import soundfile as sf; from pathlib import Path; asset_dir = Path(r'D:\GithubRep\WatcheRobot-Firmware\tools\voice_wake\voice_wake_test_assets'); [print(wav.name, sf.info(wav).samplerate, sf.info(wav).channels, sf.info(wav).subtype, f'{sf.info(wav).duration:.2f}s') for wav in sorted(asset_dir.glob('*.wav'))]"
```

### 4.7 在 GUI 中使用新素材

1. 启动 `wake_gui.py`。
2. 点击“添加 WAV”。
3. 选择 `voice_wake_test_assets/` 下新生成的 WAV。
4. 选择测试范围为“选中音频”或“全部音频”。
5. 设置音量、距离、角度、语速和测试次数。
6. 点击“开始测试”。

注意：

- 如果测试 WakeNet 的 Jarvis 模型，应优先使用 `jarvis_tts_*.wav`。
- 如果测试“你好小智”模型，应优先使用 `nihao_xiaozhi_tts_*.wav`。
- 素材内容必须和固件中烧录的唤醒词模型一致，否则测试结果会误导。

## 5. 脚本工作流程

### 5.1 启动 GUI

运行 `wake_gui.py` 后会打开“WatcheRobot 语音唤醒自动化测试”窗口。

GUI 主要区域包括：

- 串口与测试参数。
- 测试音频 WAV 列表。
- 实时状态。
- 测试结果表。
- 汇总统计表。
- 实时串口日志。

### 5.2 读取测试配置

点击“开始测试”或“单次测试选中”时，脚本会读取 GUI 中的配置：

- 串口和波特率。
- WAV 文件列表。
- 音量列表。
- 语速列表。
- 每档次数。
- 检测等待时间。
- 轮次间隔。
- 唤醒关键字。
- 是否等待设备恢复待唤醒。
- 恢复关键字和最大等待时间。
- 测试模式。
- 音量控制模式。
- 距离、角度和环境备注。

如果配置错误，例如没有选择 WAV、WAV 文件不存在、音量超出 0-100、语速不合法，脚本会弹窗提示并停止启动。

### 5.3 打开串口并采集日志

脚本会用 `pyserial` 打开配置的串口，例如 `COM6 @ 115200`。

串口读取线程会持续读取 ESP32-S3 输出，每行日志会：

- 进入 GUI 实时日志窗口。
- 进入最近事件缓存，用于本轮判定。
- 写入 live log 文件。
- 在测试结束时写入 raw log 文件。

脚本会从串口日志中识别这些状态：

- `wake_idle frame=`：设备处于待唤醒监听状态。
- `Wake word detection started`：唤醒检测启动。
- `Wake word detected`：检测到唤醒词。
- `Wake word triggered recording` 或 `state -> RECORDING`：进入录音。
- `VAD triggered stop` 或 `audio end marker sent`：录音结束。
- `ASR result` 或 `evt.asr.result`：识别结果。
- `TTS started`、`Audio mode: playback`：TTS 播放开始。
- `TTS playback complete`、`TTS session complete`：TTS 播放完成。
- `Resuming wake word detection`：恢复唤醒检测。

### 5.4 自动播放 WAV

脚本用 `soundfile` 读取 WAV，用 `sounddevice` 播放音频。

播放时支持：

- 软件音量：直接缩放 WAV PCM 数据。
- Windows 主音量：通过 `pycaw` 设置系统输出音量。
- both：同时设置 Windows 主音量并缩放软件音量。
- 输出设备选择：可选择系统默认或指定音频输出设备。

语速实现方式：

- 通过改变播放采样率实现。
- 例如 `0.8x` 会让播放变慢、时长变长；`1.2x` 会让播放变快、时长变短。

### 5.5 每轮判定

每轮测试流程：

1. 如果启用“等待恢复待唤醒”，先等串口出现 ready 关键字。
2. 播放当前 WAV。
3. 在检测等待时间内监听串口日志。
4. 如果出现唤醒关键字，则本轮判定为检测到唤醒。
5. 记录从播放开始到唤醒日志出现的延迟。
6. 抽取本轮日志里的 `wake_idle` 或 `audio frame` RMS/Peak 最大值。
7. 如果是 dialog 模式，还会继续检查录音、ASR、TTS、恢复唤醒等链路是否完整。

wake-only 模式下：

- 主要看是否出现唤醒关键字。
- 唤醒后会等待 VAD/audio end 和唤醒检测恢复，避免下一轮播放时设备还没回到待唤醒状态。

dialog 模式下：

- 成功标准更严格，需要看到唤醒、录音结束、非空 ASR、TTS 开始、TTS 完成、唤醒检测恢复。

## 6. 支持的测试模式

### 6.1 `wake-only: wake rate`

用于测试唤醒词识别率。

适合场景：

- Jarvis 单唤醒词识别率测试。
- 不关心完整对话链路，只看能否唤醒。
- 音量、距离、角度、语速组合测试。

### 6.2 `dialog: wake + command + TTS`

用于测试完整语音交互链路。

要求测试 WAV 不能只有唤醒词，还需要包含命令语音，否则脚本会提示：

`dialog mode needs WAV audio with Jarvis plus a command`

### 6.3 `issue33: Jarvis nihao 100 dialog loops`

用于 issue33 类场景，预设为 Jarvis + 你好相关 100 轮对话链路测试。

脚本会自动设置：

- 次数：`100`
- 音量：`60`
- 语速：`1.0`
- 等待检测：`10s`
- 轮次间隔：`5s`
- 恢复等待：`120s`

### 6.4 `issue34: voice state machine`

用于 issue34 类语音状态机测试。

脚本会自动设置：

- 次数：`10`
- 音量：`10,20,30,40,50,60,70,80,90,100`
- 语速：`1.0`
- 等待检测：`10s`
- 轮次间隔：`5s`
- 恢复等待：`120s`

## 7. 需要的环境和工具

### 7.1 硬件

- WatcheRobot ESP32-S3 设备。
- USB 数据线，用于供电和串口日志。
- 电脑扬声器或外接音箱，用于播放唤醒音频。
- 安静测试环境，或明确记录噪声环境。
- 固定距离的摆放条件，例如 5cm、10cm、15cm、20cm、30cm。

### 7.2 固件前置条件

ESP32-S3 固件需要：

- 已启用 WakeNet 唤醒检测。
- 已烧录匹配的唤醒词模型，例如 Jarvis 对应模型。
- 串口输出包含唤醒检测、ready、录音、ASR、TTS 等关键日志。
- 如果做 wake-only 测试，至少需要能输出 `Wake word detected` 和 `wake_idle frame=`。
- 如果做 dialog 测试，需要能输出录音、ASR、TTS 和恢复唤醒相关日志。

### 7.3 PC 软件环境

- Windows 电脑。
- Python 3.9 或更新版本，建议 Python 3.11。
- PowerShell 或 CMD。
- USB 串口驱动可用，设备能识别为 COM 口。
- 音频输出设备可用。

### 7.4 Python 依赖

脚本直接 import 了以下第三方库：

- `pyserial`
- `sounddevice`
- `soundfile`
- `numpy`
- `matplotlib`
- `comtypes`
- `pycaw`

其中：

- `pyserial` 用于串口日志。
- `sounddevice` 用于播放音频。
- `soundfile` 用于读取 WAV。
- `numpy` 用于音频数据缩放和统计。
- `matplotlib` 用于生成图表。
- `pycaw` 和 `comtypes` 用于读取、设置 Windows 主音量。

安装命令：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\tools\voice_wake
python -m pip install -r requirements.txt
```

如果 `sounddevice` 安装或播放失败，需要检查 PortAudio 相关环境和 Windows 音频设备。

如果 `pycaw` 不可用，脚本仍可运行，但 `windows` 音量模式会跳过 Windows 主音量设置，建议改用 `software` 音量模式。

## 8. 启动方式

推荐通过启动脚本运行：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\tools\voice_wake
.\run_wake_gui.ps1 -InstallDeps
```

后续运行：

```powershell
.\run_wake_gui.ps1
```

也可以直接运行 Python 文件：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\tools\voice_wake\voice_wake_tester
python .\wake_gui.py
```

启动后自动切到日志页：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\tools\voice_wake
.\run_wake_gui.ps1 -ShowLogs
```

启动后按当前配置自动开始测试：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\tools\voice_wake
.\run_wake_gui.ps1 -AutoStart
```

也可以两个参数一起用：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\tools\voice_wake
.\run_wake_gui.ps1 -ShowLogs -AutoStart
```

## 9. 推荐操作流程

1. 烧录包含目标唤醒词模型的 ESP32-S3 固件。
2. 用 USB 连接设备，确认串口号，例如 `COM6`。
3. 准备电脑音频输出，确认 WAV 可以正常播放。
4. 安装 Python 依赖。
5. 运行 `.\run_wake_gui.ps1`，或直接运行 `voice_wake_tester\wake_gui.py`。
6. 在 GUI 中刷新串口，选择正确 COM 口和 `115200` 波特率。
7. 点击“添加 WAV”，选择当前目录下的测试音频。
8. 设置测试范围：选中音频或全部音频。
9. 设置音量列表，例如 `10,20,30,40,50,60,70,80,90,100`。
10. 设置语速列表，例如 `1.0` 或 `0.8,1.0,1.2`。
11. 设置每档次数，例如 `10`。
12. 设置距离、角度、环境备注。
13. 选择测试模式，常规唤醒率测试选 `wake-only: wake rate`。
14. 点击“开始测试”。
15. 测试结束后查看“测试结果”和“汇总统计”。
16. 需要交付时点击“导出 CSV”、“保存图表”、“生成报告”。

## 10. 输出结果说明

CSV 每轮结果包含：

- 时间。
- WAV 文件名。
- 语速。
- 播放时长。
- 音量。
- 音量档位。
- 轮次。
- 距离。
- 距离档位。
- 角度。
- 环境备注。
- 是否检测到唤醒。
- 唤醒延迟。
- RMS/Peak 最大值。
- 恢复状态。
- dialog 模式下的录音、ASR、TTS、恢复状态。
- 失败原因。
- 本轮日志摘录。

Markdown 报告包含：

- 生成时间。
- 串口。
- 音量模式。
- 输出设备。
- 环境备注。
- 最佳观测配置。
- 按音频、语速、距离、角度、音量聚合的成功率。
- 音量档位汇总。
- 距离档位汇总。
- dialog 链路通过率和失败原因统计。

## 11. 常见问题

### 启动后没有默认 WAV

原因可能是配置文件里记录的 WAV 被移动、删除，或素材目录为空。

处理方式：

- 在 GUI 中点击“添加 WAV”，手动选择：
  - `D:\GithubRep\WatcheRobot-Firmware\tools\voice_wake\voice_wake_test_assets\jarvis_tts_male.wav`
  - 或其他当前目录下的 WAV。

### 串口打不开

处理方式：

- 确认设备管理器里的 COM 口。
- 关闭其他占用串口的软件，例如 ESP-IDF monitor 或串口助手。
- 在 GUI 中点击“刷新”，重新选择串口。

### 一直显示起始未就绪

处理方式：

- 确认固件已启动 WakeNet。
- 查看串口是否出现 `wake_idle frame=` 或 `Wake word detection started`。
- 将 ready preset 改为 `relaxed: wake_idle only`。
- 增大最大恢复等待时间。

### 播放了音频但没有唤醒

处理方式：

- 确认设备麦克风正常。
- 确认播放设备和输出音量正确。
- 先点击“播放选中”确认电脑确实有声音。
- 调整距离、音量、角度。
- 确认固件中烧录的唤醒词模型与 WAV 内容一致，例如 Jarvis 模型对应 Jarvis 音频。

### Windows 主音量没有被调整

处理方式：

- 安装 `pycaw` 和 `comtypes`。
- 如果仍不可用，将音量模式改为 `software`。

### dialog 模式报错

原因：

- dialog 模式要求 WAV 包含唤醒词和命令语音，不能只有 Jarvis 唤醒词。

处理方式：

- 使用包含 “Jarvis + 命令” 的 WAV。
- 如果只测唤醒率，改用 `wake-only: wake rate`。

## 12. 交接结论

`voice_wake` 目录已经具备语音唤醒自动化测试能力。接手人可以直接使用 `wake_gui.py` 对 Jarvis/你好小智音频进行不同音量、距离、语速、角度下的批量测试，并生成 CSV、日志、图表和 Markdown 报告。

当前已补充 `requirements.txt` 和 `run_wake_gui.ps1`，并把默认素材、结果和配置路径改为仓库内相对路径，后续在仓库移动时更容易复用。
