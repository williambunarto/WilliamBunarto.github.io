import sqlite3, urllib.request, json, ast, subprocess

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
print('Has market:', conn.execute('SELECT COUNT(*) FROM trades WHERE market IS NOT NULL').fetchone()[0])
print('Has datetime:', conn.execute('SELECT COUNT(*) FROM trades WHERE trade_datetime IS NOT NULL').fetchone()[0])
print('Null entry_price:', conn.execute('SELECT COUNT(*) FROM trades WHERE entry_price IS NULL').fetchone()[0])
print('Null direction:', conn.execute('SELECT COUNT(*) FROM trades WHERE direction IS NULL').fetchone()[0])
print('PnL total:', conn.execute('SELECT ROUND(SUM(pnl_usdt),2) FROM trades').fetchone()[0])
print('Liquidations:', conn.execute("SELECT COUNT(*) FROM trades WHERE trade_type='Liquidation'").fetchone()[0])
for r in conn.execute('SELECT id,market,direction,outcome,pnl_usdt FROM trades ORDER BY id LIMIT 3').fetchall():
    print('  sample:', r)
conn.close()

# 2. Syntax check
print('=== SYNTAX ===')
for path in ['/home/ubuntu/wbtrade/routers/trades.py', '/home/ubuntu/wbtrade/database.py']:
    try:
        src = open(path).read()
        ast.parse(src)
        print(f'{path.split("/")[-1]}: OK ({len(src)} bytes)')
    except SyntaxError as e:
        print(f'{path.split("/")[-1]}: SYNTAX ERROR at line {e.lineno}: {e.msg}')

# 3. Grep key patterns
print('=== CODE PATCHES ===')
trades_src = open('/home/ubuntu/wbtrade/routers/trades.py').read()
db_src = open('/home/ubuntu/wbtrade/database.py').read()
print('database.py has trade_datetime Column:', 'trade_datetime' in db_src)
print('trades.py has market in dict:', '"market": t.market' in trades_src)
print('trades.py has /import endpoint:', '"/import"' in trades_src or "'/import'" in trades_src)
print('trades.py has csv import:', 'import csv' in trades_src)
html_src = open('/home/ubuntu/wbtrade/static/index.html').read()
print('index.html has Import CSV button:', 'importBybitCSV' in html_src)

# 4. API response check
print('=== API RESPONSE ===')
try:
    resp = urllib.request.urlopen('http://127.0.0.1:8001/api/trades/')
    data = json.loads(resp.read())
    print('HTTP 200, trade count:', len(data))
    if data:
        keys = sorted(data[0].keys())
        print('Response keys:', keys)
        print('Has market:', 'market' in data[0])
        print('Has trade_datetime:', 'trade_datetime' in data[0])
        print('Sample trade:', {k: data[0][k] for k in ['market','direction','pnl_usdt','trade_datetime'] if k in data[0]})
except Exception as e:
    print('API ERROR:', e)

# 5. Import endpoint
print('=== IMPORT ENDPOINT ===')
try:
    req = urllib.request.Request('http://127.0.0.1:8001/api/trades/import', method='POST', data=b'')
    try:
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        print(f'POST /import -> HTTP {e.code} (422=correct, 404=missing, 405=wrong method)')
except Exception as e:
    print('Error:', e)

# 6. File sizes
print('=== DATA FILES ===')
import os
for f in sorted(os.listdir('/home/ubuntu/wbtrade/data/')):
    size = os.path.getsize(f'/home/ubuntu/wbtrade/data/{f}')
    print(f'  {f}: {size//1024}KB')
