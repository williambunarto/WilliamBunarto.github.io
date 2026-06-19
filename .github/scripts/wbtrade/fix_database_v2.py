import re, sys

PATH = '/home/ubuntu/wbtrade/database.py'
with open(PATH) as f:
    src = f.read()

print(f'database.py size: {len(src)} bytes')

# The 7 new field names we need inside the Trade class
NEW_FIELDS = ['market', 'trade_type', 'qty', 'opening_fee', 'closing_fee', 'funding_fee', 'trade_datetime']

# Check runtime attribute presence
sys.path.insert(0, '/home/ubuntu/wbtrade')
try:
    import importlib
    import database as db_mod
    importlib.reload(db_mod)
    Trade = db_mod.Trade
    missing = [f for f in NEW_FIELDS if not hasattr(Trade, f)]
    print(f'Trade class missing attributes: {missing}')
except Exception as e:
    missing = NEW_FIELDS
    print(f'Import failed: {e}')

if not missing:
    print('All attributes present on Trade class - nothing to do')
    sys.exit(0)

# Step 1: Remove any module-level (unindented) occurrences of new field definitions
lines = src.splitlines()
cleaned = []
for line in lines:
    # Remove lines like: market          = Column(...)
    stripped = line.lstrip()
    is_module_level_col = (
        not line.startswith(' ') and
        not line.startswith('#') and
        any(line.startswith(f + ' ') or line.startswith(f + '=') or line.startswith(f + '\t') 
            for f in NEW_FIELDS) and
        'Column' in line
    )
    if is_module_level_col:
        print(f'Removing module-level line: {repr(line[:80])}')
    else:
        cleaned.append(line)
src = '\n'.join(cleaned)

# Step 2: Find the plan_id column line inside the Trade class (has 4-space indent)
plan_id_pattern = re.compile(r'^([ \t]+plan_id\s*=\s*Column.*)', re.MULTILINE)
m = plan_id_pattern.search(src)
if not m:
    print('ERROR: Could not find plan_id column in Trade class')
    print('=== Full database.py ===')
    print(src)
    sys.exit(1)

plan_id_line = m.group(1)
# Determine the indentation used by plan_id
indent = re.match(r'^([ \t]+)', plan_id_line).group(1)
print(f'Found plan_id line with indent={repr(indent)}: {plan_id_line[:60]}')

# Step 3: Build new column definitions with same indentation
new_cols = '\n'.join([
    f'{indent}market         = Column(Text,    nullable=True)',
    f'{indent}trade_type     = Column(Text,    nullable=True)',
    f'{indent}qty            = Column(Float,   nullable=True)',
    f'{indent}opening_fee    = Column(Float,   nullable=True)',
    f'{indent}closing_fee    = Column(Float,   nullable=True)',
    f'{indent}funding_fee    = Column(Float,   nullable=True)',
    f'{indent}trade_datetime = Column(DateTime, nullable=True)',
])

# Step 4: Insert after plan_id line
src = src.replace(plan_id_line, plan_id_line + '\n' + new_cols, 1)

# Verify syntax
import ast
try:
    ast.parse(src)
    print('Syntax check: OK')
except SyntaxError as e:
    print(f'Syntax ERROR: {e}')
    sys.exit(1)

with open(PATH, 'w') as f:
    f.write(src)
print(f'database.py written ({len(src)} bytes)')

# Verify at runtime
try:
    import importlib, database as db2
    importlib.reload(db2)
    Trade2 = db2.Trade
    still_missing = [f for f in NEW_FIELDS if not hasattr(Trade2, f)]
    if still_missing:
        print(f'STILL MISSING after fix: {still_missing}')
    else:
        print('All attributes now present on Trade class - SUCCESS')
except Exception as e:
    print(f'Post-fix import error: {e}')
