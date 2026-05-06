
import json
from collections import Counter

data = json.load(open('petitions_parsed.json'))
statuses = Counter(p.get('_parse_status', 'missing') for p in data)
print('Parse status breakdown:')
for s, n in sorted(statuses.items()):
    print(f'  {s:10s}: {n}')

empty = [p for p in data if p.get('_parse_status') == 'empty']
print('Sample of empty PIDs:')
for p in empty[:10]:
    print(f'  PID {p["pid"]:5d} | close_date: {p.get("close_date")} | sigs: {p.get("signatures")}')

pids = sorted(p['pid'] for p in data)
gaps = [(pids[i], pids[i+1], pids[i+1]-pids[i]) for i in range(len(pids)-1) if pids[i+1]-pids[i] > 5]
print('Large PID gaps:')
for start, end, size in gaps[:15]:
    print(f'  {start} -> {end}  (gap of {size})')

