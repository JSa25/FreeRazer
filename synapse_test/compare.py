import json, sys
a, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
for mouse in ('Viper V4 Pro', 'DeathAdder V2 Pro'):
    x, y = a[mouse], b[mouse]
    if isinstance(y, str) or isinstance(x, str): print(mouse, x if isinstance(x, str) else y); continue
    diffs = {k: (x.get(k), y.get(k)) for k in set(x) | set(y) if k not in ('battery', 'errors') and x.get(k) != y.get(k)}
    print(f'{mouse}: {diffs or "unchanged"} | read errors: {y["errors"]}')
