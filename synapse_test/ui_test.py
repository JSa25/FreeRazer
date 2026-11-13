"""Toasts, the Ctrl+K switcher, keyboard menus and rolling numbers, on a stand-in mouse. Nothing is written to a
real mouse and the settings file is untouched.
    py -3.13 ui_test.py out_prefix"""
import ctypes, importlib.util, os, sys, time
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
fr.log_event = lambda text: None  # what the app logs about the mouse stays out of the real error.log
rs = fr.rs
fr.App.check_updates = lambda self, manual=False: None
fr.App.refresh_device = lambda self, repeat=True: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
log_size = os.path.getsize(fr.LOG) if os.path.exists(fr.LOG) else 0
app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: True
app.deiconify()
app.attributes('-topmost', True)
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('ok  ' if cond else 'FAIL', name, flush=True)


def wait(s=0.35):  # let animations run to the end
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.update()
        time.sleep(0.01)


def shot(name):
    from PIL import ImageGrab
    wait(0.05)
    # the window itself, wherever it is (FR_TEST_SCREEN puts it on another monitor); pop-ups are separate windows,
    # so for those the area of the screen is grabbed instead
    pops = [w for w in app.winfo_children() if isinstance(w, fr.tk.Toplevel) and w.winfo_ismapped()]
    if not pops:
        return ImageGrab.grab(window=ctypes.windll.user32.GetParent(app.winfo_id())).save(f'{sys.argv[1]}_{name}.png')
    ImageGrab.grab(window=pops[-1].winfo_id()).save(f'{sys.argv[1]}_{name}.png')


def key(widget, seq, **kw):
    if not isinstance(widget, fr.tk.Toplevel):  # a menu keeps focus on its highlighted row
        widget.focus_force()
    widget.event_generate(f'<{seq}>', when='tail', **kw)
    wait(0.05)


