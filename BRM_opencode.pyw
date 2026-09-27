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
import shutil
import tempfile
from collections import deque
from datetime import datetime
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
try:
    import psutil
except ImportError:
    psutil = None
try:
    import brm_blendparse
except ImportError:
    brm_blendparse = None
try:
    import brm_theme as TH
    TH.fonts_ready()
except ImportError:
    TH = None
from concurrent.futures import ThreadPoolExecutor

# ====================================================================
# CONFIGURATION
# ====================================================================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = os.path.join(os.path.expanduser("~"), "blender_monitor_config.json")
HISTORY_FILE = os.path.join(os.path.expanduser("~"), "blender_monitor_history.json")

# Design system (brm_theme.py = palette, type, drawn icons). C_* aliases stay
# so backend code is untouched.
if TH is None:
    C_BG = "#0b0b0b"; C_PANEL = "#111111"; C_ROW = "#181818"
    C_ACCENT = "#4d80f0"; C_ACCENT_HOVER = "#3d6cd6"; C_ACCENT2 = "#6b96f7"
    C_GREEN = "#3ecf8e"; C_RED = "#f05151"; C_YELLOW = "#f0b429"
    C_GRAY_TXT = "#888888"; C_FAINT = "#444444"; C_ENTRY = "#181818"
    C_LINE = "#2a2a2a"; C_LINE2 = "#353535"; C_HOVER = "#202020"; C_TXT = "#d8d8d8"
    F_TITLE = ("Segoe UI", 15, "bold"); F_HEAD = ("Segoe UI", 11, "bold")
    F_BODY = ("Segoe UI", 12); F_SMALL = ("Segoe UI", 11); F_MONO = ("Consolas", 10)
    F_MONO_SM = ("Consolas", 9); F_LABEL_SM = ("Segoe UI", 9, "bold")
    APP_VERSION = "3.0.0"
else:
    C_BG = TH.BG; C_PANEL = TH.S1; C_ROW = TH.S2
    C_ACCENT = TH.ORANGE; C_ACCENT_HOVER = "#3d6cd6"; C_ACCENT2 = TH.ORANGE2
    C_GREEN = TH.GREEN; C_RED = TH.RED; C_YELLOW = TH.AMBER
    C_GRAY_TXT = TH.DIM; C_FAINT = TH.FAINT; C_ENTRY = TH.S2
    C_LINE = TH.LINE; C_LINE2 = TH.LINE2; C_HOVER = TH.S3; C_TXT = TH.TEXT
    F_TITLE = TH.F_UI_TITLE; F_HEAD = TH.F_LABEL
    F_BODY = TH.F_BODY; F_SMALL = TH.F_SMALL; F_MONO = TH.F_MONO
    F_MONO_SM = ("Source Code Pro", 9); F_LABEL_SM = TH.F_LABEL_SM
    APP_VERSION = TH.APP_VERSION

# ---- design language: one spacing scale, square corners ----
PAD = 12        # outer padding of panels
GAP = 8         # gaps between controls
SEC_GAP = 10    # space between sections
RADIUS = 0      # hard edges everywhere
ROW_H = 28      # queue row height
BTN_H = 28      # standard button height
SET_H = 36          # settings-window widget height (roomier per request)
F_SET = ("Barlow", 13)
F_SET_MONO = ("Source Code Pro", 12)
F_SET_HEAD = ("Barlow Condensed", 14, "bold")

ENGINES = ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES", "WORKBENCH"]
FILE_FORMATS = ["PNG", "JPEG", "OPEN_EXR", "TIFF", "BMP", "TARGA"]
COLOR_MODES = ["BW", "RGB", "RGBA"]
OUTPUT_VARS = ["{camera_name}", "{scene_name}"]

DEFAULT_CONFIG = {
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
    "webhook_start_desc": "Scene: {scene} | Camera: {camera} | Frames: {start}-{end}\nStarting attempt {attempt}...",
    "webhook_done_title": "✅ RENDER COMPLETE: {filename}",
    "webhook_done_desc": "Scene: {scene}\nCamera: {camera}\nFrames: {start}-{end} (finished {frame})\nDuration: {duration}",
    "webhook_crash_title": "🔴 RENDER CRASHED: {filename}",
    "webhook_crash_desc": "Scene: {scene}\nCamera: {camera}\nFrames: {start}-{end}\nLast frame saved: {frame}\nAttempt: {attempt}",
    "webhook_stop_title": "⏸ RENDER STOPPED: {filename}",
    "webhook_stop_desc": "Scene: {scene}\nCamera: {camera}\nFrames: {start}-{end}\nStopped at frame {frame}",
    "discord_interval": 15.0,
    "render_mode": "Multi",
    "batch_size": 0,
    "scaling": "100%",
    "auto_full_probe": True,
    "quiet_mode": True,
    "filter_noisy_cycles_lines": True,
    "show_blender_console": False,
    "max_retries": 5,
    "retry_delay": 5.0,
    "finish_sound": True,
    "ffmpeg_path": "",
    "ffmpeg_fps": 60,
    "ffmpeg_crf": 12,
    "on_complete": "Do nothing",
    "gui_for_hurricane": True,
    "blender_version": "",
    "viewport_visible": True,
    "layout": {"left": ["queue"], "center": ["view"], "right": ["props"],
               "bottom": ["prog", "log"]},
    "layout_active": {},
    "layout_hidden": [],
    "layout_split": {},
    "layout_sizes": {"left": 280, "right": 256, "bottom": 0},
    "geometry": "",
    "selected_path": "",
    "queue_scroll": 0.0,
}

# ---- dockable layout: 5 panels, 4 slots (left/center/right/bottom) ----
# Side slots stack their panels vertically, the bottom slot lays them out
# horizontally. Every slot always keeps at least one panel.
PANELS = ("queue", "view", "prog", "props", "log")
SLOTS = ("left", "center", "right", "bottom")
PANEL_TITLES = {"queue": "QUEUE", "view": "VIEWPORT", "prog": "PROGRESS",
                "props": "PROPERTIES", "log": "LOG"}
DEFAULT_LAYOUT = {"left": ["queue"], "center": ["view"], "right": ["props"],
                  "bottom": ["prog", "log"]}
DEFAULT_LAYOUT_SIZES = {"left": 280, "right": 256}
LAYOUT_PRESETS = {
    "Default": {"left": ["queue"], "center": ["view"], "right": ["props"],
                "bottom": ["prog", "log"]},
    "Viewport left": {"left": ["view"], "center": ["queue"], "right": ["props"],
                      "bottom": ["prog", "log"]},
    "Log right": {"left": ["queue"], "center": ["view"], "right": ["log"],
                  "bottom": ["prog", "props"]},
}

QUEUE_ITEM_DEFAULTS = {
    "path": "",
    "status": "Pending",
    "enabled": True,
    "scene": None,
    "camera": None,
    "view_layer": None,
    "engine": None,
    "samples": None,
    "res_x": None,
    "res_y": None,
    "res_pct": None,
    "film_transparent": None,
    "overwrite": None,
    "placeholder": None,
    "file_format": None,
    "color_mode": None,
    "color_depth": None,
    "compression": None,
    "frame_start": None,
    "frame_end": None,
    "output": None,
    "fps": None,
    "python_args": "",
    "gui_mode": None,
    "hurricane": False,
    "probe": None,
    "last_duration": None,
    "current_frame": None,
    "total_frames": None,
    "last_frame_path": None,
    "converted_mp4": None,
    "ov": {"res_x": False, "res_y": False, "scale": False, "overwrite": False, "placeholder": False},
}


def migrate_queue_item(item):
    """Ensure a queue dict has all known keys (backward compatible with old configs)."""
    if not isinstance(item, dict):
        return dict(QUEUE_ITEM_DEFAULTS, path=str(item), ov=dict(QUEUE_ITEM_DEFAULTS["ov"]))
    out = dict(QUEUE_ITEM_DEFAULTS)
    out["ov"] = dict(QUEUE_ITEM_DEFAULTS["ov"])
    for k, v in item.items():
        if k == "ov" and isinstance(v, dict):
            out["ov"].update(v)
        else:
            out[k] = v
    return out


def load_config():
    default_config = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
            default_config.update(data)
            return default_config
        except Exception:
            pass
    return default_config


def save_config(data):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass


def autodetect_blender():
    """Best-effort Blender location (first run with no path set)."""
    try:
        import glob
        cands = [r"E:\Client\Steam\steamapps\common\Blender\blender.exe"]
        try:
            cands.append(shutil.which("blender") or "")
        except Exception:
            pass
        cands += sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"),
                        reverse=True)
        cands += sorted(glob.glob(r"D:\SteamLibrary\steamapps\common\Blender\blender.exe"))
        for c in cands:
            try:
                if c and os.path.exists(c):
                    return c
            except Exception:
                continue
    except Exception:
        pass
    return None


def play_finish_sound():
    """Soft single system tap (Windows ding, terminal bell elsewhere)."""
    try:
        if os.name == "nt":
            import winsound
            try:
                winsound.MessageBeep(winsound.MB_OK)
            except Exception:
                winsound.Beep(880, 160)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass


