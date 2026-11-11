"""Button bindings for Razer mice, without Synapse. Unofficial; not affiliated with Razer.

  py -3.13 razer_switch.py               list profiles
  py -3.13 razer_switch.py apply NAME    write a profile to the mouse (it stays until changed)
  py -3.13 razer_switch.py auto          switch by focused program (.exe profile names)
  py -3.13 razer_switch.py show          print what the mouse has on each button
  py -3.13 razer_switch.py probe         read-only report for adding a new mouse (paste it into an issue)
  py -3.13 razer_switch.py test          offline self-check
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import sys
import threading
import time

import hid

VID = 0x1532  # Razer
PROFILE = 0x01  # the only profile slot web Synapse wrote to

# One entry per model. Only 'verified' entries are ever written to, and only on the button IDs listed:
# on the V4 Pro, IDs outside these answer with leftover memory, so a wrong ID could write into it.
DEVICES = [
    {'name': 'Viper V4 Pro', 'pids': (0x00E6,),  # dongle and cable report the same PID
     'txn': 0x1F, 'verified': True, 'drawing': 'viper-v4-pro', 'low_power_max': 100,
     'buttons': {  # id: (label as Synapse names it, factory action)
         1: ('Left Click', 'mouse:left'),
         2: ('Right Click', 'mouse:right'),
         3: ('Scroll Click', 'mouse:middle'),
         5: ('Mouse Button 5', 'mouse:forward'),
         4: ('Mouse Button 4', 'mouse:back'),
         9: ('Scroll Up', 'mouse:scrollup'),
         10: ('Scroll Down', 'mouse:scrolldown'),
         0x60: ('DPI Button', 'dpi:cycleup'),
     }},
    # tested on the wireless dongle (0x007D); OpenRazer lists 0x007C for the cable, not tested here
    {'name': 'DeathAdder V2 Pro', 'pids': (0x007D,), 'txn': 0x1F, 'verified': True, 'drawing': 'generic',
     'dpi_max': 20000,  # OpenRazer's DPI_MAX for this model
     'led': 0x04,  # the logo; every effect below tested on this mouse 2026-11-10
     'buttons': {
         1: ('Left Click', 'mouse:left'),
         2: ('Right Click', 'mouse:right'),
         3: ('Scroll Click', 'mouse:middle'),
         5: ('Mouse Button 5', 'mouse:forward'),
         4: ('Mouse Button 4', 'mouse:back'),
         9: ('Scroll Up', 'mouse:scrollup'),
         10: ('Scroll Down', 'mouse:scrolldown'),
     }},
]
# transaction IDs tried, read-only, on a mouse not in DEVICES (0x11 is what web Synapse sent the V4 Pro)
TXN_GUESSES = (0x1F, 0x3F, 0xFF, 0x11)


def unknown_model(pid, name=''):
    """A Razer mouse not in DEVICES: read-only, showing the buttons every mouse has."""
    common = {b: v for b, v in DEVICES[0]['buttons'].items() if b in (1, 2, 3, 4, 5, 9, 10)}
    return {'name': name or f'Razer mouse {pid:#06x}', 'pids': (pid,), 'txn': None, 'verified': False,
            'drawing': 'generic', 'buttons': common}


def model_for(pid, name=''):
    return next((d for d in DEVICES if pid in d['pids']), None) or unknown_model(pid, name)


def editable(model):
    """Buttons a profile may change. Left click stays left click, so you can't lock yourself out."""
    return [b for b in model['buttons'] if b != 1]


def mice():
    """HID entries of Razer mice plugged in, known models first."""
    infos = hid.enumerate(VID)
    # a PID with a mouse interface (usage page 1, usage 2); skips Razer keyboards and headsets
    pids = {i['product_id'] for i in infos if (i['usage_page'], i['usage']) == (1, 2)}
    pids |= {p for d in DEVICES for p in d['pids']}
    infos = [i for i in infos if i['product_id'] in pids]
    return sorted(infos, key=lambda i: model_for(i['product_id'])['txn'] is None)


def detect():
    """Model of the first Razer mouse plugged in, without opening it; None if there is none."""
    infos = mice()
    return model_for(infos[0]['product_id'], infos[0]['product_string']) if infos else None

# action type 01: payload is the mouse button number, as the left/right/middle/scroll IDs report it
MOUSE = {'left': 1, 'right': 2, 'middle': 3, 'back': 4, 'forward': 5, 'scrollup': 9, 'scrolldown': 10}

