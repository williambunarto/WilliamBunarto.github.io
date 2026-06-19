import sqlite3

conn = sqlite3.connect('/home/ubuntu/wbtrade/data/trade.db')
count = conn.execute('SELECT COUNT(*) FROM trades').fetchone()[0]
total = conn.execute(
    'SELECT ROUND(SUM(pnl_usdt),2) FROM trades WHERE pnl_usdt IS NOT NULL'
).fetchone()[0]
mkts = [
    r[0] for r in conn.execute(
        'SELECT DISTINCT market FROM trades WHERE market IS NOT NULL ORDER BY market'
    ).fetchall()
]
liq = conn.execute(
    "SELECT COUNT(*) FROM trades WHERE trade_type='Liquidation'"
).fetchone()[0]
print(f'Total trades : {count}')
print(f'Total PnL    : {total} USDT')
print(f'Liquidations : {liq}')
print(f'Markets      : {mkts}')
conn.close()
