"""Screenshots of the Lighting section with the colour picker in a few states. Sends nothing to any mouse.
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
app.write_cfg = lambda: None
app._send = lambda write, done: print('would send:', done, flush=True)
app.deiconify()
app.attributes('-topmost', True)


def shot(name):
    from PIL import ImageGrab
    app.update()
    b = app.light_box
    x, y = b.winfo_rootx(), b.winfo_rooty()
    ImageGrab.grab((x - 10, y - 10, x + app.winfo_width() - 20, y + b.winfo_height() + 10)).save(f'{sys.argv[1]}_{name}.png')
    print(name, app.light_var.get(), app._rgb, 'hue', app.hue.get(), flush=True)


def run():
    app.show_page('performance')
    app.light_box.pack(anchor='w', before=app.perf_note)
    app.light_var.set('spectrum'); app.show_color(); app.bright.set(33)
    shot('start')
    app.hue_sliding(210); app.hue.set(210); app.light_changed()
    shot('hue210')
    app.pick_color((255, 255, 255))
    shot('white')
    app.quit_app()


app.after(2500, run)
app.mainloop()
