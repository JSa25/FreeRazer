"""Pop-ups close on a click outside them and on their own opener; clicks inside keep them. Sends nothing to a mouse."""
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
app._send = lambda write, done, keep=None: None
app.deiconify()
app.attributes('-topmost', True)
results = []


def popups():
    return [w for w in app.winfo_children() if isinstance(w, fr.tk.Toplevel) and w.winfo_exists()]


def click(widget):
    widget.event_generate('<Button-1>', x=5, y=5)
    widget.event_generate('<ButtonRelease-1>', x=5, y=5)


def check(name, want_open):
    ok = bool(popups()) == want_open
    results.append(ok)
    print(('ok  ' if ok else 'FAIL'), name, flush=True)


steps = [
    lambda: (app.show_page('performance'), app.light_box.pack(anchor='w', before=app.perf_note), app.show_color()),
    lambda: click(app.swatch),
    lambda: check('chip opens the picker', True),
    lambda: click(next(w for w in popups()[0].winfo_children() if isinstance(w, fr.tk.Canvas))),
    lambda: check('click inside keeps it open', True),
    lambda: click(app.perf_note),
    lambda: check('click on the page closes it', False),
    lambda: click(app.swatch),
    lambda: check('chip opens it again', True),
    lambda: click(app.swatch),
    lambda: check('chip closes it', False),
    lambda: app.profile_menu(),
    lambda: check('profile menu opens', True),
    lambda: click(app.dpi_scale),
    lambda: check('click on a slider closes the menu', False),
    lambda: (print('all ok' if all(results) else 'SOME FAILED', flush=True), app.quit_app()),
]


def run(i=0):
    steps[i]()
    if i + 1 < len(steps):
        app.after(300, run, i + 1)


app.after(2500, run)
app.mainloop()