# USB HID keyboard usage codes (action type 02)
KEYS = {chr(c): 0x04 + i for i, c in enumerate(range(ord('a'), ord('z') + 1))}
KEYS.update({str(n): 0x1E + i for i, n in enumerate([1, 2, 3, 4, 5, 6, 7, 8, 9, 0])})
KEYS.update({f'f{n}': 0x3A + n - 1 for n in range(1, 13)})
KEYS.update({f'f{n}': 0x68 + n - 13 for n in range(13, 25)})
KEYS.update({'enter': 0x28, 'esc': 0x29, 'backspace': 0x2A, 'tab': 0x2B, 'space': 0x2C,
             '-': 0x2D, '=': 0x2E, '[': 0x2F, ']': 0x30, '\\': 0x31, ';': 0x33, "'": 0x34,
             '`': 0x35, ',': 0x36, '.': 0x37, '/': 0x38, 'capslock': 0x39,
             'insert': 0x49, 'home': 0x4A, 'pageup': 0x4B, 'delete': 0x4C, 'end': 0x4D,
             'pagedown': 0x4E, 'right': 0x4F, 'left': 0x50, 'down': 0x51, 'up': 0x52,
             'ctrl': 0xE0, 'shift': 0xE1, 'alt': 0xE2, 'rctrl': 0xE4, 'rshift': 0xE5, 'ralt': 0xE6})
NAMES = {v: k for k, v in KEYS.items()}
# modifier byte before the key code, captured from web Synapse: Ctrl+5 -> 01, Shift+Alt+5 -> 06
MODS = {'ctrl': 0x01, 'shift': 0x02, 'alt': 0x04}

ACTIONS = [f'mouse:{m}' for m in MOUSE] + ['dpi:cycleup'] + list(KEYS)
_PRETTY = {'mouse:left': 'Left Click', 'mouse:right': 'Right Click', 'mouse:middle': 'Scroll Click',
           'mouse:back': 'Mouse Button 4', 'mouse:forward': 'Mouse Button 5', 'mouse:scrollup': 'Scroll Up',
           'mouse:scrolldown': 'Scroll Down', 'dpi:cycleup': 'Cycle Up Sensitivity Stages', 'pageup': 'Page Up',
           'pagedown': 'Page Down', 'capslock': 'Caps Lock', 'ctrl': 'Left Ctrl', 'shift': 'Left Shift',
           'alt': 'Left Alt', 'rctrl': 'Right Ctrl', 'rshift': 'Right Shift', 'ralt': 'Right Alt',
           'esc': 'Esc', 'up': 'Arrow Up', 'down': 'Arrow Down', 'left': 'Arrow Left', 'right': 'Arrow Right'}


def pretty(action):
    if '+' in action:  # key combo such as 'ctrl+5'
        *mods, key = action.split('+')
        return ' + '.join([m.title() for m in mods] + [pretty(key)])
    if action in _PRETTY:
        return _PRETTY[action]
    if action.startswith('raw:'):
        return 'Other (set elsewhere)'
    return action.upper() if len(action) == 1 or action[0] == 'f' and action[1:].isdigit() else action.title()


def encode(action):
    """action name -> (action type, payload bytes)"""
    if action.startswith('mouse:') and action[6:] in MOUSE:
        return 0x01, [MOUSE[action[6:]]]
    if action == 'dpi:cycleup':
        return 0x06, [0x06]  # as read back from the DPI button
    if action in KEYS:
        return 0x02, [0x00, KEYS[action]]  # 00 = no modifier keys
    *mods, key = action.split('+')
    if mods and key in KEYS and all(m in MODS for m in mods):
        return 0x02, [sum(MODS[m] for m in set(mods)), KEYS[key]]
    raise ValueError(f'unknown action {action!r}')


def combo(mods, key):
    """Action name for modifiers + key, in a fixed order: 'ctrl+shift+5'."""
    return '+'.join([m for m in MODS if m in mods] + [key])


def decode(kind, payload):
    if kind == 0x02 and len(payload) == 2 and payload[0] and payload[1] in NAMES \
            and not payload[0] & ~sum(MODS.values()):
        return combo([m for m, bit in MODS.items() if payload[0] & bit], NAMES[payload[1]])
    for action in ACTIONS:
        if encode(action) == (kind, list(payload)):
            return action
    return f'raw:{kind:02x}:{bytes(payload).hex()}'


# polling-rate codes, captured from web Synapse on the V4 Pro (set with 00/40, read with 00/C0)
POLL_HZ = {0x40: 125, 0x10: 500, 0x08: 1000, 0x04: 2000, 0x02: 4000, 0x01: 8000}
# older mice (DeathAdder V2 Pro) refuse 00/C0 and use 00/85 to read, 00/05 to set; codes as in OpenRazer, tested
POLL_HZ_CLASSIC = {0x08: 125, 0x02: 500, 0x01: 1000}
DPI_RANGE = (100, 50000)  # the range web Synapse offers for the V4 Pro
# besides button sets (02/0C), the only writes allowed, and only on verified models
SETTING_WRITES = {b'\x00\x40', b'\x00\x05', b'\x04\x06', b'\x07\x03', b'\x07\x01', b'\x0f\x02', b'\x0f\x04'}
# lighting (OpenRazer's extended matrix): 0F/02 sets the effect, 0F/04 the brightness; 0F/82 and 0F/84 read them
LIGHT_EFFECTS = {'off': 0x00, 'static': 0x01, 'breathing': 0x02, 'spectrum': 0x03}
# sleep when idle: 07/83 read, 07/03 set, seconds as 2 bytes (OpenRazer: 60-900; Synapse: 1-15 min)
SLEEP_MIN = (1, 15)
# low power mode: 07/81 read, 07/01 set, one byte out of 255 (the V4 Pro read 77 where Synapse showed 30%)
LOW_POWER_MIN = 5


