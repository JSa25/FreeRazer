"""Where test windows open. Set FR_TEST_SCREEN=x,y,width,height (a monitor's desktop rectangle) to keep the test
window, and the pop-ups placed from it, entirely on that monitor; unset, tests open where Windows puts them.
The window is shrunk to fit if needed, so size-checking tests (resize_test) are only meaningful unset."""
import os


def place(app):
    spot = os.environ.get('FR_TEST_SCREEN')
    if not spot:
        return
    x, y, w, h = map(int, spot.split(','))
    app.update_idletasks()
    app.minsize(1, 1)
    app.geometry(f'{min(app.winfo_reqwidth(), w - 40)}x{min(app.winfo_reqheight(), h - 80)}+{x + 20}+{y + 20}')
    app.update_idletasks()
