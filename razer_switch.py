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

# Mice tested here, by hand. Every other mouse comes from the mouse database (devices.json, built from
# OpenRazer by tools/gen_devices.py): it gets the features OpenRazer sends the same commands for, and only the
# buttons that read back as their factory action on the mouse itself (see Mouse.confirm_buttons). Button IDs
# outside these answer with leftover memory on the V4 Pro, so a wrong ID could write into it.
ALL_FEATURES = ('battery', 'dpi', 'stages', 'poll', 'sleep', 'low_power', 'light')
DEVICES = [
    {'name': 'Viper V4 Pro', 'pids': (0x00E6,),  # dongle and cable report the same PID
     'txn': 0x1F, 'verified': True, 'drawing': 'viper-v4-pro', 'low_power_max': 100, 'hypershift': True,
     'features': {'battery', 'dpi', 'stages', 'poll', 'sleep', 'low_power'},
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
     'leds': [0x04],  # the logo; every effect tested on this mouse 2026-11-10
     'features': set(ALL_FEATURES),
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


COMMON_BUTTONS = (1, 2, 3, 4, 5, 9, 10)
# Buttons of database mice whose button IDs and factory actions were read off a real mouse in its factory state
# (by its owner, with the probe). They replace the common buttons; each still unlocks only when it reads back
# as its factory action (Mouse.confirm_buttons).
_BASIC = {1: ('Left Click', 'mouse:left'), 2: ('Right Click', 'mouse:right'), 3: ('Scroll Click', 'mouse:middle'),
          9: ('Scroll Up', 'mouse:scrollup'), 10: ('Scroll Down', 'mouse:scrolldown')}
BUTTON_LAYOUTS = {
    # Naga V2 HyperSpeed, GitHub issue 1: no IDs 4/5; the two thumb buttons switch DPI at factory settings, the
    # 12-button grid is 0x40-0x4B in the order printed on it (1 = front column, bottom)
    0x00B4: {**_BASIC, 0x0B: ('Top Thumb Button', 'raw:06:01'), 0x0C: ('Bottom Thumb Button', 'raw:06:02'),
             0x34: ('Tilt Left', 'raw:0e:09008e'), 0x35: ('Tilt Right', 'raw:0e:0a008e'),
             **{0x40 + i: (f'Side Button {i + 1}', key) for i, key in enumerate('1234567890-=')}},
}
# factory actions FreeRazer has no name for, exactly as a mouse above reads them back: only these raw values may
# be written (to put a button back to factory)
FACTORY_RAW = {'raw:06:01': 'DPI (factory)', 'raw:06:02': 'DPI (factory)',
               'raw:0e:09008e': 'Tilt (factory)', 'raw:0e:0a008e': 'Tilt (factory)'}
DB_FILE = 'devices.json'
DB = {}  # pid -> mouse database entry, see use_db
# commands the database may give a transaction ID for ('ccii': class, id)
DB_TXN_KEYS = {'0780', '0784', '0485', '0405', '0486', '0406', '0085', '0005', '00c0', '0040', '0783', '0703',
               '0781', '0701', '0f02', '0f84', '0f04'}
DB_LEDS = {0x01, 0x04, 0x05, 0x10, 0x11}  # scroll wheel, logo, backlight, right side, left side


def check_db(db):
    """The mouse database as {pid: entry}, or ValueError. It can come from the internet, so every field is
    checked; one bad entry rejects the whole file."""
    if not isinstance(db, dict) or not isinstance(db.get('version'), int) or not isinstance(db.get('mice'), list):
        raise ValueError('not a FreeRazer mouse database')
    out = {}
    is_int = lambda v, lo, hi: isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi
    unique = lambda v, ok: isinstance(v, list) and all(ok(x) for x in v) and len(set(v)) == len(v)
    for e in db['mice']:
        ok = (isinstance(e, dict) and set(e) <= {'pid', 'name', 'dpi_max', 'dpi_read_store', 'poll',
              'poll_again_txn', 'leds', 'features', 'txn'}
              and is_int(e.get('pid'), 1, 0xFFFF) and e.get('pid') not in out
              and isinstance(e.get('name'), str) and 0 < len(e['name']) <= 80
              and is_int(e.get('dpi_max', 100), 100, 100000) and is_int(e.get('dpi_read_store', 0), 0, 1)
              and e.get('poll', 'classic') in ('classic', 'v2') and is_int(e.get('poll_again_txn', 0), 0, 255)
              and unique(e.get('leds', []), lambda x: is_int(x, 0, 255) and x in DB_LEDS)
              and unique(e.get('features', []), lambda x: isinstance(x, str) and x in ALL_FEATURES)
              and isinstance(e.get('txn', {}), dict)
              and all(isinstance(k, str) and k in DB_TXN_KEYS and is_int(t, 0, 255) for k, t in e.get('txn', {}).items()))
        if not ok:
            raise ValueError(f'bad mouse database entry: {str(e)[:80]}')
        out[e['pid']] = e
    return out


def use_db(db):
    global DB
    DB = check_db(db)


def db_model(e):
    """A model built from a mouse database entry. Buttons: the ones nearly every mouse has; which of them can be
    changed is decided on the mouse itself (Mouse.confirm_buttons)."""
    common = {b: v for b, v in DEVICES[0]['buttons'].items() if b in COMMON_BUTTONS}
    m = {'name': e['name'].removeprefix('Razer '), 'pids': (e['pid'],), 'txn': None, 'verified': False,
         'drawing': 'generic', 'buttons': dict(BUTTON_LAYOUTS.get(e['pid'], common)),
         'layout': e['pid'] in BUTTON_LAYOUTS, 'features': set(e.get('features', [])),
         'cmd_txn': {k: v for k, v in e.get('txn', {}).items()}, 'leds': list(e.get('leds', []))}
    for key in ('dpi_max', 'dpi_read_store', 'poll', 'poll_again_txn'):
        if key in e:
            m[key] = e[key]
    if m.get('poll') == 'v2':
        m['poll_args'] = 0  # OpenRazer reads 00/C0 and sets 00/40 with 00 first (the V4 Pro, by Synapse: 01)
    return m


def unknown_model(pid, name=''):
    """A Razer mouse with no data: no features, only buttons confirmed on the mouse can change."""
    common = {b: v for b, v in DEVICES[0]['buttons'].items() if b in COMMON_BUTTONS}
    # named like db_model names it ('Razer Basilisk V3' -> 'Basilisk V3'), so what the app remembers per mouse
    # name still applies after a database update adds this mouse
    return {'name': (name or '').removeprefix('Razer ').strip() or f'Razer mouse {pid:#06x}', 'pids': (pid,),
            'txn': None, 'verified': False,
            'drawing': 'generic', 'buttons': common, 'features': set()}


LEARNED = {}  # model name -> {button ID: (name, factory action)}, taught in the app by pressing each button


def model_for(pid, name=''):
    m = (next((d for d in DEVICES if pid in d['pids']), None) or (db_model(DB[pid]) if pid in DB else None)
         or unknown_model(pid, name))
    learned = LEARNED.get(m['name'])
    return {**m, 'buttons': {**m['buttons'], **learned}} if learned else m


def match_press(actions, action):
    """Button IDs whose action (as read off the mouse: {ID: action}) is what Windows just saw. A tilt has no
    Windows key, so a sideways scroll ('tilt') matches any tilt action."""
    if action == 'tilt':
        return sorted(b for b, a in actions.items() if a.startswith('raw:0e:'))
    return sorted(b for b, a in actions.items() if a == action)


def has(model, feature):
    return feature in model.get('features', ())


HS = 0x100  # button ID + HS = that button on the HyperShift layer (byte 2 of 02/0C and 02/8C is the layer)


def editable(model):
    """Buttons a profile may change, and each of them on the HyperShift layer as ID + HS. Left click stays left
    click, so you can't lock yourself out."""
    ids = [b for b in model['buttons'] if b != 1]
    return ids + [b + HS for b in ids]


def factory(model, b):
    """Factory action of button b on either layer (the HyperShift layer starts as a copy of the standard one)."""
    return model['buttons'][b & 0xFF][1]


def label(model, b):
    return model['buttons'][b & 0xFF][0] + (' (HyperShift)' if b & HS else '')


def mice():
    """HID entries of Razer mice plugged in, known models first."""
    infos = hid.enumerate(VID)
    # a PID with a mouse interface (usage page 1, usage 2); skips Razer keyboards and headsets
    pids = {i['product_id'] for i in infos if (i['usage_page'], i['usage']) == (1, 2)}
    pids |= {p for d in DEVICES for p in d['pids']} | set(DB)
    infos = [i for i in infos if i['product_id'] in pids]
    return sorted(infos, key=lambda i: model_for(i['product_id'])['txn'] is None)


def connected():
    """[(pid, model name)] of the Razer mice plugged in, one per PID, in mice() order.
    shortcut: two mice of the same model share a PID and show once; tell them apart by HID path if that comes up."""
    out = {}
    for i in mice():
        out.setdefault(i['product_id'], model_for(i['product_id'], i['product_string'])['name'])
    return list(out.items())


def detect(pid=None):
    """Model of the chosen Razer mouse (else the first) plugged in, without opening it; None if there is none."""
    infos = mice()
    infos = [i for i in infos if i['product_id'] == pid] or infos
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

ACTIONS = [f'mouse:{m}' for m in MOUSE] + ['dpi:cycleup', 'hypershift'] + list(KEYS)
_PRETTY = {'hypershift': 'Razer HyperShift', 'mouse:left': 'Left Click', 'mouse:right': 'Right Click', 'mouse:middle': 'Scroll Click',
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
    if action in FACTORY_RAW:
        return FACTORY_RAW[action]
    if action.startswith('raw:'):
        return 'Other (set elsewhere)'
    return action.upper() if len(action) == 1 or action[0] == 'f' and action[1:].isdigit() else action.title()


def encode(action):
    """action name -> (action type, payload bytes); ValueError for anything else (profiles can be imported)"""
    if not isinstance(action, str):
        raise ValueError(f'unknown action {action!r}')
    if action.startswith('mouse:') and action[6:] in MOUSE:
        return 0x01, [MOUSE[action[6:]]]
    if action == 'dpi:cycleup':
        return 0x06, [0x06]  # as read back from the DPI button
    if action == 'hypershift':
        return 0x0C, [0x01]  # as read back after web Synapse made Mouse Button 5 the HyperShift key
    if action in FACTORY_RAW:
        _, kind, payload = action.split(':')
        return int(kind, 16), list(bytes.fromhex(payload))
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
# besides button sets (02/0C), the only writes allowed, each only on a model with that feature
SETTING_WRITES = {b'\x00\x40': 'poll', b'\x00\x05': 'poll', b'\x04\x06': 'stages', b'\x04\x05': 'dpi',
                  b'\x07\x03': 'sleep', b'\x07\x01': 'low_power', b'\x0f\x02': 'light', b'\x0f\x04': 'light'}
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
    return packet(0x02, 0x8C, [PROFILE, button & 0xFF, button >> 8], txn)  # 0x8C: high bit set = read


def set_packet(button, action, txn):
    kind, payload = encode(action)
    # args: profile, button, layer (0 standard, 1 HyperShift), action type, payload length, payload
    return packet(0x02, 0x0C, [PROFILE, button & 0xFF, button >> 8, kind, len(payload), *payload], txn)


def resolve(default, own=None, model=DEVICES[0]):
    """Full binding {button: action}: factory, then the default profile, then this profile.
    Buttons the model doesn't have are left out, so one profile works across models."""
    out = {b: factory(model, b) for b in editable(model)}
    for layer in (default, own or {}):
        for b, action in layer.items():
            b = int(b)
            if b & 0xFF == 1:
                raise ValueError('left click cannot be changed')
            if b in out:
                # written the way the mouse reads it back ('shift+ctrl+5' -> 'ctrl+shift+5'), so a profile
                # compares equal to what is on the mouse
                out[b] = factory(model, b) if action == 'default' else decode(*encode(action))
    # the HyperShift key is the HyperShift key on both layers (as Synapse leaves it); nothing else is
    for b, action in out.items():
        if action == 'hypershift' and b & HS:
            out[b] = factory(model, b)
    for b in [b for b in out if not b & HS and out[b] == 'hypershift']:
        out[b + HS] = 'hypershift'
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
            if len(r) < 90:
                raise OSError(f'short answer from the mouse ({len(r)} bytes)')
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


def _locked(method):
    """Run a Mouse method under its lock from start to finish. The app reads on a background thread while
    changes go out from others; without this a reconnect between two steps (to another mouse, or with the
    polling table reset) could pair one mouse's reading with another's write."""
    def run(self, *args, **kw):
        with self.lock:
            return method(self, *args, **kw)
    run.__doc__ = method.__doc__
    return run


class Mouse:
    def __init__(self):
        self.dev, self.model, self.txn = None, None, None
        self.poll_table = None  # POLL_HZ or POLL_HZ_CLASSIC, whichever this mouse answered to
        self.pid = None  # the mouse picked in the app when several are plugged in; None = the first found
        self.confirmed = {}  # model name: buttons of a mouse not tested here that read back as their factory action
        self.hs = {}  # model name: whether it has a HyperShift layer, once a HyperShift write showed it (see write)
        self.lock = threading.RLock()  # the app reads battery/DPI on a background thread while writes happen on the main one

    def has_hs(self):
        """True: this mouse has a HyperShift layer; False: it hasn't; None: not known yet."""
        return True if self.model.get('hypershift') else self.hs.get(self.model['name'])

    def writable(self):
        """Buttons that may be changed: all but left click on a mouse tested here, else the confirmed ones; on
        the HyperShift layer too unless the mouse turned out not to have one."""
        ids = [b for b in editable(self.model) if not (b & HS and self.has_hs() is False)]
        if self.model['verified']:
            return set(ids)
        return {b for b in ids if b & 0xFF in self.confirmed.get(self.model['name'], set())}

    @_locked
    def confirm_buttons(self):
        """(model name, buttons) for the mouse actually connected: the common buttons that read back as their
        factory action. A real button does; an ID that isn't one answers with leftover memory, which won't spell
        out exactly this. A button already changed (by FreeRazer or Synapse) won't match either, which is why
        the app remembers what was confirmed. Reads only."""
        self.connect()
        model = self.model
        known = self.confirmed.get(model['name'], set())
        got = {b for b in model['buttons'] if b != 1 and (b in COMMON_BUTTONS or model.get('layout')) and b not in known
               and self._try(lambda b=b: self.get_action(b)) == model['buttons'][b][1]} | known
        if self.model is not model:  # reconnected to another mouse part way: nothing here can be trusted
            raise OSError('the mouse changed while its buttons were being read')
        return model['name'], got

    def _try(self, read):
        """A read, or None if the mouse refuses that command."""
        try:
            return read()
        except OSError as e:
            if 'rejected' not in str(e):  # unplugged or asleep, not refused
                raise
            return None

    def choose(self, pid):
        """Talk to this mouse from now on (it is opened on the next call)."""
        with self.lock:
            if self.dev:
                self.dev.close()
            self.dev, self.pid = None, pid

    def connect(self):
        with self.lock:
            self._connect()

    def _connect(self):
        if self.dev:
            return
        found = mice()
        if self.pid in {i['product_id'] for i in found}:  # the picked one if it is plugged in, else whichever is
            found = [i for i in found if i['product_id'] == self.pid]
        for info in found:
            model = model_for(info['product_id'], info['product_string'])
            # shortcut: a mouse that answers no button read with any of these isn't opened at all, even if the
            # database has other features for it; add a fallback read if such a mouse turns up
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

    def call(self, pkt, txn=None):
        """Send one command. txn: a transaction ID for this packet only; otherwise the one the mouse database
        gives for this command, otherwise the mouse's own (the checksum doesn't cover that byte)."""
        with self.lock:
            try:
                self._connect()
                key = bytes(pkt[6:8])
                # the one place packets go out: anything but a read must be an allowed button or setting
                if not pkt[7] & 0x80 and not ((key == b'\x02\x0c' and pkt[9] + (pkt[10] << 8) in self.writable()) or (
                        key in SETTING_WRITES and has(self.model, SETTING_WRITES[key])
                        and (pkt[6] != 0x0F or pkt[9] in self.model.get('leds', ())))):
                    raise ValueError(f'refusing to send command {pkt[6]:02x}/{pkt[7]:02x} to {self.model["name"]}')
                pkt = bytearray(pkt)
                pkt[1] = txn if txn is not None else self.model.get('cmd_txn', {}).get(key.hex(), self.txn)
                r = transact(self.dev, pkt)
            except OSError:
                if self.dev:
                    self.dev.close()
                self.dev = None  # unplugged or asleep: the next call looks for the mouse again
                raise
        if r[0] in (0x01, 0x04):  # still busy, or no answer: asleep or out of range, not a refusal
            raise OSError(f'the mouse did not answer (status {r[0]:#04x}); is it asleep?')
        if r[0] != 0x02:
            raise OSError(f'mouse rejected command, status {r[0]:#04x}')
        return r

    @_locked
    def get_action(self, button):
        self.connect()
        r = self.call(read_packet(button, self.txn))
        return decode(r[11], r[13:13 + r[12]])

    @_locked
    def set_action(self, button, action):
        self.connect()
        if button not in self.writable():
            raise ValueError(f'button {button} cannot be changed on {self.model["name"]}')
        self.call(set_packet(button, action, self.txn))

    @_locked
    def write(self, binding):
        """Put a binding on the mouse. A mouse with no HyperShift layer may ignore the layer byte and take a
        HyperShift write as a normal one, so until a mouse is known to have the layer, only HyperShift buttons
        that differ from their normal action are sent, and the normal buttons are read back afterwards: if they
        changed, they are put back and the mouse is remembered as having no HyperShift."""
        self.connect()
        hs = self.has_hs()
        std = {b: a for b, a in binding.items() if not b & HS}
        if hs is False:  # no HyperShift key either; that button keeps its factory action
            std = {b: factory(self.model, b) if a == 'hypershift' else a for b, a in std.items()}
        uses = 'hypershift' in std.values() or any(a != factory(self.model, b) for b, a in binding.items() if b & HS)
        layer = {} if hs is False or not (hs or uses) else {
            b: a for b, a in binding.items() if b & HS and (hs or a != std.get(b - HS))}
        for b, action in std.items():
            self.set_action(b, action)
        try:
            for b, action in layer.items():
                self.set_action(b, action)
        except OSError as e:
            if 'rejected' not in str(e) or hs:
                raise
            self.hs[self.model['name']] = False
            raise OSError(f'{self.model["name"]} has no HyperShift layer (it refused the HyperShift buttons). '
                          'Its normal buttons are on')
        if layer and not hs:
            ok = {b: self.get_action(b) for b in std} == std
            self.hs[self.model['name']] = ok
            if not ok:  # no layer, so no HyperShift key either: that button gets its factory action
                for b, action in std.items():
                    self.set_action(b, factory(self.model, b) if action == 'hypershift' else action)
                raise OSError(f'{self.model["name"]} has no HyperShift layer: it took the HyperShift buttons as normal '
                              'ones. Its normal buttons were put back')

    def read(self, cls, cmd, args=(), size=0x0A):
        """Args part of the answer to a read-only query (command id has the 0x80 bit set). `size` is OpenRazer's
        data size for the command; the mice tested here were read with 0x0A, so they keep it."""
        self.connect()
        return self.call(packet(cls, cmd, list(args), self.txn, size=0x0A if self.model['verified'] else size))[8:24]

    @_locked
    def battery(self):
        """(percent, charging), or None for a mouse without a battery. Read on the V4 Pro: 07/80 byte 1 is the
        level out of 255, 07/84 byte 1 is charging."""
        self.connect()
        level = self._try(lambda: self.read(0x07, 0x80, size=0x02)[1])
        if level is None:
            return None
        if 'cmd_txn' in self.model and '0784' not in self.model['cmd_txn']:
            return round(level * 100 / 255), False  # OpenRazer never asks these mice whether they charge
        return round(level * 100 / 255), bool(self._try(lambda: self.read(0x07, 0x84, size=0x02)[1]))

    @_locked
    def power(self):
        """(sleep after idle in minutes, low power mode below this battery %), or None if the mouse refuses."""
        a, b = self._try(lambda: self.read(0x07, 0x83, size=0x02)), self._try(lambda: self.read(0x07, 0x81, size=0x01))
        if a is None or b is None:
            return None
        return round((a[0] << 8 | a[1]) / 60), byte_to_percent(b[0])

    @_locked
    def set_sleep(self, minutes):
        if not SLEEP_MIN[0] <= int(minutes) <= SLEEP_MIN[1]:
            raise ValueError(f'sleep time must be {SLEEP_MIN[0]} to {SLEEP_MIN[1]} minutes')
        s = int(minutes) * 60
        self.connect()
        self.call(packet(0x07, 0x03, [s >> 8, s & 0xFF], self.txn, size=0x02))

    @_locked
    def set_low_power(self, percent):
        self.connect()
        lo, hi = low_power_range(self.model)
        if not lo <= int(percent) <= hi:
            raise ValueError(f'low power level must be {lo} to {hi}%')
        b = percent_to_byte(int(percent))
        if 'low_power_max' not in self.model:
            b = min(b, 0x3F)  # OpenRazer never sends more than 0x3F; 25% would be 0x40
        self.call(packet(0x07, 0x01, [b], self.txn, size=0x01))

    @_locked
    def dpi(self):
        """Current (x, y) DPI, or None if refused. Read on the V4 Pro: 04/85 with storage 01 answers 01, x hi/lo,
        y hi/lo; OpenRazer reads most mice with storage 00 (the mouse database says which)."""
        self.connect()
        a = self._try(lambda: self.read(0x04, 0x85, [self.model.get('dpi_read_store', 1)], size=0x07))
        return None if a is None else (a[1] << 8 | a[2], a[3] << 8 | a[4])

    @_locked
    def dpi_stages(self):
        """(active stage number from 1, [(x, y), ...]). 04/86 answers storage, active, count, then 7 bytes per
        stage: stage number, x hi/lo, y hi/lo, 2 reserved (read on the V4 Pro with five stages set by Synapse)."""
        self.connect()
        return parse_stages(self.call(packet(0x04, 0x86, [0x01], self.txn, size=0x26))[8:8 + 0x26])

    @_locked
    def polling(self):
        """Polling rate in Hz, or None for a code we haven't seen or a mouse that refuses. A change shows up
        ~0.3 s after it is set. Newer mice answer 00/C0 (the V4 Pro rejects 00/85); older ones reject 00/C0 and
        answer 00/85. The mouse database says which; otherwise the newer one is tried first."""
        self.connect()
        kind = self.model.get('poll')
        if kind != 'classic' and self.poll_table is not POLL_HZ_CLASSIC:
            a = self._try(lambda: self.read(0x00, 0xC0, [self.model.get('poll_args', 1)], size=0x01))
            if a is not None:
                self.poll_table = POLL_HZ
                return POLL_HZ.get(a[1])
            if kind == 'v2':
                return None
        a = self._try(lambda: self.read(0x00, 0x85, size=0x01))
        if a is None:
            return None
        self.poll_table = POLL_HZ_CLASSIC
        return POLL_HZ_CLASSIC.get(a[0])

    def polling_rates(self):
        """The rates this mouse can be set to (the newer set until the first polling read)."""
        return sorted((self.poll_table or POLL_HZ).values())

    @_locked
    def set_polling(self, hz):
        self.connect()
        if self.poll_table is None:
            self.polling()
        table = self.poll_table  # one table for both the code and the command, even if a reconnect resets it
        code = {v: k for k, v in (table or {}).items()}.get(hz)
        if code is None:
            raise ValueError(f'{hz} Hz is not one of {self.polling_rates()}')
        if table is POLL_HZ:
            self.call(packet(0x00, 0x40, [self.model.get('poll_args', 1), code], self.txn, size=0x02))
            if 'poll_again_txn' in self.model:  # OpenRazer sends these mice the set a second time, with 01
                self.call(packet(0x00, 0x40, [0x01, code], self.txn, size=0x02), txn=self.model['poll_again_txn'])
        else:
            self.call(packet(0x00, 0x05, [code], self.txn, size=0x01))

    @_locked
    def set_dpi(self, dpi):
        """One DPI for both axes. With one stage this is what web Synapse sends; with several (the DPI button
        cycles through them) only the active stage changes and the others stay as they are. A mouse without
        stages gets 04/05, as OpenRazer sends it."""
        self.connect()
        lo, hi = dpi_range(self.model)
        if not lo <= int(dpi) <= hi:
            raise ValueError(f'DPI must be {lo} to {hi}')
        d = int(dpi)
        if not has(self.model, 'stages'):
            return self.call(packet(0x04, 0x05, [0x01, d >> 8, d & 0xFF, d >> 8, d & 0xFF, 0, 0], self.txn, size=0x07))
        active, stages = self.dpi_stages()
        if not 1 <= active <= len(stages):  # unreadable table: fall back to a single stage
            active, stages = 1, [(0, 0)]
        stages[active - 1] = (d, d)
        self.call(stages_packet(active, stages, self.txn))

    @_locked
    def set_stages(self, active, stages):
        """Write a whole DPI stage table [(x, y), ...] (1 to 5 stages), keeping stage `active` (from 1) picked."""
        self.connect()
        lo, hi = dpi_range(self.model)
        if not 1 <= len(stages) <= 5 or not all(lo <= v <= hi for s in stages for v in s):
            raise ValueError(f'DPI stages must be 1 to 5 values from {lo} to {hi}')
        self.call(stages_packet(min(max(int(active), 1), len(stages)), [tuple(map(int, s)) for s in stages], self.txn))

    @_locked
    def lighting(self):
        """(effect name, (r, g, b), brightness %) of the model's first LED, or None if it has none we know.
        0F/82 answers storage, led, effect, 2 effect bytes, colour count, r, g, b. That read isn't in OpenRazer
        (it worked on the DeathAdder V2 Pro); for a mouse that refuses it the effect is None (unknown), which is
        not the same as 'other' (an effect FreeRazer doesn't offer, such as Synapse's custom frames)."""
        self.connect()
        leds = self.model.get('leds')
        if not leds:
            return None
        b = self._try(lambda: self.call(packet(0x0F, 0x84, [0x01, leds[0]], self.txn, size=0x03))[8:])
        if b is None:
            return None
        a = self._try(lambda: self.call(packet(0x0F, 0x82, [0x01, leds[0]], self.txn, size=0x0C),
                                        txn=self.model.get('cmd_txn', {}).get('0f02'))[8:])
        if a is None:
            return None, (0, 0, 0), byte_to_percent(b[2])
        effect = {v: k for k, v in LIGHT_EFFECTS.items()}.get(a[2], 'other')  # e.g. Synapse's own custom frames
        return effect, tuple(a[6:9]), byte_to_percent(b[2])

    @_locked
    def set_lighting(self, effect, rgb=(0, 255, 0)):
        """The same effect on every LED the model has."""
        self.connect()
        if not self.model.get('leds') or effect not in LIGHT_EFFECTS:
            raise ValueError(f'{self.model["name"]} has no {effect} lighting')
        for led in self.model['leds']:
            args = [0x01, led, LIGHT_EFFECTS[effect]]
            if effect in ('static', 'breathing'):  # breathing's 1 = one colour
                args += [0, 0, 1, *rgb] if effect == 'static' else [1, 0, 1, *rgb]
            self.call(packet(0x0F, 0x02, args, self.txn, size=max(len(args), 6)))  # OpenRazer's sizes: 6 or 9

    @_locked
    def set_brightness(self, percent):
        self.connect()
        if not self.model.get('leds') or not 0 <= int(percent) <= 100:
            raise ValueError('brightness must be 0 to 100%')
        for led in self.model['leds']:
            self.call(packet(0x0F, 0x04, [0x01, led, percent_to_byte(int(percent))], self.txn, size=0x03))


def describe(binding, model=DEVICES[0]):
    changed = [f'{label(model, b)} = {pretty(a)}' for b, a in binding.items()
               if a != factory(model, b) and not (b & HS and a == 'hypershift')]  # the key shows once
    return ', '.join(changed) or 'factory bindings'


APP_DIR = 'FreeRazer'
OLD_APP_DIR = 'MouseProfiles'  # this app's folder before it was renamed FreeRazer


def profiles_path(legacy_dir=None):
    """%APPDATA%\\FreeRazer\\profiles.json. On first run, copies over what an older version left: the whole
    %APPDATA%\\MouseProfiles folder (profiles), or else a profiles.json next to the exe or
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


def db_paths():
    """(database shipped with the app, database downloaded with Update mouse database)."""
    shipped = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), DB_FILE)
    return shipped, os.path.join(os.path.dirname(profiles_path()), DB_FILE)


def load_db():
    """Use the newest valid mouse database of the two; returns it (None if neither is usable)."""
    best = None
    for path in db_paths():
        try:
            with open(path, encoding='utf-8') as f:
                db = json.load(f)
            check_db(db)
        except (OSError, ValueError):  # missing, or not valid: the other one is used
            continue
        if best is None or db['version'] > best['version']:
            best = db
    if best:
        use_db(best)
    return best


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
    print(probe_report(ids))


def probe_report(ids=range(1, 0x80)):
    """Read-only report for adding a mouse, as text. Sends only button reads (class 02, id 8C)."""
    out = []
    print = out.append  # the lines below were written for the command line
    print('Razer HID devices:')
    infos = hid.enumerate(VID)
    for i in infos:
        print(f"  PID {i['product_id']:#06x} interface {i['interface_number']} usage {i['usage_page']:#06x}/"
              f"{i['usage']:#06x} {i['product_string']!r}")
    for pid in sorted({i['product_id'] for i in infos}):
        found, asleep = None, False
        for info in (i for i in infos if i['product_id'] == pid):
            for txn in TXN_GUESSES:
                d = hid.device()
                try:
                    d.open_path(info['path'])
                    for _ in range(4):  # 04 = no answer in time: a wireless mouse asleep; give it time to wake
                        status = transact(d, read_packet(1, txn))[0]
                        if status != 0x04:
                            break
                        asleep = True
                        time.sleep(0.5)
                    if status == 0x02:
                        found = d, txn, info['interface_number']
                        break
                except OSError:
                    pass
                d.close()
            if found:
                break
        if not found:
            print(f'\nPID {pid:#06x}: ' + ('the mouse did not answer: it is probably asleep. Move it, then make the '
                                          'report again' if asleep else 'no answer to button reads'))
            continue
        d, txn, iface = found
        known = model_for(pid)
        print(f'\nPID {pid:#06x}: answers on interface {iface} with transaction ID {txn:#04x}'
              f' (FreeRazer knows it as: {known["name"]}, {"built in" if known["verified"] else "from the mouse database" if pid in DB else "not known"})')
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
    return '\n'.join(out)


class _FakeDev:
    """Stands in for the mouse in test(): records what was sent, answers 'ok'."""
    def __init__(self, refuse=(), timeout=()):
        self.sent, self.refuse = [], set(refuse)  # refuse: (class, command) pairs answered with status 05
        self.timeout = set(timeout)  # (class, command) pairs answered with 04, as a sleeping mouse does
        self.stray = 0  # how many of the next answers belong to another program's command
        self.actions = {}  # button: (action type, payload) for button reads to answer with

    store = None  # 'layers': button sets are kept per layer and read back; 'ignore': kept, layer byte ignored

    def _key(self, p):
        return p[9] + (p[10] << 8 if self.store == 'layers' else 0)

    def send_feature_report(self, data):
        self.sent.append(bytes(data[1:]))
        p = self.sent[-1]
        if self.store and (p[6], p[7]) == (0x02, 0x0C):
            self.actions[self._key(p)] = (p[11], list(p[13:13 + p[12]]))

    def get_feature_report(self, _id, _n):
        last = self.sent[-1] if self.sent else bytes(90)
        if self.stray:  # an answer to someone else's command, like Synapse's lighting frames
            self.stray -= 1
            return b'\x00\x02' + bytes(4) + b'\x08\x0f\x03' + bytes(82)
        if (last[6], last[7]) == (0x02, 0x8C) and self._key(last) in self.actions:
            kind, payload = self.actions[self._key(last)]
            args = bytes([last[8], last[9], 0, kind, len(payload), *payload])
            return b'\x00\x02' + last[1:8] + args + bytes(82 - len(args))
        status = b'\x04' if (last[6], last[7]) in self.timeout else b'\x05' if (last[6], last[7]) in self.refuse else b'\x02'
        # status, then the command header echoed back (as the mouse does), arguments zero
        return b'\x00' + status + last[1:8] + bytes(82)

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
        for b, (_, action) in d['buttons'].items():
            encode(action)
    assert model_for(0x00E6) is v4 and v4['verified'] and v4['txn'] == 0x1F
    assert set(v4['buttons']) == {1, 2, 3, 4, 5, 9, 10, 0x60}
    other = model_for(0x0BAD, 'Some Mouse')
    assert not other['verified'] and other['name'] == 'Some Mouse' and 0x60 not in other['buttons']
    # a profile made on one model applies to another without the buttons it lacks
    assert resolve({}, {'96': 'f5', '4': 'e'}, other) == {**resolve({}, None, other), 4: 'e'}

    # HyperShift, as read back after web Synapse set Mouse Button 5 = HyperShift and HyperShift layer button 4 = F9
    assert decode(0x0C, b'\x01') == 'hypershift' and decode(0x02, b'\x00\x42') == 'f9'
    assert set_packet(4 + HS, 'f10', 0x1F)[8:15].hex(' ') == '01 04 01 02 02 00 43'
    assert read_packet(4 + HS, 0x1F)[8:11].hex(' ') == '01 04 01'
    full = resolve({}, {'5': 'hypershift', str(4 + HS): 'f9'}, v4)
    assert full[5] == full[5 + HS] == 'hypershift' and full[4 + HS] == 'f9' and full[4] == 'mouse:back'
    assert len(full) == 14 and 1 + HS not in full
    assert describe(full, v4) == 'Mouse Button 5 = Razer HyperShift, Mouse Button 4 (HyperShift) = F9'
    # HyperShift on the HyperShift layer only (no key on the standard one): factory; every mouse gets the layer
    assert resolve({}, {str(3 + HS): 'hypershift'}, v4)[3 + HS] == 'mouse:middle'
    assert resolve({}, {'5': 'hypershift', str(4 + HS): 'f9'}, other)[4 + HS] == 'f9'
    da = model_for(0x007D)
    hs_prof = resolve({}, {'5': 'hypershift', '3': 'e', str(4 + HS): 'f9'}, da)
    for store, want in (('layers', True), ('ignore', False)):
        m = Mouse()
        m.dev, m.model, m.txn = _FakeDev(), da, 0x1F
        m.dev.store = store
        try:
            m.write(hs_prof)
            assert want, 'a mouse that ignores the layer passed'
        except OSError as e:
            assert not want and 'no HyperShift' in str(e), e
        assert m.hs[da['name']] is want and m.has_hs() is want
        sets = [p for p in m.dev.sent if p[6:8] == b'\x02\x0c']
        # unknown mouse: only HyperShift buttons that differ from normal are sent (3 is E normally, Scroll Click here)
        assert [p[9] for p in sets if p[10]] == [3, 4], [p[8:12].hex() for p in sets if p[10]]
        normal = {b: m.get_action(b) for b in hs_prof if not b & HS}
        assert normal == {b: factory(da, b) if a == 'hypershift' and not want else a
                          for b, a in hs_prof.items() if not b & HS}, normal  # normal buttons as they should be
        if not want:  # remembered: nothing on the HyperShift layer is sent or allowed again
            n = len(m.dev.sent)
            m.write(hs_prof)
            assert not [p for p in m.dev.sent[n:] if p[6:8] == b'\x02\x0c' and p[10]]
            assert m.get_action(5) == factory(da, 5)  # no HyperShift key without the layer
            assert 4 + HS not in m.writable()
    # learned buttons join the model; a press matches the IDs doing that
    LEARNED[v4['name']] = {0x50: ('Button F9', 'f9')}
    assert model_for(v4['pids'][0])['buttons'][0x50] == ('Button F9', 'f9') and 0x50 not in v4['buttons']
    LEARNED.clear()
    assert match_press({4: 'mouse:back', 0x40: '1', 0x41: '1', 7: 'raw:01:02'}, '1') == [0x40, 0x41]
    assert match_press({0x34: 'raw:0e:09008e', 4: 'mouse:back'}, 'tilt') == [0x34]
    assert match_press({4: 'mouse:back'}, 'f9') == []
    # Naga V2 HyperSpeed: buttons as its owner read them in factory state (GitHub issue 1)
    naga = db_model({'pid': 0x00B4, 'name': 'Razer Naga V2 HyperSpeed (Receiver)', 'features': ['dpi']})
    assert len(naga['buttons']) == 21 and 4 not in naga['buttons'] and 5 not in naga['buttons']
    assert naga['buttons'][0x40] == ('Side Button 1', '1') and naga['buttons'][0x4B] == ('Side Button 12', '=')
    for _, action in naga['buttons'].values():
        assert decode(*encode(action)) == action, action  # every factory action can be written back exactly
    assert encode('raw:0e:09008e') == (0x0E, [0x09, 0x00, 0x8E]) and pretty('raw:06:02') == 'DPI (factory)'
    for bad in ('raw:06:03', 'raw:0e:09', 'raw:0c:01'):  # other raw values stay unwritable
        try:
            encode(bad)
            raise AssertionError(f'{bad} encoded')
        except ValueError:
            pass
    # factory scan bytes: 0x0B = type 06 payload 01, 0x34 = type 0e payload 09 00 8e, 0x40 = key 1 (1e)
    assert decode(0x06, b'\x01') == 'raw:06:01' and decode(0x0E, b'\x09\x00\x8e') == 'raw:0e:09008e'
    assert decode(0x02, b'\x00\x1e') == '1' and decode(0x02, b'\x00\x2e') == '='
    m = Mouse()
    m.dev, m.model, m.txn = _FakeDev(), naga, 0x1F
    m.dev.actions = {b: encode(a) for b, (_, a) in naga['buttons'].items()}
    m.dev.actions[0x41] = encode('r')  # one grid button still remapped elsewhere: stays locked
    name, got = m.confirm_buttons()
    assert got == set(b for b in naga['buttons'] if b != 1) - {0x41}, sorted(got)
    m.confirmed = {name: got}
    m.set_action(0x40, 'f13')
    assert m.dev.sent[-1][8:15].hex(' ') == '01 40 00 02 02 00 68'
    try:
        m.set_action(0x41, 'f13')
        raise AssertionError('unconfirmed grid button written')
    except ValueError:
        pass

    # a profile without HyperShift sends nothing on that layer to a mouse not known to have it
    m = Mouse()
    m.dev, m.model, m.txn = _FakeDev(), da, 0x1F
    m.write(resolve({}, {'3': 'e'}, da))
    assert not [p for p in m.dev.sent if p[6:8] == b'\x02\x0c' and p[10]] and m.has_hs() is None
    # a mouse that refuses HyperShift writes: remembered too, normal buttons stay on
    m = Mouse()
    m.dev, m.model, m.txn = _FakeDev(), da, 0x1F
    m.dev.refuse = set()
    real_send = m.dev.send_feature_report
    m.dev.send_feature_report = lambda d: (real_send(d), m.dev.refuse.add((2, 12)) if d[1 + 10] else m.dev.refuse.discard((2, 12)))
    try:
        m.write(hs_prof)
        raise AssertionError('refused HyperShift write passed')
    except OSError as e:
        assert 'refused' in str(e) and m.hs[da['name']] is False
    for bad in (str(1 + HS),):
        try:
            resolve({}, {bad: 'f5'}, v4)
            raise AssertionError('left click must be locked on the HyperShift layer too')
        except ValueError:
            pass

    # write guards, on a fake device so no mouse is touched
    m = Mouse()
    m.dev, m.model, m.txn = _FakeDev(), v4, 0x1F
    m.set_action(5, 'f7')
    assert m.dev.sent[-1] == bytes(cap)
    m.set_action(4 + HS, 'f9')
    assert m.dev.sent[-1][8:15].hex(' ') == '01 04 01 02 02 00 42'
    for bad in (lambda: m.set_action(1, 'f7'), lambda: m.set_action(6, 'f7'), lambda: m.set_action(1 + HS, 'f7'),
                lambda: m.call(packet(0x02, 0x0C, [1, 4, 2, 2, 2, 0, 0x42], 0x1F)),  # no layer 2
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
        raise AssertionError('a button not confirmed on the mouse was written')
    except ValueError:
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

    # mouse database: a mouse from OpenRazer gets only its listed features, with OpenRazer's transaction IDs
    def refused(*writes):
        for w in writes:
            n = len(m.dev.sent)
            try:
                w()
                raise AssertionError('write was allowed')
            except ValueError:
                assert len(m.dev.sent) == n, 'sent before refusing'
    entry = {'pid': 0x0BEE, 'name': 'Razer Test Mouse', 'dpi_max': 16000, 'dpi_read_store': 0, 'poll': 'v2',
             'poll_again_txn': 0xFF, 'leds': [1], 'features': ['dpi', 'poll', 'light'],
             'txn': {'0405': 0x3F, '0040': 0x1F, '0f02': 0x3F}}
    use_db({'version': 1, 'mice': [entry]})
    t = model_for(0x0BEE)
    assert not t['verified'] and t['name'] == 'Test Mouse' and has(t, 'dpi') and not has(t, 'sleep')
    m.model, m.txn, m.dev, m.poll_table, m.confirmed = t, 0x11, _FakeDev(), None, {}
    m.set_dpi(800)  # no DPI stages listed: 04/05, as OpenRazer sends it
    assert m.dev.sent[-1][1] == 0x3F and m.dev.sent[-1][5:15].hex(' ') == '07 04 05 01 03 20 03 20 00 00'
    m.set_polling(500)  # OpenRazer: 00 first, then 01 with the second transaction ID
    assert [(p[1], p[8]) for p in m.dev.sent[-2:]] == [(0x1F, 0), (0xFF, 1)] and m.dev.sent[-1][9] == 0x10
    m.set_lighting('spectrum')
    assert m.dev.sent[-1][1] == 0x3F and m.dev.sent[-1][8:11].hex(' ') == '01 01 03'
    m.get_action(4)
    assert m.dev.sent[-1][1] == 0x11  # no database ID for buttons: the one the mouse answered on connect
    refused(lambda: m.set_sleep(5), lambda: m.set_action(4, 'f5'), lambda: m.call(packet(0x0F, 0x02, [1, 4, 0], 0x1F)))
    # buttons unlock when they read back as their factory action; a changed or odd answer doesn't
    m.dev = _FakeDev()
    m.dev.actions = {2: encode('mouse:right'), 4: encode('mouse:back'), 5: encode('f5'), 9: (0x09, [1])}
    assert m.confirm_buttons() == ('Test Mouse', {2, 4})
    m.confirmed = {'Test Mouse': {2, 4}, 'Other Mouse': {5}}  # another model's confirmations don't count here
    m.set_action(4, 'f5')
    refused(lambda: m.set_action(5, 'f5'), lambda: m.set_action(9, 'f5'))
    for bad in ({**entry, 'txn': {'020c': 1}}, {**entry, 'leds': [0x20]}, {**entry, 'extra': 1}, {**entry, 'pid': -1},
                {**entry, 'features': ['firmware']}, {**entry, 'leds': [[1]]}, {**entry, 'features': [['dpi']]},
                {**entry, 'leds': [1.0]}, {**entry, 'dpi_read_store': 1.0}, {**entry, 'leds': [1] * 1000},
                {**entry, 'pid': True}, {**entry, 'txn': {'0405': 3.0}}, {**entry, 'name': 7}, 'not a dict'):
        try:
            check_db({'version': 1, 'mice': [bad]})
            raise AssertionError(f'bad database entry accepted: {bad}')
        except ValueError:
            pass
    try:
        check_db({'version': 1, 'mice': [entry, entry]})
        raise AssertionError('a mouse listed twice was accepted')
    except ValueError:
        pass
    # no answer (asleep) is not a refusal: it must not look like "this mouse has no battery"
    m.dev = _FakeDev(timeout={(0x07, 0x80)})
    try:
        m.battery()
        raise AssertionError('a timed-out read was taken as "not supported"')
    except OSError as e:
        assert 'did not answer' in str(e)
    # profiles are written the way the mouse reads them back, and odd actions are refused cleanly
    assert resolve({}, {'5': 'shift+ctrl+5'})[5] == 'ctrl+shift+5'
    for bad in ({'5': 5}, {'5': None}, {'5': 'ctrl+'}):
        try:
            resolve({}, bad)
            raise AssertionError(f'bad action accepted: {bad}')
        except ValueError:
            pass
    shipped = db_paths()[0]
    if os.path.exists(shipped):
        with open(shipped, encoding='utf-8') as f:
            assert len(check_db(json.load(f))) > 100
    use_db({'version': 0, 'mice': []})

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
    if cmd != 'test':
        load_db()
    if cmd == 'apply' and len(sys.argv) > 2:
        apply(sys.argv[2])
    else:
        {'show': show, 'test': test, 'list': list_profiles, 'auto': run, 'probe': probe}.get(cmd, list_profiles)()
