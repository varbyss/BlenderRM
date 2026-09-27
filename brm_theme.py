"""BRM design system: palette, fonts, drawn icons.

Palette + type scale come straight from the design reference (index.css).
Fonts (Barlow / Barlow Condensed / Source Code Pro, all OFL) live in
assets/fonts and are registered privately via AddFontResourceEx.
All icons are drawn with PIL (crisp at any size, exact brand colors).
"""

import os

# ---- palette (designref index.css) ----
BG      = "#0b0b0b"
S1      = "#111111"
S2      = "#181818"
S3      = "#202020"
LINE    = "#2a2a2a"
LINE2   = "#353535"
TEXT    = "#d8d8d8"
DIM     = "#888888"
FAINT   = "#444444"
ORANGE  = "#4d80f0"
ORANGE2 = "#6b96f7"
ORANGE_BG = "#4d80f0"
GREEN   = "#3ecf8e"
GREEN_BG = "#3ecf8e"
RED     = "#f05151"
RED_BG  = "#f05151"
AMBER   = "#f0b429"

# ---- type scale ----
F_UI_TITLE = ("Barlow Condensed", 15, "bold")
F_LABEL    = ("Barlow Condensed", 11, "bold")   # micro-headers, always UPPER
F_LABEL_SM = ("Barlow Condensed", 9, "bold")
F_BODY     = ("Barlow", 12)
F_SMALL    = ("Barlow", 11)
F_MONO     = ("Source Code Pro", 10)
F_MONO_SM  = ("Source Code Pro", 9)

APP_VERSION = "3.4.0"

_font_ok = None


def _base_dir():
    try:
        return os.path.abspath(os.path.dirname(__file__))
    except NameError:
        return os.getcwd()


def fonts_ready():
    global _font_ok
    if _font_ok is not None:
        return _font_ok
    _font_ok = False
    try:
        d = os.path.join(_base_dir(), "assets", "fonts")
        files = ["Barlow-Regular.ttf", "Barlow-Medium.ttf",
                 "BarlowCondensed-SemiBold.ttf", "BarlowCondensed-Bold.ttf",
                 "SourceCodePro-Regular.ttf", "SourceCodePro-Medium.ttf"]
        have = sum(1 for f in files if os.path.exists(os.path.join(d, f)))
        if have == 0:
            return False
        if os.name == "nt":
            try:
                import ctypes
                n = 0
                for f in files:
                    p = os.path.join(d, f)
                    if os.path.exists(p):
                        try:
                            n += ctypes.windll.gdi32.AddFontResourceExW(p, 0x10, 0)
                        except Exception:
                            pass
                _font_ok = n > 0
            except Exception:
                _font_ok = False
        else:
            _font_ok = True
    except Exception:
        _font_ok = False
    return _font_ok


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


_img_cache = {}


def _canvas(size):
    try:
        from PIL import Image
        return Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
    except Exception:
        return None


def _finish(img, size, key):
    try:
        from PIL import Image
        img = img.resize((size, size), Image.LANCZOS)
        _img_cache[key] = img
        return img
    except Exception:
        return None


