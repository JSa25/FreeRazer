"""Screenshots of the Lighting section and the detailed colour picker. Sends nothing to any mouse.
    py -3.13 color_look.py out_prefix"""
import ctypes, importlib.util, os, sys
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
fr.App.check_updates = lambda self, manual=False: None
fr.App.refresh_device = lambda self, repeat=True: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: None
app._send = lambda write, done, keep=None: print('would send:', done, app._rgb, flush=True)
app.deiconify()
app.attributes('-topmost', True)


def picker():
    return next((w for w in app.winfo_children() if isinstance(w, fr.tk.Toplevel) and w.winfo_exists()), None)


def shot(name):
    from PIL import ImageGrab
    app.update()
    boxes = [(app.winfo_rootx(), app.winfo_rooty(), app.winfo_rootx() + app.winfo_width(), app.winfo_rooty() + app.winfo_height())]
    p = picker()
    if p:
        boxes.append((p.winfo_rootx(), p.winfo_rooty(), p.winfo_rootx() + p.winfo_width(), p.winfo_rooty() + p.winfo_height()))
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    ImageGrab.grab((x0, max(y0, app.light_box.winfo_rooty() - 330), x1, y1)).save(f'{sys.argv[1]}_{name}.png')
    print(name, app.light_var.get(), app._rgb, flush=True)


def ev(widget, x, y):
    return type('E', (), {'x': x, 'y': y, 'widget': widget})()


def run():
    app.show_page('performance')
    app.light_box.pack(anchor='w', before=app.perf_note)
    app.light_var.set('spectrum'); app.show_color(); app.bright.set(33); app.bright_val.configure(text='33%')
    shot('row')
    app.open_picker()
    app.after(500, step2)


def step2():
    shot('picker')
    p = picker()
    sv = next(w for w in p.winfo_children() if isinstance(w, fr.tk.Canvas) and not isinstance(w, fr.HueSlider))
    hue = next(w for w in p.winfo_children() if isinstance(w, fr.HueSlider))
    hue._move(280); hue._let_go()  # purple
    sv.event_generate('<Button-1>', x=60, y=30); sv.event_generate('<ButtonRelease-1>', x=60, y=30)
    app.after(300, lambda: (shot('picked'), app.quit_app()))


app.after(2500, run)
app.mainloop()
