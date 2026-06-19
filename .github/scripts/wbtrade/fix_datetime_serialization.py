# Fix: trade_datetime in _trade_dict may be a string (SQLite TEXT) not a datetime object.
# Replace the isoformat() call with a safe version that handles both.

path = '/home/ubuntu/wbtrade/routers/trades.py'
with open(path) as f:
    src = f.read()

old = '        "trade_datetime": t.trade_datetime.isoformat() if t.trade_datetime else None,'
new = '        "trade_datetime": (t.trade_datetime.isoformat() if hasattr(t.trade_datetime, "isoformat") else str(t.trade_datetime)) if t.trade_datetime else None,'

if old in src:
    src = src.replace(old, new)
    with open(path, 'w') as f:
        f.write(src)
    print('Fixed: trade_datetime serialization patched')
elif 'hasattr(t.trade_datetime' in src:
    print('Already fixed')
else:
    print('WARNING: pattern not found, checking what is there:')
    for i, line in enumerate(src.splitlines(), 1):
        if 'trade_datetime' in line:
            print(f'  line {i}: {line.rstrip()}')
