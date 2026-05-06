# voice_wake

WatcheRobot 语音唤醒词测试工具目录。

主要入口：

- 详细说明：`VOICE_WAKE_GUI_TESTER_GUIDE.md`
- 启动脚本：`run_wake_gui.ps1`
- GUI 主程序：`voice_wake_tester/wake_gui.py`
- 默认配置：`voice_wake_tester/wake_gui_config.json`
- 测试素材：`voice_wake_test_assets/`
- 历史结果：`voice_wake_test_assets/results/`

首次运行：

```powershell
cd D:\GithubRep\WatcheRobot-Firmware\tools\voice_wake
.\run_wake_gui.ps1 -InstallDeps
```

后续运行：

```powershell
.\run_wake_gui.ps1
```

说明：

- 测试素材生成和转换命令见 `VOICE_WAKE_GUI_TESTER_GUIDE.md`。
- 当前脚本已使用仓库内相对路径定位素材、结果和配置。
