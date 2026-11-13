"""A mouse that leaves one settings read unanswered (GitHub issue 2, DeathAdder V2 X HyperSpeed) still shows as
connected, with only that setting blank, and the read is logged once; a mouse that answers nothing shows as not
connected, also logged once. Stand-in mouse; nothing is written to a real mouse, the settings file or the log.
    py -3.13 reads_test.py"""
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
fr.log_event = lambda text: logged.append(text) if 'read got no answer' in text else None  # only what read_info logs

app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: True
app.deiconify()
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('ok  ' if cond else 'FAIL', name, flush=True)


def mouse(timeout=()):
    da = rs.model_for(0x009C)
    fake = rs.Mouse()
    fake.dev, fake.model, fake.txn = rs._FakeDev(timeout=timeout), da, 0x1F
    fake.dev.actions = {b: rs.encode(a) for b, (_, a) in da['buttons'].items()}
    fake.confirmed = {}
    rs.mice = lambda: []  # a reconnect after a failed read finds nothing; the stand-in stays open below
    fake._connect = lambda: None
    app.mouse = fake
    app._use_model(da)
    return da


def show():
    global info
    try:
        info = app.read_info()
    except OSError:
        info = None
    app._device_done(info)
    app.update()
    return app.dev_lbl.cget('text')


def run():
    da = mouse(timeout={(0x07, 0x81)})  # low power level: no answer
    app._connected = True
    text = show()
    print('  header:', text, '| log:', logged, flush=True)
    check('one read unanswered: still connected', text.startswith('Battery'))
    check('battery and DPI still read', info[0] is not None and info[1] is not None)
    check('power saving blank', info[4] is None)
    check('logged which read', logged == [f'{da["name"]}: power saving read got no answer: '
                                          'the mouse did not answer (status 0x04); is it asleep?'])
    show()
    check('logged once, not every refresh', len(logged) == 1)

    logged.clear()
    mouse(timeout={(0x07, 0x80), (0x07, 0x83), (0x07, 0x81), (0x04, 0x85), (0x00, 0x85), (0x00, 0xC0)})
    text = show()
    print('  header:', text, '| log:', logged, flush=True)
    check('nothing answers: not connected', text == 'Mouse not connected')
    check('logged that nothing answered', len(logged) == 1 and ': every read got no answer' in logged[0])
    show()
    check('that also once', len(logged) == 1)
    print('ALL OK' if all(ok) else 'SOME FAILED', flush=True)
    app.after(200, app.quit_app)


app.after(800, run)
app.mainloop()
