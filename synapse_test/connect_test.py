"""Opening mice that don't answer the usual way, and what gets logged about it, on stand-in HID devices:
a Mamba 2012 that answers no button read (GitHub issue 3) opens for its settings only; a mouse that answers nothing
logs every attempt; the DeathAdder V2 X HyperSpeed (issue 2) gets its two DPI buttons. Nothing touches a real
mouse, the settings file or the log.
    py -3.13 connect_test.py"""
import ctypes, importlib.util, os, sys
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
rs = fr.rs
fr.App.check_updates = lambda self, manual=False: None
fr.App.refresh_device = lambda self, repeat=True: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
logged = []
fr.log_event = logged.append
app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: True
app.deiconify()
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('ok  ' if cond else 'FAIL', name, flush=True)


class Dev(rs._FakeDev):
    def open_path(self, path):
        pass


def plug(pid, name, refuse=(), timeout=(), actions=None):
    """One stand-in mouse on interface 0, as hid.enumerate lists it."""
    info = {'product_id': pid, 'interface_number': 0, 'usage_page': 1, 'usage': 2, 'product_string': name, 'path': b'x'}
    rs.mice = lambda: [info]

    def device():
        d = Dev(refuse=refuse, timeout=timeout)
        d.actions = dict(actions or {})
        return d
    rs.hid.device = device


def run():
    # Mamba 2012: button reads refused, DPI read answered
    plug(0x0024, 'Razer Mamba', refuse={(0x02, 0x8C)})
    m = rs.Mouse()
    m.connect()
    check('Mamba 2012 opens for settings', m.model and m.model.get('settings_only') and m.txn == 0xFF)
    check('no buttons to change', rs.editable(m.model) == [] and m.writable() == set())
    print('  log:', logged, flush=True)
    check('logged how it was opened', any('for settings only' in line and '04/85' in line for line in logged))
    app.mouse = m
    app._connected = False
    app._device_done(app.read_info())
    app.update()
    print('  header:', app.dev_lbl.cget('text'), '| status:', app.last_status, flush=True)
    check('shown as connected', app.dev_lbl.cget('text') != 'Mouse not connected')
    check('says why buttons can\'t change', 'doesn\'t answer button commands' in app.last_status)
    check('app shows no changeable button', app.editable == [] and app.model.get('settings_only'))
    check('a profile switch writes no buttons', app.put_on_mouse('default') and
          not [p for p in m.dev.sent if p[6:8] == b'\x02\x0c'])

    # a mouse that answers nothing: every attempt is logged, once
    logged.clear()
    plug(0x0024, 'Razer Mamba', timeout={(0x02, 0x8C), (0x04, 0x85), (0x07, 0x80)})
    m = rs.Mouse()
    for _ in range(2):
        try:
            m.connect()
        except OSError:
            pass
    print('  log:', logged, flush=True)
    check('nothing answers: attempts logged once', len(logged) == 1 and logged[0].startswith('no mouse opened: ')
          and logged[0].count('txn') == 4 and 'settings read 04/85: status 0x04' in logged[0])

    # DeathAdder V2 X HyperSpeed: DPI buttons from issue 2; scroll click reads HyperShift, so it stays locked
    logged.clear()
    da = rs.model_for(0x009C)
    check('DeathAdder V2 X has its DPI buttons', da.get('layout') and da['buttons'][0x0B] == ('DPI Up', 'raw:06:01')
          and da['buttons'][0x0C] == ('DPI Down', 'raw:06:02'))
    plug(0x009C, 'Razer DeathAdder V2 X HyperSpeed', actions={
        1: (1, [1]), 2: (1, [2]), 3: (0x0C, [1]), 4: (1, [4]), 5: (1, [5]), 9: (1, [9]), 10: (1, [10]),
        0x0B: (6, [1]), 0x0C: (6, [2])})
    m = rs.Mouse()
    m.connect()
    name, got = m.confirm_buttons()
    print('  unlocked:', sorted(got), '| log:', logged, flush=True)
    check('DPI buttons unlock, scroll click doesn\'t', got == {2, 4, 5, 9, 10, 0x0B, 0x0C})
    check('logged why scroll click is locked', any('button 0x03 reads hypershift, not its factory mouse:middle' in line
                                                   for line in logged))
    check('logged which mouse opened', any(line.startswith('opened DeathAdder V2 X HyperSpeed (PID 0x009c interface 0')
                                           for line in logged))
    n = len(logged)
    app.log_once(logged[0])
    check('log_once', len(logged) == n)
    print('ALL OK' if all(ok) else 'SOME FAILED', flush=True)
    app.after(200, app.quit_app)


app.after(800, run)
app.mainloop()
