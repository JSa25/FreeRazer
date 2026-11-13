"""Crash logging and the lighting put-back, with a stand-in mouse (nothing is sent to a real one).
Writes its log to a temp file, not the real error.log."""
import ctypes, importlib.util, os, sys, tempfile, threading, types
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
fr.log_event = lambda text: None  # what the app logs about the mouse stays out of the real error.log
fr.LOG = os.path.join(tempfile.mkdtemp(), 'error.log')
fr.App.check_updates = lambda self, manual=False: None
fr.App.refresh_device = lambda self, repeat=True: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: None
ok = []


def check(name, cond):
    ok.append(cond)
    print('ok  ' if cond else 'FAIL', name, flush=True)


def log():
    return open(fr.LOG, encoding='utf-8').read() if os.path.exists(fr.LOG) else ''


def window_error():
    app.after(10, lambda: 1 / 0)
    app.after(300, thread_error)


def thread_error():
    check('window error logged', 'error in the window' in log() and 'ZeroDivisionError' in log())
    check('window error shown', 'Something went wrong' in app.last_status)
    app.set_status('')
    t = threading.Thread(target=lambda: [][1])
    t.start(); t.join()
    app.after(800, after_thread)


def after_thread():
    check('background error logged', 'error in background work' in log() and 'IndexError' in log())
    check('background error shown', 'Something went wrong' in app.last_status)
    with open(fr.LOG, 'a', encoding='utf-8') as f:
        f.write('x' * 80 + '\n' * 1 + ('y' * 99 + '\n') * 8000)  # ~800 KB
    try:
        raise KeyError('cap test')
    except KeyError:
        fr.log_error('cap test')
    size = os.path.getsize(fr.LOG)
    check(f'log capped ({size} bytes)', size < fr.LOG_MAX and log().endswith("KeyError: 'cap test'\n\n"))
    try:
        put_back()
    except Exception:
        import traceback
        traceback.print_exc()
        app.quit_app()


def put_back():
    da = fr.rs.model_for(0x7D)
    sent = []
    want = app.resolved(app.cfg.get('active', 'default'))
    real = app.mouse
    app.mouse = types.SimpleNamespace(lock=threading.RLock(), set_dpi=None, set_polling=None, set_sleep=None, set_low_power=None,model=da, get_action=lambda b: want.get(b), write=lambda w: sent.append('buttons'),
                                      set_lighting=lambda e, rgb: sent.append(('light', e, rgb)),
                                      set_brightness=lambda v: sent.append(('bright', v)))
    app.cfg['keep'] = {da['name']: {'light': ['static', [255, 0, 0]], 'bright': 33}}
    app.model, app.editable = da, app.editable_for(da)  # the put-back only runs for the mouse the window shows
    info = ((50, False), (800, 800), 1000, da, (5, 5), ('other', (0, 0, 0), 20))
    fixed = app.keep_settings(info)
    check(f'Synapse lighting put back {fixed} {sent}',
          fixed == ['lighting', 'brightness'] and sent == [('light', 'static', (255, 0, 0)), ('bright', 33)])
    sent.clear()
    same = ((50, False), (800, 800), 1000, da, (5, 5), ('static', (255, 0, 0), 33))
    check('nothing written when unchanged', app.keep_settings(same) == [] and not sent)
    app.cfg['keep'][da['name']]['light'] = ['spectrum', [0, 255, 0]]
    rainbow = ((50, False), (800, 800), 1000, da, (5, 5), ('spectrum', (0, 0, 0), 33))
    check('rainbow has no colour to compare', app.keep_settings(rainbow) == [])
    print('all ok' if all(ok) else 'SOME FAILED', flush=True)
    app.mouse = real
    app.quit_app()


app.after(2000, window_error)
app.mainloop()
