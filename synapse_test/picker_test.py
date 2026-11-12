"""UI check with both mice plugged in: resize speed, editor following the picture, the two drop-down menus,
and switching mice (picture redrawn). Read-only on the mice; settings file untouched.
    py -3.13 picker_test.py out_prefix"""
import ctypes, importlib.util, os, sys, time
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
fr.App.check_updates = lambda self, manual=False: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: None
app.deiconify()
app.attributes('-topmost', True)


def shot(name, pad=0):
    from PIL import ImageGrab
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab((x, y, x + app.winfo_width(), y + app.winfo_height() + pad)).save(f'{sys.argv[1]}_{name}.png')


def state(name):
    pic = bool(app.canvas.itemcget(app.art_item, 'image'))
    print(f'{name}: picker {app.mouse_btn.cget("text")!r} shown={bool(app.mouse_pick.winfo_ismapped())} | model '
          f'{app.model["name"]} | talking to {app.mouse.model and app.mouse.model["name"]} | picture drawn={pic} | '
          f'lighting shown={bool(app.light_box.winfo_ismapped())}', flush=True)


def resize():
    print('window', app.winfo_width(), app.winfo_height(), 'minsize', app.minsize(), flush=True)
    for page in ('buttons', 'performance'):
        app.show_page(page)
        if page == 'buttons':
            app.select(app.editable[1])
        app.update()
        times = []
        for w, h in [(1400, 1000), (1200, 900), (1600, 1100)]:
            t = time.perf_counter()
            app.geometry(f'{w}x{h}')
            app.update()
            times.append(round((time.perf_counter() - t) * 1000))
        print(page, 'ms per resize:', times, flush=True)
    app.show_page('buttons'); app.select(app.editable[1]); app.update()
    pop_x, cv_x = app.pop.winfo_x(), app.canvas.winfo_x()
    app.geometry('1200x900'); app.update(); app.update()
    print('editor moved with picture:', app.pop.winfo_x() - pop_x == app.canvas.winfo_x() - cv_x, flush=True)
    shot('resized')
    app.close_popover()
    app.after(500, menus)


def menus():
    state('start')
    app.mouse_menu()
    app.after(600, lambda: (shot('mousemenu', 150), close_and(dots)))


def close_and(then):
    for w in app.winfo_children():
        if isinstance(w, fr.tk.Toplevel):
            w.destroy()
    app.after(300, then)


def dots():
    app.profile_menu()
    app.after(600, lambda: (shot('dotsmenu', 150), close_and(switch)))


def switch():
    other = next(pid for pid, _ in app._mice if pid not in app.model['pids'])
    first = app.model['pids'][0]
    app.on_pick_mouse(other)
    app.after(4000, lambda: (state('picked'), shot('picked'), app.on_pick_mouse(first),
                             app.after(4000, lambda: (state('back'), app.quit_app()))))


app.after(4000, resize)
app.mainloop()
