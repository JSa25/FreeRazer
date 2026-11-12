"""Learn buttons (the key tester) on a stand-in mouse FreeRazer has no button map for: presses find their button
IDs, new ones are added and can then be changed, and the results open as a filled-in GitHub issue. One real F24 key press goes
through the Windows hooks. Nothing is written to a real mouse and the settings file is untouched.
    py -3.13 learn_test.py out_prefix"""
import ctypes, importlib.util, os, re, sys, time
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
rs = fr.rs
fr.App.check_updates = lambda self, manual=False: None
fr.App.refresh_device = lambda self, repeat=True: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
log_size = os.path.getsize(fr.LOG) if os.path.exists(fr.LOG) else 0
app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: True
app.deiconify()
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('ok  ' if cond else 'FAIL', name, flush=True)


def wait(s=0.3):
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.update()
        time.sleep(0.01)


def run():
    # the key watcher's translation, without hooks
    got = []
    w = fr.InputWatch.__new__(fr.InputWatch)
    w.seen, w.held, w.alone = got.append, set(), None
    for vk, down in ((0xA2, 1), (0x4B, 1), (0x4B, 0), (0xA2, 0), (0xA3, 1), (0xA3, 0), (0x31, 1)):
        w.key(vk, bool(down))
    w.button(0x20B, 1 << 16)
    w.button(0x20B, 2 << 16)
    w.button(0x20A, 120 << 16)
    w.button(0x20A, (-120 & 0xFFFF) << 16)
    w.button(0x20E, 120 << 16)
    print('  watched:', got, flush=True)
    check('keys and buttons named', got == ['ctrl+k', 'rctrl', '1', 'mouse:back', 'mouse:forward', 'mouse:scrollup',
                                            'mouse:scrolldown', 'tilt'])

    model = rs.model_for(0x00A7)  # in the mouse database, with no button map
    fake = rs.Mouse()
    fake.dev, fake.model, fake.txn = rs._FakeDev(), model, 0x1F
    fake.dev.store = 'layers'
    fake.dev.actions = {b: rs.encode(a) for b, (_, a) in model['buttons'].items()}
    fake.dev.actions.update({0x40: rs.encode('1'), 0x41: rs.encode('2'), 0x42: rs.encode('f24'),
                             0x44: rs.encode('f23'), 0x45: rs.encode('f23'), 0x34: (0x0E, [0x0B, 0x00, 0x8E])})
    app.mouse = fake
    app.mouse.confirmed = {model['name']: {2, 3, 4, 5, 9, 10}}
    app._use_model(model)
    check('grid not known before', 0x40 not in app.buttons)

    app.learn_buttons()
    top = app._learn
    for _ in range(100):
        wait(0.05)
        if top.watch:
            break
    check('mouse read, watching', top.reads and top.reads.get(0x40) == '1' and top.watch and top.watch.tid)
    top.press('1')
    top.press('mouse:back')
    top.press('f22')
    top.press('f23')
    top.press('tilt')
    # one real key press through the Windows hooks (F24: no keyboard has it, nothing reacts)
    u = ctypes.windll.user32
    u.keybd_event(0x87, 0, 0, 0)
    u.keybd_event(0x87, 0, 2, 0)
    wait(0.5)
    check('real F24 press found its button', 0x42 in top.found)
    check('new button gets a name box', top.found[0x40][1] is not None and top.found[0x40][1].get() == 'Button 1')
    check('known button says so', top.found[4][1] is None and top.found[4][3] == 'Mouse Button 4')
    check('several IDs: not guessed', 'F23' in top.unclear and 0x44 not in top.found)
    check('nothing does it: noted', top.missed == ['F22'])
    check('tilt it can\'t put back: not offered', 0x34 in top.found and top.found[0x34][1] is None)
    top.found[0x40][1].set('Thumb 1')
    wait()
    from PIL import ImageGrab
    ImageGrab.grab(window=u.GetParent(top.winfo_id())).save(f'{sys.argv[1]}_learn.png')

    top.add.invoke()
    wait()
    check('added to the mouse', app.buttons.get(0x40) == ('Thumb 1', '1') and app.buttons.get(0x42) == ('Button F24', 'f24'))
    check('saved in settings', app.cfg['learned'][model['name']] == {'64': ['Thumb 1', '1'], '66': ['Button F24', 'f24']})
    fr.check_cfg(app.cfg)  # raises if the saved shape is wrong
    check('changeable now', 0x40 in app.editable and 0x40 + rs.HS in app.editable and 0x40 in fake.writable())
    check('shown under the picture', 0x40 in app.labels)
    app.clipboard_clear()
    opened = []
    fr.os.startfile = opened.append
    send_btn = [w for f in top.winfo_children() for w in f.winfo_children()
                if isinstance(w, fr.ttk.Button) and w.cget('text') == 'Send to GitHub'][0]
    send_btn.invoke()
    text = app.clipboard_get()
    print(text, flush=True)
    check('list for GitHub', '0x40: 1 (Thumb 1)' in text and 'F22' in text and '0x44, 0x45' in text)
    from urllib.parse import urlsplit, parse_qs
    url = urlsplit(opened[0]) if opened else None
    q = parse_qs(url.query) if url else {}
    print('  link', len(opened[0]) if opened else 0, 'chars', flush=True)
    check('opens a filled-in issue', url and url.netloc == 'github.com' and url.path == '/JSa25/freerazer/issues/new'
          and q['template'] == ['buttons.yml'] and q['mouse'] == [model['name']] and q['pid'] == ['0x00a7']
          and q['buttons'] == [text] and q['title'] == [f'Buttons for {model["name"]}'])
    form = open(os.path.join(here, '.github', 'ISSUE_TEMPLATE', 'buttons.yml'), encoding='utf-8').read()
    fields = set(re.findall(r'^\s+id: (\w+)$', form, re.M))
    check('every field in the link is on the form', set(q) - {'template', 'title'} <= fields)
    top.close()
    check('closing stops watching', not top.winfo_exists() and top.watch.tid is None)

    app.cfg['profiles']['Learn test'] = {}
    app.load_profile('Learn test')
    app.select(0x40)
    app.record('f5')
    check('learned button set', app.edit.get('64') == 'f5')
    app.put_on_mouse('Learn test')
    check('written to the mouse', fake.get_action(0x40) == 'f5')
    app.close_popover()
    rs.LEARNED.clear()
    rs.LEARNED.update({n: {int(b): tuple(v) for b, v in d.items()} for n, d in app.cfg['learned'].items()})
    check('loads back from settings', rs.model_for(0x00A7)['buttons'][0x40] == ('Thumb 1', '1'))
    bad = dict(app.cfg, learned={'x': {'not a number': ['a', 'b']}})
    try:
        fr.check_cfg(bad)
        check('bad learned data refused', False)
    except ValueError:
        check('bad learned data refused', True)
    check('no errors logged', not (os.path.exists(fr.LOG) and os.path.getsize(fr.LOG) > log_size))
    print('ALL OK' if all(ok) else 'SOME FAILED', flush=True)
    app.after(200, app.quit_app)


app.after(800, run)
app.mainloop()
