import sys
import time
import csv
import re
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import customtkinter as ctk
import serial.tools.list_ports

# ── Dependency Checks ────────────────────────────────────────────────────────
try:
    from nexgraphpy.nexgraph import NexGraph
except ImportError:
    print("[ERROR] nexgraphpy not found. Install with: pip install nexgraphpy")
    sys.exit(1)

try:
    from goprocam import GoProCamera, constants as gp_constants
except ImportError:
    print("[ERROR] goprocam not found. Install with: pip install goprocam")
    sys.exit(1)

try:
    import pigpio
except ImportError:
    print("[ERROR] pigpio not found. Run: pip install pigpio")
    sys.exit(1)

# Set global modern UI styling
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

def _parse_number(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"[-+]?\d+\.?\d*", text)
    return float(m.group()) if m else None


class UnifiedControllerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        # ── Backend Parameters ───────────────────────────────────────────────
        # Force Gauge
        self.ng = NexGraph()
        self.fg_connected = False
        self.fg_recording = False
        self._sync_record_thread = None
        self._sync_stop_event = threading.Event()
        self.sample_interval = 0.05
        self.output_file = ""
        self._force_mode = True  # True = Tension
        self._baud_rate = "high"

        # GoPro Camera
        self.gopro = None
        self.gp_connected = False
        self.gp_recording = False

        # AMT102 Encoder Configuration
        self.GPIO_A = 17       # Pin connected to level-shifted Channel A of AMT102
        self.PPR = 200         # Set to match your encoder DIP switch settings
        self.pi = None
        self.encoder_connected = False
        self.pulse_count = 0
        self.cb_encoder = None

        # ── Window Setup ─────────────────────────────────────────────────────
        self.title("Unified Force, Encoder & GoPro Sync Station")
        self.geometry("1050x750")

        # Layout allocation
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Main Tabbed view partitioning the apps
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.tab_sync = self.tab_view.add("Master Sync Dashboard")
        self.tab_gauge = self.tab_view.add("Force Gauge Config")
        self.tab_encoder = self.tab_view.add("Encoder Config")
        self.tab_gopro = self.tab_view.add("GoPro Camera Settings")

        self._build_sync_tab()
        self._build_gauge_tab()
        self._build_encoder_tab()
        self._build_gopro_tab()

        # Initialize configurations
        self.refresh_ports()
        self.connect_pi_gpio()
        self.update_ui_states()

    def log(self, message: str):
        """Thread-safe routing to push internal event alerts to the master console."""
        self.txt_console.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.txt_console.see(tk.END)

    def run_async(self, target_func, *args):
        """Utility wrapper to safely run network/serial calls off the UI main thread."""
        thread = threading.Thread(target=target_func, args=args, daemon=True)
        thread.start()

    # ─────────────────────────────────────────────────────────────────────────────
    # TAB 1: MASTER SYNC DASHBOARD BUILDER
    # ─────────────────────────────────────────────────────────────────────────────
    def _build_sync_tab(self):
        self.tab_sync.grid_columnconfigure(0, weight=1)
        self.tab_sync.grid_rowconfigure(2, weight=1)

        # Status Ribbon Panel
        status_frame = ctk.CTkFrame(self.tab_sync)
        status_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=10)
        status_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.lbl_sync_fg_status = ctk.CTkLabel(status_frame, text="Force Gauge: Disconnected", fg_color="#e74c3c", corner_radius=6, height=35)
        self.lbl_sync_fg_status.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.lbl_sync_enc_status = ctk.CTkLabel(status_frame, text="Encoder (pigpio): Disconnected", fg_color="#e74c3c", corner_radius=6, height=35)
        self.lbl_sync_enc_status.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        self.lbl_sync_gp_status = ctk.CTkLabel(status_frame, text="GoPro: Disconnected", fg_color="#e74c3c", corner_radius=6, height=35)
        self.lbl_sync_gp_status.grid(row=0, column=2, padx=10, pady=10, sticky="ew")

        # Synchronized Master Actions Trigger Deck
        sync_ctrl_frame = ctk.CTkFrame(self.tab_sync)
        sync_ctrl_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=10)

        sync_title = ctk.CTkLabel(sync_ctrl_frame, text="Synchronized System Actions (Force + Encoder + Video)", font=ctk.CTkFont(weight="bold"))
        sync_title.pack(anchor="w", padx=20, pady=(10, 0))

        self.btn_sync_record = ctk.CTkButton(sync_ctrl_frame, text="🚀 Sync Start Recording (All Streams)", 
                                             fg_color="#9b59b6", hover_color="#8e44ad", height=45,
                                             command=self.toggle_synchronized_recording)
        self.btn_sync_record.pack(fill="x", padx=20, pady=15)

        # Interactive Terminal System Console View
        lbl_console = ctk.CTkLabel(self.tab_sync, text="System Master Event Logger", font=ctk.CTkFont(weight="bold"))
        lbl_console.grid(row=2, column=0, sticky="w", padx=15, pady=(10, 0))

        self.txt_console = ctk.CTkTextbox(self.tab_sync, font=ctk.CTkFont(family="Courier", size=12))
        self.txt_console.grid(row=3, column=0, sticky="nsew", padx=15, pady=(5, 15))

    # ─────────────────────────────────────────────────────────────────────────────
    # TAB 2: FORCE GAUGE INTERFACE BUILDER
    # ─────────────────────────────────────────────────────────────────────────────
    def _build_gauge_tab(self):
        self.tab_gauge.grid_columnconfigure(1, weight=1)
        self.tab_gauge.grid_rowconfigure(0, weight=1)

        fg_sidebar = ctk.CTkFrame(self.tab_gauge, width=280)
        fg_sidebar.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(fg_sidebar, text="DEVICE LINK", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5), padx=10, anchor="w")
        
        port_frame = ctk.CTkFrame(fg_sidebar, fg_color="transparent")
        port_frame.pack(fill="x", padx=10, pady=5)
        self.port_combo = ctk.CTkComboBox(port_frame, values=["Auto-Detect"])
        self.port_combo.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(port_frame, text="🔄", width=35, command=self.refresh_ports).pack(side="right")

        self.mode_switch = ctk.CTkSegmentedButton(fg_sidebar, values=["Tension", "Compression"])
        self.mode_switch.set("Tension")
        self.mode_switch.pack(fill="x", padx=10, pady=10)

        self.baud_switch = ctk.CTkSegmentedButton(fg_sidebar, values=["High", "Low"])
        self.baud_switch.set("High")
        self.baud_switch.pack(fill="x", padx=10, pady=5)

        self.btn_fg_connect = ctk.CTkButton(fg_sidebar, text="Connect Gauge", fg_color="#2ecc71", command=self.toggle_gauge_connection)
        self.btn_fg_connect.pack(fill="x", padx=10, pady=15)

        ctk.CTkFrame(fg_sidebar, height=2, fg_color="gray").pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(fg_sidebar, text="HARDWARE MANUAL TWEAKS", font=ctk.CTkFont(weight="bold")).pack(padx=10, anchor="w")

        grid_f = ctk.CTkFrame(fg_sidebar, fg_color="transparent")
        grid_f.pack(fill="x", padx=10, pady=5)
        grid_f.columnconfigure((0, 1), weight=1)
        
        self.btn_zero = ctk.CTkButton(grid_f, text="Zero / Tare", command=self.send_zero)
        self.btn_zero.grid(row=0, column=0, padx=2, pady=4, sticky="ew")
        self.btn_unit = ctk.CTkButton(grid_f, text="Cycle Unit", command=self.change_unit)
        self.btn_unit.grid(row=0, column=1, padx=2, pady=4, sticky="ew")
        self.btn_track = ctk.CTkButton(grid_f, text="Track/Peak", command=self.toggle_track_peak)
        self.btn_track.grid(row=1, column=0, padx=2, pady=4, sticky="ew")
        self.btn_reset = ctk.CTkButton(grid_f, text="Reset Board", fg_color="#e74c3c", command=self.send_reset)
        self.btn_reset.grid(row=1, column=1, padx=2, pady=4, sticky="ew")

        # Display Data Card
        fg_main = ctk.CTkFrame(self.tab_gauge)
        fg_main.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        fg_main.columnconfigure(0, weight=1)

        self.telemetry_card = ctk.CTkFrame(fg_main, fg_color=("#dbdbdb", "#2b2b2b"))
        self.telemetry_card.grid(row=0, column=0, sticky="ew", padx=15, pady=15)
        self.lbl_live_val = ctk.CTkLabel(self.telemetry_card, text="---", font=ctk.CTkFont(size=44, weight="bold"))
        self.lbl_live_val.pack(pady=10)
        self.lbl_live_status = ctk.CTkLabel(self.telemetry_card, text="Device Not Polling")
        self.lbl_live_status.pack(pady=(0, 10))

        rec_frame = ctk.CTkFrame(fg_main)
        rec_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=5)
        ctk.CTkLabel(rec_frame, text="Sample Interval (s):").pack(side="left", padx=(10, 2))
        self.entry_interval = ctk.CTkEntry(rec_frame, width=60)
        self.entry_interval.insert(0, str(self.sample_interval))
        self.entry_interval.pack(side="left", padx=5, pady=10)

        self.btn_fg_record = ctk.CTkButton(rec_frame, text="🔴 Start Isolated Log", fg_color="#e67e22", command=self.toggle_gauge_recording_standalone)
        self.btn_fg_record.pack(side="right", padx=10, pady=10)

    # ─────────────────────────────────────────────────────────────────────────────
    # TAB 3: ENCODER INTERFACE BUILDER
    # ─────────────────────────────────────────────────────────────────────────────
    def _build_encoder_tab(self):
        self.tab_encoder.grid_columnconfigure(0, weight=1)
        self.tab_encoder.grid_rowconfigure(0, weight=1)

        enc_container = ctk.CTkFrame(self.tab_encoder)
        enc_container.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        enc_container.columnconfigure(0, weight=1)

        title = ctk.CTkLabel(enc_container, text="AMT102 Encoder Integration Settings", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(anchor="w", padx=20, pady=15)

        # Settings Panel
        settings_f = ctk.CTkFrame(enc_container)
        settings_f.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(settings_f, text="GPIO Input Pin (Channel A):").grid(row=0, column=0, padx=15, pady=10, sticky="w")
        self.entry_pin = ctk.CTkEntry(settings_f, width=100)
        self.entry_pin.insert(0, str(self.GPIO_A))
        self.entry_pin.grid(row=0, column=1, padx=15, pady=10, sticky="w")

        ctk.CTkLabel(settings_f, text="Encoder PPR Setting:").grid(row=1, column=0, padx=15, pady=10, sticky="w")
        self.entry_ppr = ctk.CTkEntry(settings_f, width=100)
        self.entry_ppr.insert(0, str(self.PPR))
        self.entry_ppr.grid(row=1, column=1, padx=15, pady=10, sticky="w")

        btn_apply = ctk.CTkButton(settings_f, text="Apply & Reinitialize GPIO", command=self.apply_encoder_configs)
        btn_apply.grid(row=2, column=0, columnspan=2, padx=15, pady=15, sticky="ew")

        # Telemetry Display Card
        self.enc_card = ctk.CTkFrame(enc_container, fg_color=("#dbdbdb", "#2b2b2b"))
        self.enc_card.pack(fill="x", padx=20, pady=15)
        self.lbl_live_rpm = ctk.CTkLabel(self.enc_card, text="--- RPM", font=ctk.CTkFont(size=44, weight="bold"))
        self.lbl_live_rpm.pack(pady=15)
        self.lbl_total_edges = ctk.CTkLabel(self.enc_card, text="Accrued Pulse Edges: 0")
        self.lbl_total_edges.pack(pady=(0, 15))

    # ─────────────────────────────────────────────────────────────────────
    # TAB 4: GOPRO INTERFACE BUILDER
    # ─────────────────────────────────────────────────────────────────────
    def _build_gopro_tab(self):
        self.tab_gopro.grid_columnconfigure(0, weight=1)

        gp_container = ctk.CTkScrollableFrame(self.tab_gopro)
        gp_container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.tab_gopro.grid_rowconfigure(0, weight=1)

        conn_box = ctk.CTkFrame(gp_container)
        conn_box.pack(fill="x", padx=15, pady=10)
        
        conn_title = ctk.CTkLabel(conn_box, text="Network Initialization", font=ctk.CTkFont(weight="bold"))
        conn_title.pack(anchor="w", padx=15, pady=(10, 0))

        self.btn_gp_connect = ctk.CTkButton(conn_box, text="Connect to GoPro (HERO4 Wi-Fi)", command=lambda: self.run_async(self.connect_gopro))
        self.btn_gp_connect.pack(fill="x", padx=15, pady=15)

        self.gp_settings_box = ctk.CTkFrame(gp_container)
        self.gp_settings_box.pack(fill="x", padx=15, pady=10)

        settings_title = ctk.CTkLabel(self.gp_settings_box, text="Protune Capture Presets", font=ctk.CTkFont(weight="bold"))
        settings_title.pack(anchor="w", padx=15, pady=(10, 0))

        ctk.CTkLabel(self.gp_settings_box, text="Resolution & Frame Rates:").pack(anchor="w", padx=15, pady=(10, 2))
        self.combo_res = ctk.CTkComboBox(self.gp_settings_box, values=["1080p 60fps", "1080p 30fps", "4K 30fps", "720p 120fps"])
        self.combo_res.pack(fill="x", padx=15, pady=5)
        self.combo_res.set("1080p 60fps")
        self.combo_res.configure(command=lambda e: self.run_async(self.change_gp_resolution))

        ctk.CTkLabel(self.gp_settings_box, text="White Balance color temp:").pack(anchor="w", padx=15, pady=(10, 2))
        self.combo_wb = ctk.CTkComboBox(self.gp_settings_box, values=["Auto", "3000K (Warm)", "5500K (Daylight)", "6500K (Cloudy)", "Native"])
        self.combo_wb.pack(fill="x", padx=15, pady=5)
        self.combo_wb.set("Auto")
        self.combo_wb.configure(command=lambda e: self.run_async(self.change_gp_white_balance))

        ctk.CTkLabel(self.gp_settings_box, text="Maximum ISO Sensitivity:").pack(anchor="w", padx=15, pady=(10, 2))
        self.combo_iso = ctk.CTkComboBox(self.gp_settings_box, values=["Auto", "400", "1600", "6400"])
        self.combo_iso.pack(fill="x", padx=15, pady=5)
        self.combo_iso.set("Auto")
        self.combo_iso.configure(command=lambda e: self.run_async(self.change_gp_iso))

        self.gp_controls_box = ctk.CTkFrame(gp_container)
        self.gp_controls_box.pack(fill="x", padx=15, pady=10)

        controls_title = ctk.CTkLabel(self.gp_controls_box, text="Manual Shutter Controls", font=ctk.CTkFont(weight="bold"))
        controls_title.pack(anchor="w", padx=15, pady=(10, 0))

        btn_f = ctk.CTkFrame(self.gp_controls_box, fg_color="transparent")
        btn_f.pack(fill="x", padx=15, pady=10)
        btn_f.columnconfigure((0, 1), weight=1)

        self.btn_mode_photo = ctk.CTkButton(btn_f, text="Photo Mode", command=lambda: self.run_async(self.set_gp_photo_mode))
        self.btn_mode_photo.grid(row=0, column=0, padx=2, pady=5, sticky="ew")
        self.btn_mode_video = ctk.CTkButton(btn_f, text="Video Mode", command=lambda: self.run_async(self.set_gp_video_mode))
        self.btn_mode_video.grid(row=0, column=1, padx=2, pady=5, sticky="ew")

        self.btn_photo = ctk.CTkButton(self.gp_controls_box, text="📸 Capture Still Frame Photo", command=lambda: self.run_async(self.take_gp_photo))
        self.btn_photo.pack(fill="x", padx=15, pady=5)

        self.btn_video = ctk.CTkButton(self.gp_controls_box, text="🎥 Start Video Recording Only", fg_color="#e67e22", command=lambda: self.run_async(self.toggle_gopro_recording_standalone))
        self.btn_video.pack(fill="x", padx=15, pady=5)

        self.btn_download = ctk.CTkButton(self.gp_controls_box, text="💾 Download Last Captured Media Asset", command=lambda: self.run_async(self.download_gp_media))
        self.btn_download.pack(fill="x", padx=15, pady=5)

        self.btn_power = ctk.CTkButton(self.gp_controls_box, text="🛑 Power Down Camera Array", fg_color="#e74c3c", command=lambda: self.run_async(self.power_off_gp))
        self.btn_power.pack(fill="x", padx=15, pady=15)

    # ─────────────────────────────────────────────────────────────────────
    # LOCAL STATE & PORT INTERACTION
    # ─────────────────────────────────────────────────────────────────────
    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo.configure(values=["Auto-Detect"] + ports)
        self.port_combo.set("Auto-Detect")
        self.log("Scanned local structural buses for active hardware communication serial lines.")

    def connect_pi_gpio(self):
        """Initializes pigpio connection and configures target input pins."""
        self.log("Attempting connection to pigpio daemon...")
        try:
            self.pi = pigpio.pi()
            if not self.pi.connected:
                raise RuntimeError("pigpio daemon connection dropped.")
            
            self.encoder_connected = True
            self.log(" pigpio Daemon connection established successfully.")
            self.setup_encoder_gpio()
        except Exception as e:
            self.encoder_connected = False
            self.log(f"[GPIO Warning]: pigpio not responding. {e}")
            messagebox.showwarning("pigpio Not Found", "Unable to establish contact with 'pigpiod'. Run 'sudo pigpiod' inside terminal.")

    def setup_encoder_gpio(self):
        """Configures the selected pin as input and sets hardware interrupts."""
        if not self.encoder_connected or not self.pi:
            return
        
        # Clean up existing callbacks
        if self.cb_encoder:
            self.cb_encoder.cancel()

        try:
            self.pi.set_mode(self.GPIO_A, pigpio.INPUT)
            self.pi.set_pull_up_down(self.GPIO_A, pigpio.PUD_UP)
            
            # Count rising and falling edges
            self.cb_encoder = self.pi.callback(self.GPIO_A, pigpio.EITHER_EDGE, self._on_encoder_pulse)
            self.log(f"Encoder registered on GPIO Pin {self.GPIO_A} @ {self.PPR} PPR configuration.")
        except Exception as e:
            self.log(f"[GPIO Register Error]: Failed setup. {e}")

    def _on_encoder_pulse(self, gpio, level, tick):
        self.pulse_count += 1

    def apply_encoder_configs(self):
        try:
            pin = int(self.entry_pin.get())
            ppr = int(self.entry_ppr.get())
            if ppr <= 0 or pin < 0:
                raise ValueError
            self.GPIO_A = pin
            self.PPR = ppr
            self.setup_encoder_gpio()
            self.update_ui_states()
        except ValueError:
            messagebox.showerror("Configuration Error", "Ensure Pin and PPR settings are positive integers.")

    def update_ui_states(self):
        """Dynamic evaluation rule tree mapping device statuses into UI availability states."""
        # 1. Update Gauge specific views
        if self.fg_connected:
            self.btn_fg_connect.configure(text="Disconnect Gauge", fg_color="#e74c3c")
            m_str = "Tension" if self._force_mode else "Compression"
            self.lbl_live_status.configure(text=f"Port Active: {self.ng.device_path} ({m_str})")
            self.lbl_sync_fg_status.configure(text=f"Force Gauge: Active on {self.ng.device_path}", fg_color="#2ecc71")
            fg_state = "normal"
        else:
            self.btn_fg_connect.configure(text="Connect Gauge", fg_color="#2ecc71")
            self.lbl_live_status.configure(text="Device Status: Not connected")
            self.lbl_live_val.configure(text="---")
            self.lbl_sync_fg_status.configure(text="Force Gauge: Disconnected", fg_color="#e74c3c")
            fg_state = "disabled"

        for w in [self.btn_zero, self.btn_unit, self.btn_track, self.btn_reset, self.btn_fg_record]:
            w.configure(state=fg_state)

        # 2. Update Encoder status
        if self.encoder_connected:
            self.lbl_sync_enc_status.configure(text=f"Encoder: GPIO {self.GPIO_A} Connected", fg_color="#2ecc71")
        else:
            self.lbl_sync_enc_status.configure(text="Encoder (pigpio): Offline", fg_color="#e74c3c")

        # 3. Update GoPro specific views
        if self.gp_connected:
            self.btn_gp_connect.configure(text="GoPro Connected (HERO4)", fg_color="#2ecc71")
            self.lbl_sync_gp_status.configure(text="GoPro: Camera Mesh Connected", fg_color="#2ecc71")
            gp_state = "normal"
        else:
            self.btn_gp_connect.configure(text="Connect to GoPro (HERO4 Wi-Fi)", fg_color="#3498db")
            self.lbl_sync_gp_status.configure(text="GoPro: Disconnected", fg_color="#e74c3c")
            gp_state = "disabled"

        for w in [self.combo_res, self.combo_wb, self.combo_iso, self.btn_mode_photo, 
                  self.btn_mode_video, self.btn_photo, self.btn_video, self.btn_download, self.btn_power]:
            w.configure(state=gp_state)

        # 4. Synchronized Action Button Rules
        if self.fg_recording or self.gp_recording:
            self.btn_sync_record.configure(text="⏹ Stop Synchronized Recording", fg_color="#7f8c8d")
            self.btn_fg_record.configure(state="disabled")
            self.btn_video.configure(state="disabled")
        else:
            self.btn_sync_record.configure(text="🚀 Sync Start Recording (All Streams)", fg_color="#9b59b6")
            if self.fg_connected: self.btn_fg_record.configure(state="normal")
            if self.gp_connected: self.btn_video.configure(state="normal")

    # ─────────────────────────────────────────────────────────────────────
    # HARDWARE LAYER: FORCE GAUGE CORE ACTIONS
    # ─────────────────────────────────────────────────────────────────────
    def toggle_gauge_connection(self):
        if self.fg_connected:
            if self.fg_recording: self.stop_pipeline()
            self.ng.disconnect()
            self.fg_connected = False
            self.log("Force gauge link terminated cleanly.")
            self.update_ui_states()
        else:
            sel = self.port_combo.get()
            port = None if sel == "Auto-Detect" else sel
            f_mode = self.mode_switch.get() == "Tension"
            b_rate = self.baud_switch.get().lower()

            if not port:
                if not self.ng.find():
                    messagebox.showerror("Hardware Error", "Could not automatically track a responsive sensor bus link.")
                    return
            
            if self.ng.connect(force_mode=f_mode, rate=b_rate):
                self.fg_connected = True
                self._force_mode = f_mode
                self._baud_rate = b_rate
                self.log(f"Force sensor assigned to address -> {self.ng.device_path}")
                self.update_ui_states()
            else:
                messagebox.showerror("Bus Error", "Handshake dropped by core sensor serial controller module.")

    def toggle_gauge_recording_standalone(self):
        """Launches recording tracking only the Force Gauge telemetry."""
        if self.fg_recording:
            self.stop_pipeline()
            self.update_ui_states()
        else:
            if not self.initialize_filename_context(): return
            self.start_pipeline(only_gauge=True)
            self.update_ui_states()

    def initialize_filename_context(self) -> bool:
        try:
            self.sample_interval = float(self.entry_interval.get())
            if self.sample_interval <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("Input Error", "Sample rate metrics must evaluate to valid positive coefficients.")
            return False

        fn = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Log Document", "*.csv")])
        if not fn: return False
        self.output_file = fn
        return True

    def start_pipeline(self, only_gauge=False):
        self._sync_stop_event.clear()
        self.fg_recording = True
        
        target_loop = self._gauge_only_recording_loop if only_gauge else self._synchronized_recording_loop
        self._sync_record_thread = threading.Thread(target=target_loop, daemon=True)
        self._sync_record_thread.start()
        self.log(f"Asynchronous data channel logging explicitly to: {self.output_file}")

    def stop_pipeline(self):
        self._sync_stop_event.set()
        if self._sync_record_thread:
            self._sync_record_thread.join(timeout=2)
        self.fg_recording = False
        self.log("Logging and sensor scanning loop safely halted.")
        self.after(0, lambda: self.lbl_live_val.configure(text="---"))
        self.after(0, lambda: self.lbl_live_rpm.configure(text="--- RPM"))

    def _gauge_only_recording_loop(self):
        """Asynchronous collection loops mapping directly into local hardware registers."""
        with open(self.output_file, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["timestamp", "elapsed_s", "force_parsed", "short_output", "long_output"])
            fh.flush()

            start_t = time.time()
            while not self._sync_stop_event.is_set():
                try:
                    short = self.ng.short_output()
                    long_ = self.ng.long_output()
                    elapsed = round(time.time() - start_t, 3)
                    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    parsed = _parse_number(short)

                    writer.writerow([ts, elapsed, parsed, short, long_])
                    fh.flush()

                    disp = short if short else f"{parsed}"
                    self.after(0, lambda d=disp: self.lbl_live_val.configure(text=d))
                except Exception as e:
                    self.after(0, lambda err=e: self.log(f"[Telemetry Exception Trace]: {err}"))

                self._sync_stop_event.wait(self.sample_interval)

    # ── Quick Force Gauge Wrappers ──
    def send_zero(self): self.run_async(lambda: self.log("Zero/Tare: OK") if self.ng.zero() else self.log("Zero failed."))
    def change_unit(self): self.run_async(lambda: self.log("Unit Swapped") if self.ng.unit() else self.log("Unit swap failed."))
    def toggle_track_peak(self): self.run_async(lambda: self.log("Mode Toggled") if self.ng.mode() else self.log("Mode toggle failed."))
    def send_reset(self): self.run_async(lambda: self.log("Device Reset") if self.ng.reset() else self.log("Reset rejected."))

    # ─────────────────────────────────────────────────────────────────────
    # HARDWARE LAYER: GOPRO WIRELESS NETWORK CORE ACTIONS
    # ─────────────────────────────────────────────────────────────────────
    def connect_gopro(self):
        self.log("Scanning system network gateways for explicit GoPro HERO4 endpoints...")
        try:
            self.gopro = GoProCamera.GoPro(gp_constants.gpcontrol)
            self.gp_connected = True
            self.log("GoPro client connection verified over standard network API interfaces.")
        except Exception as e:
            self.gp_connected = False
            self.log(f"[Network Initialization Error]: Connection trace rejected -> {e}")
            self.after(0, lambda: messagebox.showerror("Camera Network Error", f"Failed to secure access to the local camera network.\n\n{e}"))
        self.after(0, self.update_ui_states)

    def toggle_gopro_recording_standalone(self):
        if self.gp_recording:
            self.gopro.shutter(gp_constants.Shutter.OFF)
            self.gp_recording = False
            self.log("GoPro capture operations terminated manually.")
            self.after(0, lambda: self.btn_video.configure(text="🎥 Start Video Recording Only"))
        else:
            self.gopro.shutter(gp_constants.Shutter.ON)
            self.gp_recording = True
            self.log("GoPro single-channel digital recording session initiated.")
            self.after(0, lambda: self.btn_video.configure(text="🛑 Stop Recording"))
        self.after(0, self.update_ui_states)

    # ── Settings & Asset Handlers ──
    def change_gp_resolution(self):
        sel = self.combo_res.get()
        if sel == "1080p 60fps":
            self.gopro.gpControlCommand("setting/2/9"); self.gopro.gpControlCommand("setting/3/5")
        elif sel == "1080p 30fps":
            self.gopro.gpControlCommand("setting/2/9"); self.gopro.gpControlCommand("setting/3/8")
        elif sel == "4K 30fps":
            self.gopro.gpControlCommand("setting/2/1"); self.gopro.gpControlCommand("setting/3/8")
        elif sel == "720p 120fps":
            self.gopro.gpControlCommand("setting/2/12"); self.gopro.gpControlCommand("setting/3/1")
        self.log(f"GoPro frame matrix changed to -> {sel}")

    def change_gp_white_balance(self):
        sel = self.combo_wb.get()
        m = {"Auto": "0", "3000K (Warm)": "1", "5500K (Daylight)": "2", "6500K (Cloudy)": "3", "Native": "4"}
        self.gopro.gpControlCommand(f"setting/11/{m[sel]}")
        self.log(f"GoPro Color Space Balanced -> {sel}")

    def change_gp_iso(self):
        sel = self.combo_iso.get()
        m = {"Auto": "0", "400": "2", "1600": "1", "6400": "0"}
        self.gopro.gpControlCommand(f"setting/13/{m[sel]}")
        self.log(f"GoPro Light Limit Adjusted -> {sel}")

    def set_gp_photo_mode(self): self.gopro.mode(gp_constants.Mode.PhotoMode); self.log("Camera mode forced to Photo Mode.")
    def set_gp_video_mode(self): self.gopro.mode(gp_constants.Mode.VideoMode); self.log("Camera mode forced to Video Mode.")
    def take_gp_photo(self): self.gopro.take_photo(); self.log("Still snapshot transaction successfully committed.")
    
    def download_gp_media(self):
        self.log("Querying storage blocks over Wi-Fi allocations...")
        try:
            self.gopro.downloadLastMedia()
            self.after(0, lambda: messagebox.showinfo("Download Complete", "Last media capture downloaded successfully to workspace."))
        except Exception as e:
            self.after(0, lambda err=e: messagebox.showerror("Transfer Error", f"Asset stream failed -> {err}"))

    def power_off_gp(self):
        if messagebox.askyesno("Power Down", "Terminate wireless connection and turn off camera array power?"):
            self.gopro.power_off()
            self.gp_connected = False
            self.gp_recording = False
            self.log("GoPro system has been powered off.")
            self.update_ui_states()

    # ─────────────────────────────────────────────────────────────────────
    # MASTER CONSOLIDATED MULTI-DEVICE SYNCHRONIZED ACQUISITION
    # ─────────────────────────────────────────────────────────────────────
    def toggle_synchronized_recording(self):
        """Unified master control script initiating state triggers across all devices."""
        if self.fg_recording or self.gp_recording:
            self.log("Broadcasting stop commands across active system arrays...")
            
            # 1. Kill telemetry scanning and file handles
            if self.fg_recording:
                self.stop_pipeline()
                self.log("Multi-channel master sync log saved.")

            # 2. Shut off camera video stream
            if self.gp_recording:
                def halt_shutter_async():
                    try:
                        self.gopro.shutter(gp_constants.Shutter.OFF)
                        self.gp_recording = False
                        self.log("GoPro wireless recording array stopped.")
                    except Exception as e:
                        self.log(f"[Sync Warning]: Camera shutter command timed out -> {e}")
                    self.after(0, self.update_ui_states)
                
                self.run_async(halt_shutter_async)
            else:
                self.update_ui_states()
        else:
            if not self.fg_connected:
                messagebox.showerror("Sync Execution Error", "Unified recordings require a connected force gauge asset.")
                return
            if not self.gp_connected:
                messagebox.showerror("Sync Execution Error", "Unified recordings require an active GoPro client mesh.")
                return
            if not self.encoder_connected:
                messagebox.showerror("Sync Execution Error", "Unified recordings require a running 'pigpio' connection.")
                return

            if not self.initialize_filename_context():
                return

            self.log("Aligning asynchronous arrays for master sync start sequence...")

            # 1. Start GoPro recording off-thread
            def initialize_sync_shutter_async():
                try:
                    self.gopro.shutter(gp_constants.Shutter.ON)
                    self.gp_recording = True
                    self.log("GoPro video stream successfully established.")
                except Exception as e:
                    self.log(f"[Sync Critical Failure]: Shutter link failed to connect -> {e}")
                
                # 2. Immediately initiate synchronized file logger on standard time ticks
                self.after(0, lambda: self.start_pipeline(only_gauge=False))
                self.after(0, self.update_ui_states)

            self.run_async(initialize_sync_shutter_async)

    def _synchronized_recording_loop(self):
        """
        The Master Telemetry Engine: Pulls Force and Encoder ticks simultaneously 
        at a fixed time frequency, printing and saving them to a single synced CSV.
        """
        with open(self.output_file, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            # Unified data headers
            writer.writerow(["timestamp", "elapsed_s", "force_parsed", "encoder_pulses_in_tick", "encoder_RPM", "force_raw_short"])
            fh.flush()

            start_t = time.time()
            self.pulse_count = 0  # Reset pulse tracking to zero
            
            while not self._sync_stop_event.is_set():
                tick_start = time.time()
                try:
                    # 1. Fetch Force Gauge values
                    force_short = self.ng.short_output()
                    force_parsed = _parse_number(force_short)

                    # 2. Fetch Encoder values (Thread-safe read of pulse counter)
                    current_pulses = self.pulse_count
                    self.pulse_count = 0  # Reset for the next interval segment
                    
                    # Either_Edge tracking counts both rising and falling states (2 edges per cycle)
                    cycles = current_pulses / 2.0
                    rpm = (cycles / self.PPR) * (60.0 / self.sample_interval)

                    # 3. Compile timing metrics
                    elapsed = round(time.time() - start_t, 3)
                    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

                    # 4. Write to Consolidated Log file
                    writer.writerow([ts, elapsed, force_parsed, current_pulses, round(rpm, 2), force_short])
                    fh.flush()

                    # 5. Push updates cleanly to Dashboard Cards
                    f_disp = force_short if force_short else f"{force_parsed}"
                    self.after(0, lambda d=f_disp: self.lbl_live_val.configure(text=d))
                    self.after(0, lambda r=rpm, p=current_pulses: self._update_encoder_telemetry_ui(r, p))

                except Exception as e:
                    self.after(0, lambda err=e: self.log(f"[Telemetry Exception Trace]: {err}"))

                # Keep loop timings uniform by subtracting processing overhead delay
                work_time = time.time() - tick_start
                remaining_delay = max(0, self.sample_interval - work_time)
                self._sync_stop_event.wait(remaining_delay)

    def _update_encoder_telemetry_ui(self, rpm_val, pulses):
        self.lbl_live_rpm.configure(text=f"{rpm_val:.1f} RPM")
        self.lbl_total_edges.configure(text=f"Last Tick Edges: {pulses}")


if __name__ == "__main__":
    app = UnifiedControllerGUI()
    app.mainloop()