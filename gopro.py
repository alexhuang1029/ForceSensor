import tkinter as tk
from tkinter import messagebox, ttk
import threading
import time
from goprocam import GoProCamera, constants

class GoProControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GoPro HERO4 Controller")
        self.root.geometry("450x650")
        self.root.resizable(False, False)
        
        self.gopro = None
        self.is_recording = False
        
        self.create_widgets()
        
    def create_widgets(self):
        # --- Connection Section ---
        conn_frame = ttk.LabelFrame(self.root, text=" Connection ", padding=10)
        conn_frame.pack(fill="x", padx=15, pady=5)
        
        self.btn_connect = ttk.Button(conn_frame, text="Connect to GoPro", command=self.connect_gopro)
        self.btn_connect.pack(fill="x")
        
        self.lbl_status = tk.Label(conn_frame, text="Status: Disconnected", fg="red", font=("Arial", 10, "bold"))
        self.lbl_status.pack(pady=5)

        # --- Settings Section ---
        self.settings_frame = ttk.LabelFrame(self.root, text=" Camera Settings ", padding=10)
        self.settings_frame.pack(fill="x", padx=15, pady=5)
        
        # Video Resolution & FPS
        # For HERO4, changing resolution/fps requires sending combined or specific index commands.
        # Here we map user-friendly options to their gpControl command values.
        ttk.Label(self.settings_frame, text="Video Resolution / FPS:").pack(anchor="w", pady=2)
        self.combo_res = ttk.Combobox(self.settings_frame, state="disabled", values=[
            "1080p 60fps", 
            "1080p 30fps", 
            "4K 30fps", 
            "720p 120fps"
        ])
        self.combo_res.pack(fill="x", pady=2)
        self.combo_res.current(0)
        self.combo_res.bind("<<ComboboxSelected>>", lambda e: self.run_async(self.change_resolution))

        # White Balance (Lighting)
        ttk.Label(self.settings_frame, text="White Balance (Lighting):").pack(anchor="w", pady=2)
        self.combo_wb = ttk.Combobox(self.settings_frame, state="disabled", values=[
            "Auto", 
            "3000K (Warm/Incandescent)", 
            "5500K (Daylight)", 
            "6500K (Cool/Cloudy)", 
            "Native"
        ])
        self.combo_wb.pack(fill="x", pady=2)
        self.combo_wb.current(0)
        self.combo_wb.bind("<<ComboboxSelected>>", lambda e: self.run_async(self.change_white_balance))

        # ISO Limit
        ttk.Label(self.settings_frame, text="ISO Limit (Low Light):").pack(anchor="w", pady=2)
        self.combo_iso = ttk.Combobox(self.settings_frame, state="disabled", values=[
            "Auto", "400", "1600", "6400"
        ])
        self.combo_iso.pack(fill="x", pady=2)
        self.combo_iso.current(0)
        self.combo_iso.bind("<<ComboboxSelected>>", lambda e: self.run_async(self.change_iso))

        # --- Control Section ---
        self.control_frame = ttk.LabelFrame(self.root, text=" Camera Controls ", padding=10)
        self.control_frame.pack(fill="both", expand=True, padx=15, pady=5)
        
        mode_frame = ttk.Frame(self.control_frame)
        mode_frame.pack(pady=5, fill="x")
        
        self.btn_mode_photo = ttk.Button(mode_frame, text="Switch to Photo Mode", command=lambda: self.run_async(self.set_photo_mode), state="disabled")
        self.btn_mode_photo.pack(side="left", fill="x", expand=True, padx=2)
        
        self.btn_mode_video = ttk.Button(mode_frame, text="Switch to Video Mode", command=lambda: self.run_async(self.set_video_mode), state="disabled")
        self.btn_mode_video.pack(side="right", fill="x", expand=True, padx=2)
        
        self.btn_photo = ttk.Button(self.control_frame, text="📸 Take Photo", command=lambda: self.run_async(self.take_photo), state="disabled")
        self.btn_photo.pack(fill="x", pady=5)
        
        self.btn_video = ttk.Button(self.control_frame, text="🎥 Start Recording", command=lambda: self.run_async(self.toggle_video), state="disabled")
        self.btn_video.pack(fill="x", pady=5)
        
        self.btn_download = ttk.Button(self.control_frame, text="💾 Download Last Media", command=lambda: self.run_async(self.download_media), state="disabled")
        self.btn_download.pack(fill="x", pady=5)
        
        self.btn_power = ttk.Button(self.control_frame, text="🛑 Power Off GoPro", command=lambda: self.run_async(self.power_off), state="disabled")
        self.btn_power.pack(fill="x", pady=10)

    def run_async(self, target_func):
        thread = threading.Thread(target=target_func)
        thread.daemon = True
        thread.start()

    def connect_gopro(self):
        self.lbl_status.config(text="Status: Connecting...", fg="orange")
        self.root.update_idletasks()
        
        try:
            self.gopro = GoProCamera.GoPro(constants.gpcontrol)
            self.lbl_status.config(text="Status: Connected (HERO4)", fg="green")
            
            # Enable everything
            for widget in [self.combo_res, self.combo_wb, self.combo_iso, 
                           self.btn_mode_photo, self.btn_mode_video, 
                           self.btn_photo, self.btn_video, self.btn_download, self.btn_power]:
                widget.config(state="normal")
            
        except Exception as e:
            self.lbl_status.config(text="Status: Connection Failed", fg="red")
            messagebox.showerror("Error", f"Could not connect to GoPro.\n\n{e}")

    # --- Settings Handlers ---
    def change_resolution(self):
        selected = self.combo_res.get()
        # GoPro HERO4 API endpoints for standard setups
        if selected == "1080p 60fps":
            self.gopro.gpControlCommand("setting/2/9")  # 1080p
            self.gopro.gpControlCommand("setting/3/5")  # 60fps
        elif selected == "1080p 30fps":
            self.gopro.gpControlCommand("setting/2/9")  # 1080p
            self.gopro.gpControlCommand("setting/3/8")  # 30fps
        elif selected == "4K 30fps":
            self.gopro.gpControlCommand("setting/2/1")  # 4K
            self.gopro.gpControlCommand("setting/3/8")  # 30fps
        elif selected == "720p 120fps":
            self.gopro.gpControlCommand("setting/2/12") # 720p
            self.gopro.gpControlCommand("setting/3/1")  # 120fps

    def change_white_balance(self):
        selected = self.combo_wb.get()
        # Endpoint mapping for White Balance (Setting ID 11)
        mapping = {
            "Auto": "0",
            "3000K (Warm/Incandescent)": "1",
            "5500K (Daylight)": "2",
            "6500K (Cool/Cloudy)": "3",
            "Native": "4"
        }
        self.gopro.gpControlCommand(f"setting/11/{mapping[selected]}")

    def change_iso(self):
        selected = self.combo_iso.get()
        # Endpoint mapping for Video ISO Limit (Setting ID 13)
        mapping = {
            "Auto": "0", # Depending on mode, 0 or specific ranges apply
            "400": "2",
            "1600": "1",
            "6400": "0" 
        }
        self.gopro.gpControlCommand(f"setting/13/{mapping[selected]}")

    # --- Core Actions ---
    def set_photo_mode(self): self.gopro.mode(constants.Mode.PhotoMode)
    def set_video_mode(self): self.gopro.mode(constants.Mode.VideoMode)

    def take_photo(self):
        self.btn_photo.config(state="disabled")
        self.gopro.take_photo()
        time.sleep(1)
        self.btn_photo.config(state="normal")

    def toggle_video(self):
        if not self.is_recording:
            self.gopro.shutter(constants.Shutter.ON)
            self.is_recording = True
            self.btn_video.config(text="🛑 Stop Recording")
        else:
            self.gopro.shutter(constants.Shutter.OFF)
            self.is_recording = False
            self.btn_video.config(text="🎥 Start Recording")

    def download_media(self):
        self.lbl_status.config(text="Status: Downloading...", fg="blue")
        try:
            self.gopro.downloadLastMedia()
            messagebox.showinfo("Success", "Last media item downloaded!")
        except Exception as e:
            messagebox.showerror("Error", f"Download failed: {e}")
        self.lbl_status.config(text="Status: Connected (HERO4)", fg="green")

    def power_off(self):
        if messagebox.askyesno("Power Off", "Are you sure you want to turn off the GoPro?"):
            self.gopro.power_off()
            self.lbl_status.config(text="Status: Disconnected", fg="red")
            for widget in [self.combo_res, self.combo_wb, self.combo_iso, 
                           self.btn_mode_photo, self.btn_mode_video, 
                           self.btn_photo, self.btn_video, self.btn_download, self.btn_power]:
                widget.config(state="disabled")

if __name__ == "__main__":
    root = tk.Tk()
    app = GoProControlGUI(root)
    root.mainloop()