def status_icon(kind, size=15, frame=0):
    """PIL image: done / rendering / crashed / paused / queued (+dim variant frame=1)."""
    key = ("st", kind, size, frame)
    if key in _img_cache:
        return _img_cache[key]
    try:
        from PIL import ImageDraw
        S = size * 4
        img = _canvas(size)
        if img is None:
            return None
        dr = ImageDraw.Draw(img)
        c = S // 2
        r = S // 2 - 6
        dim = (frame == 1)
        if kind == "done":
            col = _hex(GREEN) + ((110,) if dim else (255,))
            dr.ellipse([c - r, c - r, c + r, c + r], outline=col, width=5)
            dr.line([(c - r * 0.45, c + r * 0.02), (c - r * 0.08, c + r * 0.38),
                     (c + r * 0.5, c - r * 0.35)], fill=col, width=6, joint="curve")
        elif kind == "rendering":
            base = _hex(ORANGE) + (70,)
            dr.ellipse([c - r, c - r, c + r, c + r], outline=base, width=6)
            a0 = (frame * 45) % 360
            dr.arc([c - r, c - r, c + r, c + r], start=a0, end=a0 + 110,
                   fill=_hex(ORANGE) + (255,), width=7)
        elif kind == "crashed":
            col = _hex(RED) + ((110,) if dim else (255,))
            dr.ellipse([c - r, c - r, c + r, c + r], outline=col, width=5)
            o = r * 0.42
            dr.line([(c - o, c - o), (c + o, c + o)], fill=col, width=6)
            dr.line([(c + o, c - o), (c - o, c + o)], fill=col, width=6)
        elif kind == "paused":
            col = _hex(AMBER) + ((255,) if not dim else (255,))
            dr.ellipse([c - r, c - r, c + r, c + r], outline=col, width=5)
            bw, bh = 9, r
            dr.rectangle([c - bw - 3, c - bh // 2, c - 3, c + bh // 2], fill=col)
            dr.rectangle([c + 3, c - bh // 2, c + bw + 3, c + bh // 2], fill=col)
        else:  # queued
            col = _hex(FAINT) + (255,)
            dr.ellipse([c - r, c - r, c + r, c + r], outline=col, width=5)
            dr.ellipse([c - 7, c - 7, c + 7, c + 7], fill=col)
        return _finish(img, size, key)
    except Exception:
        return None


def glyph(name, size=14, color="#d8d8d8"):
    """Small geometric UI glyphs: pause/stop/play/plus/x/menu/trash/folder/external/refresh/check."""
    key = ("gl", name, size, color)
    if key in _img_cache:
        return _img_cache[key]
    try:
        from PIL import ImageDraw
        S = size * 4
        img = _canvas(size)
        if img is None:
            return None
        dr = ImageDraw.Draw(img)
        col = _hex(color) + (255,)
        m = S * 0.28
        if name == "pause":
            bw = S * 0.16
            dr.rectangle([m, m, m + bw, S - m], fill=col)
            dr.rectangle([S - m - bw, m, S - m, S - m], fill=col)
        elif name == "stop":
            dr.rectangle([m, m, S - m, S - m], fill=col)
        elif name == "play":
            dr.polygon([(m + 4, m), (S - m, S / 2), (m + 4, S - m)], fill=col)
        elif name == "plus":
            w = S * 0.11
            dr.rectangle([S / 2 - w, m, S / 2 + w, S - m], fill=col)
            dr.rectangle([m, S / 2 - w, S - m, S / 2 + w], fill=col)
        elif name == "x":
            w = S * 0.11
            o = S * 0.30
            dr.line([(o, o), (S - o, S - o)], fill=col, width=int(w * 2))
            dr.line([(S - o, o), (o, S - o)], fill=col, width=int(w * 2))
        elif name == "menu":
            w = S * 0.10
            for y in (S * 0.30, S * 0.50, S * 0.70):
                dr.rectangle([m, y - w, S - m, y + w], fill=col)
        elif name == "trash":
            w = S * 0.10
            dr.rectangle([m + 4, S * 0.26, S - m - 4, S - m], outline=col, width=int(w * 2))
            dr.rectangle([m - 2, S * 0.18, S - m + 2, S * 0.24], fill=col)
            dr.rectangle([S / 2 - w, S * 0.08, S / 2 + w, S * 0.20], fill=col)
            dr.line([(S / 2 - 8, S * 0.36), (S / 2 - 8, S - m - 8)], fill=col, width=int(w * 2))
            dr.line([(S / 2 + 8, S * 0.36), (S / 2 + 8, S - m - 8)], fill=col, width=int(w * 2))
        elif name == "folder":
            dr.rectangle([m, S * 0.32, S - m, S - m], outline=col, width=int(S * 0.09))
            dr.polygon([(m, S * 0.32), (m, S * 0.22), (S * 0.45, S * 0.22),
                        (S * 0.52, S * 0.32)], fill=col)
        elif name == "external":
            w = int(S * 0.11)
            dr.rectangle([m, m, S - m - 6, S - m - 6], outline=col, width=w)
            dr.line([(S / 2, S / 2), (S - m + 2, m - 2)], fill=col, width=w)
            dr.line([(S - m - 12, m - 2), (S - m + 2, m - 2)], fill=col, width=w)
            dr.line([(S - m + 2, m - 2), (S - m + 2, m + 12)], fill=col, width=w)
        elif name == "refresh":
            dr.arc([m, m, S - m, S - m], start=40, end=320, fill=col, width=int(S * 0.11))
            dr.polygon([(S - m - 2, m - 6), (S - m + 14, m + 2), (S - m - 8, m + 12)], fill=col)
        elif name == "check":
            w = int(S * 0.12)
            dr.line([(m + 2, S / 2), (S / 2 - 2, S - m - 2), (S - m, m + 4)], fill=col, width=w, joint="curve")
        elif name == "chev":
            w = int(S * 0.12)
            dr.line([(S * 0.36, S * 0.24), (S * 0.62, S / 2), (S * 0.36, S * 0.76)], fill=col, width=w, joint="curve")
        elif name == "settings":
            import math
            cx = cy = S / 2
            r_out, r_in, teeth, tw = S * 0.34, S * 0.20, 8, S * 0.075
            for k in range(teeth):
                a = 2 * math.pi * k / teeth
                dx, dy = math.cos(a), math.sin(a)
                px, py = -dy, dx
                r1, r2 = r_out - S * 0.02, r_out + S * 0.06
                dr.polygon([(cx + dx * r1 + px * tw, cy + dy * r1 + py * tw),
                            (cx + dx * r2 + px * tw, cy + dy * r2 + py * tw),
                            (cx + dx * r2 - px * tw, cy + dy * r2 - py * tw),
                            (cx + dx * r1 - px * tw, cy + dy * r1 - py * tw)], fill=col)
            dr.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], outline=col, width=int(S * 0.09))
            dr.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], fill=(0, 0, 0, 0))
        else:
            return None
        return _finish(img, size, key)
    except Exception:
        return None