def _validate_geometry(g, sw, sh):
    """'WxH+X+Y' sanity + clamp into the screen. Returns cleaned string or None."""
    try:
        import re
        m = re.match(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$", (g or "").strip())
        if not m:
            return None
        w, h, x, y = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        if w < 400 or h < 300:
            return None
        w, h = min(w, int(sw)), min(h, int(sh))
        x = min(max(x, -w + 120), int(sw) - 120)
        y = min(max(y, 0), int(sh) - 120)
        return "{}x{}+{}+{}".format(w, h, x, y)
    except Exception:
        return None


def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def save_history(items):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(items[-500:], f, indent=2)
    except Exception:
        pass


def log_history(entry):
    try:
        items = load_history()
        items.append(entry)
        save_history(items)
    except Exception:
        pass


def ffmpeg_exe(configured=""):
    """Resolve ffmpeg binary path: explicit setting -> PATH -> common install dir."""
    if configured and os.path.exists(configured):
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    for cand in (r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"):
        if os.path.exists(cand):
            return cand
    return None


def resolve_output_dir(output_path, blend_path):
    """Resolve a Blender output path (may contain // or ####) to an absolute folder."""
    blend_dir = os.path.dirname(os.path.abspath(blend_path)) if blend_path else os.getcwd()
    p = (output_path or "").strip() or blend_dir
    if p.startswith("//"):
        p = os.path.join(blend_dir, p[2:])
    elif not os.path.isabs(p):
        p = os.path.join(blend_dir, p)
    p = os.path.normpath(p)
    base = os.path.basename(p)
    if "#" in base or os.path.splitext(base)[1] != "":
        p = os.path.dirname(p)
    return p


def expand_output_vars(output_path, scene=None, camera=None):
    out = output_path or ""
    out = out.replace("{scene_name}", scene or "")
    out = out.replace("{camera_name}", camera or "")
    return out


def find_png_sequence(folder):
    """Inspect a folder with rendered PNGs. Returns dict or None."""
    try:
        files = [f for f in os.listdir(folder) if f.lower().endswith(".png")]
    except Exception:
        return None
    if not files:
        return None
    groups = {}
    for f in files:
        m = re.match(r"^(.*?)(\d+)\.png$", f, re.IGNORECASE)
        if not m:
            continue
        prefix, digits = m.group(1), m.group(2)
        groups.setdefault(prefix, []).append((int(digits), len(digits), f))
    if not groups:
        return None
    prefix = max(groups.keys(), key=lambda k: len(groups[k]))
    entries = sorted(groups[prefix])
    width = entries[0][1]
    return {
        "pattern": "%0{}d.png".format(width),
        "pattern_prefixed": "{}%0{}d.png".format(prefix, width),
        "prefix": prefix,
        "start": entries[0][0],
        "width": width,
        "count": len(entries),
        "files": [e[2] for e in entries],
    }


def build_ffmpeg_command(ffmpeg, folder, pattern, start, fps, crf, mp4_path):
    """Build the ffmpeg command list (mirrors the user's .bat workflow)."""
    return [
        ffmpeg, "-y",
        "-start_number", str(start),
        "-framerate", str(fps),
        "-i", pattern,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-pix_fmt", "yuv444p",
        "-colorspace", "bt709",
        "-color_trc", "bt709",
        "-color_primaries", "bt709",
        mp4_path,
    ]


def parse_probe_output(text):
    """Extract probe JSON between sentinels. Falls back to legacy bare-{...} parse."""
    if not text:
        return None
    m = re.search(r"@@BRM_PROBE_BEGIN@@\s*(\{.*?\})\s*@@BRM_PROBE_END@@", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def parse_frames_text(text, default_start=None, default_end=None):
    """Parse '1-20' / '1:20' / '15' into (start, end)."""
    t = (text or "").strip().replace(" ", "")
    if not t:
        return default_start, default_end
    m = re.match(r"^(\d+)\s*[-:;]+\s*(\d+)$", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (a, b) if a <= b else (b, a)
    m = re.match(r"^(\d+)$", t)
    if m:
        return int(m.group(1)), int(m.group(1))
    return default_start, default_end


def describe_item(item):
    """One-line summary (logs / fallback)."""
    status = item.get("status", "Pending")
    icon = ("P" if status == "Pending" else "R" if status == "Rendering"
            else "D" if status == "Done" else "S" if status == "Stopped" else "F")
    name = os.path.basename(item.get("path", "?"))
    parts = ["{} {} [{}]".format(icon, name, status)]
    if item.get("scene"):
        parts.append("Scene:{}".format(item["scene"]))
    if item.get("camera"):
        parts.append("Cam:{}".format(item["camera"]))
    if item.get("res_pct"):
        parts.append("{}%".format(item["res_pct"]))
    fs, fe = item.get("frame_start"), item.get("frame_end")
    if fs is not None or fe is not None:
        parts.append("F:{}-{}".format(fs if fs is not None else "?", fe if fe is not None else "?"))
    if item.get("hurricane"):
        parts.append("(sim)")
    if item.get("gui_mode"):
        parts.append("(GUI)")
    return " | ".join(parts)


def status_text(item):
    s = item.get("status", "Pending")
    if s == "Done":
        d = item.get("last_duration")
        return "Done in {}".format(d) if d else "Done"
    if s == "Rendering":
        cf = item.get("current_frame")
        return "Rendering frame {}".format(cf) if cf else "Rendering"
    if s == "Failed":
        return "Failed"
    if s == "Stopped":
        return "Stopped"
    return "Ready"


# ====================================================================
# BLENDER HELPER SCRIPTS (run inside Blender via --python)
# ====================================================================
PROBE_SCRIPT = r"""
import bpy, json, os
info = {"active": None, "scenes": [], "hurricane": False, "hurricane_objects": [], "missing": [], "missing_count": 0}
try:
    info["active"] = bpy.context.scene.name if bpy.context.scene else None
except Exception:
    pass
try:
    for sc in bpy.data.scenes:
        cams = []
        try:
            cams = [o.name for o in sc.objects if o.type == 'CAMERA']
        except Exception:
            pass
        try:
            fps_base = float(sc.render.fps_base) if sc.render.fps_base else 1.0
            fps = float(sc.render.fps) / fps_base
        except Exception:
            fps = 24.0
        try:
            fmt = sc.render.image_settings.file_format
        except Exception:
            fmt = ""
        try:
            cmode = sc.render.image_settings.color_mode
        except Exception:
            cmode = ""
        try:
            cdepth = sc.render.image_settings.color_depth
        except Exception:
            cdepth = ""
        try:
            compr = int(sc.render.image_settings.compression)
        except Exception:
            compr = 15
        try:
            vls = [vl.name for vl in sc.view_layers]
        except Exception:
            vls = []
        try:
            samples = int(sc.cycles.samples)
        except Exception:
            samples = 0
        try:
            esamples = int(sc.eevee.taa_render_samples)
        except Exception:
            esamples = 0
        try:
            film = bool(sc.render.film_transparent)
        except Exception:
            film = False
        info["scenes"].append({
            "name": sc.name,
            "frame_start": int(sc.frame_start),
            "frame_end": int(sc.frame_end),
            "fps": fps,
            "camera": sc.camera.name if sc.camera else None,
            "cameras": cams,
            "view_layers": vls,
            "engine": sc.render.engine,
            "samples": samples,
            "eevee_samples": esamples,
            "res_x": int(sc.render.resolution_x),
            "res_y": int(sc.render.resolution_y),
            "res_pct": int(sc.render.resolution_percentage),
            "film_transparent": film,
            "use_overwrite": bool(sc.render.use_overwrite),
            "use_placeholder": bool(sc.render.use_placeholder),
            "output": sc.render.filepath,
            "file_format": fmt,
            "color_mode": cmode,
            "color_depth": str(cdepth),
            "compression": compr,
        })
except Exception as e:
    info["error"] = str(e)
try:
    for o in bpy.data.objects:
        try:
            names = [m.name for m in getattr(o, "modifiers", [])] if hasattr(o, "modifiers") else []
        except Exception:
            names = []
        hit = False
        try:
            if o.get("hurr_original_mesh_deform"):
                hit = True
        except Exception:
            pass
        for n in names:
            if "hurricane" in n.lower():
                hit = True
                break
        if hit:
            info["hurricane"] = True
            if len(info["hurricane_objects"]) < 10:
                info["hurricane_objects"].append(o.name)
    try:
        for sc in bpy.data.scenes:
            if hasattr(sc, "hurr"):
                try:
                    sim = sc.hurr.sim.selected
                    if sim is not None:
                        info["hurricane"] = True
                except Exception:
                    pass
    except Exception:
        pass
except Exception:
    pass
try:
    miss = []
    for img in bpy.data.images:
        try:
            if img.source not in ('FILE', 'SEQUENCE'):
                continue
            fp = bpy.path.abspath(img.filepath) if img.filepath else ""
            if fp and not os.path.exists(fp):
                miss.append(img.filepath)
        except Exception:
            pass
    info["missing"] = miss[:20]
    info["missing_count"] = len(miss)
except Exception:
    pass
print("@@BRM_PROBE_BEGIN@@")
print(json.dumps(info))
print("@@BRM_PROBE_END@@")
"""

SETUP_SCRIPT_TEMPLATE = "\n".join([
    "import bpy",
    "_TARGET_SCENE = @SCENE@",
    "_TARGET_CAM = @CAM@",
    "_TARGET_LAYER = @LAYER@",
    "_TARGET_RES = @RES@",
    "_TARGET_RESX = @RESX@",
    "_TARGET_RESY = @RESY@",
    "_TARGET_OUT = @OUT@",
    "_TARGET_ENGINE = @ENGINE@",
    "_TARGET_SAMPLES = @SAMPLES@",
    "_TARGET_FILM = @FILM@",
    "_TARGET_OVERWRITE = @OVERWRITE@",
    "_TARGET_PLACEHOLDER = @PLACEHOLDER@",
    "_TARGET_FORMAT = @FORMAT@",
    "_TARGET_CMODE = @CMODE@",
    "_TARGET_CDEPTH = @CDEPTH@",
    "_TARGET_COMPR = @COMPR@",
    "sc = bpy.data.scenes.get(_TARGET_SCENE) if _TARGET_SCENE else bpy.context.scene",
    "if sc is None:",
    "    sc = bpy.context.scene",
    "if sc is not None:",
    "    if _TARGET_ENGINE:",
    "        try:",
    "            sc.render.engine = _TARGET_ENGINE",
    "            print('[BRM setup] engine -> %s' % _TARGET_ENGINE)",
    "        except Exception as e:",
    "            print('[BRM setup] engine failed: %s' % e)",
    "    if _TARGET_SAMPLES is not None:",
    "        try:",
    "            if sc.render.engine == 'CYCLES':",
    "                sc.cycles.samples = int(_TARGET_SAMPLES)",
    "            else:",
    "                sc.eevee.taa_render_samples = int(_TARGET_SAMPLES)",
    "            print('[BRM setup] samples -> %s' % _TARGET_SAMPLES)",
    "        except Exception as e:",
    "            print('[BRM setup] samples failed: %s' % e)",
    "    if _TARGET_CAM:",
    "        o = bpy.data.objects.get(_TARGET_CAM)",
    "        if o is not None:",
    "            try:",
    "                sc.camera = o",
    "                print('[BRM setup] camera -> %s' % _TARGET_CAM)",
    "            except Exception as e:",
    "                print('[BRM setup] camera failed: %s' % e)",
    "        else:",
    "            print('[BRM setup] camera not found: %s' % _TARGET_CAM)",
    "    if _TARGET_RESX is not None:",
    "        try:",
    "            sc.render.resolution_x = int(_TARGET_RESX)",
    "            print('[BRM setup] res_x -> %s' % _TARGET_RESX)",
    "        except Exception as e:",
    "            print('[BRM setup] res_x failed: %s' % e)",
    "    if _TARGET_RESY is not None:",
    "        try:",
    "            sc.render.resolution_y = int(_TARGET_RESY)",
    "            print('[BRM setup] res_y -> %s' % _TARGET_RESY)",
    "        except Exception as e:",
    "            print('[BRM setup] res_y failed: %s' % e)",
    "    if _TARGET_RES is not None:",
    "        try:",
    "            sc.render.resolution_percentage = int(_TARGET_RES)",
    "            print('[BRM setup] resolution -> %s' % _TARGET_RES + '%')",
    "        except Exception as e:",
    "            print('[BRM setup] resolution failed: %s' % e)",
    "    if _TARGET_FILM is not None:",
    "        try:",
    "            sc.render.film_transparent = bool(_TARGET_FILM)",
    "            print('[BRM setup] film_transparent -> %s' % _TARGET_FILM)",
    "        except Exception as e:",
    "            print('[BRM setup] film failed: %s' % e)",
    "    if _TARGET_OVERWRITE is not None:",
    "        try:",
    "            sc.render.use_overwrite = bool(_TARGET_OVERWRITE)",
    "            print('[BRM setup] overwrite -> %s' % _TARGET_OVERWRITE)",
    "        except Exception as e:",
    "            print('[BRM setup] overwrite failed: %s' % e)",
    "    if _TARGET_PLACEHOLDER is not None:",
    "        try:",
    "            sc.render.use_placeholder = bool(_TARGET_PLACEHOLDER)",
    "            print('[BRM setup] placeholder -> %s' % _TARGET_PLACEHOLDER)",
    "        except Exception as e:",
    "            print('[BRM setup] placeholder failed: %s' % e)",
    "    if _TARGET_FORMAT:",
    "        try:",
    "            sc.render.image_settings.file_format = _TARGET_FORMAT",
    "            print('[BRM setup] format -> %s' % _TARGET_FORMAT)",
    "        except Exception as e:",
    "            print('[BRM setup] format failed: %s' % e)",
    "    if _TARGET_CMODE:",
    "        try:",
    "            sc.render.image_settings.color_mode = _TARGET_CMODE",
    "            print('[BRM setup] color_mode -> %s' % _TARGET_CMODE)",
    "        except Exception as e:",
    "            print('[BRM setup] color_mode failed: %s' % e)",
    "    if _TARGET_CDEPTH:",
    "        try:",
    "            sc.render.image_settings.color_depth = _TARGET_CDEPTH",
    "            print('[BRM setup] color_depth -> %s' % _TARGET_CDEPTH)",
    "        except Exception as e:",
    "            print('[BRM setup] color_depth failed: %s' % e)",
    "    if _TARGET_COMPR is not None:",
    "        try:",
    "            sc.render.image_settings.compression = int(_TARGET_COMPR)",
    "            print('[BRM setup] compression -> %s' % _TARGET_COMPR)",
    "        except Exception as e:",
    "            print('[BRM setup] compression failed: %s' % e)",
    "    if _TARGET_OUT:",
    "        try:",
    "            sc.render.filepath = _TARGET_OUT",
    "            print('[BRM setup] output -> %s' % _TARGET_OUT)",
    "        except Exception as e:",
    "            print('[BRM setup] output failed: %s' % e)",
    "    if _TARGET_LAYER:",
    "        try:",
    "            done = False",
    "            for win in bpy.context.window_manager.windows:",
    "                try:",
    "                    wsc = win.scene",
    "                    if wsc is not None and wsc.name == sc.name and _TARGET_LAYER in sc.view_layers:",
    "                        win.view_layer = sc.view_layers[_TARGET_LAYER]",
    "                        done = True",
    "                except Exception:",
    "                    pass",
    "            if done:",
    "                print('[BRM setup] view_layer -> %s' % _TARGET_LAYER)",
    "            else:",
    "                print('[BRM setup] view_layer not switched (headless renders the active layer)')",
    "        except Exception as e:",
    "            print('[BRM setup] view_layer failed: %s' % e)",
    "    print('[BRM setup] ready scene=%s' % sc.name)",
    "else:",
    "    print('[BRM setup] WARNING: target scene not found')",
])

GUI_RENDER_TEMPLATE = SETUP_SCRIPT_TEMPLATE + "\n" + "\n".join([
    "if True:",
    "    if @FS@ is not None:",
    "        sc.frame_start = int(@FS@)",
    "    if @FE@ is not None:",
    "        sc.frame_end = int(@FE@)",
    "    print('[BRM gui] rendering scene=%s frames %s-%s' % (sc.name, sc.frame_start, sc.frame_end))",
    "@PYTRAILER@",
    # A GUI Blender never exits on its own: without this the window sits open
    # forever after the last frame and the queue hangs (next job never starts).
    # os._exit carries the outcome in the exit code (quit_blender is always 0).
    "    _brm_ok = True",
    "    try:",
    "        bpy.ops.render.render(animation=True)",
    "    except Exception as _e:",
    "        print('[BRM gui] render FAILED: %s' % _e)",
    "        _brm_ok = False",
    "    print('[BRM gui] render finished ok=%s' % _brm_ok)",
    "    import sys as _sys",
    "    try:",
    "        _sys.stdout.flush()",
    "    except Exception:",
    "        pass",
    "    import os as _os",
    "    _os._exit(0 if _brm_ok else 1)",
])


def _silent_popen_kwargs():
    """kwargs preventing console-window flashes for background child processes.

    blender.exe / ffmpeg.exe are console-subsystem binaries; on Windows they
    pop a CMD window unless CREATE_NO_WINDOW + STARTF_USESHOWWINDOW are set.
    """
    if os.name != "nt":
        return {}
    kw = {}
    try:
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    except Exception:
        pass
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kw["startupinfo"] = si
    except Exception:
        pass
    return kw


def render_probe(blender_path, blend_file, timeout=240, allow_blender=True):
    """File info for a .blend: disk cache -> fast direct parse -> Blender fallback.
    allow_blender=False skips the fallback (no surprise full-Blender loads from
    automatic background probing; manual refresh and render start keep it)."""
    if brm_blendparse is not None:
        try:
            cached = brm_blendparse.load_cached_probe(blend_file)
            if cached:
                return cached
        except Exception:
            pass
        try:
            probe = brm_blendparse.fast_probe(blend_file)
            try:
                brm_blendparse.store_cached_probe(blend_file, probe)
            except Exception:
                pass
            return probe
        except Exception:
            pass
    if not allow_blender:
        return None
    if not blender_path or not os.path.exists(blender_path):
        return None
    fd, script = tempfile.mkstemp(suffix="_brm_probe.py")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(PROBE_SCRIPT)
        cmd = [blender_path, "-b", blend_file, "--python", script]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             errors="ignore", timeout=timeout, **_silent_popen_kwargs())
        out = (res.stdout or "") + "\n" + (res.stderr or "")
        return parse_probe_output(out)
    except Exception:
        return None
    finally:
        try:
            os.remove(script)
        except Exception:
            pass


def write_setup_script(scene=None, camera=None, res_pct=None, output=None, frame_s=None,
                       frame_e=None, gui=False, view_layer=None, engine=None, samples=None,
                       res_x=None, res_y=None, film=None, overwrite=None, placeholder=None,
                       file_format=None, color_mode=None, color_depth=None, compression=None,
                       python_trailer=""):
    """Write a temp pre-render/render-driver script. Returns path (caller deletes)."""
    tpl = GUI_RENDER_TEMPLATE if gui else SETUP_SCRIPT_TEMPLATE
    for k, v in {"@SCENE@": repr(scene), "@CAM@": repr(camera), "@LAYER@": repr(view_layer),
                 "@RES@": repr(res_pct), "@RESX@": repr(res_x), "@RESY@": repr(res_y),
                 "@OUT@": repr(output), "@ENGINE@": repr(engine),
                 "@SAMPLES@": repr(samples), "@FILM@": repr(film),
                 "@OVERWRITE@": repr(overwrite), "@PLACEHOLDER@": repr(placeholder),
                 "@FORMAT@": repr(file_format), "@CMODE@": repr(color_mode),
                 "@CDEPTH@": repr(color_depth), "@COMPR@": repr(compression)}.items():
        tpl = tpl.replace(k, v)
    if gui:
        tpl = tpl.replace("@FS@", repr(frame_s)).replace("@FE@", repr(frame_e))
        tpl = tpl.replace("@PYTRAILER@", python_trailer or "    pass")
    fd, path = tempfile.mkstemp(suffix="_brm_setup.py")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(tpl)
    return path


def build_python_trailer(python_args):
    """Turn the inspector 'Python arguments' field into driver-script code."""
    t = (python_args or "").strip()
    if not t:
        return "    pass"
    if os.path.exists(t) and t.lower().endswith(".py"):
        return "    exec(compile(open(%r, encoding='utf-8').read(), %r, 'exec'))" % (t, t)
    return "    exec(compile(%r, '<brm-pyargs>', 'exec'))" % t


def scene_info_from_probe(probe, scene_name):
    if not probe:
        return None
    for sc in probe.get("scenes", []):
        if sc.get("name") == scene_name:
            return sc
    return None


def effective_job_settings(item, probe):
    """Resolve Auto (None) values to concrete ones using probe data."""
    scenes = (probe or {}).get("scenes", [])
    active = (probe or {}).get("active")
    scene = item.get("scene") or active or (scenes[0]["name"] if scenes else None)
    sc = scene_info_from_probe(probe, scene) or {}
    camera = item.get("camera") or sc.get("camera")
    vls = sc.get("view_layers") or []
    layer = item.get("view_layer") or (vls[0] if vls else None)
    ov = item.get("ov", {}) or {}
    base_x = item.get("res_x") if (ov.get("res_x") and item.get("res_x")) else sc.get("res_x")
    base_y = item.get("res_y") if (ov.get("res_y") and item.get("res_y")) else sc.get("res_y")
    if ov.get("scale") and item.get("res_pct"):
        res_pct = int(item["res_pct"])
    elif item.get("res_pct") and not (ov.get("res_x") or ov.get("res_y") or ov.get("scale")):
        res_pct = int(item["res_pct"])
    else:
        res_pct = int(sc.get("res_pct") or 100)
    fs = item.get("frame_start")
    if fs is None:
        fs = sc.get("frame_start", 1)
    fe = item.get("frame_end")
    if fe is None:
        fe = sc.get("frame_end", 250)
    output = item.get("output") or sc.get("output") or "//"
    output = expand_output_vars(output, scene=scene, camera=camera)
    fps = item.get("fps") or sc.get("fps") or 24.0
    samples = item.get("samples")
    if samples is None:
        eng0 = (item.get("engine") or sc.get("engine") or "")
        samples = sc.get("samples") if "CYCLES" in eng0 else sc.get("eevee_samples")
    film = item.get("film_transparent")
    if film is None:
        film = sc.get("film_transparent", False)
    if ov.get("overwrite") and item.get("overwrite") is not None:
        overwrite = bool(item["overwrite"])
    else:
        overwrite = bool(sc.get("use_overwrite", True))
    if ov.get("placeholder") and item.get("placeholder") is not None:
        placeholder = bool(item["placeholder"])
    else:
        placeholder = bool(sc.get("use_placeholder", False))
    return {
        "scene": scene, "camera": camera, "view_layer": layer,
        "res_pct": res_pct, "res_x": base_x, "res_y": base_y,
        "frame_start": int(fs), "frame_end": int(fe),
        "output": output, "fps": float(fps),
        "engine": item.get("engine") or sc.get("engine", ""),
        "samples": samples, "film_transparent": bool(film),
        "overwrite": overwrite, "placeholder": placeholder,
        "file_format": item.get("file_format") or sc.get("file_format", ""),
        "color_mode": item.get("color_mode") or sc.get("color_mode", ""),
        "color_depth": str(item.get("color_depth") or sc.get("color_depth") or ""),
        "compression": item.get("compression") if item.get("compression") is not None else sc.get("compression"),
        "python_args": item.get("python_args", "") or "",
    }


# ====================================================================
# TOOLTIP CLASS
# ====================================================================
class ToolTip:
    """Hover tooltip that survives hover storms: shows only after a delay
    with the pointer still inside, at most one tip window app-wide, and
    bindings coexist (add='+') with widgets' own hover handlers."""
    _active = None

    def __init__(self, widget, text, delay=450):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window = None
        self._after = None
        try:
            self.widget.bind("<Enter>", self._schedule, add="+")
            self.widget.bind("<Leave>", self.hide_tip, add="+")
            self.widget.bind("<Motion>", self._schedule, add="+")
            self.widget.bind("<ButtonPress-1>", self.hide_tip, add="+")
        except Exception:
            pass

    def show_tip(self, event=None):
        self._schedule(event)

    def _schedule(self, event=None):
        try:
            self.hide_tip()
            if not self.text:
                return
            if self._after:
                try:
                    self.widget.after_cancel(self._after)
                except Exception:
                    pass
            self._after = self.widget.after(self.delay, self._maybe_show)
        except Exception:
            pass

    def _maybe_show(self):
        try:
            self._after = None
            try:
                x, y = self.widget.winfo_pointerxy()
                wx, wy = self.widget.winfo_rootx(), self.widget.winfo_rooty()
                if not (wx <= x < wx + self.widget.winfo_width()
                        and wy <= y < wy + self.widget.winfo_height()):
                    return
            except Exception:
                return
            if ToolTip._active is not None:
                try:
                    ToolTip._active.destroy()
                except Exception:
                    pass
                ToolTip._active = None
            tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry("+{}+{}".format(x + 16, y + 16))
            frame = tk.Frame(tw, bg="#2b2b2b", relief="solid", borderwidth=1)
            frame.pack()
            tk.Label(frame, text=self.text, justify=tk.LEFT, background="#2b2b2b",
                     foreground="#ffffff", font=("Segoe UI", 9), padx=5, pady=2).pack()
            self.tip_window = tw
            ToolTip._active = tw
        except Exception:
            pass

    def hide_tip(self, event=None):
        try:
            if self._after:
                try:
                    self.widget.after_cancel(self._after)
                except Exception:
                    pass
                self._after = None
        except Exception:
            pass
        try:
            if self.tip_window is not None:
                if ToolTip._active is self.tip_window:
                    ToolTip._active = None
                try:
                    self.tip_window.destroy()
                except Exception:
                    pass
                self.tip_window = None
        except Exception:
            pass


# ====================================================================
# MAIN APP — screenshot layout
# ====================================================================
class BlenderRenderApp(ctk.CTk):
    def __init__(self):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('blenderbot.monitor.v8.modern')
        except Exception:
            pass

        super().__init__()
        try:
            self.title("Blender Render Manager v{}".format(APP_VERSION))
        except Exception:
            self.title("Blender Render Manager")
        self.geometry("1400x900")
        self.configure(fg_color=C_BG)

        self.ctk_logo = None
        self.temp_ico = None
        try:
            base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(os.path.dirname(__file__))
            logo_path = os.path.join(base_path, "512x512logo.png")
            if Image and os.path.exists(logo_path):
                logo_image = Image.open(logo_path)
                self.ctk_logo = ctk.CTkImage(light_image=logo_image, dark_image=logo_image, size=(28, 28))
                self.temp_ico = os.path.join(tempfile.gettempdir(), "blenderbot_icon.ico")
                logo_image.save(self.temp_ico, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
                self.iconbitmap(self.temp_ico)
                self.logo_photo = ImageTk.PhotoImage(logo_image)
                self.wm_iconphoto(True, self.logo_photo)
        except Exception as e:
            print(f"Error loading logo: {e}")

        self.config = load_config()
        self.config["queue_list"] = [migrate_queue_item(i) for i in self.config.get("queue_list", [])]
        for item in self.config.get("queue_list", []):
            if item.get("status") == "Rendering":
                item["status"] = "Pending"

        self.is_rendering = False
        self.is_converting = False
        self.paused = False
        self.stop_event = threading.Event()
        self.render_process = None
        self.convert_procs = set()
        self.discord_msg_id = self.config.get("last_msg_id")
        self.global_end_frame = 0
        self.global_start_frame = 1
        self.selected_idx = None
        self._inspector_updating = False
        self.row_widgets = []
        self.bottom_tab = "progress"
        self.blender_version_label = self.config.get("blender_version", "")
        self.frame_marks = []
        self.settings_win = None
        # viewport + animation state
        self._anim_rows = set()
        self._anim_frame = 0
        self._live_on = False
        self.vp_idx = None
        self.vp_photo = None
        self.vp_path = None
        self._vp_has_img = False
        self._vp_drawn = None
        self._vp_decoding = False
        self._vp_pending = None
        self.vp_aspect = (16, 9)
        self._vp_center = ("", C_FAINT)
        self.vp_job_start = None
        self._vp_after = None
        self._vp_last_pct = -1
        self._vp_samples = ""
        self._vp_mem = ""

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.layout = self._valid_layout(self.config.get("layout"))
        try:
            self.layout_hidden = [p for p in (self.config.get("layout_hidden") or [])
                                  if p in PANELS]
        except Exception:
            self.layout_hidden = []
        self.layout_active = {}
        self.layout_home = {}
        try:
            raw_split = self.config.get("layout_split") or {}
            self.layout_split = {s: dict(v) for s, v in raw_split.items()
                                 if s in SLOTS and isinstance(v, dict)}
        except Exception:
            self.layout_split = {}
        sizes = self.config.get("layout_sizes") or {}
        try:
            self.layout_sizes = {"left": max(120, int(sizes.get("left", 280))),
                                 "right": max(120, int(sizes.get("right", 256)))}
        except Exception:
            self.layout_sizes = dict(DEFAULT_LAYOUT_SIZES)
        try:
            self._slot_w = {"left": max(140, int(sizes.get("left", 280))),
                            "center": max(140, int(sizes.get("center", 480))),
                            "right": max(140, int(sizes.get("right", 256)))}
        except Exception:
            self._slot_w = {"left": 280, "center": 480, "right": 256}
        try:
            self._bottom_h = int(sizes.get("bottom", 0)) or None
        except Exception:
            self._bottom_h = None
        self._drag = None
        self._tab_down = None
        self._geo_after = None
        self._sash_y0 = None
        self._sel_after = None
        self._sel_token = 0
        self._autoprobe_busy = False
        self._row_down = None
        self._row_ghost = None
        self._row_drop_idx = None
        self.selected_paths = set()
        self._sel_anchor = None
        self._apply_saved_geometry()

        self.build_topbar()
        self.build_main()
        self.build_bottom()
        self.apply_layout()
        self._restore_pane_sizes()
        try:
            self.vert_paned.bind("<ButtonRelease-1>", lambda e: self.after(100, self._save_pane_sizes))
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_win_configure)

        self.bind("<Control-o>", lambda e: self.add_to_queue())
        self.bind("<Control-O>", lambda e: self.add_to_queue())
        self.bind("<Delete>", self._on_delete_key)
        try:
            bp = self.config.get("blender_path", "")
            if not bp or not os.path.exists(bp):
                found = autodetect_blender()
                if found:
                    self.config["blender_path"] = found
                    save_config(self.config)
                    self.log("Blender auto-detected: {}".format(found))
        except Exception:
            pass

        self.refresh_all_rows()
        self.refresh_inspector()
        if self.config["queue_list"] and self.selected_idx is None:
            self.selected_idx = 0
            self.refresh_row_selection()
            self.refresh_inspector()
            try:
                self.lbl_project_tab.configure(text=os.path.basename(self.config["queue_list"][0].get("path", "")))
            except Exception:
                pass
        # restore last session's selected job + queue scroll position
        try:
            spath = self.config.get("selected_path") or ""
            if spath:
                for _i, _it in enumerate(self.config["queue_list"]):
                    if _it.get("path") == spath:
                        self.selected_idx = _i
                        break
            self.refresh_row_selection()
            self.refresh_inspector()
            self._update_pill()
            try:
                sc = float(self.config.get("queue_scroll") or 0.0)
            except Exception:
                sc = 0.0
            if 0.0 < sc < 1.0:
                self.after(300, lambda: self._restore_scroll(sc))
        except Exception:
            pass
        self.after(200, self._set_window_icon)
        self.after(400, self._force_show)
        self.after(500, self._anim_tick)
        # initial viewport state, synchronously: a blind after() timer here
        # used to fire mid-session and wipe a newer picture/selection
        try:
            self.vp_show_job(self.selected_idx)
        except Exception:
            pass
        try:
            _me = os.path.abspath(sys.argv[0]) if getattr(sys, "argv", None) else "?"
            self.log("BRM v{} @ {}".format(APP_VERSION, _me))
        except Exception:
            pass
        threading.Thread(target=self._detect_blender_version, daemon=True).start()
        # Load real per-file settings (scenes/cameras/layers/frames) in the background
        # so rows show file values instead of generic Auto/1-250 placeholders.
        threading.Thread(target=self._auto_probe_new, daemon=True).start()

    def _force_show(self):
        try:
            self.deiconify()
            self.lift()
        except Exception:
            pass

    def _set_window_icon(self):
        try:
            if hasattr(self, 'logo_photo'):
                self.wm_iconphoto(True, self.logo_photo)
            if self.temp_ico:
                self.iconbitmap(self.temp_ico)
        except Exception:
            pass

    # ---- icons (drawn, brm_theme) ----
    def _icon(self, name, size=14, color="#d8d8d8"):
        """CTkImage glyph or None (caller must pass a text fallback)."""
        try:
            cache = self._icon_cache
        except AttributeError:
            cache = self._icon_cache = {}
        if TH is None:
            return None
        key = ("g", name, size, color)
        if key in cache:
            return cache[key]
        try:
            pil = TH.glyph(name, size, color)
            if pil is None:
                return None
            img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(size, size))
            cache[key] = img
            return img
        except Exception:
            return None

    def _status_img(self, kind, size=15, frame=0):
        """CTkImage status icon (done/rendering/crashed/paused/queued)."""
        try:
            cache = self._icon_cache
        except AttributeError:
            cache = self._icon_cache = {}
        if TH is None:
            return None
        key = ("s", kind, size, frame)
        if key in cache:
            return cache[key]
        try:
            pil = TH.status_icon(kind, size, frame)
            if pil is None:
                return None
            img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(size, size))
            cache[key] = img
            return img
        except Exception:
            return None

    def _glyph(self, name, fallback=""):
        return fallback

    def _ifont(self, size=14):
        return ("Segoe UI", size)

    def _detect_blender_version(self):
        b = self.config.get("blender_path", "")
        ver = ""
        if b and os.path.exists(b):
            try:
                r = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=30,
                                   encoding="utf-8", errors="ignore", **_silent_popen_kwargs())
                m = re.search(r"Blender\s+(\d+\.\d+)", (r.stdout or ""))
                if m:
                    ver = m.group(1)
            except Exception:
                pass
        if ver:
            self.blender_version_label = ver
            self.config["blender_version"] = ver
            save_config(self.config)
        try:
            self.after(0, lambda: self.lbl_blender_ver.configure(text=self.blender_version_label or "?"))
        except Exception:
            pass

    # ================= TOP BAR =================
    def _hbtn(self, parent, text, glyph_name, style, command, width=86):
        """Header action button: solid-orange / outline-amber / outline-red / ghost."""
        img = self._icon(glyph_name, 11, "#ffffff" if style == "solid-orange" else
                         (C_YELLOW if style == "outline-amber" else C_RED if style == "outline-red" else C_GRAY_TXT))
        if style == "solid-orange":
            kw = dict(fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, text_color="white", border_width=0)
        elif style == "outline-amber":
            kw = dict(fg_color="transparent", hover_color=C_ROW, text_color=C_YELLOW,
                      border_width=1, border_color=C_YELLOW)
        elif style == "outline-red":
            kw = dict(fg_color="transparent", hover_color=C_ROW,
                      text_color=C_RED, border_width=1, border_color=C_RED)
        else:
            kw = dict(fg_color="transparent", hover_color=C_ROW, text_color=C_GRAY_TXT, border_width=0)
        try:
            b = ctk.CTkButton(parent, text=text, image=img, compound="left", width=width, height=24,
                              corner_radius=0, font=("Barlow Condensed", 12, "bold"), command=command, **kw)
            if img is None:
                b.configure(text=text, image=None)
        except Exception:
            b = ctk.CTkButton(parent, text=text, width=width, height=24,
                              corner_radius=0, font=("Barlow Condensed", 12, "bold"), command=command, **kw)
        return b

    def _brand_hex(self, parent, size=22):
        try:
            cv = tk.Canvas(parent, width=size, height=size, bg=C_PANEL,
                           highlightthickness=0, bd=0)
            cx, cy, r = size / 2, size / 2, size / 2 - 1
            import math
            pts = []
            for k in range(6):
                a = math.pi / 3 * k - math.pi / 6
                pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
            cv.create_polygon(pts, fill=C_ACCENT, outline="")
            cv.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, outline="white", width=1)
            cv.create_oval(cx - 1, cy - 1, cx + 1, cy + 1, fill="white", outline="")
            return cv
        except Exception:
            return tk.Label(parent, text="B", bg=C_ACCENT, fg="white")

    def build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0, height=38)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        bar.grid_propagate(False)

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, padx=(14, 0), sticky="w")
        try:
            self._brand_hex(brand).pack(side="left", padx=(0, 7))
        except Exception:
            pass
        ctk.CTkLabel(brand, text="BRM", font=("Barlow Condensed", 14, "bold"),
                     text_color=C_TXT).pack(side="left")

        center = ctk.CTkFrame(bar, fg_color="transparent")
        center.grid(row=0, column=1, sticky="w", padx=(18, 0))
        pill = ctk.CTkFrame(center, fg_color=C_ROW, corner_radius=0, border_width=1, border_color=C_LINE)
        pill.pack(side="left")
        self.lbl_project_tab = ctk.CTkLabel(pill, text="No selection", font=F_MONO, text_color=C_TXT)
        self.lbl_project_tab.pack(side="left", padx=(10, 2), pady=3)
        b_pillx = ctk.CTkButton(pill, text="x", width=22, height=18, fg_color="transparent",
                                hover_color=C_ROW, text_color=C_GRAY_TXT, font=F_MONO_SM,
                                command=self._clear_selection)
        b_pillx.pack(side="left", padx=(0, 4))
        b_top_add = ctk.CTkButton(center, text="+", width=26, height=24, fg_color="transparent",
                                  hover_color=C_ROW, border_width=1, border_color=C_LINE,
                                  text_color=C_GRAY_TXT, font=F_BODY, command=self.add_to_queue)
        b_top_add.pack(side="left", padx=(6, 0))
        ToolTip(b_top_add, "Add .blend files (Ctrl+O)")

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=2, padx=(0, 14), sticky="e")
        ver = ctk.CTkFrame(right, fg_color="transparent")
        ver.pack(side="left", padx=(0, PAD))
        ctk.CTkLabel(ver, text="BLENDER", font=("Barlow Condensed", 10, "bold"),
                     text_color=C_GRAY_TXT).pack(side="left", padx=(0, 6))
        self.lbl_blender_ver = ctk.CTkLabel(ver, text=self.blender_version_label or "?",
                                            font=F_MONO, text_color=C_ACCENT)
        self.lbl_blender_ver.pack(side="left")
        b_ver = ctk.CTkButton(ver, text="", image=self._icon("refresh", 12), width=24, height=24,
                              fg_color="transparent", hover_color=C_ROW,
                              command=lambda: threading.Thread(target=self._detect_blender_version, daemon=True).start())
        if b_ver.cget("image") in (None, ""):
            b_ver.configure(text="R", width=24)
        b_ver.pack(side="left", padx=(4, 0))
        self.btn_settings = ctk.CTkButton(right, text="", image=self._icon("settings", 14),
                                          width=28, height=24, corner_radius=0,
                                          fg_color="transparent", hover_color=C_ROW,
                                          command=self.open_settings_window)
        if self.btn_settings.cget("image") in (None, ""):
            self.btn_settings.configure(text="S", width=28)
        ToolTip(self.btn_settings, "Settings")
        self.btn_settings.pack(side="left", padx=2)
        b_about = ctk.CTkButton(right, text="About", width=64, height=24, corner_radius=0,
                                fg_color="transparent", hover_color=C_ROW,
                                text_color=C_GRAY_TXT, font=("Barlow Condensed", 12, "bold"),
                                command=self.open_about)
        b_about.pack(side="left", padx=4)
        self.btn_pause = self._hbtn(right, "PAUSE", "pause", "outline-amber",
                                    self.toggle_pause, width=86)
        self.btn_pause.pack(side="left", padx=2)
        self.btn_pause.configure(state="disabled")
        if psutil is None:
            ToolTip(self.btn_pause, "Pause needs the 'psutil' package:\npip install psutil")
        self.btn_stop = self._hbtn(right, "STOP", "stop", "outline-red", self.stop_render, width=80)
        self.btn_stop.pack(side="left", padx=2)
        self.btn_stop.configure(state="disabled")
        self.btn_start = self._hbtn(right, "START", "play", "solid-orange",
                                    self.start_render_thread, width=86)
        self.btn_start.pack(side="left", padx=2)

    def open_about(self):
        try:
            messagebox.showinfo(
                "About",
                "Blender Render Manager v{}\nby var\n\nQueues .blend files and renders them in the background "
                "with per-job scene, camera, resolution and format settings, a live viewport, "
                "automatic crash restarts, one-click MP4 conversion, render history "
                "and Discord notifications.\n\nBlender: {}\nConfig: {}\nffmpeg: {}".format(
                    APP_VERSION, self.config.get("blender_path", "—") or "—",
                    CONFIG_FILE, ffmpeg_exe(self.config.get("ffmpeg_path", "")) or "—"))
        except Exception:
            pass

    def _on_delete_key(self, event=None):
        try:
            w = getattr(event, "widget", None)
            if w is not None:
                if w.__class__.__name__ in (
                        "Entry", "Text", "CTkEntry", "CTkTextbox", "Listbox"):
                    return
                try:
                    if w.winfo_toplevel() is not self:
                        return
                except Exception:
                    pass
            if not self._guard_not_rendering("Remove job"):
                return
            try:
                paths = set(self.selected_paths or set())
            except Exception:
                paths = set()
            idxs = []
            try:
                for j in range(len(self.config["queue_list"])):
                    if self._row_key(j) in paths:
                        idxs.append(j)
            except Exception:
                pass
            if not idxs and self.selected_idx is not None:
                idxs = [self.selected_idx]
            if not idxs:
                return
            for j in sorted(idxs, reverse=True):
                try:
                    del self.config["queue_list"][j]
                except Exception:
                    pass
            self.selected_idx = None
            save_config(self.config)
            self.refresh_all_rows()
            self.refresh_inspector()
            self._sync_selection()
            self.refresh_row_selection()
        except Exception:
            pass

    def _clear_selection(self):
        self.selected_idx = None
        try:
            self.selected_paths = set()
            self._sel_anchor = None
        except Exception:
            pass
        try:
            self.refresh_row_selection()
            self.refresh_inspector()
            self._update_pill()
            self.vp_show_job(None)
        except Exception:
            pass

    def _update_pill(self):
        try:
            if self.selected_idx is not None:
                self.lbl_project_tab.configure(
                    text=os.path.basename(self.config["queue_list"][self.selected_idx].get("path", "")))
            else:
                self.lbl_project_tab.configure(text="No selection")
        except Exception:
            pass

    # ================= MAIN SPLIT =================
    def build_main(self):
        # vertical splitter: main area over bottom slot, same draggable sash
        # feel as the left/center/right dividers
        self.vert_paned = tk.PanedWindow(self, orient="vertical", bg=C_LINE, bd=0,
                                         sashwidth=5, sashrelief="flat", showhandle=False,
                                         opaqueresize=False)
        self.vert_paned.grid(row=1, column=0, rowspan=2, sticky="nsew")
        self.main_paned = tk.PanedWindow(self.vert_paned, orient="horizontal", bg=C_LINE, bd=0,
                                         sashwidth=5, sashrelief="flat", showhandle=False,
                                         opaqueresize=False)
        self.vert_paned.add(self.main_paned, minsize=200, sticky="nsew", stretch="always")
        main = self.main_paned

        # ---- layout slots: Premiere-style tab groups ----
        # Each slot shows its panels as TABS (one visible at a time). Slots may
        # be empty (collapsed to a slim strip) and panels may be hidden
        # entirely (Panels menu / right-click a tab to re-show).
        self.slot_frames = {}
        self.slot_bar = {}
        self.slot_body = {}
        self.slot_tabs = {}
        self.slot_hint = {}
        self.slot_pane = {}
        self.slot_gframe = {}
        self.slot_bar2 = {}
        self.slot_body2 = {}
        for _slot_name in ("left", "center", "right"):
            _slot = tk.Frame(main, bg=C_BG)
            main.add(_slot, minsize=120, sticky="nsew",
                     stretch="always" if _slot_name == "center" else "never")
            self.slot_frames[_slot_name] = _slot
            self._build_slot_chrome(_slot_name, _slot)
        self.slot_bottom = tk.Frame(self.vert_paned, bg=C_BG)
        self.vert_paned.add(self.slot_bottom, minsize=60, sticky="nsew", stretch="never")
        self._build_slot_chrome("bottom", self.slot_bottom)

        # ---- queue panel (docked into a slot by apply_layout) ----
        q = tk.Frame(self, bg=C_BG, width=280)
        q.grid_columnconfigure(0, weight=1)
        q.grid_rowconfigure(3, weight=1)
        self.panel_queue = q

        qh = tk.Frame(q, bg=C_PANEL, height=26)
        qh.grid(row=0, column=0, sticky="ew")
        qh.grid_propagate(False)
        qh.grid_columnconfigure(0, weight=1)
        b_qmenu = tk.Button(qh, text="≡", font=F_MONO, fg=C_GRAY_TXT, bg=C_PANEL,
                            activebackground=C_ROW, activeforeground="white",
                            relief="flat", bd=0, highlightthickness=0, width=3,
                            command=self.queue_menu)
        b_qmenu.grid(row=0, column=1, padx=(0, 6), sticky="e")

        self.btn_add_big = ctk.CTkButton(q, text="+ ADD FILES", height=30, corner_radius=0,
                                         fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                                         text_color="white", font=("Barlow Condensed", 12, "bold"),
                                         command=self.add_to_queue)
        self.btn_add_big.grid(row=1, column=0, sticky="ew", padx=10, pady=(8, 6))

        sub = tk.Frame(q, bg=C_PANEL, height=22)
        sub.grid(row=2, column=0, sticky="new")
        sub.grid_propagate(False)
        sub.grid_columnconfigure(2, weight=1)
        tk.Label(sub, text="#", font=F_LABEL_SM, fg=C_FAINT, bg=C_PANEL, width=3,
                 anchor="e").grid(row=0, column=0, padx=(10, 2), sticky="w")
        tk.Label(sub, text="PROJECT", font=F_LABEL_SM, fg=C_FAINT, bg=C_PANEL,
                 anchor="w").grid(row=0, column=1, columnspan=2, padx=2, sticky="w")
        tk.Label(sub, text="FRAMES", font=F_LABEL_SM, fg=C_FAINT, bg=C_PANEL,
                 anchor="e").grid(row=0, column=3, padx=(2, 10), sticky="e")

        self.rows_scroll = ctk.CTkScrollableFrame(q, fg_color=C_BG, corner_radius=0,
                                                  scrollbar_button_color=C_LINE2,
                                                  scrollbar_button_hover_color=C_GRAY_TXT)
        self.rows_scroll.grid(row=3, column=0, sticky="nsew")
        self.rows_scroll.grid_columnconfigure(0, weight=1)

        qf = tk.Frame(q, bg=C_PANEL)
        qf.grid(row=4, column=0, sticky="ew", padx=10, pady=8)
        b_cv = tk.Button(qf, text="Convert MP4", font=F_SMALL, fg=C_ACCENT2, bg=C_PANEL,
                         activebackground=C_PANEL, activeforeground="white",
                         relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                         command=self.convert_mass_mp4)
        b_cv.pack(side="left")
        ToolTip(b_cv, "Convert selection, else all finished jobs without MP4 (max 2 at once)")
        b_cf = tk.Button(qf, text="Clear finished", font=F_SMALL, fg=C_GRAY_TXT, bg=C_PANEL,
                         activebackground=C_PANEL, activeforeground="white",
                         relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                         command=self.clear_finished)
        b_cf.pack(side="left", padx=(14, 0))
        b_ca = tk.Button(qf, text="Clear all", font=F_SMALL, fg=C_FAINT, bg=C_PANEL,
                         activebackground=C_PANEL, activeforeground=C_RED,
                         relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                         command=self.clear_queue)
        b_ca.pack(side="left", padx=(14, 0))

        # ---- center: viewport + progress (movable panel) ----
        cp = tk.Frame(self, bg="#060609")
        cp.grid_columnconfigure(0, weight=1)
        cp.grid_rowconfigure(0, weight=1)
        self.panel_view = cp
        try:
            # exact signal: reload pending picture the moment we're mapped
            # (timers race mapping; this cannot arrive too early)
            cp.bind("<Map>", lambda e: self._vp_sync_visibility())
        except Exception:
            pass

        # (no title bar: the VIEWPORT tab already names this panel and drags it)
        self.vp_canvas = tk.Canvas(cp, bg="#080808", highlightthickness=0, bd=0,
                                   cursor="hand2", height=220)
        self.vp_canvas.grid(row=0, column=0, sticky="nsew")
        self.vp_canvas.bind("<Configure>", lambda e: self._vp_soon())
        self.vp_canvas.bind("<Button-1>", lambda e: self.vp_zoom_open())
        ToolTip(self.vp_canvas, "Click to zoom")
        self.vp_stats = tk.Frame(cp, bg="#000000", height=24)
        self.vp_stats.grid(row=1, column=0, sticky="ew")
        self.vp_stats.grid_propagate(False)
        tk.Frame(self.vp_stats, bg=C_LINE, height=1).pack(fill="x")
        sbody = tk.Frame(self.vp_stats, bg="#000000")
        sbody.pack(fill="both", expand=True, padx=10)
        self.lbl_vp_name = tk.Label(sbody, text="", font=F_MONO_SM, fg=C_ACCENT2, bg="#000000", anchor="w")
        self.lbl_vp_name.pack(side="left", fill="x", expand=True)
        self.lbl_vp_f = tk.Label(sbody, text="", font=F_MONO_SM, fg=C_TXT, bg="#000000")
        self.lbl_vp_f.pack(side="left", padx=7)
        self.lbl_vp_s = tk.Label(sbody, text="", font=F_MONO_SM, fg=C_TXT, bg="#000000")
        self.lbl_vp_s.pack(side="left", padx=7)
        self.lbl_vp_t = tk.Label(sbody, text="", font=F_MONO_SM, fg=C_TXT, bg="#000000")
        self.lbl_vp_t.pack(side="left", padx=7)
        self.lbl_vp_mem = tk.Label(sbody, text="", font=F_MONO_SM, fg=C_TXT, bg="#000000")
        self.lbl_vp_mem.pack(side="left", padx=7)
        self.lbl_vp_aspect = tk.Label(sbody, text="16:9", font=F_MONO_SM, fg=C_GRAY_TXT, bg="#000000")
        self.lbl_vp_aspect.pack(side="right", padx=(7, 0))
        self.live_frame = tk.Frame(sbody, bg="#000000")
        self.live_frame.pack(side="right", padx=(7, 0))
        self.live_frame.pack_forget()
        self.lbl_live_dot = tk.Label(self.live_frame, text="\u25cf", font=("Segoe UI", 8),
                                     fg=C_FAINT, bg="#000000")
        self.lbl_live_dot.pack(side="left", padx=(0, 4))
        tk.Label(self.live_frame, text="LIVE", font=("Barlow Condensed", 9, "bold"),
                 fg=C_ACCENT, bg="#000000").pack(side="left")
        self.vp_bar_bg = tk.Frame(cp, bg=C_LINE, height=2)
        self.vp_bar_bg.grid(row=2, column=0, sticky="ew")
        self.vp_bar = tk.Frame(self.vp_bar_bg, bg=C_ACCENT, height=2, width=1)
        self.vp_bar.place(relx=0, rely=0, anchor="nw", relheight=1.0, relwidth=0.0)
        # ---- progress panel (own dockable panel, may sit anywhere) ----
        self.panel_prog = tk.Frame(self, bg=C_PANEL)
        self.panel_prog.grid_columnconfigure(0, weight=1)
        # (no title bar: the PROGRESS tab already names this panel and drags it)
        self.view_progress = tk.Frame(self.panel_prog, bg=C_PANEL)
        self.view_progress.grid(row=0, column=0, sticky="ew")
        self.view_progress.grid_columnconfigure(0, weight=1)
        prow = tk.Frame(self.view_progress, bg=C_PANEL)
        prow.grid(row=0, column=0, sticky="ew", pady=(6, 4))
        prow.grid_columnconfigure(1, weight=1)
        tk.Label(prow, text="RENDERING", font=("Barlow Condensed", 10, "bold"),
                 fg=C_GRAY_TXT, bg=C_PANEL).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.lbl_prog_job = tk.Label(prow, text="Idle", font=F_MONO_SM, fg=C_GRAY_TXT,
                                     bg=C_PANEL, anchor="w")
        self.lbl_prog_job.grid(row=0, column=1, sticky="ew")
        self.bar_overall = ctk.CTkProgressBar(self.view_progress, height=8, corner_radius=0,
                                               progress_color=C_ACCENT, fg_color=C_LINE)
        self.bar_overall.grid(row=1, column=0, sticky="ew")
        self.bar_overall.set(0)
        srow = tk.Frame(self.view_progress, bg=C_PANEL)
        srow.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        self.lbl_prog_start = tk.Label(srow, text="Start: \u2014", font=F_MONO_SM, fg=C_FAINT, bg=C_PANEL)
        self.lbl_prog_start.pack(side="left")
        self.lbl_prog_elapsed = tk.Label(srow, text="Elapsed: \u2014", font=F_MONO_SM, fg=C_FAINT, bg=C_PANEL)
        self.lbl_prog_elapsed.pack(side="left", padx=14)
        self.lbl_prog_mid = tk.Label(srow, text="", font=F_MONO_SM, fg=C_FAINT, bg=C_PANEL)
        self.lbl_prog_mid.pack(side="left", padx=14)
        self.lbl_prog_end = tk.Label(srow, text="End: \u2014", font=F_MONO_SM, fg=C_FAINT, bg=C_PANEL)
        self.lbl_prog_end.pack(side="left", padx=14)
        self.lbl_prog_last = tk.Label(srow, text="", font=F_MONO_SM, fg=C_FAINT, bg=C_PANEL)
        self.lbl_prog_last.pack(side="left", padx=14)
        self.lbl_prog_rem = tk.Label(srow, text="", font=F_MONO_SM, fg=C_FAINT, bg=C_PANEL)
        self.lbl_prog_rem.pack(side="right")
        self.lbl_prog_status = tk.Label(self.view_progress, text="", font=F_MONO_SM,
                                        fg=C_FAINT, bg=C_PANEL, anchor="w")
        self.lbl_prog_status.grid(row=3, column=0, sticky="ew")

        # ---- right: properties (movable panel) ----
        pr = tk.Frame(self, bg=C_PANEL, width=256)
        pr.grid_columnconfigure(0, weight=1)
        pr.grid_rowconfigure(0, weight=1)
        self.panel_props = pr
        # (no title bar: the PROPERTIES tab already names this panel and drags it)
        self.prop_scroll = ctk.CTkScrollableFrame(pr, fg_color="transparent", corner_radius=0,
                                                  scrollbar_button_color=C_LINE2,
                                                  scrollbar_button_hover_color=C_GRAY_TXT)
        self.prop_scroll.grid(row=0, column=0, sticky="nsew")
        self.prop_scroll.grid_columnconfigure(0, weight=1)
        self.prop_body = tk.Frame(self.prop_scroll, bg=C_PANEL)
        self.prop_body.pack(fill="both", expand=True)
        self.build_properties()

    # ================= PROPERTIES =================
    def _psec(self, title):
        h = tk.Frame(self.prop_body, bg=C_PANEL)
        h.pack(fill="x", padx=PAD, pady=(SEC_GAP, 2))
        tk.Label(h, text=title.upper(), font=F_HEAD, fg=C_ACCENT, bg=C_PANEL).pack(side="left")
        tk.Frame(h, bg=C_LINE, height=1).pack(side="left", fill="x", expand=True, padx=(GAP, 0))
        body = tk.Frame(self.prop_body, bg=C_PANEL)
        body.pack(fill="x", padx=PAD)
        return body

    def _prow(self, parent, label):
        r = tk.Frame(parent, bg=C_PANEL)
        r.pack(fill="x", pady=2)
        tk.Label(r, text=label.upper(), font=("Barlow Condensed", 10, "bold"),
                 fg=C_GRAY_TXT, bg=C_PANEL, width=10, anchor="w").pack(side="left")
        box = tk.Frame(r, bg=C_PANEL)
        box.pack(side="right", fill="x", expand=True)
        return box

    def _pentry(self, parent, width=None, justify="left"):
        e = tk.Entry(parent, bg=C_ENTRY, fg=C_TXT, relief="flat", bd=0,
                     highlightthickness=1, highlightbackground=C_LINE2,
                     highlightcolor=C_ACCENT, insertbackground="white", font=F_MONO)
        if width:
            e.configure(width=width)
        e.configure(justify=justify)
        return e

    def _pmenu(self, parent, var, values, on_pick, width=16):
        # CTk dropdown: the native tk.OptionMenu draws an ugly bordered "-"
        # indicator on this theme; CTk draws a clean arrow instead.
        if not values:
            values = ["Auto (file)"]
        try:
            om = ctk.CTkOptionMenu(parent, variable=var, values=list(values),
                                   fg_color=C_ENTRY, button_color=C_LINE2,
                                   button_hover_color=C_HOVER, text_color=C_TXT,
                                   dropdown_fg_color=C_ENTRY,
                                   dropdown_text_color=C_TXT,
                                   dropdown_hover_color=C_ACCENT,
                                   font=F_MONO_SM, dropdown_font=F_MONO_SM,
                                   corner_radius=0, width=width * 8, height=26,
                                   anchor="w")
        except Exception:
            om = tk.OptionMenu(parent, var, *values)
            try:
                om.configure(bg=C_ENTRY, fg=C_TXT, activebackground=C_HOVER,
                             activeforeground="white", relief="flat", bd=0,
                             highlightthickness=0, anchor="w", width=width)
                om["menu"].configure(bg=C_ENTRY, fg=C_TXT, activebackground=C_ACCENT,
                                     activeforeground="white", relief="flat", bd=0)
            except Exception:
                pass
        var.trace_add("write", lambda *a: on_pick())
        return om

    def _pset_menu(self, om, var, values, current):
        try:
            if not values:
                values = ["Auto (file)"]
            is_ctk = om.__class__.__name__ == "CTkOptionMenu"
            if is_ctk:
                try:
                    om.configure(values=list(values))
                except Exception:
                    pass
            else:
                menu = om["menu"]
                menu.delete(0, "end")
                for v in values:
                    menu.add_command(label=v, command=lambda _v=v: var.set(_v))
            self._plock = True
            try:
                if is_ctk:
                    try:
                        om.set(current)
                    except Exception:
                        var.set(current)
                else:
                    var.set(current)
            finally:
                self._plock = False
            try:
                if is_ctk:
                    om.configure(width=max(64, min(170, max(len(str(v)) for v in values) * 8 + 24)))
                else:
                    om.configure(width=max(8, min(20, max(len(str(v)) for v in values) + 1)))
            except Exception:
                pass
        except Exception:
            try:
                self._plock = False
            except Exception:
                pass

    def _mkcheck(self, parent, text, var=None, cmd=None):
        # High-contrast checkbox used EVERYWHERE: oversized box, thick white
        # check on accent fill when on; bright-bordered dark box when off.
        # (Native tk.Checkbutton draws a thin gray check on blue = invisible.)
        kw = dict(text=text, checkbox_width=20, checkbox_height=20,
                  border_width=2, corner_radius=0,
                  fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                  border_color=C_GRAY_TXT, checkmark_color="#ffffff",
                  text_color=C_TXT, font=F_SMALL)
        if var is not None:
            kw["variable"] = var
        if cmd is not None:
            kw["command"] = cmd
        try:
            return ctk.CTkCheckBox(parent, **kw)
        except Exception:
            return tk.Checkbutton(parent, text=text, variable=var, bg=C_PANEL,
                                  fg="white", activebackground=C_PANEL,
                                  activeforeground="white", selectcolor=C_ACCENT,
                                  bd=0, highlightthickness=0,
                                  anchor="w", font=F_SMALL, command=cmd)

    def _pcheck(self, parent, text, var, cmd):
        return self._mkcheck(parent, text, var=var, cmd=cmd)

    def _seg(self, parent, var, options, on_pick, width=7):
        fr = tk.Frame(parent, bg=C_PANEL)
        for i, o in enumerate(options):
            b = tk.Button(fr, text=o, width=width, font=F_MONO, fg=C_GRAY_TXT, bg=C_PANEL,
                          activebackground=C_HOVER, activeforeground="white",
                          relief="flat", bd=0, highlightthickness=1,
                          highlightbackground=C_LINE2,
                          command=lambda _o=o: (var.set(_o), self._seg_paint(fr, var), on_pick()))
            b.grid(row=0, column=i, padx=(0, 1), sticky="ew")
            fr.grid_columnconfigure(i, weight=1)
        self._seg_paint(fr, var)
        return fr

    def _seg_paint(self, fr, var):
        try:
            cur = var.get()
        except Exception:
            return
        try:
            for b in fr.winfo_children():
                try:
                    on = (b.cget("text") == cur)
                    b.configure(bg=C_ACCENT if on else C_PANEL,
                                fg="white" if on else C_GRAY_TXT)
                except Exception:
                    pass
        except Exception:
            pass

    def _abtn(self, parent, text, glyph_name, style, command):
        """Action button: solid / ghost / danger-ghost."""
        img = self._icon(glyph_name, 13, "#ffffff" if style == "solid" else C_GRAY_TXT)
        if style == "solid":
            kw = dict(fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, text_color="white")
        elif style == "danger":
            kw = dict(fg_color="transparent", hover_color=C_ROW, text_color=C_RED,
                      border_width=1, border_color=C_RED)
        else:
            kw = dict(fg_color="transparent", hover_color=C_ROW, text_color=C_TXT,
                      border_width=1, border_color=C_LINE2)
        try:
            b = ctk.CTkButton(parent, text=text, image=img, compound="left",
                              height=BTN_H, corner_radius=0, font=F_BODY, command=command, **kw)
            if img is None:
                b.configure(text=text, image=None)
        except Exception:
            b = ctk.CTkButton(parent, text=text, height=BTN_H, corner_radius=0,
                              font=F_BODY, command=command, **kw)
        return b

    def build_properties(self):
        # ---- BLEND FILE ----
        b = self._psec("Blend file")
        self.lbl_pfile = tk.Label(b, text="No selection", font=F_MONO, fg=C_ACCENT2,
                                  bg=C_PANEL, anchor="w", justify="left")
        self.lbl_pfile.pack(fill="x", pady=(0, 1))
        self.lbl_ppath = tk.Label(b, text="", font=F_MONO_SM, fg=C_GRAY_TXT,
                                  bg=C_PANEL, anchor="w", justify="left", wraplength=220)
        self.lbl_ppath.pack(fill="x")
        ToolTip(self.lbl_ppath, "Full path to the .blend file.")
        self._abtn(b, "OPEN FILE", "folder", "ghost", self.open_blend_file).pack(fill="x", pady=(6, 0))

        # ---- STATUS ----
        b = self._psec("Status")
        srow = tk.Frame(b, bg=C_PANEL)
        srow.pack(fill="x", pady=2)
        self.lbl_pstatus_icon = tk.Label(srow, bg=C_PANEL)
        self.lbl_pstatus_icon.pack(side="left", padx=(0, 6))
        self.lbl_pstatus = tk.Label(srow, text="—", font=("Barlow Condensed", 11, "bold"),
                                    fg=C_GRAY_TXT, bg=C_PANEL)
        self.lbl_pstatus.pack(side="left")

        # ---- RENDER ----
        b = self._psec("Render")
        self.var_pengine = tk.StringVar(value="CYCLES")
        box = self._prow(b, "Engine")
        self.om_pengine = self._pmenu(box, self.var_pengine, ENGINES, self.insp_apply, width=14)
        self.om_pengine.pack(fill="x")
        box = self._prow(b, "Samples")
        self.entry_psamples = self._pentry(box)
        self.entry_psamples.pack(fill="x")
        self.entry_psamples.bind("<FocusOut>", lambda e: self.insp_apply())
        self.entry_psamples.bind("<Return>", lambda e: self.insp_apply())
        self.var_pfilm = tk.BooleanVar(value=False)
        self._pcheck(b, "Film Transparent", self.var_pfilm, self.insp_apply).pack(fill="x", pady=1)

        # ---- SCENE ----
        b = self._psec("Scene")
        self.var_pscene = tk.StringVar(value="Auto (file)")
        box = self._prow(b, "Scene")
        self.om_pscene = self._pmenu(box, self.var_pscene, ["Auto (file)"], self.insp_apply, width=14)
        self.om_pscene.pack(fill="x")
        self.var_pcamera = tk.StringVar(value="Auto (file)")
        box = self._prow(b, "Camera")
        self.om_pcamera = self._pmenu(box, self.var_pcamera, ["Auto (file)"], self.insp_apply, width=14)
        self.om_pcamera.pack(fill="x")
        self.var_player = tk.StringVar(value="Auto (file)")
        box = self._prow(b, "Layer")
        self.om_player = self._pmenu(box, self.var_player, ["Auto (file)"], self.insp_apply, width=14)
        self.om_player.pack(fill="x")
        box = self._prow(b, "Frames")
        self.entry_pframes = self._pentry(box)
        self.entry_pframes.pack(fill="x")
        self.entry_pframes.bind("<FocusOut>", lambda e: self.insp_apply())
        self.entry_pframes.bind("<Return>", lambda e: self.insp_apply())

        # ---- FORMAT ----
        b = self._psec("Format")
        brow = tk.Frame(b, bg=C_PANEL)
        brow.pack(fill="x", pady=(0, 2))
        tk.Button(brow, text="MATCH SOURCE", font=("Barlow Condensed", 9, "bold"), fg=C_ACCENT,
                  bg=C_PANEL, activebackground=C_PANEL, activeforeground=C_ACCENT2,
                  relief="flat", bd=0, highlightthickness=0,
                  command=self.match_source).pack(side="right")
        box = self._prow(b, "Res X")
        self.entry_presx = self._pentry(box, justify="center")
        self.entry_presx.pack(fill="x")
        self.entry_presx.bind("<FocusOut>", lambda e: self.insp_apply())
        self.entry_presx.bind("<Return>", lambda e: self.insp_apply())
        box = self._prow(b, "Res Y")
        self.entry_presy = self._pentry(box, justify="center")
        self.entry_presy.pack(fill="x")
        self.entry_presy.bind("<FocusOut>", lambda e: self.insp_apply())
        self.entry_presy.bind("<Return>", lambda e: self.insp_apply())
        box = self._prow(b, "Scale")
        srow2 = tk.Frame(box, bg=C_PANEL)
        srow2.pack(fill="x")
        self.slider_pscale = ctk.CTkSlider(srow2, from_=10, to=200, height=12,
                                           button_color=C_ACCENT, button_hover_color=C_ACCENT2,
                                           progress_color=C_ACCENT, fg_color=C_LINE,
                                           command=lambda v: self.on_scale_slide(v))
        self.slider_pscale.pack(side="left", fill="x", expand=True)
        self.lbl_pscale = tk.Label(srow2, text="100%", font=F_MONO, fg=C_TXT, bg=C_PANEL, width=5)
        self.lbl_pscale.pack(side="right")
        ToolTip(self.slider_pscale, "Resolution percentage. Drag, release to apply.")

        # ---- OUTPUT ----
        b = self._psec("Output")
        self.entry_poutput = self._pentry(b)
        self.entry_poutput.pack(fill="x", pady=2)
        self.entry_poutput.bind("<FocusOut>", lambda e: self.insp_apply())
        self.entry_poutput.bind("<Return>", lambda e: self.insp_apply())
        orow = tk.Frame(b, bg=C_PANEL)
        orow.pack(fill="x", pady=(0, 2))
        ctk.CTkButton(orow, text="Open", width=70, height=24, corner_radius=0,
                      fg_color="transparent", hover_color=C_ROW, border_width=1,
                      border_color=C_LINE2, font=F_SMALL,
                      command=self.open_selected_output).pack(side="left", padx=(0, 4))
        ctk.CTkButton(orow, text="Browse", width=70, height=24, corner_radius=0,
                      fg_color="transparent", hover_color=C_ROW, border_width=1,
                      border_color=C_LINE2, font=F_SMALL,
                      command=self.browse_selected_output).pack(side="left")
        self.lbl_out_resolved = tk.Label(b, text="", font=F_MONO_SM, fg=C_GREEN,
                                         bg=C_PANEL, anchor="w", justify="left", wraplength=220)
        self.lbl_out_resolved.pack(fill="x", pady=(0, 2))
        box = self._prow(b, "Format")
        self.var_pformat = tk.StringVar(value="PNG")
        self.seg_pformat = self._seg(box, self.var_pformat, ["PNG", "EXR", "JPEG", "TIFF"],
                                    self.insp_apply, width=6)
        self.seg_pformat.pack(fill="x")
        box = self._prow(b, "Color")
        self.var_pcmode = tk.StringVar(value="RGB")
        self.seg_pcmode = self._seg(box, self.var_pcmode, COLOR_MODES, self.insp_apply, width=6)
        self.seg_pcmode.pack(fill="x")
        box = self._prow(b, "Depth")
        self.var_pcdepth = tk.StringVar(value="8")
        self.seg_pcdepth = self._seg(box, self.var_pcdepth, ["8", "16"], self.insp_apply, width=6)
        self.seg_pcdepth.pack(fill="x")

        self.btn_padv = tk.Button(b, text="ADVANCED OUTPUT SETTINGS  ▸", font=("Barlow Condensed", 9, "bold"),
                                  fg=C_GRAY_TXT, bg=C_PANEL, activebackground=C_PANEL,
                                  activeforeground=C_TXT, relief="flat", bd=0, highlightthickness=0,
                                  anchor="w", command=self.toggle_adv)
        self.btn_padv.pack(fill="x", pady=(4, 0))
        self.adv_body = tk.Frame(b, bg=C_PANEL)
        box = self._prow(self.adv_body, "Compress")
        crow = tk.Frame(box, bg=C_PANEL)
        crow.pack(fill="x")
        self.slider_pcompr = ctk.CTkSlider(crow, from_=0, to=100, height=12,
                                           button_color=C_ACCENT, button_hover_color=C_ACCENT2,
                                           progress_color=C_ACCENT, fg_color=C_LINE,
                                           command=lambda v: self.on_compr_slide(v))
        self.slider_pcompr.pack(side="left", fill="x", expand=True)
        self.lbl_pcompr = tk.Label(crow, text="15%", font=F_MONO, fg=C_TXT, bg=C_PANEL, width=4)
        self.lbl_pcompr.pack(side="right")
        self.var_poverwrite = tk.BooleanVar(value=True)
        self._pcheck(self.adv_body, "Overwrite existing frames", self.var_poverwrite,
                     self.insp_apply).pack(fill="x", pady=1)
        self.var_pplaceholder = tk.BooleanVar(value=False)
        self._pcheck(self.adv_body, "Placeholders", self.var_pplaceholder, self.insp_apply).pack(fill="x", pady=1)
        box = self._prow(self.adv_body, "FPS (mp4)")
        self.entry_pfps = self._pentry(box)
        self.entry_pfps.pack(fill="x")
        self.entry_pfps.bind("<FocusOut>", lambda e: self.insp_apply())
        self.entry_pfps.bind("<Return>", lambda e: self.insp_apply())
        tk.Button(self.adv_body, text="RESET TO FILE VALUES", font=("Barlow Condensed", 9, "bold"),
                  fg=C_ACCENT, bg=C_PANEL, activebackground=C_PANEL, activeforeground=C_ACCENT2,
                  relief="flat", bd=0, highlightthickness=0, anchor="w",
                  command=self.reset_to_file).pack(fill="x", pady=(4, 0))

        # ---- PYTHON ----
        b = self._psec("Python")
        self.entry_pyargs = self._pentry(b)
        self.entry_pyargs.pack(fill="x", pady=2)
        try:
            self.entry_pyargs.configure(fg=C_GRAY_TXT)
            self.entry_pyargs.insert(0, "--python-expr ...")
            self.entry_pyargs.bind("<FocusIn>", lambda e: self._pyargs_hint())
        except Exception:
            pass
        self.entry_pyargs.bind("<FocusOut>", lambda e: self.insp_apply())
        self.entry_pyargs.bind("<Return>", lambda e: self.insp_apply())
        ToolTip(self.entry_pyargs, "Extra code ran before each render:\na .py file path or a python expression.")
        self.var_pgui = tk.BooleanVar(value=False)
        self._pcheck(b, "GUI mode render (sim-safe)", self.var_pgui, self.insp_apply).pack(fill="x", pady=1)
        ToolTip(b.winfo_children()[-1], "Render with a visible Blender window.\nNeeded for Hurricane / simulator files.")
        self.lbl_pwarn = tk.Label(b, text="", font=F_SMALL, fg=C_YELLOW,
                                  bg=C_PANEL, anchor="w", justify="left", wraplength=220)
        self.lbl_pwarn.pack(fill="x", pady=2)

        # ---- ACTIONS ----
        b = self._psec("Actions")
        self._abtn(b, "START RENDER", "play", "solid", self.start_render_thread).pack(fill="x", pady=(0, 6))
        self._abtn(b, "CONVERT MP4", "check", "ghost", self.convert_selected_to_mp4).pack(fill="x")

    def _pyargs_hint(self):
        try:
            if self.entry_pyargs.get().strip() in ("--python-expr ...", ""):
                self.entry_pyargs.delete(0, "end")
                self.entry_pyargs.configure(fg=C_TXT)
        except Exception:
            pass

    def toggle_adv(self):
        try:
            if self.adv_body.winfo_ismapped():
                self.adv_body.pack_forget()
                self.btn_padv.configure(text="ADVANCED OUTPUT SETTINGS  ▸")
            else:
                self.adv_body.pack(fill="x")
                self.btn_padv.configure(text="ADVANCED OUTPUT SETTINGS  ▾")
        except Exception:
            pass

    def on_scale_slide(self, v):
        try:
            self.lbl_pscale.configure(text="{}%".format(int(float(v))))
        except Exception:
            pass
        try:
            if self._scale_after is not None:
                self.after_cancel(self._scale_after)
        except Exception:
            pass
        try:
            self._scale_after = self.after(350, self.insp_apply)
        except Exception:
            pass

    def on_compr_slide(self, v):
        try:
            self.lbl_pcompr.configure(text="{}%".format(int(float(v))))
        except Exception:
            pass
        try:
            if self._compr_after is not None:
                self.after_cancel(self._compr_after)
        except Exception:
            pass
        try:
            self._compr_after = self.after(350, self.insp_apply)
        except Exception:
            pass

    def reset_to_file(self):
        idx = self.selected_idx
        if idx is None:
            return
        item = self.config["queue_list"][idx]
        for k in ("engine", "samples", "res_x", "res_y", "res_pct", "film_transparent",
                  "overwrite", "placeholder", "file_format", "color_mode", "color_depth",
                  "compression"):
            item[k] = None
        item["ov"] = {"res_x": False, "res_y": False, "scale": False,
                      "overwrite": False, "placeholder": False}
        item["scene"] = None
        item["camera"] = None
        item["view_layer"] = None
        item["frame_start"] = None
        item["frame_end"] = None
        item["output"] = None
        item["fps"] = None
        item["python_args"] = ""
        item["gui_mode"] = None
        save_config(self.config)
        self.refresh_inspector()
        self.refresh_row(idx)

    def open_blend_file(self):
        idx = self.selected_idx
        if idx is None:
            return
        try:
            p = self.config["queue_list"][idx].get("path", "")
            if os.path.exists(p):
                if os.name == "nt":
                    os.startfile(p)
                else:
                    import subprocess as _sp
                    _sp.Popen(["xdg-open", p])
        except Exception as e:
            messagebox.showerror("Open", str(e))

    def browse_py_script(self):
        p = filedialog.askopenfilename(filetypes=[("Python", "*.py"), ("All", "*.*")])
        if p:
            try:
                self.entry_pyargs.delete(0, "end")
                self.entry_pyargs.insert(0, p)
                try:
                    self.entry_pyargs.configure(fg=C_TXT)
                except Exception:
                    pass
            except Exception:
                pass
            self.insp_apply()

    def browse_selected_output(self):
        d = filedialog.askdirectory(title="Output folder (use #### for frame numbers in name if needed)")
        if d:
            self.entry_poutput.delete(0, "end")
            self.entry_poutput.insert(0, d + "/")
            self.insp_apply()

    def open_selected_output(self):
        idx = self.selected_idx
        if idx is None:
            return
        try:
            item = self.config["queue_list"][idx]
            eff = effective_job_settings(item, item.get("probe"))
            folder = resolve_output_dir(eff["output"], item.get("path", ""))
        except Exception as e:
            messagebox.showerror("Output", str(e))
            return
        # Explorer can stall for seconds (AV, network, thumb cache): never
        # block the UI on it
        threading.Thread(target=self._open_folder_thread, args=(folder,), daemon=True).start()

    def _open_folder_thread(self, folder):
        try:
            if os.path.isdir(folder):
                os.startfile(folder)
            else:
                try:
                    self.after(0, lambda: messagebox.showinfo(
                        "Output", "Folder does not exist yet:\n{}".format(folder)))
                except Exception:
                    pass
        except Exception as e:
            try:
                self.after(0, lambda: messagebox.showerror("Output", str(e)))
            except Exception:
                pass

    def _popup_menu(self, m):
        # post() never grabs, so a stuck/invisible menu can never freeze the app
        # (tk_popup's grab did exactly that in some sessions).
        try:
            m.post(self.winfo_pointerx(), self.winfo_pointery())
            m.bind("<FocusOut>", lambda e, _m=m: self._safe_unpost(_m))
        except Exception:
            pass

    def _safe_unpost(self, m):
        try:
            m.unpost()
        except Exception:
            pass

    # ================= DOCKABLE LAYOUT =================
    TAB_H = 26
    COLLAPSED_W = 26

    def _build_slot_chrome(self, slot, outer):
        """Tab bar + split paned per slot. The secondary group (bar2/body2)
        is built once but only added to the paned on an edge-split drop."""
        try:
            self.slot_tabs.setdefault(slot, {})
        except Exception:
            self.slot_tabs = {slot: {}}
        bar = tk.Frame(outer, bg=C_BG, height=self.TAB_H)
        bar.pack(side="top", fill="x")
        try:
            bar.pack_propagate(False)
        except Exception:
            pass
        self.slot_bar[slot] = bar
        plus = tk.Button(bar, text="+", font=F_SMALL, fg=C_FAINT, bg=C_BG,
                         activebackground=C_HOVER, activeforeground="white",
                         relief="flat", bd=0, highlightthickness=0, width=3,
                         command=lambda s=slot: self._slot_plus_menu(s, "main"))
        plus.pack(side="right", fill="y", padx=(1, 2))
        ToolTip(plus, "Show a hidden panel here")
        paned = tk.PanedWindow(outer, orient="horizontal", bg=C_LINE, bd=0,
                               sashwidth=5, sashrelief="flat", showhandle=False,
                               opaqueresize=False)
        paned.pack(side="top", fill="both", expand=True)
        try:
            paned.bind("<ButtonRelease-1>",
                       lambda e, s=slot: self.after(100, lambda: self._save_split_frac(s)))
        except Exception:
            pass
        self.slot_pane[slot] = paned
        body = tk.Frame(paned, bg=C_BG)
        try:
            paned.add(body, minsize=100, sticky="nsew", stretch="always")
        except Exception:
            pass
        self.slot_body[slot] = body
        hint = tk.Label(body, text="Drop panels here   •   + to add",
                        font=F_SMALL, fg=C_FAINT, bg=C_BG)
        self.slot_hint[slot] = hint
        # secondary group (hidden until an edge split)
        g2 = tk.Frame(paned, bg=C_BG)
        bar2 = tk.Frame(g2, bg=C_BG, height=self.TAB_H)
        bar2.pack(side="top", fill="x")
        try:
            bar2.pack_propagate(False)
        except Exception:
            pass
        plus2 = tk.Button(bar2, text="+", font=F_SMALL, fg=C_FAINT, bg=C_BG,
                          activebackground=C_HOVER, activeforeground="white",
                          relief="flat", bd=0, highlightthickness=0, width=3,
                          command=lambda s=slot: self._slot_plus_menu(s, "split"))
        plus2.pack(side="right", fill="y", padx=(1, 2))
        ToolTip(plus2, "Show a hidden panel here")
        body2 = tk.Frame(g2, bg=C_BG)
        body2.pack(side="top", fill="both", expand=True)
        self.slot_gframe[slot] = g2
        self.slot_bar2[slot] = bar2
        self.slot_body2[slot] = body2

    def _tab_text(self, panel):
        try:
            if panel == "queue":
                return "QUEUE ({})".format(len(self.config.get("queue_list", [])))
        except Exception:
            pass
        return PANEL_TITLES.get(panel, panel)

    def _refresh_queue_tab(self):
        """Keep the QUEUE tab's job count current wherever it is docked."""
        try:
            slot = self._slot_of("queue")
            if slot is None:
                return
            b = (self.slot_tabs.get(slot) or {}).get("queue")
            if b is not None:
                b.configure(text=self._tab_text("queue"))
        except Exception:
            pass

    def _make_tab(self, slot, bar, name, group):
        try:
            b = tk.Button(bar, text=self._tab_text(name), font=F_SMALL,
                          relief="flat", bd=0, highlightthickness=0, padx=10,
                          anchor="w", cursor="fleur",
                          command=lambda n=name, s=slot, g=group: self._activate_tab(s, n, g))
            b._brm_panel = name
            b._brm_group = group
            b.pack(side="left", padx=(0, 1), fill="y")
            b.bind("<ButtonPress-1>", lambda e, n=name: self._tab_press(e, n))
            b.bind("<B1-Motion>", lambda e, n=name: self._tab_motion(e, n))
            b.bind("<ButtonRelease-1>",
                   lambda e, s=slot, n=name: self._tab_release(e, s, n))
            b.bind("<Double-Button-1>", lambda e, n=name: self.close_panel(n))
            b.bind("<Button-3>", lambda e, n=name: self._tab_menu(e, n))
            ToolTip(b, "Drag to move • double-click to hide • drop at a slot edge to split")
            return b
        except Exception:
            return None

    def _rebuild_tabs(self, slot):
        for b in list((self.slot_tabs.get(slot) or {}).values()):
            try:
                b.destroy()
            except Exception:
                pass
        tabs = {}
        try:
            groups = [("main", self.slot_bar[slot], self.layout.get(slot, []))]
            sp = (self.layout_split or {}).get(slot)
            if isinstance(sp, dict) and sp.get("tabs"):
                groups.append(("split", self.slot_bar2[slot], sp.get("tabs")))
            for group, bar, names in groups:
                for name in names:
                    b = self._make_tab(slot, bar, name, group)
                    if b is not None:
                        tabs[name] = b
        except Exception:
            pass
        self.slot_tabs[slot] = tabs

    def _paint_tabs(self, slot):
        try:
            for name, b in (self.slot_tabs.get(slot) or {}).items():
                try:
                    group = getattr(b, "_brm_group", "main")
                    active = self._group_active(slot, group)
                    if name == active:
                        b.configure(bg=C_LINE2, fg="white")
                    else:
                        b.configure(bg=C_BG, fg=C_GRAY_TXT)
                except Exception:
                    pass
        except Exception:
            pass

    def _activate_tab(self, slot, panel, group="main"):
        try:
            if panel not in self._group_tabs(slot, group):
                return
            self._set_group_active(slot, group, panel)
            self._show_panel_widget(slot)
            self._paint_tabs(slot)
            try:
                if panel == "view":
                    self._vp_sync_visibility()
                    self.after(150, self._vp_sync_visibility)
            except Exception:
                pass
            try:
                self.config["layout_active"] = {s: a for s, a in
                                                self.layout_active.items() if a}
                self.config["layout_split"] = self._serial_split()
                save_config(self.config)
            except Exception:
                pass
        except Exception:
            pass

    def _show_panel_widget(self, slot):
        """Pack each group's active tab into its own body; park the rest.
        Only this slot's own panels are touched (other slots manage theirs)."""
        try:
            bodies = (("main", self.slot_body[slot]),)
            try:
                if self._has_split(slot):
                    bodies = bodies + (("split", self.slot_body2[slot]),)
            except Exception:
                pass
            for group, body in bodies:
                names = self._group_tabs(slot, group)
                active = self._group_active(slot, group)
                for name in names:
                    try:
                        w = self._panel_widget(name)
                    except Exception:
                        continue
                    try:
                        if name == active:
                            w.pack(in_=body, fill="both", expand=True)
                        else:
                            w.pack_forget()
                    except Exception:
                        pass
            try:
                hint = self.slot_hint.get(slot)
                if hint is not None:
                    if names:
                        hint.pack_forget()
                    else:
                        hint.pack(fill="both", expand=True, pady=8)
            except Exception:
                pass
        except Exception:
            pass

    def _render_split(self, slot):
        """Add/forget the secondary group pane; sash follows saved frac."""
        try:
            paned = self.slot_pane.get(slot)
            g2 = self.slot_gframe.get(slot)
            if paned is None or g2 is None:
                return
            sp = (self.layout_split or {}).get(slot)
            try:
                panes = [str(p) for p in paned.panes()]
            except Exception:
                panes = []
            if isinstance(sp, dict) and sp.get("tabs"):
                if str(g2) not in panes:
                    try:
                        if sp.get("side") == "left":
                            paned.add(g2, before=str(self.slot_body[slot]))
                        else:
                            paned.add(g2)
                    except Exception:
                        try:
                            paned.add(g2)
                        except Exception:
                            pass
                try:
                    paned.paneconfigure(g2, minsize=120, stretch="always")
                    paned.paneconfigure(self.slot_body[slot], minsize=120,
                                        stretch="always")
                except Exception:
                    pass
            else:
                if str(g2) in panes:
                    try:
                        paned.forget(g2)
                    except Exception:
                        pass
        except Exception:
            pass

    def _apply_all_split_fracs(self):
        try:
            for s in SLOTS:
                self._apply_split_frac(s)
        except Exception:
            pass

    def _apply_split_frac(self, slot):
        try:
            sp = (self.layout_split or {}).get(slot)
            if not sp:
                return
            paned = self.slot_pane.get(slot)
            total = paned.winfo_width()
            if total < 120:
                return
            frac = min(0.85, max(0.15, float(sp.get("frac", 0.65))))
            if sp.get("side") == "left":
                pos = int((1.0 - frac) * total)
            else:
                pos = int(frac * total)
            try:
                paned.sash_place(0, pos, 0)
            except Exception:
                pass
        except Exception:
            pass

    def _save_split_frac(self, slot):
        try:
            sp = (self.layout_split or {}).get(slot)
            paned = self.slot_pane.get(slot)
            if not sp or paned is None:
                return
            try:
                x, _y = paned.sash_coord(0)
            except Exception:
                return
            total = paned.winfo_width()
            if total < 120:
                return
            f = float(x) / float(total)
            if sp.get("side") == "left":
                f = 1.0 - f
            sp["frac"] = round(min(0.85, max(0.15, f)), 3)
            try:
                self.config["layout_split"] = self._serial_split()
                save_config(self.config)
            except Exception:
                pass
        except Exception:
            pass

    def _slot_band_geom(self, slot):
        """(rx, ry, rw, rh, edge) of the splittable body area, or None when
        the slot is empty/split (no edge trays there)."""
        try:
            if self._has_split(slot) or not self.layout.get(slot):
                return None
            body = self.slot_body.get(slot)
            rx, ry = body.winfo_rootx(), body.winfo_rooty()
            rw, rh = body.winfo_width(), body.winfo_height()
            if rw < 40 or rh < 20:
                return None
            return (rx, ry, rw, rh, max(64, min(160, int(rw * 0.25))))
        except Exception:
            return None

    def _slot_band(self, slot, x, y):
        """(band, group) for a drop point. Tab-bar drops and split slots
        resolve to tab flow ("center"); a body edge band of an unsplit slot
        means "split here" ("left"/"right")."""
        try:
            if not self.layout.get(slot):
                return ("center", "main")
            if self._has_split(slot):
                return ("center", self._group_at(slot, x, y))
            try:
                bar = self.slot_bar.get(slot)
                if (bar is not None and bar.winfo_rootx() <= x
                        < bar.winfo_rootx() + bar.winfo_width()
                        and bar.winfo_rooty() <= y
                        < bar.winfo_rooty() + bar.winfo_height()):
                    return ("center", "main")
            except Exception:
                pass
            g = self._slot_band_geom(slot)
            if g is None:
                return ("center", "main")
            rx, ry, rw, rh, edge = g
            if not (rx <= x < rx + rw and ry <= y < ry + rh):
                return ("center", "main")
            if x - rx < edge:
                return ("left", "main")
            if rx + rw - x <= edge:
                return ("right", "main")
            return ("center", "main")
        except Exception:
            pass
        return ("center", "main")

    def _group_at(self, slot, x, y):
        """Which tab group is under a point (split slots only)."""
        try:
            groups = (("split", (self.slot_bar2.get(slot), self.slot_body2.get(slot))),
                      ("main", (self.slot_bar.get(slot), self.slot_body.get(slot))))
            for grp, widgets in groups:
                for w in widgets:
                    try:
                        if (w is not None and w.winfo_ismapped()
                                and w.winfo_rootx() <= x
                                < w.winfo_rootx() + w.winfo_width()
                                and w.winfo_rooty() <= y
                                < w.winfo_rooty() + w.winfo_height()):
                            return grp
                    except Exception:
                        continue
        except Exception:
            pass
        return "main"

    def _split_slot(self, slot, side, panel):
        """Edge-band drop: panel becomes a secondary group on `side`."""
        try:
            self._detach_panel(panel)
            self.layout_split[slot] = {"side": side, "frac": 0.65,
                                       "tabs": [panel], "active": panel}
            self.apply_layout()
            try:
                self._flash_tab(slot, panel)
            except Exception:
                pass
            self.log("Split {} panel.".format(PANEL_TITLES.get(panel, panel)))
        except Exception:
            pass

    def _rebalance_stretch(self):
        """Free window width must land somewhere: normally only a non-empty
        center absorbs it (sidebars keep their set widths); with center gone
        the remaining side slots share it; with all three empty the left
        strip grows into a big drop zone. Without this the leftover shows as
        bare paned background (gray void)."""
        try:
            nonempty = [s for s in ("left", "center", "right")
                        if self.layout.get(s)]
            if "center" in nonempty:
                holders = {"center"}
            elif nonempty:
                holders = set(nonempty)
            else:
                holders = {"left"}
            for s in ("left", "center", "right"):
                try:
                    self.main_paned.paneconfigure(
                        self.slot_frames[s],
                        stretch="always" if s in holders else "never")
                except Exception:
                    pass
        except Exception:
            pass

    def _set_slot_collapsed(self, slot, collapsed):
        """Empty slots shrink to a slim strip (stay valid drop targets)."""
        try:
            pane = self.slot_pane[slot]
            if slot == "bottom":
                try:
                    in_vert = [str(p) for p in self.vert_paned.panes()]
                except Exception:
                    in_vert = []
                if collapsed:
                    if str(self.slot_bottom) in in_vert:
                        try:
                            self.vert_paned.forget(self.slot_bottom)
                        except Exception:
                            pass
                else:
                    if str(self.slot_bottom) not in in_vert:
                        try:
                            self.vert_paned.add(self.slot_bottom, minsize=60,
                                                sticky="nsew", stretch="never")
                        except Exception:
                            pass
                    self._apply_bottom_height()
                return
            fr = self.slot_frames[slot]
            if collapsed:
                try:
                    w = fr.winfo_width()
                    if w > 60:
                        self._slot_w[slot] = w
                except Exception:
                    pass
                pane.pack_forget()
                self.main_paned.paneconfigure(fr, width=self.COLLAPSED_W,
                                              minsize=self.COLLAPSED_W)
            else:
                pane.pack(side="top", fill="both", expand=True)
                self.main_paned.paneconfigure(
                    fr, width=max(140, int(self._slot_w.get(slot, 280))),
                    minsize=120)
        except Exception:
            pass

    def _apply_bottom_height(self):
        try:
            h = getattr(self, "_bottom_h", None)
            if h and int(h) >= 80:
                self.vert_paned.paneconfigure(self.slot_bottom, height=int(h))
        except Exception:
            pass

    # ---- tab drag (press-hold threshold so clicks still activate) ----
    def _tab_press(self, event, panel):
        try:
            self._tab_down = {"panel": panel, "x": event.x_root, "y": event.y_root,
                              "dragging": False}
        except Exception:
            self._tab_down = None

    def _tab_motion(self, event, panel):
        try:
            d = getattr(self, "_tab_down", None)
            if not d or d.get("panel") != panel:
                return
            if d.get("dragging"):
                self._drag_move(event)
                return
            if abs(event.x_root - d.get("x", 0)) + abs(event.y_root - d.get("y", 0)) > 6:
                d["dragging"] = True
                self._drag_start(event, panel)
                self._drag_move(event)
        except Exception:
            pass

    def _tab_release(self, event, slot, panel):
        try:
            d = getattr(self, "_tab_down", None)
            self._tab_down = None
            if d and d.get("dragging") and (getattr(self, "_drag", None) or {}).get("panel") == panel:
                self._drag_end(event)
            else:
                try:
                    group = getattr(event.widget, "_brm_group", "main")
                except Exception:
                    group = "main"
                self._activate_tab(slot, panel, group)
        except Exception:
            pass

    def _flash_tab(self, slot, panel):
        """Briefly flare the landed tab so the drop target is unmistakable."""
        try:
            b = (self.slot_tabs.get(slot) or {}).get(panel)
            if b is None:
                return
            b.configure(bg=C_ACCENT, fg="white")
            self.after(650, lambda: self._paint_tabs(slot))
        except Exception:
            pass

    def _tab_menu(self, event, panel):
        try:
            m = tk.Menu(self, tearoff=0)
            m.add_command(label="Hide {}".format(PANEL_TITLES.get(panel, panel)),
                          command=lambda: self.close_panel(panel))
            hid = [p for p in PANELS if self._slot_of(p) is None]
            if hid:
                m.add_separator()
                for p in hid:
                    m.add_command(label="Show {}".format(PANEL_TITLES.get(p, p)),
                                  command=lambda p=p: self.show_panel(p))
            self._popup_menu(m)
        except Exception:
            pass

    def _slot_plus_menu(self, slot, group="main"):
        try:
            m = tk.Menu(self, tearoff=0)
            hid = [p for p in PANELS if self._slot_of(p) is None]
            if not hid:
                m.add_command(label="All panels visible", state="disabled")
            for p in hid:
                m.add_command(label="Show {}".format(PANEL_TITLES.get(p, p)),
                              command=lambda p=p: self.show_panel(p, slot, group))
            self._popup_menu(m)
        except Exception:
            pass

    # ---- hide / show panels ----
    def close_panel(self, panel):
        try:
            slot, group = self._panel_group(panel)
            if slot is None:
                return
            names = [p for p in self._group_tabs(slot, group) if p != panel]
            self._set_group_tabs(slot, group, names)
            if panel not in self.layout_hidden:
                self.layout_hidden.append(panel)
            self.apply_layout()
            self.log("{} hidden — Panels menu to re-show.".format(
                PANEL_TITLES.get(panel, panel)))
        except Exception:
            pass

    def show_panel(self, panel, slot=None, group="main"):
        try:
            cur, cgroup = self._panel_group(panel)
            if cur is not None:
                self._activate_tab(cur, panel, cgroup)
                return
            if slot not in SLOTS:
                slot = (self.layout_home or {}).get(panel)
            if slot not in SLOTS:
                for s, names in DEFAULT_LAYOUT.items():
                    if panel in names:
                        slot = s
                        break
            slot = slot if slot in SLOTS else "center"
            if group == "split" and not self._has_split(slot):
                group = "main"
            if panel in self.layout_hidden:
                self.layout_hidden.remove(panel)
            names = [p for p in self._group_tabs(slot, group) if p != panel] + [panel]
            self._set_group_tabs(slot, group, names)
            self._set_group_active(slot, group, panel)
            self.apply_layout()
        except Exception:
            pass

    def toggle_panel(self, panel):
        try:
            if self._slot_of(panel) is None:
                self.show_panel(panel)
            else:
                self.close_panel(panel)
        except Exception:
            pass

    def _valid_layout(self, lay, hidden=(), placed=()):
        """Accept {slot: [panels]} (slots may be EMPTY); migrate legacy
        {slot: panel} strings (progress joins bottom); drop unknown names,
        first occurrence wins; panels listed nowhere (and neither hidden nor
        already placed in an edge split) return to their default slot;
        anything else falls back to default."""
        try:
            if isinstance(lay, dict) and set(lay.keys()) == set(SLOTS):
                if all(isinstance(v, str) for v in lay.values()):
                    conv = {s: [lay[s]] for s in SLOTS}
                    conv["bottom"] = ["prog"] + conv["bottom"]
                    lay = conv
                if all(isinstance(v, list) for v in lay.values()):
                    out = {s: [] for s in SLOTS}
                    seen = set()
                    for s in SLOTS:
                        for p in lay.get(s, []):
                            if p in PANELS and p not in seen:
                                seen.add(p)
                                out[s].append(p)
                    missing = {p for p in PANELS
                               if p not in seen and p not in (hidden or ())
                               and p not in (placed or ())}
                    for s in SLOTS:
                        dflt = list(DEFAULT_LAYOUT[s])
                        miss = [p for p in dflt if p in missing]
                        if miss:
                            have = out[s]
                            out[s] = sorted(
                                have + miss,
                                key=lambda p: dflt.index(p) if p in dflt else 999)
                    return out
        except Exception:
            pass
        return {s: list(v) for s, v in DEFAULT_LAYOUT.items()}

    def _slot_of(self, panel):
        try:
            return self._panel_group(panel)[0]
        except Exception:
            pass
        return None

    # ---- tab groups (primary + optional edge-split secondary) ----
    def _group_tabs(self, slot, group):
        try:
            if group == "split":
                sp = (self.layout_split or {}).get(slot) or {}
                return list(sp.get("tabs") or [])
            return list(self.layout.get(slot) or [])
        except Exception:
            return []

    def _group_active(self, slot, group):
        try:
            if group == "split":
                sp = (self.layout_split or {}).get(slot) or {}
                a = sp.get("active")
                return a if a in (sp.get("tabs") or []) else None
            a = (self.layout_active or {}).get(slot)
            return a if a in (self.layout.get(slot) or []) else None
        except Exception:
            return None

    def _panel_group(self, panel):
        """(slot, group) owning a panel; (None, None) if hidden/unknown."""
        try:
            for s in SLOTS:
                if panel in (self.layout.get(s) or []):
                    return (s, "main")
                sp = (self.layout_split or {}).get(s) or {}
                if panel in (sp.get("tabs") or []):
                    return (s, "split")
        except Exception:
            pass
        return (None, None)

    def _has_split(self, slot):
        try:
            sp = (self.layout_split or {}).get(slot)
            return bool(isinstance(sp, dict) and sp.get("tabs"))
        except Exception:
            return False

    def _set_group_tabs(self, slot, group, names):
        try:
            if group == "split":
                sp = (self.layout_split or {}).get(slot)
                if isinstance(sp, dict):
                    sp["tabs"] = list(names)
                    if sp.get("active") not in names:
                        sp["active"] = names[0] if names else None
            else:
                self.layout[slot] = list(names)
        except Exception:
            pass

    def _set_group_active(self, slot, group, panel):
        try:
            if group == "split":
                sp = (self.layout_split or {}).get(slot)
                if isinstance(sp, dict):
                    sp["active"] = panel
            else:
                self.layout_active[slot] = panel
        except Exception:
            pass

    def _detach_panel(self, panel):
        cur, cgroup = self._panel_group(panel)
        if cur is None:
            return (None, None)
        try:
            names = [p for p in self._group_tabs(cur, cgroup) if p != panel]
            self._set_group_tabs(cur, cgroup, names)
        except Exception:
            pass
        return (cur, cgroup)

    def _valid_split(self, sp):
        try:
            if not isinstance(sp, dict):
                return None
            tabs = [p for p in (sp.get("tabs") or []) if p in PANELS]
            if not tabs:
                return None
            side = sp.get("side")
            if side not in ("left", "right"):
                side = "right"
            try:
                frac = float(sp.get("frac", 0.65))
            except Exception:
                frac = 0.65
            frac = min(0.85, max(0.15, frac))
            active = sp.get("active")
            return {"side": side, "frac": frac, "tabs": tabs,
                    "active": active if active in tabs else tabs[0]}
        except Exception:
            return None

    def _serial_split(self):
        try:
            return {s: {"side": v.get("side", "right"),
                        "frac": float(v.get("frac", 0.65)),
                        "tabs": list(v.get("tabs") or []),
                        "active": v.get("active")}
                    for s, v in (self.layout_split or {}).items()
                    if isinstance(v, dict) and v.get("tabs")}
        except Exception:
            return {}

    def _panel_widget(self, panel):
        return {"queue": self.panel_queue, "view": self.panel_view,
                "prog": self.panel_prog, "props": self.panel_props,
                "log": self.panel_log}[panel]

    def apply_layout(self):
        """Dock panels into tabbed slots. Empty slots collapse to a slim
        strip (stay valid drop targets); hidden panels stay out. Backend
        widgets are untouched."""
        try:
            try:
                saved_hidden = list(self.config.get("layout_hidden") or [])
            except Exception:
                saved_hidden = []
            try:
                for p in (getattr(self, "layout_hidden", None) or []):
                    if p not in saved_hidden:
                        saved_hidden.append(p)
            except Exception:
                pass
            try:
                raw_split = getattr(self, "layout_split", None) or {}
            except Exception:
                raw_split = {}
            placed = set()
            for _s in SLOTS:
                try:
                    _v = self._valid_split(raw_split.get(_s))
                except Exception:
                    _v = None
                if _v is not None:
                    placed.update(_v.get("tabs") or [])
            self.layout = self._valid_layout(self.layout, saved_hidden, placed)
        except Exception:
            self.layout = {s: list(v) for s, v in DEFAULT_LAYOUT.items()}
        try:
            # validate edge splits: primary wins dupes, empty secondary dies,
            # orphaned secondary promotes back to primary tabs
            try:
                raw = getattr(self, "layout_split", None) or {}
            except Exception:
                raw = {}
            split = {}
            for s in SLOTS:
                v = self._valid_split(raw.get(s))
                if v is not None:
                    split[s] = v
            prim = {p for s in SLOTS for p in self.layout.get(s, [])}
            for s in SLOTS:
                sp = split.get(s)
                if not sp:
                    continue
                seen2 = set()
                kept = []
                for p in sp["tabs"]:
                    if p not in prim and p not in seen2:
                        seen2.add(p)
                        kept.append(p)
                sp["tabs"] = kept
                if not kept:
                    del split[s]
                    continue
                if sp.get("active") not in kept:
                    sp["active"] = kept[0]
                if not self.layout.get(s):
                    self.layout[s] = kept
                    del split[s]
            self.layout_split = split
            flat = [p for s in SLOTS for p in self.layout.get(s, [])]
            for s in SLOTS:
                sp = split.get(s)
                if sp:
                    flat.extend([p for p in sp["tabs"] if p not in flat])
            hidden = [p for p in saved_hidden if p in PANELS and p not in flat]
            for p in PANELS:
                if p not in flat and p not in hidden:
                    for s, names in DEFAULT_LAYOUT.items():
                        if p in names:
                            self.layout.setdefault(s, []).append(p)
                            flat.append(p)
                            break
            self.layout_hidden = hidden
            try:
                act = dict(self.config.get("layout_active") or {})
            except Exception:
                act = {}
            try:
                act.update(getattr(self, "layout_active", None) or {})
            except Exception:
                pass
            if not hasattr(self, "layout_active") or not isinstance(self.layout_active, dict):
                self.layout_active = {}
            for s in SLOTS:
                names = self.layout.get(s, [])
                a = act.get(s)
                self.layout_active[s] = a if a in names else (names[0] if names else None)
            if not hasattr(self, "layout_home") or not isinstance(self.layout_home, dict):
                self.layout_home = {}
            for p in PANELS:
                try:
                    self._panel_widget(p).pack_forget()
                except Exception:
                    pass
            for s in SLOTS:
                self._rebuild_tabs(s)
                self._paint_tabs(s)
                self._show_panel_widget(s)
                self._render_split(s)
                self._set_slot_collapsed(s, not self.layout.get(s))
                for p in self.layout.get(s, []):
                    self.layout_home[p] = s
                sp = split.get(s)
                if sp:
                    for p in sp["tabs"]:
                        self.layout_home[p] = s
            self._rebalance_stretch()
            self._vp_sync_visibility()
            try:
                # geometry settles after this call: re-sync once mapped
                self.after(150, self._vp_sync_visibility)
            except Exception:
                pass
            self.config["layout"] = {s: list(v) for s, v in self.layout.items()}
            self.config["layout_hidden"] = list(self.layout_hidden)
            self.config["layout_active"] = {s: a for s, a in
                                            self.layout_active.items() if a}
            self.config["layout_split"] = self._serial_split()
            save_config(self.config)
            try:
                self.after(80, self._apply_all_split_fracs)
            except Exception:
                pass
        except Exception:
            pass

    def _slot_index_at(self, x, y, slot, group="main"):
        """Tab insertion index from the drop x (all tab bars run horizontally)."""
        try:
            names = [p for p in self._group_tabs(slot, group)
                     if p != (getattr(self, "_drag", None) or {}).get("panel")]
            tabs = self.slot_tabs.get(slot, {}) if hasattr(self, "slot_tabs") else {}
            xs = []
            for name in names:
                try:
                    w = tabs.get(name)
                    xs.append(w.winfo_rootx() + w.winfo_width() // 2)
                except Exception:
                    xs.append(x)
            i = 0
            for cx in xs:
                if x >= cx:
                    i += 1
                else:
                    break
            return i
        except Exception:
            pass
        return 0

    def _save_pane_sizes(self):
        """Persist side widths + bottom height. Each side saves independently
        (a collapsed 26px strip must never block the others)."""
        try:
            sizes = dict(self.config.get("layout_sizes") or {})
            for s in ("left", "center", "right"):
                try:
                    if not self.layout.get(s):
                        continue  # empty slot: keep last meaningful width
                    w = self.slot_frames[s].winfo_width()
                except Exception:
                    continue
                if w >= 20:
                    sizes[s] = int(w)
                    try:
                        if w > 60:
                            self._slot_w[s] = int(w)
                    except Exception:
                        pass
            try:
                if self.layout.get("bottom"):
                    bh = self.slot_bottom.winfo_height()
                    if bh >= 40:
                        sizes["bottom"] = int(bh)
                        self._bottom_h = int(bh)
            except Exception:
                pass
            self.config["layout_sizes"] = sizes
            save_config(self.config)
        except Exception:
            pass

    def _restore_pane_sizes(self):
        """Re-apply saved widths/heights (skips collapsed/empty slots)."""
        try:
            sizes = self.config.get("layout_sizes") or {}
            for s in ("left", "center", "right"):
                try:
                    w = int(sizes.get(s, 0))
                except Exception:
                    w = 0
                if w >= 60 and self.layout.get(s):
                    try:
                        self._slot_w[s] = w
                        self.main_paned.paneconfigure(self.slot_frames[s], width=w)
                    except Exception:
                        pass
            try:
                bh = int(sizes.get("bottom", 0))
            except Exception:
                bh = 0
            if bh >= 80 and self.layout.get("bottom"):
                self._bottom_h = bh
                self._apply_bottom_height()
        except Exception:
            pass

    # ---- window + queue UI state ----
    def _apply_saved_geometry(self):
        try:
            g = _validate_geometry(self.config.get("geometry") or "",
                                   self.winfo_screenwidth(),
                                   self.winfo_screenheight())
            if g:
                self.geometry(g)
        except Exception:
            pass

    def _on_win_configure(self, event):
        try:
            if event is None or getattr(event, "widget", None) is not self:
                return
            if getattr(self, "_geo_after", None):
                try:
                    self.after_cancel(self._geo_after)
                except Exception:
                    pass
            self._geo_after = self.after(800, self._save_geometry_only)
        except Exception:
            pass

    def _save_geometry_only(self):
        try:
            self._geo_after = None
            g = self.geometry()
            if _validate_geometry(g, self.winfo_screenwidth(),
                                  self.winfo_screenheight()):
                self.config["geometry"] = g
                save_config(self.config)
        except Exception:
            pass

    def _restore_scroll(self, frac):
        try:
            self.rows_scroll._parent_canvas.yview_moveto(
                max(0.0, min(0.99, float(frac))))
        except Exception:
            pass

    def _save_ui_state(self):
        """Window geometry + slot sizes + queue selection/scroll. Best effort."""
        try:
            self._save_pane_sizes()
        except Exception:
            pass
        try:
            try:
                self.update_idletasks()
            except Exception:
                pass
            try:
                g = self.geometry()
                if _validate_geometry(g, self.winfo_screenwidth(),
                                      self.winfo_screenheight()):
                    self.config["geometry"] = g
            except Exception:
                pass
            try:
                if (self.selected_idx is not None
                        and 0 <= self.selected_idx < len(self.config["queue_list"])):
                    self.config["selected_path"] = (
                        self.config["queue_list"][self.selected_idx].get("path", ""))
                else:
                    self.config["selected_path"] = ""
            except Exception:
                pass
            try:
                yv = self.rows_scroll._parent_canvas.yview()
                self.config["queue_scroll"] = float(yv[0]) if yv else 0.0
            except Exception:
                pass
            save_config(self.config)
        except Exception:
            pass

    def _terminate_child(self, proc):
        try:
            if proc is None:
                return
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=4)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        except Exception:
            pass

    def _on_close(self):
        try:
            self._save_ui_state()
        except Exception:
            pass
        # never leave Blender/ffmpeg orphans rendering behind the closed app
        try:
            self.stop_event.set()
        except Exception:
            pass
        try:
            self._terminate_child(getattr(self, "render_process", None))
        except Exception:
            pass
        try:
            for _p in list(getattr(self, "convert_procs", None) or []):
                self._terminate_child(_p)
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def set_layout_preset(self, name):
        try:
            self.layout = self._valid_layout(LAYOUT_PRESETS.get(name))
            self.layout_hidden = []
            self.layout_active = {}
            self.layout_split = {}
            self.config["layout_hidden"] = []
            self.config["layout_active"] = {}
            self.config["layout_split"] = {}
            self.apply_layout()
            self.log("Layout: {}".format(name))
        except Exception:
            pass

    def _drag_start(self, event, panel):
        self._drag = {"panel": panel, "target": None, "ghost": None}
        try:
            g = tk.Toplevel(self)
            g.wm_overrideredirect(True)
            g.attributes("-alpha", 0.88)
            try:
                g.attributes("-topmost", True)
            except Exception:
                pass
            tk.Label(g, text=PANEL_TITLES.get(panel, panel), font=F_HEAD,
                     fg="white", bg=C_ACCENT, padx=16, pady=7).pack()
            self._drag["ghost"] = g
            self._move_ghost(event)
        except Exception:
            pass
        self._show_drop_guide()

    def _move_ghost(self, event):
        try:
            self._drag["ghost"].geometry(f"+{event.x_root + 14}+{event.y_root + 14}")
        except Exception:
            pass

    def _slot_rects(self):
        """Current screen rects of the four drop slots: {slot: (x, y, w, h)}."""
        rects = {}
        try:
            areas = [("left", self.slot_frames["left"]),
                     ("center", self.slot_frames["center"]),
                     ("right", self.slot_frames["right"]),
                     ("bottom", self.slot_bottom)]
            for name, f in areas:
                try:
                    rects[name] = (f.winfo_rootx(), f.winfo_rooty(),
                                   f.winfo_width(), f.winfo_height())
                except Exception:
                    continue
        except Exception:
            pass
        return rects

    def _slot_at(self, x, y):
        try:
            for name, (rx, ry, w, h) in self._slot_rects().items():
                if w > 10 and h > 10 and rx <= x < rx + w and ry <= y < ry + h:
                    return name
        except Exception:
            pass
        # Forgiving fallback: dropped onto a panel (or sash gap) instead of a
        # slot rect -> resolve through the widget under the cursor.
        try:
            w = self.winfo_containing(x, y)
            if w is not None:
                panel = self._panel_of_widget(w)
                if panel:
                    return self._slot_of(panel)
        except Exception:
            pass
        return None

    def _panel_of_widget(self, w):
        """Walk up from a widget to the owning panel name (None if outside)."""
        try:
            paths = {str(self.panel_queue): "queue", str(self.panel_view): "view",
                     str(self.panel_prog): "prog", str(self.panel_props): "props",
                     str(self.panel_log): "log"}
            d = getattr(self, "_drag", None) or {}
            ghost = d.get("ghost")
            ghost_path = ""
            try:
                ghost_path = str(ghost) if ghost is not None else ""
            except Exception:
                pass
            cur = w
            guard = 0
            while cur is not None and guard < 64:
                guard += 1
                try:
                    hit = getattr(cur, "_brm_panel", None)
                    if hit in ("queue", "view", "prog", "props", "log"):
                        return hit
                except Exception:
                    pass
                try:
                    cur_s = str(cur)
                except Exception:
                    return None
                if ghost_path and (cur_s == ghost_path or cur_s.startswith(ghost_path + ".")):
                    return None
                if cur_s in paths:
                    return paths[cur_s]
                try:
                    parent_name = cur.winfo_parent()
                except Exception:
                    return None
                if not parent_name:
                    return None
                try:
                    cur = cur.nametowidget(parent_name)
                except Exception:
                    return None
        except Exception:
            pass
        return None

    def _show_drop_guide(self):
        """Overlay showing the four labeled drop zones while dragging."""
        self._hide_drop_guide()
        try:
            rects = self._slot_rects()
            if len(rects) < 4:
                return
            ox = self.winfo_rootx()
            tops = [ry for (_, ry, _, _) in rects.values()]
            bots = [ry + h for (_, ry, _, h) in rects.values()]
            oy, obot = min(tops), max(bots)
            ov = tk.Toplevel(self)
            ov.wm_overrideredirect(True)
            try:
                ov.attributes("-alpha", 0.72)
            except Exception:
                pass
            try:
                ov.attributes("-topmost", True)
            except Exception:
                pass
            ov.configure(bg="black")
            ov.geometry("+{}+{}".format(ox, oy))
            zones = {}
            trays = {}
            titles = {"left": "LEFT", "center": "CENTER", "right": "RIGHT", "bottom": "BOTTOM"}
            for slot in ("left", "center", "right", "bottom"):
                rx, ry, w, h = rects[slot]
                box = tk.Frame(ov, bg="#101623", highlightthickness=2,
                               highlightbackground=C_LINE2, highlightcolor=C_LINE2)
                box.place(x=rx - ox + 3, y=ry - oy + 3, width=max(10, w - 6), height=max(10, h - 6))
                cur = ""
                try:
                    names = list(self.layout.get(slot, []))
                    sp = (self.layout_split or {}).get(slot) or {}
                    names = names + [p for p in (sp.get("tabs") or [])
                                     if p not in names]
                    cur = ", ".join(PANEL_TITLES.get(p, p) for p in names)
                except Exception:
                    pass
                tk.Label(box, text=titles[slot], font=F_HEAD, fg=C_ACCENT2,
                         bg="#101623").pack(expand=True)
                tk.Label(box, text=cur, font=F_SMALL, fg=C_GRAY_TXT,
                         bg="#101623").pack()
                zones[slot] = box
                # edge-split trays: light up when the cursor sits in the band
                try:
                    geom = self._slot_band_geom(slot)
                except Exception:
                    geom = None
                if geom is not None:
                    grx, gry, grw, grh, edge = geom
                    for band, arrow in (("left", "◀ SPLIT"), ("right", "SPLIT ▶")):
                        try:
                            tx = (grx - rx) + (0 if band == "left" else (grw - edge))
                            tray = tk.Frame(box, bg="#101623", highlightthickness=1,
                                            highlightbackground="#2a3a55",
                                            highlightcolor="#2a3a55")
                            tray.place(x=max(0, tx), y=max(0, gry - ry),
                                       width=min(edge, max(10, w - 6)),
                                       height=max(10, grh))
                            tk.Label(tray, text=arrow, font=F_MONO_SM, fg=C_FAINT,
                                     bg="#101623").pack(expand=True)
                            trays[(slot, band)] = tray
                        except Exception:
                            pass
            ov.geometry("{}x{}".format(self.winfo_width(), obot - oy))
            self._drag["guide"] = ov
            self._drag["zones"] = zones
            self._drag["trays"] = trays
            ov.geometry("{}x{}".format(self.winfo_width(), obot - oy))
            self._drag["guide"] = ov
            self._drag["zones"] = zones
            self._guide_highlight(None)
        except Exception:
            try:
                self._hide_drop_guide()
            except Exception:
                pass

    def _hide_drop_guide(self):
        try:
            d = getattr(self, "_drag", None) or {}
            g = d.get("guide")
            if g is not None:
                try:
                    g.destroy()
                except Exception:
                    pass
                d["guide"] = None
                d["zones"] = {}
        except Exception:
            pass

    def _guide_highlight(self, target, band=None):
        try:
            zones = (getattr(self, "_drag", None) or {}).get("zones") or {}
            trays = (getattr(self, "_drag", None) or {}).get("trays") or {}
            for slot, box in zones.items():
                try:
                    if slot == target:
                        box.configure(highlightbackground=C_ACCENT, highlightcolor=C_ACCENT,
                                      bg="#16233d")
                        for ch in box.winfo_children():
                            try:
                                ch.configure(bg="#16233d")
                            except Exception:
                                pass
                    else:
                        box.configure(highlightbackground=C_LINE2, highlightcolor=C_LINE2,
                                      bg="#101623")
                        for ch in box.winfo_children():
                            try:
                                ch.configure(bg="#101623")
                            except Exception:
                                pass
                except Exception:
                    pass
            # trays paint LAST: they are zone children and the zone loop above
            # would otherwise repaint them with the zone background
            for (slot, bd), tray in trays.items():
                try:
                    on = (slot == target and bd == band)
                    tray.configure(bg=C_ACCENT if on else "#101623",
                                   highlightbackground=C_ACCENT if on else "#2a3a55",
                                   highlightcolor=C_ACCENT if on else "#2a3a55")
                    for ch in tray.winfo_children():
                        try:
                            ch.configure(bg=C_ACCENT if on else "#101623",
                                         fg="white" if on else C_FAINT)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    def _highlight_slot(self, target):
        try:
            for name in ("left", "center", "right", "bottom"):
                try:
                    self.slot_bar[name].configure(
                        bg="#1a2c4d" if name == target else C_BG)
                except Exception:
                    pass
        except Exception:
            pass

    def _drag_move(self, event):
        d = getattr(self, "_drag", None)
        if not d:
            return
        try:
            self._move_ghost(event)
            target = self._slot_at(event.x_root, event.y_root)
            band = None
            if target:
                try:
                    b, _g = self._slot_band(target, event.x_root, event.y_root)
                    band = b if b in ("left", "right") else None
                except Exception:
                    pass
            if target != d.get("target") or band != d.get("band"):
                d["target"] = target
                d["band"] = band
                self._highlight_slot(target)
                self._guide_highlight(target, band)
        except Exception:
            pass

    def _drag_end(self, event):
        d = getattr(self, "_drag", None)
        try:
            if d is not None and d.get("ghost") is not None:
                try:
                    d["ghost"].destroy()
                except Exception:
                    pass
            try:
                self._hide_drop_guide()
            except Exception:
                pass
            self._highlight_slot(None)
            if not d:
                return
            try:
                # Fresh geometry: tab buttons rebuilt by an earlier drop may
                # not be laid out yet (width reads 1 -> wrong insert index).
                self.update_idletasks()
            except Exception:
                pass
            try:
                wx, wy = self.winfo_rootx(), self.winfo_rooty()
                ww, wh = self.winfo_width(), self.winfo_height()
            except Exception:
                wx = wy = ww = wh = 0
            panel = d.get("panel")
            try:
                raw_out = (ww > 0 and (event.x_root < wx - 30
                                       or event.x_root > wx + ww + 30
                                       or event.y_root < wy - 30
                                       or event.y_root > wy + wh + 30))
            except Exception:
                raw_out = False
            if raw_out and panel:
                # dragged out of the window: dismiss (hide) the panel,
                # browser-tab style. Panels menu brings it back.
                try:
                    self.close_panel(panel)
                except Exception:
                    pass
                return
            try:
                # Forgive releases a few px outside the window edge (e.g. when
                # aiming at the far-right tab): clamp into the window first.
                ex = min(max(event.x_root, wx + 2), wx + ww - 3)
                ey = min(max(event.y_root, wy + 2), wy + wh - 3)
            except Exception:
                ex, ey = event.x_root, event.y_root
            try:
                target = self._slot_at(ex, ey)
            except Exception:
                target = d.get("target")
            if target and panel:
                cur, cgroup = self._panel_group(panel)
                if cur:
                    band, group = self._slot_band(target, ex, ey)
                    if (band in ("left", "right")
                            and not self._has_split(target)
                            and not (cur == target
                                     and len(self._group_tabs(cur, cgroup)) < 2)):
                        # edge band of an unsplit slot: side-by-side split
                        self._split_slot(target, band, panel)
                    else:
                        # Premiere-style pure move into the group under the
                        # cursor; slots may empty (they collapse to a strip).
                        g = group if self._has_split(target) else "main"
                        names = [p for p in self._group_tabs(target, g)
                                 if p != panel]
                        idx = max(0, min(self._slot_index_at(
                            ex, ey, target, g), len(names)))
                        self._detach_panel(panel)
                        names.insert(idx, panel)
                        self._set_group_tabs(target, g, names)
                        self._set_group_active(target, g, panel)
                        self.apply_layout()
                        try:
                            self._flash_tab(target, panel)
                        except Exception:
                            pass
                        self.log("Moved {} panel.".format(
                            PANEL_TITLES.get(panel, panel)))
        finally:
            self._drag = None

    def queue_menu(self):
        m = tk.Menu(self, tearoff=0)
        lay = tk.Menu(m, tearoff=0)
        for preset in ("Default", "Viewport left", "Log right"):
            lay.add_command(label=preset, command=lambda p=preset: self.set_layout_preset(p))
        lay.add_separator()
        lay.add_command(label="Reset layout", command=lambda: self.set_layout_preset("Default"))
        m.add_cascade(label="Layout", menu=lay)
        m._layout_menu = lay
        pan = tk.Menu(m, tearoff=0)
        for p in PANELS:
            try:
                pan.add_checkbutton(label=PANEL_TITLES.get(p, p),
                                    variable=tk.BooleanVar(
                                        value=self._slot_of(p) is not None),
                                    command=lambda p=p: self.toggle_panel(p))
            except Exception:
                pass
        m.add_cascade(label="Panels", menu=pan)
        m._panels_menu = pan
        m.add_separator()
        m.add_command(label="Settings…", command=self.open_settings_window)
        m.add_command(label="Probe all files (full info)", command=self.probe_all_deep)
        m.add_command(label="MP4 from folder…", command=self.convert_folder_dialog)
        m.add_separator()
        m.add_command(label="Clear finished", command=self.clear_finished)
        m.add_command(label="Clear all", command=self.clear_queue)
        self._popup_menu(m)

    def match_source(self):
        idx = self.selected_idx
        if idx is None:
            return
        item = self.config["queue_list"][idx]
        probe = item.get("probe")
        sc = scene_info_from_probe(probe, item.get("scene") or (probe.get("active") if probe else None))
        if not sc or sc.get("res_x") is None or sc.get("res_pct") is None:
            # Preview probes only carry scene name + frame range: no resolution
            # data to copy yet. Bail out instead of blanking the item with Nones.
            messagebox.showinfo("Match source",
                                "No resolution data yet.\nRefresh file info first, then Match source.")
            return
        item["res_x"] = sc.get("res_x")
        item["res_y"] = sc.get("res_y")
        item["res_pct"] = sc.get("res_pct")
        item["file_format"] = sc.get("file_format") or None
        item["color_mode"] = sc.get("color_mode") or None
        item["color_depth"] = None
        item["compression"] = sc.get("compression")
        item["film_transparent"] = None
        item["ov"] = {"res_x": False, "res_y": False, "scale": False, "overwrite": False, "placeholder": False}
        save_config(self.config)
        self.refresh_inspector()
        self.refresh_row(idx)


    # ================= INSPECTOR DATA =================
    def current_item(self):
        if self.selected_idx is None or self.selected_idx >= len(self.config["queue_list"]):
            return None
        return self.config["queue_list"][self.selected_idx]

    STATUS_LABEL = {"Pending": ("QUEUED", None), "Rendering": ("RENDERING", None),
                    "Done": ("DONE", None), "Failed": ("CRASHED", None)}

    def _fmt_for_seg(self, file_format):
        ff = (file_format or "PNG")
        if ff.startswith("OPEN_EXR"):
            return "EXR"
        return ff if ff in ("PNG", "JPEG", "TIFF") else "PNG"

    def _seg_to_fmt(self, disp):
        return {"EXR": "OPEN_EXR"}.get(disp, disp)

    def refresh_inspector(self):
        self._inspector_updating = True
        try:
            item = self.current_item()
            if item is None:
                self.lbl_pfile.configure(text="No selection")
                self.lbl_ppath.configure(text="")
                self.lbl_pstatus.configure(text="—", fg=C_GRAY_TXT)
                try:
                    self.lbl_pstatus_icon.configure(image="")
                except Exception:
                    pass
                return
            self.lbl_pfile.configure(text=os.path.basename(item.get("path", "?")))
            self.lbl_ppath.configure(text=item.get("path", ""))
            probe = item.get("probe")
            eff = effective_job_settings(item, probe)
            sc = scene_info_from_probe(probe, eff["scene"]) or {}

            # status
            st = item.get("status", "Pending")
            if st == "Rendering" and self.paused:
                label, color, kind = "PAUSED", C_YELLOW, "paused"
            else:
                label = {"Pending": "QUEUED", "Rendering": "RENDERING",
                         "Done": "DONE", "Failed": "CRASHED",
                         "Stopped": "STOPPED"}.get(st, st.upper())
                color = {"Pending": C_GRAY_TXT, "Rendering": C_ACCENT,
                         "Done": C_GREEN, "Failed": C_RED,
                         "Stopped": C_YELLOW}.get(st, C_GRAY_TXT)
                kind = {"Pending": "queued", "Rendering": "rendering",
                        "Done": "done", "Failed": "crashed",
                        "Stopped": "paused"}.get(st, "queued")
            self.lbl_pstatus.configure(text=label, fg=color)
            try:
                img = self._status_img(kind, 15, 0)
                self.lbl_pstatus_icon.configure(image=img)
                self.lbl_pstatus_icon.image = img
            except Exception:
                pass

            # engine / samples / film
            eng = item.get("engine") or sc.get("engine") or "CYCLES"
            evals = list(ENGINES)
            if eng not in evals:
                evals.append(eng)
            self._pset_menu(self.om_pengine, self.var_pengine, evals, eng)
            self.entry_psamples.delete(0, "end")
            if item.get("samples") is not None:
                self.entry_psamples.insert(0, str(item["samples"]))
                self.entry_psamples.configure(fg=C_TXT)
            else:
                self.entry_psamples.configure(fg=C_GRAY_TXT)
                if eff.get("samples"):
                    self.entry_psamples.insert(0, str(eff.get("samples")))
            self.var_pfilm.set(bool(eff.get("film_transparent")))

            # scene / camera / layer / frames
            scenes = (probe or {}).get("scenes", [])
            svals = ["Auto (file)"] + [s["name"] for s in scenes]
            if item.get("scene") and item["scene"] not in svals:
                svals.append(item["scene"])
            self._pset_menu(self.om_pscene, self.var_pscene, svals,
                            item.get("scene") or eff.get("scene") or "Auto (file)")
            cvals = ["Auto (file)"] + (sc.get("cameras") or [])
            if item.get("camera") and item["camera"] not in cvals:
                cvals.append(item["camera"])
            self._pset_menu(self.om_pcamera, self.var_pcamera, cvals,
                            item.get("camera") or eff.get("camera") or "Auto (file)")
            lvals = ["Auto (file)"] + (sc.get("view_layers") or [])
            if item.get("view_layer") and item["view_layer"] not in lvals:
                lvals.append(item["view_layer"])
            self._pset_menu(self.om_player, self.var_player, lvals,
                            item.get("view_layer") or eff.get("view_layer") or "Auto (file)")
            self.entry_pframes.delete(0, "end")
            if item.get("frame_start") is not None or item.get("frame_end") is not None:
                a = item.get("frame_start") if item.get("frame_start") is not None else eff["frame_start"]
                b = item.get("frame_end") if item.get("frame_end") is not None else eff["frame_end"]
                self.entry_pframes.insert(0, "{}-{}".format(a, b))
                self.entry_pframes.configure(fg=C_TXT)
            else:
                self.entry_pframes.configure(fg=C_GRAY_TXT)
                self.entry_pframes.insert(0, "{}-{}".format(eff["frame_start"], eff["frame_end"]))

            # format
            self.entry_presx.delete(0, "end")
            self.entry_presy.delete(0, "end")
            if item.get("res_x") is not None:
                self.entry_presx.insert(0, str(item["res_x"]))
                self.entry_presx.configure(fg=C_TXT)
            else:
                self.entry_presx.configure(fg=C_GRAY_TXT)
                if sc.get("res_x"):
                    self.entry_presx.insert(0, str(sc.get("res_x")))
            if item.get("res_y") is not None:
                self.entry_presy.insert(0, str(item["res_y"]))
                self.entry_presy.configure(fg=C_TXT)
            else:
                self.entry_presy.configure(fg=C_GRAY_TXT)
                if sc.get("res_y"):
                    self.entry_presy.insert(0, str(sc.get("res_y")))
            try:
                self.slider_pscale.set(int(eff.get("res_pct", 100)))
                self.lbl_pscale.configure(text="{}%".format(int(eff.get("res_pct", 100))))
            except Exception:
                pass

            # output
            self.entry_poutput.delete(0, "end")
            if item.get("output"):
                self.entry_poutput.insert(0, item["output"])
                self.entry_poutput.configure(fg=C_TXT)
            else:
                self.entry_poutput.configure(fg=C_GRAY_TXT)
                if sc.get("output"):
                    self.entry_poutput.insert(0, sc.get("output"))
            self.lbl_out_resolved.configure(text=eff.get("output", ""))
            self.var_pformat.set(self._fmt_for_seg(item.get("file_format") or sc.get("file_format")))
            self._seg_paint(self.seg_pformat, self.var_pformat)
            cm = item.get("color_mode") or sc.get("color_mode") or "RGB"
            self.var_pcmode.set(cm if cm in COLOR_MODES else "RGB")
            self._seg_paint(self.seg_pcmode, self.var_pcmode)
            cd = str(item.get("color_depth") or sc.get("color_depth") or "8")
            self.var_pcdepth.set(cd if cd in ("8", "16") else "8")
            self._seg_paint(self.seg_pcdepth, self.var_pcdepth)
            compr = eff.get("compression")
            try:
                self.slider_pcompr.set(int(compr) if compr is not None else 15)
                self.lbl_pcompr.configure(text="{}%".format(int(compr) if compr is not None else 15))
            except Exception:
                pass
            self.var_poverwrite.set(bool(eff.get("overwrite")))
            self.var_pplaceholder.set(bool(eff.get("placeholder")))
            self.entry_pfps.delete(0, "end")
            if item.get("fps"):
                self.entry_pfps.insert(0, str(item["fps"]))
                self.entry_pfps.configure(fg=C_TXT)
            else:
                self.entry_pfps.configure(fg=C_GRAY_TXT)
                if sc.get("fps"):
                    self.entry_pfps.insert(0, "{:.2f}".format(float(sc.get("fps"))))

            # python / gui
            self.entry_pyargs.delete(0, "end")
            if item.get("python_args"):
                self.entry_pyargs.insert(0, item["python_args"])
                self.entry_pyargs.configure(fg=C_TXT)
            else:
                self.entry_pyargs.configure(fg=C_GRAY_TXT)
                self.entry_pyargs.insert(0, "--python-expr ...")
            self.var_pgui.set(bool(item.get("gui_mode")))
            warns = []
            if item.get("hurricane") or (probe and probe.get("hurricane")):
                warns.append("Hurricane sim: use GUI mode or the object may vanish.")
            if probe and probe.get("missing_count"):
                warns.append("{} missing file(s).".format(probe["missing_count"]))
            self.lbl_pwarn.configure(text=" ".join(warns))
        finally:
            self._inspector_updating = False

    def _same(self, a, b):
        try:
            return str(a) == str(b)
        except Exception:
            return False

    def insp_apply(self):
        if self._inspector_updating:
            return
        item = self.current_item()
        if item is None:
            return
        probe = item.get("probe")
        try:
            v = self.var_pengine.get()
            sc_e = scene_info_from_probe(probe, item.get("scene") or (probe.get("active") if probe else None)) or {}
            item["engine"] = None if self._same(v, sc_e.get("engine")) else (v or None)
        except Exception:
            pass
        t = self.entry_psamples.get().strip()
        try:
            if not t:
                item["samples"] = None
            else:
                v = int(t)
                sc_e = scene_info_from_probe(probe, item.get("scene") or (probe.get("active") if probe else None)) or {}
                item["samples"] = None if self._same(v, sc_e.get("samples") or sc_e.get("eevee_samples")) else v
        except Exception:
            item["samples"] = None
        try:
            v = bool(self.var_pfilm.get())
            sc_e = scene_info_from_probe(probe, item.get("scene") or (probe.get("active") if probe else None)) or {}
            item["film_transparent"] = None if self._same(v, sc_e.get("film_transparent", False)) else v
        except Exception:
            pass
        sc0 = scene_info_from_probe(probe, item.get("scene") or (probe.get("active") if probe else None)) or {}
        try:
            v = self.var_pscene.get()
            if v in ("Auto (file)", "Auto") or self._same(v, (probe.get("active") if probe else None)):
                new_sc = None
            else:
                new_sc = v or None
        except Exception:
            new_sc = item.get("scene")
        old_sc = item.get("scene")
        item["scene"] = new_sc
        if new_sc != old_sc:
            # Scene switch invalidates every per-scene widget still showing the
            # old scene: drop them, persist, repaint, and stop here. The user
            # edits fresh values afterwards.
            item["camera"] = None
            item["view_layer"] = None
            save_config(self.config)
            self.refresh_inspector()
            self.refresh_row(self.selected_idx)
            return
        sc = scene_info_from_probe(probe, new_sc or (probe.get("active") if probe else None)) or sc0
        try:
            v = self.var_pcamera.get()
            item["camera"] = None if (v in ("Auto (file)", "Auto") or self._same(v, sc.get("camera"))) else v
        except Exception:
            pass
        try:
            v = self.var_player.get()
            vl0 = (sc.get("view_layers") or [None])[0]
            item["view_layer"] = None if (v in ("Auto (file)", "Auto") or self._same(v, vl0)) else v
        except Exception:
            pass
        t = self.entry_pframes.get().strip()
        try:
            if not t:
                item["frame_start"] = item["frame_end"] = None
            else:
                a, b = parse_frames_text(t, None, None)
                fa, fb = sc.get("frame_start"), sc.get("frame_end")
                item["frame_start"] = None if (a is not None and self._same(a, fa)) else a
                item["frame_end"] = None if (b is not None and self._same(b, fb)) else b
        except Exception:
            pass
        for key, entry in (("res_x", self.entry_presx), ("res_y", self.entry_presy)):
            t = entry.get().strip().lower().replace("px", "")
            try:
                if not t:
                    item[key] = None
                    item["ov"][key] = False
                else:
                    v = int(t)
                    if self._same(v, sc.get(key)):
                        item[key] = None
                        item["ov"][key] = False
                    else:
                        item[key] = v
                        item["ov"][key] = True
            except Exception:
                item[key] = None
        try:
            v = int(float(self.slider_pscale.get()))
            self.lbl_pscale.configure(text="{}%".format(v))
            if self._same(v, sc.get("res_pct", 100)):
                item["res_pct"] = None
                item["ov"]["scale"] = False
            else:
                item["res_pct"] = v
                item["ov"]["scale"] = True
        except Exception:
            pass
        t = self.entry_poutput.get().strip()
        try:
            item["output"] = None if (not t or self._same(t, sc.get("output"))) else t
        except Exception:
            item["output"] = t or None
        try:
            v = self._seg_to_fmt(self.var_pformat.get())
            item["file_format"] = None if self._same(v, sc.get("file_format")) else v
        except Exception:
            pass
        try:
            v = self.var_pcmode.get()
            item["color_mode"] = None if self._same(v, sc.get("color_mode")) else (v or None)
        except Exception:
            pass
        try:
            v = self.var_pcdepth.get()
            item["color_depth"] = None if self._same(v, str(sc.get("color_depth", ""))) else v
        except Exception:
            pass
        try:
            v = int(float(self.slider_pcompr.get()))
            self.lbl_pcompr.configure(text="{}%".format(v))
            item["compression"] = None if self._same(v, sc.get("compression")) else v
        except Exception:
            pass
        try:
            v = bool(self.var_poverwrite.get())
            item["overwrite"] = None if self._same(v, sc.get("use_overwrite", True)) else v
            item["ov"]["overwrite"] = item["overwrite"] is not None
        except Exception:
            pass
        try:
            v = bool(self.var_pplaceholder.get())
            item["placeholder"] = None if self._same(v, sc.get("use_placeholder", False)) else v
            item["ov"]["placeholder"] = item["placeholder"] is not None
        except Exception:
            pass
        t = self.entry_pfps.get().strip()
        try:
            if not t:
                item["fps"] = None
            else:
                v = float(t)
                item["fps"] = None if self._same(v, sc.get("fps")) else v
        except Exception:
            item["fps"] = None
        try:
            t = self.entry_pyargs.get().strip()
            item["python_args"] = "" if t in ("", "--python-expr ...") else t
        except Exception:
            pass
        try:
            item["gui_mode"] = bool(self.var_pgui.get())
        except Exception:
            pass
        save_config(self.config)
        try:
            eff = effective_job_settings(item, item.get("probe"))
            self.lbl_out_resolved.configure(text=eff.get("output", ""))
        except Exception:
            pass
        self.refresh_row(self.selected_idx)

    # ================= QUEUE ROWS =================
    # Lightweight native rows: index / status icon / filename / frames / hover-X.
    # Scene/camera/layer/frames editing lives in the properties panel.
    def _row_key(self, idx):
        try:
            p = self.config["queue_list"][idx].get("path", "")
            return p if p else "\x00%d" % idx
        except Exception:
            return "\x00%d" % idx

    def _sync_selection(self):
        """Prune dead paths; keep the primary consistent with the set."""
        try:
            live = set()
            for j, it in enumerate(self.config["queue_list"]):
                try:
                    p = it.get("path", "")
                    live.add(p if p else "\x00%d" % j)
                except Exception:
                    pass
            self.selected_paths = set(p for p in (self.selected_paths or set())
                                      if p in live)
            if self.selected_idx is not None:
                try:
                    cur = self._row_key(self.selected_idx)
                except Exception:
                    cur = None
                if cur is None or cur not in live:
                    self.selected_idx = None
                elif cur not in self.selected_paths:
                    self.selected_paths.add(cur)
            if self.selected_idx is None and self.selected_paths:
                for j in range(len(self.config["queue_list"])):
                    try:
                        if self._row_key(j) in self.selected_paths:
                            self.selected_idx = j
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    def _row_click(self, idx, event=None):
        try:
            if event is not None:
                self._row_down = {"idx": idx, "x": event.x_root, "y": event.y_root,
                                  "dragging": False}
            else:
                self._row_down = None
        except Exception:
            self._row_down = None
        try:
            state = int(getattr(event, "state", 0) or 0) if event is not None else 0
        except Exception:
            state = 0
        ctrl = bool(state & 0x4)
        shift = bool(state & 0x1)
        try:
            if event is None or (not ctrl and not shift):
                self.selected_paths = set([self._row_key(idx)])
                self._sel_anchor = idx
            elif ctrl:
                k = self._row_key(idx)
                if k in self.selected_paths and len(self.selected_paths) > 1:
                    self.selected_paths.discard(k)
                else:
                    self.selected_paths.add(k)
                self._sel_anchor = idx
            else:
                try:
                    a = self._sel_anchor if self._sel_anchor is not None else idx
                except Exception:
                    a = idx
                lo, hi = (a, idx) if a <= idx else (idx, a)
                try:
                    for j in range(lo, hi + 1):
                        self.selected_paths.add(self._row_key(j))
                except Exception:
                    pass
            self.selected_idx = idx
        except Exception:
            pass
        try:
            self.refresh_row_selection()
        except Exception:
            pass
        try:
            self._update_pill()
        except Exception:
            pass
        # heavy panels follow the LAST click only: debounce inspector +
        # viewport so rapid click-through never queues redundant rebuilds
        try:
            if getattr(self, "_sel_after", None):
                try:
                    self.after_cancel(self._sel_after)
                except Exception:
                    pass
            token = int(getattr(self, "_sel_token", 0) or 0) + 1
            self._sel_token = token
            self._sel_after = self.after(100, lambda: self._select_idle(idx, token))
        except Exception:
            pass

    def _select_idle(self, idx, token):
        try:
            self._sel_after = None
            if token != getattr(self, "_sel_token", 0):
                return
            if idx != self.selected_idx:
                return
            self.refresh_row_selection()
            self.refresh_inspector()
            try:
                # a live render owns the viewport; selection takes over only
                # when idle (clicking around mid-render must not hijack it)
                if not getattr(self, "_live_on", False):
                    self.vp_show_job(idx)
            except Exception:
                pass
        except Exception:
            pass

    # ---- queue drag-to-reorder (no handle: press selects, drag moves) ----
    def _row_motion(self, event, idx):
        try:
            d = getattr(self, "_row_down", None)
            if not d or d.get("idx") != idx:
                return
            if d.get("dragging"):
                self._move_row_ghost(event)
                self._row_drop_mark(self._row_mark_idx(event))
                return
            try:
                dy = abs(event.y_root - d.get("y", 0))
            except Exception:
                return
            if dy > 8:
                d["dragging"] = True
                try:
                    g = tk.Toplevel(self)
                    g.wm_overrideredirect(True)
                    g.attributes("-alpha", 0.88)
                    try:
                        g.attributes("-topmost", True)
                    except Exception:
                        pass
                    nm = os.path.basename((self.config["queue_list"][idx] or {}).get("path", "?"))
                    tk.Label(g, text=nm[:32], font=F_MONO, fg="white",
                             bg=C_ACCENT, padx=12, pady=5).pack()
                    self._row_ghost = g
                    self._move_row_ghost(event)
                except Exception:
                    pass
                self._row_drop_mark(self._row_mark_idx(event))
        except Exception:
            pass

    def _move_row_ghost(self, event):
        try:
            g = getattr(self, "_row_ghost", None)
            if g is not None:
                g.geometry("+{}+{}".format(event.x_root + 14, event.y_root + 14))
        except Exception:
            pass

    def _row_target_at(self, x, y):
        """Drop slot 0..n: first row whose vertical middle is below y."""
        try:
            n = len(self.config["queue_list"])
            for i, w in enumerate(self.row_widgets):
                try:
                    mid = w["frame"].winfo_rooty() + w["frame"].winfo_height() // 2
                except Exception:
                    continue
                if y < mid:
                    return i
            return n
        except Exception:
            pass
        return 0

    def _row_mark_idx(self, event):
        try:
            n = len(self.config["queue_list"])
            if n == 0:
                return None
            tgt = self._row_target_at(event.x_root, event.y_root)
            return tgt if tgt < n else n - 1
        except Exception:
            return None

    def _row_drop_mark(self, idx):
        try:
            prev = getattr(self, "_row_drop_idx", None)
            if prev == idx:
                return
            self._row_drop_idx = idx
            try:
                self.refresh_row_selection()
            except Exception:
                pass
            if idx is not None:
                try:
                    w = self.row_widgets[idx]
                    w["frame"].configure(bg="#1a2c4d")
                    for k in ("idx", "name", "frames", "sub"):
                        try:
                            w[k].configure(bg="#1a2c4d")
                        except Exception:
                            pass
                    w["status"].configure(bg="#1a2c4d")
                except Exception:
                    pass
        except Exception:
            pass

    def _row_release(self, event, idx):
        try:
            d = getattr(self, "_row_down", None)
            self._row_down = None
            self._row_drop_mark(None)
            g = getattr(self, "_row_ghost", None)
            self._row_ghost = None
            if g is not None:
                try:
                    g.destroy()
                except Exception:
                    pass
            if not d or not d.get("dragging"):
                return
            frm = d.get("idx")
            tgt = self._row_target_at(event.x_root, event.y_root)
            self._row_move(frm, tgt)
        except Exception:
            pass

    def _row_move(self, frm, to):
        try:
            if frm is None or to is None or frm == to:
                return
            if not self._guard_not_rendering("Reorder queue"):
                return
            q = self.config["queue_list"]
            if not (0 <= frm < len(q)):
                return
            try:
                sel_path = q[self.selected_idx].get("path", "") \
                    if self.selected_idx is not None else ""
            except Exception:
                sel_path = ""
            item = q.pop(frm)
            to = max(0, min(int(to), len(q)))
            q.insert(to, item)
            if sel_path:
                for j, it in enumerate(q):
                    try:
                        if it.get("path") == sel_path:
                            self.selected_idx = j
                            break
                    except Exception:
                        continue
            save_config(self.config)
            self.refresh_all_rows()
            self.refresh_inspector()
            self._update_pill()
        except Exception:
            pass

    def _status_kind(self, item):
        st = item.get("status", "Pending")
        if st == "Done":
            return "done"
        if st == "Rendering":
            return "paused" if self.paused else "rendering"
        if st == "Failed":
            return "crashed"
        if st == "Stopped":
            return "paused"
        return "queued"

    def refresh_row_selection(self):
        try:
            selset = set(getattr(self, "selected_paths", None) or set())
        except Exception:
            selset = set()
        for i, w in enumerate(self.row_widgets):
            try:
                try:
                    sel = self._row_key(i) in selset
                except Exception:
                    sel = (i == self.selected_idx)
                w["frame"].configure(bg="#141a26" if sel else C_PANEL)
                w["stripe"].configure(bg=C_ACCENT if sel else C_PANEL)
                try:
                    item = self.config["queue_list"][i]
                    base = C_ACCENT2 if sel else (C_TXT if item.get("status") == "Rendering" else "#8d8d8d")
                    if not item.get("enabled", True):
                        base = C_FAINT
                    w["name"].configure(bg="#141a26" if sel else C_PANEL, fg=base)
                    for k in ("idx", "frames", "sub"):
                        w[k].configure(bg="#141a26" if sel else C_PANEL)
                except Exception:
                    pass
            except Exception:
                pass

    def refresh_all_rows(self):
        fresh = not self.row_widgets
        for w in self.row_widgets:
            try:
                w["frame"].destroy()
                w["line"].destroy()
            except Exception:
                pass
        self.row_widgets = []
        total = len(self.config["queue_list"])
        if self.selected_idx is not None and self.selected_idx >= total:
            self.selected_idx = total - 1 if total else None
        for i in range(total):
            try:
                self._build_row(i)
            except Exception:
                pass
        if fresh:
            try:
                self.rows_scroll._parent_canvas.yview_moveto(0)
            except Exception:
                pass
        self._update_queue_count()
        self.refresh_row_selection()

    def _update_queue_count(self):
        self._refresh_queue_tab()
    def _row_spec(self, item, eff):
        """Short 'Scene • Camera • WxH@P% • ENGINE n • FPS' job summary."""
        try:
            parts = []
            sc = item.get("scene") or (eff or {}).get("scene")
            if sc and sc != "Auto (file)":
                parts.append(str(sc)[:18])
            cam = item.get("camera") or (eff or {}).get("camera")
            if cam and cam != "Auto (file)":
                parts.append(str(cam)[:18])
            rx, ry = (eff or {}).get("res_x"), (eff or {}).get("res_y")
            if rx and ry:
                try:
                    parts.append("{}x{}@{}%".format(int(rx), int(ry),
                                                   int((eff or {}).get("res_pct", 100))))
                except Exception:
                    pass
            eng = item.get("engine") or (eff or {}).get("engine")
            if eng:
                seg = str(eng).replace("BLENDER_", "")
                sm = item.get("samples")
                if sm is None:
                    sm = (eff or {}).get("samples")
                if sm:
                    seg += " {}".format(sm)
                parts.append(seg[:16])
            return "  •  ".join(parts)
        except Exception:
            return ""

    def _row_sub_text(self, item, eff):
        """(text, color) status line for a queue row: progress, result, MP4."""
        st = item.get("status", "Pending")
        try:
            fs, fe = int(eff["frame_start"]), int(eff["frame_end"])
        except Exception:
            fs, fe = 1, 250
        total = max(1, fe - fs + 1)
        if not item.get("enabled", True):
            return "OFF", C_FAINT
        if st == "Rendering":
            cf = item.get("current_frame")
            if getattr(self, "paused", False):
                head = "PAUSED {}–{}".format(fs, fe)
            elif cf:
                try:
                    pct = min(99, max(0, int(100 * (int(cf) - fs + 1) / total)))
                except Exception:
                    pct = 0
                head = "RENDERING {}–{}  {}%".format(fs, fe, pct)
            else:
                head = "RENDERING {}–{}".format(fs, fe)
            spec = self._row_spec(item, eff)
            return (head + ("  •  " + spec if spec else ""), C_ACCENT)
        if st == "Done":
            t = "DONE" + (" in {}".format(item["last_duration"])
                          if item.get("last_duration") else "")
            spec = self._row_spec(item, eff)
            if spec:
                t += "  •  " + spec
            try:
                mp4 = item.get("converted_mp4")
                if mp4 and os.path.exists(mp4):
                    t += "  •  MP4 READY"
            except Exception:
                pass
            return t, C_GREEN
        if st == "Failed":
            return "FAILED", C_RED
        if st == "Stopped":
            return "STOPPED", C_YELLOW
        try:
            if not os.path.exists(item.get("path", "")):
                return "MISSING FILE", C_RED
        except Exception:
            pass
        spec = self._row_spec(item, eff)
        return ("QUEUED" + ("  •  " + spec if spec else ""), C_GRAY_TXT)

    def _build_row(self, idx):
        item = self.config["queue_list"][idx]
        row = tk.Frame(self.rows_scroll, bg=C_PANEL, height=46)
        row.grid(row=idx * 2, column=0, sticky="ew")
        row.grid_propagate(False)
        row.grid_columnconfigure(3, weight=1)
        w = {"frame": row, "idx": idx}

        stripe = tk.Frame(row, bg=C_PANEL, width=2)
        stripe.grid(row=0, column=0, rowspan=2, sticky="ns")
        w["stripe"] = stripe

        lb_idx = tk.Label(row, text="{:02d}".format(idx + 1), font=F_MONO_SM, fg=C_FAINT,
                          bg=C_PANEL, width=3, anchor="e")
        lb_idx.grid(row=0, column=1, rowspan=2, padx=(6, 2), sticky="ns")
        w["idx"] = lb_idx

        lb_st = tk.Label(row, bg=C_PANEL, width=3, font=F_MONO_SM, fg=C_FAINT)
        lb_st.grid(row=0, column=2, rowspan=2, padx=2)
        w["status"] = lb_st

        nm = os.path.basename(item.get("path", "?"))
        lb_nm = tk.Label(row, text=nm, font=F_MONO, fg="#8d8d8d", bg=C_PANEL, anchor="w")
        lb_nm.grid(row=0, column=3, padx=2, sticky="ew")
        w["name"] = lb_nm
        w["nametip"] = ToolTip(lb_nm, item.get("path", ""))

        eff = effective_job_settings(item, item.get("probe"))
        lb_fr = tk.Label(row, text="{}–{}".format(eff["frame_start"], eff["frame_end"]),
                         font=F_MONO_SM, fg=C_GRAY_TXT, bg=C_PANEL, width=9, anchor="e")
        lb_fr.grid(row=0, column=4, padx=(2, 4), sticky="e")
        w["frames"] = lb_fr

        try:
            subtxt, subfg = self._row_sub_text(item, eff)
        except Exception:
            subtxt, subfg = "", C_GRAY_TXT
        lb_sub = tk.Label(row, text=subtxt, font=F_MONO_SM, fg=subfg,
                          bg=C_PANEL, anchor="w")
        lb_sub.grid(row=1, column=3, columnspan=2, padx=2, sticky="ew")
        w["sub"] = lb_sub

        bx = tk.Button(row, text="x", font=F_MONO_SM, fg=C_GRAY_TXT, bg=C_PANEL,
                       activebackground=C_PANEL, activeforeground=C_RED,
                       relief="flat", bd=0, highlightthickness=0, width=2,
                       command=lambda _i=idx: self.remove_at(_i))
        bx.grid(row=0, column=5, rowspan=2, padx=(0, 6))
        w["close"] = bx

        line = tk.Frame(self.rows_scroll, bg=C_LINE, height=1)
        line.grid(row=idx * 2 + 1, column=0, sticky="ew")
        w["line"] = line

        for wd in (row, lb_idx, lb_st, lb_nm, lb_fr, lb_sub):
            wd.bind("<Button-1>", lambda e, _i=idx: self._row_click(_i, e))
            wd.bind("<B1-Motion>", lambda e, _i=idx: self._row_motion(e, _i))
            wd.bind("<ButtonRelease-1>", lambda e, _i=idx: self._row_release(e, _i))
            wd.bind("<Button-3>", lambda e, _i=idx: self.row_menu(_i))
            wd.bind("<Enter>", lambda e, _i=idx: self._row_hover(_i, True))
            wd.bind("<Leave>", lambda e, _i=idx: self._row_hover(_i, False))
        bx.bind("<Enter>", lambda e, _i=idx: self._row_hover(_i, True))

        self.row_widgets.append(w)
        self.apply_status_color(idx)

    def _row_hover(self, idx, on):
        try:
            w = self.row_widgets[idx]
            if idx != self.selected_idx:
                w["frame"].configure(bg=C_ROW if on else C_PANEL)
                for k in ("idx", "name", "frames", "sub"):
                    try:
                        w[k].configure(bg=C_ROW if on else C_PANEL)
                    except Exception:
                        pass
                w["status"].configure(bg=C_ROW if on else C_PANEL)
        except Exception:
            pass

    def apply_status_color(self, idx):
        try:
            item = self.config["queue_list"][idx]
            w = self.row_widgets[idx]
            kind = self._status_kind(item)
            code, color = {"queued": ("Q", C_FAINT), "rendering": ("R", C_ACCENT),
                           "paused": ("II", C_YELLOW), "done": ("D", C_GREEN),
                           "crashed": ("F", C_RED)}.get(kind, ("•", C_FAINT))
            try:
                if not item.get("enabled", True):
                    code, color = ("OFF", C_FAINT)
                w["status"].configure(text=code, fg=color, image="")
            except Exception:
                pass
            missing = not os.path.exists(item.get("path", ""))
            if missing and item.get("status") == "Pending":
                try:
                    w["name"].configure(text="{}  [missing]".format(os.path.basename(item.get("path", "?"))[:28]))
                except Exception:
                    pass
            self._anim_mark(idx, kind in ("rendering", "crashed"))
            self.refresh_row_selection()
        except Exception:
            pass

    def refresh_row(self, idx):
        if idx is None:
            return
        try:
            item = self.config["queue_list"][idx]
            w = self.row_widgets[idx]
            nm = os.path.basename(item.get("path", "?"))
            w["name"].configure(text=nm)
            w["nametip"].text = item.get("path", "")
            eff = effective_job_settings(item, item.get("probe"))
            w["frames"].configure(text="{}–{}".format(eff["frame_start"], eff["frame_end"]))
            try:
                subtxt, subfg = self._row_sub_text(item, eff)
                w["sub"].configure(text=subtxt, fg=subfg)
            except Exception:
                pass
            self.apply_status_color(idx)
        except Exception:
            pass

    def refresh_rows_status(self):
        for i in range(len(self.row_widgets)):
            try:
                self.apply_status_color(i)
            except Exception:
                pass

    # ---- status icon / LIVE animation registry ----
    def _anim_mark(self, idx, animated):
        try:
            if animated:
                self._anim_rows.add(idx)
            else:
                self._anim_rows.discard(idx)
        except Exception:
            pass

    def _anim_tick(self):
        try:
            self._anim_frame = (getattr(self, "_anim_frame", 0) + 1) % 8
            f = self._anim_frame
            for idx in list(getattr(self, "_anim_rows", set())):
                try:
                    item = self.config["queue_list"][idx]
                    kind = self._status_kind(item)
                    if kind not in ("rendering", "crashed"):
                        continue
                    w = self.row_widgets[idx]
                    # pulse the status letter (never stamp images: the code
                    # column is text so it always stays readable)
                    base = C_ACCENT if kind == "rendering" else C_RED
                    try:
                        w["status"].configure(
                            image="",
                            fg=base if f % 2 == 0 else C_FAINT)
                    except Exception:
                        pass
                except Exception:
                    pass
            # LIVE dot pulse
            try:
                if getattr(self, "_live_on", False):
                    self.lbl_live_dot.configure(fg=C_ACCENT if f % 2 == 0 else C_FAINT)
            except Exception:
                pass
        except Exception:
            pass
        try:
            self.after(180, self._anim_tick)
        except Exception:
            pass

    def row_set_scene(self, idx, v):
        self.selected_idx = idx
        item = self.config["queue_list"][idx]
        if v in ("Auto (file)", "Auto"):
            item["scene"] = None  # follow the file again
        else:
            item["scene"] = v
        item["camera"] = None
        item["view_layer"] = None
        save_config(self.config)
        self.refresh_row(idx)
        self.refresh_inspector()

    def row_set_camera(self, idx, v):
        self.selected_idx = idx
        self.config["queue_list"][idx]["camera"] = None if v in ("Auto (file)", "Auto") else v
        save_config(self.config)
        self.refresh_inspector()

    def row_set_layer(self, idx, v):
        self.selected_idx = idx
        self.config["queue_list"][idx]["view_layer"] = None if v in ("Auto (file)", "Auto") else v
        save_config(self.config)
        self.refresh_inspector()

    def row_apply_frames(self, idx, text):
        a, b = parse_frames_text(text if isinstance(text, str) else text.get())
        if a is None:
            return
        self.config["queue_list"][idx]["frame_start"] = a
        self.config["queue_list"][idx]["frame_end"] = b
        save_config(self.config)
        self.refresh_row(idx)
        self.refresh_inspector()

    def row_menu(self, idx):
        try:
            if self._row_key(idx) not in (self.selected_paths or set()):
                self.selected_paths = set([self._row_key(idx)])
                self._sel_anchor = idx
            self.selected_idx = idx
        except Exception:
            self.selected_idx = idx
        self.refresh_row_selection()
        self.refresh_inspector()
        self._update_pill()
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="Move up", command=lambda: self.move_at(idx, -1))
        m.add_command(label="Move down", command=lambda: self.move_at(idx, 1))
        m.add_command(label="Duplicate", command=self.duplicate_selected)
        cur = self.config["queue_list"][idx].get("enabled", True)
        m.add_command(label="Disable" if cur else "Enable",
                      command=lambda: self.set_enabled(idx, not cur))
        m.add_command(label="Requeue (Pending)", command=lambda: self.requeue(idx))
        m.add_separator()
        m.add_command(label="Refresh file info", command=self.probe_selected)
        m.add_command(label="Render test frame", command=lambda: self.render_test_frame(idx))
        m.add_command(label="Convert to MP4", command=self.convert_selected_to_mp4)
        m.add_command(label="Open output folder", command=self.open_selected_output)
        m.add_separator()
        m.add_command(label="Remove", command=lambda: self.remove_at(idx))
        self._popup_menu(m)

    def render_test_frame(self, idx):
        """Render ONE frame through the real BRM pipeline (A/B vs Blender GUI)."""
        try:
            if getattr(self, "is_rendering", False):
                messagebox.showwarning("Render running", "Test frame: stop the render first.")
                return
            item = self.config["queue_list"][idx]
        except Exception:
            return
        threading.Thread(target=self._test_frame_thread, args=(idx,), daemon=True).start()

    def _test_frame_thread(self, idx):
        try:
            item = self.config["queue_list"][idx]
        except Exception:
            return
        try:
            probe = item.get("probe")
            eff = effective_job_settings(item, probe)
            f = item.get("current_frame") or eff.get("frame_start", 1)
            blend = item.get("path", "")
            bp = self.config.get("blender_path", "")
            if not bp or not os.path.exists(bp):
                self.log("TEST FRAME: set Blender path first.")
                return
            if not blend or not os.path.exists(blend):
                self.log("TEST FRAME: file not found.")
                return
            gui = item.get("gui_mode")
            if gui is None:
                gui = bool(self.config.get("gui_for_hurricane", True)
                           and bool(item.get("hurricane")
                                    or (probe and probe.get("hurricane"))))
            self.log("TEST FRAME {} (overwrite): {} ...".format(f, os.path.basename(blend)))
            ok, _lf = self.run_blender_process(
                bp, blend, f, f, "", 1,
                scene=eff.get("scene"), camera=eff.get("camera"),
                res_pct=eff.get("res_pct"), output=eff.get("output"),
                gui_mode=bool(gui), view_layer=eff.get("view_layer"),
                engine=eff.get("engine") or None, samples=eff.get("samples"),
                res_x=eff.get("res_x"), res_y=eff.get("res_y"),
                film=eff.get("film_transparent"),
                overwrite=True, placeholder=eff.get("placeholder"),
                file_format=eff.get("file_format") or None,
                color_mode=eff.get("color_mode") or None,
                color_depth=eff.get("color_depth") or None,
                compression=eff.get("compression"),
                python_args=eff.get("python_args") or "",
                progress_item=item, progress_row=lambda: self.refresh_row(idx))
            try:
                self.after(0, lambda: self._vp_show_last_frame(item, eff))
                self.after(0, lambda _i=idx: self.refresh_row(_i))
            except Exception:
                pass
            self.log("TEST FRAME {}: {}".format("done" if ok else "FAILED",
                                                os.path.basename(blend)))
        except Exception as e:
            try:
                self.log("TEST FRAME error: {}".format(e))
            except Exception:
                pass

    def set_enabled(self, idx, val):
        try:
            self.config["queue_list"][idx]["enabled"] = bool(val)
            save_config(self.config)
            self.refresh_row(idx)
        except Exception:
            pass

    def toggle_enabled(self, idx):
        try:
            cur = self.config["queue_list"][idx].get("enabled", True)
            self.set_enabled(idx, not cur)
        except Exception:
            pass

    def clear_finished(self):
        if not self._guard_not_rendering("Clear finished"):
            return
        q = self.config["queue_list"]
        keep = [it for it in q if it.get("status") != "Done"]
        n = len(q) - len(keep)
        if n <= 0:
            return
        self.config["queue_list"] = keep
        if self.selected_idx is not None and self.selected_idx >= len(keep):
            self.selected_idx = len(keep) - 1 if keep else None
        self._sync_selection()
        save_config(self.config)
        self.refresh_all_rows()
        self.refresh_inspector()

    def requeue(self, idx):
        self.config["queue_list"][idx]["status"] = "Pending"
        self.config["queue_list"][idx]["current_frame"] = None
        save_config(self.config)
        self.refresh_row(idx)
        self.refresh_inspector()

    def row_set_camera(self, idx, v):
        self.selected_idx = idx
        self.config["queue_list"][idx]["camera"] = None if v in ("Auto (file)", "Auto") else v
        save_config(self.config)
        self.refresh_inspector()

    def row_set_layer(self, idx, v):
        self.selected_idx = idx
        self.config["queue_list"][idx]["view_layer"] = None if v in ("Auto (file)", "Auto") else v
        save_config(self.config)
        self.refresh_inspector()

    def row_apply_frames(self, idx, widget):
        a, b = parse_frames_text(widget.get())
        if a is None:
            return
        self.config["queue_list"][idx]["frame_start"] = a
        self.config["queue_list"][idx]["frame_end"] = b
        save_config(self.config)
        self.refresh_inspector()

    def row_menu(self, idx):
        self.selected_idx = idx
        self.refresh_row_selection()
        self.refresh_inspector()
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="Move up", command=lambda: self.move_at(idx, -1))
        m.add_command(label="Move down", command=lambda: self.move_at(idx, 1))
        m.add_command(label="Refresh file info", command=self.probe_selected)
        m.add_command(label="Convert to MP4", command=self.convert_selected_to_mp4)
        m.add_command(label="Open output folder", command=self.open_selected_output)
        m.add_separator()
        m.add_command(label="Remove", command=lambda: self.remove_at(idx))
        self._popup_menu(m)

    def toggle_enabled(self, idx):
        try:
            self.config["queue_list"][idx]["enabled"] = bool(
                self.row_widgets[idx]["enabled_var"].get())
            save_config(self.config)
        except Exception:
            pass

    def requeue(self, idx):
        self.config["queue_list"][idx]["status"] = "Pending"
        self.config["queue_list"][idx]["current_frame"] = None
        save_config(self.config)
        self.refresh_row(idx)

    # ================= QUEUE OPS =================
    def add_to_queue(self):
        files = filedialog.askopenfilenames(filetypes=[("Blender Files", "*.blend"), ("BRQ", "*.brq"), ("All", "*.*")])
        if files:
            base = len(self.config["queue_list"])
            for fp in files:
                self.config["queue_list"].append(migrate_queue_item({"path": fp, "status": "Pending"}))
            save_config(self.config)
            # incremental: append only the new rows (no full-list rebuild flash)
            self._append_rows(range(base, len(self.config["queue_list"])))
            if self.selected_idx is None and self.config["queue_list"]:
                self.selected_idx = len(self.config["queue_list"]) - 1
                self._sync_selection()
                self.refresh_row_selection()
                self.refresh_inspector()
            threading.Thread(target=self._auto_probe_new, daemon=True).start()

    def _append_rows(self, idxs):
        try:
            total = len(self.config["queue_list"])
            if self.selected_idx is not None and self.selected_idx >= total:
                self.selected_idx = total - 1 if total else None
            for i in idxs:
                try:
                    self._build_row(i)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._update_queue_count()
        except Exception:
            pass
        try:
            self.refresh_row_selection()
        except Exception:
            pass

    def duplicate_selected(self):
        if not self._guard_not_rendering("Duplicate job"):
            return
        if self.selected_idx is None:
            return
        import copy
        dup = copy.deepcopy(self.config["queue_list"][self.selected_idx])
        dup["status"] = "Pending"
        dup["current_frame"] = None
        self.config["queue_list"].insert(self.selected_idx + 1, dup)
        self._sync_selection()
        save_config(self.config)
        self.refresh_all_rows()

    def clear_queue(self):
        if not self.config["queue_list"]:
            return
        if self.is_rendering:
            messagebox.showwarning("Clear queue", "Stop the render first.")
            return
        n = len(self.config["queue_list"])
        if messagebox.askyesno("Clear queue", "Remove all {} job(s) from the queue?".format(n)):
            self.config["queue_list"] = []
            self.selected_idx = None
            self.selected_paths = set()
            self._sel_anchor = None
            save_config(self.config)
            self.refresh_all_rows()
            self.refresh_inspector()
            self.log("Queue cleared ({} job(s) removed).".format(n))

    def _guard_not_rendering(self, what="Edit the queue"):
        if getattr(self, "is_rendering", False):
            messagebox.showwarning("Render running", "{}: stop the render first.".format(what))
            return False
        return True

    def remove_at(self, idx):
        if not self._guard_not_rendering("Remove job"):
            return
        try:
            del self.config["queue_list"][idx]
        except Exception:
            return
        if self.selected_idx is not None:
            if self.selected_idx >= len(self.config["queue_list"]):
                self.selected_idx = len(self.config["queue_list"]) - 1 if self.config["queue_list"] else None
        self._sync_selection()
        save_config(self.config)
        self.refresh_all_rows()
        self.refresh_inspector()

    def remove_selected(self):
        if self.selected_idx is not None:
            self.remove_at(self.selected_idx)

    def move_at(self, idx, d):
        if not self._guard_not_rendering("Reorder queue"):
            return
        ni = idx + d
        if 0 <= ni < len(self.config["queue_list"]):
            q = self.config["queue_list"]
            q[idx], q[ni] = q[ni], q[idx]
            self.selected_idx = ni
            self._sync_selection()
            save_config(self.config)
            self.refresh_all_rows()
            self.refresh_inspector()

    def _auto_probe_new(self):
        # Single-flight drain loop: concurrent adds share one worker instead of
        # stacking full passes (duplicate parses + save/refresh storms).
        try:
            if getattr(self, "_autoprobe_busy", False):
                return
            self._autoprobe_busy = True
        except Exception:
            pass
        try:
            while True:
                if not self._autoprobe_round():
                    break
        finally:
            try:
                self._autoprobe_busy = False
            except Exception:
                pass

    def _autoprobe_round(self):
        """One preview + deep sweep. Returns True if anything was (re)probed."""
        import time as _t
        did = False
        # Phase 1: instant REND preview ONLY (scene + frames, <0.1s for all files).
        try:
            missing = [i for i, item in enumerate(self.config["queue_list"])
                       if item.get("probe") is None and os.path.exists(item.get("path", ""))]
        except Exception:
            missing = []
        if missing and brm_blendparse is not None:
            t0 = _t.time()
            n_prev = 0
            for i in missing:
                try:
                    prev = brm_blendparse.preview_probe(self.config["queue_list"][i]["path"])
                except Exception:
                    prev = None
                if prev:
                    try:
                        self.config["queue_list"][i]["probe"] = prev
                        n_prev += 1
                        self.after(0, lambda _i=i: self.refresh_row(_i))
                    except Exception:
                        pass
            if n_prev:
                did = True
                save_config(self.config)
                self.log("File info: {} file(s) (scene + frames, {:.1f}s). Loading full details...".format(
                    n_prev, _t.time() - t0))
                if self.selected_idx is not None:
                    try:
                        self.after(0, self.refresh_inspector)
                    except Exception:
                        pass
        # Phase 2: full details (cameras, resolution, formats, sim flags) for
        # anything still on a preview probe. Sequential, no Blender fallback,
        # skipped while a render runs (render start deep-reads its own file).
        if not self.config.get("auto_full_probe", True):
            return did
        try:
            deep = [i for i, item in enumerate(self.config["queue_list"])
                    if os.path.exists(item.get("path", ""))
                    and (item.get("probe") is None
                         or (isinstance(item.get("probe"), dict)
                             and item["probe"].get("preview")))]
        except Exception:
            deep = []
        # one probe per unique path: 5x the same file = 1 parse fanned out
        # to every row (no duplicate work, no log spam, no cross-talk)
        by_path = {}
        order = []
        for i in deep:
            try:
                ppath = self.config["queue_list"][i].get("path", "")
            except Exception:
                continue
            if ppath not in by_path:
                by_path[ppath] = []
                order.append(ppath)
            by_path[ppath].append(i)
        n_deep = 0
        t0 = _t.time()
        for n, ppath in enumerate(order):
            try:
                if self.is_rendering:
                    break
                try:
                    self.log("Probing {}/{}: {} ...".format(
                        n + 1, len(order),
                        os.path.basename(ppath or "?")))
                except Exception:
                    pass
                p = render_probe(self.config.get("blender_path", ""), ppath,
                                 allow_blender=False)
            except Exception:
                p = None
            if isinstance(p, dict) and not p.get("preview"):
                for i in by_path.get(ppath, []):
                    self._store_probe(i, p, match_path=ppath)
                n_deep += 1
        if n_deep:
            did = True
            self.log("Full details loaded for {} file(s) in {:.1f}s (cameras, resolution).".format(
                n_deep, _t.time() - t0))
        return did

    def probe_all_deep(self):
        """Explicit bulk deep-read (queue menu). Cached on disk afterwards."""
        missing = [i for i, item in enumerate(self.config["queue_list"])
                   if (self.config["queue_list"][i].get("probe") is None
                       or self.config["queue_list"][i].get("probe", {}).get("preview"))
                   and os.path.exists(self.config["queue_list"][i].get("path", ""))]
        if not missing:
            self.log("All files already have full info.")
            return
        self.log("Deep-reading {} file(s) in the background (one-time, then cached)...".format(len(missing)))
        blender = self.config.get("blender_path", "")

        def _deep(i):
            try:
                item = self.config["queue_list"][i]
            except Exception:
                return
            probe = None
            if brm_blendparse is not None:
                try:
                    probe = brm_blendparse.fast_probe(item["path"])
                    try:
                        brm_blendparse.store_cached_probe(item["path"], probe)
                    except Exception:
                        pass
                except Exception:
                    probe = None
            if probe is None and blender and os.path.exists(blender):
                try:
                    fd, script = tempfile.mkstemp(suffix="_brm_probe.py")
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(PROBE_SCRIPT)
                    cmd = [blender, "-b", item["path"], "--python", script]
                    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                         errors="ignore", timeout=240, **_silent_popen_kwargs())
                    probe = parse_probe_output((res.stdout or "") + "\n" + (res.stderr or ""))
                    try:
                        os.remove(script)
                    except Exception:
                        pass
                except Exception:
                    probe = None
            if probe:
                try:
                    ppath = self.config["queue_list"][i].get("path", "")
                except Exception:
                    ppath = ""
                self._store_probe(i, probe, match_path=ppath)

        def _run():
            try:
                with ThreadPoolExecutor(max_workers=2) as ex:
                    list(ex.map(_deep, missing))
            except Exception as e:
                self.log("Background read failed: {}".format(e))
                return
            if not self.is_rendering:
                self.log("File info refresh finished.")

        threading.Thread(target=_run, daemon=True).start()

    def _apply_probe_defaults(self, item, probe):
        # NOTE: scene/camera/layer stay None (= follow file); rows display the
        # effective file values. Only flags are stored here.
        # The sim auto-GUI obeys the global toggle: with "Auto GUI mode"
        # OFF, probing leaves gui_mode alone (None = background render)
        # instead of force-enabling it. Explicit per-job choices always win.
        if probe.get("hurricane"):
            item["hurricane"] = True
            if item.get("gui_mode") is None and self.config.get("gui_for_hurricane", True):
                item["gui_mode"] = True

    def probe_selected(self):
        idx = self.selected_idx
        if idx is None:
            messagebox.showinfo("Probe", "Select a queue item first.")
            return
        item = self.config["queue_list"][idx]
        self.log("Probing {} ...".format(os.path.basename(item["path"])))
        threading.Thread(target=self._probe_thread, args=(idx,), daemon=True).start()

    def _probe_thread(self, idx):
        try:
            item = self.config["queue_list"][idx]
        except Exception:
            return
        probe = render_probe(self.config.get("blender_path", ""), item.get("path", ""))
        if probe:
            self._store_probe(idx, probe, match_path=item.get("path", ""))
        else:
            self.log("Probe FAILED for {}".format(os.path.basename(item.get("path", "?"))))

    def _store_probe(self, idx, probe, match_path=None):
        """Persist a probe result + refresh UI. Shared by manual/auto probing.
        The requesting slot wins when it still holds our file (matters for
        duplicate paths); otherwise re-resolve by path (queue edits shift
        indices); a vanished job's result is dropped, never misfiled."""
        try:
            q = self.config["queue_list"]
            if match_path:
                try:
                    here_ok = q[idx].get("path", "") == match_path
                except Exception:
                    here_ok = False
                if not here_ok:
                    for j, it in enumerate(q):
                        try:
                            if it.get("path") == match_path:
                                idx = j
                                break
                        except Exception:
                            continue
                    else:
                        return
            q[idx]["probe"] = probe
            self._apply_probe_defaults(q[idx], probe)
            save_config(self.config)
            self.log("Probe OK: {} scene(s), active='{}', sim={}, missing={}".format(
                len(probe.get("scenes", [])), probe.get("active"),
                probe.get("hurricane"), probe.get("missing_count", 0)))
            for mm in (probe.get("missing") or [])[:10]:
                self.log("  missing: {}".format(mm))
            self.after(0, lambda: self.refresh_row(idx))
            if idx == self.selected_idx:
                self.after(0, self.refresh_inspector)
        except Exception:
            pass


    # ================= VIEWPORT =================
    def _vp_job(self):
        try:
            if self.vp_idx is not None:
                return self.config["queue_list"][self.vp_idx]
        except Exception:
            pass
        return None

    def vp_show_job(self, idx):
        self.vp_idx = idx
        item = self._vp_job()
        try:
            if item is None:
                self.lbl_vp_name.configure(text="")
                self.lbl_vp_aspect.configure(text="—")
                self.vp_aspect = (16, 9)
                self.vp_path = None
                self._vp_clear_image()
                self._vp_center_text("NO JOB SELECTED", C_FAINT)
                for k in ("f", "s", "t", "mem"):
                    getattr(self, "lbl_vp_" + k).configure(text="")
                return
            probe = item.get("probe")
            eff = effective_job_settings(item, probe)
            rx, ry = eff.get("res_x") or 16, eff.get("res_y") or 9
            try:
                pct = int(eff.get("res_pct", 100))
                rx, ry = int(rx * pct / 100), int(ry * pct / 100)
            except Exception:
                pass
            self.vp_aspect = (max(1, rx), max(1, ry))
            if rx >= ry:
                asp = "16:9" if abs(rx / max(1, ry) - 16 / 9) < 0.3 else "{}:{}".format(rx, ry)
            else:
                asp = "9:16" if abs(ry / max(1, rx) - 16 / 9) < 0.3 else "{}:{}".format(rx, ry)
            self.lbl_vp_aspect.configure(text=asp)
            self.lbl_vp_name.configure(text=os.path.basename(item.get("path", "")))
            st = item.get("status", "Pending")
            label = {"Pending": "AWAITING RENDER", "Rendering": "", "Done": "",
                     "Stopped": "", "Failed": "RENDER FAILED"}.get(st, st.upper())
            color = {"Pending": C_FAINT, "Rendering": C_ACCENT, "Done": C_GREEN,
                     "Stopped": C_YELLOW, "Failed": C_RED}.get(st, C_GRAY_TXT)
            if st in ("Done", "Stopped"):
                # keep the latest rendered picture (never blank a finished job)
                lp = item.get("last_frame_path")
                if not (lp and os.path.exists(lp)):
                    try:
                        if self._vp_show_last_frame(item, eff):
                            lp = item.get("last_frame_path")
                    except Exception:
                        pass
                if lp and os.path.exists(lp):
                    try:
                        self.vp_path = lp
                        self.after(0, lambda p=lp: self._vp_draw_path(p))
                    except Exception:
                        pass
                    self._vp_center_text("", color)
                else:
                    self._vp_clear_image()
                    self._vp_center_text("COMPLETE" if st == "Done" else "STOPPED", color)
                try:
                    self.lbl_vp_f.configure(text="F {}/{}".format(
                        item.get("current_frame") or eff.get("frame_end", "?"),
                        eff.get("frame_end", "?")))
                except Exception:
                    pass
            else:
                if st != "Rendering":
                    self._vp_clear_image()
                if label:
                    self._vp_center_text(label, color)
                else:
                    self._vp_center_text("", color)
        except Exception:
            pass
        self._vp_redraw()

    def _vp_center_text(self, text, color):
        self._vp_center = (text, color)
        try:
            self.vp_canvas.delete("center")
            if text:
                w = self.vp_canvas.winfo_width()
                h = self.vp_canvas.winfo_height()
                if (w or 0) < 50:
                    w = 640
                if (h or 0) < 50:
                    h = 360
                self.vp_canvas.create_text(w / 2, h / 2, text=text, fill=color,
                                           font=("Source Code Pro", 10), tags="center")
        except Exception:
            pass

    def _vp_visible(self):
        try:
            return bool(self.panel_view.winfo_ismapped())
        except Exception:
            return False

    def _vp_sync_visibility(self):
        """Visibility policy: a hidden viewport holds no image memory (latest
        path is remembered); a re-shown one reloads it."""
        try:
            if self._vp_visible():
                if not getattr(self, "_vp_has_img", False) and getattr(self, "vp_path", None):
                    try:
                        self._vp_draw_path(self.vp_path)
                    except Exception:
                        pass
            else:
                try:
                    self.vp_canvas.delete("preview")
                except Exception:
                    pass
                self.vp_photo = None
                self._vp_has_img = False
                self._vp_drawn = None
        except Exception:
            pass

    def _vp_clear_image(self):
        try:
            self.vp_canvas.delete("preview")
            self.vp_photo = None
            self._vp_has_img = False
            self._vp_drawn = None
        except Exception:
            pass

    def _latest_frame_file(self, folder):
        try:
            best, best_key = None, None
            for f in os.listdir(folder):
                if not f.lower().endswith((".png", ".jpg", ".jpeg")):
                    continue
                m = re.search(r"(\d+)\.(png|jpg|jpeg)$", f, re.IGNORECASE)
                if not m:
                    continue
                try:
                    key = (int(m.group(1)), os.path.getmtime(os.path.join(folder, f)))
                except Exception:
                    continue
                if best_key is None or key > best_key:
                    best_key, best = key, os.path.join(folder, f)
            return best
        except Exception:
            return None

    def _vp_poll_latest(self, item):
        """Worker-safe: scan the job's output dir; if a newer frame file than
        the recorded one exists, adopt it and schedule a preview refresh."""
        try:
            probe = item.get("probe")
            try:
                eff = effective_job_settings(item, probe)
            except Exception:
                eff = {}
            out = (item.get("output") or (eff.get("output") if eff else None) or "//")
            folder = resolve_output_dir(out, item.get("path", ""))
            if not folder or not os.path.isdir(folder):
                return False
            latest = self._latest_frame_file(folder)
            if not latest or latest == item.get("last_frame_path"):
                return False
            try:
                item["last_frame_path"] = latest
            except Exception:
                pass
            try:
                self.after(0, lambda p=latest: self.update_image_preview(p))
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _vp_show_last_frame(self, item, eff=None):
        """Draw the newest rendered frame file, independent of the Saved:
        stream (covers skipped/resumed/cached renders that print nothing)."""
        try:
            try:
                eff = eff or effective_job_settings(item, item.get("probe"))
            except Exception:
                eff = {}
            out = (item.get("output") or (eff.get("output") if eff else None) or "//")
            folder = resolve_output_dir(out, item.get("path", ""))
            if not folder or not os.path.isdir(folder):
                return False
            latest = self._latest_frame_file(folder)
            if not latest:
                return False
            try:
                item["last_frame_path"] = latest
            except Exception:
                pass
            self.update_image_preview(latest)
            return True
        except Exception:
            return False

    def _vp_soon(self):
        try:
            if self._vp_after is not None:
                self.after_cancel(self._vp_after)
        except Exception:
            pass
        try:
            self._vp_after = self.after(120, self._vp_redraw)
        except Exception:
            pass

    def _vp_box(self):
        """Aspect-fit box (x0, y0, x1, y1) for the render canvas."""
        try:
            W = self.vp_canvas.winfo_width()
            H = self.vp_canvas.winfo_height()
            if W < 50:
                W = 640
            if H < 50:
                H = 360
        except Exception:
            return 0, 0, 640, 360
        aw, ah = self.vp_aspect
        s = min(W / aw, H / ah)
        bw, bh = aw * s, ah * s
        x0, y0 = (W - bw) / 2, (H - bh) / 2
        return x0, y0, x0 + bw, y0 + bh

    def _vp_redraw(self):
        try:
            c = self.vp_canvas
            c.delete("chrome")
            W = c.winfo_width() or 600
            H = c.winfo_height() or 400
            x0, y0, x1, y1 = self._vp_box()
            # scanlines
            y = y0 + 2
            while y < y1:
                c.create_line(x0, y, x1, y, fill="#101014", tags="chrome")
                y += 4
            # frame outline
            c.create_rectangle(x0, y0, x1, y1, outline=C_LINE2, tags="chrome")
            # corner brackets
            L, co = 16, C_ACCENT
            for (bx, by, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1),
                                     (x0, y1, 1, -1), (x1, y1, -1, -1)):
                c.create_line(bx, by, bx + dx * L, by, fill=co, width=2, tags="chrome")
                c.create_line(bx, by, bx, by + dy * L, fill=co, width=2, tags="chrome")
            # refit current preview into new box
            if self.vp_path:
                self._vp_draw_path(self.vp_path)
            else:
                txt, col = getattr(self, "_vp_center", ("", C_FAINT))
                self._vp_center_text(txt, col)
        except Exception:
            pass

    def _vp_draw_path(self, path, _retry=True):
        # Full-res direct load: the file exactly as Blender wrote it, centered
        # 1:1 (no thumbnail, no refining). Decode happens off-thread; only the
        # PhotoImage wrap + canvas place run on the UI thread.
        # Layer order (bottom→top): chrome < tiles < preview < center text.
        try:
            if not self._vp_visible():
                return False
        except Exception:
            pass
        try:
            if not Image:
                return False
            try:
                st = os.stat(path)
                key = (path, st.st_size, int(st.st_mtime))
            except Exception:
                key = (path,)
            if key == getattr(self, "_vp_drawn", None) and self.vp_photo is not None:
                try:
                    self._vp_place_existing()
                except Exception:
                    pass
                return True
            try:
                if getattr(self, "_vp_decoding", False):
                    self._vp_pending = path
                    return True
                self._vp_decoding = True
            except Exception:
                pass
            threading.Thread(target=self._vp_decode_worker, args=(path, key),
                             daemon=True).start()
            return True
        except Exception:
            return False

    def _vp_decode_worker(self, path, key):
        try:
            try:
                src = Image.open(path)
                img = src.convert("RGB")
            finally:
                try:
                    src.close()
                except Exception:
                    pass
        except Exception:
            img = None
        try:
            self.after(0, lambda: self._vp_place_photo(path, key, img))
        except Exception:
            pass

    def _vp_place_photo(self, path, key, img):
        try:
            if path != getattr(self, "vp_path", None):
                return  # superseded by a newer frame
            if img is None:
                # file may still be flushing to disk: one delayed retry
                try:
                    self.after(1200, lambda: self._vp_draw_path(path, False))
                except Exception:
                    pass
                return
            if not self._vp_visible():
                return
            from PIL import ImageTk
            self.vp_photo = ImageTk.PhotoImage(img)
            self._vp_drawn = key
            self._vp_place_existing()
        except Exception:
            pass
        finally:
            try:
                self._vp_decoding = False
                pend = getattr(self, "_vp_pending", None)
                self._vp_pending = None
                if pend:
                    self.update_image_preview(pend)
            except Exception:
                pass

    def _vp_place_existing(self):
        try:
            c = self.vp_canvas
            W = c.winfo_width() or 600
            H = c.winfo_height() or 400
            c.delete("preview")
            c.create_image(W / 2, H / 2, image=self.vp_photo, tags="preview")
            c.delete("center")
            c.delete("tiles")
            self._vp_has_img = True
            try:
                c.tag_lower("chrome")
                c.tag_raise("preview")
            except Exception:
                pass
        except Exception:
            pass

    # extensions PIL can draw directly (EXR needs OpenEXR: tiles + log instead)
    VP_VIEWABLE = ('.png', '.gif', '.ppm', '.pgm', '.jpg', '.jpeg',
                   '.tif', '.tiff', '.tga', '.bmp')

    def _vp_note(self, msg):
        try:
            import time as _t
            now = _t.time()
            if now - float(getattr(self, "_vp_note_t", 0) or 0) < 60:
                return
            self._vp_note_t = now
            self.log(msg)
        except Exception:
            pass

    def update_image_preview(self, image_path):
        # previews are always on; the only off-switch is a hidden viewport
        # (handled by the visibility gate in _vp_draw_path)
        try:
            if not (image_path or "").lower().endswith(self.VP_VIEWABLE):
                try:
                    ext = os.path.splitext(image_path or "")[1] or "?"
                except Exception:
                    ext = "?"
                self._vp_note("Preview: {} frames can't display ({}).".format(ext, image_path))
                return
            self.vp_path = image_path
            self.after(0, lambda p=image_path: self._vp_draw_path(p))
            self.after(0, self.vp_zoom_refresh)
        except Exception as e:
            print("Preview Error: {}".format(e))

    def vp_update_tiles(self, done, total):
        try:
            try:
                if not self._vp_visible():
                    return
            except Exception:
                pass
            # tiles are the no-picture progress visual: never draw (or leave)
            # stray squares over a rendered image
            if getattr(self, "_vp_has_img", False):
                try:
                    self.vp_canvas.delete("tiles")
                except Exception:
                    pass
                return
            c = self.vp_canvas
            c.delete("tiles")
            if total <= 0 or done < 0:
                return
            x0, y0, x1, y1 = self._vp_box()
            cols, rows = (4, 8) if (x1 - x0) < (y1 - y0) else (8, 4)
            n = cols * rows
            lit = min(n, int(n * max(0, done) / max(1, total)))
            cw, ch = (x1 - x0) / cols, (y1 - y0) / rows
            for i in range(n):
                cx, cy = i % cols, i // cols
                px, py = x0 + cx * cw + 2, y0 + cy * ch + 2
                if i < lit:
                    shade = "#16233d" if i % 3 else "#1a2c4d"
                    c.create_rectangle(px, py, px + cw - 4, py + ch - 4,
                                       fill=shade, outline="", tags="tiles")
                elif i == lit and done < total:
                    c.create_rectangle(px, py, px + cw - 4, py + ch - 4,
                                       outline=C_ACCENT, tags="tiles")
            c.tag_lower("tiles")
        except Exception:
            pass

    def vp_zoom_open(self):
        try:
            zw = getattr(self, "_zoom_win", None)
            if zw is not None and zw.winfo_exists():
                try:
                    zw.lift()
                except Exception:
                    pass
                return
        except Exception:
            pass
        try:
            z = self._zoom_win = tk.Toplevel(self)
        except Exception:
            return
        try:
            z.title("Render viewport")
            z.configure(bg="#000000")
            z.transient(self)
            w, h = self.winfo_width(), self.winfo_height()
            z.geometry("%dx%d+120+80" % (max(800, w - 200), max(600, h - 120)))
            z.lift()
        except Exception:
            pass
        try:
            cv = self._zoom_canvas = tk.Canvas(z, bg="#080808", highlightthickness=0, bd=0,
                                               cursor="hand2")
            cv.pack(fill="both", expand=True)
            cv.bind("<Configure>", lambda e: self._zoom_soon())
            cv.bind("<Button-1>", lambda e: self.vp_zoom_close())
            z.bind("<Escape>", lambda e: self.vp_zoom_close())
            zb = tk.Frame(z, bg="#000000", height=26)
            zb.pack(fill="x", side="bottom")
            zb.pack_propagate(False)
            self._zoom_stats = tk.Label(zb, text="", font=F_MONO_SM, fg=C_GRAY_TXT, bg="#000000")
            self._zoom_stats.pack(side="left", padx=10)
            tk.Label(zb, text="CLICK / ESC TO CLOSE", font=F_LABEL_SM, fg=C_FAINT,
                     bg="#000000").pack(side="right", padx=10)
            ToolTip(cv, "Click to close")
            self._zoom_after = None
            self.vp_zoom_refresh()
        except Exception:
            pass

    def vp_zoom_close(self):
        try:
            zw = getattr(self, "_zoom_win", None)
            if zw is not None:
                zw.destroy()
        except Exception:
            pass
        self._zoom_win = None
        self._zoom_canvas = None

    def _zoom_soon(self):
        try:
            if getattr(self, "_zoom_after", None) is not None:
                self.after_cancel(self._zoom_after)
        except Exception:
            pass
        try:
            self._zoom_after = self.after(120, self.vp_zoom_refresh)
        except Exception:
            pass

    def vp_zoom_refresh(self):
        try:
            zc = getattr(self, "_zoom_canvas", None)
            if zc is None or not zc.winfo_exists():
                return
            W, H = zc.winfo_width(), zc.winfo_height()
            if W < 50 or H < 50:
                return
            zc.delete("all")
            aw, ah = getattr(self, "vp_aspect", (16, 9))
            s = min(W / max(1, aw), H / max(1, ah))
            bw, bh = aw * s, ah * s
            x0, y0 = (W - bw) / 2, (H - bh) / 2
            x1, y1 = x0 + bw, y0 + bh
            L = 18
            for (bx, by, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1),
                                     (x0, y1, 1, -1), (x1, y1, -1, -1)):
                zc.create_line(bx, by, bx + dx * L, by, fill=C_ACCENT, width=2)
                zc.create_line(bx, by, bx, by + dy * L, fill=C_ACCENT, width=2)
            shown = False
            if getattr(self, "vp_path", None) and Image:
                try:
                    img = Image.open(self.vp_path).convert("RGB")
                    img.thumbnail((max(8, int(bw)), max(8, int(bh))), Image.LANCZOS)
                    from PIL import ImageTk
                    self._zoom_photo = ImageTk.PhotoImage(img)
                    zc.create_image(W / 2, H / 2, image=self._zoom_photo)
                    shown = True
                except Exception:
                    pass
            if not shown:
                txt, col = getattr(self, "_vp_center", ("", C_FAINT))
                if txt:
                    zc.create_text(W / 2, H / 2, text=txt, fill=col, font=("Source Code Pro", 12))
            try:
                item = self._vp_job()
                nm = os.path.basename(item.get("path", "")) if item else ""
                st = item.get("status", "") if item else ""
                self._zoom_stats.configure(text="{}   {}".format(nm, st))
            except Exception:
                pass
        except Exception:
            pass

    def vp_set_live(self, on, job_idx=None):
        try:
            self._live_on = bool(on)
            if on:
                try:
                    self.live_frame.pack(side="right", padx=(8, 0))
                except Exception:
                    pass
                if job_idx is not None:
                    self.vp_show_job(job_idx)
            else:
                try:
                    self.live_frame.pack_forget()
                except Exception:
                    pass
                self.lbl_live_dot.configure(fg=C_FAINT)
        except Exception:
            pass

    # ================= BOTTOM PANEL =================
    def build_bottom(self):
        bot = tk.Frame(self, bg=C_PANEL)
        bot.grid_columnconfigure(0, weight=1)
        self.panel_log = bot
        tk.Frame(bot, bg=C_LINE, height=1).grid(row=0, column=0, sticky="ew")

        tabs = tk.Frame(bot, bg=C_PANEL)
        tabs.grid(row=1, column=0, sticky="ew", padx=14)
        tabs.grid_columnconfigure(0, weight=1)
        oc = tk.Frame(tabs, bg=C_PANEL)
        oc.grid(row=0, column=0, sticky="e", pady=4)
        tk.Label(oc, text="ON COMPLETION", font=("Barlow Condensed", 9, "bold"),
                 fg=C_FAINT, bg=C_PANEL).pack(side="left", padx=(0, 8))
        self.var_on_complete = tk.StringVar(value=self.config.get("on_complete", "Do nothing"))
        self.opt_on_complete = ctk.CTkOptionMenu(oc, variable=self.var_on_complete,
                                                 values=["Do nothing", "Shutdown PC", "Sleep"],
                                                 fg_color=C_ENTRY, button_color=C_LINE2,
                                                 button_hover_color=C_HOVER, text_color=C_TXT,
                                                 dropdown_fg_color=C_ENTRY,
                                                 dropdown_text_color=C_TXT,
                                                 dropdown_hover_color=C_ACCENT,
                                                 font=F_MONO_SM, dropdown_font=F_MONO_SM,
                                                 corner_radius=0, width=130, height=26,
                                                 anchor="w")
        self.opt_on_complete.pack(side="left")
        self.var_on_complete.trace_add("write", lambda *a: self.on_complete_changed(self.var_on_complete.get()))

        body = tk.Frame(bot, bg=C_PANEL)
        body.grid(row=2, column=0, sticky="nsew", padx=14, pady=(4, 2))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        bot.grid_rowconfigure(2, weight=1)

        # log view (stretches with the slot: no dead space under the text)
        self.view_log = tk.Frame(body, bg=C_PANEL)
        self.view_log.grid(row=0, column=0, sticky="nsew")
        self.view_log.grid_columnconfigure(0, weight=1)
        self.view_log.grid_rowconfigure(0, weight=1)
        self.log_box = ctk.CTkTextbox(self.view_log, font=F_MONO, height=110,
                                       fg_color=C_BG, corner_radius=0, border_width=1,
                                       border_color=C_LINE,
                                       text_color=C_TXT)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        self.log_box.configure(state="disabled")
        try:
            tb = self.log_box._textbox
            tb.tag_config("log_ok", foreground=C_GREEN)
            tb.tag_config("log_err", foreground=C_RED)
            tb.tag_config("log_warn", foreground=C_YELLOW)
            tb.tag_config("log_info", foreground=C_ACCENT2)
        except Exception:
            pass

        # status bar
        sbar = tk.Frame(bot, bg=C_PANEL)
        sbar.grid(row=3, column=0, sticky="ew", padx=14, pady=(2, 6))
        sbar.grid_columnconfigure(1, weight=1)
        self.lbl_stat_left = tk.Label(sbar, text="Success rate: —", font=F_MONO_SM,
                                      fg=C_FAINT, bg=C_PANEL, anchor="w")
        self.lbl_stat_left.grid(row=0, column=0, sticky="w")
        self.lbl_stat_mid = tk.Label(sbar, text="Timing data will appear here", font=F_MONO_SM,
                                     fg=C_FAINT, bg=C_PANEL)
        self.lbl_stat_mid.grid(row=0, column=1)
        tk.Label(sbar, text="v{}".format(APP_VERSION), font=F_MONO_SM,
                 fg=C_FAINT, bg=C_PANEL).grid(row=0, column=2, sticky="e")

        self.select_bottom("progress")
        self.update_stats_bar()

    def select_bottom(self, name):
        # Bottom panel is log-only now; the live progress block lives in the
        # center column. Kept for backend call compatibility.
        self.bottom_tab = name
        try:
            self.view_log.grid()
            self.log_box.see("end")
        except Exception:
            pass

    def on_complete_changed(self, value):
        self.config["on_complete"] = value
        save_config(self.config)

    def update_stats_bar(self):
        try:
            items = load_history()
            renders = [h for h in items if h.get("kind") == "render"]
            if renders:
                done = sum(1 for h in renders if str(h.get("status", "")).startswith("Done"))
                self.lbl_stat_left.configure(
                    text="Success rate: {}/{} ({}%)".format(done, len(renders), int(100 * done / max(1, len(renders)))))
                last = renders[-1]
                self.lbl_stat_mid.configure(text="Last: {} — {} {}".format(
                    os.path.basename(last.get("file", "?")), last.get("status", "?"),
                    last.get("detail", ""))[:120])
        except Exception:
            pass

    def draw_strip(self, done=0, current=-1, total=0):
        self._strip_state = (done, current, total)
        try:
            pct = max(0.0, min(1.0, done / max(1, total)))
            if abs(pct * 100 - self._vp_last_pct) >= 2 or done >= total:
                self._vp_last_pct = pct * 100
                self.vp_update_tiles(done, total)
                try:
                    self.vp_bar.place_configure(relwidth=pct)
                except Exception:
                    pass
        except Exception:
            pass

    def update_progress_ui(self, text, frac, stats):
        try:
            self.lbl_prog_job.configure(text=text)
            self.bar_overall.set(max(0.0, min(1.0, frac)))
            self.lbl_prog_mid.configure(text=stats)
        except Exception:
            pass

    LOG_TAGS = (
        ("log_ok", ("RENDER DONE", "CONVERT DONE", "DONE", "Sequence Finished",
                    "--- ALL DONE", "Probe OK", "Full details", "Settings Saved")),
        ("log_err", ("RENDER CRASHED", "CRASHED", "FAILED", "Failed", "CRITICAL",
                     "Error", "FFmpeg failed")),
        ("log_warn", ("RENDER STOP", "STOPPING", "WARNING", "Max attempts",
                      "SKIP", "PAUSED", "Convert SKIP", "Missing ")),
        ("log_info", ("===", "--- STARTING", "Starting", "Split", "Moved",
                      "Deep-reading", "Deep-read", "GUI mode", "Probe", "Loading",
                      "File info", "Convert", "FFmpeg", "Auto-Restarting")),
    )

    def _log_tag(self, msg):
        try:
            s = (msg or "").lstrip()
            for tag, keys in self.LOG_TAGS:
                for k in keys:
                    if s.startswith(k):
                        return tag
        except Exception:
            pass
        return None

    def log(self, msg):
        try:
            tag = self._log_tag(msg)
            tb = getattr(self.log_box, "_textbox", None)
            self.log_box.configure(state="normal")
            if tb is not None and tag:
                tb.insert("end", msg + "\n", tag)
            else:
                self.log_box.insert("end", msg + "\n")
            try:
                target = tb if tb is not None else self.log_box
                if int(str(target.index("end-1c")).split(".")[0]) > 3000:
                    target.delete("1.0", "1000.0")
            except Exception:
                pass
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        except Exception:
            try:
                print(msg)
            except Exception:
                pass

    def _dfmt(self, tmpl, fallback, **kw):
        """Discord template with graceful fallback to the builtin text."""
        try:
            if tmpl:
                return str(tmpl).format(**kw)
        except Exception:
            pass
        try:
            return str(fallback).format(**kw)
        except Exception:
            return str(fallback)

    def send_discord(self, url, title, desc, color, patch_id=None):
        if not self.config.get("enable_discord", True):
            return None
        if not url:
            return None
        data = {"embeds": [{"title": title, "description": desc, "color": color,
                            "timestamp": datetime.utcnow().isoformat() + "Z"}]}
        try:
            if patch_id:
                r = requests.patch(f"{url}/messages/{patch_id}", json=data)
                if r.status_code == 404:
                    return None
                return patch_id
            r = requests.post(f"{url}?wait=true", json=data)
            r.raise_for_status()
            return r.json().get('id')
        except Exception:
            return None

    def show_notification(self, message, color=C_GREEN):
        try:
            f = ctk.CTkFrame(self, fg_color=color, corner_radius=10, height=40)
            f.place(relx=1.2, rely=0.06, anchor="e")
            lb = ctk.CTkLabel(f, text=message, text_color="black", font=("Segoe UI", 12, "bold"))
            lb.pack(padx=20, pady=10)
            f.bind("<Button-1>", lambda e: f.destroy())
            lb.bind("<Button-1>", lambda e: f.destroy())

            def animate_in(x):
                if x > 0.98:
                    f.place(relx=x - 0.02, rely=0.06, anchor="e")
                    self.after(10, lambda: animate_in(x - 0.02))
                else:
                    self.after(3000, animate_out)

            def animate_out():
                try:
                    x = float(f.place_info()['relx'])
                    if x < 1.2:
                        f.place(relx=x + 0.02, rely=0.06, anchor="e")
                        self.after(10, animate_out)
                    else:
                        f.destroy()
                except Exception:
                    pass
            animate_in(1.2)
        except Exception:
            pass

    # ================= SETTINGS WINDOW =================
    def open_settings_window(self):
        try:
            if self.settings_win is not None and self.settings_win.winfo_exists():
                try:
                    self.settings_win.deiconify()
                    self.settings_win.lift()
                except Exception:
                    pass
                return
        except Exception:
            pass
        try:
            win = self.settings_win = ctk.CTkToplevel(self)
            win.title("Settings")
            win.geometry("920x860")
            win.configure(fg_color=C_PANEL)
            try:
                # build + theme while hidden: no visible restyle flicker
                win.withdraw()
                win.transient(self)
            except Exception as e:
                self.log("Settings window setup: {}".format(e))
        except Exception as e:
            try:
                self.log("Cannot open Settings: {}".format(e))
            except Exception:
                pass
            messagebox.showerror("Settings", "Could not open Settings:\n{}".format(e))
            return
        try:
            self._build_settings(win)
        except Exception as e:
            try:
                self.log("Settings build failed: {}".format(e))
            except Exception:
                pass
            messagebox.showerror("Settings", "Settings failed to load:\n{}".format(e))
            return
        try:
            win.deiconify()
            win.lift()
        except Exception:
            pass

    def _build_settings(self, win):
        _hdr = ctk.CTkLabel(win, text="SETTINGS", font=F_HEAD, text_color=C_ACCENT)
        _hdr.pack(anchor="w", padx=16, pady=(12, 0))
        _hdr._keep_style = True
        tabs = ctk.CTkTabview(win)
        tabs.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        for t in ("General", "Discord", "FFmpeg", "History"):
            tabs.add(t)
        g = tabs.tab("General")
        g.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(g, text="Blender Executable Path").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        r0 = ctk.CTkFrame(g, fg_color="transparent")
        r0.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10)
        r0.grid_columnconfigure(0, weight=1)
        self.s_blender = ctk.CTkEntry(r0)
        self.s_blender.grid(row=0, column=0, sticky="ew")
        self.s_blender.insert(0, self.config.get("blender_path", ""))
        ctk.CTkButton(r0, text="Browse", width=90, command=lambda: self.browse_into(self.s_blender)).grid(row=0, column=1, padx=(6, 0))

        self.s_quiet = self._mkcheck(g, "Quiet mode (-q)")
        self.s_quiet.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=4)
        if self.config.get("quiet_mode", True):
            self.s_quiet.select()
        self.s_filter = self._mkcheck(g, "Filter noisy Cycles lines (faster piped renders)")
        self.s_filter.grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=4)
        if self.config.get("filter_noisy_cycles_lines", True):
            self.s_filter.select()
        self.s_console = self._mkcheck(g, "Show Blender console window (no in-app logs)")
        self.s_console.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=4)
        if self.config.get("show_blender_console", False):
            self.s_console.select()
        self.s_guih = self._mkcheck(g, "Auto GUI mode for sim files (sim-safe)")
        self.s_guih.grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=4)
        if self.config.get("gui_for_hurricane", True):
            self.s_guih.select()
        self.s_autoprobe = self._mkcheck(g, "Auto full file info (cameras, resolution)")
        self.s_autoprobe.grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=4)
        if self.config.get("auto_full_probe", True):
            self.s_autoprobe.select()
        ToolTip(self.s_autoprobe, "OFF = instant add, details load on Refresh/render (never freezes)")

        fr = ctk.CTkFrame(g, fg_color="transparent")
        fr.grid(row=7, column=0, columnspan=2, sticky="ew", padx=10, pady=6)
        ctk.CTkLabel(fr, text="Batch limit (0=All):").pack(side="left")
        self.s_batch = ctk.CTkEntry(fr, width=70)
        self.s_batch.pack(side="left", padx=6)
        self.s_batch.insert(0, str(self.config.get("batch_size", 0)))
        ctk.CTkLabel(fr, text="Retry delay s:").pack(side="left", padx=(12, 0))
        self.s_delay = ctk.CTkEntry(fr, width=60)
        self.s_delay.pack(side="left", padx=6)
        self.s_delay.insert(0, str(self.config.get("retry_delay", 5.0)))
        self.s_sound = self._mkcheck(fr, "Finish sound")
        self.s_sound.pack(side="left", padx=(12, 0))
        if self.config.get("finish_sound", True):
            self.s_sound.select()

        fr2 = ctk.CTkFrame(g, fg_color="transparent")
        fr2.grid(row=8, column=0, columnspan=2, sticky="ew", padx=10, pady=6)
        self.s_restart = self._mkcheck(fr2, "Auto restart on crash, tries:")
        self.s_restart.pack(side="left")
        if self.config.get("auto_restart", False):
            self.s_restart.select()
        self.s_retries = ctk.CTkEntry(fr2, width=50)
        self.s_retries.pack(side="left", padx=6)
        self.s_retries.insert(0, str(self.config.get("max_retries", 5)))
        ToolTip(self.s_retries, "Crash restarts per job, then next in queue (stops when empty)")
        ctk.CTkLabel(fr2, text="On completion:").pack(side="left", padx=(16, 4))
        self.s_oncomplete = ctk.CTkOptionMenu(fr2, values=["Do nothing", "Shutdown PC", "Sleep"])
        self.s_oncomplete.pack(side="left")
        try:
            self.s_oncomplete.set(self.config.get("on_complete", "Do nothing"))
        except Exception:
            pass

        d = tabs.tab("Discord")
        d.grid_columnconfigure(0, weight=1)
        d.grid_rowconfigure(0, weight=1)
        dscroll = ctk.CTkScrollableFrame(d, fg_color="transparent", corner_radius=0,
                                         scrollbar_button_color=C_LINE2,
                                         scrollbar_button_hover_color=C_GRAY_TXT)
        dscroll.grid(row=0, column=0, sticky="nsew")
        dscroll.grid_columnconfigure(0, weight=1)
        self.s_discord = self._mkcheck(dscroll, "Enable Discord notifications")
        self.s_discord.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
        if self.config.get("enable_discord", True):
            self.s_discord.select()
        ctk.CTkLabel(dscroll, text="Webhook URL").grid(row=1, column=0, sticky="w", padx=10)
        self.s_webhook = ctk.CTkEntry(dscroll)
        self.s_webhook.grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        self.s_webhook.insert(0, self.config.get("webhook_url", ""))
        fr3 = ctk.CTkFrame(dscroll, fg_color="transparent")
        fr3.grid(row=3, column=0, sticky="w", padx=10, pady=4)
        ctk.CTkLabel(fr3, text="Update interval s:").pack(side="left")
        self.s_dinterval = ctk.CTkEntry(fr3, width=70)
        self.s_dinterval.pack(side="left", padx=6)
        self.s_dinterval.insert(0, str(self.config.get("discord_interval", 15.0)))
        ctk.CTkLabel(dscroll, text="Title template").grid(row=4, column=0, sticky="w", padx=10)
        self.s_title = ctk.CTkEntry(dscroll)
        self.s_title.grid(row=5, column=0, sticky="ew", padx=10, pady=4)
        self.s_title.insert(0, self.config.get("webhook_title", ""))
        ctk.CTkLabel(dscroll, text="Description template").grid(row=6, column=0, sticky="w", padx=10)
        self.s_desc = ctk.CTkTextbox(dscroll, height=110)
        self.s_desc.grid(row=7, column=0, sticky="ew", padx=10, pady=4)
        self.s_desc.insert("1.0", self.config.get("webhook_desc", ""))
        ctk.CTkLabel(dscroll, text="Vars: {filename} {scene} {camera} {start} {end} {frame} {attempt} {avg} {est} {bar} {pct} {elapsed} {duration} {date}").grid(
            row=8, column=0, sticky="w", padx=10)
        ctk.CTkLabel(dscroll, text="Start message").grid(row=9, column=0, sticky="w", padx=10)
        self.s_startmsg = ctk.CTkTextbox(dscroll, height=55)
        self.s_startmsg.grid(row=10, column=0, sticky="ew", padx=10, pady=4)
        self.s_startmsg.insert("1.0", self.config.get("webhook_start_desc", ""))
        ctk.CTkLabel(dscroll, text="Done title").grid(row=11, column=0, sticky="w", padx=10)
        self.s_donetitle = ctk.CTkEntry(dscroll)
        self.s_donetitle.grid(row=12, column=0, sticky="ew", padx=10, pady=4)
        self.s_donetitle.insert(0, self.config.get("webhook_done_title", ""))
        ctk.CTkLabel(dscroll, text="Done message").grid(row=13, column=0, sticky="w", padx=10)
        self.s_donemsg = ctk.CTkTextbox(dscroll, height=55)
        self.s_donemsg.grid(row=14, column=0, sticky="ew", padx=10, pady=4)
        self.s_donemsg.insert("1.0", self.config.get("webhook_done_desc", ""))
        ctk.CTkLabel(dscroll, text="Crash title").grid(row=15, column=0, sticky="w", padx=10)
        self.s_crashtitle = ctk.CTkEntry(dscroll)
        self.s_crashtitle.grid(row=16, column=0, sticky="ew", padx=10, pady=4)
        self.s_crashtitle.insert(0, self.config.get("webhook_crash_title", ""))
        ctk.CTkLabel(dscroll, text="Crash message").grid(row=17, column=0, sticky="w", padx=10)
        self.s_crashmsg = ctk.CTkTextbox(dscroll, height=55)
        self.s_crashmsg.grid(row=18, column=0, sticky="ew", padx=10, pady=4)
        self.s_crashmsg.insert("1.0", self.config.get("webhook_crash_desc", ""))
        ctk.CTkLabel(dscroll, text="Stop title").grid(row=19, column=0, sticky="w", padx=10)
        self.s_stoptitle = ctk.CTkEntry(dscroll)
        self.s_stoptitle.grid(row=20, column=0, sticky="ew", padx=10, pady=4)
        self.s_stoptitle.insert(0, self.config.get("webhook_stop_title", ""))
        ctk.CTkLabel(dscroll, text="Stop message").grid(row=21, column=0, sticky="w", padx=10)
        self.s_stopmsg = ctk.CTkTextbox(dscroll, height=55)
        self.s_stopmsg.grid(row=22, column=0, sticky="ew", padx=10, pady=4)
        self.s_stopmsg.insert("1.0", self.config.get("webhook_stop_desc", ""))

        ff = tabs.tab("FFmpeg")
        ff.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ff, text="ffmpeg.exe path (empty = auto)").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.s_ffmpeg = ctk.CTkEntry(ff)
        self.s_ffmpeg.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=4)
        self.s_ffmpeg.insert(0, self.config.get("ffmpeg_path", ""))
        ctk.CTkButton(ff, text="Browse", width=90, command=lambda: self.browse_into(self.s_ffmpeg)).grid(row=1, column=2, padx=(0, 10))
        ctk.CTkLabel(ff, text="Default FPS:").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        self.s_ffps = ctk.CTkEntry(ff, width=100)
        self.s_ffps.grid(row=2, column=1, sticky="w", padx=10)
        self.s_ffps.insert(0, str(self.config.get("ffmpeg_fps", 60)))
        ctk.CTkLabel(ff, text="CRF:").grid(row=3, column=0, sticky="w", padx=10, pady=4)
        self.s_fcrf = ctk.CTkEntry(ff, width=100)
        self.s_fcrf.grid(row=3, column=1, sticky="w", padx=10)
        self.s_fcrf.insert(0, str(self.config.get("ffmpeg_crf", 12)))
        ctk.CTkButton(ff, text="Convert folder to MP4...", command=self.convert_folder_dialog).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=12)

        h = tabs.tab("History")
        h.grid_columnconfigure(0, weight=1)
        h.grid_rowconfigure(0, weight=1)
        self.history_box = tk.Listbox(h, bg="#1a1d21", fg="white", font=("Segoe UI", 11), relief="flat")
        self.history_box.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        hr = ctk.CTkFrame(h, fg_color="transparent")
        hr.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkButton(hr, text="Refresh", fg_color=C_ENTRY, command=self.refresh_history_ui).pack(side="left", padx=4)
        ctk.CTkButton(hr, text="Open Folder", fg_color=C_ENTRY, command=self.open_history_folder).pack(side="left", padx=4)
        ctk.CTkButton(hr, text="Clear", fg_color=C_RED, command=self.clear_history).pack(side="left", padx=4)
        self.refresh_history_ui()

        br = ctk.CTkFrame(win, fg_color="transparent")
        br.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(br, text="Save", command=self.save_settings_window).pack(side="left", padx=(0, 8))
        ctk.CTkButton(br, text="Close", fg_color=C_ENTRY, command=win.destroy).pack(side="left")
        self._theme_settings(win)

    def _theme_settings(self, win):
        """Apply the app design language to the settings window."""
        def walk(w):
            try:
                kids = w.winfo_children()
            except Exception:
                return
            for k in kids:
                try:
                    if getattr(k, "_keep_style", False):
                        walk(k)
                        continue
                    cls = k.__class__.__name__
                    if cls == "CTkLabel":
                        k.configure(font=F_SET, text_color=C_GRAY_TXT)
                    elif cls == "CTkEntry":
                        k.configure(font=F_SET_MONO, text_color=C_TXT, fg_color=C_ENTRY,
                                    border_color=C_LINE2, border_width=1, height=32)
                    elif cls == "CTkButton":
                        try:
                            txt = k.cget("text")
                        except Exception:
                            txt = ""
                        if txt == "Save":
                            k.configure(font=F_SET, fg_color=C_ACCENT,
                                        hover_color=C_ACCENT_HOVER, text_color="white",
                                        corner_radius=0, height=SET_H)
                        elif txt == "Clear":
                            k.configure(font=F_SET, fg_color="transparent",
                                        hover_color=C_ROW, text_color=C_RED,
                                        border_width=1, border_color=C_RED,
                                        corner_radius=0, height=SET_H)
                        else:
                            k.configure(font=F_SET, fg_color="transparent",
                                        hover_color=C_ROW, text_color=C_TXT,
                                        border_width=1, border_color=C_LINE2,
                                        corner_radius=0, height=SET_H)
                    elif cls == "CTkCheckBox":
                        k.configure(font=F_SET, text_color=C_TXT, fg_color=C_ACCENT,
                                    hover_color=C_ACCENT_HOVER, border_color=C_GRAY_TXT,
                                    border_width=2, checkmark_color="#ffffff",
                                    corner_radius=0)
                        try:
                            k.configure(checkbox_width=22, checkbox_height=22)
                        except Exception:
                            pass
                    elif cls == "CTkOptionMenu":
                        k.configure(font=F_SET_MONO, text_color=C_TXT, fg_color=C_ENTRY,
                                    button_color=C_LINE2, button_hover_color=C_HOVER,
                                    dropdown_fg_color=C_ENTRY, dropdown_text_color=C_TXT,
                                    dropdown_hover_color=C_ACCENT, corner_radius=0,
                                    height=32)
                    elif cls == "CTkTextbox":
                        k.configure(font=F_SET_MONO, text_color=C_TXT, fg_color=C_BG,
                                    border_color=C_LINE, border_width=1, corner_radius=0,
                                    scrollbar_button_color=C_LINE2,
                                    scrollbar_button_hover_color=C_GRAY_TXT)
                    elif cls == "CTkTabview":
                        try:
                            k.configure(fg_color=C_PANEL, corner_radius=0, border_width=0,
                                        segmented_button_fg_color=C_BG,
                                        segmented_button_selected_color=C_ACCENT,
                                        segmented_button_selected_hover_color=C_ACCENT_HOVER,
                                        segmented_button_unselected_hover_color=C_HOVER)
                            try:
                                k._segmented_button.configure(font=F_SET_HEAD)
                            except Exception:
                                pass
                        except Exception:
                            pass
                    elif cls == "CTkFrame":
                        try:
                            if k.cget("fg_color") not in ("transparent",):
                                k.configure(fg_color="transparent")
                        except Exception:
                            pass
                    elif cls == "Listbox":
                        k.configure(bg=C_BG, fg=C_TXT, font=F_SET_MONO,
                                    selectbackground=C_ACCENT, selectforeground="white",
                                    relief="flat", bd=0, highlightthickness=0)
                except Exception:
                    pass
                walk(k)
        walk(win)

    def browse_into(self, entry):
        p = filedialog.askopenfilename(filetypes=[("Executables", "*.exe"), ("All Files", "*.*")])
        if p:
            entry.delete(0, "end")
            entry.insert(0, p)

    def save_settings_window(self):
        try:
            self.config["blender_path"] = self.s_blender.get()
            self.config["quiet_mode"] = bool(self.s_quiet.get())
            self.config["filter_noisy_cycles_lines"] = bool(self.s_filter.get())
            self.config["show_blender_console"] = bool(self.s_console.get())
            self.config["gui_for_hurricane"] = bool(self.s_guih.get())
            self.config["auto_full_probe"] = bool(self.s_autoprobe.get())
            self.config["auto_restart"] = bool(self.s_restart.get())
            self.config["finish_sound"] = bool(self.s_sound.get())
            self.config["on_complete"] = self.s_oncomplete.get()
            self.config["enable_discord"] = bool(self.s_discord.get())
            self.config["webhook_url"] = self.s_webhook.get()
            self.config["webhook_title"] = self.s_title.get()
            self.config["webhook_desc"] = self.s_desc.get("1.0", "end-1c")
            self.config["webhook_start_desc"] = self.s_startmsg.get("1.0", "end-1c")
            self.config["webhook_done_title"] = self.s_donetitle.get()
            self.config["webhook_done_desc"] = self.s_donemsg.get("1.0", "end-1c")
            self.config["webhook_crash_title"] = self.s_crashtitle.get()
            self.config["webhook_crash_desc"] = self.s_crashmsg.get("1.0", "end-1c")
            self.config["webhook_stop_title"] = self.s_stoptitle.get()
            self.config["webhook_stop_desc"] = self.s_stopmsg.get("1.0", "end-1c")
            self.config["ffmpeg_path"] = self.s_ffmpeg.get().strip()
            try:
                self.config["batch_size"] = int(self.s_batch.get())
            except Exception:
                pass
            try:
                self.config["max_retries"] = max(1, int(self.s_retries.get()))
            except Exception:
                pass
            try:
                self.config["retry_delay"] = max(0.0, float(self.s_delay.get()))
            except Exception:
                pass
            try:
                self.config["discord_interval"] = max(2.0, float(self.s_dinterval.get()))
            except Exception:
                pass
            try:
                self.config["ffmpeg_fps"] = max(1, int(self.s_ffps.get()))
            except Exception:
                pass
            try:
                self.config["ffmpeg_crf"] = min(51, max(0, int(self.s_fcrf.get())))
            except Exception:
                pass
            try:
                self.var_on_complete.set(self.config["on_complete"])
            except Exception:
                pass
            save_config(self.config)
            self.show_notification("Settings Saved!")
        except Exception as e:
            messagebox.showerror("Settings", str(e))

    def _history_projects(self):
        """History lists finished blend projects only (actions live in the log)."""
        try:
            return [h for h in load_history()
                    if h.get("kind") == "render"
                    and str(h.get("status", "")).startswith("Done")]
        except Exception:
            return []

    def refresh_history_ui(self):
        try:
            self.history_box.delete(0, "end")
            for hh in self._history_projects():
                self.history_box.insert("end", "[{}] {}: {} {}".format(
                    hh.get("time", "?"), os.path.basename(hh.get("file", "?")),
                    hh.get("status", "?"), hh.get("detail", "")))
            self.history_box.see("end")
        except Exception:
            pass

    def open_history_folder(self):
        try:
            sel = self.history_box.curselection()
            if not sel:
                return
            hh = self._history_projects()[sel[0]]
            folder = hh.get("folder", "")
            if folder and os.path.isdir(folder):
                os.startfile(folder)
            else:
                f = hh.get("file", "")
                if f and os.path.exists(os.path.dirname(f)):
                    os.startfile(os.path.dirname(f))
        except Exception as e:
            messagebox.showerror("History", str(e))

    def clear_history(self):
        if messagebox.askyesno("History", "Clear the whole render history?"):
            save_history([])
            self.refresh_history_ui()


    # ================= RENDER =================
    def start_render_thread(self):
        if getattr(self, "is_rendering", False):
            messagebox.showinfo("Render", "A render is already running.")
            return
        if not self.config["queue_list"]:
            messagebox.showerror("Error", "Queue is empty! Press ADD BLEND OR BRQ FILES.")
            return
        if not any(i.get("enabled", True) and i.get("status") != "Done" for i in self.config["queue_list"]):
            messagebox.showinfo("Render", "Nothing to render (all disabled or Done).")
            return
        self.is_rendering = True
        self.paused = False
        self.stop_event.clear()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_pause.configure(state="normal" if psutil is not None else "disabled", text="PAUSE",
                                 image=self._icon("pause", 11, C_YELLOW))
        self.select_bottom("progress")
        self.log("--- STARTING RENDER ---")
        threading.Thread(target=self.render_loop, daemon=True).start()

    def toggle_pause(self):
        if not self.is_rendering or self.render_process is None:
            return
        if psutil is None:
            messagebox.showwarning("Pause", "Install psutil for pause support:\npip install psutil")
            return
        try:
            proc = psutil.Process(self.render_process.pid)
            kids = proc.children(recursive=True)
            if not self.paused:
                for k in kids:
                    try:
                        k.suspend()
                    except Exception:
                        pass
                try:
                    proc.suspend()
                except Exception:
                    pass
                self.paused = True
                self.btn_pause.configure(text="RESUME", image=self._icon("play", 11, C_YELLOW))
                self.log("|| PAUSED (process suspended)")
            else:
                try:
                    proc.resume()
                except Exception:
                    pass
                for k in kids:
                    try:
                        k.resume()
                    except Exception:
                        pass
                self.paused = False
                self.btn_pause.configure(text="PAUSE", image=self._icon("pause", 11, C_YELLOW))
                self.log("RESUMED")
        except Exception as e:
            self.log("Pause failed: {}".format(e))

    def stop_render(self):
        if self.is_rendering:
            self.stop_event.set()
            if self.render_process:
                try:
                    if psutil is not None and self.paused:
                        try:
                            psutil.Process(self.render_process.pid).resume()
                        except Exception:
                            pass
                    self.render_process.terminate()
                    try:
                        pid = self.render_process.pid
                    except Exception:
                        pid = None
                    if pid:
                        self.after(8000, lambda: self._stop_escalate(pid))
                except Exception:
                    pass
            self.paused = False
            self.log("!!! STOPPING !!! (kills the process if it ignores this)")

    def _stop_escalate(self, pid):
        try:
            if not self.stop_event.is_set():
                return
            p = getattr(self, "render_process", None)
            if p is None:
                return
            try:
                if p.pid != pid or p.poll() is not None:
                    return
            except Exception:
                return
            self.log("STOP stuck: killing Blender process.")
            try:
                p.kill()
            except Exception:
                pass
        except Exception:
            pass

    def render_loop(self):
        blender_path = self.config["blender_path"]
        webhook_url = self.config["webhook_url"]
        batch_size = self.config.get("batch_size", 0)
        try:
            max_attempts = max(1, int(self.config.get("max_retries", 5)))
        except Exception:
            max_attempts = 5
        try:
            retry_delay = max(0.0, float(self.config.get("retry_delay", 5.0)))
        except Exception:
            retry_delay = 5.0
        if not self.config.get("auto_restart", False):
            max_attempts = 1
        processed_count = 0

        # live length: jobs added mid-render join the same run instead of
        # waiting for the next START (removals are blocked while rendering,
        # so indices below stay stable and only appends extend the run)
        i = 0
        while True:
            try:
                n = len(self.config["queue_list"])
            except Exception:
                break
            if i >= n:
                break
            if self.stop_event.is_set():
                break
            if batch_size > 0 and processed_count >= batch_size:
                break
            item = migrate_queue_item(self.config["queue_list"][i])
            self.config["queue_list"][i] = item
            if not item.get("enabled", True):
                i += 1
                continue
            if item.get("status") == "Done":
                i += 1
                continue
            blend_file = item["path"]
            if not os.path.exists(blend_file):
                self.log("SKIP: file not found: {}".format(blend_file))
                item["status"] = "Failed"
                save_config(self.config)
                self.after(0, lambda _i=i: self.refresh_row(_i))
                i += 1
                continue

            job_t0 = time.time()
            self.log("\n=== STARTING PROJECT {}: {} ===".format(i + 1, os.path.basename(blend_file)))
            item["status"] = "Rendering"
            save_config(self.config)
            self.after(0, lambda _i=i: self.refresh_row(_i))
            self._vp_samples = ""
            self._vp_mem = ""
            self._vp_last_pct = -1
            try:
                self.after(0, lambda _i=i: self.vp_set_live(True, _i))
            except Exception:
                pass
            self.discord_msg_id = None
            try:
                probe = item.get("probe")
                if probe is None or probe.get("preview"):
                    # Deep read before rendering: sim detection + cameras must be exact.
                    # (One-time per file, then cached on disk.)
                    self.log("Deep-reading file info (sim check, cameras, layers)...")
                    probe = render_probe(blender_path, blend_file)
                    if probe:
                        item["probe"] = probe
                        self._apply_probe_defaults(item, probe)
                        save_config(self.config)
                        self.after(0, lambda _i=i: self.refresh_row(_i))
                        if i == self.selected_idx:
                            self.after(0, self.refresh_inspector)
                eff = effective_job_settings(item, probe)
                scene, camera = eff["scene"], eff["camera"]
                project_start_f, end_f = eff["frame_start"], eff["frame_end"]
                if project_start_f > end_f:
                    project_start_f, end_f = end_f, project_start_f
                output_path = eff["output"]
                self.log("Job: scene='{}' camera='{}' layer='{}' engine={} {}sp res={}x{}@{}% frames={}-{} out={}".format(
                    scene, camera, eff.get("view_layer"), eff.get("engine"), eff.get("samples"),
                    eff.get("res_x"), eff.get("res_y"), eff.get("res_pct"),
                    project_start_f, end_f, output_path))
                if item.get("hurricane") or (probe and probe.get("hurricane")):
                    gui_auto = self.config.get("gui_for_hurricane", True)
                    use_gui = item["gui_mode"] if item.get("gui_mode") is not None else gui_auto
                    if use_gui:
                        self.log("Hurricane sim: rendering with VISIBLE Blender (GUI mode).")
                    else:
                        self.log("WARNING: sim file with GUI mode OFF — object may vanish/freeze!")
                self.global_start_frame = project_start_f
                self.global_end_frame = end_f
                out_dir = resolve_output_dir(output_path, blend_file)
                total = max(1, end_f - project_start_f + 1)
                self.after(0, lambda: self.draw_strip(0, 0, total))
                current_start = self.find_last_rendered_frame(output_path, project_start_f, end_f, blend_file)
                attempt = 1
                if current_start > end_f:
                    self.log("All frames found. Marking as Done.")
                    item["status"] = "Done"
                    processed_count += 1
                    save_config(self.config)
                    log_history({"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "kind": "render",
                                 "file": blend_file, "status": "Done (cached)",
                                 "detail": "scene={} {}-{}".format(scene, project_start_f, end_f),
                                 "folder": out_dir})
                    self.after(0, lambda _i=i: self.refresh_row(_i))
                    continue
                success = False
                while current_start <= end_f and not self.stop_event.is_set():
                    self.log("\n--- Batch: Frame {} to {} (Attempt {}) ---".format(current_start, end_f, attempt))
                    setup_res = eff["res_pct"] if (probe or item.get("res_pct")) else None
                    setup_out = output_path if (probe or item.get("output")) else None
                    setup_rx = eff["res_x"] if (probe and (item.get("ov", {}) or {}).get("res_x")) else (item.get("res_x") if (item.get("ov", {}) or {}).get("res_x") else None)
                    setup_ry = eff["res_y"] if (probe and (item.get("ov", {}) or {}).get("res_y")) else (item.get("res_y") if (item.get("ov", {}) or {}).get("res_y") else None)
                    success, last_frame = self.run_blender_process(
                        blender_path, blend_file, current_start, end_f, webhook_url, attempt,
                        scene=scene, camera=camera, res_pct=setup_res, output=setup_out,
                        gui_mode=item.get("gui_mode") if item.get("gui_mode") is not None else (
                            self.config.get("gui_for_hurricane", True) and bool(item.get("hurricane") or (probe and probe.get("hurricane")))),
                        view_layer=eff.get("view_layer"), engine=eff.get("engine") or None,
                        samples=eff.get("samples"), res_x=setup_rx, res_y=setup_ry,
                        film=eff.get("film_transparent"),
                        overwrite=eff.get("overwrite"), placeholder=eff.get("placeholder"),
                        file_format=eff.get("file_format") or None,
                        color_mode=eff.get("color_mode") or None,
                        color_depth=eff.get("color_depth") or None,
                        compression=eff.get("compression"),
                        python_args=eff.get("python_args") or "",
                        progress_item=item,
                        progress_row=lambda: self.refresh_row(i))
                    if self.stop_event.is_set():
                        break
                    if success:
                        self.log("RENDER DONE: {}".format(os.path.basename(blend_file)))
                        item["status"] = "Done"
                        item["current_frame"] = end_f
                        item["total_frames"] = max(1, end_f - project_start_f + 1)
                        item["last_duration"] = time.strftime('%Mm %Ss', time.gmtime(time.time() - job_t0))
                        processed_count += 1
                        save_config(self.config)
                        try:
                            total = max(1, end_f - project_start_f + 1)
                            self.after(0, lambda: self.lbl_vp_f.configure(
                                text="F {}/{}".format(end_f, end_f)))
                            self.after(0, lambda: self.update_progress_ui(
                                "Done: {}".format(os.path.basename(blend_file)), 1.0,
                                "{} of {} frames (100%)".format(total, total)))
                            self.after(0, lambda: self.draw_strip(total, total, total))
                            self.after(0, lambda _i=i: self.refresh_row(_i))
                            try:
                                self.after(0, lambda _i=i: self._vp_show_last_frame(
                                    self.config["queue_list"][_i]))
                            except Exception:
                                pass
                        except Exception:
                            pass
                        break
                    else:
                        if self.stop_event.is_set():
                            self.log("RENDER STOP: {}".format(os.path.basename(blend_file)))
                            item["status"] = "Stopped"
                            processed_count += 1
                            save_config(self.config)
                            break
                        self.log("RENDER CRASHED: {} at frame {}".format(
                            os.path.basename(blend_file), last_frame))
                        self.log_crash("Crash at frame {}".format(last_frame), last_frame, blend_file)
                        if attempt < max_attempts:
                            self.log("Auto-Restarting in {}s... (Attempt {}/{})".format(retry_delay, attempt, max_attempts))
                            current_start = last_frame + 1
                            if current_start > end_f:
                                current_start = end_f
                            attempt += 1
                            rescanned = self.find_last_rendered_frame(output_path, current_start, end_f, blend_file)
                            if rescanned > current_start:
                                current_start = rescanned
                            time.sleep(retry_delay)
                        else:
                            self.log("Max attempts reached. Moving to next project.")
                            item["status"] = "Failed"
                            processed_count += 1
                            save_config(self.config)
                            try:
                                if self.config.get("finish_sound", True):
                                    play_finish_sound()
                                    time.sleep(0.3)
                                    play_finish_sound()
                            except Exception:
                                pass
                            break
                dur = time.time() - job_t0
                log_history({"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "kind": "render",
                             "file": blend_file, "status": item.get("status", "?"),
                             "detail": "scene={} {}-{} in {}".format(scene, project_start_f, end_f, time.strftime('%Hh %Mm %Ss', time.gmtime(dur))),
                             "folder": out_dir})
            except Exception as e:
                self.log("CRITICAL ERROR: {}".format(e))
                self.log_crash(str(e), 0, blend_file)
                item["status"] = "Failed"
                processed_count += 1
                save_config(self.config)
                log_history({"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "kind": "render",
                             "file": blend_file, "status": "Failed", "detail": str(e)[:200],
                             "folder": os.path.dirname(blend_file)})
            self.after(0, lambda _i=i: self.refresh_row(_i))
            try:
                self.after(0, lambda _i=i: self.vp_show_job(_i))
            except Exception:
                pass
            i += 1

        self.is_rendering = False
        self.paused = False
        try:
            self.after(0, lambda: self.vp_set_live(False))
            self.after(0, lambda: self.update_stats_bar())
        except Exception:
            pass
        try:
            self.after(0, lambda: self.btn_start.configure(state="normal"))
            self.after(0, lambda: self.btn_stop.configure(state="disabled"))
            self.after(0, lambda: self.btn_pause.configure(state="disabled", text="PAUSE",
                                                           image=self._icon("pause", 11, C_YELLOW)))
            self.after(0, lambda: self.update_progress_ui("Idle", 0, ""))
        except Exception:
            pass
        self.log("--- ALL DONE ---")
        try:
            self.show_notification("Queue finished!")
        except Exception:
            pass
        try:
            if self.config.get("finish_sound", True):
                play_finish_sound()
        except Exception:
            pass
        try:
            self._on_complete_action()
        except Exception:
            pass

    def _remaining_jobs(self):
        try:
            return [it for it in self.config["queue_list"]
                    if it.get("enabled", True)
                    and it.get("status") not in ("Done", "Failed")]
        except Exception:
            return []

    def _on_complete_action(self):
        """Shutdown/Sleep once, after ALL queue files (never mid-queue, never
        after a manual stop, never with jobs left over e.g. batch limit)."""
        try:
            oc = self.config.get("on_complete")
            if oc not in ("Shutdown PC", "Sleep"):
                return False
            if self.stop_event.is_set():
                return False
            remaining = self._remaining_jobs()
            if remaining:
                self.log("On-complete '{}' skipped: {} job(s) left.".format(oc, len(remaining)))
                return False
            if oc == "Shutdown PC":
                self.log("Shutting down PC in 60s (queue complete). Run 'shutdown /a' to abort.")
                try:
                    os.system('shutdown /s /t 60 /c "BRM queue complete"')
                except Exception as e:
                    self.log("Shutdown failed: {}".format(e))
            else:
                self.log("Sending PC to sleep (queue complete).")
                try:
                    if os.name == "nt":
                        os.system('rundll32.exe powrprof.dll,SetSuspendState 0,1,0')
                    else:
                        os.system('systemctl suspend')
                except Exception as e:
                    self.log("Sleep failed: {}".format(e))
            return True
        except Exception:
            return False

    def get_blender_settings(self, blender_path, blend_file):
        for item in self.config.get("queue_list", []):
            if item.get("path") == blend_file and item.get("probe"):
                eff = effective_job_settings(item, item["probe"])
                self.log("Detected: Start {}, End {}".format(eff['frame_start'], eff['frame_end']))
                return eff["frame_start"], eff["frame_end"], eff["output"]
        self.log("Reading settings...")
        probe = render_probe(blender_path, blend_file)
        if probe and probe.get("scenes"):
            sc = scene_info_from_probe(probe, probe.get("active")) or probe["scenes"][0]
            self.log("Detected: Start {}, End {}".format(sc['frame_start'], sc['frame_end']))
            return sc["frame_start"], sc["frame_end"], sc.get("output", "//")
        return 1, 250, "//"

    def find_last_rendered_frame(self, output_path, start, end, blend_path=""):
        out_dir = resolve_output_dir(output_path, blend_path or (self.config["queue_list"][0]["path"] if self.config["queue_list"] else ""))
        if not os.path.isdir(out_dir):
            return start
        base = os.path.basename(os.path.normpath((output_path or "").strip()))
        if "#" in base:
            prefix = base.split("#")[0]
        else:
            prefix = os.path.splitext(base)[0] if os.path.splitext(base)[1] else ""
        max_frame = start - 1
        try:
            for f in os.listdir(out_dir):
                if not f.lower().endswith(('.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff', '.tga', '.bmp')):
                    continue
                if prefix and not f.startswith(prefix):
                    continue
                m = re.findall(r'(\d+)', os.path.splitext(f)[0])
                if m:
                    frame_num = int(m[-1])
                    if start <= frame_num <= end:
                        max_frame = max(max_frame, frame_num)
        except Exception:
            return start
        return max_frame + 1

    def log_crash(self, error, frame, project):
        try:
            with open("crashlog.txt", "a", encoding="utf-8") as f:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write("[{}] Project: {} | Frame: {} | Error: {}\n".format(ts, project, frame, error))
        except Exception:
            pass

    def run_blender_process(self, blender_path, blend_file, start_frame, end_frame, webhook_url, attempt_num,
                            scene=None, camera=None, res_pct=None, output=None, gui_mode=False,
                            view_layer=None, engine=None, samples=None, res_x=None, res_y=None,
                            film=None, overwrite=None, placeholder=None, file_format=None,
                            color_mode=None, color_depth=None, compression=None, python_args="",
                            progress_item=None, progress_row=None):
        quiet = bool(self.config.get("quiet_mode", True))
        show_console = bool(self.config.get("show_blender_console", False))
        filter_noisy = bool(self.config.get("filter_noisy_cycles_lines", True))

        setup_script = None
        gui_script = None
        try:
            if gui_mode:
                gui_script = write_setup_script(scene=scene, camera=camera, res_pct=res_pct, output=output,
                                                frame_s=start_frame, frame_e=end_frame, gui=True,
                                                view_layer=view_layer, engine=engine, samples=samples,
                                                res_x=res_x, res_y=res_y, film=film,
                                                overwrite=overwrite, placeholder=placeholder,
                                                file_format=file_format, color_mode=color_mode,
                                                color_depth=color_depth, compression=compression,
                                                python_trailer=build_python_trailer(python_args))
                cmd = [blender_path, blend_file]
                if scene:
                    cmd += ["-S", scene]
                cmd += ["--python", gui_script]
                self.log("GUI mode: Blender window will open for this job.")
            else:
                needs_setup = bool(camera or res_pct or output or engine or samples or res_x or res_y
                                   or film is not None or overwrite is not None or placeholder is not None
                                   or file_format or color_mode or color_depth or compression is not None
                                   or view_layer)
                if needs_setup:
                    setup_script = write_setup_script(scene=scene, camera=camera, res_pct=res_pct, output=output,
                                                      view_layer=view_layer, engine=engine, samples=samples,
                                                      res_x=res_x, res_y=res_y, film=film,
                                                      overwrite=overwrite, placeholder=placeholder,
                                                      file_format=file_format, color_mode=color_mode,
                                                      color_depth=color_depth, compression=compression)
                cmd = [blender_path, "-b", blend_file]
                if scene:
                    cmd += ["-S", scene]
                if setup_script:
                    cmd += ["--python", setup_script]
                # extra user python args (background CLI form)
                if python_args and os.path.exists(python_args) and python_args.lower().endswith(".py"):
                    cmd += ["--python", python_args]
                elif python_args:
                    cmd += ["--python-expr", python_args]
                if quiet:
                    cmd.append("-q")
                cmd += ["-s", str(start_frame), "-e", str(end_frame), "-a"]
        except Exception as e:
            self.log("Failed to build render command: {}".format(e))
            return False, start_frame

        popen_kwargs = {}
        if show_console and not gui_mode and os.name == "nt" and hasattr(subprocess, "CREATE_NEW_CONSOLE"):
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            self.render_process = subprocess.Popen(cmd, **popen_kwargs)
        else:
            popen_kwargs.update(_silent_popen_kwargs())
            self.render_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                   text=True, encoding='utf-8', errors='ignore', bufsize=1,
                                                   **popen_kwargs)

        current_display_frame = start_frame
        finished_frame = None
        job_start_time = time.time()
        frame_render_times = deque(maxlen=10)
        last_frame_finish_time = time.time()
        last_discord_update = 0
        last_frame_dur = 0.0

        title_text = self._dfmt(self.config.get("webhook_title", ""),
                                "RENDERING: {filename}",
                                filename=os.path.basename(blend_file))
        start_desc = self._dfmt(self.config.get("webhook_start_desc", ""),
                                "Scene: {scene} | Camera: {camera} | Frames: {start}-{end}\nStarting attempt {attempt}...",
                                filename=os.path.basename(blend_file), scene=scene or "?",
                                camera=camera or "?", start=start_frame, end=end_frame,
                                attempt=attempt_num)
        self.discord_msg_id = self.send_discord(webhook_url, title_text, start_desc, 16776960)
        self.config["last_msg_id"] = self.discord_msg_id
        save_config(self.config)

        last_row_push = [0.0]
        last_vp_poll = [0.0]

        def push_progress(avg_time, elapsed_job, rem_seconds):
            total_range = self.global_end_frame - self.global_start_frame + 1
            try:
                if progress_item is not None:
                    ref = finished_frame if finished_frame is not None else start_frame - 1
                    progress_item["current_frame"] = min(self.global_end_frame, ref + 1)
                    progress_item["total_frames"] = max(1, total_range)
                    if progress_row is not None and time.time() - last_row_push[0] > 1.0:
                        last_row_push[0] = time.time()
                        try:
                            self.after(0, progress_row)
                        except Exception:
                            pass
                    # folder truth: newest file in the output dir wins, even if
                    # Saved: lines were missed, buffered, or skipped entirely
                    if time.time() - last_vp_poll[0] > 3.0:
                        last_vp_poll[0] = time.time()
                        try:
                            self._vp_poll_latest(progress_item)
                        except Exception:
                            pass
            except Exception:
                pass
            ref_frame = finished_frame if finished_frame is not None else start_frame - 1
            current_done = (ref_frame - self.global_start_frame + 1)
            pct = min(1.0, max(0.0, current_done / total_range)) if total_range > 0 else 0
            bar = "█" * int(15 * pct) + "░" * (15 - int(15 * pct))
            display_frame_num = ref_frame + 1 if ref_frame < self.global_end_frame else self.global_end_frame
            est_str = time.strftime('%Hh %Mm %Ss', time.gmtime(rem_seconds)) if avg_time > 0 else "Calculating..."
            elapsed_str = time.strftime('%Hh %Mm %Ss', time.gmtime(elapsed_job))
            avg_str = "{:.1f}s".format(avg_time) if avg_time > 0 else "..."
            desc_tmpl = self.config.get("webhook_desc", "")
            try:
                desc = desc_tmpl.format(filename=os.path.basename(blend_file), attempt=attempt_num,
                                        start=self.global_start_frame, end=self.global_end_frame,
                                        frame=display_frame_num, avg=avg_str, est=est_str, bar=bar,
                                        pct=int(pct * 100), elapsed=elapsed_str,
                                        date=datetime.now().strftime("%d.%m.%Y %H:%M"))
            except Exception:
                desc = "Error formatting template"
            self.send_discord(webhook_url, title_text, desc, 4309328, patch_id=self.discord_msg_id)
            try:
                label = "Rendering: {} ({})".format(os.path.basename(blend_file), display_frame_num)
                mid = "{} of {} frames ({}%)".format(max(0, current_done), total_range, int(pct * 100))
                self.after(0, lambda: self.update_progress_ui(label, pct, mid))
                self.after(0, lambda: self.lbl_prog_start.configure(text="Start: {}".format(self.global_start_frame)))
                self.after(0, lambda: self.lbl_prog_end.configure(text="End: {}".format(self.global_end_frame)))
                self.after(0, lambda: self.lbl_prog_elapsed.configure(text="Elapsed: {}".format(elapsed_str)))
                self.after(0, lambda: self.lbl_prog_last.configure(
                    text="Last frame: {}".format("{:.2f}s".format(last_frame_dur) if last_frame_dur else "--")))
                self.after(0, lambda: self.lbl_prog_rem.configure(text="Remaining: {}".format(est_str)))
                self.after(0, lambda: self.draw_strip(max(0, current_done), current_done, total_range))
                self.after(0, lambda: self.lbl_vp_f.configure(
                    text="F {}/{}".format(display_frame_num, self.global_end_frame)))
                self.after(0, lambda: self.lbl_vp_t.configure(text="T {}".format(elapsed_str)))
                self.after(0, lambda: self.lbl_vp_s.configure(
                    text="S {}".format(getattr(self, "_vp_samples", "") or "—")))
                self.after(0, lambda: self.lbl_vp_mem.configure(
                    text="MEM {}".format(getattr(self, "_vp_mem", "") or "—")))
            except Exception:
                pass

        def do_discord_update():
            avg_time = sum(frame_render_times) / len(frame_render_times) if frame_render_times else 0
            elapsed_job = time.time() - job_start_time
            ref_frame = finished_frame if finished_frame is not None else start_frame - 1
            frames_left = max(0, self.global_end_frame - ref_frame)
            push_progress(avg_time, elapsed_job, avg_time * frames_left)

        if show_console and not gui_mode:
            while self.render_process.poll() is None:
                if self.stop_event.is_set():
                    try:
                        self.render_process.terminate()
                    except Exception:
                        pass
                    return False, current_display_frame
                if time.time() - last_discord_update > self.config.get("discord_interval", 15.0):
                    do_discord_update()
                    last_discord_update = time.time()
                time.sleep(0.5)
            return_code = self.render_process.returncode
        else:
            _last_out = [time.time()]
            _last_warn = [0.0]
            while self.render_process.poll() is None:
                if self.stop_event.is_set():
                    try:
                        self.render_process.terminate()
                    except Exception:
                        pass
                    return False, current_display_frame
                try:
                    if time.time() - _last_warn[0] > 300 and time.time() - _last_out[0] > 600:
                        _last_warn[0] = time.time()
                        self.log("Still waiting: no Blender output for 10m+ "
                                 "(long frames/bakes can do this) ...")
                except Exception:
                    pass
                try:
                    line = self.render_process.stdout.readline()
                    if not line:
                        continue
                    line = line.strip()
                    _last_out[0] = time.time()
                except Exception:
                    continue
                if "ModuleNotFoundError" in line or "addon" in line.lower():
                    continue
                match_fra = re.search(r"(?:Fra:|Frame:|Frame)\s*(\d+)", line, re.IGNORECASE)
                if match_fra:
                    current_display_frame = int(match_fra.group(1))
                    try:
                        self.after(0, lambda f=current_display_frame: self.lbl_prog_status.configure(text="Fra:{}".format(f)))
                    except Exception:
                        pass
                    try:
                        m_s = re.search(r"Rendering\s+(\d+)\s*/\s*(\d+)\s*samples", line, re.IGNORECASE)
                        if m_s:
                            self._vp_samples = "{}/{}".format(m_s.group(1), m_s.group(2))
                        m_m = re.search(r"Mem:([\d.]+\s*[MG]B?)", line, re.IGNORECASE)
                        if m_m:
                            self._vp_mem = m_m.group(1).replace(" ", "")
                    except Exception:
                        pass
                if filter_noisy:
                    noisy_substrings = ("Synchronizing object", "Updating Geometry BVH", "Building BVH",
                                        "Building OptiX acceleration structure", "Copying Attributes to device",
                                        "Computing attributes", "Updating Objects | Copying Transformations")
                    if any(s in line for s in noisy_substrings):
                        continue
                if "Saved:" in line or "Error" in line:
                    self.log(line)
                elif "Fra:" in line and ("Time:" in line or "Remaining:" in line or "Sample" in line):
                    self.log(line)
                    try:
                        self.after(0, lambda t=line: self.lbl_prog_status.configure(text=t[:150]))
                    except Exception:
                        pass
                elif "[BRM " in line:
                    self.log(line)
                match_saved = re.search(r"Saved:.*[\/\\](\d+)\.\w+['\"]", line, re.IGNORECASE)
                if not match_saved:
                    match_saved = re.search(r"Saved:.*?(\d+)\.\w+['\"]?\s*$", line, re.IGNORECASE)
                if match_saved:
                    finished_frame = int(match_saved.group(1))
                    current_display_frame = finished_frame
                    now = time.time()
                    duration = now - last_frame_finish_time
                    last_frame_dur = duration
                    last_frame_finish_time = now
                    if duration > 0.1:
                        frame_render_times.append(duration)
                    saved_path_match = re.search(r"Saved:\s*['\"](.*?)['\"]", line, re.IGNORECASE)
                    if saved_path_match:
                        saved_path = saved_path_match.group(1)
                        if not os.path.isabs(saved_path):
                            saved_path = os.path.join(os.path.dirname(blend_file), saved_path)
                        try:
                            if progress_item is not None and os.path.exists(saved_path):
                                progress_item["last_frame_path"] = saved_path
                        except Exception:
                            pass
                        self.after(0, lambda p=saved_path: self.update_image_preview(p))
                    if time.time() - last_discord_update > self.config.get("discord_interval", 15.0):
                        do_discord_update()
                        last_discord_update = time.time()
                elif time.time() - last_discord_update > self.config.get("discord_interval", 15.0):
                    do_discord_update()
                    last_discord_update = time.time()
        # Blender (esp. GUI-mode block-buffered stdout) can leave its final
        # lines unread in the pipe: drain them so finished_frame and the last
        # preview image are exact instead of randomly stale.
        try:
            _so = getattr(self.render_process, "stdout", None)
            if _so is not None:
                _t_end = time.time() + 15
                _tail = 0
                while time.time() < _t_end and _tail < 2000:
                    try:
                        _line = _so.readline()
                    except Exception:
                        break
                    if not _line:
                        break
                    _tail += 1
                    _line = _line.strip()
                    if not _line:
                        continue
                    _m2 = re.search(r"Saved:.*[\/\\](\d+)\.\w+['\"]", _line, re.IGNORECASE)
                    if not _m2:
                        _m2 = re.search(r"Saved:.*?(\d+)\.\w+['\"]?\s*$", _line, re.IGNORECASE)
                    if _m2:
                        try:
                            finished_frame = int(_m2.group(1))
                            current_display_frame = finished_frame
                        except Exception:
                            pass
                        try:
                            _sm = re.search(r"Saved:\s*['\"](.*?)['\"]", _line, re.IGNORECASE)
                            if _sm:
                                _sp2 = _sm.group(1)
                                if not os.path.isabs(_sp2):
                                    _sp2 = os.path.join(os.path.dirname(blend_file), _sp2)
                                if os.path.exists(_sp2):
                                    if progress_item is not None:
                                        progress_item["last_frame_path"] = _sp2
                                    try:
                                        self.after(0, lambda p=_sp2: self.update_image_preview(p))
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                    else:
                        _mf = re.search(r"(?:Fra:|Frame:|Frame)\s*(\d+)", _line, re.IGNORECASE)
                        if _mf:
                            try:
                                current_display_frame = int(_mf.group(1))
                            except Exception:
                                pass
        except Exception:
            pass
        try:
            return_code = self.render_process.returncode
        except Exception:
            return_code = 1
        result_frame = finished_frame if finished_frame is not None else current_display_frame
        for p in (setup_script, gui_script):
            if p:
                try:
                    os.remove(p)
                except Exception:
                    pass
        fn = os.path.basename(blend_file)
        dur = time.strftime('%Hh %Mm %Ss', time.gmtime(time.time() - job_start_time))
        if return_code == 0:
            done_title = self._dfmt(self.config.get("webhook_done_title", ""),
                                    "✅ RENDER COMPLETE: {filename}", filename=fn)
            done_desc = self._dfmt(self.config.get("webhook_done_desc", ""),
                                   "Scene: {scene}\nCamera: {camera}\nFrames: {start}-{end} (finished {frame})\nDuration: {duration}",
                                   filename=fn, scene=scene or "?", camera=camera or "?",
                                   start=self.global_start_frame, end=self.global_end_frame,
                                   frame=result_frame, duration=dur)
            self.send_discord(webhook_url, done_title, done_desc, 65280, patch_id=self.discord_msg_id)
            self.config["last_msg_id"] = None
            save_config(self.config)
            return True, result_frame
        if self.stop_event.is_set():
            stop_title = self._dfmt(self.config.get("webhook_stop_title", ""),
                                    "⏸ RENDER STOPPED: {filename}", filename=fn)
            stop_desc = self._dfmt(self.config.get("webhook_stop_desc", ""),
                                   "Scene: {scene}\nCamera: {camera}\nFrames: {start}-{end}\nStopped at frame {frame}",
                                   filename=fn, scene=scene or "?", camera=camera or "?",
                                   start=self.global_start_frame, end=self.global_end_frame,
                                   frame=result_frame)
            self.send_discord(webhook_url, stop_title, stop_desc, 16776960, patch_id=self.discord_msg_id)
            return False, result_frame
        crash_title = self._dfmt(self.config.get("webhook_crash_title", ""),
                                 "🔴 RENDER CRASHED: {filename}", filename=fn)
        crash_desc = self._dfmt(self.config.get("webhook_crash_desc", ""),
                                "Scene: {scene}\nCamera: {camera}\nFrames: {start}-{end}\nLast frame saved: {frame}\nAttempt: {attempt}",
                                filename=fn, scene=scene or "?", camera=camera or "?",
                                start=self.global_start_frame, end=self.global_end_frame,
                                frame=result_frame, attempt=attempt_num)
        self.send_discord(webhook_url, crash_title, crash_desc, 16711680, patch_id=self.discord_msg_id)
        return False, result_frame

    # ================= FFMPEG INSTANT CONVERT =================
    def _ffmpeg_bin(self):
        ff = ffmpeg_exe(self.config.get("ffmpeg_path", ""))
        if not ff:
            self.log("FFmpeg not found. Set its path in Settings > FFmpeg.")
        return ff

    def _start_convert(self, targets, scope):
        if not targets:
            return
        if self.is_converting:
            messagebox.showinfo("Convert", "A conversion is already running.")
            return
        self.select_bottom("log")
        try:
            if len(targets) > 1 or scope != "selection":
                self.log("Converting {} job(s) [{}], max 2 ffmpeg at once ...".format(
                    len(targets), scope))
        except Exception:
            pass
        threading.Thread(target=self._convert_thread, args=(targets,), daemon=True).start()

    def convert_selected_to_mp4(self):
        try:
            paths = set(self.selected_paths or set())
        except Exception:
            paths = set()
        targets = []
        try:
            for it in self.config["queue_list"]:
                try:
                    if it.get("path", "") in paths:
                        targets.append(migrate_queue_item(it))
                except Exception:
                    continue
        except Exception:
            pass
        if not targets:
            if self.selected_idx is None:
                messagebox.showinfo("Convert", "Select a queue job first (finished jobs have PNGs ready).")
                return
            try:
                targets = [migrate_queue_item(self.config["queue_list"][self.selected_idx])]
            except Exception:
                return
        self._start_convert(targets, "selection")

    def convert_mass_mp4(self):
        """Footer one-click: selection, else all finished jobs lacking an MP4."""
        try:
            paths = set(self.selected_paths or set())
        except Exception:
            paths = set()
        targets = []
        try:
            for it in self.config["queue_list"]:
                try:
                    if it.get("path", "") in paths:
                        targets.append(migrate_queue_item(it))
                except Exception:
                    continue
        except Exception:
            pass
        scope = "selection"
        if not targets:
            scope = "finished"
            try:
                for it in self.config["queue_list"]:
                    try:
                        if it.get("status") != "Done":
                            continue
                        mp4 = it.get("converted_mp4")
                        if mp4 and os.path.exists(mp4):
                            continue
                        targets.append(migrate_queue_item(it))
                    except Exception:
                        continue
            except Exception:
                pass
        if not targets:
            messagebox.showinfo("Convert", "Nothing to convert (no selection, no finished jobs without MP4).")
            return
        self._start_convert(targets, scope)

    def convert_folder_dialog(self):
        folder = filedialog.askdirectory(title="Pick a folder with rendered PNGs")
        if not folder:
            return
        if self.is_converting:
            messagebox.showinfo("Convert", "A conversion is already running.")
            return
        self.select_bottom("log")
        threading.Thread(target=self._convert_folders_thread, args=([folder], None), daemon=True).start()

    def _mark_converted(self, folder):
        """Flag queue jobs rendered into `folder` as MP4-ready (row badge)."""
        try:
            mp4s = [os.path.join(folder, f) for f in os.listdir(folder)
                    if f.lower().endswith(".mp4")]
            if not mp4s:
                return
            newest = max(mp4s, key=os.path.getmtime)
            hit = False
            for q in self.config["queue_list"]:
                try:
                    out = q.get("output") or ""
                    probe = q.get("probe")
                    eff = effective_job_settings(q, probe) if probe else None
                    if eff and eff.get("output"):
                        out = eff["output"]
                    if os.path.normcase(os.path.normpath(resolve_output_dir(out, q.get("path", "")))) == \
                            os.path.normcase(os.path.normpath(folder)):
                        q["converted_mp4"] = newest
                        hit = True
                except Exception:
                    continue
            if hit:
                save_config(self.config)
                try:
                    self.after(0, self.refresh_all_rows)
                except Exception:
                    pass
        except Exception:
            pass

    def _convert_thread(self, items):
        # at most 2 ffmpeg instances at once: more just bottleneck each other
        self.is_converting = True
        try:
            from concurrent.futures import ThreadPoolExecutor

            def _one(item):
                try:
                    blend = item.get("path", "")
                    probe = item.get("probe")
                    eff = effective_job_settings(item, probe) if probe else None
                    out = (eff["output"] if eff else None) or item.get("output") or ""
                    folder = resolve_output_dir(out, blend)
                    fps = item.get("fps") or (eff["fps"] if eff else None) or self.config.get("ffmpeg_fps", 60)
                    ok = self._convert_one_folder(folder, fps, hint=os.path.basename(blend))
                    if ok:
                        self._mark_converted(folder)
                    return bool(ok)
                except Exception as e:
                    try:
                        self.log("Convert error: {}".format(e))
                    except Exception:
                        pass
                    return False

            try:
                with ThreadPoolExecutor(max_workers=2) as ex:
                    results = list(ex.map(_one, list(items or [])))
            except Exception:
                results = []
            try:
                if len(results) > 1:
                    self.log("Batch convert: {}/{} ok.".format(
                        sum(1 for r in results if r), len(results)))
            except Exception:
                pass
        finally:
            self.is_converting = False
            self.log("CONVERT DONE")

    def _convert_folders_thread(self, folders, fps):
        self.is_converting = True
        try:
            for folder in folders:
                if self._convert_one_folder(folder, fps or self.config.get("ffmpeg_fps", 60),
                                             hint=os.path.basename(folder)):
                    self._mark_converted(folder)
        finally:
            self.is_converting = False
            self.log("CONVERT DONE")

    def _convert_one_folder(self, folder, fps, hint=""):
        ff = self._ffmpeg_bin()
        if not ff:
            return False
        if not os.path.isdir(folder):
            self.log("Convert SKIP (no folder yet): {}".format(folder))
            return False
        seq = find_png_sequence(folder)
        if not seq:
            self.log("Convert SKIP (no PNGs): {}".format(folder))
            return False
        try:
            crf = int(self.config.get("ffmpeg_crf", 12))
        except Exception:
            crf = 12
        clean_prefix = seq["prefix"].rstrip("_- .")
        if clean_prefix:
            mp4_name = "{}.mp4".format(clean_prefix)
        else:
            mp4_name = "{}.mp4".format(os.path.basename(os.path.normpath(folder)))
        mp4_path = os.path.join(folder, mp4_name)
        pattern = seq["pattern_prefixed"] if seq["prefix"] else seq["pattern"]
        cmd = build_ffmpeg_command(ff, folder, pattern, seq["start"], fps, crf, mp4_path)
        self.log("FFmpeg [{}]: {} PNGs from {} @ {}fps -> {}".format(hint or folder, seq["count"], pattern, fps, mp4_name))
        try:
            proc = subprocess.Popen(cmd, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="ignore",
                                    **_silent_popen_kwargs())
            try:
                self.convert_procs.add(proc)
            except Exception:
                pass
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                if "frame=" in line or "time=" in line:
                    self.log("  ffmpeg: " + line[-160:])
                elif "Error" in line or "Invalid" in line:
                    self.log("  ffmpeg: " + line)
            proc.wait()
            try:
                self.convert_procs.discard(proc)
            except Exception:
                pass
            if proc.returncode == 0 and os.path.exists(mp4_path):
                self.log("MP4 ready: {} ({:.1f} MB)".format(mp4_path, os.path.getsize(mp4_path) / 1048576))
                log_history({"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "kind": "ffmpeg",
                             "file": hint or folder, "status": "Done",
                             "detail": "{} -> {}".format(pattern, mp4_name), "folder": folder})
                return True
            self.log("FFmpeg failed (code {})".format(proc.returncode))
            return False
        except Exception as e:
            try:
                self.convert_procs.discard(proc)
            except Exception:
                pass
            self.log("FFmpeg error: {}".format(e))
            return False


if __name__ == "__main__":
    app = BlenderRenderApp()
    app.mainloop()

