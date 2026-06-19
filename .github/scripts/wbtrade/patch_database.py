import re, ast

PATH = '/home/ubuntu/wbtrade/database.py'

with open(PATH) as f:
    src = f.read()

print(f'database.py size: {len(src)} bytes')
print('Has market column:', 'market' in src)

if 'market' in src:
    print('database.py already has new columns - OK')
else:
    # Find the last field before we need to insert new ones
    # Look for plan_id column and insert after it
    old = '    plan_id         = Column(Integer, ForeignKey("plans.id"), nullable=True)'
    if old not in src:
        # Try without nullable
        for line in src.splitlines():
            if 'plan_id' in line and 'Column' in line:
                print(f'Found plan_id line: {repr(line)}')
                old = line
                break
    
    new_cols = '''
    market          = Column(Text,    nullable=True)
    trade_type      = Column(Text,    nullable=True)
    qty             = Column(Float,   nullable=True)
    opening_fee     = Column(Float,   nullable=True)
    closing_fee     = Column(Float,   nullable=True)
    funding_fee     = Column(Float,   nullable=True)
    trade_datetime  = Column(DateTime, nullable=True)'''
    
    if old in src:
        src = src.replace(old, old + new_cols, 1)
        with open(PATH, 'w') as f:
            f.write(src)
        print(f'database.py patched ({len(src)} bytes)')
    else:
        print('ERROR: could not find plan_id column in database.py')
        print('=== database.py content ===')
        print(src)

# Verify syntax
try:
    ast.parse(src)
    print('database.py syntax: OK')
except SyntaxError as e:
    print(f'database.py syntax ERROR: {e}')
