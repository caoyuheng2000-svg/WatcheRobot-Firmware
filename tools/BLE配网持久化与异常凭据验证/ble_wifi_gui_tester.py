import asyncio
import json
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import messagebox, ttk

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # pragma: no cover - handled by GUI
    BleakClient = None
    BleakScanner = None

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # pragma: no cover - handled by GUI
    serial = None


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
RECORD_DIR = ROOT / "records"
SERVICE_UUID_16 = "00ff"
CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"


@dataclass
class BleDevice:
    name: str
    address: str


class BleWorker:
    def __init__(self, ui_queue: queue.Queue):
        self.ui_queue = ui_queue
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.client: Optional[BleakClient] = None
        self.device: Optional[BleDevice] = None
        self.last_payload = ""

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def scan(self):
        if BleakScanner is None:
            raise RuntimeError("缺少 bleak，请先运行: python -m pip install -r requirements.txt")
        devices = await BleakScanner.discover(timeout=5.0, service_uuids=None)
        result = []
        for dev in devices:
            name = dev.name or "(unknown)"
            result.append(BleDevice(name=name, address=dev.address))
        return result

    async def connect(self, device: BleDevice):
        if BleakClient is None:
            raise RuntimeError("缺少 bleak，请先运行: python -m pip install -r requirements.txt")
        await self.disconnect()
        self.client = BleakClient(device.address)
        await self.client.connect(timeout=12.0)
        self.device = device
        await self.client.start_notify(CHAR_UUID, self._on_notify)
        self.ui_queue.put(("ble", f"已连接 BLE: {device.name} {device.address}"))

    async def disconnect(self):
        if self.client:
            try:
                if self.client.is_connected:
                    try:
                        await self.client.stop_notify(CHAR_UUID)
                    except Exception:
                        pass
                    await self.client.disconnect()
            finally:
                self.client = None
                self.device = None

    async def write_json(self, payload: dict):
        if not self.client or not self.client.is_connected:
            raise RuntimeError("BLE 未连接")
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.last_payload = text
        await self.client.write_gatt_char(CHAR_UUID, text.encode("utf-8"), response=True)
        self.ui_queue.put(("ble", f"TX {text}"))

    def _on_notify(self, _sender, data: bytearray):
        text = data.decode("utf-8", errors="replace").strip()
        self.ui_queue.put(("ble", f"RX {text}"))


class SerialWorker:
    def __init__(self, ui_queue: queue.Queue):
        self.ui_queue = ui_queue
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.handle = None
        self.log_file = None

    @staticmethod
    def ports():
        if serial is None:
            return []
        return [p.device for p in serial.tools.list_ports.comports()]

    def start(self, port: str, baud: int, log_path: Path):
        if serial is None:
            raise RuntimeError("缺少 pyserial，请先运行: python -m pip install -r requirements.txt")
        self.stop()
        self.stop_event.clear()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file = log_path.open("a", encoding="utf-8", errors="replace")
        self.handle = serial.Serial(port=port, baudrate=baud, timeout=0.2)
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        self.ui_queue.put(("serial", f"串口日志已开始: {port} -> {log_path}"))

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.thread = None
        if self.handle:
            try:
                self.handle.close()
            except Exception:
                pass
            self.handle = None
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
            self.log_file = None

    def _read_loop(self):
        while not self.stop_event.is_set():
            try:
                line = self.handle.readline()
                if not line:
                    continue
                text = line.decode("utf-8", errors="replace").rstrip()
                stamped = f"{datetime.now().isoformat(timespec='seconds')} {text}"
                if self.log_file:
                    self.log_file.write(stamped + "\n")
                    self.log_file.flush()
                self.ui_queue.put(("serial", stamped))
            except Exception as exc:
                self.ui_queue.put(("serial", f"串口读取失败: {exc}"))
                break


class TesterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BLE 配网持久化与异常凭据验证")
        self.geometry("1080x760")
        self.ui_queue = queue.Queue()
        self.ble = BleWorker(self.ui_queue)
        self.serial_worker = SerialWorker(self.ui_queue)
        self.devices: list[BleDevice] = []
        self.run_id = tk.StringVar(value=f"issue31-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        self.ssid = tk.StringVar(value="Erroright")
        self.password = tk.StringVar(value="erroright")
        self.wrong_password = tk.StringVar(value="ERRORIGHT")
        self.password_visible = tk.BooleanVar(value=False)
        self.wrong_password_visible = tk.BooleanVar(value=False)
        self.manual_ble_mode = tk.BooleanVar(value=False)
        self.manual_response = tk.StringVar()
        self.current_serial_log_path: Optional[Path] = None
        self.command_counter = 1
        self.case_results = {}
        self.current_case = tk.StringVar(value="TC-01")
        self.ble_status = tk.StringVar(value="BLE: not connected")
        self.serial_status = tk.StringVar(value="Serial: stopped")
        self.hint_status = tk.StringVar(value="Ready: click one-key prepare, then start from TC-04 clear credentials.")
        self.case_status_vars = {f"TC-0{i}": tk.StringVar(value=f"TC-0{i}: -") for i in range(1, 7)}
        self.plan_stop_event = threading.Event()
        self.plan_running = False
        self.message_lock = threading.Lock()
        self.recent_messages = []
        self._build_ui()
        self.after(100, self._poll_queue)

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        config = ttk.LabelFrame(root, text="配置")
        config.pack(fill=tk.X)

        status_bar = ttk.Frame(root)
        status_bar.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(status_bar, textvariable=self.ble_status, width=28).pack(side=tk.LEFT, padx=4)
        ttk.Label(status_bar, textvariable=self.serial_status, width=34).pack(side=tk.LEFT, padx=4)
        ttk.Label(status_bar, textvariable=self.hint_status).pack(side=tk.LEFT, padx=4)

        ttk.Label(config, text="Run ID").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(config, textvariable=self.run_id, width=28).grid(row=0, column=1, sticky=tk.W, padx=4)
        ttk.Label(config, text="SSID").grid(row=0, column=2, sticky=tk.W, padx=4)
        ttk.Entry(config, textvariable=self.ssid, width=24).grid(row=0, column=3, sticky=tk.W, padx=4)
        ttk.Label(config, text="正确密码").grid(row=0, column=4, sticky=tk.W, padx=4)
        self.password_entry = ttk.Entry(config, textvariable=self.password, width=24, show="*")
        self.password_entry.grid(row=0, column=5, sticky=tk.W, padx=4)
        self.password_toggle = ttk.Button(config, text="显示", width=6, command=self.toggle_password)
        self.password_toggle.grid(row=0, column=6, sticky=tk.W, padx=4)
        ttk.Label(config, text="错误密码").grid(row=1, column=4, sticky=tk.W, padx=4)
        self.wrong_password_entry = ttk.Entry(config, textvariable=self.wrong_password, width=24, show="*")
        self.wrong_password_entry.grid(row=1, column=5, sticky=tk.W, padx=4)
        self.wrong_password_toggle = ttk.Button(config, text="显示", width=6, command=self.toggle_wrong_password)
        self.wrong_password_toggle.grid(row=1, column=6, sticky=tk.W, padx=4)

        ttk.Label(config, text="BLE 设备").grid(row=1, column=0, sticky=tk.W, padx=4)
        self.device_combo = ttk.Combobox(config, width=42, state="readonly")
        self.device_combo.grid(row=1, column=1, columnspan=3, sticky=tk.W, padx=4)
        ttk.Button(config, text="扫描 BLE", command=self.scan_ble).grid(row=1, column=7, padx=4)
        ttk.Button(config, text="连接 BLE", command=self.connect_ble).grid(row=1, column=8, padx=4)

        ttk.Label(config, text="串口").grid(row=2, column=0, sticky=tk.W, padx=4)
        self.port_combo = ttk.Combobox(config, width=16, values=SerialWorker.ports())
        self.port_combo.grid(row=2, column=1, sticky=tk.W, padx=4)
        if "COM6" in self.port_combo["values"]:
            self.port_combo.set("COM6")
        self.baud = tk.StringVar(value="115200")
        ttk.Label(config, text="波特率").grid(row=2, column=2, sticky=tk.W, padx=4)
        ttk.Entry(config, textvariable=self.baud, width=10).grid(row=2, column=3, sticky=tk.W, padx=4)
        ttk.Button(config, text="刷新串口", command=self.refresh_ports).grid(row=2, column=4, padx=4)
        ttk.Button(config, text="开始串口日志", command=self.start_serial).grid(row=2, column=5, padx=4)
        ttk.Button(config, text="停止串口日志", command=self.stop_serial).grid(row=2, column=6, padx=4)
        ttk.Checkbutton(config, text="手机 BLE 手动模式", variable=self.manual_ble_mode).grid(row=2, column=7, columnspan=2, sticky=tk.W, padx=4)

        serial_actions = ttk.Frame(config)
        serial_actions.grid(row=3, column=0, columnspan=9, sticky=tk.W, pady=(4, 0))
        ttk.Button(serial_actions, text="清空串口显示", command=self.clear_serial_display).pack(side=tk.LEFT, padx=4)
        ttk.Button(serial_actions, text="插入串口标记", command=self.add_serial_marker).pack(side=tk.LEFT, padx=4)
        ttk.Button(serial_actions, text="打开日志目录", command=self.open_log_dir).pack(side=tk.LEFT, padx=4)
        ttk.Button(serial_actions, text="一键准备自动测试", command=self.prepare_auto_test).pack(side=tk.LEFT, padx=4)
        ttk.Button(serial_actions, text="自动执行今日计划", command=self.run_today_plan).pack(side=tk.LEFT, padx=4)
        ttk.Button(serial_actions, text="停止自动计划", command=self.stop_today_plan).pack(side=tk.LEFT, padx=4)

        actions = ttk.LabelFrame(root, text="测试动作")
        actions.pack(fill=tk.X, pady=8)

        buttons = [
            ("TC-01 读取初始状态", self.tc01_get),
            ("TC-02 正确配网", self.tc02_set_valid),
            ("只排查 TC-02", self.run_tc02_diagnostic),
            ("TC-03 掉电后读取", self.tc03_power_cycle_prompt),
            ("TC-04 清除凭据", self.tc04_clear),
            ("TC-05 错误密码", self.tc05_wrong_password),
            ("TC-06 AP 不可达", self.tc06_ap_unavailable_prompt),
            ("生成记录", self.write_record),
        ]
        for idx, (text, cmd) in enumerate(buttons):
            ttk.Button(actions, text=text, command=cmd).grid(row=0, column=idx, padx=4, pady=6)

        results = ttk.LabelFrame(root, text="用例结果")
        results.pack(fill=tk.X, pady=(0, 8))
        for idx, case_id in enumerate([f"TC-0{i}" for i in range(1, 7)]):
            ttk.Label(results, textvariable=self.case_status_vars[case_id], width=16).grid(row=0, column=idx, sticky=tk.W, padx=4, pady=4)

        panes = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(panes, text="BLE / 测试日志")
        right = ttk.LabelFrame(panes, text="串口日志")
        panes.add(left, weight=1)
        panes.add(right, weight=1)

        self.ble_log = tk.Text(left, wrap=tk.WORD, height=24)
        self.ble_log.pack(fill=tk.BOTH, expand=True)
        self.serial_log = tk.Text(right, wrap=tk.WORD, height=24)
        self.serial_log.pack(fill=tk.BOTH, expand=True)
        self._configure_log_tags()

        footer = ttk.Frame(root)
        footer.pack(fill=tk.X, pady=6)
        ttk.Button(footer, text="标记当前用例 PASS", command=lambda: self.mark_current("PASS")).pack(side=tk.LEFT, padx=4)
        ttk.Button(footer, text="标记当前用例 FAIL", command=lambda: self.mark_current("FAIL")).pack(side=tk.LEFT, padx=4)
        ttk.Button(footer, text="清除 BLE 日志", command=self.clear_ble_display).pack(side=tk.LEFT, padx=4)
        ttk.Button(footer, text="清除串口日志", command=self.clear_serial_display).pack(side=tk.LEFT, padx=4)
        ttk.Button(footer, text="打开记录目录", command=self.show_paths).pack(side=tk.LEFT, padx=4)
        ttk.Label(footer, text="当前用例").pack(side=tk.LEFT, padx=(18, 4))
        ttk.Combobox(footer, textvariable=self.current_case, width=8, values=[f"TC-0{i}" for i in range(1, 7)]).pack(side=tk.LEFT)
        ttk.Label(footer, text="手机 BLE 响应").pack(side=tk.LEFT, padx=(18, 4))
        ttk.Entry(footer, textvariable=self.manual_response, width=36).pack(side=tk.LEFT, padx=4)
        ttk.Button(footer, text="记录响应", command=self.record_manual_response).pack(side=tk.LEFT, padx=4)

    def _poll_queue(self):
        while True:
            try:
                kind, message = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            widget = self.serial_log if kind == "serial" else self.ble_log
            self._append(widget, message)
            with self.message_lock:
                self.recent_messages.append((time.time(), kind, message))
                if len(self.recent_messages) > 2000:
                    self.recent_messages = self.recent_messages[-1000:]
            self._update_live_status(kind, message)
            self._auto_analyze_message(kind, message)
        self.after(100, self._poll_queue)

    def _configure_log_tags(self):
        for widget in (self.ble_log, self.serial_log):
            widget.tag_configure("ok", foreground="#0b7a28")
            widget.tag_configure("warn", foreground="#9a5b00")
            widget.tag_configure("fail", foreground="#b00020")
            widget.tag_configure("info", foreground="#005a9e")

    def _append(self, widget: tk.Text, message: str):
        tag = self._tag_for_message(message)
        if tag:
            widget.insert(tk.END, message + "\n", tag)
        else:
            widget.insert(tk.END, message + "\n")
        widget.see(tk.END)

    def _tag_for_message(self, message: str) -> Optional[str]:
        upper = message.upper()
        if any(token in upper for token in ("WIFI_CONNECTED", "\"STATUS\":\"CONNECTED\"", "GOT IP", "WIFI_CLEARED", "WIFI_UNCONFIGURED", "\"STATUS\":\"UNCONFIGURED\"", "PASS", "SYS.ACK")):
            return "ok"
        if any(token in upper for token in ("WIFI_DISCONNECTED", "\"STATUS\":\"DISCONNECTED\"", "WIFI_CONNECTING", "\"STATUS\":\"CONNECTING\"", "NO AP", "AUTH", "FAIL")):
            return "warn"
        if any(token in upper for token in ("WDT", "PANIC", "GURU MEDITATION", "ASSERT", "ERROR", "EXCEPTION")):
            return "fail"
        if any(token in upper for token in ("TX ", "RX ", "MARK", "FOUND", "CONNECTED BLE", "已连接 BLE")):
            return "info"
        return None

    def _update_live_status(self, kind: str, message: str):
        if kind == "ble":
            if "已连接 BLE" in message or "CONNECTED BLE" in message:
                self.ble_status.set("BLE: connected")
            elif message.startswith("ERROR"):
                self.ble_status.set("BLE: error")
            elif "TX " in message:
                self.ble_status.set("BLE: command sent")
            elif "RX " in message:
                self.ble_status.set("BLE: response received")
        elif kind == "serial":
            if "串口日志已开始" in message:
                self.serial_status.set(f"Serial: logging {self.port_combo.get().strip()}")
            elif "串口日志已停止" in message:
                self.serial_status.set("Serial: stopped")

    def _auto_analyze_message(self, kind: str, message: str):
        upper = message.upper()
        case_id = self.current_case.get()
        if any(token in upper for token in ("WDT", "PANIC", "GURU MEDITATION", "ASSERT")):
            self.hint_status.set("Risk: reboot/WDT/panic detected. Mark current case FAIL unless environment explains it.")
            self._suggest_case_result(case_id, "FAIL", "crash/reset risk")
            return
        if "WIFI_UNCONFIGURED" in upper or "\"STATUS\":\"UNCONFIGURED\"" in upper:
            self.hint_status.set("Good: Wi-Fi is unconfigured. Clear-credential or initial-state check likely passed.")
            if case_id in ("TC-01", "TC-04"):
                self._suggest_case_result(case_id, "PASS", "unconfigured")
        elif "WIFI_CLEARED" in upper or "STORED WIFI CREDENTIALS CLEARED" in upper:
            self.hint_status.set("Good: credentials cleared. Reboot and run TC-01 next.")
            self._suggest_case_result("TC-04", "PASS", "cleared")
        elif "WIFI_CONNECTED" in upper or "\"STATUS\":\"CONNECTED\"" in upper or "GOT IP" in upper:
            self.hint_status.set("Good: Wi-Fi connected. Correct provisioning or recovery likely passed.")
            if case_id in ("TC-02", "TC-03", "TC-06"):
                self._suggest_case_result(case_id, "PASS", "connected")
        elif "WIFI_DISCONNECTED:ERRORIGHT" in upper or "WIFI_DISCONNECTED:ER" in upper or ("\"STATUS\":\"DISCONNECTED\"" in upper and "\"SSID\":\"ERRORIGHT\"" in upper):
            if case_id in ("TC-01", "TC-04"):
                self.hint_status.set("Warning: Erroright credential still appears after clear. Verify TC-04 before continuing.")
                self._suggest_case_result(case_id, "FAIL", "old credential remains")
            else:
                self.hint_status.set("Info: Wi-Fi disconnected with Erroright credential present.")
        elif "AUTH" in upper or "WRONG" in upper or "NO_AP" in upper or "NO AP" in upper:
            self.hint_status.set("Info: abnormal credential/AP condition observed. Confirm no WDT and BLE remains usable.")

    def _suggest_case_result(self, case_id: str, result: str, reason: str):
        if case_id not in self.case_status_vars:
            return
        if self.case_results.get(case_id) == result:
            return
        if case_id not in self.case_results:
            self.case_status_vars[case_id].set(f"{case_id}: suggest {result}")
            self._append(self.ble_log, f"AUTO {case_id} suggest {result}: {reason}")

    def record_manual_response(self):
        text = self.manual_response.get().strip()
        if not text:
            return
        self._append(self.ble_log, f"PHONE RX {text}")
        self.manual_response.set("")

    def toggle_password(self):
        visible = not self.password_visible.get()
        self.password_visible.set(visible)
        self.password_entry.configure(show="" if visible else "*")
        self.password_toggle.configure(text="隐藏" if visible else "显示")

    def toggle_wrong_password(self):
        visible = not self.wrong_password_visible.get()
        self.wrong_password_visible.set(visible)
        self.wrong_password_entry.configure(show="" if visible else "*")
        self.wrong_password_toggle.configure(text="隐藏" if visible else "显示")

    def _run_ble(self, coro, done=None):
        future = self.ble.submit(coro)

        def waiter():
            try:
                result = future.result()
                if done:
                    self.after(0, lambda: done(result))
            except Exception as exc:
                self.ui_queue.put(("ble", f"ERROR {exc}"))
                self.after(0, lambda: messagebox.showerror("BLE 错误", str(exc)))

        threading.Thread(target=waiter, daemon=True).start()

    def scan_ble(self):
        if self.manual_ble_mode.get():
            self._append(self.ble_log, "手机 BLE 手动模式已启用：请在手机 BLE 工具中扫描并连接设备。")
            return
        self._append(self.ble_log, "开始扫描 BLE，约 5 秒...")

        def done(devices):
            self.devices = devices
            values = [f"{d.name} | {d.address}" for d in devices]
            self.device_combo["values"] = values
            if values:
                self.device_combo.current(0)
            self._append(self.ble_log, f"扫描完成，共 {len(values)} 个设备")

        self._run_ble(self.ble.scan(), done)

    def connect_ble(self):
        if self.manual_ble_mode.get():
            self._append(self.ble_log, "手机 BLE 手动模式已启用：电脑不连接 BLE，使用手机连接设备。")
            return
        idx = self.device_combo.current()
        if idx < 0 or idx >= len(self.devices):
            messagebox.showwarning("未选择设备", "请先扫描并选择 BLE 设备")
            return
        self._run_ble(self.ble.connect(self.devices[idx]))

    def prepare_auto_test(self):
        self.manual_ble_mode.set(False)
        self.ble_status.set("BLE: scanning")
        self.hint_status.set("Preparing: serial logging starts, then ESP_ROBOT BLE scan/connect.")
        if not self.port_combo.get().strip():
            self.refresh_ports()
        if self.port_combo.get().strip():
            self.start_serial()
        self._append(self.ble_log, "一键准备：开始扫描 ESP_ROBOT，约 5 秒...")

        def done(devices):
            self.devices = devices
            values = [f"{d.name} | {d.address}" for d in devices]
            self.device_combo["values"] = values
            target_index = -1
            for i, device in enumerate(devices):
                if device.name == "ESP_ROBOT" or device.address.upper() == "80:B5:4E:EF:B1:2A":
                    target_index = i
                    break
            if target_index < 0:
                self._append(self.ble_log, "未找到 ESP_ROBOT，请确认设备上电并处于可连接状态。")
                self.ble_status.set("BLE: ESP_ROBOT not found")
                self.hint_status.set("Blocked: ESP_ROBOT not found. Check power, reset BLE, then retry one-key prepare.")
                return
            self.device_combo.current(target_index)
            self._append(self.ble_log, f"找到目标设备：{values[target_index]}")
            self.ble_status.set("BLE: connecting")
            self._run_ble(self.ble.connect(devices[target_index]))

        self._run_ble(self.ble.scan(), done)

    def stop_today_plan(self):
        self.plan_stop_event.set()
        self.hint_status.set("Auto plan stop requested. Current BLE operation may finish first.")
        self._append(self.ble_log, "AUTO stop requested")

    def run_tc02_diagnostic(self):
        if self.plan_running:
            messagebox.showinfo("TC-02 排查", "自动计划正在执行中，请先停止。")
            return
        self.plan_stop_event.clear()
        self.plan_running = True
        self.manual_ble_mode.set(False)
        self.hint_status.set("TC-02 diagnostic running: verify AP/password, then wait for connected or timeout.")
        threading.Thread(target=self._tc02_diagnostic_worker, daemon=True).start()

    def _tc02_diagnostic_worker(self):
        try:
            self._auto_log("TC-02 DIAG START: valid Wi-Fi provisioning only.")
            self._ensure_serial_for_plan()
            self._connect_target_for_plan()
            self._auto_case("TC-02", "diagnostic baseline read before valid provisioning")
            start = self._message_cursor()
            self._send_payload_for_plan({"type": "cfg.wifi.get", "data": {"command_id": self._command_id("wifi-get-before-tc02")}})
            self._wait_for_patterns((
                "WIFI_UNCONFIGURED",
                "\"status\":\"unconfigured\"",
                "WIFI_DISCONNECTED",
                "\"status\":\"disconnected\"",
                "WIFI_CONNECTED",
                "\"status\":\"connected\"",
            ), 12, "TC-02", "BLOCKED", start)

            self._auto_log("TC-02 DIAG: sending Erroright valid credentials.")
            start = self._message_cursor()
            self._send_payload_for_plan({
                "type": "cfg.wifi.set",
                "data": {
                    "ssid": self.ssid.get(),
                    "password": self.password.get(),
                    "command_id": self._command_id("wifi-set-diag"),
                },
            })
            connected = self._wait_for_patterns(("WIFI_CONNECTED", "\"status\":\"connected\"", "GOT IP"), 75, "TC-02", "PASS", start, fail_patterns=("WDT", "PANIC", "GURU MEDITATION"))

            start = self._message_cursor()
            self._send_payload_for_plan({"type": "cfg.wifi.get", "data": {"command_id": self._command_id("wifi-get-after-tc02")}})
            if connected:
                self._wait_for_patterns(("WIFI_CONNECTED", "\"status\":\"connected\"", "GOT IP"), 12, "TC-02", "PASS", start)
            else:
                self._wait_for_patterns(("WIFI_DISCONNECTED", "\"status\":\"disconnected\"", "WIFI_CONNECTING", "\"status\":\"connecting\"", "WIFI_UNCONFIGURED", "\"status\":\"unconfigured\""), 12, "TC-02", "BLOCKED", start)

            self._auto_log("TC-02 DIAG DONE: review BLE and serial logs for disconnect reason/auth/no AP.")
            self.after(0, self.write_record)
        except Exception as exc:
            self._auto_log(f"TC-02 DIAG ERROR: {exc}")
            self.after(0, lambda: self.hint_status.set(f"TC-02 diagnostic blocked/error: {exc}"))
        finally:
            self.plan_running = False

    def run_today_plan(self):
        if self.plan_running:
            messagebox.showinfo("自动计划", "自动计划正在执行中。")
            return
        self.plan_stop_event.clear()
        self.plan_running = True
        self.manual_ble_mode.set(False)
        self.hint_status.set("Auto plan running. Physical reboot/AP steps still need manual action during countdown.")
        threading.Thread(target=self._today_plan_worker, daemon=True).start()

    def _today_plan_worker(self):
        try:
            self._auto_log("AUTO PLAN START: Issue #31 full plan, not smoke test.")
            self._ensure_serial_for_plan()
            self._connect_target_for_plan()

            self._auto_case("TC-04", "clear credentials before testing")
            start = self._message_cursor()
            self._send_payload_for_plan({"type": "cfg.wifi.clear", "data": {"command_id": self._command_id("wifi-clear")}})
            self._wait_for_patterns(("WIFI_CLEARED", "WIFI_UNCONFIGURED", "\"status\":\"unconfigured\"", "STORED WIFI CREDENTIALS CLEARED"), 12, "TC-04", "PASS", start)
            start = self._message_cursor()
            self._send_payload_for_plan({"type": "cfg.wifi.get", "data": {"command_id": self._command_id("wifi-get")}})
            self._wait_for_patterns(("WIFI_UNCONFIGURED", "\"status\":\"unconfigured\"", "WIFI_DISCONNECTED", "\"status\":\"disconnected\""), 10, "TC-04", "PASS", start)

            self._manual_confirm("请现在手动断电重启设备；设备启动完成后点“继续”。")
            self._connect_target_for_plan()

            self._auto_case("TC-01", "read initial Wi-Fi state after clear")
            start = self._message_cursor()
            self._send_payload_for_plan({"type": "cfg.wifi.get", "data": {"command_id": self._command_id("wifi-get")}})
            self._wait_for_patterns(("WIFI_UNCONFIGURED", "\"status\":\"unconfigured\""), 12, "TC-01", "PASS", start, fail_patterns=("WIFI_CONNECTED", "\"status\":\"connected\"", "WIFI_DISCONNECTED:ERRORIGHT", "WIFI_DISCONNECTED:ER", "\"status\":\"disconnected\",\"ssid\":\"Erroright\""))

            self._auto_case("TC-02", "provision valid Wi-Fi credentials")
            start = self._message_cursor()
            self._send_payload_for_plan({
                "type": "cfg.wifi.set",
                "data": {
                    "ssid": self.ssid.get(),
                    "password": self.password.get(),
                    "command_id": self._command_id("wifi-set"),
                },
            })
            self._wait_for_patterns(("WIFI_CONNECTED", "\"status\":\"connected\"", "GOT IP"), 60, "TC-02", "PASS", start, fail_patterns=("WDT", "PANIC", "GURU MEDITATION"))
            self._send_payload_for_plan({"type": "cfg.wifi.get", "data": {"command_id": self._command_id("wifi-get")}})

            self._manual_confirm("请现在手动断电重启设备，验证掉电保存；设备启动完成后点“继续”。")
            self._connect_target_for_plan()

            self._auto_case("TC-03", "read Wi-Fi state after power cycle")
            start = self._message_cursor()
            self._send_payload_for_plan({"type": "cfg.wifi.get", "data": {"command_id": self._command_id("wifi-get-after-reboot")}})
            self._wait_for_patterns(("WIFI_CONNECTED", "\"status\":\"connected\"", "GOT IP"), 25, "TC-03", "PASS", start, fail_patterns=("WIFI_UNCONFIGURED", "\"status\":\"unconfigured\"", "WDT", "PANIC"))

            self._auto_case("TC-04", "clear credentials and verify old credential is not reused")
            start = self._message_cursor()
            self._send_payload_for_plan({"type": "cfg.wifi.clear", "data": {"command_id": self._command_id("wifi-clear")}})
            self._wait_for_patterns(("WIFI_CLEARED", "WIFI_UNCONFIGURED", "\"status\":\"unconfigured\"", "STORED WIFI CREDENTIALS CLEARED"), 12, "TC-04", "PASS", start)
            self._manual_confirm("请现在再次手动断电重启设备，验证旧凭据不再自动连接；设备启动完成后点“继续”。")
            self._connect_target_for_plan()
            start = self._message_cursor()
            self._send_payload_for_plan({"type": "cfg.wifi.get", "data": {"command_id": self._command_id("wifi-get-after-clear")}})
            self._wait_for_patterns(("WIFI_UNCONFIGURED", "\"status\":\"unconfigured\""), 15, "TC-04", "PASS", start, fail_patterns=("WIFI_CONNECTED", "\"status\":\"connected\"", "WIFI_DISCONNECTED:ERRORIGHT", "WIFI_DISCONNECTED:ER", "\"status\":\"disconnected\",\"ssid\":\"Erroright\""))

            self._auto_case("TC-05", "send wrong password and confirm recoverable failure")
            start = self._message_cursor()
            self._send_payload_for_plan({
                "type": "cfg.wifi.set",
                "data": {
                    "ssid": self.ssid.get(),
                    "password": self.wrong_password.get(),
                    "command_id": self._command_id("wifi-wrong"),
                },
            })
            self._wait_for_patterns(("WIFI_DISCONNECTED", "\"status\":\"disconnected\"", "AUTH", "FAIL", "NO AP", "WIFI_CONNECTING", "\"status\":\"connecting\""), 35, "TC-05", "PASS", start, fail_patterns=("WIFI_CONNECTED", "\"status\":\"connected\"", "WDT", "PANIC"))
            self._send_payload_for_plan({"type": "cfg.wifi.get", "data": {"command_id": self._command_id("wifi-get-after-wrong")}})

            self._auto_case("TC-06", "AP unavailable and restore")
            start = self._message_cursor()
            self._send_payload_for_plan({
                "type": "cfg.wifi.set",
                "data": {
                    "ssid": self.ssid.get(),
                    "password": self.password.get(),
                    "command_id": self._command_id("wifi-set-ap-test"),
                },
            })
            self._wait_for_patterns(("WIFI_CONNECTED", "\"status\":\"connected\"", "GOT IP"), 25, "TC-06", "PASS", start)
            self._manual_confirm("请现在关闭 Erroright AP；观察到设备进入断连/重试后点“继续”。")
            start = self._message_cursor()
            self._send_payload_for_plan({"type": "cfg.wifi.get", "data": {"command_id": self._command_id("wifi-get-ap-off")}})
            self._wait_for_patterns(("WIFI_DISCONNECTED", "\"status\":\"disconnected\"", "WIFI_CONNECTING", "\"status\":\"connecting\""), 25, "TC-06", "PASS", start, fail_patterns=("WIFI_CONNECTED", "\"status\":\"connected\"", "WDT", "PANIC"))
            self._manual_confirm("请现在重新打开 Erroright AP；AP 恢复并等待设备重连后点“继续”。")
            start = self._message_cursor()
            self._send_payload_for_plan({"type": "cfg.wifi.get", "data": {"command_id": self._command_id("wifi-get-ap-restore")}})
            self._wait_for_patterns(("WIFI_CONNECTED", "\"status\":\"connected\"", "GOT IP"), 40, "TC-06", "PASS", start, fail_patterns=("WDT", "PANIC"))

            self._auto_log("AUTO PLAN DONE: please review suggested PASS/FAIL, then generate/fill final conclusion.")
            self.after(0, self.write_record)
        except Exception as exc:
            self._auto_log(f"AUTO PLAN ERROR: {exc}")
            self.after(0, lambda: self.hint_status.set(f"Auto plan blocked/error: {exc}"))
        finally:
            self.plan_running = False

    def _ensure_not_stopped(self):
        if self.plan_stop_event.is_set():
            raise RuntimeError("auto plan stopped by user")

    def _auto_log(self, message: str):
        self.ui_queue.put(("ble", message))

    def _auto_case(self, case_id: str, note: str):
        self._ensure_not_stopped()
        self.after(0, lambda: self.current_case.set(case_id))
        self._auto_log(f"AUTO {case_id}: {note}")
        self.ui_queue.put(("serial", f"===== AUTO {case_id} {datetime.now().isoformat(timespec='seconds')} {note} ====="))

    def _ensure_serial_for_plan(self):
        port = self.port_combo.get().strip() or "COM6"
        baud = int(self.baud.get() or "115200")
        self.after(0, lambda: self.port_combo.set(port))
        if self.serial_worker.handle is None:
            log_path = LOG_DIR / f"{self.run_id.get()}-serial.log"
            if self.serial_worker.handle is not None:
                self.serial_worker.stop()
            self.serial_worker.start(port, baud, log_path)
            self.current_serial_log_path = log_path
            self.after(0, lambda: self.serial_status.set(f"Serial: logging {port}"))

    def _connect_target_for_plan(self):
        self._ensure_not_stopped()
        self.after(0, lambda: self.ble_status.set("BLE: scanning"))
        devices = self.ble.submit(self.ble.scan()).result(timeout=18)
        target = None
        for device in devices:
            if device.name == "ESP_ROBOT" or device.address.upper() == "80:B5:4E:EF:B1:2A":
                target = device
                break
        if target is None:
            raise RuntimeError("ESP_ROBOT not found")
        self._auto_log(f"AUTO found target: {target.name} {target.address}")
        self.after(0, lambda: self.ble_status.set("BLE: connecting"))
        self.ble.submit(self.ble.connect(target)).result(timeout=25)

    def _send_payload_for_plan(self, payload: dict, wait_seconds: int = 0):
        self._ensure_not_stopped()
        self.ble.submit(self.ble.write_json(payload)).result(timeout=20)
        for _ in range(wait_seconds):
            self._ensure_not_stopped()
            time.sleep(1)

    def _message_cursor(self) -> int:
        with self.message_lock:
            return len(self.recent_messages)

    def _wait_for_patterns(self, pass_patterns, timeout_seconds: int, case_id: str, pass_result: str, start_index: int, fail_patterns=()):
        pass_upper = tuple(pattern.upper() for pattern in pass_patterns)
        fail_upper = tuple(pattern.upper() for pattern in fail_patterns)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            self._ensure_not_stopped()
            with self.message_lock:
                window = self.recent_messages[start_index:]
            text = "\n".join(item[2] for item in window).upper()
            if any(pattern in text for pattern in fail_upper):
                self._set_case_result(case_id, "FAIL", f"matched fail pattern: {fail_patterns}")
                return False
            if any(pattern in text for pattern in pass_upper):
                self._set_case_result(case_id, pass_result, f"matched pass pattern: {pass_patterns}")
                return True
            time.sleep(0.5)
        self._set_case_result(case_id, "BLOCKED", f"timeout waiting for {pass_patterns}")
        return False

    def _set_case_result(self, case_id: str, result: str, note: str):
        self.case_results[case_id] = result
        self.after(0, lambda: self.case_status_vars[case_id].set(f"{case_id}: {result}") if case_id in self.case_status_vars else None)
        self._auto_log(f"AUTO {case_id} {result}: {note}")

    def _manual_confirm(self, message: str):
        self._ensure_not_stopped()
        self._auto_log(f"AUTO MANUAL ACTION: {message}")
        self.after(0, lambda: self.hint_status.set(message))
        done = threading.Event()
        result = {"ok": False}

        def ask():
            result["ok"] = messagebox.askokcancel("手动步骤确认", message)
            done.set()

        self.after(0, ask)
        while not done.wait(0.5):
            self._ensure_not_stopped()
        if not result["ok"]:
            raise RuntimeError("manual step cancelled")

    def refresh_ports(self):
        ports = SerialWorker.ports()
        self.port_combo["values"] = ports
        if "COM6" in ports:
            self.port_combo.set("COM6")
        elif ports and not self.port_combo.get():
            self.port_combo.set(ports[0])

    def start_serial(self):
        port = self.port_combo.get().strip()
        if not port:
            messagebox.showwarning("未选择串口", "请选择串口")
            return
        log_path = LOG_DIR / f"{self.run_id.get()}-serial.log"
        try:
            if self.serial_worker.handle is not None:
                self.serial_worker.stop()
            self.serial_worker.start(port, int(self.baud.get()), log_path)
            self.current_serial_log_path = log_path
            self.serial_status.set(f"Serial: logging {port}")
        except Exception as exc:
            self.serial_status.set("Serial: error")
            messagebox.showerror("串口错误", str(exc))

    def stop_serial(self):
        self.serial_worker.stop()
        self.serial_status.set("Serial: stopped")
        self._append(self.serial_log, "串口日志已停止")

    def clear_serial_display(self):
        self.serial_log.delete("1.0", tk.END)

    def clear_ble_display(self):
        self.ble_log.delete("1.0", tk.END)

    def add_serial_marker(self):
        marker = f"===== MARK {datetime.now().isoformat(timespec='seconds')} {self.current_case.get()} ====="
        self._append(self.serial_log, marker)
        if self.serial_worker.log_file:
            self.serial_worker.log_file.write(marker + "\n")
            self.serial_worker.log_file.flush()

    def open_log_dir(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            import os
            os.startfile(LOG_DIR)
        except Exception as exc:
            messagebox.showerror("打开日志目录失败", str(exc))

    def _command_id(self, prefix: str) -> str:
        value = f"{prefix}-{self.command_counter:03d}"
        self.command_counter += 1
        return value

    def _write_payload(self, payload: dict):
        if self.manual_ble_mode.get():
            text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            try:
                self.clipboard_clear()
                self.clipboard_append(text)
            except Exception:
                pass
            self._append(self.ble_log, f"PHONE TX {text}")
            self._append(self.ble_log, "已复制到剪贴板；请在手机 BLE 工具写入 0xFF01 特征。收到响应后填入底部“手机 BLE 响应”并点“记录响应”。")
            return
        self._run_ble(self.ble.write_json(payload))

    def tc01_get(self):
        self.current_case.set("TC-01")
        self.hint_status.set("TC-01: expect WIFI_UNCONFIGURED after clear, or connected only after provisioning/recovery.")
        self._write_payload({"type": "cfg.wifi.get", "data": {"command_id": self._command_id("wifi-get")}})

    def tc02_set_valid(self):
        self.current_case.set("TC-02")
        self.hint_status.set("TC-02: expect WIFI_CONNECTING then WIFI_CONNECTED/Got IP with Erroright.")
        if not self.ssid.get() or not self.password.get():
            messagebox.showwarning("缺少 Wi-Fi 信息", "请填写 SSID 和正确密码")
            return
        self._write_payload({
            "type": "cfg.wifi.set",
            "data": {
                "ssid": self.ssid.get(),
                "password": self.password.get(),
                "command_id": self._command_id("wifi-set"),
            },
        })

    def tc03_power_cycle_prompt(self):
        self.current_case.set("TC-03")
        self.hint_status.set("TC-03: power-cycle device, one-key prepare again, then read status.")
        messagebox.showinfo("手动步骤", "请断电重启设备。重启后重新连接 BLE，然后点击 TC-01 或本按钮后再读取状态。")
        self.tc01_get()

    def tc04_clear(self):
        self.current_case.set("TC-04")
        self.hint_status.set("TC-04: expect WIFI_CLEARED/WIFI_UNCONFIGURED, then reboot and verify with TC-01.")
        self._write_payload({"type": "cfg.wifi.clear", "data": {"command_id": self._command_id("wifi-clear")}})

    def tc05_wrong_password(self):
        self.current_case.set("TC-05")
        self.hint_status.set("TC-05: expect failure/disconnected, no WDT/panic, BLE still usable.")
        if not self.ssid.get() or not self.wrong_password.get():
            messagebox.showwarning("缺少 Wi-Fi 信息", "请填写 SSID 和错误密码")
            return
        self._write_payload({
            "type": "cfg.wifi.set",
            "data": {
                "ssid": self.ssid.get(),
                "password": self.wrong_password.get(),
                "command_id": self._command_id("wifi-wrong"),
            },
        })

    def tc06_ap_unavailable_prompt(self):
        self.current_case.set("TC-06")
        self.hint_status.set("TC-06: turn AP off, expect disconnected/connecting; restore AP and expect connected.")
        messagebox.showinfo("手动步骤", "请关闭 AP 或手机热点，等待日志出现断连/重试；之后恢复 AP，再观察是否自动恢复 connected。")
        self.tc01_get()

    def mark_current(self, result: str):
        case_id = self.current_case.get()
        self.case_results[case_id] = result
        if case_id in self.case_status_vars:
            self.case_status_vars[case_id].set(f"{case_id}: {result}")
        self.hint_status.set(f"{case_id} marked {result}. Continue with the next planned step.")
        self._append(self.ble_log, f"{case_id} 标记为 {result}")

    def write_record(self):
        RECORD_DIR.mkdir(parents=True, exist_ok=True)
        run_id = self.run_id.get().strip() or f"issue31-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        path = RECORD_DIR / f"{run_id}.md"
        ble_text = self._redact_sensitive(self.ble_log.get("1.0", tk.END).strip())
        serial_text = self._redact_sensitive(self.serial_log.get("1.0", tk.END).strip())
        conclusion = self._final_conclusion()
        network_precondition = "干净" if self.case_results.get("TC-04") == "PASS" else "不干净/需复核"
        rows = []
        for i in range(1, 7):
            case = f"TC-0{i}"
            rows.append(f"| {case} | {self.case_results.get(case, '')} | | | | |")
        content = f"""# BLE 配网持久化与异常凭据验证执行记录

## 基本信息

| 字段 | 内容 |
|---|---|
| 测试记录编号 | {run_id} |
| 测试日期 | {datetime.now().isoformat(timespec='seconds')} |
| BLE 设备 | {self.ble.device.name + ' ' + self.ble.device.address if self.ble.device else ''} |
| SSID | {self.ssid.get()} |
| 正确密码 | ****** |
| 错误密码 | ****** |
| 串口日志 | logs/{run_id}-serial.log |
| 自动结论 | {conclusion} |
| #30/#32 网络前置状态 | {network_precondition} |

## 最终结论

执行结论：{conclusion}

对 #30/#32 的影响：网络前置状态 {network_precondition}。如果 TC-04 不是 PASS，后续 #30/#32 必须注明网络前置状态不干净。

## 用例结果

| 编号 | 结果 | BLE 请求 | BLE 响应 / Notify | 串口证据 | 备注 |
|---|---|---|---|---|---|
{chr(10).join(rows)}

## BLE / 测试日志

```text
{ble_text}
```

## 串口日志摘录

```text
{serial_text[-12000:]}
```
"""
        path.write_text(content, encoding="utf-8")
        messagebox.showinfo("记录已生成", str(path))

    def _redact_sensitive(self, text: str) -> str:
        for secret in (self.password.get(), self.wrong_password.get()):
            if secret:
                text = text.replace(secret, "******")
        return text

    def _final_conclusion(self) -> str:
        expected = [f"TC-0{i}" for i in range(1, 7)]
        results = [self.case_results.get(case) for case in expected]
        if all(result == "PASS" for result in results):
            return "通过"
        if any(result == "FAIL" for result in results):
            return "失败"
        if any(result == "BLOCKED" for result in results):
            return "阻塞"
        return "未完成"

    def show_paths(self):
        messagebox.showinfo("目录", f"记录目录:\n{RECORD_DIR}\n\n日志目录:\n{LOG_DIR}")

    def destroy(self):
        try:
            self.serial_worker.stop()
            self.ble.submit(self.ble.disconnect()).result(timeout=2)
        except Exception:
            pass
        super().destroy()


if __name__ == "__main__":
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    app = TesterApp()
    app.mainloop()
