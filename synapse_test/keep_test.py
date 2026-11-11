"""Fake Synapse overwriting a mouse, then check the app's keep_settings() puts it back. Settings file untouched."""
import ctypes, importlib.util, os, sys, time
pid = int(sys.argv[1], 16)
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
orig = fr.rs.mice
fr.rs.mice = lambda: [i for i in orig() if i['product_id'] == pid]
fr.App.check_updates = lambda self, manual=False: None
fr.App.refresh_device = lambda self: None  # this test drives the reads itself
ctypes.windll.shcore.SetProcessDpiAwareness(1)
app = fr.App()
app.write_cfg = lambda: None
m = app.mouse
read = app.read_info


def run():
    before = read()
    (_, _), (x, _), hz, _, (sleep, low), _ = before
    for key, v in (('dpi', x), ('hz', hz), ('sleep', sleep), ('low', low)):
        app.remember(key, v)
    buttons = {b: m.get_action(b) for b in app.editable}
    # what Synapse did when its window showed the mouse
    m.set_action(4, 'f24'); m.set_polling(125); m.set_sleep(7)
    time.sleep(0.5)
    print('after fake Synapse:', m.get_action(4), m.polling(), m.power())
    fixed = app.keep_settings(read())
    time.sleep(0.5)
    after = read()
    print('put back:', fixed)
    print('matches before:', after[1:] == before[1:] and {b: m.get_action(b) for b in app.editable} == buttons)
    app.quit_app()
app.after(3000, run)
app.mainloop()
