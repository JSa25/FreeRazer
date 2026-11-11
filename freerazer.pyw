"""FreeRazer: save and apply button profiles for Razer mice. Unofficial; not affiliated with Razer.

Start with:  pyw -3.13 freerazer.pyw   (or the built "FreeRazer.exe")
Profiles live in profiles.json in the FreeRazer folder under %APPDATA%; the mouse keeps whatever was applied last.
"""
import ctypes
import json
import math
import os
import queue
import re
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

import razer_switch as rs

HERE = os.path.dirname(os.path.abspath(__file__))  # as an exe this is the temp unpack folder
CFG = rs.profiles_path()
LOG = os.path.join(os.path.dirname(CFG), 'error.log')  # the exe has no console, so problems are written here


LOG_MAX = 512_000  # bytes; past this the oldest half is dropped


def check_cfg(cfg):
    """ValueError unless the settings file has the shape the app relies on (it can be edited by hand). Bad data
    is reported, never silently dropped: the next save would lose it for good."""
    def need(ok, what):
        if not ok:
            raise ValueError(f'{what} in the settings file is not valid')
    str_dict = lambda d, vals: isinstance(d, dict) and all(isinstance(k, str) and vals(v) for k, v in d.items())
    need(isinstance(cfg, dict), 'the file')
    need(str_dict(cfg.get('profiles', {}), lambda p: str_dict(p, lambda a: isinstance(a, str))), '"profiles"')
    need(str_dict(cfg.get('links', {}), lambda p: isinstance(p, str)), '"links"')
    need(str_dict(cfg.get('confirmed', {}), lambda ids: isinstance(ids, list) and all(
        isinstance(b, int) and not isinstance(b, bool) for b in ids)), '"confirmed"')
    need(str_dict(cfg.get('keep', {}), lambda d: isinstance(d, dict)), '"keep"')
    need(str_dict(cfg.get('hypershift', {}), lambda v: isinstance(v, bool)), '"hypershift"')
    need(isinstance(cfg.get('active', 'default'), str), '"active"')
    need(cfg.get('mouse') is None or isinstance(cfg['mouse'], int), '"mouse"')


def log_error(where, exc=None):
    """Append an exception (the one being handled, or exc=(type, value, traceback)) to error.log, with the
    app version, so a silent failure can still be found. The log keeps only its newest ~256 KB."""
    import time
    import traceback
    text = ''.join(traceback.format_exception(*exc)) if exc else traceback.format_exc()
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > LOG_MAX:
            with open(LOG, 'rb') as f:
                f.seek(-LOG_MAX // 2, os.SEEK_END)
                tail = f.read()
            with open(LOG, 'wb') as f:
                f.write(b'(older entries removed)\n' + tail[tail.find(b'\n') + 1:])
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} FreeRazer {APP_VERSION} {where}\n{text}\n')
    except OSError:
        pass
BG, SIDE, PANEL, LINE, LEADER = '#1b1c1f', '#151619', '#26282d', '#7c818a', '#474b53'
FG, MUTED, DIM, ACCENT, ACCENT_DIM, SEL_FILL = '#e8e8e8', '#9aa0aa', '#5c6169', '#44d62c', '#2f6b27', '#1d2b1a'
FONT = ('Segoe UI', 10)
WARN = '#e5a83b'
MOUSE_CHOICES = [a for a in rs.ACTIONS if a.startswith('mouse:')]
DPI_CHOICES = [a for a in rs.ACTIONS if a.startswith('dpi:')]
REC_IDLE = 'Click, then press a key or combo'
PAGE_PAD = 24  # content margin around every page (Windows app guidance)
LIGHT_NAMES = {'off': 'Off', 'static': 'Static', 'breathing': 'Breathing', 'spectrum': 'Rainbow'}
LIGHT_PRESETS = ('#44d62c', '#ff0000', '#ff7a00', '#ffd400', '#00e5ff', '#0050ff', '#9b30ff', '#ff2d95', '#ffffff')

# Tk key names -> razer_switch key names (letters, digits and F-keys map by lowercasing)
TK_KEYS = {'Return': 'enter', 'Escape': 'esc', 'BackSpace': 'backspace', 'Tab': 'tab', 'space': 'space',
           'minus': '-', 'equal': '=', 'bracketleft': '[', 'bracketright': ']', 'backslash': '\\',
           'semicolon': ';', 'apostrophe': "'", 'quoteright': "'", 'grave': '`', 'quoteleft': '`',
           'comma': ',', 'period': '.', 'slash': '/', 'Caps_Lock': 'capslock', 'Insert': 'insert',
           'Home': 'home', 'Prior': 'pageup', 'Next': 'pagedown', 'Delete': 'delete', 'End': 'end',
           'Up': 'up', 'Down': 'down', 'Left': 'left', 'Right': 'right', 'Control_L': 'ctrl',
           'Control_R': 'rctrl', 'Shift_L': 'shift', 'Shift_R': 'rshift', 'Alt_L': 'alt', 'Alt_R': 'ralt'}
# held while recording, these become a combo's modifiers (Ctrl + 5); tapped alone they are the key itself
MOD_KEYSYMS = {'Control_L': 'ctrl', 'Control_R': 'ctrl', 'Shift_L': 'shift', 'Shift_R': 'shift',
               'Alt_L': 'alt', 'Alt_R': 'alt'}
# Windows key codes -> key names; used instead of the typed character, which Shift changes (5 -> %)
VK_KEYS = {0x08: 'backspace', 0x09: 'tab', 0x0D: 'enter', 0x14: 'capslock', 0x1B: 'esc', 0x20: 'space',
           0x21: 'pageup', 0x22: 'pagedown', 0x23: 'end', 0x24: 'home', 0x25: 'left', 0x26: 'up',
           0x27: 'right', 0x28: 'down', 0x2D: 'insert', 0x2E: 'delete', 0xBA: ';', 0xBB: '=', 0xBC: ',',
           0xBD: '-', 0xBE: '.', 0xBF: '/', 0xC0: '`', 0xDB: '[', 0xDC: '\\', 0xDD: ']', 0xDE: "'",
           **{0x30 + i: str(i) for i in range(10)}, **{0x41 + i: chr(97 + i) for i in range(26)},
           **{0x70 + i: f'f{i + 1}' for i in range(24)}}

# button: (label side, label y, line end x relative to centre, line end y) on a 720x340 drawing
W, H, CX = 720, 340, 360
EXTRA_ROW = 32  # spacing of the More buttons rows under the picture
# button: (side, label row y, target x from centre, target y). Rows are evenly spaced and ordered like the
# targets, so each leader (straight out, then one bend into its button) never crosses another.
# Side buttons and both clicks sit level with their row, so those leaders are dead straight.
LABELS = {1: ('l', 45, -35, 45), 3: ('l', 95, -8, 65), 5: ('l', 145, -78, 145), 4: ('l', 195, -80, 195),
          2: ('r', 45, 35, 45), 9: ('r', 95, 4, 42), 10: ('r', 145, 3, 87), 0x60: ('r', 195, 9, 230)}
REACH = 125  # label dots sit this far from the centre line


def leader(b):
    """Points of button b's leader line: from its label, to its dot, to the bend outside the shell, into the button."""
    side, y, tx, ty = LABELS[b]
    s = -1 if side == 'l' else 1
    return [(CX + s * (REACH + 45), y), (CX + s * REACH, y), (CX + s * (REACH - 35), y), (CX + tx, ty)]


APP_VERSION = '1.0.3'  # build.ps1 reads this; bump it for every release
UPDATE_REPO = 'JSa25/freerazer'  # GitHub repo whose Releases carry the installer
SETUP_ASSET = 'FreeRazerSetup.exe'  # release asset, plus SETUP_ASSET + '.sha256'
DB_URL = f'https://raw.githubusercontent.com/{UPDATE_REPO}/master/{rs.DB_FILE}'  # the mouse database, kept in the repo
ISSUES_URL = f'https://github.com/{UPDATE_REPO}/issues/new'  # where mouse reports go
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: helper programs run without flashing a console


def _curl(*args, timeout=60):
    """Windows' own curl does the HTTPS, so the exe doesn't have to bundle OpenSSL."""
    r = subprocess.run(['curl.exe', '-fsSL', '--max-time', str(timeout), *args], capture_output=True,
                       creationflags=NO_WINDOW)
    if r.returncode == 22:
        raise OSError('no release found on GitHub')
    if r.returncode:
        raise OSError(f'could not reach GitHub (curl error {r.returncode})')
    return r.stdout


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r'\d+', v)[:3])


def latest_release():
    """(tag, {asset name: download url}, release notes) of the newest published release."""
    data = json.loads(_curl('-H', 'Accept: application/vnd.github+json',
                            f'https://api.github.com/repos/{UPDATE_REPO}/releases/latest', timeout=20))
    if not isinstance(data, dict) or not isinstance(data.get('tag_name'), str) or not isinstance(data.get('assets', []), list):
        raise ValueError('GitHub answered with something that is not a release')
    assets = {a.get('name'): a.get('browser_download_url') for a in data.get('assets', []) if isinstance(a, dict)}
    return data['tag_name'], assets, data.get('body') if isinstance(data.get('body'), str) else ''


def file_sha256(path):
    out = subprocess.run(['certutil', '-hashfile', path, 'SHA256'], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout.splitlines()
    return out[1].replace(' ', '').strip().lower() if len(out) > 1 else ''


def download_update(tag, assets):
    """Download the new installer and check it against the release's published SHA-256; returns its path.
    The links are built here from the release tag, never taken from the API answer, so a tampered answer
    can't point the download (and its checksum) somewhere else."""
    if not re.fullmatch(r'v\d+(\.\d+){1,3}', tag) or SETUP_ASSET not in assets or SETUP_ASSET + '.sha256' not in assets:
        raise OSError('the release has no installer and checksum from this project')
    base = f'https://github.com/{UPDATE_REPO}/releases/download/{tag}/'
    folder = os.path.join(os.environ.get('TEMP') or os.path.dirname(CFG), 'FreeRazerUpdate')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, SETUP_ASSET)
    _curl('-o', path, base + SETUP_ASSET, timeout=300)
    expected = (_curl(base + SETUP_ASSET + '.sha256', timeout=30).decode('ascii', 'replace').split() or [''])[0].lower()
    if not re.fullmatch(r'[0-9a-f]{64}', expected) or file_sha256(path) != expected:
        os.remove(path)
        raise OSError('the download did not match its published checksum, so it was thrown away')
    return path


def fullscreen_foreground():
    """True while the window in front covers its whole screen (a game, a video), so automatic pop-ups wait."""
    u32 = ctypes.windll.user32
    from ctypes import wintypes as w
    hwnd = u32.GetForegroundWindow()
    cls = ctypes.create_unicode_buffer(64)
    u32.GetClassNameW(hwnd, cls, 64)
    if not hwnd or cls.value in ('Progman', 'WorkerW', 'Shell_TrayWnd'):  # the desktop and taskbar don't count
        return False

    class MonitorInfo(ctypes.Structure):
        _fields_ = [('cbSize', w.DWORD), ('rcMonitor', w.RECT), ('rcWork', w.RECT), ('dwFlags', w.DWORD)]
    win, mi = w.RECT(), MonitorInfo()
    mi.cbSize = ctypes.sizeof(MonitorInfo)
    if not u32.GetWindowRect(hwnd, ctypes.byref(win)) or \
            not u32.GetMonitorInfoW(u32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi)):  # 2: nearest monitor
        return False
    m = mi.rcMonitor
    return win.left <= m.left and win.top <= m.top and win.right >= m.right and win.bottom >= m.bottom


# shortcut: matched by name only (Synapse 2/3/4 run processes with these in their names); not tested against
# a real Synapse install here, so a renamed Synapse process would be missed. Upgrade if a report shows one.
SYNAPSE_HINTS = ('synapse', 'razerappengine')


class _ProcessEntry(ctypes.Structure):
    from ctypes import wintypes as _w
    _fields_ = [('dwSize', _w.DWORD), ('cntUsage', _w.DWORD), ('th32ProcessID', _w.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', _w.DWORD), ('cntThreads', _w.DWORD),
                ('th32ParentProcessID', _w.DWORD), ('pcPriClassBase', ctypes.c_long), ('dwFlags', _w.DWORD),
                ('szExeFile', ctypes.c_wchar * 260)]


def synapse_running():
    """Names of running Razer Synapse processes. Both apps writing the mouse would undo each other.
    Reads Windows' process list directly (a few ms) instead of starting tasklist every 30 s."""
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = (ctypes.c_void_p, ctypes.POINTER(_ProcessEntry))
    k32.CloseHandle.argtypes = (ctypes.c_void_p,)
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap in (None, ctypes.c_void_p(-1).value):
        raise OSError('could not list processes')
    names, entry = set(), _ProcessEntry()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            names.add(entry.szExeFile.lower())
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return sorted(n for n in names if any(h in n for h in SYNAPSE_HINTS))


def slider_to_dpi(v, rng=rs.DPI_RANGE):
    """The DPI slider runs 0..1000 on a log scale, so 400-3200 (where most people sit) isn't squeezed into a sliver."""
    lo, hi = rng
    return max(lo, min(hi, round(lo * (hi / lo) ** (v / 1000) / 50) * 50))


def rounded_image(size, r, fill, outline=None, k=1.0):
    """Anti-aliased rounded rectangle (or circle when r is half the size) with transparent corners."""
    from PIL import Image, ImageDraw, ImageTk
    w, h = (round(v * k) for v in size)
    S = 4
    img = Image.new('RGBA', (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=round(r * k * S), fill=fill,
                                          outline=outline, width=S if outline else 0)
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


def round_corners(win):
    """Windows 11 rounds the window's corners and gives it a thin border; older Windows leaves it square."""
    try:
        hwnd = int(win.wm_frame(), 16)
        r, g, b = (int(LINE[i:i + 2], 16) for i in (1, 3, 5))
        for attr, value in ((33, 2), (34, b << 16 | g << 8 | r)):  # DWMWA_WINDOW_CORNER_PREFERENCE = round, border colour
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ctypes.c_int(value)), 4)
    except (OSError, ValueError, AttributeError):
        pass


def chevron_image(up, color, k=1.0):
    """A small anti-aliased arrow for combobox and spinbox buttons, on a transparent background."""
    from PIL import Image, ImageDraw, ImageTk
    w, h, S = round(10 * k), round(6 * k), 4
    img = Image.new('RGBA', (w * S, h * S), (0, 0, 0, 0))
    pts = [(S, h * S - S * 1.5), (w * S / 2, S * 1.5), (w * S - S, h * S - S * 1.5)]
    if not up:
        pts = [(x, h * S - y) for x, y in pts]
    ImageDraw.Draw(img).line(pts, fill=color, width=round(1.5 * k * S), joint='curve')
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


