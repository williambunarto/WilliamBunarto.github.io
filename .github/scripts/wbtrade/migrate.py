import sqlite3, re, sys

DB = '/home/ubuntu/wbtrade/data/trade.db'
conn = sqlite3.connect(DB)
existing = [r[1] for r in conn.execute('PRAGMA table_info(trades)').fetchall()]
for col, typ in [
    ('market', 'TEXT'), ('trade_type', 'TEXT'), ('qty', 'REAL'),
    ('opening_fee', 'REAL'), ('closing_fee', 'REAL'),
    ('funding_fee', 'REAL'), ('trade_datetime', 'DATETIME'),
]:
    if col not in existing:
        conn.execute(f'ALTER TABLE trades ADD COLUMN {col} {typ}')
        print(f'Added: {col}')
    else:
        print(f'Skip: {col}')
conn.commit()
conn.close()
print('Migration done')

with open('/home/ubuntu/wbtrade/database.py') as f:
    src = f.read()

if 'trade_datetime' not in src:
    new_fields = (
        '    # Bybit import fields\n'
        '    market             = Column(String)\n'
        '    trade_type         = Column(String)\n'
        '    qty                = Column(Float)\n'
        '    opening_fee        = Column(Float)\n'
        '    closing_fee        = Column(Float)\n'
        '    funding_fee        = Column(Float)\n'
        '    trade_datetime     = Column(DateTime)\n'
    )
    src2 = re.sub(
        r'\n+class DailyBias\(Base\):',
        '\n' + new_fields + '\n\nclass DailyBias(Base):',
        src
    )
    if src2 != src:
        with open('/home/ubuntu/wbtrade/database.py', 'w') as f:
            f.write(src2)
        print('database.py patched')
    else:
        print('ERROR: DailyBias marker not found')
else:
    print('database.py already patched')
