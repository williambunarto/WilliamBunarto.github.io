import sqlite3, urllib.request, urllib.error, json, ast, os, subprocess

# 1. DB schema + data
conn = sqlite3.connect('/home/ubuntu/wbtrade/data/trade.db')
cols = [r[1] for r in conn.execute('PRAGMA table_info(trades)').fetchall()]
print('=== SCHEMA ===')
print('Columns:', cols)
required = ['market','trade_type','qty','opening_fee','closing_fee','funding_fee','trade_datetime']
missing = [c for c in required if c not in cols]
print('Missing new cols:', missing if missing else 'NONE - all present')

print('=== DATA ===')
print('Total:', conn.execute('SELECT COUNT(*) FROM trades').fetchone()[0])
print('PnL total:', conn.execute('SELECT ROUND(SUM(pnl_usdt),2) FROM trades').fetchone()[0])
conn.close()

# 2. Syntax check
print('=== SYNTAX ===')
for path in ['/home/ubuntu/wbtrade/routers/trades.py', '/home/ubuntu/wbtrade/database.py']:
    try:
        src = open(path).read()
        ast.parse(src)
        print(f'{path.split("/")[-1]}: OK ({len(src)} bytes)')
    except SyntaxError as e:
        print(f'{path.split("/")[-1]}: SYNTAX ERROR line {e.lineno}: {e.msg}')

# 3. Check trade_datetime lines in trades.py
print('=== TRADE_DATETIME IN TRADES.PY ===')
trades_src = open('/home/ubuntu/wbtrade/routers/trades.py').read()
for i, line in enumerate(trades_src.splitlines(), 1):
    if 'trade_datetime' in line:
        print(f'  L{i}: {line.rstrip()}')

# 4. API response - capture error body
print('=== API RESPONSE ===')
try:
    resp = urllib.request.urlopen('http://127.0.0.1:8001/api/trades/')
    data = json.loads(resp.read())
    print('HTTP 200, trade count:', len(data))
    if data:
        print('Keys:', sorted(data[0].keys()))
        print('Has market:', 'market' in data[0])
        sample = {k: data[0][k] for k in ['market','direction','pnl_usdt','trade_datetime'] if k in data[0]}
        print('Sample:', sample)
except urllib.error.HTTPError as e:
    body = e.read().decode('utf-8', errors='replace')[:2000]
    print(f'HTTP {e.code}: {body}')
except Exception as e:
    print('Error:', e)

# 5. Import endpoint
print('=== IMPORT ENDPOINT ===')
try:
    req = urllib.request.Request('http://127.0.0.1:8001/api/trades/import', method='POST', data=b'')
    try:
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        print(f'POST /import -> HTTP {e.code}')
except Exception as e:
    print('Error:', e)

# 6. Service journal (last 20 lines)
print('=== SERVICE JOURNAL ===')
result = subprocess.run(['sudo', 'journalctl', '-u', 'wbtrade', '-n', '20', '--no-pager', '--output=short'],
                       capture_output=True, text=True)
print(result.stdout[-3000:] if result.stdout else result.stderr[:1000])
