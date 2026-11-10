"""Read-only: every setting FreeRazer knows on each connected verified mouse, as JSON. Counts failed reads.
    py -3.13 mouse_state.py [out.json]"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hid, razer_switch as rs


def open_mouse(pid):
    model = rs.model_for(pid)
    for info in (i for i in hid.enumerate(rs.VID) if i['product_id'] == pid):
        d = hid.device()
        try:
            d.open_path(info['path'])
            if rs.transact(d, rs.read_packet(1, model['txn']))[0] == 0x02:
                m = rs.Mouse()
                m.dev, m.model, m.txn = d, model, model['txn']
                return m
        except OSError:
            pass
        d.close()
    return None


def state(m):
    out, errors = {}, []
    for name, fn in (('buttons', lambda: {b: m.get_action(b) for b in m.model['buttons']}),
                     ('dpi', m.dpi), ('stages', m.dpi_stages), ('polling', m.polling), ('power', m.power),
                     ('battery', m.battery)):
        try:
            out[name] = fn()
        except (OSError, ValueError) as e:
            errors.append(f'{name}: {e}')
    out['errors'] = errors
    return out


if __name__ == '__main__':
    result = {'time': time.strftime('%H:%M:%S')}
    for pid in sorted({d for dev in rs.DEVICES for d in dev['pids']}):
        m = open_mouse(pid)
        result[rs.model_for(pid)['name']] = state(m) if m else 'not answering'
        if m:
            m.dev.close()
    text = json.dumps(result, indent=1, default=str)
    if len(sys.argv) > 1:
        open(sys.argv[1], 'w').write(text)
    print(text)
