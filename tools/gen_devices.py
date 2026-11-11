"""Builds devices.json, FreeRazer's mouse database, from OpenRazer's source (GPL-2.0; only facts are taken:
device IDs, names and which command and transaction ID the driver sends for each feature).

    py -3.13 tools/gen_devices.py razermouse_driver.c razermouse_driver.h mouse.py [out.json]

razermouse_driver.c / .h: openrazer/driver/;  mouse.py: openrazer/daemon/openrazer_daemon/hardware/mouse.py.
A feature is listed for a mouse only when the driver sends that mouse the same bytes FreeRazer sends
(checked against razerchromacommon.c: battery 07/80, charging 07/84, DPI 04/85 and 04/05, stages 04/86 and
04/06, polling 00/85+00/05 or 00/C0+00/40, sleep 07/83+07/03, low power 07/81+07/01, lighting 0F/02 and
brightness 0F/04+0F/84 on the extended matrix). Anything else the driver does differently is left out."""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import openrazer_parse as op

LEDS = {'logo': 0x04, 'scroll': 0x01, 'backlight': 0x05, 'left': 0x11, 'right': 0x10}


def txn_of(body):
    found = set(int(t, 16) for t in re.findall(r'transaction_id\.id\s*=\s*(0x[0-9a-fA-F]+)', body))
    return found.pop() if len(found) == 1 else None


def build(c_src, h_src, py_src):
    fns = op.functions(c_src)
    pids = op.pid_values(h_src)
    daemon = op.daemon_devices(py_src)
    by_value = {v: k for k, v in pids.items()}

    def case(fn, sym, i=0):
        """Body of the switch case `sym` is in (i-th switch of the function), or None if it isn't listed."""
        sw = fns[fn]['switches']
        return sw[i].get(sym) if i < len(sw) else None

    def plain(fn, sym, call=None, i=0):
        """Transaction ID when the PID's case only sets one and (if given) calls `call` exactly; else None."""
        body = case(fn, sym, i)
        if body is None or 'return -EINVAL' in body:
            return None
        if call and not re.search(rf'\b{call}\(', body):
            return None
        return txn_of(body)

    mice = []
    for pid, d in sorted(daemon.items()):
        sym = by_value.get(pid)
        if not sym:
            continue
        m, feats, txn = set(d['methods']), [], {}
        entry = {'pid': pid, 'name': d['name']}
        if d['dpi_max']:
            entry['dpi_max'] = d['dpi_max']

        t1, t2 = plain('razer_attr_read_charge_level', sym), plain('razer_attr_read_charge_status', sym)
        if 'get_battery' in m and t1 is not None:
            feats.append('battery')
            txn['0780'] = t1
            if t2 is not None:
                txn['0784'] = t2

        rd = plain('razer_attr_read_dpi', sym, 'razer_chroma_misc_get_dpi_xy')
        special = case('razer_attr_write_dpi', sym, 0)  # byte-sized and odd DPI mice return early here
        wr = plain('razer_attr_write_dpi', sym, None, 1)
        if {'get_dpi_xy', 'set_dpi_xy'} <= m and rd is not None and wr is not None and \
                (special is None or 'return' not in special):
            feats.append('dpi')
            body = case('razer_attr_read_dpi', sym)
            entry['dpi_read_store'] = 1 if 'get_dpi_xy(VARSTORE)' in body else 0
            txn['0485'], txn['0405'] = rd, wr
            rs_, ws_ = plain('razer_attr_read_dpi_stages', sym), plain('razer_attr_write_dpi_stages', sym)
            if {'get_dpi_stages', 'set_dpi_stages'} <= m and rs_ is not None and ws_ is not None:
                feats.append('stages')
                txn['0486'], txn['0406'] = rs_, ws_

        if {'get_poll_rate', 'set_poll_rate'} <= m:
            classic = (plain('razer_attr_read_poll_rate', sym, 'razer_chroma_misc_get_polling_rate'),
                       plain('razer_attr_write_poll_rate', sym, 'razer_chroma_misc_set_polling_rate'))
            v2 = (plain('razer_attr_read_poll_rate', sym, 'razer_chroma_misc_get_polling_rate2'),
                  plain('razer_attr_write_poll_rate', sym, 'razer_chroma_misc_set_polling_rate2'))
            if None not in classic:
                feats.append('poll')
                entry['poll'] = 'classic'
                txn['0085'], txn['0005'] = classic
            elif None not in v2:
                feats.append('poll')
                entry['poll'] = 'v2'
                txn['00c0'], txn['0040'] = v2
                again = case('razer_attr_write_poll_rate', sym, 1)  # some mice get the set twice: argument 00 then 01
                if again and txn_of(again) is not None:
                    entry['poll_again_txn'] = txn_of(again)

        idle = (plain('razer_attr_read_device_idle_time', sym), plain('razer_attr_write_device_idle_time', sym))
        low = (plain('razer_attr_read_charge_low_threshold', sym), plain('razer_attr_write_charge_low_threshold', sym))
        if {'get_idle_time', 'set_idle_time'} <= m and None not in idle:
            feats.append('sleep')
            txn['0783'], txn['0703'] = idle
        if {'get_low_battery_threshold', 'set_low_battery_threshold'} <= m and None not in low:
            feats.append('low_power')
            txn['0781'], txn['0701'] = low

        # lighting: every effect FreeRazer offers, on the extended matrix, with one transaction ID throughout
        effects = (plain('razer_attr_write_matrix_effect_static_common', sym, 'razer_chroma_extended_matrix_effect_static'),
                   plain('razer_attr_write_matrix_effect_none_common', sym, 'razer_chroma_extended_matrix_effect_none'),
                   plain('razer_attr_write_matrix_effect_spectrum_common', sym, 'razer_chroma_extended_matrix_effect_spectrum'),
                   plain('razer_attr_write_matrix_effect_breath_common', sym, None, 1))
        breath = case('razer_attr_write_matrix_effect_breath_common', sym, 0) or ''
        bright = (plain('razer_attr_read_led_brightness', sym, 'razer_chroma_extended_matrix_get_brightness'),
                  plain('razer_attr_write_led_brightness', sym, 'razer_chroma_extended_matrix_brightness'))
        leds = [led for name, led in LEDS.items()
                if {f'set_{name}_static', f'set_{name}_none', f'set_{name}_spectrum', f'set_{name}_breath_single',
                    f'get_{name}_brightness', f'set_{name}_brightness'} <= m]
        if leds and None not in effects and len(set(effects)) == 1 and None not in bright and \
                'razer_chroma_extended_matrix_effect_breathing_single(' in breath:
            feats.append('light')
            entry['leds'] = leds
            txn['0f02'], txn['0f84'], txn['0f04'] = effects[0], *bright

        if feats:
            entry['features'], entry['txn'] = feats, txn
        mice.append(entry)
    return {'version': int(time.strftime('%Y%m%d')), 'source': 'openrazer', 'mice': mice}


if __name__ == '__main__':
    c, h, py = (open(p, encoding='utf-8', errors='replace').read() for p in sys.argv[1:4])
    db = build(c, h, py)
    out = sys.argv[4] if len(sys.argv) > 4 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                             'devices.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=1)
    n = len(db['mice'])
    print(f'{n} mice, {sum("features" in m for m in db["mice"])} with features -> {out}')
    from collections import Counter
    print(Counter(f for m in db['mice'] for f in m.get('features', [])))
