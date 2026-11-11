"""Reads OpenRazer's mouse driver (razermouse_driver.c) and daemon device list (mouse.py) into plain data:
    functions(c_source) -> {function name: {PID name: [body text of every switch case that PID is in]}}
    pid_values(header)  -> {PID name: number}
    daemon_devices(py)  -> {PID number: {'name', 'methods', 'dpi_max'}}
Used by gen_devices.py. Plain text parsing; the C file is never compiled or run."""
import ast
import re

FUNC = re.compile(r'^static ssize_t (razer_attr_\w+)\(', re.M)


def _block(text, start):
    """Text between the brace that opens at or after `start` and its matching close."""
    i = text.index('{', start)
    depth = 0
    for j in range(i, len(text)):
        depth += {'{': 1, '}': -1}.get(text[j], 0)
        if depth == 0:
            return text[i + 1:j]
    raise ValueError('unbalanced braces')


def _strip_comments(c):
    c = re.sub(r'/\*.*?\*/', '', c, flags=re.S)
    return re.sub(r'//[^\n]*', '', c)


def switch_cases(body):
    """[{PID name: case body}] for each `switch(device->usb_pid)` in a function body; 'default' included."""
    out = []
    for m in re.finditer(r'switch\s*\(\s*(?:device->usb_pid|usb_dev->descriptor\.idProduct)\s*\)', body):
        sw = _block(body, m.end())
        cases, labels, text = {}, [], []
        for line in sw.split('\n'):
            lab = re.match(r'\s*case\s+(USB_DEVICE_ID_\w+)\s*:', line)
            dflt = re.match(r'\s*default\s*:', line)
            if lab or dflt:
                if text and any(t.strip() for t in text):
                    for l in labels:
                        cases[l] = '\n'.join(text)
                    labels, text = [], []
                labels.append(lab.group(1) if lab else 'default')
            else:
                text.append(line)
        for l in labels:
            cases[l] = '\n'.join(text)
        out.append(cases)
    return out


def functions(c_source):
    c = _strip_comments(c_source)
    out = {}
    for m in FUNC.finditer(c):
        out[m.group(1)] = {'body': _block(c, m.end()), 'switches': switch_cases(_block(c, m.end()))}
    return out


def pid_values(header):
    return {m.group(1): int(m.group(2), 16)
            for m in re.finditer(r'#define\s+(USB_DEVICE_ID_RAZER_\w+)\s+0x([0-9A-Fa-f]+)', header)}


def daemon_devices(py_source):
    """Classes in openrazer's daemon mouse.py, inheritance resolved."""
    tree = ast.parse(py_source)
    raw = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        d = {'base': node.bases[0].id if node.bases and isinstance(node.bases[0], ast.Name) else None,
             'doc': ast.get_docstring(node) or ''}
        for st in node.body:
            if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name):
                d[st.targets[0].id] = st.value
        raw[node.name] = d

    def get(cls, key):
        while cls in raw:
            if key in raw[cls]:
                return raw[cls][key], cls
            cls = raw[cls]['base']
        return None, None

    def methods(cls):
        v, owner = get(cls, 'METHODS')
        if v is None:
            return []
        if isinstance(v, ast.List):
            return [e.value for e in v.elts if isinstance(e, ast.Constant)]
        if isinstance(v, ast.BinOp):  # Parent.METHODS + [...]
            left = methods(raw[owner]['base']) if isinstance(v.left, ast.Attribute) else []
            right = [e.value for e in v.right.elts if isinstance(e, ast.Constant)] if isinstance(v.right, ast.List) else []
            return left + right
        return []

    out = {}
    for cls, d in raw.items():
        pid, _ = get(cls, 'USB_PID')
        if not isinstance(pid, ast.Constant):
            continue
        dpi, _ = get(cls, 'DPI_MAX')
        m = re.search(r'Class for the (Razer [^\n]+)', d['doc'])
        # no docstring of its own: the class name spelled out ('RazerBasiliskUltimateReceiver' ->
        # 'Razer Basilisk Ultimate Receiver')
        name = m.group(1).strip() if m else re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])', ' ', cls)
        out[pid.value] = {'name': name, 'methods': methods(cls),
                          'dpi_max': dpi.value if isinstance(dpi, ast.Constant) else None}
    return out