class Slider(tk.Canvas):
    """A rounded track with a round knob (tk.Scale can only draw square ones). `command` gets the value
    while dragging; `release` runs once the knob is let go, which is when the mouse gets the new value."""

    def __init__(self, parent, from_, to, length, k, command=None, release=None, bg=BG):
        self.h, self.r = round(20 * k), round(8 * k)
        super().__init__(parent, width=length, height=self.h, bg=bg, highlightthickness=0, bd=0, takefocus=1,
                         cursor='hand2')
        self.lo, self.hi, self.val, self.length = from_, to, from_, length
        self.command, self.release, self.on = command, release, True
        self.knobs = {c: rounded_image((16, 16), 8, c, k=k) for c in (ACCENT, DIM)}
        y, width = self.h / 2, max(2, round(4 * k))
        self.create_line(self.r, y, length - self.r, y, width=width, capstyle='round', fill=PANEL)
        self.fill = self.create_line(self.r, y, self.r, y, width=width, capstyle='round', fill=ACCENT)
        self.knob = self.create_image(self.r, y, image=self.knobs[ACCENT])
        self.bind('<Button-1>', lambda e: (self.focus_set(), self._drag(e)))
        self.bind('<B1-Motion>', self._drag)
        self.bind('<ButtonRelease-1>', lambda e: self._let_go())
        for key, step in (('Left', -1), ('Down', -1), ('Right', 1), ('Up', 1)):
            self.bind(f'<{key}>', lambda e, step=step: self._move(self.val + step))
            self.bind(f'<KeyRelease-{key}>', lambda e: self._let_go())

    def set(self, value):
        self.val = min(max(round(value), self.lo), self.hi)
        span = (self.val - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0
        x, y = self.r + span * (self.length - 2 * self.r), self.h / 2
        self.coords(self.fill, self.r, y, x, y)
        self.coords(self.knob, x, y)

    def get(self):
        return self.val

    def set_range(self, lo, hi):
        self.lo, self.hi = lo, hi
        self.set(self.val)

    def enable(self, on):
        self.on = on
        self.itemconfigure(self.fill, fill=ACCENT if on else DIM)
        self.itemconfigure(self.knob, image=self.knobs[ACCENT if on else DIM])
        self.configure(cursor='hand2' if on else '')

    def _drag(self, e):
        self._move(self.lo + (e.x - self.r) / max(1, self.length - 2 * self.r) * (self.hi - self.lo))

    def _move(self, value):
        if self.on:
            self.set(value)
            if self.command:
                self.command(self.val)

    def _let_go(self):
        if self.on and self.release:
            self.release()


def hex_color(rgb):
    return '#%02x%02x%02x' % tuple(rgb)


def hue_rgb(hue):
    import colorsys
    return tuple(round(v * 255) for v in colorsys.hsv_to_rgb(hue / 360, 1, 1))


class HueSlider(Slider):
    """Slider over every hue (0-359) on a rainbow track; the knob shows the light's colour."""

    def __init__(self, parent, length, k, command=None, release=None, bg=BG):
        super().__init__(parent, 0, 359, length, k, command, release, bg)
        from PIL import Image, ImageDraw, ImageTk
        self.k = k
        self.delete('all')
        r, h, S = self.r, round(8 * k), 4
        w = length - 2 * r + h  # rounded ends reach past the knob's travel by half the track height
        grad = Image.new('RGB', (w * S, h * S))
        d = ImageDraw.Draw(grad)
        for px in range(w * S):  # the hue under each pixel matches the value the knob gives there
            d.line((px, 0, px, h * S), fill=hue_rgb(min(max((px / S - h / 2) / (length - 2 * r), 0), 1) * 359))
        mask = Image.new('L', (w * S, h * S), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=h * S // 2, fill=255)
        grad.putalpha(mask)
        self.track_img = ImageTk.PhotoImage(grad.resize((w, h), Image.LANCZOS))
        self.create_image(length / 2, self.h / 2, image=self.track_img)
        self.fill = self.create_line(0, 0, 0, 0, state='hidden')  # Slider.set moves it; nothing to show here
        self.ring_img = rounded_image((18, 18), 9, '#ffffff', k=k)
        self.ring = self.create_image(r, self.h / 2, image=self.ring_img)
        self.knob = self.create_image(r, self.h / 2)
        self.show((0, 255, 0))

    def set(self, value):
        super().set(value)
        self.coords(self.ring, *self.coords(self.knob))

    def show(self, rgb):
        self.knob_img = rounded_image((13, 13), 6.5, hex_color(rgb), k=self.k)
        self.itemconfigure(self.knob, image=self.knob_img)

    def enable(self, on):
        self.on = on
        self.configure(cursor='hand2' if on else '')


def swatch_image(rgb, w, h):
    """The light's colour as a rounded chip with a small down arrow (it opens the picker)."""
    from PIL import Image, ImageDraw, ImageTk
    S = 4
    img = Image.new('RGBA', (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=h * S // 2, fill=PANEL)
    d.rounded_rectangle((3 * S, 3 * S, (w - 22) * S, (h - 3) * S), radius=(h - 6) * S // 2, fill=hex_color(rgb))
    cx, cy = (w - 11) * S, h * S // 2
    d.line([(cx - 4 * S, cy - 2 * S), (cx, cy + 2 * S), (cx + 4 * S, cy - 2 * S)], fill=MUTED, width=round(1.5 * S),
           joint='curve')
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


def ring_image(k):
    """Hollow white ring with a dark edge, so the picker's knob shows on any colour."""
    from PIL import Image, ImageDraw, ImageTk
    n, S = round(16 * k), 4
    img = Image.new('RGBA', (n * S, n * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, n * S - 1, n * S - 1), outline=(0, 0, 0, 140), width=round(4 * k * S))
    d.ellipse((S, S, (n - 1) * S - 1, (n - 1) * S - 1), outline='#ffffff', width=round(2 * k * S))
    return ImageTk.PhotoImage(img.resize((n, n), Image.LANCZOS))


class ColorDots(tk.Canvas):
    """A row of round colour presets; the picked one gets a ring. `command` gets the (r, g, b) clicked."""

    def __init__(self, parent, colors, k, command, bg=BG):
        self.step, size = round(28 * k), round(24 * k)
        super().__init__(parent, width=self.step * len(colors), height=size, bg=bg, highlightthickness=0, bd=0,
                         cursor='hand2')
        self.colors = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in colors]
        self.imgs = [rounded_image((16, 16), 8, c, k=k) for c in colors]
        self.ring_img = rounded_image((22, 22), 11, BG, outline=FG, k=k)
        self.ring = self.create_image(-100, size / 2, image=self.ring_img)
        for i, img in enumerate(self.imgs):
            x = self.step * i + self.step / 2
            self.create_image(x, size / 2, image=img, tags=(f'c{i}',))
            self.tag_bind(f'c{i}', '<Button-1>', lambda e, i=i: command(self.colors[i]))

    def show(self, rgb):
        i = self.colors.index(tuple(rgb)) if tuple(rgb) in self.colors else None
        self.coords(self.ring, -100 if i is None else self.step * i + self.step / 2, self.winfo_reqheight() / 2)


def dpi_to_slider(dpi, rng=rs.DPI_RANGE):
    lo, hi = rng
    return 1000 * math.log(max(lo, dpi) / lo) / math.log(hi / lo)


def catmull(pts, start=None, end=None, n=8):
    """Smooth curve through every point (Catmull-Rom). start/end are phantom points that set the end tangents."""
    p = [start or pts[0], *pts, end or pts[-1]]
    out = [pts[0]]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for s in range(1, n + 1):
            t = s / n
            out.append(tuple(0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (3 * b - a - 3 * c + d) * t ** 3)
                             for a, b, c, d in zip(p0, p1, p2, p3)))
    return out


RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'  # per-user startup list (Task Manager > Startup)
OLD_RUN_NAMES = ('Viper Profiles', 'Mouse Profiles')  # this app's earlier names


def startup_command():
    """The command Windows runs at sign-in for this app, or None if it isn't set to start."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, 'FreeRazer')[0]
    except OSError:
        return None


def set_startup(on):
    import winreg
    if getattr(sys, 'frozen', False):
        cmd = f'"{sys.executable}" --tray'
    else:  # running as a script: use pythonw so no console window opens at sign-in
        pyw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
        cmd = f'"{pyw}" "{os.path.abspath(__file__)}" --tray'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, 'FreeRazer', 0, winreg.REG_SZ, cmd)
        elif startup_command() is not None:
            winreg.DeleteValue(k, 'FreeRazer')


def migrate_startup():
    """Move a startup entry left under an earlier app name over to this one."""
    import winreg
    found = False
    for name in OLD_RUN_NAMES:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_ALL_ACCESS) as k:
                winreg.QueryValueEx(k, name)
                winreg.DeleteValue(k, name)
                found = True
        except OSError:
            pass
    if found:
        set_startup(True)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('FreeRazer')
        self.configure(bg=BG)
        try:
            with open(CFG, encoding='utf-8-sig') as f:  # -sig: also reads files an editor saved with a BOM
                self.cfg = json.load(f)
            check_cfg(self.cfg)
        except (OSError, ValueError) as e:
            # never start with blank settings: the next save would overwrite the user's profiles
            log_error('settings file could not be read')
            self.withdraw()
            messagebox.showerror('FreeRazer', f'FreeRazer could not read its settings file:\n{CFG}\n\n{e}\n\n'
                                 'Nothing was changed. Fix or remove that file, then start FreeRazer again.')
            raise SystemExit(1)
        self.cfg['default'] = {}  # the default profile is always factory and can't be edited
        self.cfg.pop('picture', None)  # left over from the removed own-picture option
        self.cfg.setdefault('profiles', {})
        self.cfg.setdefault('links', {})  # game exe name -> profile
        try:
            self.db = rs.load_db()  # the mouse database: shipped one or a newer downloaded one
        except Exception:  # never stop the app over it; mice without data are still read
            log_error('mouse database could not be loaded')
            self.db = None
        self.mouse = rs.Mouse()
        self.mouse.pid = self.cfg.get('mouse')  # picked in the header when several mice are plugged in
        # buttons that read back as their factory action, per model; see Mouse.confirm_buttons
        self.mouse.confirmed = {n: set(ids) for n, ids in self.cfg.get('confirmed', {}).items()}
        self.mouse.hs = dict(self.cfg.get('hypershift', {}))  # which mice turned out to have a HyperShift layer
        self.model = rs.detect(self.mouse.pid) or rs.DEVICES[0]  # V4 Pro layout until a mouse is found
        self.buttons, self.editable = self.model['buttons'], self.editable_for(self.model)
        migrate_startup()
        self.current, self.sel, self.edit, self.recording = 'default', 5, {}, False
        self.layer = 0  # 0 = standard buttons, rs.HS = the HyperShift layer
        if self.sel not in self.buttons or self.sel == 1 or (self.editable and self.sel not in self.editable):
            self.sel = (self.editable or [b for b in self.buttons if b != 1])[0]
        self._set_icon()
        self.tray, self._told_tray = None, False
        self.protocol('WM_DELETE_WINDOW', self.hide_window)  # X hides to the tray, so auto-switch keeps running
        self._style()
        self._build()
        self.load_profile('default')
        self.refresh_list()
        self.read_mouse()
        self.view_active()  # open on whatever the mouse is actually using
        # the profile to return to when no linked game is in focus
        active = self.cfg.get('active', 'default')
        self.base = active if active not in self.cfg['links'].values() else 'default'
        self._start_tray()
        if self.startup_var.get() and getattr(sys, 'frozen', False):
            # keep the entry pointing here if the installed app was moved; a copy run from source (tests, a
            # developer) must not take Windows startup away from the installed one
            set_startup(True)
        if '--tray' in sys.argv and self.tray:  # started with Windows: go straight to the tray
            self._told_tray = True
            self.withdraw()
        self.after(500, self.poll_games)
        self._connected, self._q = None, queue.Queue()  # background results, picked up by poll_games
        self._gen = 0  # bumped when another mouse is picked; results read before that are dropped
        import threading

        def thread_error(a):  # an unexpected error in background work: log it, say so in the window
            log_error('error in background work', (a.exc_type, a.exc_value, a.exc_traceback))
            self._q.put(self._problem)
        threading.excepthook = thread_error
        self.after(300, self.refresh_device)
        self.after(60_000, self.check_updates)
        if '--updated' in sys.argv and self.tray:  # started by the installer after an automatic update
            self.after(3000, lambda: self.tray.notify(f'Updated to version {APP_VERSION}.', 'FreeRazer'))

    # ---------- data ----------
    def shown(self, name):
        """How a profile name is displayed; the built-in one is stored as 'default'."""
        return 'Default' if name == 'default' else name

    def names(self):
        return ['default', *self.cfg['profiles']]

    def own(self, name):
        return self.cfg['default'] if name == 'default' else self.cfg['profiles'][name]

    def editable_for(self, model):
        """Buttons that can be changed: all but left click on a mouse tested here; on any other mouse, the ones
        that read back as their factory action (confirmed when it connects)."""
        ids = rs.editable(model)
        return ids if model['verified'] else [b for b in ids if b & 0xFF in self.mouse.confirmed.get(model['name'], ())]

    def resolved(self, name):
        """{button: action} a profile puts on the mouse; ValueError for a missing profile or a bad action."""
        if name != 'default' and name not in self.cfg['profiles']:
            raise ValueError(f'there is no profile called "{name}"')
        full = rs.resolve({}, None if name == 'default' else self.cfg['profiles'][name], self.model)
        if not self.hs_ok():  # this mouse has no HyperShift layer: normal buttons only, no HyperShift key
            full = {b: rs.factory(self.model, b) if a == 'hypershift' else a for b, a in full.items() if not b & rs.HS}
        return {b: a for b, a in full.items() if b in self.editable}

    def effective(self, b):
        """(action, where it comes from) for button b, on the layer shown, in the profile being edited."""
        if self.layer and self.hs_key(b):
            return 'hypershift', 'Hold it to use the HyperShift buttons'
        key = str(b + self.layer)
        if key in self.edit and self.edit[key] != 'default':
            return self.edit[key], 'Changed in this profile'
        return self.buttons[b][1], 'Factory setting'

    def hs_ok(self, known=False):
        """This mouse may have a HyperShift layer: it isn't known not to (known=True: it is known to)."""
        seen = True if self.model.get('hypershift') else self.mouse.hs.get(self.model['name'])
        return seen is True if known else seen is not False

    def hs_key(self, b):
        """Button b is the HyperShift key in the profile being edited."""
        return self.hs_ok() and self.edit.get(str(b)) == 'hypershift'

    def show_layer_row(self):
        if self.hs_ok():
            self.layer_row.place(in_=self.canvas, relx=0.5, rely=1.0, y=4, anchor='n')
        else:
            self.layer_row.place_forget()
            self.layer_var.set(0)
            self.layer = 0

    def set_layer(self):
        self.close_popover()
        self.layer = self.layer_var.get()
        self.redraw()
        if self.layer and not any(self.hs_key(b) for b in self.buttons):
            self.set_status('No button is the HyperShift key in this profile yet. On Standard, pick a button and '
                            'set it to Mouse > Razer HyperShift.')
        elif self.layer:
            self.set_status('HyperShift: these actions work while you hold the HyperShift key.')

    def _set_icon(self):
        # the icon file is packed inside the exe (unpacked to _MEIPASS); as a script it sits next to this file
        path = os.path.join(getattr(sys, '_MEIPASS', HERE), 'icon.ico')
        try:
            # own taskbar identity, so Windows shows this window's icon instead of Python's
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('FreeRazer')
            self.iconbitmap(default=path)
            from PIL import Image, ImageTk
            self._icon = ImageTk.PhotoImage(Image.open(path).convert('RGBA').resize((256, 256)))
            self.iconphoto(True, self._icon)  # large icon for the taskbar and Alt+Tab
        except (tk.TclError, OSError):
            pass

    # ---------- tray (the hidden-icons arrow by the clock) ----------
    def _start_tray(self):
        try:
            self._make_tray()
        except Exception:  # no tray: the X then minimizes to the taskbar instead, and error.log says why
            self.tray = None
            log_error('tray icon could not start')

    def report_callback_exception(self, *exc):
        log_error('error in the window', exc)  # Tk calls this for exceptions in clicks and timers
        self._problem()

    def _problem(self):
        self.set_status('Something went wrong. The details are in the error log (Settings > Open error log).')

    def _make_tray(self):
        import pystray
        from PIL import Image
        img = Image.open(os.path.join(getattr(sys, '_MEIPASS', HERE), 'icon.ico'))
        later = lambda f, *a: (lambda: self.after(0, f, *a))  # tray runs on its own thread; hand work to Tk
        profiles = pystray.Menu(lambda: [
            pystray.MenuItem(self.shown(n), later(self.apply_from_tray, n), radio=True,
                             checked=lambda item, n=n: self.cfg.get('active') == n)
            for n in self.names()])
        self.tray = pystray.Icon('FreeRazer', img, 'FreeRazer', pystray.Menu(
            pystray.MenuItem('Open FreeRazer', later(self.show_window), default=True),
            pystray.MenuItem('Profile', profiles),
            pystray.MenuItem('Auto-switch for games', later(self.toggle_auto_from_tray),
                             checked=lambda item: bool(self.cfg.get('auto'))),
            pystray.MenuItem('Start with Windows', later(self.toggle_startup_from_tray),
                             checked=lambda item: startup_command() is not None),
            pystray.MenuItem('Check for updates', later(self.check_updates, True)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', later(self.quit_app))))
        self.tray.run_detached()

    def hide_window(self):
        if not self.tray:
            return self.iconify()
        self.close_popover()
        self.withdraw()
        if not self._told_tray:  # say once where it went
            self._told_tray = True
            self.tray.notify('Still running. Open it from the icon by the clock (the ^ arrow).', 'FreeRazer')

    def show_window(self):
        self.view_active()
        self.deiconify()
        self.lift()
        self.focus_force()

    def view_active(self):
        active = self.cfg.get('active')
        if active in self.names() and active != self.current:
            self.load_profile(active)
            self.refresh_list()

    def apply_from_tray(self, name):
        if name in self.names() and self.put_on_mouse(name) and name not in self.cfg['links'].values():
            self.base = name

    def toggle_auto_from_tray(self):
        self.auto_var.set(not self.auto_var.get())
        self.toggle_auto()

    def toggle_startup(self):
        try:
            set_startup(self.startup_var.get())
        except OSError as e:
            self.startup_var.set(startup_command() is not None)
            return self.set_status(f'Could not change the Windows startup setting: {e}')
        if self.tray:
            self.tray.update_menu()
        self.set_status('Starts with Windows, hidden in the tray by the clock.' if self.startup_var.get()
                        else 'No longer starts with Windows.')

    def toggle_startup_from_tray(self):
        self.startup_var.set(not self.startup_var.get())
        self.toggle_startup()

    def quit_app(self):
        if self.tray:
            self.tray.stop()
        self.destroy()

    def write_cfg(self):
        """Save the settings; False (and a message) if the file can't be written, e.g. held by another program.
        Nothing in memory is lost then, and the next save tries again."""
        tmp = CFG + '.tmp'  # write then swap, so a crash can't leave a half-written file
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.cfg, f, indent=2)
                f.flush()
                os.fsync(f.fileno())  # on disk before the swap, so a power cut can't leave an empty file
            os.replace(tmp, CFG)
        except OSError as e:
            log_error('settings could not be saved')
            self.set_status(f'Could not save your settings ({e.strerror or e}). They are kept until the next save.')
            return False
        if getattr(self, 'tray', None):
            self.tray.update_menu()  # profile names, active profile or auto-switch may have changed
        return True

    # ---------- layout ----------
    # Follows Microsoft's Windows app guidance: top navigation for 5 or fewer equal sections, a 52 px header,
    # 24 px content margins, sizes in multiples of 4. The button editor is a pop-up shown only on request.
    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=BG, foreground=FG, font=FONT, bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
        s.configure('TSeparator', background=PANEL)
        s.configure('Muted.TLabel', foreground=MUTED)
        s.configure('H2.TLabel', font=('Segoe UI Semibold', 12))
        s.configure('Head.TFrame', background=SIDE)
        s.configure('Head.TLabel', background=SIDE)
        s.configure('HeadMuted.TLabel', background=SIDE, foreground=MUTED)
        s.configure('HeadOn.TLabel', background=SIDE, foreground=ACCENT)
        s.configure('HeadWarn.TLabel', background=SIDE, foreground=WARN)
        s.configure('Title.TLabel', background=SIDE, font=('Segoe UI Semibold', 12))
        for name, bg in (('Link.TButton', BG), ('HeadLink.TButton', SIDE), ('PopLink.TButton', PANEL)):  # text-only
            s.configure(name, background=bg, foreground=MUTED, padding=(0, 2), borderwidth=0, focuscolor=bg, width=0)
            s.map(name, background=[('active', bg)], foreground=[('active', FG), ('disabled', DIM)])
        s.configure('HeadLink.TButton', font=('Segoe UI', 14), padding=(6, 0))
        s.configure('Nav.TButton', background=BG, foreground=MUTED, padding=(0, 10), borderwidth=0, focuscolor=BG, width=0)
        s.map('Nav.TButton', background=[('active', BG)], foreground=[('active', FG)])
        s.configure('NavOn.TButton', background=BG, foreground=FG, padding=(0, 10), borderwidth=0, focuscolor=BG,
                    width=0, font=('Segoe UI Semibold', 10))
        s.map('NavOn.TButton', background=[('active', BG)])
        s.configure('TButton', background=PANEL, foreground=FG, padding=(14, 7), borderwidth=0)
        s.map('TButton', background=[('active', '#2e333d')])
        s.configure('Accent.TButton', background=ACCENT, foreground='#0b0d10', font=('Segoe UI Semibold', 10), padding=(14, 5))
        s.map('Accent.TButton', background=[('active', '#5fe84a')])
        s.configure('Pop.TFrame', background=PANEL)
        s.configure('PopMuted.TLabel', background=PANEL, foreground=MUTED)
        s.configure('PopSmall.TLabel', background=PANEL, foreground=DIM, font=('Segoe UI', 9))
        s.configure('PopBig.TLabel', background=PANEL, font=('Segoe UI Semibold', 15))
        s.configure('PopBigOn.TLabel', background=PANEL, foreground=ACCENT, font=('Segoe UI Semibold', 15))
        s.configure('Field.TButton', background=SIDE, foreground=MUTED, padding=(10, 12), borderwidth=0)
        s.map('Field.TButton', background=[('active', BG)], foreground=[('active', FG)])
        s.configure('Rec.TButton', background=SEL_FILL, foreground=ACCENT, padding=(10, 12), borderwidth=0)
        s.map('Rec.TButton', background=[('active', SEL_FILL)])
        for name, bg, hover in (('Seg.Toolbutton', PANEL, '#2e333d'), ('PopSeg.Toolbutton', SIDE, BG)):
            s.configure(name, background=bg, foreground=MUTED, padding=(0, 6), anchor='center', borderwidth=0)
            s.map(name, background=[('selected', SEL_FILL), ('active', hover)],
                  foreground=[('selected', ACCENT), ('disabled', DIM), ('active', FG)])
        s.configure('TEntry', fieldbackground=PANEL, foreground=FG, insertcolor=FG, padding=4)
        for name in ('TSpinbox', 'TCombobox'):
            s.configure(name, fieldbackground=PANEL, background=PANEL, foreground=FG, arrowcolor=MUTED,
                        insertcolor=FG, padding=(6, 3), bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
            s.map(name, fieldbackground=[('readonly', PANEL), ('disabled', BG)], foreground=[('disabled', DIM)],
                  selectbackground=[('readonly', PANEL)], selectforeground=[('readonly', FG)])
        s.configure('Pop.TCombobox', fieldbackground=SIDE, background=SIDE, bordercolor=SIDE, lightcolor=SIDE, darkcolor=SIDE)
        s.map('Pop.TCombobox', fieldbackground=[('readonly', SIDE)])
        self._round_styles(s)
        self.option_add('*TCombobox*Listbox.background', PANEL)
        self.option_add('*TCombobox*Listbox.foreground', FG)
        self.option_add('*TCombobox*Listbox.selectBackground', SEL_FILL)
        self.option_add('*TCombobox*Listbox.selectForeground', ACCENT)

    def _build(self):
        self.k = k = self.winfo_fpixels('1i') / 96  # scale drawings with Windows display scaling
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self._switch_imgs = self._switch_images()
        self._shown = {}  # what the mouse last reported, so unchanged controls don't trigger a write

        # header: the profile you're looking at, whether it's on the mouse, battery
        self.head = hd = ttk.Frame(self, style='Head.TFrame', padding=(24, 0))
        hd.grid(row=0, column=0, sticky='nsew')
        self.rowconfigure(0, minsize=round(52 * k))
        ttk.Label(hd, text='FreeRazer', style='Title.TLabel').pack(side='left')
        self.profile_box = ttk.Combobox(hd, state='readonly', width=22, style='Head.TCombobox')
        self.profile_box.pack(side='left', padx=(24, 2))
        self.profile_box.bind('<<ComboboxSelected>>', self.on_pick_profile)
        ttk.Button(hd, text='⋯', style='HeadLink.TButton', command=self.profile_menu).pack(side='left')
        self.state_lbl = ttk.Label(hd, style='HeadMuted.TLabel')
        self.state_lbl.pack(side='left', padx=(16, 12))
        self.apply_btn = ttk.Button(hd, text='Apply to mouse', style='Head.Accent.TButton', command=self.apply)
        self.dev_lbl = ttk.Label(hd, style='HeadMuted.TLabel', text='Looking for the mouse…')
        self.dev_lbl.pack(side='right')
        self.mouse_pick = ttk.Frame(hd, style='Head.TFrame')  # only shown with 2+ mice plugged in
        ttk.Label(self.mouse_pick, text='Mouse', style='HeadMuted.TLabel').pack(side='left', padx=(0, 8))
        self.mouse_btn = ttk.Button(self.mouse_pick, style='Head.TButton', image=self._chevron, compound='right',
                                    command=self.mouse_menu)
        self.mouse_btn.pack(side='left')
        self._mice = []
        self.warn_lbl = ttk.Label(hd, style='HeadWarn.TLabel')  # shown while Razer Synapse is running
        self._synapse = []

        # top navigation: four equal sections
        nav = ttk.Frame(self, padding=(24, 0))
        nav.grid(row=1, column=0, sticky='ew')
        self.nav = {}
        for key, text in (('buttons', 'Buttons'), ('performance', 'Performance'), ('games', 'Games'), ('settings', 'Settings')):
            f = ttk.Frame(nav)
            f.pack(side='left', padx=(0, 24))
            b = ttk.Button(f, text=text, style='Nav.TButton', command=lambda key=key: self.show_page(key))
            b.pack()
            bar = tk.Frame(f, height=2, bg=BG)  # green underline on the open page
            bar.pack(fill='x')
            self.nav[key] = (b, bar)
        ttk.Separator(self).grid(row=2, column=0, sticky='ew')

        body = ttk.Frame(self)
        body.grid(row=3, column=0, sticky='nsew')
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.pages = {key: ttk.Frame(body, padding=PAGE_PAD) for key in self.nav}
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky='nsew')

        # Buttons: the picture gets the whole page; click a button for its editor
        pg = self.pages['buttons']
        pg.configure(height=round((H + 88) * k))  # room for the pop-up under the lower buttons
        self.canvas = tk.Canvas(pg, width=W * k, height=H * k, bg=BG, highlightthickness=0, takefocus=1)
        self.canvas.pack(anchor='n')
        self.canvas.bind('<Button-1>', self.on_canvas_click)
        self.canvas.bind('<Motion>', self.on_motion)
        # Esc anywhere closes the editor, except while recording, when Esc is the key being recorded
        self.bind('<Escape>', lambda e: self.on_key(e) if self.recording else self.close_popover())
        self.canvas.bind('<Return>', lambda e: self.select(self.sel))
        for key, step in (('<Up>', -1), ('<Left>', -1), ('<Down>', 1), ('<Right>', 1)):
            self.canvas.bind(key, lambda e, s=step: self.step_sel(s))
        self._draw_mouse()
        # Standard / HyperShift, under the picture on a mouse with HyperShift; placed, so the page keeps its size
        self.layer_row = ttk.Frame(pg)
        self.layer_var = tk.IntVar(value=0)
        for i, (val, txt) in enumerate(((0, 'Standard'), (rs.HS, 'HyperShift'))):
            ttk.Radiobutton(self.layer_row, text=txt, value=val, variable=self.layer_var, style='Seg.Toolbutton',
                            width=11, command=self.set_layer).pack(side='left', padx=(0 if i == 0 else 2, 0))
        self.show_layer_row()
        self._build_popover(pg)

        # Performance: sensitivity and polling rate together
        pg = self.pages['performance']
        ttk.Label(pg, text='Sensitivity', style='H2.TLabel').pack(anchor='w')
        ttk.Label(pg, text='How far the pointer moves for each inch you move the mouse.', style='Muted.TLabel').pack(anchor='w', pady=(2, 12))
        row = ttk.Frame(pg)
        row.pack(anchor='w')
        self.dpi_var = tk.StringVar()
        self.dpi_rng = rs.DPI_RANGE  # the connected mouse's own range, set when it is read
        self.dpi_box = ttk.Spinbox(row, textvariable=self.dpi_var, from_=rs.DPI_RANGE[0], to=rs.DPI_RANGE[1],
                                   increment=50, width=8, command=self.dpi_changed)
        self.dpi_box.pack(side='left')
        self.dpi_box.bind('<Return>', lambda e: self.dpi_changed())
        self.dpi_box.bind('<FocusOut>', lambda e: self.dpi_changed())
        ttk.Label(row, text='DPI', style='Muted.TLabel').pack(side='left', padx=(8, 20))
        self.dpi_scale = Slider(row, 0, 1000, round(360 * k), k, command=self.dpi_sliding, release=self.dpi_changed)
        self.dpi_scale.pack(side='left')
        ttk.Label(pg, text='Polling rate', style='H2.TLabel').pack(anchor='w', pady=(32, 0))
        ttk.Label(pg, text='How often the mouse reports its position, per second. Higher feels smoother '
                           'but uses more battery.', style='Muted.TLabel').pack(anchor='w', pady=(2, 12))
        seg = ttk.Frame(pg)
        seg.pack(anchor='w')
        self.poll_var = tk.IntVar()
        self.poll_btns = []
        for i, hz in enumerate(sorted(rs.POLL_HZ.values())):
            rb = ttk.Radiobutton(seg, text=f'{hz} Hz', value=hz, variable=self.poll_var, style='Seg.Toolbutton',
                                 width=9, command=self.poll_changed)
            rb.grid(row=0, column=i, padx=(0 if i == 0 else 2, 0))
            self.poll_btns.append(rb)
        ttk.Label(pg, text='Power saving', style='H2.TLabel').pack(anchor='w', pady=(32, 0))
        ttk.Label(pg, text='Makes the battery last longer when the mouse is wireless.',
                  style='Muted.TLabel').pack(anchor='w', pady=(2, 8))
        self.power = {}  # 'sleep' / 'low': (slider, value label, unit)
        for key, text, lo, hi, unit in (('sleep', 'Sleep after being idle for', *rs.SLEEP_MIN, 'min'),
                                         ('low', 'Low power mode when battery is below', rs.LOW_POWER_MIN, 25, '%')):
            row = ttk.Frame(pg)
            row.pack(anchor='w', pady=(6, 0))
            ttk.Label(row, text=text, width=34).pack(side='left')
            sc = Slider(row, lo, hi, round(260 * k), k, command=lambda v, key=key: self.power_sliding(key, v),
                        release=lambda key=key: self.power_changed(key))
            sc.pack(side='left')
            val = ttk.Label(row, width=8, style='Muted.TLabel')
            val.pack(side='left', padx=(12, 0))
            self.power[key] = (sc, val, unit)
        self.light_box = ttk.Frame(pg)  # shown only for a mouse whose light FreeRazer knows
        ttk.Label(self.light_box, text='Lighting', style='H2.TLabel').pack(anchor='w', pady=(32, 0))
        ttk.Label(self.light_box, text='The light on the mouse.', style='Muted.TLabel').pack(anchor='w', pady=(2, 12))
        row = ttk.Frame(self.light_box)
        row.pack(anchor='w')
        self.light_var = tk.StringVar()
        self._rgb = (0x44, 0xD6, 0x2C)  # colour for Static and Breathing, kept while another effect is on
        for i, (key, text) in enumerate(LIGHT_NAMES.items()):
            ttk.Radiobutton(row, text=text, value=key, variable=self.light_var, style='Seg.Toolbutton', width=11,
                            command=self.light_changed).grid(row=0, column=i, padx=(0 if i == 0 else 2, 0))
        row = ttk.Frame(self.light_box)
        row.pack(anchor='w', pady=(12, 0))
        ttk.Label(row, text='Color', width=34).pack(side='left')
        # the current colour; click it for the detailed picker
        self.swatch = tk.Canvas(row, width=round(64 * k), height=round(26 * k), bg=BG, highlightthickness=0,
                                cursor='hand2', takefocus=1)
        self.swatch_item = self.swatch.create_image(0, 0, anchor='nw')
        self.swatch.pack(side='left')
        self.swatch.bind('<Button-1>', lambda e: self.open_picker())
        self.swatch.bind('<Return>', lambda e: self.open_picker())
        self.dots = ColorDots(row, LIGHT_PRESETS, k, command=self.pick_color)
        self.dots.pack(side='left', padx=(20, 0))
        row = ttk.Frame(self.light_box)
        row.pack(anchor='w', pady=(12, 0))
        ttk.Label(row, text='Brightness', width=34).pack(side='left')
        self.bright = Slider(row, 0, 100, round(260 * k), k, command=lambda v: self.bright_val.configure(text=f'{int(float(v))}%'),
                             release=self.bright_changed)
        self.bright.pack(side='left')
        self.bright_val = ttk.Label(row, width=8, style='Muted.TLabel')
        self.bright_val.pack(side='left', padx=(12, 0))
        self.perf_note = ttk.Label(pg, style='Muted.TLabel')
        self.perf_note.pack(anchor='w', pady=(24, 0))

        # Games: which game uses which profile
        pg = self.pages['games']
        top = ttk.Frame(pg)
        top.pack(fill='x')
        ttk.Label(top, text='Games', style='H2.TLabel').pack(side='left')
        self.auto_var = tk.BooleanVar(value=self.cfg.get('auto', False))
        self._switch(top, 'Auto-switch', self.auto_var, self.toggle_auto).pack(side='right')
        ttk.Label(pg, text='While a game below is the window in focus, its profile goes on the mouse. '
                           'Any other window uses the profile you applied yourself.',
                  style='Muted.TLabel', wraplength=round(620 * k)).pack(anchor='w', pady=(4, 16))
        self.games_list = ttk.Frame(pg)
        self.games_list.pack(fill='x')
        ttk.Button(pg, text='+ Add a game…', style='Link.TButton', command=self.link_game).pack(anchor='w', pady=(12, 0))

        # Settings: the app itself
        pg = self.pages['settings']
        ttk.Label(pg, text='Startup', style='H2.TLabel').pack(anchor='w')
        self.startup_var = tk.BooleanVar(value=startup_command() is not None)
        self._switch(pg, 'Start with Windows, hidden in the tray by the clock', self.startup_var,
                     self.toggle_startup).pack(anchor='w', pady=(8, 0))
        ttk.Label(pg, text='Profiles', style='H2.TLabel').pack(anchor='w', pady=(32, 8))
        row = ttk.Frame(pg)
        row.pack(anchor='w')
        for i, (text, cmd) in enumerate((('New profile', self.new), ('Duplicate', self.duplicate),
                                         ('Export…', self.export_profile), ('Import…', self.import_profiles))):
            ttk.Button(row, text=text, command=cmd).pack(side='left', padx=(0 if i == 0 else 8, 0))
        ttk.Label(pg, text='Updates', style='H2.TLabel').pack(anchor='w', pady=(32, 8))
        self.auto_update_var = tk.BooleanVar(value=self.cfg.get('auto_update', True))
        self._switch(pg, 'Check for updates automatically and ask before installing', self.auto_update_var,
                     self.toggle_auto_update).pack(anchor='w')
        row = ttk.Frame(pg)
        row.pack(anchor='w', pady=(8, 0))
        ttk.Button(row, text='Check for updates', command=lambda: self.check_updates(manual=True)).pack(side='left')
        self.update_lbl = ttk.Label(row, style='Muted.TLabel', text=f'Version {APP_VERSION}')
        self.update_lbl.pack(side='left', padx=(12, 0))
        ttk.Label(pg, text='Mouse database', style='H2.TLabel').pack(anchor='w', pady=(32, 0))
        ttk.Label(pg, text='Which Razer mice FreeRazer knows the settings of. Updating adds new mice without a new version.',
                  style='Muted.TLabel').pack(anchor='w', pady=(2, 8))
        row = ttk.Frame(pg)
        row.pack(anchor='w')
        ttk.Button(row, text='Update mouse database', command=self.update_db).pack(side='left')
        self.db_lbl = ttk.Label(row, style='Muted.TLabel')
        self.db_lbl.pack(side='left', padx=(12, 0))
        self.show_db()
        ttk.Label(pg, text='Mouse missing buttons, or not known? Copy a report and paste it into an issue on GitHub. '
                           'It only reads from the mouse.', style='Muted.TLabel').pack(anchor='w', pady=(12, 8))
        row = ttk.Frame(pg)
        row.pack(anchor='w')
        self.report_btn = ttk.Button(row, text='Copy mouse report', command=self.copy_report)
        self.report_btn.pack(side='left')
        ttk.Button(row, text='Open GitHub issues', style='Link.TButton',
                   command=lambda: os.startfile(ISSUES_URL)).pack(side='left', padx=(12, 0))
        ttk.Label(pg, text='About', style='H2.TLabel').pack(anchor='w', pady=(32, 4))
        self.about_lbl = ttk.Label(pg, style='Muted.TLabel')
        self.about_lbl.pack(anchor='w')
        ttk.Label(pg, text='Mouse data thanks to the OpenRazer project (github.com/openrazer/openrazer). '
                           'Not affiliated with Razer or OpenRazer.', style='Muted.TLabel').pack(anchor='w', pady=(4, 0))
        row = ttk.Frame(pg)
        row.pack(anchor='w', pady=(12, 0))
        ttk.Button(row, text='Open error log', command=self.open_log).pack(side='left')
        ttk.Button(row, text='Quit FreeRazer', command=self.quit_app).pack(side='left', padx=(8, 0))

        self.status = ttk.Label(self, style='Muted.TLabel')
        self.status.grid(row=4, column=0, sticky='w', padx=24, pady=(0, 16))
        # the smallest window that fits every page (Lighting included); measured while all pages are stacked
        self.light_box.pack(anchor='w', before=self.perf_note)
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self._min_size = (w, h - round((self.extra_height() - H) * k))  # without any More buttons rows
        self.light_box.pack_forget()
        self.minsize(w, h)
        self.geometry(f'{w}x{h}')  # a set size, so switching pages doesn't resize the window
        self.show_page('buttons')

    def _build_popover(self, parent):
        """The button editor: a small card next to the clicked button, closed with Esc or a click elsewhere."""
        k = self.k
        self.pop = ttk.Frame(parent, style='Card.TFrame', padding=round(5 * k))  # rounded card; see _round_styles
        inner = ttk.Frame(self.pop, style='Pop.TFrame', padding=12)
        inner.pack(fill='both')
        top = ttk.Frame(inner, style='Pop.TFrame')
        top.pack(fill='x')
        self.btn_name = ttk.Label(top, style='PopMuted.TLabel')
        self.btn_name.pack(side='left')
        ttk.Button(top, text='✕', style='PopLink.TButton', command=self.close_popover).pack(side='right')
        self.action_lbl = ttk.Label(inner, style='PopBig.TLabel')
        self.action_lbl.pack(anchor='w')
        self.source_lbl = ttk.Label(inner, style='PopSmall.TLabel')
        self.source_lbl.pack(anchor='w', pady=(0, 12))
        seg = ttk.Frame(inner, style='Pop.TFrame')
        seg.pack(fill='x', pady=(0, 8))
        self.mode_var = tk.StringVar(value='key')
        self.seg_btns = []
        for i, (val, txt) in enumerate((('key', 'Key'), ('mouse', 'Mouse'), ('dpi', 'DPI'))):
            rb = ttk.Radiobutton(seg, text=txt, value=val, variable=self.mode_var, style='PopSeg.Toolbutton',
                                 command=self.show_mode)
            rb.grid(row=0, column=i, sticky='ew', padx=(0 if i == 0 else 2, 0))
            seg.columnconfigure(i, weight=1, uniform='seg')
            self.seg_btns.append(rb)
        self.body = ttk.Frame(inner, style='Pop.TFrame', width=round(264 * k), height=round(48 * k))
        self.body.pack(fill='x')
        self.body.pack_propagate(False)  # same size for every kind of action, so the card doesn't jump
        self.rec_btn = ttk.Button(self.body, text=REC_IDLE, style='Field.TButton', command=self.toggle_record)
        self.pick_box = ttk.Combobox(self.body, state='readonly', style='Pop.TCombobox')
        self.pick_box.bind('<<ComboboxSelected>>', self.pick_action)
        self.locked_lbl = ttk.Label(self.body, style='PopMuted.TLabel', wraplength=round(260 * k),
                                    text='Default is the factory setup. Make a new profile (⋯ menu) to change buttons.')
        foot = ttk.Frame(inner, style='Pop.TFrame')
        foot.pack(fill='x', pady=(12, 0))
        self.reset_btn = ttk.Button(foot, text='Reset to factory', style='PopLink.TButton', command=self.factory)
        self.reset_btn.pack(side='left')
        self.saved_lbl = ttk.Label(foot, style='PopSmall.TLabel')
        self.saved_lbl.pack(side='right')
        self.pop_open = False
        # the picture is centred, so it moves when the window is resized; move the editor with it
        # checked again when it runs: the editor may have been closed in the meantime
        parent.bind('<Configure>', lambda e: self.pop_open and self.after_idle(
            lambda: self.pop_open and self.open_popover()))

    def open_popover(self):
        """Place the editor under the selected button's label, or above it when there's no room below."""
        self.pop_open = True
        self.update_idletasks()
        x0, y0, x1, y1 = self.canvas.bbox(self.labels[self.sel][0])
        cx, cy = self.canvas.winfo_x(), self.canvas.winfo_y()
        page = self.pop.master
        gap = round(8 * self.k)
        for _ in range(2):  # Tk reports a smaller size before the card is first shown: place, measure, place again
            pw, ph = max(self.pop.winfo_width(), self.pop.winfo_reqwidth()), max(self.pop.winfo_height(), self.pop.winfo_reqheight())
            x = cx + (x1 - pw if LABELS.get(self.sel, ('r',))[0] == 'l' else x0)
            x = max(0, min(x, page.winfo_width() - pw))
            y = cy + y1 + gap
            if y + ph > page.winfo_height():
                y = max(0, cy + y0 - gap - ph)
            self.pop.place(x=x - PAGE_PAD, y=y - PAGE_PAD)  # place measures from inside the page's padding
            self.pop.lift()
            self.update_idletasks()

    def close_popover(self):
        self.stop_record()
        self.pop.place_forget()
        self.pop_open = False

    def show_page(self, key):
        self.close_popover()
        for name, page in self.pages.items():  # hidden pages are taken out so resizing doesn't redraw them
            page.grid() if name == key else page.grid_remove()
        for name, (b, bar) in self.nav.items():
            b.configure(style='NavOn.TButton' if name == key else 'Nav.TButton')
            bar.configure(bg=ACCENT if name == key else BG)
        if key == 'games':
            self.show_games()

    def _round_styles(self, s):
        """Rounded corners: each style draws its shape as an anti-aliased picture. The corners are see-through
        and show the style's own background, so every style's background is the colour of what it sits on."""
        k = self.winfo_fpixels('1i') / 96
        self._round_imgs = []
        plain = s.layout('TButton')  # text-only buttons keep the flat layout

        def shape(name, states, outer, r=6):
            """states: [(state spec or None, fill, outline)], the plain look first."""
            # Tk tiles the middle of the picture to fill the widget; a big middle means few tiles (fast resizing)
            imgs = [rounded_image((2 * r + 200, 2 * r + 200), r, fill, outline, k) for _, fill, outline in states]
            self._round_imgs += imgs
            small = round((2 * r + 8) * k)  # the size the element asks for, not the picture's size
            s.element_create(name, 'image', imgs[0], *[(st, im) for (st, _, _), im in zip(states[1:], imgs[1:])],
                             border=round((r + 3) * k), padding=0, sticky='nsew', width=small, height=small)
            return outer

        def button(style, states, outer, kind='Button'):
            el = f'{style}.round'
            shape(el, states, outer)
            s.layout(style, [(el, {'sticky': 'nsew', 'children': [(f'{kind}.focus', {'sticky': 'nsew', 'children': [
                (f'{kind}.padding', {'sticky': 'nsew', 'children': [(f'{kind}.label', {'sticky': 'nsew'})]})]})]})])
            s.configure(style, background=outer, focuscolor=outer)
            s.map(style, background=[])

        hover = '#2e333d'
        button('TButton', [(None, PANEL, None), ('pressed', hover, None), ('active', hover, None)], BG)
        button('Accent.TButton', [(None, ACCENT, None), ('active', '#5fe84a', None)], BG)
        s.configure('Head.Accent.TButton', background=SIDE, focuscolor=SIDE)
        button('Field.TButton', [(None, SIDE, None), ('active', BG, None)], PANEL)
        button('Rec.TButton', [(None, SEL_FILL, ACCENT_DIM)], PANEL)
        for name in ('Link.TButton', 'HeadLink.TButton', 'PopLink.TButton', 'Nav.TButton', 'NavOn.TButton'):
            s.layout(name, plain)
        button('Seg.Toolbutton', [(None, PANEL, None), ('selected', SEL_FILL, ACCENT_DIM), ('active', hover, None)], BG,
               'Toolbutton')
        button('PopSeg.Toolbutton', [(None, SIDE, None), ('selected', SEL_FILL, ACCENT_DIM), ('active', BG, None)], PANEL,
               'Toolbutton')
        s.configure('Head.TButton', background=SIDE, focuscolor=SIDE, padding=(10, 3))  # mouse picker in the header
        # drop-down menu rows (see popup)
        button('Menu.TButton', [(None, PANEL, None), ('disabled', PANEL, None), ('active', hover, None)], PANEL)
        s.configure('Menu.TButton', anchor='w', padding=(12, 6))
        s.map('Menu.TButton', foreground=[('disabled', DIM)])
        s.configure('On.Menu.TButton', foreground=ACCENT)  # the item that is picked now

        # fields: combobox, spinbox, entry. Arrow element names must end in downarrow/uparrow for Tk's bindings.
        down, up = chevron_image(False, MUTED, k), chevron_image(True, MUTED, k)
        self._round_imgs += [down, up]
        self._chevron = down
        s.element_create('Round.downarrow', 'image', down, sticky='', width=round(24 * k))
        s.element_create('Spin.uparrow', 'image', up, sticky='', width=round(20 * k), height=round(12 * k))
        s.element_create('Spin.downarrow', 'image', down, sticky='', width=round(20 * k), height=round(12 * k))
        focus = ('focus', PANEL, ACCENT_DIM)
        for style, fill, outer in (('TCombobox', PANEL, BG), ('Pop.TCombobox', SIDE, PANEL)):
            el = f'{style}.round'
            shape(el, [(None, fill, None), ('disabled', BG, None)], outer)
            s.layout(style, [(el, {'sticky': 'nsew', 'children': [('Round.downarrow', {'side': 'right', 'sticky': 'ns'}),
                     ('Combobox.padding', {'sticky': 'nsew', 'children': [('Combobox.textarea', {'sticky': 'nsew'})]})]})])
            s.configure(style, background=outer, fieldbackground=fill)
            s.map(style, fieldbackground=[], selectbackground=[('readonly', fill)])
        s.configure('Head.TCombobox', background=SIDE)
        shape('TSpinbox.round', [(None, PANEL, None), focus], BG)
        s.layout('TSpinbox', [('TSpinbox.round', {'side': 'top', 'sticky': 'we', 'children': [
            ('null', {'side': 'right', 'sticky': '', 'children': [('Spin.uparrow', {'side': 'top', 'sticky': 'e'}),
                                                                  ('Spin.downarrow', {'side': 'bottom', 'sticky': 'e'})]}),
            ('Spinbox.padding', {'sticky': 'nsew', 'children': [('Spinbox.textarea', {'sticky': 'nsew'})]})]})])
        s.configure('TSpinbox', background=BG, padding=(8, 4))
        shape('TEntry.round', [(None, PANEL, None), focus], BG)
        s.layout('TEntry', [('TEntry.round', {'sticky': 'nsew', 'children': [
            ('Entry.padding', {'sticky': 'nsew', 'children': [('Entry.textarea', {'sticky': 'nsew'})]})]})])
        s.configure('TEntry', background=BG, padding=(8, 5))
        s.configure('Head.TEntry', background=SIDE)

        # the button editor card
        shape('Card.round', [(None, PANEL, LEADER)], BG, r=10)
        s.layout('Card.TFrame', [('Card.round', {'sticky': 'nsew'})])
        s.configure('Card.TFrame', background=BG)

    def _switch(self, parent, text, var, cmd):
        # classic Checkbutton: it can show a drawn switch instead of ttk's boxed tick
        return tk.Checkbutton(parent, text='  ' + text, variable=var, command=cmd, image=self._switch_imgs[0],
                              selectimage=self._switch_imgs[1], compound='left', indicatoron=False, font=FONT,
                              bg=BG, fg=FG, activebackground=BG, activeforeground=FG, selectcolor=BG,
                              bd=0, highlightthickness=0, offrelief='flat', overrelief='flat', cursor='hand2')

    def open_log(self):
        if os.path.exists(LOG):
            os.startfile(LOG)
        else:
            self.set_status('No problems have been logged.')

    def _switch_images(self):
        """Off and on pictures for the switches, drawn smooth like the mouse."""
        from PIL import Image, ImageDraw, ImageTk
        w, h, S = round(32 * self.k), round(16 * self.k), 4
        out = []
        for on in (False, True):
            img = Image.new('RGBA', (w * S, h * S), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=h * S // 2, fill=ACCENT_DIM if on else PANEL)
            r, x = h * S // 2 - 2 * S, (w * S - h * S // 2) if on else h * S // 2
            d.ellipse((x - r, h * S // 2 - r, x + r, h * S // 2 + r), fill=ACCENT if on else LINE)
            out.append(ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS)))
        return out

    def _draw_mouse(self):
        c = self.canvas
        c.delete('all')
        self.labels, self._overlays, self._base = {}, {}, None  # a new model needs its picture rendered again
        self._draw_line_art()
        self._draw_labels()
        c.scale('all', 0, 0, self.k, self.k)

    def _draw_line_art(self):
        """Top view as line art. Pillow draws it anti-aliased (Tk can't); see show_art."""
        cx = CX
        mirror = lambda pts: [(-x, y) for x, y in pts]
        A = lambda pts: [(cx + x, y) for x, y in pts]
        # traced from the owner's top-down photo (straightened 2.25°, length scaled to 305). Only the
        # right half is defined; the left is its exact mirror. Button fronts and seams are straight.
        right = [(0, 22.5), (9.5, 22.5), (11, 15.5), (60, 33)]  # wheel notch, then the button front
        if self.model['drawing'] == 'viper-v4-pro':
            body = [(60, 33), (63.5, 37), (64.6, 45.6), (66.7, 60), (68.2, 82), (70, 120), (73.2, 164),
                    (75.6, 205), (75.6, 223), (74.7, 245), (72.6, 260), (68.2, 275), (60.2, 290),
                    (46.2, 305), (30, 315), (0, 321)]
        else:  # generic: a plain symmetric shell around the same button layout, not any real model's shape
            body = [(60, 33), (65, 45), (69, 90), (74, 160), (78, 220), (74, 265), (58, 298), (32, 314), (0, 318)]
        right += catmull(body, start=(11, 15.5), end=(-30, 315))[1:]
        seam = [(63, 37), (64, 151), (62.5, 155), (59, 156), (2, 156), (2, 90), (9.5, 89), (9.5, 22.5)]
        area = [(9.5, 22.5), (11, 15.5), (60, 33), (63, 37), (64, 151), (62.5, 155), (59, 156), (2, 156), (2, 90), (9.5, 89)]
        self.art = {
            'outline': A(right) + A(mirror(right[::-1])),
            'seams': [A(seam), A(mirror(seam))],
            'areas': {2: A(area), 1: A(mirror(area))},
            'wheel': (cx - 7.6, 47, cx + 7.6, 83.5),
            'side': {5: (cx - 77, 115, cx - 70, 158), 4: (cx - 79, 165, cx - 73, 203)},
            'dpi': (cx - 9, 221, cx + 9, 239),
            'up': A([(-4, 43), (0, 39), (4, 43)]), 'down': A([(-3, 86), (0, 88.5), (3, 86)]),
        }
        box = lambda x0, y0, x1, y1: [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        # click areas, small parts first so they win over the big button areas around them
        self.hit = [(9, box(cx - 9, 36, cx + 9, 46)), (10, box(cx - 9, 84, cx + 9, 89.5)),
                    (3, box(*self.art['wheel'])), (5, box(cx - 81, 113, cx - 68, 160)),
                    (4, box(cx - 83, 163, cx - 71, 205)), (0x60, box(*self.art['dpi'])),
                    (1, self.art['areas'][1]), (2, self.art['areas'][2])]
        self.art['side'] = {b: v for b, v in self.art['side'].items() if b in self.buttons}
        self.hit = [(b, poly) for b, poly in self.hit if b in self.buttons]
        self.art_item = self.canvas.create_image(0, 0, anchor='nw')
        self.overlay_item = self.canvas.create_image(0, 0, anchor='nw')  # the highlighted button, drawn on top
        if 0x60 in self.buttons:
            self.canvas.create_text(cx, 252, text='underside', fill=DIM, font=('Segoe UI', 8))

    def _render(self, sel):
        """The whole drawing with button `sel` highlighted, at screen size."""
        from PIL import Image, ImageDraw
        S = 3 * self.k  # draw 3x larger, then shrink: smooth edges
        a = self.art
        img = Image.new('RGB', (round(W * S), round(H * S)), BG)
        d = ImageDraw.Draw(img)
        P = lambda pts: [(x * S, y * S) for x, y in pts]
        B = lambda box: [v * S for v in box]
        w = max(1, round(1.5 * S))
        on = lambda b: ACCENT if b == sel else LINE
        if sel in a['areas']:
            d.polygon(P(a['areas'][sel]), fill=SEL_FILL)
        d.line(P(a['outline'] + a['outline'][:1]), fill=LINE, width=w, joint='curve')
        for seam in a['seams']:
            d.line(P(seam), fill=LINE, width=w, joint='curve')
        d.line(P([(CX - 3, 31), (CX + 3, 31)]), fill=LINE, width=round(2 * S))  # indicator light
        d.rounded_rectangle(B(a['wheel']), radius=4 * S, fill=SEL_FILL if sel == 3 else BG, outline=on(3), width=w)
        for y in range(53, 79, 5):  # wheel grip
            d.line(P([(CX - 4, y), (CX + 4, y)]), fill=LEADER, width=max(1, round(S)))
        d.line(P(a['up']), fill=on(9), width=w, joint='curve')
        d.line(P(a['down']), fill=on(10), width=w, joint='curve')
        for b, box in a['side'].items():
            d.rounded_rectangle(B(box), radius=3 * S, fill=SEL_FILL if sel == b else BG, outline=on(b), width=w)
        for start in range(0, 360, 30) if 0x60 in self.buttons else ():  # dotted ring: DPI button underneath
            d.arc(B(a['dpi']), start, start + 15, fill=ACCENT if sel == 0x60 else LEADER, width=w)
        for b in (b for b in LABELS if b in self.buttons):  # leader lines, drawn here so they're smooth too
            pts = leader(b)
            d.line(P(pts), fill=ACCENT if b == sel else LEADER, width=max(1, round(S)), joint='curve')
            (x, y), r = pts[1], 2.2 * S
            d.ellipse((x * S - r, y * S - r, x * S + r, y * S + r), fill=ACCENT if b == sel else LEADER)
        return img.resize((round(W * self.k), round(H * self.k)), Image.LANCZOS)

    def show_art(self):
        # The full drawing is rendered once; each button's highlight is rendered once, cut down to that
        # button's corner of the picture, and laid on top. Clicking around then costs no drawing at all.
        from PIL import ImageTk
        if not getattr(self, '_base', None):
            self._base = ImageTk.PhotoImage(self._render(None))
            self.canvas.itemconfigure(self.art_item, image=self._base)
        if self.sel not in LABELS:  # an extra button has no part of the picture to light up
            return self.canvas.itemconfigure(self.overlay_item, image='')
        if self.sel not in self._overlays:
            xs, ys = zip(*dict(self.hit)[self.sel], *leader(self.sel))
            k = self.k
            box = (int((min(xs) - 4) * k), int((min(ys) - 4) * k), int((max(xs) + 4) * k) + 1, int((max(ys) + 4) * k) + 1)
            self._overlays[self.sel] = (ImageTk.PhotoImage(self._render(self.sel).crop(box)), box[0], box[1])
        photo, x, y = self._overlays[self.sel]
        self.canvas.itemconfigure(self.overlay_item, image=photo)
        self.canvas.coords(self.overlay_item, x, y)

    def hit_test(self, x, y):
        for b, poly in self.hit:
            inside = False
            for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
                if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                    inside = not inside
            if inside:
                return b
        return None

    def on_motion(self, e):
        over = self.hit_test(e.x / self.k, e.y / self.k) is not None
        over = over or any(t.startswith('b') for t in self.canvas.gettags('current'))
        self.canvas.configure(cursor='hand2' if over else '')

    def _draw_labels(self):
        """Action text in two columns; their leader lines are part of the picture (see _render). Buttons the
        picture has no place for (a mouse with more side buttons, say) go under it, in the same two columns."""
        c = self.canvas
        extra = [b for b in self.buttons if b not in LABELS]
        places = {b: (side, y) for b, (side, y, _, _) in LABELS.items() if b in self.buttons}
        if extra:
            c.create_text(CX, H + 14, text='More buttons', fill=MUTED, font=('Segoe UI Semibold', 10))
            for i, b in enumerate(extra):  # three columns: under the left labels, the mouse, the right labels
                places[b] = ('lcr'[i % 3], H + 46 + i // 3 * EXTRA_ROW)
        c.configure(height=round(self.extra_height() * self.k))
        for b, (side, y) in places.items():
            s = {'l': -1, 'c': 0, 'r': 1}[side]
            text = c.create_text(CX + s * (REACH + 53), y, anchor={'l': 'e', 'c': 'center', 'r': 'w'}[side], font=FONT,
                                 tags=(f'b{b}',))
            self.labels[b] = (text,)
            if b in self.editable:
                c.tag_bind(f'b{b}', '<Button-1>', lambda e, b=b: self.select(b))
            else:
                c.tag_bind(f'b{b}', '<Button-1>', lambda e, b=b: self.locked(b))

    def extra_height(self):
        """Canvas height: the picture, plus the More buttons rows when this mouse has buttons beyond it."""
        n = sum(b not in LABELS for b in self.buttons)
        return H + 26 + (n + 2) // 3 * EXTRA_ROW if n else H

    def on_canvas_click(self, e):
        self.canvas.focus_set()
        b = self.hit_test(e.x / self.k, e.y / self.k)
        if b is not None:
            self.select(b)  # says why when it can't be changed
        elif not self.canvas.find_withtag('current'):  # empty space closes the editor
            self.close_popover()

    def set_status(self, text):
        self.status.configure(text=text)

    # ---------- showing ----------
    def refresh_list(self):
        """Header: the profile you're looking at, and whether it is the one on the mouse."""
        self.profile_box['values'] = [self.shown(n) for n in self.names()]
        self.profile_box.set(self.shown(self.current))
        on = self.current == self.cfg.get('active')
        self.state_lbl.configure(text='On the mouse' if on else 'Not on the mouse',
                                 style='HeadOn.TLabel' if on else 'HeadMuted.TLabel')
        if on:
            self.apply_btn.pack_forget()
        else:
            self.apply_btn.pack(side='left', after=self.state_lbl)
        self.show_games()

    def load_profile(self, name):
        self.stop_record()
        self.current, self.edit = name, dict(self.own(name))
        locked = name == 'default'
        for w in (*self.seg_btns, self.reset_btn):
            w.state(['disabled'] if locked else ['!disabled'])
        self.redraw()

    def show_games(self):
        """Games page: one row per game, with the profile it uses."""
        for w in self.games_list.winfo_children():
            w.destroy()
        choices = list(self.cfg['profiles'])
        if not self.cfg['links']:
            ttk.Label(self.games_list, text='No games yet. Add one, then pick the profile it should use.',
                      style='Muted.TLabel').pack(anchor='w')
        for exe, prof in sorted(self.cfg['links'].items()):
            row = ttk.Frame(self.games_list)
            row.pack(fill='x', pady=4)
            ttk.Label(row, text=exe, width=32).pack(side='left')
            box = ttk.Combobox(row, state='readonly', width=22, values=choices)
            box.set(prof)
            box.pack(side='left', padx=(12, 16))
            box.bind('<<ComboboxSelected>>', lambda e, exe=exe, box=box: self.relink_game(exe, box.get()))
            ttk.Button(row, text='Remove', style='Link.TButton',
                       command=lambda exe=exe: self.unlink_game(exe)).pack(side='left')

    def redraw(self):
        c = self.canvas
        for b, (text,) in self.labels.items():
            editable, sel = b in self.editable and not (self.layer and self.hs_key(b)), b == self.sel
            action = self.effective(b)[0] if b in self.editable else self.buttons[b][1]
            # like Synapse: green = remapped, white = factory, dim = can't change
            color = DIM if not editable else ACCENT if action != self.buttons[b][1] else FG
            shown = rs.pretty(action) if b in LABELS else f'{self.buttons[b][0]}:  {rs.pretty(action)}'  # no line to it
            c.itemconfigure(text, text=shown, fill=color,
                            font=('Segoe UI Semibold', 10) if sel else FONT)
        self.show_art()
        action, source = self.effective(self.sel)
        self.btn_name.configure(text=rs.label(self.model, self.sel + self.layer))
        self.action_lbl.configure(text=rs.pretty(action),
                                  style='PopBigOn.TLabel' if action != self.buttons[self.sel][1] else 'PopBig.TLabel')
        self.source_lbl.configure(text=source)
        if not self.recording:
            self.mode_var.set('mouse' if action.startswith('mouse:') or action == 'hypershift' else
                              'dpi' if action.startswith('dpi:') else 'key')
        self.show_mode()

    def show_mode(self):
        """Fill the panel's one input area for the chosen kind of action."""
        self.stop_record()
        for w in (self.rec_btn, self.pick_box, self.locked_lbl):
            w.pack_forget()
        if self.current == 'default':
            return self.locked_lbl.pack(anchor='w')
        mode = self.mode_var.get()
        if mode == 'key':
            return self.rec_btn.pack(fill='both', expand=True)
        self.pick_items = DPI_CHOICES if mode == 'dpi' else MOUSE_CHOICES + (
            ['hypershift'] if self.hs_ok() and not self.layer else [])  # the key lives on Standard
        self.pick_box['values'] = [rs.pretty(a) for a in self.pick_items]
        current = self.effective(self.sel)[0]
        self.pick_box.set(rs.pretty(current) if current in self.pick_items else 'Choose…')
        self.pick_box.pack(fill='x', pady=(8, 0))

    def select(self, b):
        if b not in self.editable or self.layer and self.hs_key(b):  # the editor only opens for a button that can be changed
            return self.locked(b)
        self.stop_record()
        self.sel = b
        self.redraw()
        self.open_popover()

    def step_sel(self, step):
        """Arrow keys on the picture: the next changeable button."""
        ids = [b for b in self.editable if b in self.buttons and not (self.layer and self.hs_key(b))]
        if ids:
            self.select(ids[((ids.index(self.sel) if self.sel in ids else -1) + step) % len(ids)])

    def locked(self, b):
        if self.layer and self.hs_key(b):
            return self.set_status(f'{self.buttons[b][0]} is your HyperShift key. Change it on Standard.')
        self.set_status('Left click is locked so you can always click.' if b == 1 else
                        f'{self.buttons[b][0]} can\'t be changed on this mouse: it didn\'t answer with its factory '
                        'setting. Reset the mouse to factory settings in Razer Synapse to unlock it.')

    # ---------- editing (every change saves straight away) ----------
    def set_action(self, b, action):
        if self.current == 'default':
            return  # default stays factory
        key = str(b + self.layer)
        if action is None or action == self.buttons[b][1]:
            self.edit.pop(key, None)  # factory
        else:
            self.edit[key] = action
        self.save()
        self.redraw()

    def pick_action(self, _):
        i = self.pick_box.current()
        if i >= 0:
            self.set_action(self.sel, self.pick_items[i])

    def factory(self):
        self.set_action(self.sel, self.buttons[self.sel][1])

    def reset_all(self):
        if self.current == 'default':
            return
        self.edit = {}  # a profile stores only its changes from factory
        self.save()
        self.redraw()
        self.set_status(f'All buttons in "{self.shown(self.current)}" are back to factory.')

    def toggle_record(self):
        if self.recording:
            return self.stop_record()
        self.recording, self.held = True, []
        self.rec_btn.configure(text='Press a key or combo…', style='Rec.TButton')
        self.focus_set()  # keys go to the window, not to a focused button or field
        self.bind('<KeyPress>', self.on_key)
        self.bind('<KeyRelease>', self.on_key_up)

    def stop_record(self):
        if self.recording:
            self.recording = False
            self.unbind('<KeyPress>')
            self.unbind('<KeyRelease>')
            self.rec_btn.configure(text=REC_IDLE, style='Field.TButton')

    def on_key(self, e):
        mod = MOD_KEYSYMS.get(e.keysym)
        if mod:  # wait for the key that goes with it
            if mod not in self.held:
                self.held.append(mod)
            self.rec_btn.configure(text=rs.pretty(rs.combo(self.held, '…')))
            return 'break'
        key = VK_KEYS.get(e.keycode) or TK_KEYS.get(e.keysym)
        if key:
            self.record(rs.combo(self.held, key))
        else:
            self.stop_record()
            self.set_status(f'"{e.keysym}" can\'t be put on a mouse button yet.')
        return 'break'

    def on_key_up(self, e):
        # a modifier pressed and released with no other key: record that modifier as the key itself
        if self.recording and MOD_KEYSYMS.get(e.keysym) in self.held:
            others = [m for m in self.held if m != MOD_KEYSYMS[e.keysym]]
            self.record(rs.combo(others, TK_KEYS[e.keysym]) if others else TK_KEYS[e.keysym])
        return 'break'

    def record(self, action):
        self.stop_record()
        self.set_action(self.sel, action)

    # ---------- profiles ----------
    def on_pick_profile(self, _):
        name = self.profile_box.get()
        name = 'default' if name == 'Default' else name  # no other profile may be called that
        if name in self.names() and name != self.current:
            self.load_profile(name)
            self.refresh_list()

    def profile_menu(self):
        """The ⋯ menu next to the profile picker. Default only offers New and Import."""
        own = self.current != 'default'
        self.popup(self.profile_box, [
            ('New profile', self.new, True), ('Rename', self.start_rename, own), ('Duplicate', self.duplicate, own),
            ('Export…', self.export_profile, own), ('Import…', self.import_profiles, True), None,
            ('Reset all buttons', self.reset_all, own), ('Delete', self.delete, own)])

    def mouse_menu(self):
        shown = self.model['pids'][0]
        self.popup(self.mouse_btn, [(name, lambda pid=pid: self.on_pick_mouse(pid), True, pid == shown)
                                    for pid, name in self._mice])

    def popup(self, under, items):
        """Rounded drop-down menu under a widget. items: (text, command, enabled[, picked]), or None for a divider.
        Closes on a pick, Esc, or a click anywhere else."""
        if self._just_closed(under):  # the click on its own button that just closed it
            return
        k = self.k
        top = tk.Toplevel(self, bg=PANEL, padx=round(4 * k), pady=round(4 * k))
        top.overrideredirect(True)
        top.attributes('-topmost', True)
        for item in items:
            if item is None:
                tk.Frame(top, height=1, bg=LINE).pack(fill='x', padx=round(8 * k), pady=round(4 * k))
                continue
            text, cmd, on, picked = (*item, False)[:4]
            b = ttk.Button(top, text=text, style='On.Menu.TButton' if picked else 'Menu.TButton',
                           command=lambda c=cmd: (top.close(), c()))
            b.pack(fill='x')
            b.state(['!disabled'] if on else ['disabled'])
        top.update_idletasks()
        w = max(top.winfo_reqwidth(), under.winfo_width())
        x = min(under.winfo_rootx(), self.winfo_rootx() + self.winfo_width() - w)  # stay inside the window
        top.geometry(f'{w}x{top.winfo_reqheight()}+{x}+{under.winfo_rooty() + under.winfo_height() + round(4 * k)}')
        round_corners(top)
        self._transient(top, under)

    def _just_closed(self, opener):
        """True right after a click closed the pop-up this widget opens: that click shouldn't reopen it."""
        who, when = getattr(self, '_last_closed', (None, 0))
        return who is opener and time.monotonic() - when < 0.4

    def _transient(self, top, opener, on_close=None):
        """A pop-up card or menu closes on Esc, a click anywhere outside it, or switching to another program.
        Sets top.close() for its own buttons to use."""
        def close(_=None):
            if not top.winfo_exists():
                return
            top.destroy()
            self.unbind_all('<Button-1>')
            self._last_closed = (opener, time.monotonic())
            if on_close:
                on_close()

        # inside = the pop-up itself or one of its widgets ('.!toplevel2' is NOT inside '.!toplevel')
        inside = lambda w: str(w) == str(top) or str(w).startswith(str(top) + '.')

        def click(e):
            if not inside(e.widget):
                close()

        def gone():
            try:
                f = self.focus_get()
            except KeyError:  # focus in a widget Tk doesn't wrap, such as a combobox list
                f = None
            if not (f and inside(f)):
                close()
        top.close = close
        top.bind('<Escape>', close)
        top.bind('<FocusOut>', lambda e: top.after(1, gone))
        self.after_idle(lambda: top.winfo_exists() and self.bind_all('<Button-1>', click))  # not the click that opened it
        top.focus_force()

    def save(self):
        if self.current == 'default':
            return
        self.cfg['profiles'][self.current] = dict(sorted(self.edit.items(), key=lambda kv: int(kv[0])))
        self.write_cfg()
        on_mouse = self.cfg.get('active') == self.current
        self.saved_lbl.configure(text='Saved · apply to update the mouse' if on_mouse else 'Saved')
        self.after(2500, lambda: self.saved_lbl.winfo_exists() and self.saved_lbl.configure(text=''))

    def start_rename(self, _=None):
        """Edit the profile's name right over the header's profile picker. Enter keeps it, Esc cancels."""
        if self.current == 'default':
            return self.set_status('Default can\'t be renamed.')
        entry = ttk.Entry(self.head, style='Head.TEntry')
        entry.insert(0, self.current)
        entry.select_range(0, 'end')
        entry.place(in_=self.profile_box, x=0, y=0, relwidth=1, relheight=1)
        entry.focus_set()

        def finish(keep):
            if not entry.winfo_exists():
                return
            if keep and not self.rename(entry.get().strip()):
                return entry.focus_set()  # name not allowed: stay in the box, the status says why
            entry.destroy()
        entry.bind('<Return>', lambda e: finish(True))
        entry.bind('<Escape>', lambda e: finish(False))
        entry.bind('<FocusOut>', lambda e: finish(True))

    def rename(self, name):
        old = self.current
        if name == old:
            return True
        if not name or name.lower() == 'default':
            self.set_status('Pick a name other than "default".')
            return False
        if name in self.cfg['profiles']:
            self.set_status(f'A profile called "{self.shown(name)}" already exists.')
            return False
        # rebuild to keep list order
        self.cfg['profiles'] = {(name if k == old else k): v for k, v in self.cfg['profiles'].items()}
        if self.cfg.get('active') == old:
            self.cfg['active'] = name
        if self.base == old:
            self.base = name
        self.cfg['links'] = {exe: (name if p == old else p) for exe, p in self.cfg['links'].items()}
        self.current = name
        self.write_cfg()
        self.refresh_list()
        self.set_status(f'Renamed to "{self.shown(name)}".')
        return True

    def new(self):
        n = 1
        while f'Profile {n}' in self.cfg['profiles']:
            n += 1
        self.cfg['profiles'][f'Profile {n}'] = {}
        self.write_cfg()
        self.load_profile(f'Profile {n}')
        self.refresh_list()
        self.start_rename()  # type the real name straight away

    def delete(self):
        name = self.current
        if name == 'default' or not messagebox.askyesno('FreeRazer', f'Delete profile "{self.shown(name)}"?'):
            return
        del self.cfg['profiles'][name]
        if self.cfg.get('active') == name:
            self.cfg.pop('active')
        if self.base == name:
            self.base = 'default'
        self.cfg['links'] = {exe: p for exe, p in self.cfg['links'].items() if p != name}
        self.write_cfg()
        self.load_profile('default')
        self.refresh_list()
        self.set_status(f'Deleted "{self.shown(name)}".')

    def apply(self):
        if self.put_on_mouse(self.current) and self.current not in self.cfg['links'].values():
            self.base = self.current  # what auto-switch returns to after a game

    def put_on_mouse(self, name, why=''):
        # under the mouse's lock, so the Synapse put-back (background thread) can't write the old profile
        # back between this write and 'active' changing
        with self.mouse.lock:
            try:
                binding = self.resolved(name)
                self.mouse.write(binding)
            except (OSError, ValueError) as e:
                self.learned_hs()
                self.set_status(f'Could not put "{self.shown(name)}" on the mouse: {e}')
                return False
            self.learned_hs()
            self.cfg['active'] = name
        self.write_cfg()
        self.refresh_list()
        self.set_status(f'Mouse is on "{self.shown(name)}"{why}: {rs.describe(binding, self.model)}')
        return True

    def learned_hs(self):
        """Save whether a mouse turned out to have a HyperShift layer; hide the switch on one that hasn't."""
        if self.mouse.hs != self.cfg.get('hypershift', {}):
            self.cfg['hypershift'] = dict(self.mouse.hs)
            self.write_cfg()
            self.show_layer_row()
            self.redraw()

    # ---------- game profiles ----------
    def link_game(self):
        """Add a game; it starts on the profile you're viewing (or the first one), changeable in its row."""
        from tkinter import filedialog
        if not self.cfg['profiles']:
            return self.set_status('Make a profile first (⋯ menu > New profile), then add a game for it.')
        path = filedialog.askopenfilename(title='Pick the game', filetypes=[('Programs', '*.exe'), ('All files', '*.*')])
        if not path:
            return
        exe = os.path.basename(path).lower()
        prof = self.current if self.current in self.cfg['profiles'] else next(iter(self.cfg['profiles']))
        self.relink_game(exe, prof)

    def relink_game(self, exe, prof):
        self.cfg['links'][exe] = prof
        self.write_cfg()
        self.show_games()
        self.set_status(f'{exe} uses "{prof}".' +
                        ('' if self.auto_var.get() else ' Turn on Auto-switch to use it.'))

    def unlink_game(self, exe):
        self.cfg['links'].pop(exe, None)
        self.write_cfg()
        self.show_games()
        self.set_status(f'{exe} no longer switches profiles.')

    def toggle_auto(self):
        self.cfg['auto'] = self.auto_var.get()
        self.write_cfg()
        self.set_status('Auto-switch is on: linked games get their profile while the app runs.'
                        if self.cfg['auto'] else 'Auto-switch is off.')

    def poll_games(self):
        # scheduled first: a callback below can open a dialog that waits for an answer, and auto-switch must
        # keep running meanwhile
        self.after(500, self.poll_games)
        try:
            while True:  # results from background reads and DPI/polling writes (Tk must only be touched here)
                try:
                    self._q.get_nowait()()
                except queue.Empty:
                    break
            event = globals().get('SHOW_EVENT')
            if event and ctypes.windll.kernel32.WaitForSingleObject(event, 0) == 0:  # app was launched again
                self.show_window()
            exe = rs.foreground_exe() if self.cfg.get('auto') else None
            # ignore this window (and file pickers it opens) so editing doesn't switch profiles
            if exe and exe not in ('freerazer.exe', 'python.exe', 'pythonw.exe'):
                want = self.cfg['links'].get(exe, self.base)
                if want != 'default' and want not in self.cfg['profiles']:
                    want = 'default'
                if want != self.cfg.get('active') and want != getattr(self, '_failed', None):
                    why = f' for {exe}' if exe in self.cfg['links'] else ''
                    self._failed = None if self.put_on_mouse(want, why) else want
        except Exception:  # never let one bad turn stop auto-switch for good
            log_error('auto-switch')

    def read_mouse(self):
        try:
            if not self.model['verified']:
                self.confirm_buttons()
            # the HyperShift layer only once the mouse is known to have one: otherwise it may answer for the
            # normal buttons, which would never match a profile
            ids = [b for b in self.editable if not b & rs.HS or self.hs_ok(known=True)]
            on_mouse = {b: self.mouse.get_action(b) for b in ids}
        except OSError as e:
            self.set_status(f'Mouse not found: {e}')
            return
        if not self.editable:
            return self.set_status(f'No button on {self.model["name"]} answered with its factory setting, so buttons '
                                   'stay as they are. Reset the mouse to factory settings in Razer Synapse to unlock them.')
        def same(name):
            try:
                return {b: a for b, a in self.resolved(name).items() if b in on_mouse} == on_mouse
            except ValueError:  # a profile with an action the app can't use: it can't be what's on the mouse
                return False
        matches = [n for n in self.names() if same(n)]
        if not matches:
            self.set_status(f'The mouse has bindings that are not in any profile: {rs.describe(on_mouse, self.model)}')
            return
        active = self.cfg.get('active') if self.cfg.get('active') in matches else matches[0]
        if active != self.cfg.get('active'):
            self.cfg['active'] = active
            self.write_cfg()
            self.refresh_list()
        self.set_status(f'Mouse is on "{self.shown(active)}": {rs.describe(on_mouse, self.model)}')

    # ---------- battery, DPI and staying connected ----------
    def refresh_device(self, repeat=True):
        """Every 30 s, read battery and DPI off the main thread (the reads take ~0.5 s).
        A failed read means the mouse was unplugged, switched off or asleep; the next one reconnects."""
        import threading
        gen = self._gen

        def work():
            try:
                synapse = synapse_running()
            except OSError:
                synapse = []
            self._q.put(lambda: self._synapse_done(synapse))
            try:
                found = rs.connected()
            except OSError:
                found = []
            self._q.put(lambda: self._mice_done(found))
            try:
                info = self.read_info()
            except OSError:  # unplugged, switched off or asleep
                info = None
            if info and synapse:
                try:
                    fixed = self.keep_settings(info)
                except OSError:
                    fixed = []
                except Exception:  # a bug here must not make the mouse look disconnected
                    log_error('putting settings back after Synapse')
                    fixed = []
                    self._q.put(self._problem)
                if fixed:  # Synapse's window pushes its own profile when it shows a mouse
                    time.sleep(0.4)
                    try:
                        info = self.read_info()
                    except OSError:
                        info = None
                    msg = f'Razer Synapse changed the {", ".join(fixed)}. FreeRazer put your settings back.'
                    self._q.put(lambda: self.set_status(msg))
            self._q.put(lambda: self._device_done(info) if gen == self._gen else None)
        threading.Thread(target=work, daemon=True).start()
        if repeat:
            self.after(30000, self.refresh_device)

    def _mice_done(self, found):
        """Show the mouse picker only while more than one Razer mouse is plugged in."""
        self._mice = found
        if len(found) < 2:
            return self.mouse_pick.pack_forget()
        names = dict(found)
        name = names.get(self.mouse.pid) or names.get(self.model['pids'][0], found[0][1])
        self.mouse_btn.configure(text=name + '   ')  # room before the arrow
        self.mouse_pick.pack(side='right', padx=(20, 0), before=self.dev_lbl)

    def confirm_buttons(self):
        """For a mouse not tested here: unlock the buttons that read back as their factory action, and remember
        them (a button changed later won't read back as factory again)."""
        name, got = self.mouse.confirm_buttons()  # the name of the mouse actually read, not the one shown
        if got != self.mouse.confirmed.get(name, set()):
            self.mouse.confirmed[name] = got
            self.cfg.setdefault('confirmed', {})[name] = sorted(got)
            self.write_cfg()
        if name == self.model['name'] and self.editable != self.editable_for(self.model):
            self.set_editable(self.editable_for(self.model))

    def set_editable(self, ids):
        """New set of changeable buttons: the picked button moves to one of them, the picture follows."""
        self.editable = ids
        if self.sel not in self.buttons or self.sel == 1 or (ids and self.sel not in ids):
            self.sel = (ids or [b for b in self.buttons if b != 1])[0]
        self._draw_mouse()  # clickable labels follow what can be changed
        self.load_profile(self.current)

    def _use_model(self, model):
        """A different mouse: rebuild the picture and button list for it."""
        if model['name'] == self.model['name']:
            return
        self.close_popover()
        self.model = model
        self.buttons = model['buttons']
        self.show_layer_row()
        self.set_editable(self.editable_for(model))
        w, h = self._min_size  # a mouse with More buttons needs a taller window
        h += round((self.extra_height() - H) * self.k)
        self.minsize(w, h)
        if self.winfo_height() < h:
            self.geometry(f'{max(w, self.winfo_width())}x{h}')

    def on_pick_mouse(self, pid):
        if pid == (self.mouse.pid or self.model['pids'][0]):  # already the picked one
            return
        self.cfg['mouse'] = pid
        self.write_cfg()
        self._gen += 1  # a refresh still running for the previous mouse is ignored when it lands
        self.mouse.choose(pid)
        self._use_model(rs.model_for(pid, dict(self._mice).get(pid, '')))  # even before it answers (it may be asleep)
        self._connected = False  # _device_done then redraws the buttons for the newly picked model
        self.dev_lbl.configure(text='Switching mouse…')
        self.refresh_device(repeat=False)

    def read_info(self):
        """Everything the Performance page shows, read off the mouse (background thread only)."""
        m = self.mouse
        return m.battery(), m.dpi(), m.polling(), m.model, m.power(), m.lighting()

    def keep_settings(self, info):
        """Runs on the background thread while Synapse is open. Tested with Synapse 4: it leaves the mouse alone
        in the background, but showing a mouse in its window writes Synapse's profile onto it. Whatever differs
        from the profile and settings chosen here is written back. Returns what was put back."""
        with self.mouse.lock:  # nothing else writes to the mouse until this compare-and-write is done
            return self._keep_settings(info)

    def _keep_settings(self, info):
        model = self.mouse.model
        if model['name'] != self.model['name']:  # the window shows another mouse; nothing here to compare with
            return []
        has = lambda f: rs.has(model, f)
        fixed = []
        want = self.resolved(self.cfg.get('active', 'default'))
        if any(self.mouse.get_action(b) != a for b, a in want.items()):
            self.mouse.write(want)
            fixed.append('buttons')
        _, dpi, hz, _, power, light = info
        keep = self.cfg.get('keep', {}).get(model['name'], {})
        if has('stages') and 'stages' in keep:
            # the whole stage table, not the current DPI: the DPI button changes which stage is in use, and that
            # is the user's choice, not Synapse's
            active, stages = self.mouse.dpi_stages()
            if [list(s) for s in stages] != keep['stages']:
                self.mouse.set_stages(active, keep['stages'])
                fixed.append('DPI')
        for key, now, label, write in (('dpi', not has('stages') and has('dpi') and dpi and dpi[0], 'DPI',
                                        self.mouse.set_dpi),
                                       ('hz', has('poll') and hz, 'polling rate', self.mouse.set_polling),
                                       ('sleep', has('sleep') and power and power[0], 'sleep time', self.mouse.set_sleep),
                                       ('low', has('low_power') and power and power[1], 'low power level',
                                        self.mouse.set_low_power)):
            if key in keep and now and now != keep[key]:
                write(keep[key])
                fixed.append(label)
        light = light if has('light') else None
        if light and light[0] is not None and 'light' in keep:  # None: the mouse can't say its effect
            effect, rgb = keep['light'][0], tuple(keep['light'][1])
            colored = effect in ('static', 'breathing')  # the other effects have no colour to compare
            if light[0] != effect or (colored and light[1] != rgb):
                self.mouse.set_lighting(effect, rgb)
                fixed.append('lighting')
        if light and 'bright' in keep and light[2] != keep['bright']:
            self.mouse.set_brightness(keep['bright'])
            fixed.append('brightness')
        return fixed

    def remember(self, key, value, model=None):
        """What you set here for this mouse, so it can be put back if Synapse changes it."""
        self.cfg.setdefault('keep', {}).setdefault((model or self.model)['name'], {})[key] = value
        self.write_cfg()

    def _synapse_done(self, names):
        was, self._synapse = self._synapse, names
        if names:
            self.warn_lbl.configure(text='Razer Synapse is running')
            self.warn_lbl.pack(side='right', padx=(0, 20), before=self.dev_lbl)
            if not was:
                self.set_status('Razer Synapse is running. If it changes this mouse (it does when you open the mouse '
                                'in its window), FreeRazer puts your settings back within 30 seconds.')
        else:
            self.warn_lbl.pack_forget()
            if was:
                self.set_status('Razer Synapse has closed.')

    def _device_done(self, info):
        if not self.winfo_exists():
            return
        if info is None:
            self.dev_lbl.configure(text='Mouse not connected', style='HeadMuted.TLabel')
            for w in (self.dpi_box, *self.poll_btns):
                w.state(['disabled'])
            self.dpi_scale.enable(False)
            for sc, _, _ in self.power.values():
                sc.enable(False)
            self.light_box.pack_forget()
            self.perf_note.configure(text='Connect the mouse (plug it in or switch it on) to change these.')
            if self._connected:
                self.set_status('Mouse disconnected. Profiles still save; they go on the mouse when it is back.')
            self._connected = False
            return
        battery, dpi, hz, model, power, light = info
        level = battery and battery[0]
        self.dev_lbl.configure(text='Connected' if battery is None else
                               f'Battery {level}%' + (' · charging' if battery[1] else ''), style='HeadMuted.TLabel')
        has = lambda f: rs.has(model, f)  # what the mouse database (or testing here) says FreeRazer may change
        x = dpi and dpi[0]
        self.dpi_rng = rs.dpi_range(model)
        self.dpi_box.configure(from_=self.dpi_rng[0], to=self.dpi_rng[1])
        rates = self.mouse.polling_rates()  # older mice stop at 1000 Hz
        for rb in self.poll_btns:
            rb.grid() if int(rb.cget('value')) in rates else rb.grid_remove()
            rb.state(['!disabled'] if has('poll') and hz else ['disabled'])
        self.dpi_box.state(['!disabled'] if has('dpi') and x else ['disabled'])
        self.dpi_scale.enable(bool(has('dpi') and x))
        self.perf_note.configure(text='' if model.get('features') else
                                 f'There is no settings data for {model["name"]} yet, so these stay as they are.')
        try:
            typing = self.focus_get() is self.dpi_box
        except KeyError:  # focus in a widget Tk doesn't wrap, such as an open dropdown list
            typing = False
        self._shown = {'dpi': self._shown.get('dpi'), 'hz': hz}
        if x and not typing:  # don't overwrite a number being typed; what's shown is what the box holds
            self.dpi_var.set(str(x))
            self.dpi_scale.set(dpi_to_slider(x, self.dpi_rng))
            self._shown['dpi'] = x
        self.poll_var.set(hz or 0)
        self.power['low'][0].set_range(*rs.low_power_range(model))
        for (key, (sc, _, _)), value in zip(self.power.items(), power or (None, None)):
            sc.enable(power is not None and has({'sleep': 'sleep', 'low': 'low_power'}[key]))
            if value is not None:
                sc.set(value)
                self.power_sliding(key, value)
                self._shown[key] = value
        if light and has('light'):
            effect, rgb, bright = light
            if effect in ('static', 'breathing'):  # other effects read back no colour; keep the last one
                self._rgb = rgb
            self.light_var.set(effect if effect in LIGHT_NAMES else '')  # unknown or 'other': none picked
            self.show_color()
            self.bright.set(bright)
            self.bright_val.configure(text=f'{bright}%')
            self._shown.update(light=(effect, self._rgb), bright=bright)
            self.light_box.pack(anchor='w', before=self.perf_note)
        else:
            self.light_box.pack_forget()
        self.about_lbl.configure(text=f'{model["name"]}' + ('' if model['verified'] else
                                 ' (settings from the mouse database)' if model.get('features') else ' (no settings data)')
                                 + f'. Profiles are saved in {os.path.dirname(CFG)}.')
        if self.tray:
            self.tray.title = 'FreeRazer' if battery is None else f'FreeRazer · battery {level}%'
        # back after being unplugged, or the mouse that answered isn't the one shown (another one was opened)
        if self._connected is False or model['name'] != self.model['name']:
            self._use_model(model)
            self._failed = None  # let auto-switch retry a profile that failed while it was away
            self.read_mouse()
        self._connected = True

    def dpi_changed(self):
        try:
            dpi = int(self.dpi_var.get())
        except ValueError:
            return self.dpi_var.set(str(self._shown.get('dpi', '')))
        if dpi == self._shown.get('dpi'):
            return
        lo, hi = self.dpi_rng
        if not lo <= dpi <= hi:
            self.dpi_var.set(str(self._shown.get('dpi', '')))
            return self.set_status(f'DPI must be {lo} to {hi}.')
        self._shown['dpi'] = dpi
        self.dpi_scale.set(dpi_to_slider(dpi, self.dpi_rng))
        self._send(lambda: self.mouse.set_dpi(dpi), f'DPI set to {dpi}.', ('dpi', dpi))

    def power_sliding(self, key, value):
        sc, val, unit = self.power[key]
        val.configure(text=f'{int(float(value))} {unit}' if unit == 'min' else f'{int(float(value))}%')

    def power_changed(self, key):
        v = int(self.power[key][0].get())
        if not self.power[key][0].on or v == self._shown.get(key):
            return
        self._shown[key] = v
        if key == 'sleep':
            self._send(lambda: self.mouse.set_sleep(v), f'The mouse now sleeps after {v} min idle.', (key, v))
        else:
            self._send(lambda: self.mouse.set_low_power(v), f'Low power mode now starts below {v}% battery.', (key, v))

    def light_changed(self):
        effect, rgb = self.light_var.get(), self._rgb
        if (effect, rgb) == self._shown.get('light'):
            return
        if effect not in LIGHT_NAMES:  # nothing picked (the mouse reported an effect FreeRazer doesn't offer)
            return
        self._shown['light'] = (effect, rgb)
        self._send(lambda: self.mouse.set_lighting(effect, rgb), f'Lighting set to {LIGHT_NAMES[effect]}.',
                   ('light', [effect, list(rgb)]))

    def show_color(self, rgb=None):
        """Swatch and preset ring follow `rgb` (default: the light's colour)."""
        rgb = rgb or self._rgb
        self._swatch_img = swatch_image(rgb, self.swatch.winfo_reqwidth(), self.swatch.winfo_reqheight())
        self.swatch.itemconfigure(self.swatch_item, image=self._swatch_img)
        self.dots.show(rgb)

    def open_picker(self):
        """Detailed colour picker: saturation/brightness square, hue bar, hex and R/G/B fields. The colour shows
        while you drag; the mouse gets it when you let go or press Enter."""
        import colorsys
        from PIL import Image, ImageDraw, ImageTk
        if getattr(self, '_picker', None) and self._picker.winfo_exists():  # clicking the chip again closes it
            return self._picker.close()
        if self._just_closed(self.swatch):
            return
        k, pad = self.k, round(14 * self.k)
        top = tk.Toplevel(self, bg=BG, padx=pad, pady=pad)
        top.overrideredirect(True)
        top.attributes('-topmost', True)
        W, H = round(260 * k), round(160 * k)
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in self._rgb))
        st = {'h': h * 359, 's': s, 'v': v}
        sv = tk.Canvas(top, width=W, height=H, bg=BG, highlightthickness=0, cursor='crosshair')
        sv.pack()
        sv_item = sv.create_image(0, 0, anchor='nw')
        top._ring = ring_image(k)
        knob = sv.create_image(0, 0, image=top._ring)
        hue = HueSlider(top, W, k)
        hue.pack(pady=(12, 0))
        row = tk.Frame(top, bg=BG)
        row.pack(fill='x', pady=(12, 0))
        hex_var = tk.StringVar()
        ttk.Label(row, text='Hex', style='Muted.TLabel').pack(side='left')
        hex_box = ttk.Entry(row, textvariable=hex_var, width=8)
        hex_box.pack(side='left', padx=(6, 12))
        chans = []
        for name in 'RGB':
            ttk.Label(row, text=name, style='Muted.TLabel').pack(side='left')
            var = tk.StringVar()
            box = ttk.Spinbox(row, textvariable=var, from_=0, to=255, width=3)
            box.pack(side='left', padx=(4, 8))
            chans.append((var, box))

        def rgb_now():
            return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(st['h'] / 359, st['s'], st['v']))

        def paint_square():
            base = Image.new('RGB', (W, H), hue_rgb(st['h']))
            across = Image.linear_gradient('L').rotate(-90).resize((W, H))  # white at the left, full colour at the right
            down = Image.linear_gradient('L').resize((W, H))  # black towards the bottom
            img = Image.composite(Image.new('RGB', (W, H), '#ffffff'), base, across)
            img = Image.composite(Image.new('RGB', (W, H), '#000000'), img, down)
            S = 4
            mask = Image.new('L', (W * S, H * S), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, W * S - 1, H * S - 1), radius=round(8 * k * S), fill=255)
            img.putalpha(mask.resize((W, H), Image.LANCZOS))
            top._square = ImageTk.PhotoImage(img)
            sv.itemconfigure(sv_item, image=top._square)

        def refresh(skip=None):
            rgb = rgb_now()
            sv.coords(knob, st['s'] * (W - 1), (1 - st['v']) * (H - 1))
            hue.set(st['h'])
            hue.show(rgb)
            if skip is not hex_box:
                hex_var.set(hex_color(rgb)[1:].upper())
            for (var, box), c in zip(chans, rgb):
                if skip is not box:
                    var.set(str(c))
            self.show_color(rgb)

        def from_rgb(rgb, skip=None):
            hh, ss, vv = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
            if ss > 0 and vv > 0:  # greys have no hue; keep the hue bar where it is
                st['h'] = hh * 359
            st['s'], st['v'] = ss, vv
            paint_square()
            refresh(skip)

        def drag_square(e):
            st['s'] = min(max(e.x / (W - 1), 0), 1)
            st['v'] = 1 - min(max(e.y / (H - 1), 0), 1)
            refresh()

        def drag_hue(value):
            st['h'] = value
            paint_square()
            refresh()

        def send(_=None):
            self.pick_color(rgb_now())

        def typed_hex(_=None):
            text = hex_var.get().strip().lstrip('#')
            if re.fullmatch(r'[0-9a-fA-F]{6}', text):
                from_rgb(tuple(int(text[i:i + 2], 16) for i in (0, 2, 4)))
                send()
            else:
                refresh()  # not a colour: show the current one again

        def typed_rgb(_=None):
            try:
                rgb = tuple(min(max(int(var.get()), 0), 255) for var, _ in chans)
            except ValueError:
                return refresh()
            from_rgb(rgb)
            send()

        sv.bind('<Button-1>', drag_square)
        sv.bind('<B1-Motion>', drag_square)
        sv.bind('<ButtonRelease-1>', send)
        hue.command, hue.release = drag_hue, send
        hex_box.bind('<Return>', typed_hex)
        for var, box in chans:
            box.configure(command=typed_rgb)
            box.bind('<Return>', typed_rgb)
        paint_square()
        refresh()

        top.update_idletasks()
        x = min(self.swatch.winfo_rootx(), self.winfo_rootx() + self.winfo_width() - top.winfo_reqwidth())
        y = self.swatch.winfo_rooty() + self.swatch.winfo_height() + round(6 * k)
        if y + top.winfo_reqheight() > self.winfo_rooty() + self.winfo_height():  # no room below: open above
            y = self.swatch.winfo_rooty() - top.winfo_reqheight() - round(6 * k)
        top.geometry(f'+{x}+{y}')
        round_corners(top)
        self._picker = top
        self._transient(top, self.swatch, self.show_color)

    def pick_color(self, rgb):
        self._rgb = tuple(rgb)
        self.show_color()
        if self.light_var.get() not in ('static', 'breathing'):
            self.light_var.set('static')
        self.light_changed()

    def bright_changed(self):
        v = int(self.bright.get())
        if not self.bright.on or v == self._shown.get('bright'):
            return
        self._shown['bright'] = v
        self._send(lambda: self.mouse.set_brightness(v), f'Brightness set to {v}%.', ('bright', v))

    def dpi_sliding(self, value):
        """While the slider moves, only the number follows; the mouse is set when it is let go."""
        self.dpi_var.set(str(slider_to_dpi(float(value), self.dpi_rng)))

    def poll_changed(self):
        hz = self.poll_var.get()
        if hz != self._shown.get('hz'):
            self._shown['hz'] = hz
            self._send(lambda: self.mouse.set_polling(hz), f'Polling rate set to {hz} Hz.', ('hz', hz))

    def _send(self, write, done, keep=None):
        """Send a setting off the main thread, then read back what the mouse reports. keep=(key, value): what
        to remember for the Synapse put-back, only once the mouse has taken it, and for the mouse it went to
        (for a DPI change on a mouse with stages, the whole stage table)."""
        import threading
        import time

        def work():
            try:
                with self.mouse.lock:
                    write()
                    model = self.mouse.model
                    kept = keep
                    if keep and keep[0] == 'dpi' and rs.has(model, 'stages'):
                        kept = ('stages', [list(s) for s in self.mouse.dpi_stages()[1]])
                time.sleep(0.4)  # polling-rate changes take ~0.3 s to show up
                info = self.read_info()
                self._q.put(lambda: (kept and self.remember(*kept, model=model), self._device_done(info),
                                     self.set_status(done)))
            except (OSError, ValueError) as e:
                msg = f'Could not change it: {e}'; self._q.put(lambda: self.set_status(msg))
        threading.Thread(target=work, daemon=True).start()

    # ---------- mouse database (devices.json in the repo) ----------
    def show_db(self):
        v = str(self.db['version']) if self.db else ''
        self.db_lbl.configure(text=f'{len(rs.DB)} mice · from {v[:4]}-{v[4:6]}-{v[6:8]}' if self.db else 'Not loaded')

    def copy_report(self):
        """The read-only probe report (razer_switch.py probe) on the clipboard, for a GitHub issue. Runs in the
        background under the mouse's lock, so the app's own reads can't interleave with it."""
        import threading
        self.report_btn.state(['disabled'])
        self.set_status('Reading the mouse for the report (about 10 seconds)…')

        def work():
            try:
                with self.mouse.lock:
                    text = f'FreeRazer {APP_VERSION}\n' + rs.probe_report()
                self._q.put(lambda: done(text))
            except Exception as e:  # a report is optional: say what went wrong, never crash
                log_error('mouse report')
                self._q.put(lambda: done(None, e))

        def done(text, e=None):
            self.report_btn.state(['!disabled'])
            if text is None:
                return self.set_status(f'Could not make the report: {e}')
            self.clipboard_clear()
            self.clipboard_append(text)
            self.set_status('Mouse report copied. Paste it into a new GitHub issue, with your mouse\'s name and its '
                            'buttons.')
        threading.Thread(target=work, daemon=True).start()

    def update_db(self, manual=True):
        """Download the newest mouse database from the repo; it is checked in full before it is used or saved.
        The daily check (manual=False) only says something when the database changed."""
        import threading
        if getattr(self, '_db_busy', False):  # one download at a time (a double click, or the daily check)
            return
        self._db_busy = True
        self.db_lbl.configure(text='Checking…')
        say = self.set_status if manual else lambda text: None
        have = self.db and self.db['version']

        def finish(then):
            self._db_busy = False
            then()

        def work():
            try:
                db = json.loads(_curl(DB_URL, timeout=30))
                rs.check_db(db)
                if have and db['version'] <= have:
                    return self._q.put(lambda: finish(lambda: (self.show_db(), say('The mouse database is up to date.'))))
                path = rs.db_paths()[1]
                with open(path + '.new', 'w', encoding='utf-8') as f:
                    json.dump(db, f)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(path + '.new', path)  # a half-written file never replaces a good one
                self._q.put(lambda: finish(lambda: self._db_done(db)))
            except (OSError, ValueError) as e:
                msg = f'Could not update the mouse database: {e}'
                self._q.put(lambda: finish(lambda: (self.show_db(), say(msg))))
        threading.Thread(target=work, daemon=True).start()

    def _db_done(self, db):
        before = len(rs.DB)
        rs.use_db(db)
        self.db = db
        self.show_db()
        self.mouse.choose(self.mouse.pid)  # reopened with the new data on the next read
        new = rs.model_for(self.model['pids'][0], self.model['name'])
        old = self.model['name']
        if new['name'] != old and not self.model['verified']:
            # the database names this mouse differently: what was confirmed and remembered for it moves along
            # (a button already remapped can't be confirmed again, so losing these would lock it for good)
            for key in ('confirmed', 'keep'):
                if old in self.cfg.get(key, {}) and new['name'] not in self.cfg[key]:
                    self.cfg[key][new['name']] = self.cfg[key].pop(old)
            if old in self.mouse.confirmed:
                self.mouse.confirmed.setdefault(new['name'], self.mouse.confirmed.pop(old))
            self.write_cfg()
        if new['name'] == old:
            self.model = new  # same mouse, maybe more settings
        else:
            self._use_model(new)
        self.refresh_device(repeat=False)
        added = len(rs.DB) - before
        self.set_status('Mouse database updated' + (f': {added} more {"mouse" if added == 1 else "mice"}.' if added > 0 else '.'))

    # ---------- updates (GitHub Releases) ----------
    def toggle_auto_update(self):
        self.cfg['auto_update'] = self.auto_update_var.get()
        self.write_cfg()

    def check_updates(self, manual=False):
        """Automatic checks run every 6 h but ask GitHub at most once a day; a manual check always asks.
        Nothing is downloaded until you say yes to the pop-up."""
        import threading
        if not manual:
            self.after(6 * 3600_000, self.check_updates)
            if not self.cfg.get('auto_update', True) or time.time() - self.cfg.get('update_checked', 0) < 86400:
                return
            self.update_db(manual=False)  # new mice from the weekly database rebuild, once a day with the app check
        self.update_lbl.configure(text='Checking…')

        def work():
            try:
                tag, assets, notes = latest_release()
                if version_tuple(tag) <= version_tuple(APP_VERSION):
                    return self._q.put(lambda: self._update_checked(f'Version {APP_VERSION} · up to date', manual,
                                                                    uptodate=True))
                self._q.put(lambda: self._update_available(tag, assets, notes, manual))
            except (OSError, ValueError, KeyError) as e:
                msg = f'Could not check for updates: {e}'
                self._q.put(lambda: self._update_checked(f'Version {APP_VERSION}', manual, msg))
        threading.Thread(target=work, daemon=True).start()

    def installed(self):
        """Updates replace the installed copy only; a copy run from elsewhere (or as a script) just reports them."""
        return getattr(sys, 'frozen', False) and os.path.normcase(os.path.dirname(sys.executable)) == os.path.normcase(INSTALL_DIR)

    def _update_checked(self, text, manual, error=None, uptodate=False):
        self.cfg['update_checked'] = time.time()
        self.write_cfg()
        self.update_lbl.configure(text=text)
        if manual or error:
            self.set_status(error or text + '.')
        if manual and (error or uptodate):  # a check started from the tray needs the window to show the answer
            self.show_window()
            if error:
                messagebox.showwarning('FreeRazer', error, parent=self)
            elif uptodate:
                messagebox.showinfo('FreeRazer', f'You have the latest version ({APP_VERSION}).', parent=self)

    def _update_available(self, tag, assets, notes, manual):
        version = tag.lstrip('v')
        self._update_checked(f'Version {version} is available', manual)
        # never pop up mid-game (a linked game, or anything full screen): ask again in 5 min
        if not manual and (rs.foreground_exe() in self.cfg['links'] or fullscreen_foreground()):
            return self.after(300_000, lambda: self._update_available(tag, assets, notes, manual))
        if not self.installed():
            return self.set_status(f'Version {version} is available. Install it with FreeRazerSetup.exe.')
        if not manual and self.cfg.get('skip_version') == tag:  # you chose Skip this version; Check for updates still offers it
            return
        self.show_window()  # the pop-up needs a visible window, or it can open behind other apps
        notes = notes.strip()
        notes = f'\n\nWhat\'s new:\n{notes[:500]}{"…" if len(notes) > 500 else ""}' if notes else ''
        answer = self._ask_update(f'FreeRazer {version} is available. You have {APP_VERSION}.{notes}\n\n'
                                  'Update now? FreeRazer closes for a few seconds and reopens in the tray.')
        if answer == 'skip':
            self.cfg['skip_version'] = tag
            self.write_cfg()
            return self.set_status(f'You won\'t be asked about {version} again. Check for updates still offers it.')
        if answer != 'update':
            return self.set_status(f'Update to {version} skipped for now. You\'ll be asked again tomorrow, '
                                   'or use Check for updates.')
        self.update_lbl.configure(text=f'Downloading version {version}…')
        self.set_status(f'Downloading FreeRazer {version}…')
        import threading

        def work():
            try:
                path = download_update(tag, assets)
                self._q.put(lambda: self._install_update(tag, path))
            except (OSError, ValueError, KeyError) as e:
                msg = f'The update could not be downloaded: {e}'
                self._q.put(lambda: (self.set_status(msg), messagebox.showwarning('FreeRazer', msg, parent=self)))
        threading.Thread(target=work, daemon=True).start()

    def _ask_update(self, text):
        """Modal pop-up with Update now / Not now / Skip this version; returns 'update', 'later' or 'skip'."""
        dlg = tk.Toplevel(self, bg=BG, padx=PAGE_PAD, pady=PAGE_PAD)
        dlg.title('FreeRazer update')
        dlg.resizable(False, False)
        dlg.transient(self)
        answer = tk.StringVar(dlg, 'later')
        ttk.Label(dlg, text=text, wraplength=420, justify='left').pack(anchor='w')
        row = ttk.Frame(dlg)
        row.pack(anchor='e', pady=(16, 0))

        def pick(value):
            answer.set(value)
            dlg.destroy()
        ttk.Button(row, text='Skip this version', command=lambda: pick('skip')).pack(side='left')
        ttk.Button(row, text='Not now', command=lambda: pick('later')).pack(side='left', padx=8)
        ok = ttk.Button(row, text='Update now', style='Accent.TButton', command=lambda: pick('update'))
        ok.pack(side='left')
        dlg.bind('<Escape>', lambda e: pick('later'))
        dlg.protocol('WM_DELETE_WINDOW', lambda: pick('later'))
        dlg.update_idletasks()
        dlg.geometry(f'+{self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2}'
                     f'+{self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 3}')
        dlg.grab_set()
        dlg.lift()
        ok.focus_set()
        dlg.wait_window()
        return answer.get()

    def _install_update(self, tag, path):
        # the installer waits a moment so this app has quit (it holds the single-instance mutex the installer checks)
        subprocess.Popen(f'cmd /c ping -n 5 127.0.0.1 >nul & "{path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
                         creationflags=NO_WINDOW)
        if self.tray:
            self.tray.notify(f'Updating to version {tag.lstrip("v")}. It reopens in the tray when done.', 'FreeRazer')
        self.after(1500, self.quit_app)

    # ---------- profile tools ----------
    def duplicate(self):
        if self.current == 'default':
            return
        n, name = 2, f'{self.current} copy'
        while name in self.cfg['profiles']:
            name, n = f'{self.current} copy {n}', n + 1
        self.cfg['profiles'][name] = dict(self.cfg['profiles'][self.current])  # buttons only, not the game link
        self.write_cfg()
        self.load_profile(name)
        self.refresh_list()
        self.set_status(f'Made "{self.shown(name)}". Link a game to it if you want.')

    def export_profile(self):
        from tkinter import filedialog
        if self.current == 'default':
            return
        path = filedialog.asksaveasfilename(title=f'Export "{self.shown(self.current)}"', initialfile=f'{self.current}.json',
                                            defaultextension='.json', filetypes=[('FreeRazer profiles', '*.json')])
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'freerazer': 1, 'profiles': {self.current: self.cfg['profiles'][self.current]}}, f, indent=2)
        self.set_status(f'Exported "{self.shown(self.current)}" to {os.path.basename(path)}.')

    def import_profiles(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title='Import profiles', filetypes=[('FreeRazer profiles', '*.json')])
        if not path:
            return
        try:
            added = import_file(path, self.cfg['profiles'])
        except (OSError, ValueError) as e:
            return self.set_status(f'Could not import {os.path.basename(path)}: {e}')
        self.write_cfg()
        self.load_profile(added[-1])
        self.refresh_list()
        self.set_status(f'Imported {", ".join(added)}.')


def import_file(path, profiles):
    """Add the profiles in an exported file to `profiles`; returns the names used. Checks every button and
    action first (the file may come from anyone), and renames on a clash instead of overwriting."""
    with open(path, encoding='utf-8-sig') as f:  # -sig: files saved with a BOM too
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get('profiles'), dict) or not data['profiles']:
        raise ValueError('not a FreeRazer export')
    clean = []  # (name, binding); 'A' and 'A ' are both kept and get numbered below like any clash
    for name, binding in data['profiles'].items():
        if not isinstance(name, str) or not name.strip() or name.strip().lower() == 'default' or not isinstance(binding, dict):
            raise ValueError(f'bad profile {name!r}')
        own = {}
        for b, action in binding.items():
            # a button ID, or one + rs.HS for the HyperShift layer
            if not isinstance(b, str) or not b.isdigit() or not 2 <= int(b) & 0xFF or int(b) >= 2 * rs.HS:
                raise ValueError(f'"{name}" has a button that isn\'t one ({b!r}); left click can\'t be changed')
            # stored the way the mouse reads it back, so it compares equal to what is on the mouse;
            # rs.encode raises ValueError for anything that is not a known action
            own[str(int(b))] = 'default' if action == 'default' else rs.decode(*rs.encode(action))
        # buttons this mouse doesn't have are kept: profiles work across models and those are skipped there
        clean.append((name.strip()[:60], own))
    added = []
    for name, binding in clean:
        new, n = name, 2
        while new in profiles:
            new, n = f'{name} ({n})', n + 1
        profiles[new] = binding
        added.append(new)
    return added


INSTALL_DIR = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'FreeRazer')  # where freerazer.iss installs it
if __name__ == '__main__':
    # one copy only: two would fight over the mouse. A second launch signals the first to show itself.
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _mutex = k32.CreateMutexW(None, False, 'FreeRazerSingleInstance')
    already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    SHOW_EVENT = k32.CreateEventW(None, False, False, 'FreeRazerShow')  # auto-reset
    if already:
        k32.SetEvent(SHOW_EVENT)
        sys.exit()
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on scaled displays instead of blurry upscaling
    try:
        App().mainloop()
    except Exception:  # the exe has no console: without this a crash would leave no trace at all
        log_error('FreeRazer stopped')
        ctypes.windll.user32.MessageBoxW(None, f'FreeRazer stopped because of an error. The details were saved to:\n'
                                               f'{LOG}', 'FreeRazer', 0x10)
        sys.exit(1)
