"""Copy mouse report in the app: press it, wait, check the clipboard holds the probe report and only reads were
sent. Reads the real mouse; writes nothing to it. The settings file is untouched.
    py -3.13 report_test.py out_prefix"""
import ctypes, importlib.util, os, sys
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
rs = fr.rs
fr.App.check_updates = lambda self, manual=False: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
sent = []
real_transact = rs.transact
rs.transact = lambda dev, pkt, tries=25: (sent.append(bytes(pkt[6:8])), real_transact(dev, pkt, tries))[1]
app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: True
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


def start():
    app.refresh_device = lambda repeat=True: None
    app.show_page('settings')
    sent.clear()
    app.report_btn.invoke()
    check('button disabled while reading', 'disabled' in app.report_btn.state())
    app.after(500, wait)


def wait(n=0):
    if 'disabled' in app.report_btn.state() and n < 120:
        return app.after(500, wait, n + 1)
    text = app.clipboard_get()
    print(text[:600], '\n…', flush=True)
    check('report copied', text.startswith(f'FreeRazer {fr.APP_VERSION}\nRazer HID devices:') and 'PID 0x00e6' in text)
    check('every button ID read', all(f'  {b:#04x} ' in text for b in range(1, 0x80)))
    check(f'only reads sent ({len(sent)} commands)', sent and all(c[1] & 0x80 for c in sent))
    check('status says copied', 'copied' in app.last_status)
    check('no errors logged', not os.path.exists(fr.LOG) or 'mouse report' not in open(fr.LOG, encoding='utf-8').read())
    shot('settings')
    print('all ok' if all(ok) else 'SOME FAILED', flush=True)
    app.quit_app()


app.after(5000, start)
app.mainloop()
