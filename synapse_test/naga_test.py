"""Naga V2 HyperSpeed in the app, on a stand-in mouse that answers the factory scan from GitHub issue 1: all 20
changeable buttons unlock, the grid, thumb and tilt buttons show under the picture, a grid button can be set, and
a profile puts every factory action back exactly. Nothing is written to a real mouse; settings file untouched.
    py -3.13 naga_test.py out_prefix"""
import ctypes, importlib.util, os, sys
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
spec = importlib.util.spec_from_file_location('fr', os.path.join(here, 'freerazer.pyw'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
rs = fr.rs
fr.App.check_updates = lambda self, manual=False: None
fr.App.refresh_device = lambda self, repeat=True: None
ctypes.windll.shcore.SetProcessDpiAwareness(1)
app = fr.App()
app.write_cfg = lambda: True
app.deiconify()
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('ok  ' if cond else 'FAIL', name, flush=True)


def run():
    naga = rs.model_for(0x00B4)
    check(f'database + layout: {naga["name"]}, {len(naga["buttons"])} buttons', naga.get('layout') and len(naga['buttons']) == 21)
    fake = rs.Mouse()
    fake.dev, fake.model, fake.txn, fake.confirmed = rs._FakeDev(), naga, 0x1F, {}
    fake.dev.store = 'layers'
    fake.dev.actions = {b: rs.encode(a) for b, (_, a) in naga['buttons'].items()}  # factory state
    app.mouse = fake
    app._use_model(naga)
    app.read_mouse()
    std = [b for b in app.editable if not b & rs.HS]
    check(f'all 20 buttons unlocked ({len(std)})', len(std) == 20 and 4 not in app.buttons)
    check('mouse read as Default', app.cfg['active'] == 'default' or 'Default' in app.status.cget('text'))
    shown = [app.canvas.itemcget(app.labels[b][0], 'text') for b in (0x0B, 0x34, 0x40, 0x4B)]
    print('  labels:', shown, flush=True)
    check('More buttons labels', shown == ['Top Thumb Button:  DPI (factory)', 'Tilt Left:  Tilt (factory)',
                                            'Side Button 1:  1', 'Side Button 12:  ='])
    app.update_idletasks()
    c = app.canvas
    bottom = max(c.bbox(app.labels[b][0])[3] for b in app.labels)
    check(f'every label inside the canvas ({bottom} <= {c.winfo_height()})', bottom <= c.winfo_height())
    check(f'window tall enough ({app.winfo_height()} >= {app.minsize()[1]})', app.winfo_height() >= app.minsize()[1])
    app.cfg['profiles']['Naga test'] = {}
    app.load_profile('Naga test')
    app.select(0x40)
    check('grid button opens its editor', app.pop_open and app.btn_name.cget('text') == 'Side Button 1')
    app.record('f13')
    app.close_popover()
    fake.dev.sent.clear()
    app.put_on_mouse('Naga test')
    sets = [p for p in fake.dev.sent if p[6:8] == b'\x02\x0c']
    check(f'{len(sets)} normal buttons written, none on HyperShift', len(sets) == 20 and not any(p[10] for p in sets))
    check('F13 on Side Button 1', fake.get_action(0x40) == 'f13')
    check('factory actions written back exactly', all(fake.get_action(b) == a for b, (_, a) in naga['buttons'].items()
                                                      if b not in (1, 0x40)))
    print('  status:', app.status.cget('text'), flush=True)
    print('all ok' if all(ok) else 'SOME FAILED', flush=True)
    app.quit_app()


app.after(4000, run)
app.mainloop()
