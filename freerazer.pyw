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


def log_error(where):
    """Append the exception being handled to error.log, so a silent failure can still be found."""
    import time
    import traceback
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {where}\n{traceback.format_exc()}\n')
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
LABELS = {1: ('l', 50, -35, 70), 3: ('l', 95, -8, 65), 5: ('l', 136, -77, 136), 4: ('l', 184, -79, 184),
          9: ('r', 40, 5, 41), 2: ('r', 80, 35, 80), 10: ('r', 120, 4, 87), 0x60: ('r', 230, 9, 230)}


APP_VERSION = '1.0.0'  # build.ps1 reads this; bump it for every release
UPDATE_REPO = 'JSa25/freerazer'  # GitHub repo whose Releases carry the installer
SETUP_ASSET = 'FreeRazerSetup.exe'  # release asset, plus SETUP_ASSET + '.sha256'
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: helper programs run without flashing a console


TOKEN_FILE = os.path.join(os.path.dirname(CFG), 'update_token')  # only while the repo is private; never exported


def read_token():
    try:
        with open(TOKEN_FILE, encoding='utf-8-sig') as f:
            return f.read().strip()
    except OSError:
        return ''


def _curl(*args, timeout=60, token=''):
    """Windows' own curl does the HTTPS, so the exe doesn't have to bundle OpenSSL. The token goes in through
    stdin (curl's -K -), not the command line, so other programs can't read it from the process list; curl
    drops it on GitHub's redirect to its file storage."""
    config = f'header = "Authorization: Bearer {token}"\n' if token else ''
    r = subprocess.run(['curl.exe', '-fsSL', '--max-time', str(timeout), '-K', '-', *args], input=config.encode(),
                       capture_output=True, creationflags=NO_WINDOW)
    if r.returncode == 22 and not token:
        raise OSError('no release found (a private repo needs a token in Settings > Updates)')
    if r.returncode:
        raise OSError(f'could not reach GitHub (curl error {r.returncode})')
    return r.stdout


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r'\d+', v)[:3])


def latest_release(token=''):
    """(tag, {asset name: (public download url, API url)}, release notes) of the newest published release."""
    data = json.loads(_curl('-H', 'Accept: application/vnd.github+json',
                            f'https://api.github.com/repos/{UPDATE_REPO}/releases/latest', timeout=20, token=token))
    return (data.get('tag_name', ''), {a['name']: (a['browser_download_url'], a['url']) for a in data.get('assets', [])},
            data.get('body') or '')


