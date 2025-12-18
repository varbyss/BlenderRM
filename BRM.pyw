import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import threading
import requests
import sys
import os
import time
import re
import json
from collections import deque
from datetime import datetime
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None

# ====================================================================
# CONFIGURATION
# ====================================================================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

CONFIG_FILE = os.path.join(os.path.expanduser("~"), "blender_monitor_config.json")

def load_config():
    default_config = {
        "blender_path": "",
        "blend_file": "",
        "webhook_url": "",
        "last_msg_id": None,
        "use_queue": False,
        "queue_list": [],
        "auto_restart": False,
        "enable_discord": True,
        "webhook_title": "RENDERING: {filename}",
        "webhook_desc": "Frame: {frame} / {end}\nProgress: {bar} {pct}%\nAvg/Frame: {avg}\nEst. Remaining: {est}\nSession Time: {elapsed}\n{date}",
        "discord_interval": 15.0,
        "render_mode": "Multi",
        "batch_size": 0,
        "scaling": "100%",
        "enable_preview": True
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
            default_config.update(data)
            return default_config
        except: pass
    return default_config

def save_config(data):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except: pass

# ====================================================================
# TOOLTIP CLASS
# ====================================================================
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text: return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        frame = tk.Frame(tw, bg="#2b2b2b", relief="solid", borderwidth=1)
        frame.pack()
        label = tk.Label(frame, text=self.text, justify=tk.LEFT, background="#2b2b2b", foreground="#ffffff", font=("Segoe UI", 9), padx=5, pady=2)
        label.pack()

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

# ====================================================================
# MAIN APP (CustomTkinter)
# ====================================================================
class BlenderRenderApp(ctk.CTk):
    def __init__(self):
        # --- TASKBAR FIX (MUST BE FIRST) ---
        try:
            import ctypes
            myappid = 'blenderbot.monitor.v8.modern'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except: pass

        super().__init__()

        self.title("Blender Render Manager")
        self.geometry("1200x800")
        
        # --- LOGO SETUP ---
        self.ctk_logo = None
        self.temp_ico = None
        try:
            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
            else:
                base_path = os.path.abspath(os.path.dirname(__file__))
            
            logo_path = os.path.join(base_path, "512x512logo.png")
            
            if Image and os.path.exists(logo_path):
                # Load main logo for sidebar
                logo_image = Image.open(logo_path)
                self.ctk_logo = ctk.CTkImage(light_image=logo_image, dark_image=logo_image, size=(64, 64))
                
                # Create a temporary .ico file for the window/taskbar
                import tempfile
                self.temp_ico = os.path.join(tempfile.gettempdir(), "blenderbot_icon.ico")
                logo_image.save(self.temp_ico, format='ICO', sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
                
                # Apply icon using multiple methods
                self.iconbitmap(self.temp_ico)
                self.logo_photo = ImageTk.PhotoImage(logo_image)
                self.wm_iconphoto(True, self.logo_photo)
                
                # Refresh attempts
                self.after(200, lambda: self.iconbitmap(self.temp_ico))
                self.after(500, lambda: self.iconbitmap(self.temp_ico))
                self.after(1000, lambda: self.iconbitmap(self.temp_ico))
        except Exception as e:
            print(f"Error loading logo: {e}")

        self.config = load_config()
        
        # --- QUEUE STATE CLEANUP ---
        # If the app was closed/crashed during render, reset "Rendering" to "Pending"
        for item in self.config.get("queue_list", []):
            if item.get("status") == "Rendering":
                item["status"] = "Pending"
        
        self.is_rendering = False
        self.stop_event = threading.Event()
        self.render_process = None
        
        self.discord_msg_id = self.config.get("last_msg_id")
        self.global_end_frame = 0
        self.global_start_frame = 1 

        # --- LAYOUT CONFIG ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- SIDEBAR ---
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)

        if self.ctk_logo:
            self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="BlenderRenderManager", image=self.ctk_logo, compound="top", font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"))
        else:
            self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="BlenderRenderManager", font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.btn_nav_settings = ctk.CTkButton(self.sidebar_frame, text="Settings", command=lambda: self.select_frame("settings"), fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"))
        self.btn_nav_settings.grid(row=1, column=0, padx=20, pady=10)
        
        self.btn_nav_queue = ctk.CTkButton(self.sidebar_frame, text="Render Queue", command=lambda: self.select_frame("queue"), fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"))
        self.btn_nav_queue.grid(row=2, column=0, padx=20, pady=10)
        
        self.btn_nav_logs = ctk.CTkButton(self.sidebar_frame, text="Live Logs", command=lambda: self.select_frame("logs"), fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"))
        self.btn_nav_logs.grid(row=3, column=0, padx=20, pady=10)

        # Render Controls in Sidebar
        self.btn_start = ctk.CTkButton(self.sidebar_frame, text="START RENDER", command=self.start_render_thread, fg_color="#00e676", text_color="black", hover_color="#00c853")
        self.btn_start.grid(row=5, column=0, padx=20, pady=10)
        
        self.btn_stop = ctk.CTkButton(self.sidebar_frame, text="STOP", command=self.stop_render, fg_color="gray", hover_color="#b71c1c", state="disabled")
        self.btn_stop.grid(row=6, column=0, padx=20, pady=(0, 20))

        # --- MAIN FRAMES ---
        self.frame_settings = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.frame_queue = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.frame_logs = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")

        self.setup_settings_frame()
        self.setup_queue_frame()
        self.setup_logs_frame()

        self.select_frame("settings")
        
        # Final attempt to force the icon after everything is loaded
        self.after(200, self._set_window_icon)

    def _set_window_icon(self):
        try:
            if hasattr(self, 'logo_photo'):
                self.wm_iconphoto(True, self.logo_photo)
            if self.temp_ico:
                self.iconbitmap(self.temp_ico)
        except: pass

    def select_frame(self, name):
        # Reset buttons
        self.btn_nav_settings.configure(fg_color="transparent")
        self.btn_nav_queue.configure(fg_color="transparent")
        self.btn_nav_logs.configure(fg_color="transparent")

        # Hide all
        self.frame_settings.grid_forget()
        self.frame_queue.grid_forget()
        self.frame_logs.grid_forget()

        # Show selected
        if name == "settings":
            self.frame_settings.grid(row=0, column=1, sticky="nsew")
            self.btn_nav_settings.configure(fg_color=("gray75", "gray25"))
        elif name == "queue":
            self.frame_queue.grid(row=0, column=1, sticky="nsew")
            self.btn_nav_queue.configure(fg_color=("gray75", "gray25"))
        elif name == "logs":
            self.frame_logs.grid(row=0, column=1, sticky="nsew")
            self.btn_nav_logs.configure(fg_color=("gray75", "gray25"))

    # ================= UI SETUP =================
    def setup_settings_frame(self):
        f = self.frame_settings
        f.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(f, text="Configuration", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold")).grid(row=0, column=0, padx=20, pady=20, sticky="w")
        
        # Blender Path
        l_bp = ctk.CTkLabel(f, text="Blender Executable Path")
        l_bp.grid(row=1, column=0, padx=20, pady=(10,0), sticky="w")
        
        f_bp = ctk.CTkFrame(f, fg_color="transparent")
        f_bp.grid(row=2, column=0, padx=20, pady=(0,10), sticky="ew")
        self.entry_blender = ctk.CTkEntry(f_bp, placeholder_text="Path to blender.exe")
        self.entry_blender.pack(side="left", fill="x", expand=True)
        self.entry_blender.insert(0, self.config.get("blender_path", ""))
        ctk.CTkButton(f_bp, text="Browse", width=100, command=lambda: self.browse_path(self.entry_blender)).pack(side="right", padx=(10,0))

        # Webhook
        l_wh = ctk.CTkLabel(f, text="Discord Webhook URL")
        l_wh.grid(row=3, column=0, padx=20, pady=(10,0), sticky="w")
        
        self.entry_webhook = ctk.CTkEntry(f, placeholder_text="https://discord.com/api/webhooks/...")
        self.entry_webhook.grid(row=4, column=0, padx=20, pady=(0,10), sticky="ew")
        self.entry_webhook.insert(0, self.config.get("webhook_url", ""))

        # Switches
        self.switch_discord = ctk.CTkSwitch(f, text="Enable Discord Notifications")
        self.switch_discord.grid(row=5, column=0, padx=20, pady=(0,10), sticky="w")
        if self.config.get("enable_discord", True): self.switch_discord.select()
        else: self.switch_discord.deselect()

        self.switch_restart = ctk.CTkSwitch(f, text="Auto Restart on Crash")
        self.switch_restart.grid(row=6, column=0, padx=20, pady=(0,10), sticky="w")
        if self.config.get("auto_restart", False): self.switch_restart.select()
        else: self.switch_restart.deselect()
        
        # Batch Limit
        f_batch = ctk.CTkFrame(f, fg_color="transparent")
        f_batch.grid(row=7, column=0, padx=20, pady=(0,10), sticky="ew")
        
        ctk.CTkLabel(f_batch, text="Batch Limit (0=All):").pack(side="left", padx=(0,10))
        self.entry_batch = ctk.CTkEntry(f_batch, width=60)
        self.entry_batch.pack(side="left")
        self.entry_batch.insert(0, str(self.config.get("batch_size", 0)))

        # Discord Templates
        ctk.CTkLabel(f, text="Discord Templates", font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold")).grid(row=8, column=0, padx=20, pady=(20,10), sticky="w")
        
        self.entry_title = ctk.CTkEntry(f, placeholder_text="Title Template")
        self.entry_title.grid(row=9, column=0, padx=20, pady=(0,10), sticky="ew")
        self.entry_title.insert(0, self.config.get("webhook_title", ""))
        self.entry_title.bind("<KeyRelease>", self.update_preview)
        ToolTip(self.entry_title, "The title of the Discord embed message.")

        self.entry_desc = ctk.CTkTextbox(f, height=100)
        self.entry_desc.grid(row=10, column=0, padx=20, pady=(0,10), sticky="ew")
        self.entry_desc.insert("1.0", self.config.get("webhook_desc", ""))
        self.entry_desc._textbox.bind("<KeyRelease>", self.update_preview)
        ToolTip(self.entry_desc, "The body of the Discord message.\nSupports Markdown and placeholders.")
        
        # Placeholders Guide
        f_ph = ctk.CTkFrame(f, fg_color="transparent")
        f_ph.grid(row=11, column=0, padx=20, pady=(5,0), sticky="w")
        
        ctk.CTkLabel(f_ph, text="Syntax:", text_color="gray", font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0,5))
        
        placeholders = {
            "{filename}": "Name of the .blend file",
            "{frame}": "Current frame number",
            "{pct}": "Percentage complete (0-100)",
            "{bar}": "Visual progress bar",
            "{avg}": "Average render time per frame",
            "{est}": "Estimated time remaining",
            "{elapsed}": "Total elapsed session time",
            "{date}": "Current date and time",
            "{attempt}": "Current retry attempt",
            "{start}": "Start frame",
            "{end}": "End frame"
        }
        
        for ph, desc in placeholders.items():
            l = ctk.CTkLabel(f_ph, text=ph, text_color="#00e676", font=("Consolas", 11))
            l.pack(side="left", padx=3)
            ToolTip(l, desc)

        # Preview
        self.frame_preview_box = ctk.CTkFrame(f, fg_color="#36393f")
        self.frame_preview_box.grid(row=12, column=0, padx=20, pady=20, sticky="ew")
        
        self.lbl_prev_title = ctk.CTkLabel(self.frame_preview_box, text="Title", font=("Segoe UI", 14, "bold"), text_color="white")
        self.lbl_prev_title.pack(anchor="w", padx=10, pady=(10,0))
        self.lbl_prev_desc = ctk.CTkLabel(self.frame_preview_box, text="Desc", font=("Segoe UI", 12), text_color="#dcddde", justify="left")
        self.lbl_prev_desc.pack(anchor="w", padx=10, pady=(5,10))

        # Buttons
        f_btns = ctk.CTkFrame(f, fg_color="transparent")
        f_btns.grid(row=13, column=0, padx=20, pady=20, sticky="ew")
        ctk.CTkButton(f_btns, text="Save Settings", command=self.save_settings).pack(side="left", padx=(0, 10))
        ctk.CTkButton(f_btns, text="Reset Defaults", command=self.reset_defaults, fg_color="#d32f2f", hover_color="#b71c1c").pack(side="left")

        # Init Preview
        self.update_preview()

    def setup_queue_frame(self):
        f = self.frame_queue
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(f, text="Render Queue", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold")).grid(row=0, column=0, padx=20, pady=20, sticky="w")
        
        self.queue_listbox = tk.Listbox(f, bg="#2b2b2b", fg="white", selectbackground="#00e676", selectforeground="black", font=("Segoe UI", 12), relief="flat")
        self.queue_listbox.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        
        f_btns = ctk.CTkFrame(f, fg_color="transparent")
        f_btns.grid(row=2, column=0, padx=20, pady=20, sticky="ew")
        
        ctk.CTkButton(f_btns, text="Add File", command=self.add_to_queue).pack(side="left", padx=5)
        ctk.CTkButton(f_btns, text="Remove", command=self.remove_from_queue, fg_color="#555").pack(side="left", padx=5)
        ctk.CTkButton(f_btns, text="Move Up", command=lambda: self.move_queue(-1), fg_color="#555").pack(side="left", padx=5)
        ctk.CTkButton(f_btns, text="Move Down", command=lambda: self.move_queue(1), fg_color="#555").pack(side="left", padx=5)
        
        # Populate UI on startup
        self.update_queue_ui()

    def setup_logs_frame(self):
        f = self.frame_logs
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=3) # Logs get more space
        f.grid_rowconfigure(3, weight=2) # Preview gets some space
        
        # Header and Toggle
        header_frame = ctk.CTkFrame(f, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        
        ctk.CTkLabel(header_frame, text="Live Logs & Preview", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold")).pack(side="left")
        
        self.check_preview = ctk.CTkCheckBox(header_frame, text="Enable Preview", command=self.toggle_preview_ui)
        self.check_preview.pack(side="right", padx=10)
        if self.config.get("enable_preview", True): self.check_preview.select()
        else: self.check_preview.deselect()
        
        # Logs Box
        self.log_box = ctk.CTkTextbox(f, font=("Consolas", 12))
        self.log_box.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.log_box.configure(state="disabled")
        
        # Preview Area (Scrollable to prevent layout breakage)
        self.preview_container = ctk.CTkScrollableFrame(f, height=300, fg_color="#1a1a1a", corner_radius=5)
        self.preview_container.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")
        
        self.lbl_image_preview = ctk.CTkLabel(self.preview_container, text="No Render Yet", fg_color="transparent")
        self.lbl_image_preview.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Footer
        footer_frame = ctk.CTkFrame(f, fg_color="transparent")
        footer_frame.grid(row=4, column=0, padx=20, pady=(10, 20), sticky="ew")
        
        ctk.CTkButton(footer_frame, text="Open Output Folder", command=self.open_output).pack(side="left")
        
        # Initial UI State
        self.toggle_preview_ui()

    def toggle_preview_ui(self):
        enabled = self.check_preview.get()
        self.config["enable_preview"] = bool(enabled)
        save_config(self.config)
        
        if not enabled:
            self.lbl_image_preview.configure(image=None, text="Preview Disabled")
            self.preview_container.grid_remove()
        else:
            self.preview_container.grid()
            if not self.lbl_image_preview.cget("image"):
                self.lbl_image_preview.configure(text="Waiting for render...")

    # ================= LOGIC =================
    def save_settings(self):
        self.config["blender_path"] = self.entry_blender.get()
        self.config["webhook_url"] = self.entry_webhook.get()
        self.config["enable_discord"] = self.switch_discord.get()
        self.config["webhook_title"] = self.entry_title.get()
        self.config["webhook_desc"] = self.entry_desc.get("1.0", "end-1c")
        self.config["auto_restart"] = self.switch_restart.get()
        try: self.config["batch_size"] = int(self.entry_batch.get())
        except: self.config["batch_size"] = 0
        save_config(self.config)
        self.show_notification("Settings Saved!")

    def reset_defaults(self):
        if messagebox.askyesno("Reset", "Reset all settings to defaults?"):
            self.config = load_config()
            self.entry_blender.delete(0, "end"); self.entry_blender.insert(0, self.config.get("blender_path", ""))
            self.entry_webhook.delete(0, "end"); self.entry_webhook.insert(0, self.config.get("webhook_url", ""))
            if self.config.get("enable_discord", True): self.switch_discord.select()
            else: self.switch_discord.deselect()
            if self.config.get("auto_restart", False): self.switch_restart.select()
            else: self.switch_restart.deselect()
            self.entry_batch.delete(0, "end"); self.entry_batch.insert(0, str(self.config.get("batch_size", 0)))
            self.entry_title.delete(0, "end"); self.entry_title.insert(0, self.config.get("webhook_title", ""))
            self.entry_desc.delete("1.0", "end"); self.entry_desc.insert("1.0", self.config.get("webhook_desc", ""))
            self.update_preview()
            self.show_notification("Settings Reset!", "#ffab00")

    def browse_path(self, entry_widget):
        path = filedialog.askopenfilename(filetypes=[("Executables", "*.exe"), ("All Files", "*.*")])
        if path:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, path)

    def add_to_queue(self):
        files = filedialog.askopenfilenames(filetypes=[("Blender Files", "*.blend")])
        if files:
            for f in files:
                self.config["queue_list"].append({"path": f, "status": "Pending"})
            save_config(self.config)
            self.update_queue_ui()

    def update_queue_ui(self):
        self.queue_listbox.delete(0, "end")
        for item in self.config["queue_list"]:
            status = item.get("status", "Pending")
            icon = "⏳" if status == "Pending" else "🟢" if status == "Rendering" else "✅" if status == "Done" else "❌"
            self.queue_listbox.insert("end", f"{icon} {os.path.basename(item['path'])} [{status}]")

    def update_preview(self, event=None):
        title = self.entry_title.get()
        desc = self.entry_desc.get("1.0", "end-1c")
        
        mock = {
            "filename": "ProjectName.blend",
            "attempt": "1",
            "start": "1",
            "end": "425",
            "frame": "4",
            "avg": "25.9s",
            "est": "03h 02m 00s",
            "pct": "0",
            "bar": "░░░░░░░░░░░░░░░",
            "elapsed": "00h 01m 17s",
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        try: title = title.format(**mock)
        except: pass
        try: desc = desc.format(**mock)
        except: pass
        
        self.lbl_prev_title.configure(text=title)
        self.lbl_prev_desc.configure(text=desc)

    def remove_from_queue(self):
        sel = self.queue_listbox.curselection()
        if sel:
            del self.config["queue_list"][sel[0]]
            save_config(self.config)
            self.update_queue_ui()

    def move_queue(self, d):
        sel = self.queue_listbox.curselection()
        if not sel: return
        i = sel[0]
        ni = i + d
        if 0 <= ni < len(self.config["queue_list"]):
            self.config["queue_list"][i], self.config["queue_list"][ni] = self.config["queue_list"][ni], self.config["queue_list"][i]
            save_config(self.config)
            self.update_queue_ui()
            self.queue_listbox.selection_set(ni)

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def open_output(self):
        path = ""
        if self.config["queue_list"]: path = self.config["queue_list"][0]["path"]
        if path and os.path.exists(os.path.dirname(path)):
            os.startfile(os.path.dirname(path))

    def update_image_preview(self, image_path):
        if not self.config.get("enable_preview", True): return
        try:
            if not image_path.lower().endswith(('.png', '.gif', '.ppm', '.pgm', '.jpg', '.jpeg')): return 
            
            # Use PIL if available for better quality
            if Image:
                pil_img = Image.open(image_path)
                # Calculate aspect ratio
                w, h = pil_img.size
                max_w, max_h = self.frame_logs.winfo_width() - 40, self.frame_logs.winfo_height() - 200
                if max_w < 100: max_w = 600
                if max_h < 100: max_h = 400
                
                ratio = min(max_w/w, max_h/h)
                new_w, new_h = int(w*ratio), int(h*ratio)
                
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(new_w, new_h))
                self.lbl_image_preview.configure(image=ctk_img, text="")
                self.lbl_image_preview.image = ctk_img # Keep reference
            else:
                # Fallback to subsample
                img = tk.PhotoImage(file=image_path)
                w, h = img.width(), img.height()
                if w > 600:
                    factor = int(w / 600)
                    if factor > 1: img = img.subsample(factor, factor)
                self.lbl_image_preview.configure(image=img, text="")
                self.lbl_image_preview.image = img 
        except Exception as e: 
            print(f"Preview Error: {e}")

    def start_render_thread(self):
        self.save_settings()
        if not self.config["queue_list"]:
            messagebox.showerror("Error", "Queue is empty! Add files in Render Queue tab.")
            return
        
        self.is_rendering = True
        self.stop_event.clear()
        self.btn_start.configure(state="disabled", fg_color="gray")
        self.btn_stop.configure(state="normal", fg_color="#d32f2f")
        self.select_frame("logs")
        self.log("--- STARTING RENDER ---")
        
        threading.Thread(target=self.render_loop, daemon=True).start()

    def stop_render(self):
        if self.is_rendering:
            self.stop_event.set()
            if self.render_process: self.render_process.terminate()
            self.log("!!! STOPPING !!!")

    def render_loop(self):
        blender_path = self.config["blender_path"]
        webhook_url = self.config["webhook_url"]
        
        mode = self.config.get("render_mode", "Multi")
        batch_size = self.config.get("batch_size", 0)
        processed_count = 0
        
        for i, item in enumerate(self.config["queue_list"]):
            if self.stop_event.is_set(): break
            
            # Check Batch Limit
            if batch_size > 0 and processed_count >= batch_size: break
            
            if item.get("status") == "Done": continue # Skip already done
            
            blend_file = item["path"]
            self.log(f"\n=== STARTING PROJECT {i+1}: {os.path.basename(blend_file)} ===")
            
            # Update Status to Rendering
            self.config["queue_list"][i]["status"] = "Rendering"
            save_config(self.config)
            self.after(0, self.update_queue_ui)
            
            self.discord_msg_id = None
            try:
                project_start_f, end_f, output_path = self.get_blender_settings(blender_path, blend_file)
                self.global_start_frame = project_start_f 
                self.global_end_frame = end_f
                current_start = self.find_last_rendered_frame(output_path, project_start_f, end_f)
                attempt = 1
                max_attempts = 5 if self.config.get("auto_restart", False) else 1
                
                # Check if already finished
                if current_start > end_f:
                    self.log("All frames found. Marking as Done.")
                    self.config["queue_list"][i]["status"] = "Done"
                    processed_count += 1
                    save_config(self.config)
                    self.after(0, self.update_queue_ui)
                    continue

                success = False
                while current_start <= end_f and not self.stop_event.is_set():
                    self.log(f"\n--- Batch: Frame {current_start} to {end_f} (Attempt {attempt}) ---")
                    success, last_frame = self.run_blender_process(blender_path, blend_file, current_start, end_f, webhook_url, attempt)
                    
                    if self.stop_event.is_set(): break
                    if success:
                        self.log("Sequence Finished Successfully.")
                        self.config["queue_list"][i]["status"] = "Done"
                        processed_count += 1
                        save_config(self.config)
                        break
                    else:
                        self.log_crash(f"Crash at frame {last_frame}", last_frame, blend_file)
                        if attempt < max_attempts:
                            self.log(f"Auto-Restarting in 5s... (Attempt {attempt}/{max_attempts})")
                            current_start = last_frame + 1
                            if current_start > end_f: current_start = end_f  
                            attempt += 1
                            time.sleep(5)
                        else:
                            self.log("Max attempts reached. Moving to next project.")
                            self.config["queue_list"][i]["status"] = "Failed"
                            processed_count += 1
                            save_config(self.config)
                            break
            except Exception as e:
                self.log(f"CRITICAL ERROR: {e}")
                self.log_crash(str(e), 0, blend_file)
                self.config["queue_list"][i]["status"] = "Failed"
                processed_count += 1
                save_config(self.config)
            
            self.after(0, self.update_queue_ui)

        self.is_rendering = False
        self.btn_start.configure(state="normal", fg_color="#00e676")
        self.btn_stop.configure(state="disabled", fg_color="gray")
        self.log("--- ALL DONE ---")

    def get_blender_settings(self, blender_path, blend_file):
        self.log("Reading settings...")
        expr = "import bpy, json; s=bpy.context.scene; print(json.dumps({'s':s.frame_start,'e':s.frame_end,'o':s.render.filepath}))"
        cmd = [blender_path, "-b", blend_file, "--python-expr", expr]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            match = re.search(r'\{.*\}', res.stdout, re.DOTALL) 
            if match:
                d = json.loads(match.group(0))
                self.log(f"Detected: Start {d['s']}, End {d['e']}")
                return d['s'], d['e'], d['o']
        except Exception as e: self.log(f"Error reading settings: {e}")
        return 1, 250, "//" 

    def find_last_rendered_frame(self, output_path, start, end):
        d = os.path.dirname(output_path) or os.getcwd()
        if output_path.startswith("//"): d = os.path.dirname(self.config["queue_list"][0]["path"]) or os.getcwd()
        if not os.path.exists(d): return start
        
        max_frame = start - 1
        base_name_pattern = re.escape(os.path.basename(output_path).split('#')[0] if '#' in os.path.basename(output_path) else '')
        
        for f in os.listdir(d):
            if f.endswith(('.png', '.jpg', '.exr', '.tif', '.tga')):
                if base_name_pattern and not f.startswith(base_name_pattern): continue
                m = re.findall(r'(\d+)', f)
                if m:
                    frame_num = int(m[-1])
                    if start <= frame_num <= end: max_frame = max(max_frame, frame_num)
        
        n = max_frame + 1
        return n

    def log_crash(self, error, frame, project):
        try:
            with open("crashlog.txt", "a") as f:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] Project: {project} | Frame: {frame} | Error: {error}\n")
        except: pass

    def run_blender_process(self, blender_path, blend_file, start_frame, end_frame, webhook_url, attempt_num):
        cmd = [blender_path, "-b", blend_file, "-s", str(start_frame), "-e", str(end_frame), "-a"]
        self.render_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', bufsize=1)

        current_display_frame = start_frame
        finished_frame = None
        job_start_time = time.time()
        frame_render_times = deque(maxlen=10)
        last_frame_finish_time = time.time() 
        last_discord_update = 0

        title_text = self.config.get("webhook_title", "Rendering").format(filename=os.path.basename(blend_file))
        # Initial send
        self.discord_msg_id = self.send_discord(webhook_url, title_text, "Starting...", 16776960)
        self.config["last_msg_id"] = self.discord_msg_id
        save_config(self.config)

        def do_discord_update():
            nonlocal last_discord_update
            avg_time = sum(frame_render_times) / len(frame_render_times) if frame_render_times else 0
            elapsed_job = time.time() - job_start_time
            ref_frame = finished_frame if finished_frame is not None else start_frame - 1
            frames_left = max(0, self.global_end_frame - ref_frame)
            rem_seconds = avg_time * frames_left
            
            est_str = time.strftime('%Hh %Mm %Ss', time.gmtime(rem_seconds)) if avg_time > 0 else "Calculating..."
            elapsed_str = time.strftime('%Hh %Mm %Ss', time.gmtime(elapsed_job))
            avg_str = f"{avg_time:.1f}s" if avg_time > 0 else "..."
            
            total_range = self.global_end_frame - self.global_start_frame + 1 
            current_done = (ref_frame - self.global_start_frame + 1)
            pct = min(1.0, max(0.0, current_done / total_range)) if total_range > 0 else 0
            bar = "█" * int(15 * pct) + "░" * (15 - int(15 * pct))

            display_frame_num = ref_frame + 1 if ref_frame < self.global_end_frame else self.global_end_frame
            
            desc_tmpl = self.config.get("webhook_desc", "")
            try:
                desc = desc_tmpl.format(
                    filename=os.path.basename(blend_file),
                    attempt=attempt_num,
                    start=self.global_start_frame,
                    end=self.global_end_frame,
                    frame=display_frame_num,
                    avg=avg_str,
                    est=est_str,
                    bar=bar,
                    pct=int(pct*100),
                    elapsed=elapsed_str,
                    date=datetime.now().strftime("%d.%m.%Y %H:%M")
                )
            except: desc = "Error formatting template"
            
            self.send_discord(webhook_url, title_text, desc, 4309328, patch_id=self.discord_msg_id)
            last_discord_update = time.time()

        while self.render_process.poll() is None:
            if self.stop_event.is_set():
                self.render_process.terminate()
                return False, current_display_frame

            try:
                line = self.render_process.stdout.readline()
                if not line: continue
                line = line.strip()
            except: continue

            if "ModuleNotFoundError" in line or "addon" in line.lower(): continue
            if "Fra:" in line or "Saved:" in line or "Error" in line:
                self.log(line)

            match_fra = re.search(r"(?:Fra:|Frame:|Frame)\s*(\d+)", line, re.IGNORECASE)
            if match_fra: current_display_frame = int(match_fra.group(1))

            match_saved = re.search(r"Saved:.*[\/\\](\d+)\.\w+['\"]", line, re.IGNORECASE)
            if match_saved:
                finished_frame = int(match_saved.group(1))
                current_display_frame = finished_frame 
                now = time.time()
                duration = now - last_frame_finish_time
                last_frame_finish_time = now
                if duration > 0.1: frame_render_times.append(duration)
                
                saved_path_match = re.search(r"Saved:\s*['\"](.*?)['\"]", line, re.IGNORECASE)
                if saved_path_match:
                    saved_path = saved_path_match.group(1)
                    if not os.path.isabs(saved_path): saved_path = os.path.join(os.path.dirname(blend_file), saved_path)
                    self.after(0, lambda p=saved_path: self.update_image_preview(p))

                if time.time() - last_discord_update > self.config.get("discord_interval", 15.0):
                    do_discord_update()

            elif time.time() - last_discord_update > self.config.get("discord_interval", 15.0):
                do_discord_update()

        return_code = self.render_process.returncode
        result_frame = finished_frame if finished_frame is not None else current_display_frame 
        
        if return_code == 0:
            self.send_discord(webhook_url, "✅ RENDER COMPLETE", f"Job finished up to frame {result_frame}", 65280, patch_id=self.discord_msg_id)
            self.config["last_msg_id"] = None; save_config(self.config)
            return True, result_frame
        else:
            self.send_discord(webhook_url, "🔴 RENDER CRASHED", f"Process died. Last frame saved: {result_frame}", 16711680, patch_id=self.discord_msg_id)
            return False, result_frame

    def send_discord(self, url, title, desc, color, patch_id=None):
        if not self.config.get("enable_discord", True): return None
        if not url: return None
        data = {"embeds": [{"title": title, "description": desc, "color": color, "timestamp": datetime.utcnow().isoformat() + "Z"}]}
        try:
            if patch_id:
                r = requests.patch(f"{url}/messages/{patch_id}", json=data)
                if r.status_code == 404: return None 
                return patch_id
            else:
                r = requests.post(f"{url}?wait=true", json=data)
                r.raise_for_status() 
                return r.json().get('id')
        except: return None

    def show_notification(self, message, color="#00e676"):
        # Create notification frame
        f = ctk.CTkFrame(self, fg_color=color, corner_radius=10, height=40)
        f.place(relx=1.2, rely=0.05, anchor="e") # Start off-screen right
        
        l = ctk.CTkLabel(f, text=message, text_color="black", font=("Segoe UI", 12, "bold"))
        l.pack(padx=20, pady=10)
        
        # Dismiss on click
        f.bind("<Button-1>", lambda e: f.destroy())
        l.bind("<Button-1>", lambda e: f.destroy())
        
        # Animation
        def animate_in(current_x):
            if current_x > 0.98:
                current_x -= 0.02
                f.place(relx=current_x, rely=0.05, anchor="e")
                self.after(10, lambda: animate_in(current_x))
            else:
                # Auto-hide after 3 seconds
                self.after(3000, animate_out)
        
        def animate_out():
            try:
                current_x = float(f.place_info()['relx'])
                if current_x < 1.2:
                    current_x += 0.02
                    f.place(relx=current_x, rely=0.05, anchor="e")
                    self.after(10, animate_out)
                else:
                    f.destroy()
            except: pass

        animate_in(1.2)

if __name__ == "__main__":
    app = BlenderRenderApp()
    app.mainloop()
