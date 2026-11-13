"""Button page with a pretend mouse that has 12 extra side buttons. Nothing is sent to any mouse.
    py -3.13 extra_buttons_test.py out_prefix"""
import ctypes, importlib.util, os, sys, tempfile
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
app.deiconify()
app.attributes('-topmost', True)

base = fr.rs.DEVICES[1]['buttons']
pretend = {'name': 'Pretend 12-button mouse', 'pids': (0xFFFE,), 'txn': 0x1F, 'verified': True, 'drawing': 'generic',
           'buttons': {**base, **{0x40 + i: (f'Side {i + 1}', f'{(i + 1) % 10}') for i in range(12)}}}


def shot(name):
    from PIL import ImageGrab
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab((x, y, x + app.winfo_width(), y + app.winfo_height())).save(f'{sys.argv[1]}_{name}.png')


def run():
    app._use_model(pretend)
    app.update()
    shot('extra')
    app.select(0x45)  # Side 6
    app.after(400, step2)


def step2():
    shot('extra_selected')
    print('window', app.winfo_width(), app.winfo_height(), 'minsize', app.minsize(),
          '| canvas fits:', app.canvas.winfo_height() <= app.pages['buttons'].winfo_height(),
          '| editor open:', app.pop_open, '| errors logged:', os.path.exists(fr.LOG), flush=True)
    app.quit_app()


app.after(2500, run)
app.mainloop()
