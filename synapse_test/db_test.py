"""Mouse database in the app: the real mouse still reads as before (read-only), a database mouse on a stand-in
device gets only its features and confirmed buttons, and Update mouse database takes a newer file. Nothing is
written to a real mouse, and the real settings and database files are untouched.
    py -3.13 db_test.py out_prefix"""
import ctypes, importlib.util, json, os, sys, tempfile
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
fr.log_event = lambda text: None  # what the app logs about the mouse stays out of the real error.log
rs = fr.rs
tmp = tempfile.mkdtemp()
fr.LOG = os.path.join(tmp, 'error.log')
shipped = rs.db_paths()[0]
rs.db_paths = lambda: (shipped, os.path.join(tmp, 'devices.json'))
fr.App.check_updates = lambda self, manual=False: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: None
app._send = lambda write, done, keep=None: print('  would send:', done, flush=True)
app.deiconify()
app.attributes('-topmost', True)
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('ok  ' if cond else 'FAIL', name, flush=True)


def shot(name):
    from PIL import ImageGrab
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab((x, y, x + app.winfo_width(), y + app.winfo_height())).save(f'{sys.argv[1]}_{name}.png')


def real_mouse():
    print('database:', len(rs.DB), 'mice; window shows', app.model['name'], '|', app.dev_lbl.cget('text'), flush=True)
    check('real mouse reads (battery shown)', app.dev_lbl.cget('text').startswith('Battery'))
    check('real mouse settings usable', str(app.dpi_box.state()) != "('disabled',)" and app.power['sleep'][0].on)
    app.after(100, db_mouse)


def db_mouse():
    m = rs.model_for(0x00AB)  # Basilisk V3 Pro (wireless) from the database
    check(f'database mouse: {m["name"]} features {sorted(m["features"])}', not m['verified'] and rs.has(m, 'dpi')
          and not rs.has(m, 'light'))
    app.refresh_device = lambda repeat=True: None  # the stand-in below must not be read by the timer
    real = app.mouse
    fake = rs.Mouse()
    fake.dev, fake.model, fake.txn, fake.confirmed = rs._FakeDev(), m, 0x1F, {}
    fake.dev.actions = {b: rs.encode(m['buttons'][b][1]) for b in (2, 3, 4)}  # 5, 9, 10 answer something else
    app.mouse = fake
    app._use_model(m)
    app.read_mouse()
    check(f'confirmed buttons {app.editable}', app.editable == [2, 3, 4, 2 + rs.HS, 3 + rs.HS, 4 + rs.HS])
    check('confirmations remembered', app.cfg['confirmed'].get(m['name']) == [2, 3, 4])
    info = ((80, False), (1600, 1600), 1000, m, (5, 10), None)
    app._device_done(info)
    app.show_page('performance')
    shot('db_perf')
    check('DPI and polling usable, lighting hidden', app.dpi_scale.on and not app.light_box.winfo_ismapped())
    app.show_page('buttons')
    shot('db_buttons')
    try:
        fake.set_action(5, 'f5')
        check('unconfirmed button refused', False)
    except ValueError:
        check('unconfirmed button refused', True)
    app.mouse = real
    app.after(100, update)


def update():
    newer = json.load(open(shipped, encoding='utf-8'))
    newer['version'] += 1
    newer['mice'].append({'pid': 0x0BEE, 'name': 'Razer Brand New Mouse', 'features': ['dpi'], 'txn': {'0405': 31}})
    path = os.path.join(tmp, 'served.json')
    json.dump(newer, open(path, 'w', encoding='utf-8'))
    fr.DB_URL = 'file:///' + path.replace('\\', '/')
    before = len(rs.DB)
    app.update_db()
    app.after(2500, lambda: after_update(before))


def after_update(before):
    check(f'update took the newer file ({before} -> {len(rs.DB)} mice)', len(rs.DB) == before + 1 and 0x0BEE in rs.DB)
    check('saved for next start', os.path.exists(rs.db_paths()[1]))
    shot('settings') if app.show_page('settings') is None else None
    print('status:', app.last_status, '|', app.db_lbl.cget('text'), flush=True)
    bad = os.path.join(tmp, 'bad.json')
    json.dump({'version': 99999999, 'mice': [{'pid': 1, 'name': 'x', 'txn': {'020c': 1}}]}, open(bad, 'w'))
    fr.DB_URL = 'file:///' + bad.replace('\\', '/')
    app.update_db()
    app.after(2500, after_bad)


def after_bad():
    check('bad file refused and not saved', 'Could not update' in app.last_status and 0x0BEE in rs.DB
          and json.load(open(rs.db_paths()[1]))['version'] != 99999999)
    check('no errors logged', not os.path.exists(fr.LOG))
    print('all ok' if all(ok) else 'SOME FAILED', flush=True)
    app.quit_app()


app.after(5000, real_mouse)
app.mainloop()
