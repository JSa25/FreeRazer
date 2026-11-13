"""HyperShift in the app, on a stand-in mouse: make Mouse Button 5 the HyperShift key on Standard, put F9 on Mouse
Button 4 on the HyperShift layer, and check what would go to the mouse. Nothing is written to a real mouse and the
settings file is untouched.
    py -3.13 hypershift_test.py out_prefix"""
import ctypes, importlib.util, os, sys
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
app = fr.App()
import test_screen; test_screen.place(app)  # FR_TEST_SCREEN: keep test windows on a chosen monitor
app.write_cfg = lambda: True
app.deiconify()
app.attributes('-topmost', True)
ok = []
HS = rs.HS


def check(name, cond):
    ok.append(bool(cond))
    print('ok  ' if cond else 'FAIL', name, flush=True)


def shot(name):
    from PIL import ImageGrab
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab((x, y, x + app.winfo_width(), y + app.winfo_height())).save(f'{sys.argv[1]}_{name}.png')


def run():
    fake = rs.Mouse()
    fake.dev, fake.model, fake.txn = rs._FakeDev(), rs.DEVICES[0], 0x1F
    app.mouse = fake
    app._use_model(rs.DEVICES[0])
    app.show_page('buttons')
    check('Standard/HyperShift switch shown', app.layer_row.winfo_ismapped())
    app.cfg['profiles']['HS test'] = {}
    app.load_profile('HS test')
    app.refresh_list()
    # Standard: Mouse Button 5 -> Razer HyperShift through the Mouse list
    app.select(5)
    app.mode_var.set('mouse'); app.show_mode()
    check('HyperShift offered on Standard', 'hypershift' in app.pick_items)
    app.pick_box.current(app.pick_items.index('hypershift')); app.pick_action(None)
    check('saved as button 5', app.edit.get('5') == 'hypershift')
    shot('standard')
    # HyperShift layer
    app.layer_var.set(HS); app.set_layer()
    import time; time.sleep(0.3); app.update()  # let the labels finish fading in
    check('HyperShift key locked on the HyperShift layer', app.labels and app.canvas.itemcget(app.labels[5][0], 'fill') == fr.DIM)
    app.select(5)
    check('clicking it explains', 'HyperShift key' in app.last_status and not app.pop_open)
    app.select(4)
    app.mode_var.set('mouse'); app.show_mode()
    check('HyperShift not offered on the HyperShift layer', 'hypershift' not in app.pick_items)
    app.record('f9')
    check('saved on the HyperShift layer', app.edit.get(str(4 + HS)) == 'f9' and '4' not in app.edit)
    check('popover names the layer', app.btn_name.cget('text') == 'Mouse Button 4 (HyperShift)')
    app.close_popover()
    shot('hypershift')
    app.layer_var.set(0); app.set_layer()
    check('Standard still shows Mouse Button 4', app.effective(4)[0] == 'mouse:back')
    # what goes on the mouse
    app.put_on_mouse('HS test')
    sent = [p[8:15].hex(' ') for p in fake.dev.sent if p[6:8] == b'\x02\x0c']
    check(f'14 buttons written ({len(sent)})', len(sent) == 14)
    check('HyperShift key on both layers', '01 05 00 0c 01 01 00' in sent and '01 05 01 0c 01 01 00' in sent)
    check('F9 on HyperShift layer button 4', '01 04 01 02 02 00 42' in sent and '01 04 00 01 01 04 00' in sent)
    print('status:', app.last_status, flush=True)
    # any other mouse: the DeathAdder V2 Pro on stand-ins, one that has the layer and one that ignores it
    da = rs.model_for(0x007D)
    for store, has in (('layers', True), ('ignore', False)):
        app.mouse.hs, app.cfg['hypershift'] = {}, {}
        fake = rs.Mouse()
        fake.dev, fake.model, fake.txn, fake.hs = rs._FakeDev(), da, 0x1F, app.mouse.hs
        fake.dev.store = store
        app.mouse = fake
        app.model = rs.DEVICES[0]  # so _use_model rebuilds
        app._use_model(da)
        app.load_profile('HS test')
        check(f'{store}: switch shown before anything is known', app.layer_row.winfo_ismapped())
        app.put_on_mouse('HS test')
        check(f'{store}: learned and saved', app.cfg['hypershift'] == {da['name']: has})
        check(f'{store}: switch {"kept" if has else "hidden"}', app.layer_row.winfo_ismapped() == has)
        normal = {b: fake.get_action(b) for b in rs.editable(da) if not b & HS}
        want = {b: 'hypershift' if b == 5 else a for b, a in rs.resolve({}, None, da).items() if not b & HS}
        check(f'{store}: normal buttons right on the mouse', normal == (want if has else {
            b: a for b, a in rs.resolve({}, None, da).items() if not b & HS}))
        print('  status:', app.last_status, flush=True)
        app.read_mouse()
        check(f'{store}: read back as the profile', app.cfg['active'] == 'HS test' or not has)
        if not has:
            app.select(5); app.mode_var.set('mouse'); app.show_mode()
            check('ignore: HyperShift no longer offered', 'hypershift' not in app.pick_items)
            app.close_popover()
    print('all ok' if all(ok) else 'SOME FAILED', flush=True)
    app.quit_app()


app.after(4000, run)
app.mainloop()