def parse_stages(a):
    """04/86 arguments -> (active stage from 1, [(x, y), ...])."""
    count = min(a[2], 5)
    return a[1], [(a[3 + 7 * i + 1] << 8 | a[3 + 7 * i + 2], a[3 + 7 * i + 3] << 8 | a[3 + 7 * i + 4]) for i in range(count)]


def stages_packet(active, stages, txn):
    """04/06 as OpenRazer builds it: storage 01, active stage, count, then per stage its number from 0,
    x hi/lo, y hi/lo and 2 reserved bytes."""
    args = [0x01, active, len(stages)]
    for i, (x, y) in enumerate(stages):
        args += [i, x >> 8, x & 0xFF, y >> 8, y & 0xFF, 0, 0]
    return packet(0x04, 0x06, args, txn, size=0x26)


def dpi_range(model):
    return DPI_RANGE[0], model.get('dpi_max', DPI_RANGE[1])


def low_power_range(model):
    # web Synapse offers up to 100% on the V4 Pro; OpenRazer caps other mice at 25%
    return LOW_POWER_MIN, model.get('low_power_max', 25)


def percent_to_byte(p):
    return int(p * 255 / 100 + 0.5)


def byte_to_percent(b):
    return round(b * 100 / 255)


def packet(cls, cmd, args, txn, size=0x0A):
    p = bytearray(90)
    p[1], p[5], p[6], p[7] = txn, size, cls, cmd
    p[8:8 + len(args)] = bytes(args)
    for b in p[2:88]:
        p[88] ^= b
    return p


def read_packet(button, txn):
    return packet(0x02, 0x8C, [PROFILE, button, 0], txn)  # 0x8C: high bit set = read


def set_packet(button, action, txn):
    kind, payload = encode(action)
    # args: profile, button, hypershift (0 = off), action type, payload length, payload
    return packet(0x02, 0x0C, [PROFILE, button, 0x00, kind, len(payload), *payload], txn)


def resolve(default, own=None, model=DEVICES[0]):
    """Full binding {button: action}: factory, then the default profile, then this profile.
    Buttons the model doesn't have are left out, so one profile works across models."""
    buttons = model['buttons']
    out = {b: buttons[b][1] for b in editable(model)}
    for layer in (default, own or {}):
        for b, action in layer.items():
            b = int(b)
            if b == 1:
                raise ValueError('left click cannot be changed')
            if b in out:
                out[b] = buttons[b][1] if action == 'default' else action
                encode(out[b])
    return out


def transact(dev, pkt, tries=25):
    """Send a command and return the mouse's answer to it. Razer Synapse streams lighting frames (0F/03) to
    RGB mice over the same report, so an answer can belong to Synapse's command instead (seen on the
    DeathAdder V2 Pro, about 2 in 3 reads). Those are thrown away and the command is sent again; every
    command FreeRazer sends reads or sets a fixed value, so sending it twice is harmless."""
    timed_out = None
    for _ in range(tries):
        dev.send_feature_report(b'\x00' + bytes(pkt))
        for _ in range(20):
            time.sleep(0.02)
            r = bytes(dev.get_feature_report(0, 91))[1:]  # drop report ID
            if r[0] != 0x01:  # 01 = busy, 02 = ok
                break
        if r[6:8] == bytes(pkt[6:8]):  # the answer echoes our command class and id
            if r[0] != 0x04:
                return r
            # 04 = no answer from the mouse in time: asleep, or the wireless link busy with Synapse's frames
            timed_out = r
    if timed_out:
        return timed_out
    raise OSError('another program (Razer Synapse?) kept talking to the mouse; try again')


