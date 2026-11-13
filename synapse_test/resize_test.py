"""Resize the window through a range of sizes on each page, time each redraw, screenshot the extremes.
Read-only on the mouse; settings file untouched.    py -3.13 resize_test.py out_prefix"""
import ctypes, importlib.util, os, sys, time
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
fr.log_event = lambda text: None  # what the app logs about the mouse stays out of the real error.log
fr.App.check_updates = lambda self, manual=False: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: None
app.deiconify()
app.attributes('-topmost', True)


def shot(name):
    from PIL import ImageGrab
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab((x, y, x + app.winfo_width(), y + app.winfo_height())).save(f'{sys.argv[1]}_{name}.png')


def run():
    print('natural size', app.winfo_width(), app.winfo_height(), 'minsize', app.minsize(), flush=True)
    for page in ('buttons', 'performance'):
        app.show_page(page)
        if page == 'buttons':
            app.select(app.editable[1])  # editor open, to see if it follows the window
        app.update()
        times = []
        for w, h in [(1400, 1000), (1100, 900), (800, 700), (600, 500), (1600, 1100)]:
            t = time.perf_counter()
            app.geometry(f'{w}x{h}')
            app.update()
            times.append(round((time.perf_counter() - t) * 1000))
            if (w, h) in ((600, 500), (1600, 1100)):
                shot(f'{page}_{w}')
        print(page, 'ms per resize:', times, flush=True)
    app.quit_app()


app.after(3000, run)
app.mainloop()
