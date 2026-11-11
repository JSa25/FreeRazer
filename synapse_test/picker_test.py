"""Mouse picker with both mice plugged in: switch to each one and screenshot. Read-only on the mice; settings file untouched.
    py -3.13 picker_test.py out_prefix"""
import ctypes, importlib.util, os, sys
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
fr.App.check_updates = lambda self, manual=False: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
app = fr.App()
app.write_cfg = lambda: None
app.deiconify()
app.attributes('-topmost', True)
print('connected:', fr.rs.connected(), flush=True)


def shot(name):
    from PIL import ImageGrab
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab((x, y, x + app.winfo_width(), y + app.winfo_height())).save(f'{sys.argv[1]}_{name}.png')
    print(name, '| picker shown:', bool(app.mouse_box.winfo_ismapped()), '| picker says:', app.mouse_box.get(),
          '| model:', app.model['name'], '| talking to:', app.mouse.model and app.mouse.model['name'],
          '| lighting shown:', bool(app.light_box.winfo_ismapped()), '|', app.dev_lbl.cget('text'), flush=True)


def pick(i, then):
    app.mouse_box.current(i)
    app.on_pick_mouse()
    app.after(4000, then)


def run():
    app.show_page('performance')
    shot('start')
    other = 1 - app.mouse_box.current()
    pick(other, lambda: (shot('picked'), pick(1 - other, lambda: (shot('back'), app.quit_app()))))


app.after(4000, run)
app.mainloop()
