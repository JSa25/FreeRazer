"""Coexistence test: optionally apply test settings with FreeRazer's code, then read both mice every
10 s for N seconds and report any change from what was applied, plus every failed read.
    py -3.13 watch.py apply 120     |   py -3.13 watch.py watch 60"""
import json, sys, time
from mouse_state import open_mouse, state

mode, seconds = sys.argv[1], int(sys.argv[2])
TEST = {'buttons4': 'f24', 'polling': 500, 'sleep': 6}
mice = {0xE6: 'Viper V4 Pro', 0x7D: 'DeathAdder V2 Pro'}

if mode == 'apply':
    for pid, name in mice.items():
        m = open_mouse(pid)
        m.set_action(4, TEST['buttons4'])
        m.set_polling(TEST['polling'])
        m.set_sleep(TEST['sleep'])
        time.sleep(0.5)
        print(name, 'applied ->', m.get_action(4), m.polling(), m.power())
        m.dev.close()

errors, changes = 0, []
end = time.time() + seconds
while time.time() < end:
    for pid, name in mice.items():
        m = open_mouse(pid)
        if not m:
            errors += 1
            changes.append((time.strftime('%H:%M:%S'), name, 'not answering'))
            continue
        s = state(m)
        m.dev.close()
        errors += len(s['errors'])
        got = {'buttons4': s.get('buttons', {}).get(4), 'polling': s.get('polling'), 'sleep': (s.get('power') or [None])[0]}
        diff = {k: v for k, v in got.items() if v != TEST[k]}
        if diff or s['errors']:
            changes.append((time.strftime('%H:%M:%S'), name, diff, s['errors']))
    time.sleep(10)
print('failed reads:', errors)
print('changes from the applied settings:', json.dumps(changes, indent=1) if changes else 'none')