class Mouse:
    def __init__(self):
        self.dev, self.model, self.txn = None, None, None
        self.poll_table = None  # POLL_HZ or POLL_HZ_CLASSIC, whichever this mouse answered to
        self.lock = threading.RLock()  # the app reads battery/DPI on a background thread while writes happen on the main one

    def connect(self):
        with self.lock:
            self._connect()

    def _connect(self):
        if self.dev:
            return
        for info in mice():
            model = model_for(info['product_id'], info['product_string'])
            for txn in (model['txn'],) if model['txn'] else TXN_GUESSES:
                d = hid.device()
                try:
                    d.open_path(info['path'])
                    if transact(d, read_packet(1, txn))[0] == 0x02:
                        self.dev, self.model, self.txn, self.poll_table = d, model, txn, None
                        return
                except OSError:
                    pass
                d.close()
        raise OSError('no Razer mouse found (is it plugged in and Synapse closed?)')

    def call(self, pkt):
        with self.lock:
            try:
                self._connect()
                # the one place packets go out: anything but a read must be a button set on a verified model
                if not pkt[7] & 0x80 and not (self.model['verified'] and (
                        (pkt[6:8] == b'\x02\x0c' and pkt[9] in editable(self.model)) or
                        (bytes(pkt[6:8]) in SETTING_WRITES and (pkt[6] != 0x0F or pkt[9] == self.model.get('led'))))):
                    raise ValueError(f'refusing to send command {pkt[6]:02x}/{pkt[7]:02x} to {self.model["name"]}')
                r = transact(self.dev, pkt)
            except OSError:
                if self.dev:
                    self.dev.close()
                self.dev = None  # unplugged or asleep: the next call looks for the mouse again
                raise
        if r[0] != 0x02:
            raise OSError(f'mouse rejected command, status {r[0]:#04x}')
        return r

    def get_action(self, button):
        self.connect()
        r = self.call(read_packet(button, self.txn))
        return decode(r[11], r[13:13 + r[12]])

    def set_action(self, button, action):
        self.connect()
        if not self.model['verified']:
            raise OSError(f'{self.model["name"]} is not supported for changes yet (read-only); '
                          'run "probe" and open an issue to add it')
        if button not in editable(self.model):
            raise ValueError(f'button {button} cannot be changed on {self.model["name"]}')
        self.call(set_packet(button, action, self.txn))

    def write(self, binding):
        for b, action in binding.items():
            self.set_action(b, action)

    def read(self, cls, cmd, args=()):
        """Args part of the answer to a read-only query (command id has the 0x80 bit set)."""
        self.connect()
        return self.call(packet(cls, cmd, list(args), self.txn))[8:24]

    def battery(self):
        """(percent, charging). Read on the V4 Pro: 07/80 byte 1 is the level out of 255, 07/84 byte 1 is charging."""
        level = self.read(0x07, 0x80)[1]
        return round(level * 100 / 255), bool(self.read(0x07, 0x84)[1])

    def power(self):
        """(sleep after idle in minutes, low power mode below this battery %), or None if the mouse refuses."""
        try:
            a, b = self.read(0x07, 0x83), self.read(0x07, 0x81)
        except OSError as e:
            if 'rejected' not in str(e):
                raise
            return None
        return round((a[0] << 8 | a[1]) / 60), byte_to_percent(b[0])

    def set_sleep(self, minutes):
        if not SLEEP_MIN[0] <= int(minutes) <= SLEEP_MIN[1]:
            raise ValueError(f'sleep time must be {SLEEP_MIN[0]} to {SLEEP_MIN[1]} minutes')
        s = int(minutes) * 60
        self.connect()
        self.call(packet(0x07, 0x03, [s >> 8, s & 0xFF], self.txn, size=0x02))

    def set_low_power(self, percent):
        self.connect()
        lo, hi = low_power_range(self.model)
        if not lo <= int(percent) <= hi:
            raise ValueError(f'low power level must be {lo} to {hi}%')
        self.call(packet(0x07, 0x01, [percent_to_byte(int(percent))], self.txn, size=0x01))

    def dpi(self):
        """Current (x, y) DPI. Read on the V4 Pro: 04/85 with storage 01 answers 01, x hi/lo, y hi/lo."""
        a = self.read(0x04, 0x85, [0x01])
        return a[1] << 8 | a[2], a[3] << 8 | a[4]

    def dpi_stages(self):
        """(active stage number from 1, [(x, y), ...]). 04/86 answers storage, active, count, then 7 bytes per
        stage: stage number, x hi/lo, y hi/lo, 2 reserved (read on the V4 Pro with five stages set by Synapse)."""
        self.connect()
        return parse_stages(self.call(packet(0x04, 0x86, [0x01], self.txn, size=0x26))[8:8 + 0x26])

    def polling(self):
        """Polling rate in Hz, or None for a code we haven't seen. A change shows up ~0.3 s after it is set.
        Newer mice answer 00/C0 (the V4 Pro rejects 00/85); older ones reject 00/C0 and answer 00/85."""
        if self.poll_table is not POLL_HZ_CLASSIC:
            try:
                code = self.read(0x00, 0xC0, [0x01])[1]
                self.poll_table = POLL_HZ
                return POLL_HZ.get(code)
            except OSError as e:
                if 'rejected' not in str(e):  # unplugged, not refused
                    raise
        code = self.read(0x00, 0x85)[0]
        self.poll_table = POLL_HZ_CLASSIC
        return POLL_HZ_CLASSIC.get(code)

    def polling_rates(self):
        """The rates this mouse can be set to (the newer set until the first polling read)."""
        return sorted((self.poll_table or POLL_HZ).values())

    def set_polling(self, hz):
        self.connect()
        if self.poll_table is None:
            self.polling()
        code = {v: k for k, v in self.poll_table.items()}.get(hz)
        if code is None:
            raise ValueError(f'{hz} Hz is not one of {self.polling_rates()}')
        if self.poll_table is POLL_HZ:
            self.call(packet(0x00, 0x40, [0x01, code], self.txn, size=0x02))
        else:
            self.call(packet(0x00, 0x05, [code], self.txn, size=0x01))

    def set_dpi(self, dpi):
        """One DPI for both axes. With one stage this is what web Synapse sends; with several (the DPI button
        cycles through them) only the active stage changes and the others stay as they are."""
        self.connect()
        lo, hi = dpi_range(self.model)
        if not lo <= int(dpi) <= hi:
            raise ValueError(f'DPI must be {lo} to {hi}')
        active, stages = self.dpi_stages()
        if not 1 <= active <= len(stages):  # unreadable table: fall back to a single stage
            active, stages = 1, [(0, 0)]
        stages[active - 1] = (int(dpi), int(dpi))
        self.call(stages_packet(active, stages, self.txn))

    def lighting(self):
        """(effect name, (r, g, b), brightness %) of the model's LED, or None if it has none we know.
        0F/82 answers storage, led, effect, 2 effect bytes, colour count, r, g, b."""
        self.connect()
        led = self.model.get('led')
        if led is None:
            return None
        a = self.call(packet(0x0F, 0x82, [0x01, led], self.txn, size=0x0C))[8:]
        b = self.call(packet(0x0F, 0x84, [0x01, led], self.txn, size=0x03))[8:]
        effect = {v: k for k, v in LIGHT_EFFECTS.items()}.get(a[2], 'spectrum')
        return effect, tuple(a[6:9]), byte_to_percent(b[2])

    def set_lighting(self, effect, rgb=(0, 255, 0)):
        self.connect()
        led = self.model.get('led')
        if led is None or effect not in LIGHT_EFFECTS:
            raise ValueError(f'{self.model["name"]} has no {effect} lighting')
        args = [0x01, led, LIGHT_EFFECTS[effect]]
        if effect in ('static', 'breathing'):  # breathing's 1 = one colour
            args += [0, 0, 1, *rgb] if effect == 'static' else [1, 0, 1, *rgb]
        self.call(packet(0x0F, 0x02, args, self.txn, size=max(len(args), 6)))  # OpenRazer's sizes: 6 or 9

    def set_brightness(self, percent):
        self.connect()
        led = self.model.get('led')
        if led is None or not 0 <= int(percent) <= 100:
            raise ValueError('brightness must be 0 to 100%')
        self.call(packet(0x0F, 0x04, [0x01, led, percent_to_byte(int(percent))], self.txn, size=0x03))


