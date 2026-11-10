"""DPI stage test on both mice: one stage, then three stages with only the active one changed. Restores after."""
import time
import razer_switch as rs
from mouse_state import open_mouse

import sys
for pid in [int(p, 16) for p in sys.argv[1:]] or (0xE6, 0x7D):
    m = open_mouse(pid)
    name = m.model['name']
    before = (m.dpi(), m.dpi_stages())
    print(f'{name} before: dpi {before[0]} stages {before[1]}')
    try:
        m.set_dpi(1000); time.sleep(0.2)
        print('  set_dpi(1000), one stage ->', m.dpi(), m.dpi_stages())
        m.call(rs.stages_packet(2, [(400, 400), (800, 800), (1600, 1600)], m.txn)); time.sleep(0.2)
        print('  three stages, active 2  ->', m.dpi(), m.dpi_stages())
        m.set_dpi(900); time.sleep(0.2)
        print('  set_dpi(900)            ->', m.dpi(), m.dpi_stages())
    finally:
        x = before[0][0]
        m.call(rs.stages_packet(1, [(x, x)], m.txn)); time.sleep(0.2)
        after = (m.dpi(), m.dpi_stages())
        print(f'  restored: {after == before}  {after}')
        m.dev.close()
