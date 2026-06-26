#!/usr/bin/env python3
"""
NexGraph Force Recorder
========================
Records force sensor data over time from a Nextech force gauge via NexGraph.

Features:
  - Auto-detect or manually select USB/COM port
  - Switch ports without restarting the script
  - Toggle Track / Peak mode (mode command)
  - Switch Tension / Compression mode (reconnect with force_mode flag)
  - Change measurement unit
  - Zero / Tare and Reset commands
  - Continuous time-series recording to CSV
  - Adjustable sample rate

Usage:
  pip install nexgraphpy pyserial
  python force_recorder.py
"""

import time
import csv
import re
import sys
import threading
from datetime import datetime

# ── Dependency checks ────────────────────────────────────────────────────────
try:
    from nexgraphpy.nexgraph import NexGraph
except ImportError:
    print("[ERROR] nexgraphpy not found. Install with:  pip install nexgraphpy")
    sys.exit(1)

try:
    import serial.tools.list_ports
except ImportError:
    print("[ERROR] pyserial not found. Install with:  pip install pyserial")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# ForceRecorder
# ─────────────────────────────────────────────────────────────────────────────

class ForceRecorder:
    """Wraps the NexGraph device with recording, port-switching, and mode control."""

    def __init__(self):
        self.ng = NexGraph()
        self.connected = False
        self.recording = False
        self._record_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Recording settings
        self.sample_interval: float = 0.5   # seconds between samples
        self.output_file: str = ""

        # Track current connection params so we can reconnect cleanly
        self._force_mode: bool = True        # True = Tension, False = Compression
        self._baud_rate: str = "high"

    # ── Connection ────────────────────────────────────────────────────────────

    def list_ports(self) -> list:
        """Return and print all available serial ports."""
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            print("  (no serial ports detected)")
        else:
            for i, p in enumerate(ports):
                print(f"  [{i}] {p.device:<12} – {p.description}")
        return ports

    def connect(self, port: str | None = None,
                force_mode: bool = True,
                rate: str = "high") -> bool:
        """
        Connect to the gauge.

        Parameters
        ----------
        port       : explicit device path (e.g. 'COM3', '/dev/ttyUSB0').
                     Pass None to let NexGraph auto-find the device.
        force_mode : True  → Tension mode
                     False → Compression mode
        rate       : 'high' or 'low' baud rate
        """
        if self.connected:
            self._graceful_disconnect()

        if port:
            self.ng.device_path = port
        else:
            print("  Scanning for devices …")
            if not self.ng.find():
                print("  [!] No device found automatically.")
                print("      Try listing ports and entering the port manually.")
                return False

        success = self.ng.connect(force_mode=force_mode, rate=rate)
        if success:
            self.connected = True
            self._force_mode = force_mode
            self._baud_rate = rate
            print(f"  Connected  →  {self.ng.device_path}")
            print(f"  Measurement  : {'Tension' if force_mode else 'Compression'}")
            print(f"  Baud rate    : {rate}")
        else:
            print("  [!] Connection failed. Check the port and try again.")
        return success

    def disconnect(self):
        """Stop recording (if active) and disconnect from device."""
        if self.recording:
            self.stop_recording()
        self._graceful_disconnect()

    def _graceful_disconnect(self):
        if self.connected:
            self.ng.disconnect()
            self.connected = False
            print("  Disconnected.")

    def reconnect_compression(self):
        """Reconnect in Compression mode (force_mode=False)."""
        print("  Reconnecting in Compression mode …")
        self.connect(port=self.ng.device_path,
                     force_mode=False,
                     rate=self._baud_rate)

    def reconnect_tension(self):
        """Reconnect in Tension mode (force_mode=True)."""
        print("  Reconnecting in Tension mode …")
        self.connect(port=self.ng.device_path,
                     force_mode=True,
                     rate=self._baud_rate)

    # ── Device commands ───────────────────────────────────────────────────────

    def _require_connection(self) -> bool:
        if not self.connected:
            print("  [!] Not connected to a device.")
            return False
        return True

    def get_info(self):
        if not self._require_connection():
            return
        info = self.ng.get_info()
        print(f"\n  Device info:\n  {info}")

    def send_zero(self):
        if not self._require_connection():
            return
        ok = self.ng.zero()
        print(f"  Zero / Tare: {'OK' if ok else 'FAILED'}")

    def send_reset(self):
        if not self._require_connection():
            return
        ok = self.ng.reset()
        print(f"  Reset: {'OK' if ok else 'FAILED'}")

    def toggle_track_peak(self):
        """Toggle between Track and Peak mode via the mode() command."""
        if not self._require_connection():
            return
        ok = self.ng.mode()
        print(f"  Track/Peak mode toggled: {'OK' if ok else 'FAILED'}")

    def change_unit(self):
        """Cycle to the next unit of measurement."""
        if not self._require_connection():
            return
        ok = self.ng.unit()
        print(f"  Unit changed: {'OK' if ok else 'FAILED'}")

    def show_current_values(self):
        if not self._require_connection():
            return
        print(f"\n  Mini   : {self.ng.mini_output()}")
        print(f"  Short  : {self.ng.short_output()}")
        print(f"  Long   : {self.ng.long_output()}")
        print(f"  Print  : {self.ng.print_value()}")

    def show_peak_values(self):
        if not self._require_connection():
            return
        print(f"\n  Peak Tension     : {self.ng.peak_tension()}")
        print(f"  Peak Compression : {self.ng.peak_compression()}")

    def download_memory(self):
        if not self._require_connection():
            return
        fmt = input("  Download format [raw / csv] (default: csv): ").strip().lower()
        if fmt not in ("raw", "csv"):
            fmt = "csv"
        data = self.ng.download(out_format=fmt)
        print(f"\n  Downloaded data:\n{data}")

    # ── Recording ─────────────────────────────────────────────────────────────

    def start_recording(self, filename: str = ""):
        if not self._require_connection():
            return
        if self.recording:
            print("  [!] Already recording. Stop first.")
            return

        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"force_data_{ts}.csv"

        self.output_file = filename
        self._stop_event.clear()
        self.recording = True
        self._record_thread = threading.Thread(
            target=self._record_loop, daemon=True
        )
        self._record_thread.start()
        print(f"  Recording started  →  {filename}")
        print(f"  Sample interval    :  {self.sample_interval} s")
        print("  (readings display below; press Enter or choose Stop to halt)")

    def _record_loop(self):
        """Background thread: poll device and write rows to CSV."""
        with open(self.output_file, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "timestamp", "elapsed_s",
                "value_parsed", "short_output", "long_output"
            ])
            fh.flush()

            start = time.time()
            while not self._stop_event.is_set():
                try:
                    short = self.ng.short_output()
                    long_ = self.ng.long_output()
                    elapsed = round(time.time() - start, 3)
                    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    parsed = _parse_number(short)

                    writer.writerow([ts, elapsed, parsed, short, long_])
                    fh.flush()

                    mode_str = "T" if self._force_mode else "C"
                    print(
                        f"\r  [{ts}]  {elapsed:>8.2f} s  |  "
                        f"[{mode_str}] {short:<20}",
                        end="", flush=True
                    )
                except Exception as exc:
                    print(f"\n  [!] Read error: {exc}")

                self._stop_event.wait(self.sample_interval)

    def stop_recording(self):
        if not self.recording:
            print("  Not currently recording.")
            return
        self._stop_event.set()
        if self._record_thread:
            self._record_thread.join(timeout=3)
        self.recording = False
        print(f"\n  Recording stopped  →  saved to: {self.output_file}")

    def set_sample_interval(self):
        try:
            val = float(input(
                f"  New interval in seconds (current: {self.sample_interval}): "
            ).strip())
            if val <= 0:
                raise ValueError
            self.sample_interval = val
            print(f"  Sample interval set to {self.sample_interval} s")
        except ValueError:
            print("  [!] Invalid value – must be a positive number.")

    # ── Status string ─────────────────────────────────────────────────────────

    def status_line(self) -> str:
        if not self.connected:
            return "DISCONNECTED"
        mode_str = "Tension" if self._force_mode else "Compression"
        rec_str  = "  ● REC" if self.recording else ""
        return (
            f"CONNECTED  |  {self.ng.device_path}  |  "
            f"{mode_str}  |  {self.sample_interval:.2f} s/sample"
            f"{rec_str}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_number(text: str) -> float | None:
    """Extract the first float/int from a raw output string."""
    if not text:
        return None
    m = re.search(r"[-+]?\d+\.?\d*", text)
    return float(m.group()) if m else None


def _divider(char: str = "─", width: int = 62) -> str:
    return char * width


def _ask_connection_params() -> tuple[str | None, bool, str]:
    """Prompt user for port, force_mode, and baud rate. Returns (port, force_mode, rate)."""
    port_in = input(
        "  Port (press Enter to auto-detect, or type e.g. COM3 / /dev/ttyUSB0): "
    ).strip()
    port = port_in if port_in else None

    mode_in = input("  Mode – [T]ension / [C]ompression (default T): ").strip().upper()
    force_mode = mode_in != "C"

    baud_in = input("  Baud rate – [H]igh / [L]ow (default H): ").strip().upper()
    rate = "low" if baud_in == "L" else "high"

    return port, force_mode, rate


# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────

MENU = """
  CONNECTION
  ──────────────────────────────────────
  [1]  Auto-find & connect
  [2]  List ports, then connect
  [3]  Switch port (reconnect to new port)
  [4]  Disconnect

  DEVICE INFO & READINGS
  ──────────────────────────────────────
  [5]  Get device info
  [6]  Show current values (mini/short/long)
  [7]  Show peak values (tension & compression)
  [8]  Download device memory

  RECORDING
  ──────────────────────────────────────
  [9]  Start recording
  [0]  Stop  recording
  [s]  Set sample interval

  SENSOR CONTROLS
  ──────────────────────────────────────
  [m]  Toggle Track / Peak mode
  [t]  Switch to Tension   (reconnects)
  [c]  Switch to Compression (reconnects)
  [u]  Change unit
  [z]  Zero / Tare
  [r]  Reset

  [q]  Quit
"""


def main():
    print(_divider("═"))
    print("  NexGraph Force Recorder  –  DSF Force Sensor Logger")
    print(_divider("═"))

    rec = ForceRecorder()

    while True:
        print(f"\n{_divider()}")
        print(f"  Status : {rec.status_line()}")
        print(_divider())
        print(MENU)

        choice = input("  Choice: ").strip().lower()
        print()

        if choice == "1":
            port, force_mode, rate = _ask_connection_params()
            rec.connect(port=port, force_mode=force_mode, rate=rate)

        elif choice == "2":
            print("  Available serial ports:")
            ports = rec.list_ports()
            if ports:
                idx_or_name = input(
                    "  Enter index OR full port name: "
                ).strip()
                if idx_or_name.isdigit() and int(idx_or_name) < len(ports):
                    port = ports[int(idx_or_name)].device
                else:
                    port = idx_or_name

                mode_in = input("  Mode – [T]ension / [C]ompression (default T): ").strip().upper()
                force_mode = mode_in != "C"
                baud_in = input("  Baud rate – [H]igh / [L]ow (default H): ").strip().upper()
                rate = "low" if baud_in == "L" else "high"
                rec.connect(port=port, force_mode=force_mode, rate=rate)

        elif choice == "3":
            print("  Available serial ports:")
            ports = rec.list_ports()
            idx_or_name = input(
                "  New port – enter index OR full port name: "
            ).strip()
            if idx_or_name.isdigit() and int(idx_or_name) < len(ports):
                new_port = ports[int(idx_or_name)].device
            else:
                new_port = idx_or_name

            # Keep current force_mode and baud rate unless user wants to change
            keep = input(
                f"  Keep current settings "
                f"({'Tension' if rec._force_mode else 'Compression'}, {rec._baud_rate})? "
                "[Y/n]: "
            ).strip().upper()
            if keep == "N":
                mode_in = input("  Mode – [T]ension / [C]ompression: ").strip().upper()
                force_mode = mode_in != "C"
                baud_in = input("  Baud rate – [H]igh / [L]ow: ").strip().upper()
                rate = "low" if baud_in == "L" else "high"
            else:
                force_mode = rec._force_mode
                rate = rec._baud_rate

            rec.connect(port=new_port, force_mode=force_mode, rate=rate)

        elif choice == "4":
            rec.disconnect()

        elif choice == "5":
            rec.get_info()

        elif choice == "6":
            rec.show_current_values()

        elif choice == "7":
            rec.show_peak_values()

        elif choice == "8":
            rec.download_memory()

        elif choice == "9":
            fname = input(
                "  Output filename (Enter for auto-named): "
            ).strip()
            rec.start_recording(filename=fname or "")

        elif choice == "0":
            rec.stop_recording()

        elif choice == "s":
            rec.set_sample_interval()

        elif choice == "m":
            rec.toggle_track_peak()

        elif choice == "t":
            rec.reconnect_tension()

        elif choice == "c":
            rec.reconnect_compression()

        elif choice == "u":
            rec.change_unit()

        elif choice == "z":
            rec.send_zero()

        elif choice == "r":
            rec.send_reset()

        elif choice == "q":
            print("  Shutting down …")
            rec.disconnect()
            print("  Goodbye!")
            break

        else:
            print("  [!] Unrecognised choice.")


if __name__ == "__main__":
    main()