def describe(binding, model=DEVICES[0]):
    buttons = model['buttons']
    changed = [f'{buttons[b][0]} = {pretty(a)}' for b, a in binding.items() if a != buttons[b][1]]
    return ', '.join(changed) or 'factory bindings'


APP_DIR = 'FreeRazer'
OLD_APP_DIR = 'MouseProfiles'  # this app's folder before it was renamed FreeRazer


def profiles_path(legacy_dir=None):
    """%APPDATA%\\FreeRazer\\profiles.json. On first run, copies over what an older version left: the whole
    %APPDATA%\\MouseProfiles folder (profiles, update token), or else a profiles.json next to the exe or
    script. The old copies are left in place as a backup."""
    appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
    folder = os.path.join(appdata, APP_DIR)
    path = os.path.join(folder, 'profiles.json')
    old_folder = os.path.join(appdata, OLD_APP_DIR)
    if not os.path.exists(path) and os.path.exists(os.path.join(old_folder, 'profiles.json')):
        shutil.copytree(old_folder, folder, dirs_exist_ok=True)
    if not os.path.exists(path):
        os.makedirs(folder, exist_ok=True)
        legacy_dir = legacy_dir or os.path.dirname(sys.executable if getattr(sys, 'frozen', False)
                                                   else os.path.abspath(__file__))
        old = os.path.join(legacy_dir, 'profiles.json')
        if os.path.exists(old):
            shutil.copy2(old, path)
        else:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'default': {}, 'profiles': {}, 'links': {}}, f, indent=2)
    return path


def load_profiles(model=DEVICES[0]):
    with open(profiles_path(), encoding='utf-8-sig') as f:
        cfg = json.load(f)
    default = cfg.get('default', {})
    return (resolve(default, None, model),
            {n.lower(): resolve(default, own, model) for n, own in cfg.get('profiles', {}).items()})


def list_profiles():
    model = detect() or DEVICES[0]
    default, games = load_profiles(model)
    for name, binding in {'default': default, **games}.items():
        print(f'{name}: {describe(binding, model)}')


