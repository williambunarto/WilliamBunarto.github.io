import sqlite3, json

conn = sqlite3.connect('/home/ubuntu/wbtrade/data/trade.db')
cols = [r[1] for r in conn.execute('PRAGMA table_info(trades)').fetchall()]
print('=== SCHEMA ===')
print('Columns:', cols)

print('=== DATA COUNTS ===')
print('Total trades:', conn.execute('SELECT COUNT(*) FROM trades').fetchone()[0])
print('Has market:', conn.execute('SELECT COUNT(*) FROM trades WHERE market IS NOT NULL').fetchone()[0])
print('Has datetime:', conn.execute('SELECT COUNT(*) FROM trades WHERE trade_datetime IS NOT NULL').fetchone()[0])
print('Null entry_price:', conn.execute('SELECT COUNT(*) FROM trades WHERE entry_price IS NULL').fetchone()[0])
print('Null direction:', conn.execute('SELECT COUNT(*) FROM trades WHERE direction IS NULL').fetchone()[0])
print('PnL total:', conn.execute('SELECT ROUND(SUM(pnl_usdt),2) FROM trades').fetchone()[0])
print('Liquidations:', conn.execute("SELECT COUNT(*) FROM trades WHERE trade_type='Liquidation'").fetchone()[0])

print('=== MARKETS ===')
mkts = [r[0] for r in conn.execute('SELECT DISTINCT market FROM trades WHERE market IS NOT NULL ORDER BY market').fetchall()]
print(mkts)

print('=== 3 RECENT TRADES ===')
for r in conn.execute('SELECT id,market,direction,outcome,pnl_usdt,trade_datetime FROM trades ORDER BY COALESCE(trade_datetime,\'1970-01-01\') DESC LIMIT 3').fetchall():
    print(' ', r)

conn.close()
