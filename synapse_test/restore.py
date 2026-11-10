"""Put both mice back to the settings recorded in mice_before.json, then compare."""
import json, time
import razer_switch as rs
from mouse_state import open_mouse, state

before = json.load(open('mice_before.json'))
for pid, name in ((0xE6, 'Viper V4 Pro'), (0x7D, 'DeathAdder V2 Pro')):
    want = before[name]
    m = open_mouse(pid)
    for b, action in ((b, a) for b, a in want['buttons'].items() if int(b) in rs.editable(m.model)):
        m.set_action(int(b), action)
    x = want['dpi'][0]
    # one stage at the recorded DPI, as it was (Synapse had set five)
    m.call(rs.packet(0x04, 0x06, [0x01, 0x01, 0x01, 0x00, x >> 8, x & 0xFF, x >> 8, x & 0xFF], m.txn))
    m.set_polling(want['polling'])
    m.set_sleep(want['power'][0])
    m.set_low_power(want['power'][1])
    time.sleep(0.5)
    now = state(m)
    m.dev.close()
    same = {k: now[k] == json.loads(json.dumps(want[k])) for k in ('buttons', 'dpi', 'stages', 'polling', 'power')}
    print(name, 'restored:', same, '| errors:', now['errors'])
