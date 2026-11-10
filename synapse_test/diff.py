"""List what is in snapshot B but not in snapshot A (added) and the reverse (removed)."""
import json, sys
a, b = (json.load(open(p, encoding='utf-8-sig')) for p in sys.argv[1:3])
for key in a:
    if key == 'pnpdrv':  # pnputil prints 3 lines per driver package: compare packages, not lines
        def packages(lines):
            out, cur = set(), []
            for line in lines:
                cur.append(line.split(':', 1)[1].strip() if ':' in line else line)
                if line.startswith('Provider Name'):
                    out.add(' | '.join(cur)); cur = []
            return out
        added, removed = packages(b[key]) - packages(a[key]), packages(a[key]) - packages(b[key])
    else:
        added, removed = set(b[key]) - set(a[key]), set(a[key]) - set(b[key])
    for x in sorted(added):
        print(f'+ {key}: {x}')
    for x in sorted(removed):
        print(f'- {key}: {x}')
