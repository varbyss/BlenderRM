"""Icon system: Material Icons Outlined (Apache 2.0, bundled in assets/fonts).

Loads the font privately via AddFontResourceEx (no install, no reboot) and
maps icon names to PUA chars using the bundled .codepoints file.
Everything degrades to caller-provided ASCII fallbacks when unavailable.
"""

import os

FAMILY = "Material Icons Outlined"
_font_ok = None
_codepoints = {}


def _base_dir():
    try:
        return os.path.abspath(os.path.dirname(__file__))
    except NameError:
        return os.getcwd()


def _load():
    global _font_ok, _codepoints
    if _font_ok is not None:
        return _font_ok
    _font_ok = False
    try:
        d = os.path.join(_base_dir(), "assets", "fonts")
        otf = os.path.join(d, "MaterialIconsOutlined-Regular.otf")
        cps = os.path.join(d, "MaterialIconsOutlined-Regular.codepoints")
        if os.path.exists(cps):
            with open(cps, encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            _codepoints[parts[0]] = chr(int(parts[1], 16))
                        except ValueError:
                            pass
        if os.path.exists(otf) and os.name == "nt":
            try:
                import ctypes
                # 0x10 = private (process session), 0x20 = not enumerable
                n = ctypes.windll.gdi32.AddFontResourceExW(otf, 0x10, 0)
                _font_ok = n > 0
            except Exception:
                _font_ok = False
        elif os.path.exists(otf):
            _font_ok = True  # non-Windows: assume fontconfig finds bundled file
    except Exception:
        _font_ok = False
    return _font_ok


def available():
    return _load()


def char(name, fallback=""):
    """Return the icon char, or fallback when the font is unavailable."""
    if _load() and name in _codepoints:
        return _codepoints[name]
    return fallback


def font(size=16):
    """tk font tuple for icons."""
    return (FAMILY, size)


_cache_img = {}


def _font_path():
    try:
        d = os.path.join(_base_dir(), "assets", "fonts")
        p = os.path.join(d, "MaterialIconsOutlined-Regular.otf")
        return p if os.path.exists(p) else None
    except Exception:
        return None


def image(name, size=18, color=(255, 255, 255, 255)):
    """Prerendered PIL image of an icon (for CTk image+text buttons). Cached."""
    key = (name, size, color)
    if key in _cache_img:
        return _cache_img[key]
    try:
        from PIL import Image, ImageDraw, ImageFont
        ch = char(name)
        if not ch:
            return None
        fp = _font_path()
        if not fp:
            return None
        fnt = ImageFont.truetype(fp, size * 4)
        img = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        bb = dr.textbbox((0, 0), ch, font=fnt)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        dr.text(((size * 4 - w) / 2 - bb[0], (size * 4 - h) / 2 - bb[1]), ch,
                font=fnt, fill=color)
        img = img.resize((size, size), Image.LANCZOS)
        _cache_img[key] = img
        return img
    except Exception:
        return None