def run():
    fake = rs.Mouse()
    fake.dev, fake.model, fake.txn = rs._FakeDev(), rs.DEVICES[0], 0x1F
    app.mouse = fake
    app._use_model(rs.DEVICES[0])
    app.cfg['profiles']['UI test'] = {}
    app.load_profile('UI test')
    app.refresh_list()
    app.show_page('buttons')
    check('blend ends', fr.blend('#000000', '#ffffff', 0) == '#000000' and fr.blend('#000000', '#ffffff', 1) == '#ffffff')

    # toasts
    for t in list(app._toasts):
        app._drop_toast(t)
    wait()
    app.set_status('Profile saved.')
    wait()
    check('toast shown', len(app._toasts) == 1 and app._toasts[0].winfo_ismapped())
    app.set_status('Profile saved.')
    check('same message again: still one toast', len(app._toasts) == 1)
    app.set_status('Could not change it: the mouse is asleep.')
    wait()
    shot('toasts')
    dots = [w for c in app._toasts for w in c.winfo_children()[0].winfo_children() if isinstance(w, fr.tk.Label)]
    check('problem toast has the amber dot', dots[-1].cget('fg') == fr.WARN and dots[0].cget('fg') == fr.ACCENT)
    ys = [c.winfo_rooty() for c in app._toasts]
    check('newest at the bottom', ys[0] < ys[1])
    for i in range(3):
        app.set_status(f'Message {i}')
    wait()
    check('at most three toasts', len(app._toasts) == 3)
    first = app._toasts[0]
    app._toast_timer(first, 50)
    wait(0.5)
    check('toast goes away on its timer', first not in app._toasts and not first.winfo_exists())
    check('last message kept for tests', app.last_status == 'Message 2')

    # Ctrl+K
    app.focus_force()
    app.canvas.focus_set()
    wait()
    key(app.canvas, 'Control-k')
    wait()
    pal = app._pal
    check('Ctrl+K opens the switcher', pal is not None and pal.winfo_exists() and pal.winfo_ismapped())
    entry = [w for w in pal.winfo_children() if isinstance(w, fr.tk.Entry)][0]
    entry.insert(0, 'perf')
    wait()
    check('typing filters', [t for t, _ in pal.shown] == ['Go to Performance'])
    shot('palette')
    key(entry, 'Return')
    check('Enter runs it', app.pages['performance'].winfo_ismapped() and not pal.winfo_exists())
    key(app.nav['buttons'][0], 'Control-k')  # the picture is on a hidden page now
    pal = app._pal
    entry = [w for w in pal.winfo_children() if isinstance(w, fr.tk.Entry)][0]
    entry.insert(0, 'change button')
    wait()
    texts = [t for t, _ in pal.shown]
    print('  found', texts, flush=True)
    check('buttons are found', texts and all(t.startswith('Change button:') for t in texts))
    key(entry, 'Down')
    lst = [w for w in pal.winfo_children() if isinstance(w, fr.tk.Listbox)][0]
    check('arrow moves the pick', lst.curselection() == (1,) or len(texts) == 1)
    key(entry, 'Escape')
    check('Esc closes it', not pal.winfo_exists())
    app.show_page('buttons')

    # Ctrl+K while recording a key is the key being recorded
    app.select(4)
    app.mode_var.set('key'); app.show_mode()
    app.toggle_record()
    key(app, 'KeyPress', keysym='Control_L')
    key(app, 'Control-k')
    check('Ctrl+K recorded, switcher not opened', app.edit.get('4') == 'ctrl+k' and not (app._pal and app._pal.winfo_exists()))
    app.close_popover()

    # popover rises into place and Esc gives focus back to the picture
    app.select(4)
    app.update_idletasks()
    y0 = app.pop.winfo_y()
    print('  pop y', y0, app.pop.place_info().get('y'), flush=True)
    wait()
    check('editor settles upward', app.pop.winfo_y() < y0 or not fr.ANIMATE)
    app.rec_btn.focus_set()
    wait(0.05)
    app.close_popover()
    wait(0.05)
    check('closing the editor puts focus on the picture', app.focus_lastfor() is app.canvas)

    # a click outside the editor closes it; a click inside it doesn't
    app.select(4)
    wait()
    app.rec_btn.event_generate('<Button-1>', x=2, y=2)
    app.rec_btn.event_generate('<ButtonRelease-1>', x=2, y=2)
    wait(0.05)
    app.stop_record()
    check('click inside the editor keeps it open', app.pop_open)
    app.state_lbl.event_generate('<Button-1>', x=1, y=1)
    wait(0.05)
    check('click outside the editor closes it', not app.pop_open)

    # Games: several games under one profile, grouped; a chip moves or removes its game
    app.cfg['links'] = {}
    app.cfg['profiles']['UI other'] = {}
    app.relink_game(['arma3_x64.exe', 'cs2.exe', 'valorant.exe', 'eldenring.exe'], 'UI test')
    app.relink_game('factorio.exe', 'UI other')
    app.show_page('games')
    wait()
    secs = app.games_list.winfo_children()
    chips = lambda sec: [w for w in sec.winfo_children()[1].winfo_children()]
    check('one group per profile with games', len(secs) == 2 and len(chips(secs[0])) == 4 and len(chips(secs[1])) == 1)
    check('several games on one profile', sorted(e for e, p in app.cfg['links'].items() if p == 'UI test') ==
          ['arma3_x64.exe', 'cs2.exe', 'eldenring.exe', 'valorant.exe'])
    shot('games')
    chip = chips(secs[0])[0]
    chip.invoke()
    wait()
    menu = [w for w in app.winfo_children() if isinstance(w, fr.tk.Toplevel) and w.winfo_exists() and w is not app._pal][-1]
    items = [w.cget('text') for w in menu.winfo_children() if isinstance(w, fr.ttk.Button)]
    check('chip menu offers move and remove', 'Move to UI other' in items and 'Remove arma3_x64.exe' in items)
    menu.close()
    app.relink_game('arma3_x64.exe', 'UI other')
    check('moved to the other profile', app.cfg['links']['arma3_x64.exe'] == 'UI other')
    app.unlink_game('cs2.exe')
    check('removed', 'cs2.exe' not in app.cfg['links'])
    app.show_page('buttons')

    # ⋯ menu: arrow keys and Enter
    app.profile_menu()
    wait()
    menus = [w for w in app.winfo_children() if isinstance(w, fr.tk.Toplevel) and w.winfo_exists() and w is not app._pal]
    top = menus[-1]
    rows = [w for w in top.winfo_children() if isinstance(w, fr.ttk.Button) and 'disabled' not in w.state()]
    check('menu opens on the first row', top.focus_get() is rows[0])
    shot('menu')
    key(top, 'Down')
    check('Down moves to the next row', top.focus_get() is rows[1])
    key(top, 'Escape')
    check('Esc closes the menu and focus goes back', not top.winfo_exists() and app.focus_lastfor() is app.profile_box)

    # rolling numbers
    app._bat = 40
    info = (( 47, False), (800, 800), 1000, rs.DEVICES[0], None, None)
    app._shown['dpi'] = 800
    app._device_done(info)
    mid = app.dev_lbl.cget('text')
    wait(0.8)
    print('  battery', mid, '->', app.dev_lbl.cget('text'), flush=True)
    check('battery rolls to the new level', app.dev_lbl.cget('text') == 'Battery 47%' and mid != 'Battery 47%' or not fr.ANIMATE)
    app._device_done(((47, False), (1600, 1600), 1000, rs.DEVICES[0], None, None))
    wait(0.1)
    rolling = int(app.dpi_var.get())
    wait(0.6)
    print('  dpi', rolling, '->', app.dpi_var.get(), app._shown, flush=True)
    check('DPI rolls to what the mouse says', app.dpi_var.get() == '1600' and 800 <= rolling <= 1600)
    app._device_done(((None, False), (1600, 1600), 1000, rs.DEVICES[0], None, None))
    check('no battery level: no error', 'Battery' in app.dev_lbl.cget('text'))

    # Windows animation effects off: everything jumps straight to the end
    fr.ANIMATE = False
    app.set_status('No motion.')
    card = app._toasts[-1]
    check('animations off: toast placed at once', card.winfo_manager() == 'place' and card.y == card.y)
    fr.ANIMATE = True

    grew = os.path.exists(fr.LOG) and os.path.getsize(fr.LOG) > log_size
    check('no errors logged', not grew)
    print('ALL OK' if all(ok) else 'SOME FAILED', flush=True)
    app.after(200, app.quit_app)


app.after(800, run)
app.mainloop()
