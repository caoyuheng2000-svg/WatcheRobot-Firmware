import csv
import argparse
import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import serial
import serial.tools.list_ports
import sounddevice as sd
import soundfile as sf
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    PYCaw_AVAILABLE = True
except Exception:
    PYCaw_AVAILABLE = False


TOOL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_DIR = TOOL_ROOT / "voice_wake_test_assets"
DEFAULT_RESULT_DIR = DEFAULT_ASSET_DIR / "results"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "wake_gui_config.json"
DEFAULT_PORT = "COM6"
DEFAULT_BAUD = 115200
DEFAULT_WAKE_KEYWORDS_TEXT = "Wake word detected,Jarvis detected,wakeup"
LEGACY_READY_KEYWORDS_TEXT = "IDLE,LISTENING,WAIT_WAKE,READY"
DEFAULT_READY_KEYWORDS_TEXT = (
    "VOICE: Resuming wake word detection,"
    "HAL_WAKE_WORD: Wake word detection started,"
    "wake_idle frame="
)
DEFAULT_READY_TIMEOUT_SEC = "60"
READY_PRESET_STRICT = "strict: resume + start + idle"
READY_PRESET_RELAXED = "relaxed: wake_idle only"
READY_PRESET_START_ONLY = "start only: wake detector started"
TEST_MODE_WAKE_ONLY = "wake-only: wake rate"
TEST_MODE_DIALOG = "dialog: wake + command + TTS"
TEST_MODE_ISSUE33 = "issue33: Jarvis nihao 100 dialog loops"
TEST_MODE_ISSUE34 = "issue34: voice state machine"

WAKE_RE = re.compile(r"Wake word detected", re.IGNORECASE)
IDLE_STATS_RE = re.compile(r"wake_idle\s+frame=(?P<frame>\d+)\s+rms=(?P<rms>\d+)\s+peak=(?P<peak>\d+)")
AUDIO_STATS_RE = re.compile(r"audio\s+frame=(?P<frame>\d+)\s+rms=(?P<rms>\d+)\s+peak=(?P<peak>\d+)")
WAKE_ONLY_STOP_KEYWORDS = (
    "VAD triggered stop",
    "audio end marker sent",
)
WAKE_ONLY_RESUME_KEYWORDS = (
    "Resuming wake word detection",
    "HAL_WAKE_WORD: Wake word detection started",
)


@dataclass
class LogEvent:
    ts: float
    line: str


@dataclass
class TrialResult:
    timestamp: str
    wav_file: str
    speech_rate: float
    playback_duration_sec: float
    volume_percent: int
    volume_band: str
    trial_index: int
    distance_cm: str
    distance_band: str
    angle: str
    environment_note: str
    detected: bool
    latency_ms: Optional[int]
    rms_max: Optional[int]
    peak_max: Optional[int]
    ready_status: str
    ready_ms: Optional[int]
    ready_line: str
    wake_line: str
    test_mode: str = ""
    recording_seen: bool = False
    audio_end_seen: bool = False
    asr_seen: bool = False
    asr_text: str = ""
    asr_text_nonempty: bool = False
    tts_pause_seen: bool = False
    tts_started_seen: bool = False
    tts_complete_seen: bool = False
    resume_seen: bool = False
    ready_seen: bool = False
    dialog_success: bool = False
    failure_reason: str = ""
    round_duration_ms: Optional[int] = None
    log_excerpt: str = ""


class WakeTesterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("WatcheRobot 语音唤醒自动化测试")
        self.root.geometry("1180x680")
        self.root.minsize(980, 600)

        self.log_queue: queue.Queue[LogEvent] = queue.Queue()
        self.ui_queue: queue.Queue[tuple] = queue.Queue()
        self.stop_event = threading.Event()
        self.serial_thread: Optional[threading.Thread] = None
        self.test_thread: Optional[threading.Thread] = None
        self.serial_conn: Optional[serial.Serial] = None
        self.recent_events: List[LogEvent] = []
        self.raw_log_lines: List[str] = []
        self.results: List[TrialResult] = []
        self.original_master_volume: Optional[float] = None
        self.output_devices: Dict[str, int] = {"系统默认": -1}
        self.tts_active = False
        self.last_tts_done_ts = 0.0
        self.live_log_path: Optional[Path] = None

        self._build_ui()
        self._load_default_wavs()
        self._refresh_ports()
        self._refresh_output_devices()
        self.root.after(80, self._pump_queues)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=tk.X)

        conn = ttk.LabelFrame(top, text="串口与测试参数", padding=8)
        conn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        ttk.Label(conn, text="串口").grid(row=0, column=0, sticky=tk.W)
        self.port_var = tk.StringVar(value=DEFAULT_PORT)
        self.port_combo = ttk.Combobox(conn, textvariable=self.port_var, width=16)
        self.port_combo.grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Button(conn, text="刷新", command=self._refresh_ports).grid(row=0, column=2, sticky=tk.W)

        ttk.Label(conn, text="波特率").grid(row=0, column=3, sticky=tk.W, padx=(16, 0))
        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        ttk.Entry(conn, textvariable=self.baud_var, width=10).grid(row=0, column=4, sticky=tk.W, padx=5)

        ttk.Label(conn, text="音量列表").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        self.volumes_var = tk.StringVar(value="10,20,30,40,50,60,70,80")
        ttk.Entry(conn, textvariable=self.volumes_var, width=30).grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=5, pady=(8, 0))

        ttk.Label(conn, text="语速列表").grid(row=1, column=3, sticky=tk.W, padx=(16, 0), pady=(8, 0))
        self.speech_rates_var = tk.StringVar(value="1.0")
        ttk.Entry(conn, textvariable=self.speech_rates_var, width=16).grid(row=1, column=4, sticky=tk.W, padx=5, pady=(8, 0))

        ttk.Label(conn, text="语速预设").grid(row=1, column=5, sticky=tk.W, padx=(16, 0), pady=(8, 0))
        self.speech_rate_preset_var = tk.StringVar(value="标准 1.0x")
        self.speech_rate_preset_combo = ttk.Combobox(
            conn,
            textvariable=self.speech_rate_preset_var,
            width=22,
            state="readonly",
            values=(
                "标准 1.0x",
                "慢速-轻微 0.9x",
                "慢速-中等 0.8x",
                "慢速-明显 0.7x",
                "慢速组合 0.6-1.0x",
                "快速-轻微 1.1x",
                "快速-中等 1.2x",
                "快速-明显 1.3x",
                "快速组合 1.0-1.4x",
                "全量七挡 0.7-1.3x",
            ),
        )
        self.speech_rate_preset_combo.grid(row=1, column=6, sticky=tk.W, padx=5, pady=(8, 0))
        self.speech_rate_preset_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_speech_rate_preset())

        self.speech_rate_hint_var = tk.StringVar(value=self._build_speech_rate_hint("1.0"))
        ttk.Label(conn, textvariable=self.speech_rate_hint_var).grid(
            row=5, column=0, columnspan=9, sticky=tk.W, pady=(8, 0)
        )
        self.speech_rates_var.trace_add("write", lambda *_args: self._refresh_speech_rate_hint())

        ttk.Label(conn, text="每档次数").grid(row=1, column=7, sticky=tk.W, padx=(16, 0), pady=(8, 0))
        self.trials_var = tk.StringVar(value="10")
        ttk.Entry(conn, textvariable=self.trials_var, width=10).grid(row=1, column=8, sticky=tk.W, padx=5, pady=(8, 0))

        ttk.Label(conn, text="起始音量").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        self.volume_start_var = tk.StringVar(value="10")
        ttk.Entry(conn, textvariable=self.volume_start_var, width=10).grid(row=2, column=1, sticky=tk.W, padx=5, pady=(8, 0))

        ttk.Label(conn, text="结束音量").grid(row=2, column=2, sticky=tk.W, padx=(16, 0), pady=(8, 0))
        self.volume_end_var = tk.StringVar(value="100")
        ttk.Entry(conn, textvariable=self.volume_end_var, width=10).grid(row=2, column=3, sticky=tk.W, padx=5, pady=(8, 0))

        ttk.Label(conn, text="步进").grid(row=2, column=4, sticky=tk.W, padx=(16, 0), pady=(8, 0))
        self.volume_step_var = tk.StringVar(value="10")
        ttk.Entry(conn, textvariable=self.volume_step_var, width=8).grid(row=2, column=5, sticky=tk.W, padx=5, pady=(8, 0))

        ttk.Button(conn, text="生成音量列表", command=self.fill_volume_range).grid(row=2, column=6, sticky=tk.W, padx=(10, 0), pady=(8, 0))
        volume_band_frame = ttk.Frame(conn)
        volume_band_frame.grid(row=2, column=7, columnspan=2, sticky=tk.W, padx=5, pady=(8, 0))
        ttk.Button(volume_band_frame, text="低音量", width=8, command=lambda: self.apply_volume_band("low")).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(volume_band_frame, text="中音量", width=8, command=lambda: self.apply_volume_band("mid")).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(volume_band_frame, text="高音量", width=8, command=lambda: self.apply_volume_band("high")).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Label(conn, text="等待检测(s)").grid(row=3, column=0, sticky=tk.W, pady=(8, 0))
        self.wait_var = tk.StringVar(value="5")
        ttk.Entry(conn, textvariable=self.wait_var, width=10).grid(row=3, column=1, sticky=tk.W, padx=5, pady=(8, 0))

        ttk.Label(conn, text="轮次间隔(s)").grid(row=3, column=2, sticky=tk.W, padx=(16, 0), pady=(8, 0))
        self.gap_var = tk.StringVar(value="2")
        ttk.Entry(conn, textvariable=self.gap_var, width=10).grid(row=3, column=3, sticky=tk.W, padx=5, pady=(8, 0))

        ttk.Label(conn, text="音量模式").grid(row=3, column=4, sticky=tk.W, padx=(16, 0), pady=(8, 0))
        self.volume_mode_var = tk.StringVar(value="windows")
        self.volume_mode_combo = ttk.Combobox(
            conn,
            textvariable=self.volume_mode_var,
            width=16,
            state="readonly",
            values=("software", "windows", "both"),
        )
        self.volume_mode_combo.grid(row=3, column=5, sticky=tk.W, padx=5, pady=(8, 0))
        self.output_device_var = tk.StringVar(value="系统默认")
        self.output_device_combo = ttk.Combobox(conn, textvariable=self.output_device_var, width=28, state="readonly")
        self.output_device_combo.grid(row=3, column=7, sticky=tk.W, padx=5, pady=(8, 0))
        ttk.Button(conn, text="刷新音频设备", command=self._refresh_output_devices).grid(row=3, column=8, sticky=tk.W, padx=5, pady=(8, 0))
        ttk.Label(conn, text="software=仅软件 windows=仅主音量 both=两者").grid(
            row=3, column=6, sticky=tk.W, padx=5, pady=(8, 0)
        )

        ttk.Label(conn, text="距离(cm)").grid(row=4, column=0, sticky=tk.W, pady=(8, 0))
        self.distance_var = tk.StringVar(value="30")
        ttk.Entry(conn, textvariable=self.distance_var, width=16).grid(row=4, column=1, sticky=tk.W, padx=5, pady=(8, 0))
        distance_band_frame = ttk.Frame(conn)
        distance_band_frame.grid(row=4, column=7, columnspan=2, sticky=tk.W, padx=5, pady=(8, 0))
        ttk.Button(distance_band_frame, text="近距离", width=8, command=lambda: self.apply_distance_band("near")).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(distance_band_frame, text="中距离", width=8, command=lambda: self.apply_distance_band("mid")).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(distance_band_frame, text="远距离", width=8, command=lambda: self.apply_distance_band("far")).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(distance_band_frame, text="全距离", width=8, command=lambda: self.apply_distance_band("all")).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Label(conn, text="角度").grid(row=4, column=2, sticky=tk.W, padx=(16, 0), pady=(8, 0))
        self.angle_var = tk.StringVar(value="正面")
        ttk.Combobox(
            conn,
            textvariable=self.angle_var,
            width=12,
            values=("正面", "左侧45°", "右侧45°", "背面", "顶部", "自定义"),
        ).grid(row=4, column=3, sticky=tk.W, padx=5, pady=(8, 0))

        ttk.Label(conn, text="环境备注").grid(row=4, column=4, sticky=tk.W, padx=(16, 0), pady=(8, 0))
        self.environment_var = tk.StringVar(value="安静室内")
        ttk.Entry(conn, textvariable=self.environment_var, width=32).grid(
            row=4, column=5, columnspan=2, sticky=tk.W, padx=5, pady=(8, 0)
        )

        self.wait_ready_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(conn, text="等待恢复待唤醒", variable=self.wait_ready_var).grid(
            row=6, column=0, columnspan=2, sticky=tk.W, pady=(8, 0)
        )
        ttk.Label(conn, text="恢复关键字").grid(row=6, column=2, sticky=tk.W, padx=(16, 0), pady=(8, 0))
        self.ready_keywords_var = tk.StringVar(value=DEFAULT_READY_KEYWORDS_TEXT)
        ttk.Entry(conn, textvariable=self.ready_keywords_var, width=34).grid(
            row=6, column=3, columnspan=3, sticky=tk.W, padx=5, pady=(8, 0)
        )
        self.ready_preset_var = tk.StringVar(value=READY_PRESET_STRICT)
        self.ready_preset_combo = ttk.Combobox(
            conn,
            textvariable=self.ready_preset_var,
            width=32,
            state="readonly",
            values=(READY_PRESET_STRICT, READY_PRESET_RELAXED, READY_PRESET_START_ONLY),
        )
        self.ready_preset_combo.grid(row=6, column=8, sticky=tk.W, padx=5, pady=(8, 0))
        self.ready_preset_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_ready_preset())
        ttk.Label(conn, text="最大恢复等待(s)").grid(row=6, column=6, sticky=tk.W, padx=(16, 0), pady=(8, 0))
        self.ready_timeout_var = tk.StringVar(value=DEFAULT_READY_TIMEOUT_SEC)
        ttk.Entry(conn, textvariable=self.ready_timeout_var, width=10).grid(row=6, column=7, sticky=tk.W, padx=5, pady=(8, 0))

        ttk.Label(conn, text="唤醒关键字").grid(row=7, column=0, sticky=tk.W, pady=(8, 0))
        self.wake_keywords_var = tk.StringVar(value=DEFAULT_WAKE_KEYWORDS_TEXT)
        ttk.Entry(conn, textvariable=self.wake_keywords_var, width=72).grid(
            row=7, column=1, columnspan=6, sticky=tk.W, padx=5, pady=(8, 0)
        )
        self.tts_mode_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(conn, text="每轮有 TTS 回复", variable=self.tts_mode_var, command=self.apply_tts_mode).grid(
            row=7, column=7, columnspan=2, sticky=tk.W, padx=(16, 0), pady=(8, 0)
        )
        ttk.Label(conn, text="Test mode").grid(row=8, column=0, sticky=tk.W, pady=(8, 0))
        self.test_mode_var = tk.StringVar(value=TEST_MODE_WAKE_ONLY)
        self.test_mode_combo = ttk.Combobox(
            conn,
            textvariable=self.test_mode_var,
            width=30,
            state="readonly",
            values=(TEST_MODE_WAKE_ONLY, TEST_MODE_DIALOG, TEST_MODE_ISSUE33, TEST_MODE_ISSUE34),
        )
        self.test_mode_combo.grid(row=8, column=1, columnspan=3, sticky=tk.W, padx=5, pady=(8, 0))
        self.test_mode_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_test_mode())

        actions = ttk.LabelFrame(outer, text="操作", padding=8)
        actions.pack(fill=tk.X, pady=(8, 0))
        self.start_btn = ttk.Button(actions, text="开始测试", command=self.start_test)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_btn = ttk.Button(actions, text="停止", command=self.stop_test, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="导出 CSV", command=self.export_csv).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="保存图表", command=self.save_charts).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="打开结果目录", command=self.open_result_dir).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="单次测试选中", command=self.single_test_selected).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="清除结果", command=self.clear_results).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="清除日志", command=self.clear_logs).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="清除状态", command=self.clear_status).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="清除全部", command=self.clear_all).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="生成报告", command=self.generate_report).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="静音误唤醒测试", command=self.false_wake_silence_test).pack(side=tk.LEFT, padx=(0, 6))

        content_tabs = ttk.Notebook(outer)
        self.content_tabs = content_tabs
        content_tabs.pack(fill=tk.BOTH, expand=True, pady=8)

        audio_tab = ttk.Frame(content_tabs, padding=8)
        results_tab = ttk.Frame(content_tabs, padding=8)
        summary_tab = ttk.Frame(content_tabs, padding=8)
        logs_tab = ttk.Frame(content_tabs, padding=8)
        content_tabs.add(audio_tab, text="音频与状态")
        content_tabs.add(results_tab, text="测试结果")
        content_tabs.add(summary_tab, text="汇总统计")
        content_tabs.add(logs_tab, text="实时日志")

        audio_split = tk.PanedWindow(audio_tab, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=6)
        audio_split.pack(fill=tk.BOTH, expand=True)

        wav_panel = ttk.Frame(audio_split)
        audio_split.add(wav_panel, minsize=520, stretch="always")
        wav_box = ttk.LabelFrame(wav_panel, text="测试音频 WAV", padding=8)
        wav_box.pack(fill=tk.BOTH, expand=True)

        wav_list_frame = ttk.Frame(wav_box)
        wav_list_frame.pack(fill=tk.BOTH, expand=True)
        self.wav_list = tk.Listbox(wav_list_frame, height=12, selectmode=tk.EXTENDED)
        wav_y_scroll = ttk.Scrollbar(wav_list_frame, orient=tk.VERTICAL, command=self.wav_list.yview)
        wav_x_scroll = ttk.Scrollbar(wav_list_frame, orient=tk.HORIZONTAL, command=self.wav_list.xview)
        self.wav_list.configure(yscrollcommand=wav_y_scroll.set, xscrollcommand=wav_x_scroll.set)
        self.wav_list.bind("<MouseWheel>", lambda event: self.wav_list.yview_scroll(int(-1 * (event.delta / 120)), "units"))
        self.wav_list.grid(row=0, column=0, sticky="nsew")
        wav_y_scroll.grid(row=0, column=1, sticky="ns")
        wav_x_scroll.grid(row=1, column=0, sticky="ew")
        wav_list_frame.rowconfigure(0, weight=1)
        wav_list_frame.columnconfigure(0, weight=1)

        wav_actions = ttk.Frame(wav_box)
        wav_actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(wav_actions, text="添加 WAV", command=self.add_wavs).pack(side=tk.LEFT)
        ttk.Button(wav_actions, text="移除选中", command=self.remove_selected_wavs).pack(side=tk.LEFT, padx=6)
        ttk.Button(wav_actions, text="播放选中", command=self.play_selected_once).pack(side=tk.LEFT)

        wav_scope = ttk.Frame(wav_box)
        wav_scope.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(wav_scope, text="测试范围").pack(side=tk.LEFT)
        self.wav_scope_var = tk.StringVar(value="selected")
        ttk.Radiobutton(wav_scope, text="选中音频", variable=self.wav_scope_var, value="selected").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Radiobutton(wav_scope, text="全部音频", variable=self.wav_scope_var, value="all").pack(side=tk.LEFT, padx=(8, 0))

        status_box = ttk.LabelFrame(audio_split, text="状态", padding=8)
        audio_split.add(status_box, minsize=360, stretch="always")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status_box, textvariable=self.status_var, wraplength=420).pack(fill=tk.X)
        self.progress_var = tk.StringVar(value="进度：0/0")
        ttk.Label(status_box, textvariable=self.progress_var, wraplength=420).pack(fill=tk.X, pady=(10, 0))
        self.progress_bar = ttk.Progressbar(status_box, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))
        self.next_round_var = tk.StringVar(value="Next round: idle")
        self.next_round_label = ttk.Label(status_box, textvariable=self.next_round_var, wraplength=420)
        self.next_round_label.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(status_box, text="清除状态", command=self.clear_status).pack(anchor=tk.W, pady=(10, 0))

        result_box = ttk.LabelFrame(results_tab, text="测试结果", padding=8)
        result_box.pack(fill=tk.BOTH, expand=True)
        columns = ("time", "wav", "rate", "duration", "vol", "band", "trial", "distance", "dband", "angle", "detected", "latency", "ready", "ready_ms", "rms", "peak")
        result_table_frame = ttk.Frame(result_box)
        result_table_frame.pack(fill=tk.BOTH, expand=True)
        self.result_tree = ttk.Treeview(result_table_frame, columns=columns, show="headings", height=18)
        headings = {"time": "时间", "wav": "音频", "rate": "语速", "duration": "播放时长(s)", "vol": "音量", "band": "音量档", "trial": "轮次", "distance": "距离(cm)", "dband": "距离档", "angle": "角度", "detected": "唤醒", "latency": "延迟(ms)", "ready": "恢复", "ready_ms": "恢复(ms)", "rms": "RMS最大", "peak": "Peak最大"}
        widths = {"time": 150, "wav": 250, "rate": 70, "duration": 100, "vol": 70, "band": 80, "trial": 70, "distance": 90, "dband": 80, "angle": 90, "detected": 70, "latency": 90, "ready": 90, "ready_ms": 90, "rms": 90, "peak": 90}
        for col in columns:
            self.result_tree.heading(col, text=headings[col])
            self.result_tree.column(col, width=widths[col], anchor=tk.CENTER)
        result_y_scroll = ttk.Scrollbar(result_table_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        result_x_scroll = ttk.Scrollbar(result_table_frame, orient=tk.HORIZONTAL, command=self.result_tree.xview)
        self.result_tree.configure(yscrollcommand=result_y_scroll.set, xscrollcommand=result_x_scroll.set)
        self.result_tree.bind("<MouseWheel>", lambda event: self.result_tree.yview_scroll(int(-1 * (event.delta / 120)), "units"))
        self.result_tree.grid(row=0, column=0, sticky="nsew")
        result_y_scroll.grid(row=0, column=1, sticky="ns")
        result_x_scroll.grid(row=1, column=0, sticky="ew")
        result_table_frame.rowconfigure(0, weight=1)
        result_table_frame.columnconfigure(0, weight=1)

        summary_box = ttk.LabelFrame(summary_tab, text="汇总统计", padding=8)
        summary_box.pack(fill=tk.BOTH, expand=True)
        summary_columns = ("wav", "speech_rate", "duration", "vol", "band", "distance", "dband", "angle", "trials", "success", "rate", "latency", "ready_rate", "ready_ms", "rms", "peak")
        summary_table_frame = ttk.Frame(summary_box)
        summary_table_frame.pack(fill=tk.BOTH, expand=True)
        self.summary_tree = ttk.Treeview(summary_table_frame, columns=summary_columns, show="headings", height=18)
        summary_headings = {"wav": "音频", "speech_rate": "语速", "duration": "播放时长(s)", "vol": "音量", "band": "音量档", "distance": "距离(cm)", "dband": "距离档", "angle": "角度", "trials": "次数", "success": "成功", "rate": "成功率", "latency": "平均延迟(ms)", "ready_rate": "恢复率", "ready_ms": "平均恢复(ms)", "rms": "RMS范围", "peak": "Peak范围"}
        summary_widths = {"wav": 250, "speech_rate": 70, "duration": 100, "vol": 70, "band": 80, "distance": 90, "dband": 80, "angle": 90, "trials": 70, "success": 70, "rate": 80, "latency": 120, "ready_rate": 90, "ready_ms": 120, "rms": 120, "peak": 120}
        for col in summary_columns:
            self.summary_tree.heading(col, text=summary_headings[col])
            self.summary_tree.column(col, width=summary_widths[col], anchor=tk.CENTER)
        summary_y_scroll = ttk.Scrollbar(summary_table_frame, orient=tk.VERTICAL, command=self.summary_tree.yview)
        summary_x_scroll = ttk.Scrollbar(summary_table_frame, orient=tk.HORIZONTAL, command=self.summary_tree.xview)
        self.summary_tree.configure(yscrollcommand=summary_y_scroll.set, xscrollcommand=summary_x_scroll.set)
        self.summary_tree.bind("<MouseWheel>", lambda event: self.summary_tree.yview_scroll(int(-1 * (event.delta / 120)), "units"))
        self.summary_tree.grid(row=0, column=0, sticky="nsew")
        summary_y_scroll.grid(row=0, column=1, sticky="ns")
        summary_x_scroll.grid(row=1, column=0, sticky="ew")
        summary_table_frame.rowconfigure(0, weight=1)
        summary_table_frame.columnconfigure(0, weight=1)

        log_box = ttk.LabelFrame(logs_tab, text="实时串口日志", padding=8)
        log_box.pack(fill=tk.BOTH, expand=True)
        self.log_text = ScrolledText(log_box, height=20, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _load_default_wavs(self) -> None:
        if DEFAULT_ASSET_DIR.exists():
            for wav in sorted(DEFAULT_ASSET_DIR.glob("*.wav")):
                self.wav_list.insert(tk.END, str(wav))
        self._load_saved_config()

    def _refresh_ports(self) -> None:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo["values"] = ports
        if DEFAULT_PORT in ports:
            self.port_var.set(DEFAULT_PORT)
        elif ports:
            self.port_var.set(ports[0])

    def _refresh_output_devices(self) -> None:
        self.output_devices = {"系统默认": -1}
        try:
            devices = sd.query_devices()
            for index, device in enumerate(devices):
                if int(device.get("max_output_channels", 0)) > 0:
                    self.output_devices[f"{index}: {device['name']}"] = index
        except Exception as exc:
            self.ui_queue.put(("log", f"[提示] 刷新音频设备失败: {exc}\n"))
        values = list(self.output_devices.keys())
        self.output_device_combo["values"] = values
        if self.output_device_var.get() not in self.output_devices:
            self.output_device_var.set("系统默认")

    def add_wavs(self) -> None:
        files = filedialog.askopenfilenames(
            title="选择 WAV 文件",
            initialdir=str(DEFAULT_ASSET_DIR if DEFAULT_ASSET_DIR.exists() else Path.cwd()),
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
        )
        existing = set(self.wav_list.get(0, tk.END))
        for file in files:
            if file not in existing:
                self.wav_list.insert(tk.END, file)

    def remove_selected_wavs(self) -> None:
        for idx in reversed(self.wav_list.curselection()):
            self.wav_list.delete(idx)

    def fill_volume_range(self) -> None:
        try:
            start = int(self.volume_start_var.get().strip())
            end = int(self.volume_end_var.get().strip())
            step = int(self.volume_step_var.get().strip())
            if start < 0 or start > 100 or end < 0 or end > 100:
                raise ValueError("音量范围必须在 0-100 之间")
            if step <= 0:
                raise ValueError("步进必须大于 0")
            if start > end:
                raise ValueError("起始音量不能大于结束音量")
        except ValueError as exc:
            messagebox.showerror("音量范围错误", str(exc))
            return

        values = list(range(start, end + 1, step))
        if values[-1] != end:
            values.append(end)
        self.volumes_var.set(",".join(str(v) for v in values))

    def apply_volume_band(self, band: str) -> None:
        presets = {
            "low": ("10,20,30", "10", "30"),
            "mid": ("40,50,60,70", "40", "70"),
            "high": ("80,90,100", "80", "100"),
        }
        if band not in presets:
            return
        volumes, start, end = presets[band]
        self.volumes_var.set(volumes)
        self.volume_start_var.set(start)
        self.volume_end_var.set(end)
        self.volume_step_var.set("10")
        self.trials_var.set("10")

    def apply_distance_band(self, band: str) -> None:
        presets = {
            "near": "5,10,15",
            "mid": "20,25",
            "far": "30,35",
            "all": "5,10,15,20,25,30,35",
        }
        if band not in presets:
            return
        self.distance_var.set(presets[band])
        self.trials_var.set("10")

    def _volume_band(self, volume: int) -> str:
        if 10 <= volume <= 30:
            return "low"
        if 40 <= volume <= 70:
            return "mid"
        if 80 <= volume <= 100:
            return "high"
        return "custom"

    def _distance_band(self, distance_cm: str) -> str:
        try:
            value = float(str(distance_cm).strip())
        except ValueError:
            return "custom"
        if 5 <= value <= 15:
            return "near"
        if 20 <= value <= 25:
            return "mid"
        if 30 <= value <= 35:
            return "far"
        return "custom"

    def _refresh_speech_rate_hint(self) -> None:
        if hasattr(self, "speech_rate_hint_var"):
            self.speech_rate_hint_var.set(self._build_speech_rate_hint(self.speech_rates_var.get()))

    def apply_speech_rate_preset(self) -> None:
        presets = {
            "标准": "1.0",
            "标准 1.0x": "1.0",
            "慢速-轻微 0.9x": "0.9",
            "慢速-中等 0.8x": "0.8",
            "慢速-明显 0.7x": "0.7",
            "慢速组合 0.6-1.0x": "0.6,0.7,0.8,0.9,1.0",
            "快速-轻微 1.1x": "1.1",
            "快速-中等 1.2x": "1.2",
            "快速-明显 1.3x": "1.3",
            "快速组合 1.0-1.4x": "1.0,1.1,1.2,1.3,1.4",
            "全量七挡 0.7-1.3x": "0.7,0.8,0.9,1.0,1.1,1.2,1.3",
            "慢速三挡": "0.7,0.8,0.9",
            "慢速五挡": "0.6,0.7,0.8,0.9,1.0",
            "快速三挡": "1.1,1.2,1.3",
            "快速五挡": "1.0,1.1,1.2,1.3,1.4",
            "混合七挡": "0.7,0.8,0.9,1.0,1.1,1.2,1.3",
        }
        value = presets.get(self.speech_rate_preset_var.get(), "1.0")
        self.speech_rates_var.set(value)
        self._refresh_speech_rate_hint()

    def apply_ready_preset(self) -> None:
        presets = {
            READY_PRESET_STRICT: DEFAULT_READY_KEYWORDS_TEXT,
            READY_PRESET_RELAXED: "wake_idle frame=",
            READY_PRESET_START_ONLY: "HAL_WAKE_WORD: Wake word detection started",
        }
        self.ready_keywords_var.set(presets.get(self.ready_preset_var.get(), DEFAULT_READY_KEYWORDS_TEXT))

    def apply_tts_mode(self) -> None:
        if not self.tts_mode_var.get():
            return
        self.wait_ready_var.set(True)
        self.gap_var.set("5.0")
        self.ready_timeout_var.set("90.0")
        self.ready_preset_var.set(READY_PRESET_RELAXED)
        self.apply_ready_preset()

    def apply_test_mode(self) -> None:
        mode = self.test_mode_var.get()
        self.wait_ready_var.set(True)
        self.ready_preset_var.set(READY_PRESET_RELAXED)
        self.apply_ready_preset()
        self.wait_var.set("8.0")
        if mode in (TEST_MODE_DIALOG, TEST_MODE_ISSUE33, TEST_MODE_ISSUE34):
            self.tts_mode_var.set(True)
            self.apply_tts_mode()
            if mode == TEST_MODE_ISSUE33:
                self.trials_var.set("100")
                self.volumes_var.set("60")
                self.volume_start_var.set("60")
                self.volume_end_var.set("60")
                self.speech_rates_var.set("1.0")
                self.wait_var.set("10.0")
                self.gap_var.set("5.0")
                self.ready_timeout_var.set("120.0")
            elif mode == TEST_MODE_ISSUE34:
                self.trials_var.set("10")
                self.volumes_var.set("10,20,30,40,50,60,70,80,90,100")
                self.volume_start_var.set("10")
                self.volume_end_var.set("100")
                self.speech_rates_var.set("1.0")
                self.wait_var.set("10.0")
                self.gap_var.set("5.0")
                self.ready_timeout_var.set("120.0")
            return
        self.tts_mode_var.set(False)
        self.gap_var.set("5.0")
        self.ready_timeout_var.set("35.0")

    def _preset_for_ready_keywords(self, keywords_text: str) -> str:
        normalized = ",".join(self._split_keywords(keywords_text))
        if normalized == "wake_idle frame=":
            return READY_PRESET_RELAXED
        if normalized == "HAL_WAKE_WORD: Wake word detection started":
            return READY_PRESET_START_ONLY
        if normalized == ",".join(self._split_keywords(DEFAULT_READY_KEYWORDS_TEXT)):
            return READY_PRESET_STRICT
        return self.ready_preset_var.get()

    def _build_speech_rate_hint(self, rates_text: str) -> str:
        hints = []
        for part in rates_text.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                rate = float(part)
            except ValueError:
                continue
            if rate <= 0:
                continue
            if rate < 0.75:
                label = "明显慢速"
            elif rate < 1:
                label = "慢速"
            elif rate > 1.25:
                label = "明显快速"
            elif rate > 1:
                label = "快速"
            else:
                label = "原速"
            hints.append(f"{rate:g}x={label}/时长{(1 / rate):.2f}倍")
        return "语速说明：" + ("；".join(hints) if hints else "1.0x=原速/时长1.00倍")

    def play_selected_once(self) -> None:
        selection = self.wav_list.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先选中一个 WAV 文件")
            return
        wav = self.wav_list.get(selection[0])
        threading.Thread(target=self._play_wav, args=(wav, 100), daemon=True).start()

    def start_test(self) -> None:
        if self.test_thread and self.test_thread.is_alive():
            return
        try:
            config = self._read_config()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self.stop_event.clear()
        self.results.clear()
        self.recent_events.clear()
        self.raw_log_lines.clear()
        for row in self.result_tree.get_children():
            self.result_tree.delete(row)
        for row in self.summary_tree.get_children():
            self.summary_tree.delete(row)

        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_var.set("正在打开串口并启动测试...")
        self.next_round_var.set("Next round: opening serial")

        self.test_thread = threading.Thread(target=self._run_test, args=(config,), daemon=True)
        self.test_thread.start()

    def single_test_selected(self) -> None:
        if self.test_thread and self.test_thread.is_alive():
            messagebox.showinfo("提示", "测试运行中不能启动单次测试")
            return
        selection = self.wav_list.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先选中一个 WAV 文件")
            return
        try:
            config = self._read_config()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        wav = self.wav_list.get(selection[0])
        volume = config["volumes"][0]
        speech_rate = config["speech_rates"][0]
        config["wavs"] = [wav]
        config["volumes"] = [volume]
        config["speech_rates"] = [speech_rate]
        config["trials"] = 1

        self.stop_event.clear()
        self.status_var.set(f"单次测试: {Path(wav).name} 语速 {speech_rate:g}x 音量 {volume}%")
        self.next_round_var.set("Next round: opening serial")
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.test_thread = threading.Thread(target=self._run_test, args=(config,), daemon=True)
        self.test_thread.start()

    def stop_test(self) -> None:
        self.stop_event.set()
        self.status_var.set("正在停止...")

    def _read_config(self) -> dict:
        if self.wav_scope_var.get() == "selected":
            wavs = [self.wav_list.get(index) for index in self.wav_list.curselection()]
            if not wavs:
                raise ValueError("当前测试范围是“选中音频”，请先选择至少一个 WAV；或切换为“全部音频”")
        else:
            wavs = list(self.wav_list.get(0, tk.END))
        if not wavs:
            raise ValueError("请至少添加一个 WAV 文件")
        for wav in wavs:
            if not Path(wav).exists():
                raise ValueError(f"WAV 文件不存在: {wav}")
        if self.test_mode_var.get() in (TEST_MODE_DIALOG, TEST_MODE_ISSUE33, TEST_MODE_ISSUE34):
            wake_only_wavs = [Path(wav).stem.lower() for wav in wavs]
            if wake_only_wavs and all(name.startswith("jarvis_tts") or name == "jarvis" for name in wake_only_wavs):
                raise ValueError("dialog mode needs WAV audio with Jarvis plus a command, not wake-word-only audio.")
        volumes = []
        for part in self.volumes_var.get().split(","):
            part = part.strip()
            if not part:
                continue
            value = int(part)
            if value < 0 or value > 100:
                raise ValueError("音量必须在 0-100 之间")
            volumes.append(value)
        if not volumes:
            raise ValueError("请填写音量列表，例如 10,20,30")
        speech_rates = []
        for part in self.speech_rates_var.get().split(","):
            part = part.strip()
            if not part:
                continue
            value = float(part)
            if value <= 0 or value > 3:
                raise ValueError("语速倍率必须大于 0 且不超过 3，例如 0.8,1.0,1.2")
            speech_rates.append(value)
        if not speech_rates:
            raise ValueError("请填写语速列表，例如 0.8,1.0,1.2")
        distances = []
        for part in self.distance_var.get().split(","):
            part = part.strip()
            if not part:
                continue
            try:
                value = float(part)
            except ValueError as exc:
                raise ValueError("distance(cm) must be a number or comma list, for example 5,10,15") from exc
            if value <= 0:
                raise ValueError("distance(cm) must be greater than 0")
            distances.append(str(int(value)) if value.is_integer() else f"{value:g}")
        if not distances:
            raise ValueError("Please enter at least one distance(cm), for example 30 or 5,10,15")
        wake_keywords = self._split_keywords(self.wake_keywords_var.get())
        ready_keywords = self._split_keywords(self.ready_keywords_var.get())
        if not wake_keywords:
            raise ValueError("请填写至少一个唤醒关键字，例如 Wake word detected 或 Jarvis detected")
        if self.wait_ready_var.get() and not ready_keywords:
            raise ValueError("启用等待恢复时，请填写至少一个恢复关键字，例如 IDLE,READY")
        config = {
            "port": self.port_var.get().strip(),
            "baud": int(self.baud_var.get().strip()),
            "wavs": wavs,
            "volumes": volumes,
            "speech_rates": speech_rates,
            "trials": int(self.trials_var.get().strip()),
            "wait_sec": self._parse_seconds(self.wait_var.get(), "等待检测(s)"),
            "gap_sec": self._parse_seconds(self.gap_var.get(), "轮次间隔(s)"),
            "wake_keywords": wake_keywords,
            "wait_ready": bool(self.wait_ready_var.get()),
            "ready_keywords": ready_keywords,
            "ready_timeout_sec": self._parse_seconds(self.ready_timeout_var.get(), "最大恢复等待(s)"),
            "tts_mode": bool(self.tts_mode_var.get()),
            "test_mode": self.test_mode_var.get().strip(),
            "volume_mode": self.volume_mode_var.get().strip(),
            "distance_cm": distances[0],
            "distances_cm": distances,
            "angle": self.angle_var.get().strip(),
            "environment_note": self.environment_var.get().strip(),
            "output_device": self.output_device_var.get().strip(),
            "wav_scope": self.wav_scope_var.get().strip(),
        }
        self._save_config(config)
        return config

    def _parse_seconds(self, value: str, label: str) -> float:
        text = value.strip().lower().replace("秒", "").rstrip("s").strip()
        try:
            seconds = float(text)
        except ValueError as exc:
            raise ValueError(f"{label} 必须是数字，例如 5 或 10") from exc
        if seconds < 0:
            raise ValueError(f"{label} 不能小于 0")
        return seconds

    def _split_keywords(self, text: str) -> List[str]:
        return [item.strip() for item in re.split(r"[,，;；\n]+", text) if item.strip()]

    def _line_matches_keywords(self, line: str, keywords: List[str]) -> bool:
        lower_line = line.lower()
        return any(keyword.lower() in lower_line for keyword in keywords)

    def _run_test(self, config: dict) -> None:
        try:
            self.serial_conn = serial.Serial(config["port"], config["baud"], timeout=0.1)
        except Exception as exc:
            self.ui_queue.put(("error", f"打开串口失败: {exc}"))
            self.ui_queue.put(("done", True))
            return

        self.serial_thread = threading.Thread(target=self._serial_reader, daemon=True)
        self.serial_thread.start()

        DEFAULT_RESULT_DIR.mkdir(parents=True, exist_ok=True)
        self.live_log_path = DEFAULT_RESULT_DIR / f"wake_live_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        self.live_log_path.write_text("", encoding="utf-8")
        self.ui_queue.put(("status", f"串口已连接: {config['port']} @ {config['baud']}"))
        self.ui_queue.put(("log", f"[实时日志] {self.live_log_path}\n"))
        self.tts_active = False
        self.last_tts_done_ts = 0.0
        self.ui_queue.put(("next_state", "Next round: checking wake path"))
        time.sleep(1.0)

        try:
            if config["volume_mode"] in ("windows", "both"):
                self.original_master_volume = self._get_windows_master_volume()
                if self.original_master_volume is not None:
                    self.ui_queue.put(("log", f"[音量] 已记录原始 Windows 主音量 {round(self.original_master_volume * 100)}%\n"))

            if not self._check_device_ready(3.0):
                self.ui_queue.put(("log", "[提示] 3秒内未看到唤醒链路日志，设备可能未进入监听状态。\n"))

            total_steps = len(config["wavs"]) * len(config["speech_rates"]) * len(config["volumes"]) * len(config["distances_cm"]) * config["trials"]
            done_steps = 0
            self.ui_queue.put(("progress", (done_steps, total_steps)))

            for wav in config["wavs"]:
                for speech_rate in config["speech_rates"]:
                    for volume in config["volumes"]:
                        if self.stop_event.is_set():
                            break
                        if config["volume_mode"] in ("windows", "both"):
                            self._set_windows_master_volume(volume)
                        for trial_step in range(1, config["trials"] * len(config["distances_cm"]) + 1):
                            if self.stop_event.is_set():
                                break
                            distance_cm = config["distances_cm"][(trial_step - 1) // config["trials"]]
                            trial = ((trial_step - 1) % config["trials"]) + 1
                            self.ui_queue.put(
                                (
                                    "status",
                                    f"测试中: {Path(wav).name} 语速 {speech_rate:g}x 音量 {volume}% 第 {trial}/{config['trials']} 次",
                                )
                            )
                            result = self._run_single_trial(
                                wav,
                                speech_rate,
                                volume,
                                trial,
                                config["wait_sec"],
                                config["volume_mode"],
                                distance_cm,
                                config["angle"],
                                config["environment_note"],
                                config["wake_keywords"],
                                config["wait_ready"],
                                config["ready_keywords"],
                                config["ready_timeout_sec"],
                                config["test_mode"],
                            )
                            self.results.append(result)
                            self.ui_queue.put(("result", result))
                            done_steps += 1
                            self.ui_queue.put(("progress", (done_steps, total_steps)))
                            self._sleep_interruptible(config["gap_sec"])
        finally:
            was_stopped = self.stop_event.is_set()
            if self.original_master_volume is not None:
                self._set_windows_master_volume_scalar(self.original_master_volume)
                self.ui_queue.put(
                    ("log", f"[音量] 已恢复 Windows 主音量 {round(self.original_master_volume * 100)}%\n")
                )
            self._auto_save_results()
            self.stop_event.set()
            try:
                if self.serial_conn:
                    self.serial_conn.close()
            except Exception:
                pass
            self.ui_queue.put(("done", was_stopped))

    def _run_single_trial(
        self,
        wav: str,
        speech_rate: float,
        volume: int,
        trial: int,
        wait_sec: float,
        volume_mode: str,
        distance_cm: str,
        angle: str,
        environment_note: str,
        wake_keywords: List[str],
        wait_ready: bool,
        ready_keywords: List[str],
        ready_timeout_sec: float,
        test_mode: str,
    ) -> TrialResult:
        if wait_ready and not self._wait_until_ready_before_trial(ready_keywords, ready_timeout_sec):
            events = self._events_between(time.time() - 10, time.time())
            rms_max, peak_max = self._extract_rms_peak_max(events)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return TrialResult(
                timestamp=now,
                wav_file=Path(wav).name,
                speech_rate=speech_rate,
                playback_duration_sec=self._get_playback_duration_sec(wav, speech_rate),
                volume_percent=volume,
                volume_band=self._volume_band(volume),
                trial_index=trial,
                distance_cm=distance_cm,
                distance_band=self._distance_band(distance_cm),
                angle=angle,
                environment_note=environment_note,
                detected=False,
                latency_ms=None,
                rms_max=rms_max,
                peak_max=peak_max,
                ready_status="起始未就绪",
                ready_ms=None,
                ready_line="",
                wake_line="",
                test_mode=test_mode,
                failure_reason="pre_ready_timeout",
                log_excerpt="\n".join(e.line.strip() for e in events[-12:]),
            )

        start_ts = time.time()
        playback_volume = volume if volume_mode in ("software", "both") else 100
        playback_duration_sec = self._get_playback_duration_sec(wav, speech_rate)
        self.ui_queue.put(("next_state", "Next round: playing wake audio"))
        self._play_wav(wav, playback_volume, speech_rate)
        self.ui_queue.put(("next_state", "Next round: waiting for wake detection"))

        deadline = time.time() + wait_sec
        detected = False
        wake_line = ""
        latency_ms: Optional[int] = None
        wake_ts: Optional[float] = None

        while time.time() < deadline and not self.stop_event.is_set():
            events = self._events_since(start_ts)
            for event in events:
                if self._line_matches_keywords(event.line, wake_keywords):
                    detected = True
                    wake_line = event.line.strip()
                    wake_ts = event.ts
                    latency_ms = int((event.ts - start_ts) * 1000)
                    self.ui_queue.put(("next_state", "Next round: wake detected, processing"))
                    break
            if detected:
                break
            time.sleep(0.05)
        if not detected:
            self.ui_queue.put(("next_state", "Next round: wake not detected"))

        ready_status = "未启用"
        ready_ms: Optional[int] = None
        ready_line = ""
        if wait_ready and detected and wake_ts is not None and test_mode == TEST_MODE_WAKE_ONLY:
            ready_status, ready_ms, ready_line = self._wait_wake_only_recovery(wake_ts, ready_timeout_sec)
        elif wait_ready:
            if not detected or wake_ts is None:
                ready_status = "未唤醒"
            else:
                ready_status = "超时"
                ready_deadline = time.time() + ready_timeout_sec
                self.ui_queue.put(("next_state", "Next round: waiting for ESP32 ready"))
                self.ui_queue.put(("log", f"[恢复] 已唤醒，等待 ESP32 回到待唤醒状态，最长 {ready_timeout_sec:g}s\n"))
                while time.time() < ready_deadline and not self.stop_event.is_set():
                    for event in self._events_since(wake_ts):
                        if event.ts <= wake_ts:
                            continue
                        if self._line_matches_keywords(event.line, ready_keywords):
                            ready_status = "成功"
                            ready_line = event.line.strip()
                            ready_ms = int((event.ts - wake_ts) * 1000)
                            break
                    if ready_status == "成功":
                        break
                    time.sleep(0.05)
                if ready_status == "成功":
                    self.ui_queue.put(("next_state", "Next round: ready"))
                    self.ui_queue.put(("log", f"[恢复] ESP32 已恢复待唤醒: {ready_line}，耗时 {ready_ms}ms\n"))
                else:
                    self.ui_queue.put(("next_state", "Next round: ready timeout"))
                    self.ui_queue.put(("log", "[恢复] 等待恢复待唤醒超时，继续下一轮\n"))

        events = self._events_between(start_ts, time.time())
        rms_max, peak_max = self._extract_rms_peak_max(events)
        dialog_events = self._analyze_dialog_events(events, detected, ready_status)

        excerpt = "\n".join(e.line.strip() for e in events[-12:])
        return TrialResult(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            wav_file=Path(wav).name,
            speech_rate=speech_rate,
            playback_duration_sec=playback_duration_sec,
            volume_percent=volume,
            volume_band=self._volume_band(volume),
            trial_index=trial,
            distance_cm=distance_cm,
            distance_band=self._distance_band(distance_cm),
            angle=angle,
            environment_note=environment_note,
            detected=detected,
            latency_ms=latency_ms,
            rms_max=rms_max,
            peak_max=peak_max,
            ready_status=ready_status,
            ready_ms=ready_ms,
            ready_line=ready_line,
            wake_line=wake_line,
            test_mode=test_mode,
            recording_seen=dialog_events["recording_seen"],
            audio_end_seen=dialog_events["audio_end_seen"],
            asr_seen=dialog_events["asr_seen"],
            asr_text=dialog_events["asr_text"],
            asr_text_nonempty=dialog_events["asr_text_nonempty"],
            tts_pause_seen=dialog_events["tts_pause_seen"],
            tts_started_seen=dialog_events["tts_started_seen"],
            tts_complete_seen=dialog_events["tts_complete_seen"],
            resume_seen=dialog_events["resume_seen"],
            ready_seen=dialog_events["ready_seen"],
            dialog_success=dialog_events["dialog_success"],
            failure_reason=dialog_events["failure_reason"],
            round_duration_ms=int((time.time() - start_ts) * 1000),
            log_excerpt=excerpt,
        )

    def _extract_rms_peak_max(self, events: List[LogEvent]) -> Tuple[Optional[int], Optional[int]]:
        rms_values = []
        peak_values = []
        for event in events:
            match = IDLE_STATS_RE.search(event.line) or AUDIO_STATS_RE.search(event.line)
            if match:
                rms_values.append(int(match.group("rms")))
                peak_values.append(int(match.group("peak")))
        return (
            max(rms_values) if rms_values else None,
            max(peak_values) if peak_values else None,
        )

    def _extract_asr_text(self, line: str) -> str:
        for pattern in (r'"text"\s*:\s*"([^"]*)"', r"'text'\s*:\s*'([^']*)'"):
            match = re.search(pattern, line)
            if match:
                return match.group(1).strip()
        if "ASR result:" in line:
            return line.split("ASR result:", 1)[1].strip().strip('"')
        return ""

    def _analyze_dialog_events(self, events: List[LogEvent], detected: bool, ready_status: str) -> Dict[str, object]:
        lines = [event.line.strip() for event in events]
        lower_lines = [line.lower() for line in lines]

        recording_seen = any(
            "state -> recording" in line
            or "vad enabled" in line
            or "wake word triggered recording" in line
            or "start recording" in line
            for line in lower_lines
        )
        audio_end_seen = any(
            "audio end marker sent" in line
            or "vad triggered stop" in line
            or "voice session finished" in line
            or "empty_asr" in line
            for line in lower_lines
        )
        asr_lines = [line for line in lines if "evt.asr.result" in line.lower() or "asr result:" in line]
        asr_text = ""
        for line in asr_lines:
            text = self._extract_asr_text(line)
            if text:
                asr_text = text
                break
        asr_seen = bool(asr_lines)
        asr_text_nonempty = bool(asr_text.strip())
        tts_pause_seen = any(
            "pausing wake word detection for tts" in line
            or "wake word detection stopped" in line
            or "microphone pause" in line
            for line in lower_lines
        )
        tts_started_seen = any(
            "tts started" in line
            or "audio mode: playback" in line
            or "switching sample rate: 16000 -> 24000" in line
            or "playback started" in line
            for line in lower_lines
        )
        tts_complete_seen = any(
            "tts playback complete" in line
            or "tts session complete" in line
            or "audio stop requested; wake word path restored" in line
            or "playback complete" in line
            for line in lower_lines
        )
        resume_seen = any(
            "resuming wake word detection" in line
            or "hal_wake_word: wake word detection started" in line
            for line in lower_lines
        )
        ready_seen = resume_seen or ready_status == "成功" or any("wake_idle frame=" in line for line in lower_lines)

        required_checks = (
            (detected, "no_wake"),
            (recording_seen, "no_recording"),
            (audio_end_seen, "no_audio_end"),
            (asr_seen, "no_asr"),
            (asr_text_nonempty, "empty_asr"),
            (tts_started_seen, "no_tts_start"),
            (tts_complete_seen, "no_tts_complete"),
            (resume_seen or ready_seen, "no_resume"),
        )
        failure_reason = ""
        for passed, reason in required_checks:
            if not passed:
                failure_reason = reason
                break
        if not failure_reason and ready_status == "超时":
            failure_reason = "ready_timeout"
        dialog_success = failure_reason == ""

        return {
            "recording_seen": recording_seen,
            "audio_end_seen": audio_end_seen,
            "asr_seen": asr_seen,
            "asr_text": asr_text,
            "asr_text_nonempty": asr_text_nonempty,
            "tts_pause_seen": tts_pause_seen,
            "tts_started_seen": tts_started_seen,
            "tts_complete_seen": tts_complete_seen,
            "resume_seen": resume_seen,
            "ready_seen": ready_seen,
            "dialog_success": dialog_success,
            "failure_reason": failure_reason,
        }

    def _wait_wake_only_recovery(self, wake_ts: float, timeout_sec: float) -> Tuple[str, Optional[int], str]:
        deadline = time.time() + max(timeout_sec, 0)
        vad_stop_ts: Optional[float] = None
        audio_end_ts: Optional[float] = None
        stop_line = ""
        seen_event_ids = set()

        self.ui_queue.put(("next_state", "Next round: waiting for wake-only recovery"))
        self.ui_queue.put(
            (
                "log",
                f"[wake-only] Wake detected; waiting for VAD/audio end, then resume or {timeout_sec:g}s cooldown\n",
            )
        )

        while time.time() < deadline and not self.stop_event.is_set():
            for event in self._events_since(wake_ts):
                if event.ts <= wake_ts:
                    continue
                event_id = (event.ts, event.line)
                if event_id in seen_event_ids:
                    continue
                seen_event_ids.add(event_id)
                line = event.line.strip()
                lower_line = line.lower()

                if vad_stop_ts is None and "vad triggered stop" in lower_line:
                    vad_stop_ts = event.ts
                    stop_line = line
                    self.ui_queue.put(("next_state", "Next round: VAD stopped"))
                    self.ui_queue.put(("log", f"[wake-only] VAD stopped: {line}\n"))
                    continue

                if audio_end_ts is None and "audio end marker sent" in lower_line:
                    audio_end_ts = event.ts
                    stop_line = line
                    self.ui_queue.put(("next_state", "Next round: audio ended"))
                    self.ui_queue.put(("log", f"[wake-only] Audio end marker observed: {line}\n"))
                    continue

                gate_ts = audio_end_ts or vad_stop_ts
                if gate_ts is None or event.ts <= gate_ts:
                    continue

                is_resume = any(keyword.lower() in lower_line for keyword in WAKE_ONLY_RESUME_KEYWORDS)
                is_detector_started = "hal_wake_word: wake word detection started" in lower_line
                if is_detector_started and audio_end_ts is None:
                    continue

                if is_resume:
                    elapsed_ms = int((event.ts - wake_ts) * 1000)
                    self.ui_queue.put(("next_state", "Next round: ready"))
                    self.ui_queue.put(("log", f"[wake-only] Wake detector resumed: {line}, elapsed {elapsed_ms}ms\n"))
                    return "success", elapsed_ms, line

            time.sleep(0.05)

        if audio_end_ts is not None or vad_stop_ts is not None:
            elapsed_ms = int((time.time() - wake_ts) * 1000)
            self.ui_queue.put(("next_state", "Next round: cooldown done"))
            self.ui_queue.put(("log", f"[wake-only] Resume line not observed; cooldown done after {elapsed_ms}ms\n"))
            return "cooldown", elapsed_ms, stop_line

        self.ui_queue.put(("next_state", "Next round: ready timeout"))
        self.ui_queue.put(("log", "[wake-only] Timed out before VAD/audio end; next round may be risky\n"))
        return "timeout", None, ""

    def _serial_reader(self) -> None:
        while not self.stop_event.is_set() and self.serial_conn and self.serial_conn.is_open:
            try:
                raw = self.serial_conn.readline()
            except Exception as exc:
                self.ui_queue.put(("log", f"[串口读取错误] {exc}\n"))
                break
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").rstrip()
            event = LogEvent(time.time(), line)
            self._update_tts_state_from_line(line, event.ts)
            self.log_queue.put(event)
            stamped_line = f"{datetime.fromtimestamp(event.ts).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} {line}"
            self.raw_log_lines.append(stamped_line)
            if self.live_log_path:
                try:
                    with self.live_log_path.open("a", encoding="utf-8") as f:
                        f.write(stamped_line + "\n")
                except Exception:
                    pass
            self.ui_queue.put(("log", line + "\n"))
            inferred_state = self._infer_next_round_state(line)
            if inferred_state:
                self.ui_queue.put(("next_state", inferred_state))

    def _play_wav(self, wav: str, volume: int, speech_rate: float = 1.0) -> None:
        data, samplerate = sf.read(wav, dtype="float32", always_2d=True)
        gain = max(0.0, min(1.0, volume / 100.0))
        data = np.clip(data * gain, -1.0, 1.0)
        device_label = getattr(self, "output_device_var", tk.StringVar(value="系统默认")).get()
        device_index = self.output_devices.get(device_label, -1)
        playback_samplerate = int(round(samplerate * speech_rate))
        sd.play(data, samplerate=playback_samplerate, blocking=True, device=None if device_index == -1 else device_index)
        sd.stop()

    def _get_playback_duration_sec(self, wav: str, speech_rate: float) -> float:
        info = sf.info(wav)
        original_duration = info.frames / float(info.samplerate)
        return original_duration / speech_rate if speech_rate > 0 else original_duration

    def _infer_next_round_state(self, line: str) -> Optional[str]:
        if "wake_idle frame=" in line:
            return "Next round: ready (wake_idle)"
        if "Resuming wake word detection" in line:
            return "Next round: resuming wake detector"
        if "Wake word detection started" in line:
            return "Next round: ready (wake detector started)"
        if "TTS started" in line or "Audio mode: playback" in line:
            return "Next round: playback in progress"
        if "Pausing wake word detection for TTS" in line:
            return "Next round: wake detector paused for TTS"
        if "Wake word detection stopped" in line:
            return "Next round: wake detector stopped"
        if "Wake word triggered recording" in line or "state -> RECORDING" in line:
            return "Next round: recording"
        if "Wake word detected" in line:
            return "Next round: wake detected"
        return None

    def _update_tts_state_from_line(self, line: str, ts: float) -> None:
        if "TTS started" in line or "Audio mode: playback" in line:
            self.tts_active = True
            return
        if "TTS playback complete" in line or "TTS session complete" in line:
            self.tts_active = False
            self.last_tts_done_ts = ts
            return
        if "wake_idle frame=" in line or "Wake word detection started" in line:
            self.tts_active = False

    def _wait_until_ready_before_trial(self, ready_keywords: List[str], timeout_sec: float) -> bool:
        start = time.time()
        if self.tts_mode_var.get() and self.tts_active:
            deadline = start + max(timeout_sec, 0)
            self.ui_queue.put(("next_state", "Next round: waiting for TTS to finish"))
            self.ui_queue.put(("log", f"[播放前检查] TTS 仍在播放，等待结束后再进入下一档，最长 {timeout_sec:g}s\n"))
            while time.time() < deadline and not self.stop_event.is_set():
                if not self.tts_active:
                    break
                time.sleep(0.05)
            if self.tts_active:
                self.ui_queue.put(("next_state", "Next round: TTS timeout"))
                self.ui_queue.put(("log", "[播放前检查] 等待 TTS 结束超时，本轮不播放，避免误判\n"))
                return False

        recent_ready = [
            event for event in self._events_since(time.time() - 12)
            if self._line_matches_keywords(event.line, ready_keywords)
        ]
        if recent_ready:
            self.ui_queue.put(("next_state", "Next round: ready before playback"))
            return True

        start = time.time()
        deadline = start + max(timeout_sec, 0)
        self.ui_queue.put(("next_state", "Next round: waiting for ready before playback"))
        self.ui_queue.put(("log", f"[播放前检查] 等待 ESP32 待唤醒后再播放，最长 {timeout_sec:g}s\n"))
        while time.time() < deadline and not self.stop_event.is_set():
            for event in self._events_since(start):
                if self._line_matches_keywords(event.line, ready_keywords):
                    elapsed_ms = int((event.ts - start) * 1000)
                    self.ui_queue.put(("next_state", "Next round: ready before playback"))
                    self.ui_queue.put(("log", f"[播放前检查] ESP32 已待唤醒: {event.line.strip()}，耗时 {elapsed_ms}ms\n"))
                    return True
            time.sleep(0.05)
        self.ui_queue.put(("next_state", "Next round: pre-playback ready timeout"))
        self.ui_queue.put(("log", "[播放前检查] 等待 ESP32 待唤醒超时，本轮不播放，避免误判\n"))
        return False

    def _check_device_ready(self, seconds: float) -> bool:
        start = time.time()
        patterns = ("wake_idle", "Wake word detection", "Voice recorder started", "HAL_WAKE_WORD")
        while time.time() - start < seconds and not self.stop_event.is_set():
            events = self._events_since(start)
            if any(any(pattern in event.line for pattern in patterns) for event in events):
                self.ui_queue.put(("log", "[检查] 已看到唤醒链路日志，设备状态看起来正常。\n"))
                return True
            time.sleep(0.05)
        return False

    def _set_windows_master_volume(self, volume: int) -> None:
        self._set_windows_master_volume_scalar(max(0.0, min(1.0, volume / 100.0)))

    def _set_windows_master_volume_scalar(self, scalar: float) -> None:
        if not PYCaw_AVAILABLE:
            self.ui_queue.put(("log", "[提示] pycaw 不可用，跳过 Windows 主音量设置\n"))
            return
        try:
            devices = AudioUtilities.GetSpeakers()
            endpoint = getattr(devices, "EndpointVolume", None)
            if endpoint is None:
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                endpoint = cast(interface, POINTER(IAudioEndpointVolume))
            endpoint.SetMasterVolumeLevelScalar(max(0.0, min(1.0, scalar)), None)
            actual = int(round(endpoint.GetMasterVolumeLevelScalar() * 100))
            self.ui_queue.put(("log", f"[音量] Windows 主音量已设置为 {actual}%\n"))
        except Exception as exc:
            self.ui_queue.put(("log", f"[提示] 设置 Windows 主音量失败: {exc}\n"))

    def _get_windows_master_volume(self) -> Optional[float]:
        if not PYCaw_AVAILABLE:
            return None
        try:
            devices = AudioUtilities.GetSpeakers()
            endpoint = getattr(devices, "EndpointVolume", None)
            if endpoint is None:
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                endpoint = cast(interface, POINTER(IAudioEndpointVolume))
            return float(endpoint.GetMasterVolumeLevelScalar())
        except Exception as exc:
            self.ui_queue.put(("log", f"[提示] 读取 Windows 主音量失败: {exc}\n"))
            return None

    def _events_since(self, ts: float) -> List[LogEvent]:
        self._drain_log_queue()
        return [e for e in self.recent_events if e.ts >= ts]

    def _events_between(self, start: float, end: float) -> List[LogEvent]:
        self._drain_log_queue()
        return [e for e in self.recent_events if start <= e.ts <= end]

    def _drain_log_queue(self) -> None:
        while True:
            try:
                event = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.recent_events.append(event)
        cutoff = time.time() - 300
        self.recent_events = [e for e in self.recent_events if e.ts >= cutoff]

    def _sleep_interruptible(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end and not self.stop_event.is_set():
            time.sleep(0.05)

    def _pump_queues(self) -> None:
        while True:
            try:
                kind, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log_text.insert(tk.END, payload)
                self.log_text.see(tk.END)
            elif kind == "status":
                self.status_var.set(payload)
            elif kind == "next_state":
                self.next_round_var.set(payload)
            elif kind == "result":
                self._add_result_row(payload)
                self._refresh_summary()
            elif kind == "progress":
                done, total = payload
                self.progress_var.set(f"进度：{done}/{total}")
                self.progress_bar.configure(maximum=max(total, 1), value=done)
            elif kind == "error":
                messagebox.showerror("错误", payload)
            elif kind == "done":
                self.start_btn.configure(state=tk.NORMAL)
                self.stop_btn.configure(state=tk.DISABLED)
                was_stopped = bool(payload)
                self.status_var.set("测试已停止" if was_stopped else "测试完成")
                if was_stopped:
                    self.next_round_var.set("Next round: stopped")
        self.root.after(80, self._pump_queues)

    def _add_result_row(self, result: TrialResult) -> None:
        passed = self._result_passed(result)
        self.result_tree.insert(
            "",
            tk.END,
            values=(
                result.timestamp,
                result.wav_file,
                f"{result.speech_rate:g}x",
                f"{result.playback_duration_sec:.2f}",
                result.volume_percent,
                result.volume_band,
                result.trial_index,
                result.distance_cm,
                result.distance_band,
                result.angle,
                "成功" if passed else "失败",
                "" if result.latency_ms is None else result.latency_ms,
                result.ready_status,
                "" if result.ready_ms is None else result.ready_ms,
                "" if result.rms_max is None else result.rms_max,
                "" if result.peak_max is None else result.peak_max,
            ),
        )

    def _result_passed(self, result: TrialResult) -> bool:
        if result.test_mode in (TEST_MODE_DIALOG, TEST_MODE_ISSUE33, TEST_MODE_ISSUE34):
            return result.dialog_success
        return result.detected

    def _refresh_summary(self) -> None:
        for row in self.summary_tree.get_children():
            self.summary_tree.delete(row)

        grouped = {}
        for result in self.results:
            grouped.setdefault(
                (result.wav_file, result.speech_rate, result.playback_duration_sec, result.volume_percent, result.volume_band, result.distance_cm, result.distance_band, result.angle), []
            ).append(result)

        for (wav_file, speech_rate, duration_sec, volume, volume_band, distance_cm, distance_band, angle), rows in sorted(
            grouped.items(), key=lambda item: (item[0][0], item[0][1], item[0][5], item[0][7], item[0][3])
        ):
            total = len(rows)
            success_rows = [r for r in rows if self._result_passed(r)]
            success = len(success_rows)
            rate = f"{(success / total * 100):.0f}%" if total else "0%"
            latencies = [r.latency_ms for r in success_rows if r.latency_ms is not None]
            ready_rows = [r for r in rows if r.ready_status == "成功"]
            ready_rate = f"{(len(ready_rows) / success * 100):.0f}%" if success else ""
            ready_times = [r.ready_ms for r in ready_rows if r.ready_ms is not None]
            avg_ready = f"{sum(ready_times) / len(ready_times):.0f}" if ready_times else ""
            rms_values = [r.rms_max for r in rows if r.rms_max is not None]
            peak_values = [r.peak_max for r in rows if r.peak_max is not None]
            avg_latency = f"{sum(latencies) / len(latencies):.0f}" if latencies else ""
            rms_range = f"{min(rms_values)}-{max(rms_values)}" if rms_values else ""
            peak_range = f"{min(peak_values)}-{max(peak_values)}" if peak_values else ""
            self.summary_tree.insert(
                "",
                tk.END,
                values=(wav_file, f"{speech_rate:g}x", f"{duration_sec:.2f}", volume, volume_band, distance_cm, distance_band, angle, total, success, rate, avg_latency, ready_rate, avg_ready, rms_range, peak_range),
            )

    def export_csv(self) -> None:
        if not self.results:
            messagebox.showinfo("提示", "当前没有可导出的结果")
            return
        default_name = f"wake_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(
            title="导出 CSV",
            initialdir=str(DEFAULT_ASSET_DIR if DEFAULT_ASSET_DIR.exists() else Path.cwd()),
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(self.results[0]).keys()))
            writer.writeheader()
            for result in self.results:
                writer.writerow(asdict(result))
        messagebox.showinfo("完成", f"已导出: {path}")

    def save_charts(self) -> None:
        if not self.results:
            messagebox.showinfo("提示", "当前没有可生成图表的结果")
            return
        DEFAULT_RESULT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        success_path = DEFAULT_RESULT_DIR / f"wake_success_rate_{stamp}.png"
        peak_path = DEFAULT_RESULT_DIR / f"wake_peak_rms_{stamp}.png"
        self._save_success_chart(success_path)
        self._save_peak_rms_chart(peak_path)
        messagebox.showinfo("完成", f"图表已保存:\n{success_path}\n{peak_path}")

    def _group_results_for_charts(self):
        grouped = {}
        for result in self.results:
            key = (result.wav_file, result.speech_rate, result.distance_cm, result.angle, result.volume_percent)
            grouped.setdefault(key, []).append(result)
        return grouped

    def _save_success_chart(self, path: Path) -> None:
        grouped = self._group_results_for_charts()
        series = {}
        for (wav, speech_rate, distance, angle, volume), rows in grouped.items():
            label = f"{wav} | {speech_rate:g}x | {distance}cm | {angle}"
            success = sum(1 for row in rows if self._result_passed(row))
            rate = success / len(rows) * 100 if rows else 0
            series.setdefault(label, []).append((volume, rate))

        plt.figure(figsize=(11, 6))
        for label, points in sorted(series.items()):
            points = sorted(points)
            plt.plot([p[0] for p in points], [p[1] for p in points], marker="o", label=label)
        plt.title("Wake Word Success Rate")
        plt.xlabel("Volume (%)")
        plt.ylabel("Success Rate (%)")
        plt.ylim(-5, 105)
        plt.grid(True, alpha=0.3)
        plt.legend(fontsize=8)
        plt.tight_layout()
        plt.savefig(path, dpi=150)
        plt.close()

    def _save_peak_rms_chart(self, path: Path) -> None:
        grouped = self._group_results_for_charts()
        points = []
        for (wav, speech_rate, distance, angle, volume), rows in grouped.items():
            peaks = [row.peak_max for row in rows if row.peak_max is not None]
            rms_values = [row.rms_max for row in rows if row.rms_max is not None]
            if peaks or rms_values:
                points.append(
                    {
                        "label": f"{wav} | {speech_rate:g}x | {distance}cm | {angle}",
                        "volume": volume,
                        "peak": sum(peaks) / len(peaks) if peaks else None,
                        "rms": sum(rms_values) / len(rms_values) if rms_values else None,
                    }
                )

        plt.figure(figsize=(11, 6))
        labels = sorted(set(p["label"] for p in points))
        for label in labels:
            rows = sorted([p for p in points if p["label"] == label], key=lambda item: item["volume"])
            volumes = [p["volume"] for p in rows]
            peaks = [p["peak"] if p["peak"] is not None else np.nan for p in rows]
            rms_values = [p["rms"] if p["rms"] is not None else np.nan for p in rows]
            plt.plot(volumes, peaks, marker="o", label=f"Peak {label}")
            plt.plot(volumes, rms_values, marker="x", linestyle="--", label=f"RMS {label}")
        plt.title("Wake Audio Peak / RMS")
        plt.xlabel("Volume (%)")
        plt.ylabel("PCM Level")
        plt.grid(True, alpha=0.3)
        plt.legend(fontsize=7)
        plt.tight_layout()
        plt.savefig(path, dpi=150)
        plt.close()

    def open_result_dir(self) -> None:
        DEFAULT_RESULT_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(DEFAULT_RESULT_DIR)

    def generate_report(self) -> None:
        if not self.results:
            messagebox.showinfo("提示", "当前没有可生成报告的结果")
            return
        DEFAULT_RESULT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = DEFAULT_RESULT_DIR / f"wake_report_{stamp}.md"
        grouped = {}
        for result in self.results:
            key = (
                result.wav_file,
                result.speech_rate,
                result.playback_duration_sec,
                result.distance_cm,
                result.distance_band,
                result.angle,
                result.volume_percent,
                result.volume_band,
            )
            grouped.setdefault(key, []).append(result)

        rows: List[Tuple[str, float, float, str, str, str, int, str, int, int, float, str, str, str]] = []
        for (wav, speech_rate, duration_sec, distance, distance_band, angle, volume, volume_band), items in sorted(grouped.items()):
            total = len(items)
            success = sum(1 for item in items if self._result_passed(item))
            rate = success / total * 100 if total else 0
            latencies = [item.latency_ms for item in items if item.latency_ms is not None]
            avg_latency = f"{sum(latencies) / len(latencies):.0f}" if latencies else ""
            peaks = [item.peak_max for item in items if item.peak_max is not None]
            rms_values = [item.rms_max for item in items if item.rms_max is not None]
            peak_range = f"{min(peaks)}-{max(peaks)}" if peaks else ""
            rms_range = f"{min(rms_values)}-{max(rms_values)}" if rms_values else ""
            rows.append((wav, speech_rate, duration_sec, distance, distance_band, angle, volume, volume_band, total, success, rate, avg_latency, rms_range, peak_range))

        best = max(rows, key=lambda row: (row[10], -row[6])) if rows else None
        lines = [
            "# WatcheRobot Wake Word Test Report",
            "",
            f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- Serial port: {self.port_var.get()}",
            f"- Volume mode: {self.volume_mode_var.get()}",
            f"- Output device: {self.output_device_var.get()}",
            f"- Environment: {self.environment_var.get()}",
            "",
            "## Conclusion",
            "",
        ]
        if best:
            lines.append(
                f"- Best observed setting: `{best[0]}`, speech rate `{best[1]:g}x`, duration `{best[2]:.2f}s`, distance `{best[3]}cm` ({best[4]}), angle `{best[5]}`, volume `{best[6]}%` ({best[7]}), success rate `{best[10]:.0f}%`."
            )
        if any(row[13] and max(int(v) for v in row[13].split("-")) >= 26000 for row in rows):
            lines.append("- Some Peak values are close to or above 26000; check for loud playback or clipping risk.")
        lines.extend(
            [
                "",
                "## Summary",
                "",
                "| Audio | Speech rate | Duration(s) | Distance(cm) | Distance band | Angle | Volume | Volume band | Trials | Success | Rate | Avg latency(ms) | RMS range | Peak range |",
                "|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---|---|",
            ]
        )
        for row in rows:
            lines.append(
                f"| {row[0]} | {row[1]:g}x | {row[2]:.2f} | {row[3]} | {row[4]} | {row[5]} | {row[6]} | {row[7]} | {row[8]} | {row[9]} | {row[10]:.0f}% | {row[11]} | {row[12]} | {row[13]} |"
            )
        band_groups: Dict[str, List[TrialResult]] = {}
        for result in self.results:
            band_groups.setdefault(result.volume_band, []).append(result)
        if band_groups:
            lines.extend(["", "## Volume Band Summary", "", "| Volume band | Volume range | Trials | Success | Rate |", "|---|---|---:|---:|---:|"])
            ranges = {"low": "10,20,30", "mid": "40,50,60,70", "high": "80,90,100", "custom": "outside defined bands"}
            order = {"low": 0, "mid": 1, "high": 2, "custom": 3}
            for band, items in sorted(band_groups.items(), key=lambda item: order.get(item[0], 99)):
                total = len(items)
                success = sum(1 for item in items if self._result_passed(item))
                rate = success / total * 100 if total else 0
                lines.append(f"| {band} | {ranges.get(band, 'custom')} | {total} | {success} | {rate:.0f}% |")
        distance_groups: Dict[str, List[TrialResult]] = {}
        for result in self.results:
            distance_groups.setdefault(result.distance_band, []).append(result)
        if distance_groups:
            lines.extend(["", "## Distance Band Summary", "", "| Distance band | Distance range(cm) | Trials | Success | Rate |", "|---|---|---:|---:|---:|"])
            ranges = {"near": "5,10,15", "mid": "20,25", "far": "30,35", "custom": "outside defined bands"}
            order = {"near": 0, "mid": 1, "far": 2, "custom": 3}
            for band, items in sorted(distance_groups.items(), key=lambda item: order.get(item[0], 99)):
                total = len(items)
                success = sum(1 for item in items if self._result_passed(item))
                rate = success / total * 100 if total else 0
                lines.append(f"| {band} | {ranges.get(band, 'custom')} | {total} | {success} | {rate:.0f}% |")
        dialog_results = [result for result in self.results if result.test_mode in (TEST_MODE_DIALOG, TEST_MODE_ISSUE33, TEST_MODE_ISSUE34)]
        if dialog_results:
            failure_counts: Dict[str, int] = {}
            for result in dialog_results:
                if self._result_passed(result):
                    continue
                reason = result.failure_reason or "unknown"
                failure_counts[reason] = failure_counts.get(reason, 0) + 1
            dialog_total = len(dialog_results)
            dialog_pass = sum(1 for result in dialog_results if self._result_passed(result))
            lines.extend(
                [
                    "",
                    "## Dialog Chain",
                    "",
                    f"- Dialog pass rate: {dialog_pass}/{dialog_total} ({dialog_pass / dialog_total * 100:.0f}%).",
                    "- Pass means wake detected, recording/audio-end seen, non-empty ASR seen, TTS playback seen, and wake detection resumed.",
                ]
            )
            if failure_counts:
                lines.extend(["", "| Failure reason | Count |", "|---|---:|"])
                for reason, count in sorted(failure_counts.items(), key=lambda item: (-item[1], item[0])):
                    lines.append(f"| {reason} | {count} |")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        messagebox.showinfo("完成", f"报告已生成:\n{report_path}")

    def false_wake_silence_test(self) -> None:
        if self.test_thread and self.test_thread.is_alive():
            messagebox.showinfo("提示", "测试运行中不能启动静音误唤醒测试")
            return
        try:
            config = self._read_config()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        self.stop_event.clear()
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_var.set(f"静音误唤醒测试：监听 {config['wait_sec']} 秒")
        self.test_thread = threading.Thread(target=self._run_false_wake_silence, args=(config,), daemon=True)
        self.test_thread.start()

    def _run_false_wake_silence(self, config: dict) -> None:
        try:
            self.serial_conn = serial.Serial(config["port"], config["baud"], timeout=0.1)
        except Exception as exc:
            self.ui_queue.put(("error", f"打开串口失败: {exc}"))
            self.ui_queue.put(("done", True))
            return

        self.serial_thread = threading.Thread(target=self._serial_reader, daemon=True)
        self.serial_thread.start()
        start_ts = time.time()
        duration = float(config["wait_sec"])
        self.ui_queue.put(("progress", (0, int(duration))))
        try:
            while time.time() - start_ts < duration and not self.stop_event.is_set():
                elapsed = int(time.time() - start_ts)
                self.ui_queue.put(("progress", (elapsed, int(duration))))
                time.sleep(0.2)
            events = self._events_between(start_ts, time.time())
            wake_events = [event for event in events if self._line_matches_keywords(event.line, config["wake_keywords"])]
            rms_max, peak_max = self._extract_rms_peak_max(events)
            result = TrialResult(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                wav_file="SILENCE_FALSE_WAKE",
                speech_rate=1.0,
                playback_duration_sec=duration,
                volume_percent=0,
                volume_band=self._volume_band(0),
                trial_index=1,
                distance_cm=config["distance_cm"],
                distance_band=self._distance_band(config["distance_cm"]),
                angle=config["angle"],
                environment_note=config["environment_note"],
                detected=bool(wake_events),
                latency_ms=int((wake_events[0].ts - start_ts) * 1000) if wake_events else None,
                rms_max=rms_max,
                peak_max=peak_max,
                ready_status="未启用",
                ready_ms=None,
                ready_line="",
                wake_line=wake_events[0].line if wake_events else "",
                log_excerpt="\n".join(e.line.strip() for e in events[-12:]),
            )
            self.results.append(result)
            self.ui_queue.put(("result", result))
            self.ui_queue.put(("progress", (int(duration), int(duration))))
        finally:
            was_stopped = self.stop_event.is_set()
            self._auto_save_results()
            self.stop_event.set()
            try:
                if self.serial_conn:
                    self.serial_conn.close()
            except Exception:
                pass
            self.ui_queue.put(("done", was_stopped))

    def _auto_save_results(self) -> None:
        if not self.results and not self.raw_log_lines:
            return
        DEFAULT_RESULT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.results:
            csv_path = DEFAULT_RESULT_DIR / f"wake_results_{stamp}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=list(asdict(self.results[0]).keys()))
                writer.writeheader()
                for result in self.results:
                    writer.writerow(asdict(result))
            self.ui_queue.put(("log", f"[保存] 测试结果已自动保存: {csv_path}\n"))
        if self.raw_log_lines:
            log_path = DEFAULT_RESULT_DIR / f"wake_raw_log_{stamp}.txt"
            log_path.write_text("\n".join(self.raw_log_lines) + "\n", encoding="utf-8")
            self.ui_queue.put(("log", f"[保存] 原始日志已自动保存: {log_path}\n"))

    def _save_config(self, config: dict) -> None:
        try:
            DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = dict(config)
            data["volume_start"] = self.volume_start_var.get().strip()
            data["volume_end"] = self.volume_end_var.get().strip()
            data["volume_step"] = self.volume_step_var.get().strip()
            data["speech_rate_preset"] = self.speech_rate_preset_var.get().strip()
            data["ready_preset"] = self.ready_preset_var.get().strip()
            data["tts_mode"] = bool(self.tts_mode_var.get())
            data["test_mode"] = self.test_mode_var.get().strip()
            data["wake_keywords_text"] = self.wake_keywords_var.get().strip()
            data["ready_keywords_text"] = self.ready_keywords_var.get().strip()
            DEFAULT_CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_saved_config(self) -> None:
        if not DEFAULT_CONFIG_PATH.exists():
            return
        try:
            data = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        self.port_var.set(data.get("port", self.port_var.get()))
        self.baud_var.set(str(data.get("baud", self.baud_var.get())))
        self.volumes_var.set(",".join(str(v) for v in data.get("volumes", [])) or self.volumes_var.get())
        self.speech_rates_var.set(",".join(str(v) for v in data.get("speech_rates", [])) or self.speech_rates_var.get())
        self.speech_rate_preset_var.set(data.get("speech_rate_preset", self.speech_rate_preset_var.get()))
        self.test_mode_var.set(data.get("test_mode", self.test_mode_var.get()))
        self.ready_preset_var.set(data.get("ready_preset", self.ready_preset_var.get()))
        self.trials_var.set(str(data.get("trials", self.trials_var.get())))
        self.wait_var.set(str(data.get("wait_sec", self.wait_var.get())))
        self.gap_var.set(str(data.get("gap_sec", self.gap_var.get())))
        wake_keywords_text = data.get("wake_keywords_text", ",".join(data.get("wake_keywords", [])) or self.wake_keywords_var.get())
        self.wake_keywords_var.set(wake_keywords_text or DEFAULT_WAKE_KEYWORDS_TEXT)
        self.wait_ready_var.set(bool(data.get("wait_ready", self.wait_ready_var.get())))
        ready_keywords_text = data.get("ready_keywords_text", ",".join(data.get("ready_keywords", [])) or self.ready_keywords_var.get())
        if ready_keywords_text.strip() == LEGACY_READY_KEYWORDS_TEXT:
            ready_keywords_text = DEFAULT_READY_KEYWORDS_TEXT
            data["ready_timeout_sec"] = DEFAULT_READY_TIMEOUT_SEC
        self.ready_keywords_var.set(ready_keywords_text or DEFAULT_READY_KEYWORDS_TEXT)
        self.ready_preset_var.set(self._preset_for_ready_keywords(self.ready_keywords_var.get()))
        self.ready_timeout_var.set(str(data.get("ready_timeout_sec", self.ready_timeout_var.get())))
        self.tts_mode_var.set(bool(data.get("tts_mode", self.tts_mode_var.get())))
        self.apply_test_mode()
        self.volume_mode_var.set(data.get("volume_mode", self.volume_mode_var.get()))
        self.output_device_var.set(data.get("output_device", self.output_device_var.get()))
        self.wav_scope_var.set(data.get("wav_scope", self.wav_scope_var.get()))
        self.distance_var.set(",".join(data.get("distances_cm", [])) or data.get("distance_cm", self.distance_var.get()))
        self.angle_var.set(data.get("angle", self.angle_var.get()))
        self.environment_var.set(data.get("environment_note", self.environment_var.get()))
        self.volume_start_var.set(str(data.get("volume_start", self.volume_start_var.get())))
        self.volume_end_var.set(str(data.get("volume_end", self.volume_end_var.get())))
        self.volume_step_var.set(str(data.get("volume_step", self.volume_step_var.get())))

        saved_wavs = [wav for wav in data.get("wavs", []) if Path(wav).exists()]
        if saved_wavs:
            self.wav_list.delete(0, tk.END)
            for wav in saved_wavs:
                self.wav_list.insert(tk.END, wav)
            if self.wav_scope_var.get() == "selected":
                self.wav_list.selection_set(0, tk.END)
                self.wav_list.activate(0)

    def clear_results(self) -> None:
        if self.test_thread and self.test_thread.is_alive():
            messagebox.showinfo("提示", "测试运行中不能清除结果，请先停止测试")
            return
        self.results.clear()
        for row in self.result_tree.get_children():
            self.result_tree.delete(row)
        for row in self.summary_tree.get_children():
            self.summary_tree.delete(row)
        self.status_var.set("已清除测试结果")

    def clear_logs(self) -> None:
        if self.test_thread and self.test_thread.is_alive():
            messagebox.showinfo("提示", "测试运行中不能清除日志，请先停止测试")
            return
        self.recent_events.clear()
        self.raw_log_lines.clear()
        while True:
            try:
                self.log_queue.get_nowait()
            except queue.Empty:
                break
        self.log_text.delete("1.0", tk.END)
        self.status_var.set("已清除实时日志")

    def clear_status(self) -> None:
        self.status_var.set("就绪")
        self.progress_var.set("进度：0/0")
        self.progress_bar.configure(maximum=1, value=0)
        self.next_round_var.set("Next round: idle")

    def clear_all(self) -> None:
        if self.test_thread and self.test_thread.is_alive():
            messagebox.showinfo("提示", "测试运行中不能清除，请先停止测试")
            return
        self.clear_results()
        self.clear_logs()
        self.status_var.set("已清除结果和日志")


def main() -> None:
    parser = argparse.ArgumentParser(description="WatcheRobot voice wake GUI")
    parser.add_argument("--auto-start", action="store_true", help="Open the GUI and start the configured test automatically.")
    parser.add_argument("--show-logs", action="store_true", help="Select the real-time log tab after opening.")
    args = parser.parse_args()

    root = tk.Tk()
    app = WakeTesterApp(root)
    if args.show_logs:
        root.after(300, lambda: app.content_tabs.select(3))
    if args.auto_start:
        root.after(1000, app.start_test)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.stop_test(), root.after(150, root.destroy)))
    root.mainloop()


if __name__ == "__main__":
    main()