def apply(name):
    m = Mouse()
    m.connect()
    default, games = load_profiles(m.model)
    binding = default if name.lower() == 'default' else games.get(name.lower())
    if binding is None:
        raise SystemExit(f'no profile {name!r}; have: default, {", ".join(games)}')
    m.write(binding)
    print(f'{name}: {describe(binding, m.model)}')


def foreground_exe():
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), ctypes.byref(pid))
    h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    buf, size = ctypes.create_unicode_buffer(260), wt.DWORD(260)
    ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    k32.CloseHandle(h)
    return os.path.basename(buf.value).lower() if ok else None


def run():
    mouse, applied, last_exe = Mouse(), None, None
    mouse.connect()
    default, games = load_profiles(mouse.model)
    print('running; Ctrl+C to stop')
    while True:
        exe = foreground_exe()
        # shortcut: polls focus twice a second (~0.5 s switch delay), use SetWinEventHook if that matters
        want = games.get(exe, default)
        if want != applied:
            try:
                mouse.write(want)
                applied = want
                print(f'{exe}: {describe(want, mouse.model)}')
            except OSError as e:
                if exe != last_exe:
                    print(f'{exe}: could not write ({e}); will retry')
        last_exe = exe
        time.sleep(0.5)


def show():
    m = Mouse()
    m.connect()
    print(f'{m.model["name"]}' + ('' if m.model['verified'] else ' (not verified: read-only)'))
    for b, (label, _) in m.model['buttons'].items():
        print(f'{label}: {pretty(m.get_action(b))}')


def probe(ids=range(1, 0x80)):
    """Read-only report for adding a mouse. Sends only button reads (class 02, id 8C)."""
    print('Razer HID devices:')
    infos = hid.enumerate(VID)
    for i in infos:
        print(f"  PID {i['product_id']:#06x} interface {i['interface_number']} usage {i['usage_page']:#06x}/"
              f"{i['usage']:#06x} {i['product_string']!r}")
    for pid in sorted({i['product_id'] for i in infos}):
        found = None
        for info in (i for i in infos if i['product_id'] == pid):
            for txn in TXN_GUESSES:
                d = hid.device()
                try:
                    d.open_path(info['path'])
                    if transact(d, read_packet(1, txn))[0] == 0x02:
                        found = d, txn, info['interface_number']
                        break
                except OSError:
                    pass
                d.close()
            if found:
                break
        if not found:
            print(f'\nPID {pid:#06x}: no answer to button reads')
            continue
        d, txn, iface = found
        known = model_for(pid)
        print(f'\nPID {pid:#06x}: answers on interface {iface} with transaction ID {txn:#04x}'
              f' (in device table: {known["name"] if known["txn"] else "no"})')
        print('  id   status type len payload        decoded   (unused IDs may show leftover memory)')
        try:
            for b in ids:
                r = transact(d, read_packet(b, txn))
                n = min(r[12], 77)
                shown = r[13:13 + min(n, 8)].hex(' ') + (' …' if n > 8 else '')
                print(f'  {b:#04x} {r[0]:02x}     {r[11]:02x}   {r[12]:02x}  {shown:<26}'
                      f'{decode(r[11], r[13:13 + n]) if r[0] == 0x02 and n <= 8 else ""}')
        finally:
            d.close()
    print('\nPaste this whole report into a new issue, and say which physical buttons your mouse has.')


class _FakeDev:
    """Stands in for the mouse in test(): records what was sent, answers 'ok'."""
    def __init__(self, refuse=()):
        self.sent, self.refuse = [], set(refuse)  # refuse: (class, command) pairs answered with status 05
        self.stray = 0  # how many of the next answers belong to another program's command

    def send_feature_report(self, data):
        self.sent.append(bytes(data[1:]))

    def get_feature_report(self, _id, _n):
        last = self.sent[-1] if self.sent else bytes(90)
        if self.stray:  # an answer to someone else's command, like Synapse's lighting frames
            self.stray -= 1
            return b'\x00\x02' + bytes(4) + b'\x08\x0f\x03' + bytes(82)
        refused = (last[6], last[7]) in self.refuse
        # status, then the command header echoed back (as the mouse does), arguments zero
        return b'\x00' + (b'\x05' if refused else b'\x02') + last[1:8] + bytes(82)

    def close(self):
        pass


