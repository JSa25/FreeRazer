"""Lighting section on the DeathAdder V2 Pro, driven through the app's own handlers. Puts the logo back after.
    py -3.13 light_test.py shot.png"""
import ctypes, importlib.util, os, sys, time
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
orig = fr.rs.mice
fr.rs.mice = lambda: [i for i in orig() if i['product_id'] == 0x7D]
fr.App.check_updates = lambda self, manual=False: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: None
app.show_window() if hasattr(app, 'show_window') else app.deiconify()
app.attributes('-topmost', True)
m = app.mouse


def step(name, then, wait=2500):
    def go():
        print(name, '->', m.lighting(), flush=True)
        app.after(wait, then)
    return go


def shot():
    from PIL import ImageGrab
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab((x, y, x + app.winfo_width(), y + app.winfo_height())).save(sys.argv[1])
    print('section shown:', bool(app.light_box.winfo_ismapped()), 'effect:', app.light_var.get(),
          'brightness:', app.bright.get(), flush=True)


def blue():
    app._rgb = (0, 0, 255); app.light_var.set('static'); app.light_changed()
    app.after(1500, step('static blue', breathe))


def breathe():
    app.light_var.set('breathing'); app.light_changed()
    app.after(1500, step('breathing blue', dim))


def dim():
    app.bright.set(10); app.bright_changed()
    app.after(1500, step('brightness 10', restore))


def restore():
    app.light_var.set('spectrum'); app.light_changed()
    app.bright.set(33); app.bright_changed()  # 33% = byte 84, the original
    app.after(1500, step('restored', app.quit_app, 500))


def start():
    app.show_page('performance')
    app.after(500, lambda: (shot(), blue()))


app.after(4000, start)
app.mainloop()