def file_sha256(path):
    out = subprocess.run(['certutil', '-hashfile', path, 'SHA256'], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout.splitlines()
    return out[1].replace(' ', '').strip().lower() if len(out) > 1 else ''


def download_update(assets, token=''):
    """Download the new installer and check it against the release's published SHA-256; returns its path.
    Only this repo's own release links are accepted, so a tampered API answer can't point elsewhere.
    With a token (private repo) the files come through the API asset links, the only ones a token opens."""
    which, prefix = (1, f'https://api.github.com/repos/{UPDATE_REPO}/releases/assets/') if token else \
                    (0, f'https://github.com/{UPDATE_REPO}/releases/download/')
    exe, sums = assets.get(SETUP_ASSET), assets.get(SETUP_ASSET + '.sha256')
    exe_url, sum_url = exe and exe[which], sums and sums[which]
    if not (exe_url and sum_url and exe_url.startswith(prefix) and sum_url.startswith(prefix)):
        raise OSError('the release has no installer and checksum from this project')
    folder = os.path.join(os.environ.get('TEMP') or os.path.dirname(CFG), 'FreeRazerUpdate')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, SETUP_ASSET)
    raw = ('-H', 'Accept: application/octet-stream') if token else ()
    _curl(*raw, '-o', path, exe_url, timeout=300, token=token)
    expected = _curl(*raw, sum_url, timeout=30, token=token).decode('ascii', 'replace').split()[0].lower()
    if not re.fullmatch(r'[0-9a-f]{64}', expected) or file_sha256(path) != expected:
        os.remove(path)
        raise OSError('the download did not match its published checksum, so it was thrown away')
    return path


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
            if not isinstance(self.cfg, dict):
                raise ValueError('not a settings file')
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
        self.mouse = rs.Mouse()
        # shortcut: model is picked once at start (V4 Pro layout if no mouse is plugged in); restart after swapping mice
        self.model = rs.detect() or rs.DEVICES[0]
        self.buttons, self.editable = self.model['buttons'], rs.editable(self.model)
        migrate_startup()
        self.current, self.sel, self.edit, self.recording = 'default', 5, {}, False
        if self.sel not in self.editable:
            self.sel = self.editable[0]
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
        if self.startup_var.get():
            set_startup(True)  # keep the entry pointing here if the app was moved
        if '--tray' in sys.argv and self.tray:  # started with Windows: go straight to the tray
            self._told_tray = True
            self.withdraw()
        self.after(500, self.poll_games)
        self._connected, self._q = None, queue.Queue()  # background results, picked up by poll_games
        self.after(300, self.refresh_device)
        self.after(60_000, self.check_updates)
        if '--updated' in sys.argv and self.tray:  # started by the installer after an automatic update
            self.after(3000, lambda: self.tray.notify(f'Updated to version {APP_VERSION}.', 'FreeRazer'))

    # ---------- data ----------
    def names(self):
        return ['default', *self.cfg['profiles']]

    def own(self, name):
        return self.cfg['default'] if name == 'default' else self.cfg['profiles'][name]

    def resolved(self, name):
        return rs.resolve({}, None if name == 'default' else self.cfg["profiles"][name], self.model)

    def effective(self, b):
        """(action, where it comes from) for button b in the profile being edited."""
        if str(b) in self.edit and self.edit[str(b)] != 'default':
            return self.edit[str(b)], 'Changed in this profile'
        return self.buttons[b][1], 'Factory setting'

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

    def report_callback_exception(self, *_):
        log_error('error in the window')  # Tk calls this for exceptions in clicks and timers

    def _make_tray(self):
        import pystray
        from PIL import Image
        img = Image.open(os.path.join(getattr(sys, '_MEIPASS', HERE), 'icon.ico'))
        later = lambda f, *a: (lambda: self.after(0, f, *a))  # tray runs on its own thread; hand work to Tk
        profiles = pystray.Menu(lambda: [
            pystray.MenuItem(n, later(self.apply_from_tray, n), radio=True,
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
        tmp = CFG + '.tmp'  # write then swap, so a crash can't leave a half-written file
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.cfg, f, indent=2)
        os.replace(tmp, CFG)
        if getattr(self, 'tray', None):
            self.tray.update_menu()  # profile names, active profile or auto-switch may have changed

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
        self.profile_box = ttk.Combobox(hd, state='readonly', width=22)
        self.profile_box.pack(side='left', padx=(24, 2))
        self.profile_box.bind('<<ComboboxSelected>>', self.on_pick_profile)
        ttk.Button(hd, text='⋯', style='HeadLink.TButton', command=self.profile_menu).pack(side='left')
        self.state_lbl = ttk.Label(hd, style='HeadMuted.TLabel')
        self.state_lbl.pack(side='left', padx=(16, 12))
        self.apply_btn = ttk.Button(hd, text='Apply to mouse', style='Accent.TButton', command=self.apply)
        self.dev_lbl = ttk.Label(hd, style='HeadMuted.TLabel', text='Looking for the mouse…')
        self.dev_lbl.pack(side='right')
        self.warn_lbl = ttk.Label(hd, style='HeadWarn.TLabel')  # shown while Razer Synapse is running
        self._synapse = []
        self.menu = tk.Menu(self, tearoff=False, bg=PANEL, fg=FG, activebackground=SEL_FILL,
                            activeforeground=ACCENT, disabledforeground=DIM, borderwidth=0)
        for label, cmd in (('New profile', self.new), ('Rename', self.start_rename), ('Duplicate', self.duplicate),
                           ('Export…', self.export_profile), ('Import…', self.import_profiles), (None, None),
                           ('Reset all buttons', self.reset_all), ('Delete', self.delete)):
            self.menu.add_separator() if label is None else self.menu.add_command(label=label, command=cmd)

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
            self.canvas.bind(key, lambda e, s=step: self.select(self.editable[(self.editable.index(self.sel) + s) % len(self.editable)]))
        self._draw_mouse()
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
        # classic Scale: ttk's clam slider can't drop its outline, this one takes exact colours
        self.dpi_scale = tk.Scale(row, from_=0, to=1000, orient='horizontal', length=round(360 * k), showvalue=0,
                                  bd=0, highlightthickness=0, troughcolor=PANEL, bg=ACCENT, activebackground='#5fe84a',
                                  sliderrelief='flat', sliderlength=round(16 * k), width=round(10 * k),
                                  command=self.dpi_sliding)
        self.dpi_scale.pack(side='left')
        self.dpi_scale.bind('<ButtonRelease-1>', lambda e: self.dpi_changed())
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
        # only needed while the GitHub repo is private: a read-only token, kept on this PC
        row = ttk.Frame(pg)
        row.pack(anchor='w', pady=(8, 0))
        ttk.Label(row, text='Private repo token', style='Muted.TLabel').pack(side='left')
        self.token_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.token_var, show='•', width=36).pack(side='left', padx=(12, 8))
        ttk.Button(row, text='Save', command=self.save_token).pack(side='left')
        ttk.Button(row, text='Remove', style='Link.TButton', command=self.remove_token).pack(side='left', padx=(12, 0))
        self.token_lbl = ttk.Label(row, style='Muted.TLabel')
        self.token_lbl.pack(side='left', padx=(12, 0))
        self.token_lbl.configure(text='Saved' if read_token() else 'Not set')
        ttk.Label(pg, text='About', style='H2.TLabel').pack(anchor='w', pady=(32, 4))
        self.about_lbl = ttk.Label(pg, style='Muted.TLabel')
        self.about_lbl.pack(anchor='w')
        row = ttk.Frame(pg)
        row.pack(anchor='w', pady=(12, 0))
        ttk.Button(row, text='Open error log', command=self.open_log).pack(side='left')
        ttk.Button(row, text='Quit FreeRazer', command=self.quit_app).pack(side='left', padx=(8, 0))

        self.status = ttk.Label(self, style='Muted.TLabel')
        self.status.grid(row=4, column=0, sticky='w', padx=24, pady=(0, 16))
        self.show_page('buttons')

    def _build_popover(self, parent):
        """The button editor: a small card next to the clicked button, closed with Esc or a click elsewhere."""
        k = self.k
        self.pop = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=LEADER, highlightcolor=LEADER)
        inner = ttk.Frame(self.pop, style='Pop.TFrame', padding=16)
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
            x = cx + (x0 if LABELS[self.sel][0] == 'r' else x1 - pw)
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
        self.pages[key].tkraise()
        for name, (b, bar) in self.nav.items():
            b.configure(style='NavOn.TButton' if name == key else 'Nav.TButton')
            bar.configure(bg=ACCENT if name == key else BG)
        if key == 'games':
            self.show_games()

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
        self.labels, self._overlays = {}, {}
        self._draw_line_art()
        self._draw_labels({b: (CX + tx, ty) for b, (_, _, tx, ty) in LABELS.items() if b in self.buttons}, 125)
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
        return img.resize((round(W * self.k), round(H * self.k)), Image.LANCZOS)

    def show_art(self):
        # The full drawing is rendered once; each button's highlight is rendered once, cut down to that
        # button's corner of the picture, and laid on top. Clicking around then costs no drawing at all.
        from PIL import ImageTk
        if not getattr(self, '_base', None):
            self._base = ImageTk.PhotoImage(self._render(None))
            self.canvas.itemconfigure(self.art_item, image=self._base)
        if self.sel not in self._overlays:
            xs, ys = zip(*dict(self.hit)[self.sel])
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

    def _draw_labels(self, targets, reach):
        """Action text in two columns, each with a leader line to its button."""
        c, cx = self.canvas, CX
        for b, (side, y, _, _) in LABELS.items():
            if b not in self.buttons:
                continue
            s = -1 if side == 'l' else 1
            x_text, x_dot = cx + s * (reach + 53), cx + s * reach
            tx, ty = targets[b]
            lines = (c.create_line(cx + s * (reach + 45), y, x_dot, y, fill=LEADER), c.create_line(x_dot, y, tx, ty, fill=LEADER))
            dot = c.create_oval(x_dot - 2, y - 2, x_dot + 2, y + 2, fill=LEADER, outline=LEADER)
            text = c.create_text(x_text, y, anchor='e' if side == 'l' else 'w', font=FONT, tags=(f'b{b}',))
            self.labels[b] = (text, dot, lines)
            if b in self.editable:
                c.tag_bind(f'b{b}', '<Button-1>', lambda e, b=b: self.select(b))
            else:
                c.tag_bind(f'b{b}', '<Button-1>', lambda e: self.set_status('Left click is locked so you can always click.'))
        for item in c.find_withtag('all'):
            if c.type(item) not in ('text', 'image'):
                c.tag_raise(item)  # leader lines above the picture

    def on_canvas_click(self, e):
        self.canvas.focus_set()
        b = self.hit_test(e.x / self.k, e.y / self.k)
        if b in self.editable:
            self.select(b)
        elif b is not None:
            self.set_status('Left click is locked so you can always click.')
        elif not self.canvas.find_withtag('current'):  # empty space closes the editor
            self.close_popover()

    def set_status(self, text):
        self.status.configure(text=text)

    # ---------- showing ----------
    def refresh_list(self):
        """Header: the profile you're looking at, and whether it is the one on the mouse."""
        self.profile_box['values'] = self.names()
        self.profile_box.set(self.current)
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
        for b, (text, dot, lines) in self.labels.items():
            editable, sel = b in self.editable, b == self.sel
            action = self.effective(b)[0] if editable else self.buttons[b][1]
            # like Synapse: green = remapped, white = factory, dim = can't change
            color = DIM if not editable else ACCENT if action != self.buttons[b][1] else FG
            c.itemconfigure(text, text=rs.pretty(action), fill=color,
                            font=('Segoe UI Semibold', 10) if sel else FONT)
            lead = ACCENT if sel else LEADER
            for item in (*lines, dot):
                c.itemconfigure(item, fill=lead)
            c.itemconfigure(dot, outline=lead)
        self.show_art()
        action, source = self.effective(self.sel)
        self.btn_name.configure(text=self.buttons[self.sel][0])
        self.action_lbl.configure(text=rs.pretty(action),
                                  style='PopBigOn.TLabel' if action != self.buttons[self.sel][1] else 'PopBig.TLabel')
        self.source_lbl.configure(text=source)
        if not self.recording:
            self.mode_var.set('mouse' if action.startswith('mouse:') else 'dpi' if action.startswith('dpi:') else 'key')
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
        self.pick_items = MOUSE_CHOICES if mode == 'mouse' else DPI_CHOICES
        self.pick_box['values'] = [rs.pretty(a) for a in self.pick_items]
        current = self.effective(self.sel)[0]
        self.pick_box.set(rs.pretty(current) if current in self.pick_items else 'Choose…')
        self.pick_box.pack(fill='x', pady=(8, 0))

    def select(self, b):
        self.stop_record()
        self.sel = b
        self.redraw()
        self.open_popover()

    # ---------- editing (every change saves straight away) ----------
    def set_action(self, b, action):
        if self.current == 'default':
            return  # default stays factory
        if action is None or action == self.buttons[b][1]:
            self.edit.pop(str(b), None)  # factory
        else:
            self.edit[str(b)] = action
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
        self.set_status(f'All buttons in "{self.current}" are back to factory.')

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
        if name in self.names() and name != self.current:
            self.load_profile(name)
            self.refresh_list()

    def profile_menu(self):
        """The ⋯ menu next to the profile picker. Default only offers New and Import."""
        locked = self.current == 'default'
        for label in ('Rename', 'Duplicate', 'Export…', 'Reset all buttons', 'Delete'):
            self.menu.entryconfigure(label, state='disabled' if locked else 'normal')
        x = self.profile_box.winfo_rootx()
        y = self.profile_box.winfo_rooty() + self.profile_box.winfo_height()
        self.menu.tk_popup(x, y)

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
        entry = ttk.Entry(self.head)
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
            self.set_status(f'A profile called "{name}" already exists.')
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
        self.set_status(f'Renamed to "{name}".')
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
        if name == 'default' or not messagebox.askyesno('FreeRazer', f'Delete profile "{name}"?'):
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
        self.set_status(f'Deleted "{name}".')

    def apply(self):
        if self.put_on_mouse(self.current) and self.current not in self.cfg['links'].values():
            self.base = self.current  # what auto-switch returns to after a game
        if self._synapse:
            self.set_status(f'Applied "{self.current}", but Razer Synapse is running and may change it back.')

    def put_on_mouse(self, name, why=''):
        binding = self.resolved(name)
        try:
            self.mouse.write(binding)
        except OSError as e:
            self.set_status(f'Could not write to the mouse: {e}')
            return False
        self.cfg['active'] = name
        self.write_cfg()
        self.refresh_list()
        self.set_status(f'Mouse is on "{name}"{why}: {rs.describe(binding, self.model)}')
        return True

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
        try:
            while True:  # results from background reads and DPI/polling writes (Tk must only be touched here)
                try:
                    self._q.get_nowait()()
                except queue.Empty:
                    break
            event = globals().get('SHOW_EVENT')
            if event and ctypes.windll.kernel32.WaitForSingleObject(event, 0) == 0:  # app was launched again
                self.show_window()
            # paused while Synapse runs: two programs switching the same mouse would fight
            exe = rs.foreground_exe() if self.cfg.get('auto') and not self._synapse else None
            # ignore this window (and file pickers it opens) so editing doesn't switch profiles
            if exe and exe not in ('freerazer.exe', 'python.exe', 'pythonw.exe'):
                want = self.cfg['links'].get(exe, self.base)
                if want != 'default' and want not in self.cfg['profiles']:
                    want = 'default'
                if want != self.cfg.get('active') and want != getattr(self, '_failed', None):
                    why = f' for {exe}' if exe in self.cfg['links'] else ''
                    self._failed = None if self.put_on_mouse(want, why) else want
        finally:
            self.after(500, self.poll_games)

    def read_mouse(self):
        try:
            on_mouse = {b: self.mouse.get_action(b) for b in self.editable}
        except OSError as e:
            self.set_status(f'Mouse not found: {e}')
            return
        if not self.model['verified']:
            return self.set_status(f'{self.model["name"]} is read-only until it is added to the device table. '
                                   f'Run "razer_switch.py probe" and open an issue. Now: {rs.describe(on_mouse, self.model)}')
        matches = [n for n in self.names() if self.resolved(n) == on_mouse]
        if not matches:
            self.set_status(f'The mouse has bindings that are not in any profile: {rs.describe(on_mouse, self.model)}')
            return
        active = self.cfg.get('active') if self.cfg.get('active') in matches else matches[0]
        if active != self.cfg.get('active'):
            self.cfg['active'] = active
            self.write_cfg()
            self.refresh_list()
        self.set_status(f'Mouse is on "{active}": {rs.describe(on_mouse, self.model)}')

    # ---------- battery, DPI and staying connected ----------
    def refresh_device(self):
        """Every 30 s, read battery and DPI off the main thread (the reads take ~0.5 s).
        A failed read means the mouse was unplugged, switched off or asleep; the next one reconnects."""
        import threading

        def work():
            try:
                synapse = synapse_running()
            except OSError:
                synapse = []
            self._q.put(lambda: self._synapse_done(synapse))
            try:
                info = (self.mouse.battery(), self.mouse.dpi(), self.mouse.polling(), self.mouse.model)
            except (OSError, ValueError):
                info = None
            self._q.put(lambda: self._device_done(info))
        threading.Thread(target=work, daemon=True).start()
        self.after(30000, self.refresh_device)

    def _synapse_done(self, names):
        was, self._synapse = self._synapse, names
        if names:
            self.warn_lbl.configure(text='Razer Synapse is running · auto-switch paused')
            self.warn_lbl.pack(side='right', padx=(0, 20), before=self.dev_lbl)
            if not was:
                self.set_status('Razer Synapse is running and can undo changes made here. Quit Synapse '
                                '(its tray icon > Exit) for FreeRazer to work reliably.')
        else:
            self.warn_lbl.pack_forget()
            if was:
                self.set_status('Razer Synapse has closed. Auto-switch is running again.')

    def _device_done(self, info):
        if not self.winfo_exists():
            return
        if info is None:
            self.dev_lbl.configure(text='Mouse not connected', style='HeadMuted.TLabel')
            for w in (self.dpi_box, *self.poll_btns):
                w.state(['disabled'])
            self.dpi_scale.configure(state='disabled', bg=DIM)
            self.perf_note.configure(text='Connect the mouse (plug it in or switch it on) to change these.')
            if self._connected:
                self.set_status('Mouse disconnected. Profiles still save; they go on the mouse when it is back.')
            self._connected = False
            return
        (level, charging), (x, y), hz, model = info
        self.dev_lbl.configure(text=f'Battery {level}%' + (' · charging' if charging else ''), style='HeadMuted.TLabel')
        verified = model['verified']
        self.dpi_rng = rs.dpi_range(model)
        self.dpi_box.configure(from_=self.dpi_rng[0], to=self.dpi_rng[1])
        rates = self.mouse.polling_rates()  # older mice stop at 1000 Hz
        for rb in self.poll_btns:
            rb.grid() if int(rb.cget('value')) in rates else rb.grid_remove()
        for w in (self.dpi_box, *self.poll_btns):
            w.state(['!disabled'] if verified else ['disabled'])
        self.dpi_scale.configure(state='normal' if verified else 'disabled', bg=ACCENT if verified else DIM)
        self.perf_note.configure(text='' if verified else f'{model["name"]} is read-only until it is verified.')
        if self.focus_get() is not self.dpi_box:  # don't overwrite a number being typed
            self.dpi_var.set(str(x))
            self.dpi_scale.set(dpi_to_slider(x, self.dpi_rng))
        self.poll_var.set(hz or 0)
        self._shown = {'dpi': x, 'hz': hz}
        self.about_lbl.configure(text=f'{model["name"]}' + ('' if verified else ' (read-only, not verified yet)') +
                                 f'. Profiles are saved in {os.path.dirname(CFG)}.')
        if self.tray:
            self.tray.title = f'FreeRazer · battery {level}%'
        if self._connected is False:  # back after being unplugged
            if model['name'] != self.model['name']:  # a different mouse: rebuild the picture and button list for it
                self.model = model
                self.buttons, self.editable = model['buttons'], rs.editable(model)
                self.sel = self.sel if self.sel in self.editable else self.editable[0]
                self._draw_mouse()
                self.load_profile(self.current)
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
        self._send(lambda: self.mouse.set_dpi(dpi), f'DPI set to {dpi}.')

    def dpi_sliding(self, value):
        """While the slider moves, only the number follows; the mouse is set when it is let go."""
        self.dpi_var.set(str(slider_to_dpi(float(value), self.dpi_rng)))

    def poll_changed(self):
        hz = self.poll_var.get()
        if hz != self._shown.get('hz'):
            self._shown['hz'] = hz
            self._send(lambda: self.mouse.set_polling(hz), f'Polling rate set to {hz} Hz.')

    def _send(self, write, done):
        """Send a DPI or polling change off the main thread, then read back what the mouse reports."""
        import threading
        import time

        def work():
            try:
                write()
                time.sleep(0.4)  # polling-rate changes take ~0.3 s to show up
                info = (self.mouse.battery(), self.mouse.dpi(), self.mouse.polling(), self.mouse.model)
                self._q.put(lambda: (self._device_done(info), self.set_status(done)))
            except (OSError, ValueError) as e:
                msg = f'Could not change it: {e}'; self._q.put(lambda: self.set_status(msg))
        threading.Thread(target=work, daemon=True).start()

    # ---------- updates (GitHub Releases) ----------
    def save_token(self):
        token = self.token_var.get().strip()
        self.token_var.set('')  # never left on screen
        if not re.fullmatch(r'(github_pat_|ghp_)[A-Za-z0-9_]{20,255}', token):
            return self.set_status('That doesn\'t look like a GitHub token (they start with github_pat_).')
        with open(TOKEN_FILE, 'w', encoding='ascii') as f:
            f.write(token)
        self.token_lbl.configure(text='Saved')
        self.check_updates(manual=True)

    def remove_token(self):
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        self.token_lbl.configure(text='Not set')
        self.set_status('Token removed.')

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
        self.update_lbl.configure(text='Checking…')

        def work():
            try:
                tag, assets, notes = latest_release(read_token())
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
        if rs.foreground_exe() in self.cfg['links'] and not manual:  # never pop up mid-game: ask again in 5 min
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
                path = download_update(assets, read_token())
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
        self.set_status(f'Made "{name}". Link a game to it if you want.')

    def export_profile(self):
        from tkinter import filedialog
        if self.current == 'default':
            return
        path = filedialog.asksaveasfilename(title=f'Export "{self.current}"', initialfile=f'{self.current}.json',
                                            defaultextension='.json', filetypes=[('FreeRazer profiles', '*.json')])
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'freerazer': 1, 'profiles': {self.current: self.cfg['profiles'][self.current]}}, f, indent=2)
        self.set_status(f'Exported "{self.current}" to {os.path.basename(path)}.')

    def import_profiles(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title='Import profiles', filetypes=[('FreeRazer profiles', '*.json')])
        if not path:
            return
        try:
            added = import_file(path, self.cfg['profiles'], self.editable)
        except (OSError, ValueError) as e:
            return self.set_status(f'Could not import {os.path.basename(path)}: {e}')
        self.write_cfg()
        self.load_profile(added[-1])
        self.refresh_list()
        self.set_status(f'Imported {", ".join(added)}.')


def import_file(path, profiles, editable):
    """Add the profiles in an exported file to `profiles`; returns the names used. Checks every button and
    action first (the file may come from anyone), and renames on a clash instead of overwriting."""
    with open(path, encoding='utf-8-sig') as f:  # -sig: files saved with a BOM too
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get('profiles'), dict) or not data['profiles']:
        raise ValueError('not a FreeRazer export')
    clean = {}
    for name, binding in data['profiles'].items():
        if not isinstance(name, str) or not name.strip() or name.strip().lower() == 'default' or not isinstance(binding, dict):
            raise ValueError(f'bad profile {name!r}')
        for b, action in binding.items():
            if not str(b).isdigit() or int(b) not in editable:
                raise ValueError(f'"{name}" uses a button this mouse does not have ({b})')
            rs.encode(action)  # raises ValueError for anything that is not a known action
        clean[name.strip()[:60]] = {str(b): a for b, a in binding.items()}
    added = []
    for name, binding in clean.items():
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
    App().mainloop()
