"""Break test for the review fixes: bad settings, hostile imports, a tampered update answer, the DPI button vs
the Synapse put-back, a mismatched mouse, focus in a dropdown. Stand-in mice only; temp files only."""
import ctypes, importlib.util, json, os, sys, tempfile, types
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
rs = fr.rs
tmp = tempfile.mkdtemp()
fr.LOG = os.path.join(tmp, 'error.log')
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('ok  ' if cond else 'FAIL', name, flush=True)


def raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    except Exception as e:
        print('     raised', type(e).__name__, e)
        return False
    return False


# --- settings file shapes (offline) ---
for bad in ({'profiles': []}, {'links': None}, {'profiles': {'A': {'4': 5}}}, {'profiles': {'A': []}},
            {'confirmed': {'X': ['2']}}, {'active': 3}, {'keep': {'X': 1}}, [], {'mouse': 'x'}):
    check(f'bad settings refused: {str(bad)[:40]}', raises(lambda: fr.check_cfg(bad)))
fr.check_cfg({'profiles': {'A': {'4': 'f5'}}, 'links': {'g.exe': 'A'}, 'confirmed': {'X': [2, 4]}, 'keep': {'X': {}},
              'active': 'A', 'mouse': 230, 'auto': True})
check('good settings accepted', True)


# --- import (offline) ---
def imp(data):
    p = os.path.join(tmp, 'imp.json')
    json.dump(data, open(p, 'w'))
    profiles = {'A': {}}
    return fr.import_file(p, profiles), profiles
for bad in ({'profiles': {'X': {'4': 5}}}, {'profiles': {'X': {'4': None}}}, {'profiles': {'X': {'1': 'f5'}}},
            {'profiles': {'X': {'abc': 'f5'}}}, {'profiles': {'X': {'4': 'notakey'}}}, {'profiles': []}, [1, 2]):
    check(f'bad import refused cleanly: {str(bad)[:40]}', raises(lambda: imp(bad)))
added, profiles = imp({'profiles': {'X': {'96': 'f5', '04': 'shift+ctrl+5'}, 'A ': {}, 'A': {'5': 'e'}}})
check(f'import keeps a DPI-button remap from another model, normalises keys/combos, keeps both "A"s: {added}',
      profiles['X'] == {'96': 'f5', '4': 'ctrl+shift+5'} and len(added) == 3 and len(set(added)) == 3)


# --- updater (offline: _curl replaced) ---
served = {}
fr._curl = lambda *a, **k: served[a[-1]] if a[-1] in served else (_ for _ in ()).throw(OSError('404'))
assets = {fr.SETUP_ASSET: 'x', fr.SETUP_ASSET + '.sha256': 'y'}
check('tampered tag refused', raises(lambda: fr.download_update('v1.0.0/../../../evil', assets), OSError))
check('release without installer refused', raises(lambda: fr.download_update('v1.0.1', {}), OSError))
base = f'https://github.com/{fr.UPDATE_REPO}/releases/download/v1.0.1/'


def fake_curl(*a, **k):
    if a[0] == '-o':
        open(a[1], 'wb').write(b'installer')
        return b''
    return served.get(a[-1], b'')
fr._curl = fake_curl
served[base + fr.SETUP_ASSET + '.sha256'] = b''
check('empty checksum file refused (no crash)', raises(lambda: fr.download_update('v1.0.1', assets), OSError))
fr._curl = lambda *a, **k: json.dumps([1, 2]).encode()
check('non-release API answer refused', raises(lambda: fr.latest_release(), ValueError))

# --- the app, with stand-in mice ---
fr.App.check_updates = lambda self, manual=False: None
fr.App.refresh_device = lambda self, repeat=True: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
app = fr.App()
app.write_cfg = lambda: True
app.deiconify()


