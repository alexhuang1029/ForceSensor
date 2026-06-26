import sys
import time
import csv
import re
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
import serial.tools.list_ports

# ── Dependency Check for NexGraph ──────────────────────────────────────────
try:
    from nexgraphpy.nexgraph import NexGraph
except ImportError:
    print("[ERROR] nexgraphpy not found. Install with: pip install nexgraphpy")
    sys.exit(1)

# Set UI Theme styling
ctk.set_appearance_mode("System")  # Options: "System", "Dark", "Light"
ctk.set_default_color_theme("blue")

def _parse_number(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"[-+]?\d+\.?\d*", text)
    return float(m.group()) if m else None


class ForceRecorderGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Backend Initialization ---
        self.ng = NexGraph()
        self.connected = False
        self.recording = False
        self._record_thread = None
        self._stop_event = threading.Event()
        self.sample_interval = 0.5
        self.output_file = ""
        self._force_mode = True  # True = Tension, False = Compression
        self._baud_rate = "high"

        # --- Window Setup ---
        self.title("NexGraph Force Recorder")
        self.geometry("900x650")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._create_widgets()
        self.refresh_ports()
        self.update_status_ui()

    def _create_widgets(self):
        # ─────────────────────────────────────────────────────────────────────
        # LEFT PANEL: Connection & Configurations
        # ─────────────────────────────────────────────────────────────────────
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        lbl_conn = ctk.CTkLabel(self.sidebar, text="CONNECTION SETTINGS", font=ctk.CTkFont(weight="bold"))
        lbl_conn.pack(pady=(15, 5), padx=10, anchor="w")

        # Port Selector Row
        port_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        port_frame.pack(fill="x", padx=10, pady=5)
        self.port_combo = ctk.CTkComboBox(port_frame, values=["Auto-Detect"])
        self.port_combo.pack(side="left", fill="x", expand=True, padx=(0, 5))
        btn_refresh = ctk.CTkButton(port_frame, text="🔄", width=35, command=self.refresh_ports)
        btn_refresh.pack(side="right")

        # Configuration Segmented Toggles
        lbl_mode = ctk.CTkLabel(self.sidebar, text="Measurement Mode:")
        lbl_mode.pack(padx=10, anchor="w", pady=(5, 0))
        self.mode_switch = ctk.CTkSegmentedButton(self.sidebar, values=["Tension", "Compression"])
        self.mode_switch.set("Tension")
        self.mode_switch.pack(fill="x", padx=10, pady=5)

        lbl_baud = ctk.CTkLabel(self.sidebar, text="Baud Rate:")
        lbl_baud.pack(padx=10, anchor="w", pady=(5, 0))
        self.baud_switch = ctk.CTkSegmentedButton(self.sidebar, values=["High", "Low"])
        self.baud_switch.set("High")
        self.baud_switch.pack(fill="x", padx=10, pady=5)

        # Connect / Disconnect Buttons
        self.btn_connect = ctk.CTkButton(self.sidebar, text="Connect Device", fg_color="#2ecc71", hover_color="#27ae60", command=self.toggle_connection)
        self.btn_connect.pack(fill="x", padx=10, pady=(15, 5))

        # Divider
        ctk.CTkFrame(self.sidebar, height=2, fg_color="gray").pack(fill="x", padx=10, pady=15)

        # ─────────────────────────────────────────────────────────────────────
        # LEFT PANEL: Hardware Controls
        # ─────────────────────────────────────────────────────────────────────
        lbl_ctrl = ctk.CTkLabel(self.sidebar, text="HARDWARE CONTROLS", font=ctk.CTkFont(weight="bold"))
        lbl_ctrl.pack(padx=10, anchor="w")

        grid_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        grid_frame.pack(fill="x", padx=10, pady=5)
        grid_frame.columnconfigure((0, 1), weight=1)

        self.btn_zero = ctk.CTkButton(grid_frame, text="Zero / Tare", command=self.send_zero)
        self.btn_zero.grid(row=0, column=0, padx=2, pady=4, sticky="ew")
        
        self.btn_unit = ctk.CTkButton(grid_frame, text="Cycle Unit", command=self.change_unit)
        self.btn_unit.grid(row=0, column=1, padx=2, pady=4, sticky="ew")

        self.btn_track = ctk.CTkButton(grid_frame, text="Toggle Track/Peak", command=self.toggle_track_peak)
        self.btn_track.grid(row=1, column=0, padx=2, pady=4, sticky="ew")

        self.btn_reset = ctk.CTkButton(grid_frame, text="Reset Device", fg_color="#e74c3c", hover_color="#c0392b", command=self.send_reset)
        self.btn_reset.grid(row=1, column=1, padx=2, pady=4, sticky="ew")

        # ─────────────────────────────────────────────────────────────────────
        # RIGHT PANEL: Data Logging Dashboard
        # ─────────────────────────────────────────────────────────────────────
        self.main_content = ctk.CTkFrame(self)
        self.main_content.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.main_content.columnconfigure(0, weight=1)
        self.main_content.rowconfigure(2, weight=1)

        # Live Display Telemetry Readout Box
        self.telemetry_card = ctk.CTkFrame(self.main_content, fg_color=("#dbdbdb", "#2b2b2b"))
        self.telemetry_card.grid(row=0, column=0, sticky="ew", padx=15, pady=15)
        
        self.lbl_live_val = ctk.CTkLabel(self.telemetry_card, text="---", font=ctk.CTkFont(size=44, weight="bold"))
        self.lbl_live_val.pack(pady=10)
        self.lbl_live_status = ctk.CTkLabel(self.telemetry_card, text="Device Not Connected", font=ctk.CTkFont(size=12))
        self.lbl_live_status.pack(pady=(0, 10))

        # Recording Status & Parameters Card
        rec_frame = ctk.CTkFrame(self.main_content)
        rec_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=5)

        lbl_interval = ctk.CTkLabel(rec_frame, text="Interval (s):")
        lbl_interval.pack(side="left", padx=(10, 2))
        self.entry_interval = ctk.CTkEntry(rec_frame, width=50)
        self.entry_interval.insert(0, str(self.sample_interval))
        self.entry_interval.pack(side="left", padx=5, pady=10)

        self.btn_record = ctk.CTkButton(rec_frame, text="🔴 Start Recording", fg_color="#e67e22", hover_color="#d35400", command=self.toggle_recording)
        self.btn_record.pack(side="right", padx=10, pady=10)

        # Interactive Terminal Console Log Box
        self.txt_log = ctk.CTkTextbox(self.main_content, font=ctk.CTkFont(family="Courier", size=12))
        self.txt_log.grid(row=2, column=0, sticky="nsew", padx=15, pady=15)
        
    # ── Utility methods ───────────────────────────────────────────────────────

    def log(self, message: str):
        """Append strings safely into UI Console Terminal view."""
        self.txt_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.txt_log.see(tk.END)

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo.configure(values=["Auto-Detect"] + ports)
        self.port_combo.set("Auto-Detect")
        self.log("Refreshed hardware communication serial ports layout.")

    def update_status_ui(self):
        """Toggle active widgets states depending on physical hardware link."""
        if self.connected:
            self.btn_connect.configure(text="Disconnect Device", fg_color="#e74c3c", hover_color="#c0392b")
            mode_str = "Tension" if self._force_mode else "Compression"
            self.lbl_live_status.configure(text=f"Connected on {self.ng.device_path} ({mode_str} Mode)")
            
            state = "normal"
        else:
            self.btn_connect.configure(text="Connect Device", fg_color="#2ecc71", hover_color="#27ae60")
            self.lbl_live_status.configure(text="Device Status: Disconnected")
            self.lbl_live_val.configure(text="---")
            state = "disabled"

        # Safe lock state rules
        self.btn_zero.configure(state=state)
        self.btn_unit.configure(state=state)
        self.btn_track.configure(state=state)
        self.btn_reset.configure(state=state)
        self.btn_record.configure(state=state)

    # ── Core Action Callbacks ────────────────────────────────────────────────

    def toggle_connection(self):
        if self.connected:
            if self.recording:
                self.toggle_recording()
            self.ng.disconnect()
            self.connected = False
            self.log("Disconnected successfully.")
            self.update_status_ui()
        else:
            port_sel = self.port_combo.get()
            port = None if port_sel == "Auto-Detect" else port_sel
            f_mode = self.mode_switch.get() == "Tension"
            b_rate = self.baud_switch.get().lower()

            if not port:
                self.log("Scanning automatically via target platform rules...")
                if not self.ng.find():
                    self.log("[Error] No active devices detected instantly.")
                    messagebox.showerror("Error", "No compatible device found automatically.")
                    return

            success = self.ng.connect(force_mode=f_mode, rate=b_rate)
            if success:
                self.connected = True
                self._force_mode = f_mode
                self._baud_rate = b_rate
                self.log(f"Connection bound successfully -> {self.ng.device_path}")
                self.update_status_ui()
            else:
                self.log("[Error] Target handshakes rejected command line.")
                messagebox.showerror("Error", "Connection failed. Verify configuration rules.")

    def toggle_recording(self):
        if self.recording:
            # Stop sequence triggered
            self._stop_event.set()
            if self._record_thread:
                self._record_thread.join(timeout=2)
            self.recording = False
            self.btn_record.configure(text="🔴 Start Recording", fg_color="#e67e22")
            self.log(f"Data stream captured cleanly -> {self.output_file}")
            self.mode_switch.configure(state="normal")
            self.baud_switch.configure(state="normal")
        else:
            # Parse parameters safeguards
            try:
                self.sample_interval = float(self.entry_interval.get())
                if self.sample_interval <= 0: raise ValueError
            except ValueError:
                messagebox.showerror("Invalid Input", "Sample interval must be a positive float number.")
                return

            # Request File Export path context
            fn = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
            if not fn:
                return # User cancelled file dialog prompt

            self.output_file = fn
            self._stop_event.clear()
            self.recording = True
            self.btn_record.configure(text="⏹ Stop Recording", fg_color="#7f8c8d")
            self.mode_switch.configure(state="disabled")
            self.baud_switch.configure(state="disabled")

            # Spin logging backend asynchronously to prevent application freezes
            self._record_thread = threading.Thread(target=self._recording_loop, daemon=True)
            self._record_thread.start()
            self.log(f"Asynchronous live pipeline writing -> {fn}")

    def _recording_loop(self):
        with open(self.output_file, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["timestamp", "elapsed_s", "value_parsed", "short_output", "long_output"])
            fh.flush()

            start_time = time.time()
            while not self._stop_event.is_set():
                try:
                    short = self.ng.short_output()
                    long_ = self.ng.long_output()
                    elapsed = round(time.time() - start_time, 3)
                    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    parsed = _parse_number(short)

                    writer.writerow([ts, elapsed, parsed, short, long_])
                    fh.flush()

                    # Safely push visual measurements directly into UI Main Loop thread
                    disp_text = short if short else f"{parsed}"
                    self.after(0, lambda v=disp_text: self.lbl_live_val.configure(text=v))

                except Exception as e:
                    self.after(0, lambda err=e: self.log(f"[Exception Runtime]: {err}"))

                self._stop_event.wait(self.sample_interval)

    # ── Quick Wrappers mapping directly to your internal backend APIs ────────

    def send_zero(self):
        if self.ng.zero(): self.log("Command Execution Successful: Zero / Tare")
        else: self.log("[Fail Warning]: Zero adjustment command discarded.")

    def change_unit(self):
        if self.ng.unit(): self.log("Command Execution Successful: Unit configuration rotated.")
        else: self.log("[Fail Warning]: Unit rotation request timed out.")

    def toggle_track_peak(self):
        if self.ng.mode(): self.log("Command Execution Successful: Track/Peak hardware mode inverted.")
        else: self.log("[Fail Warning]: Mode inversion failed.")

    def send_reset(self):
        if self.ng.reset(): self.log("System Alert: Target microcontroller reset command processed.")
        else: self.log("[Fail Warning]: Reset instruction ignored by host board.")


if __name__ == "__main__":
    app = ForceRecorderGUI()
    app.mainloop()