def test():
    v4 = DEVICES[0]
    # web Synapse saving F7 on button 5 (it used transaction ID 0x11; 0x1f is accepted too)
    cap = set_packet(5, 'f7', 0x1F)
    assert cap[:15].hex(' ') == '00 1f 00 00 00 0a 02 0c 01 05 00 02 02 00 40'
    assert cap[88] == 0x40 and set_packet(5, 'f5', 0x1F)[88] == 0x3E
    assert set_packet(4, 'mouse:back', 0x1F)[8:14].hex(' ') == '01 04 00 01 01 04'
    # web Synapse saving Ctrl+5 and Shift+Alt+5 on button 5 (bytes 8-14 and checksum as captured)
    p = set_packet(5, 'ctrl+5', 0x1F)
    assert p[8:15].hex(' ') == '01 05 00 02 02 01 22' and p[88] == 0x23
    p = set_packet(5, 'shift+alt+5', 0x1F)
    assert p[8:15].hex(' ') == '01 05 00 02 02 06 22' and p[88] == 0x24
    assert decode(0x02, b'\x06\x22') == 'shift+alt+5' and pretty('ctrl+5') == 'Ctrl + 5'
    assert combo({'alt', 'ctrl'}, 'f1') == 'ctrl+alt+f1'
    # web Synapse setting 1000 Hz and 900 DPI (bytes 5 onward, as captured)
    assert packet(0x00, 0x40, [0x01, 0x08], 0x1F, size=0x02)[5:10].hex(' ') == '02 00 40 01 08'
    assert packet(0x04, 0x06, [1, 1, 1, 0, 0x03, 0x84, 0x03, 0x84], 0x1F)[5:16].hex(' ') == '0a 04 06 01 01 01 00 03 84 03 84'
    assert POLL_HZ[0x04] == 2000 and sorted(POLL_HZ.values()) == [125, 500, 1000, 2000, 4000, 8000]
    # bindings read back from the mouse decode to the expected actions
    assert decode(0x01, b'\x03') == 'mouse:middle' and decode(0x06, b'\x06') == 'dpi:cycleup'
    assert decode(0x02, b'\x00\x2c') == 'space' and decode(0x09, b'\x01').startswith('raw:')
    full = resolve({'5': 'f5'}, {'4': 'e', '5': 'default'})
    assert full[5] == 'mouse:forward' and full[4] == 'e' and full[3] == 'mouse:middle' and 1 not in full
    try:
        resolve({'1': 'f5'})
        raise AssertionError('left click must be locked')
    except ValueError:
        pass

    # device table
    pids = [p for d in DEVICES for p in d['pids']]
    assert len(pids) == len(set(pids)), 'a PID is in two entries'
    for d in DEVICES:
        assert d['buttons'].get(1, (0, 0))[1] == 'mouse:left', d['name']
        assert not d['verified'] or d['txn'], d['name']
        for b, (_, factory) in d['buttons'].items():
            encode(factory)
    assert model_for(0x00E6) is v4 and v4['verified'] and v4['txn'] == 0x1F
    assert set(v4['buttons']) == {1, 2, 3, 4, 5, 9, 10, 0x60}
    other = model_for(0x0BAD, 'Some Mouse')
    assert not other['verified'] and other['name'] == 'Some Mouse' and 0x60 not in other['buttons']
    # a profile made on one model applies to another without the buttons it lacks
    assert resolve({}, {'96': 'f5', '4': 'e'}, other) == {**resolve({}, None, other), 4: 'e'}

    # write guards, on a fake device so no mouse is touched
    m = Mouse()
    m.dev, m.model, m.txn = _FakeDev(), v4, 0x1F
    m.set_action(5, 'f7')
    assert m.dev.sent[-1] == bytes(cap)
    for bad in (lambda: m.set_action(1, 'f7'), lambda: m.set_action(6, 'f7'),
                lambda: m.call(packet(0x0F, 0x03, [], 0x1F)),  # any other write-type command (Synapse's lighting frame)
                lambda: m.call(packet(0x0F, 0x02, [1, 4, 0], 0x1F)),  # lighting on a model with no known LED
                lambda: m.set_lighting('off'),
                lambda: m.call(set_packet(0x61, 'f7', 0x1F))):  # set packet for an ID not in the entry
        n = len(m.dev.sent)
        try:
            bad()
            raise AssertionError('write was allowed')
        except ValueError:
            assert len(m.dev.sent) == n, 'sent before refusing'
    m.model = other
    try:
        m.set_action(5, 'f7')
        raise AssertionError('unverified model was written')
    except OSError:
        pass
    m.get_action(5)  # reads still work read-only
    assert all(p[7] & 0x80 for p in m.dev.sent[-1:])
    assert read_packet(0x60, 0x3F)[6:10].hex(' ') == '02 8c 01 60'

    # polling: newer mice are set with 00/40; older ones refuse 00/C0 and are set with 00/05 (DeathAdder V2 Pro)
    m.model, m.poll_table, m.dev = v4, None, _FakeDev()
    m.set_polling(500)
    assert m.dev.sent[-1][5:10].hex(' ') == '02 00 40 01 10' and m.polling_rates()[-1] == 8000
    da = model_for(0x007D)
    assert da['verified'] and set(da['buttons']) == {1, 2, 3, 4, 5, 9, 10}
    m.model, m.poll_table, m.dev = da, None, _FakeDev(refuse={(0x00, 0xC0)})
    m.set_polling(500)
    assert m.poll_table is POLL_HZ_CLASSIC and m.polling_rates() == [125, 500, 1000]
    assert m.dev.sent[-1][5:9].hex(' ') == '01 00 05 02'
    try:
        m.set_polling(8000)
        raise AssertionError('8000 Hz allowed on an older mouse')
    except ValueError:
        pass
    assert dpi_range(da) == (100, 20000) and dpi_range(v4) == DPI_RANGE

    # DPI stages, as read from the V4 Pro after Synapse set five (active: the third)
    five = bytes.fromhex('01 03 05 01 01 90 01 90 00 00 02 03 20 03 20 00 00 03 06 40 06 40 00 00 '
                         '04 0c 80 0c 80 00 00 05 19 00 19 00 00 00')
    assert parse_stages(five) == (3, [(400, 400), (800, 800), (1600, 1600), (3200, 3200), (6400, 6400)])
    p = stages_packet(3, [(400, 400), (800, 800), (1000, 1000)], 0x1F)
    assert p[5:8].hex(' ') == '26 04 06' and p[8:11].hex(' ') == '01 03 03' and p[25:32].hex(' ') == '02 03 e8 03 e8 00 00'
    assert stages_packet(1, [(900, 900)], 0x1F)[8:16].hex(' ') == '01 01 01 00 03 84 03 84'  # same args as web Synapse

    # answers to another program's command (Synapse's lighting frames) are skipped and the command resent
    m.model, m.dev = v4, _FakeDev()
    m.dev.stray = 3
    assert m.get_action(4) is not None and len(m.dev.sent) == 4
    m.dev.stray = 100
    try:
        m.get_action(4)
        raise AssertionError('a stray answer was taken as the mouse answer')
    except OSError:
        pass

    # power saving, values as read from the V4 Pro (5 min, 30%) and DeathAdder (5%)
    assert percent_to_byte(30) == 77 and byte_to_percent(77) == 30 and percent_to_byte(5) == 13 and byte_to_percent(13) == 5
    assert low_power_range(v4) == (5, 100) and low_power_range(da) == (5, 25)
    m.model, m.dev = da, _FakeDev()
    m.set_sleep(10)
    assert m.dev.sent[-1][5:10].hex(' ') == '02 07 03 02 58'
    m.set_low_power(20)
    assert m.dev.sent[-1][5:9].hex(' ') == '01 07 01 33'
    for bad in (lambda: m.set_sleep(16), lambda: m.set_low_power(30)):
        try:
            bad()
            raise AssertionError('out-of-range power setting allowed')
        except ValueError:
            pass

    # lighting, packets as sent to the DeathAdder V2 Pro logo in the 2026-11-10 test (each seen by eye)
    m.model, m.dev = da, _FakeDev()
    m.set_lighting('static', (255, 0, 0))
    assert m.dev.sent[-1][5:17].hex(' ') == '09 0f 02 01 04 01 00 00 01 ff 00 00'
    m.set_lighting('breathing', (255, 0, 0))
    assert m.dev.sent[-1][5:17].hex(' ') == '09 0f 02 01 04 02 01 00 01 ff 00 00'
    m.set_lighting('spectrum')
    assert m.dev.sent[-1][5:11].hex(' ') == '06 0f 02 01 04 03'
    m.set_brightness(33)
    assert m.dev.sent[-1][5:11].hex(' ') == '03 0f 04 01 04 54'
    assert m.lighting() is not None
    m.model = v4
    assert m.lighting() is None

    # profiles move to %APPDATA%: copied once from the old folder, never overwritten afterwards
    import tempfile
    saved = os.environ.get('APPDATA')
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['APPDATA'] = os.path.join(tmp, 'appdata')
        old = os.path.join(tmp, 'profiles.json')
        with open(old, 'w') as f:
            json.dump({'profiles': {'FM': {'4': 'space'}}}, f)
        path = profiles_path(tmp)
        assert json.load(open(path))['profiles'] == {'FM': {'4': 'space'}} and os.path.exists(old)
        with open(old, 'w') as f:
            json.dump({}, f)
        assert json.load(open(profiles_path(tmp)))['profiles'] == {'FM': {'4': 'space'}}
        empty = os.path.join(tmp, 'empty')
        os.makedirs(empty)
        os.environ['APPDATA'] = os.path.join(tmp, 'fresh')
        assert json.load(open(profiles_path(empty))) == {'default': {}, 'profiles': {}, 'links': {}}
    if saved is None:
        os.environ.pop('APPDATA')
    else:
        os.environ['APPDATA'] = saved
    print('self-check ok')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'apply' and len(sys.argv) > 2:
        apply(sys.argv[2])
    else:
        {'show': show, 'test': test, 'list': list_profiles, 'auto': run, 'probe': probe}.get(cmd, list_profiles)()