def run():
    real = app.mouse
    v4 = rs.DEVICES[0]
    fake = rs.Mouse()
    fake.dev, fake.model, fake.txn = rs._FakeDev(), v4, 0x1F
    # the buttons answer with their factory actions (Default is on the mouse)
    fake.dev.actions = {b: rs.encode(a) for b, (_, a) in {**v4['buttons'], **rs.model_for(0x7D)['buttons']}.items()}
    # answer 04/86 with a 3-stage table, active stage 2
    table = bytes.fromhex('01 02 03 00 01 90 01 90 00 00 01 03 20 03 20 00 00 02 06 40 06 40 00 00') + bytes(14)
    orig = fake.dev.get_feature_report

    def report(i, n):
        last = fake.dev.sent[-1]
        if (last[6], last[7]) == (0x04, 0x86):
            return b'\x00\x02' + last[1:8] + table + bytes(82 - len(table))
        return orig(i, n)
    fake.dev.get_feature_report = report
    app.mouse, app.model = fake, v4
    app.editable = app.editable_for(v4)
    app.cfg['active'] = 'default'
    app.cfg['keep'] = {v4['name']: {'stages': [[400, 400], [800, 800], [1600, 1600]], 'dpi': 400}}
    info = ((80, False), (800, 800), 1000, v4, (5, 30), None)
    n = len(fake.dev.sent)
    fixed = app.keep_settings(info)
    writes = [p for p in fake.dev.sent[n:] if not p[7] & 0x80]
    check(f'DPI button moved to stage 2 (800): nothing put back {fixed}', fixed == [] and not writes)
    app.cfg['keep'][v4['name']]['stages'] = [[400, 400], [900, 900], [1600, 1600]]
    fixed = app.keep_settings(info)
    last = fake.dev.sent[-1]
    check(f'stage table changed by "Synapse": whole table put back, stage 2 kept {fixed}',
          fixed == ['DPI'] and last[6:8] == b'\x04\x06' and last[9] == 2)
    # a mouse that can't say its light effect: no put-back loop
    da = rs.model_for(0x7D)
    app.mouse.model, app.model = da, da
    app.cfg['keep'] = {da['name']: {'light': ['static', [255, 0, 0]]}}
    n = len(fake.dev.sent)
    app.keep_settings(((80, False), (800, 800), 1000, da, (5, 5), (None, (0, 0, 0), 33)))
    check('unknown light effect: nothing written', not [p for p in fake.dev.sent[n:] if not p[7] & 0x80])
    # a missing active profile doesn't kill the worker
    app.cfg['active'] = 'gone'
    check('missing active profile: ValueError, not KeyError', raises(lambda: app.keep_settings(info)))
    app.cfg['active'] = 'default'
    # the window shows one mouse, another answers: the window follows the one that answered
    app.mouse = real
    app._connected = True
    app.model = v4
    app.read_mouse = lambda: None
    app._device_done(((80, False), (800, 800), 1000, da, (5, 5), None))
    check(f'window follows the mouse that answered: {app.model["name"]}', app.model['name'] == da['name'])
    # focus in an open dropdown list (focus_get raises KeyError)
    app.focus_get = lambda: (_ for _ in ()).throw(KeyError('popdown'))
    try:
        app._device_done(((80, False), (800, 800), 1000, da, (5, 5), None))
        check('device refresh with a dropdown open', True)
    except KeyError:
        check('device refresh with a dropdown open', False)
    del app.focus_get
    # a mouse where nothing is changeable: arrows and Enter do nothing, no crash
    app.editable = []
    app.step_sel(1)
    app.select(5)
    check('no changeable buttons: arrows/Enter safe, editor stays closed', not app.pop_open)
    # pop-up "inside" test: a second toplevel is not inside the first
    t1 = fr.tk.Toplevel(app)
    t2 = fr.tk.Toplevel(app)
    t1.overrideredirect(True)
    app._transient(t1, None)
    app.update()
    t2.event_generate('<Button-1>', x=1, y=1)
    app.update()
    check('a click in another window closes the pop-up', not t1.winfo_exists())
    t2.destroy()
    # auto-switch keeps its timer even when a callback fails
    app._q.put(lambda: 1 / 0)
    before = len(app.tk.call('after', 'info'))
    app.poll_games()
    check('auto-switch still scheduled after a failing callback', len(app.tk.call('after', 'info')) >= before)
    check('no unexpected errors logged', not os.path.exists(fr.LOG) or 'Traceback' not in open(fr.LOG).read()
          or 'ZeroDivisionError' in open(fr.LOG).read())
    print('all ok' if all(ok) else 'SOME FAILED', flush=True)
    app.quit_app()


app.after(1500, run)
app.mainloop()
