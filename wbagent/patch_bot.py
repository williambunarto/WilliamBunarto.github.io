"""patch_bot.py — inject BTC signal handlers into bot.py (idempotent, syntax-safe)."""
import os
import shutil
import subprocess
import sys
import tempfile

BOT = "/home/ubuntu/bot.py"
BAK = BOT + ".pre_btc_signal.bak"
MARKER = "# BTC_SIGNAL_INJECTED"

if not os.path.exists(BOT):
    print("WARN: bot.py not found")
    sys.exit(0)

with open(BOT) as f:
    content = f.read()

if MARKER in content:
    print("Already patched — nothing to do")
    sys.exit(0)

# Backup original
shutil.copy(BOT, BAK)
print("Backed up to", BAK)

# Find last TOP-LEVEL import line (not indented)
lines = content.split("\n")
last_import = -1
for i, line in enumerate(lines):
    s = line.strip()
    if (s.startswith("import ") or s.startswith("from ")) and not line[0:1] in (" ", "\t"):
        last_import = i

if last_import < 0:
    print("ERROR: no top-level imports found in bot.py")
    sys.exit(1)

print("Last top-level import at line", last_import, ":", repr(lines[last_import]))

# Build import injection block (safe string, no f-string to avoid brace issues)
import_lines = [
    "",
    MARKER,
    "try:",
    "    from btc_signal_handlers import register_btc_handlers as _register_btc",
    "    _BTC_SIGNAL_OK = True",
    "except Exception as _btc_err:",
    "    print('[WARN] btc_signal_handlers not loaded: ' + str(_btc_err))",
    "    _BTC_SIGNAL_OK = False",
    "",
]

new_lines = lines[:last_import + 1] + import_lines + lines[last_import + 1:]
content = "\n".join(new_lines)

# Find run_polling line and inject registration BEFORE it (with matching indent)
injected = False
for var in ("application", "app", "updater"):
    pattern = var + ".run_polling"
    if pattern not in content:
        continue
    all_lines = content.split("\n")
    for idx, ln in enumerate(all_lines):
        if pattern in ln:
            indent = len(ln) - len(ln.lstrip())
            pad = " " * indent
            inject_lines = [
                pad + "# BTC signal handlers",
                pad + "if _BTC_SIGNAL_OK:",
                pad + "    _register_btc(" + var + ")",
                "",
            ]
            all_lines = all_lines[:idx] + inject_lines + all_lines[idx:]
            content = "\n".join(all_lines)
            injected = True
            print("Injected before line", idx, ":", repr(ln.strip()))
            break
    if injected:
        break

if not injected:
    print("WARNING: run_polling not found — appending registration at end")
    content += "\n# BTC signal handlers (fallback)\nif _BTC_SIGNAL_OK:\n    _register_btc(application)\n"

# Verify syntax on temp file before overwriting bot.py
with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
    tmp.write(content)
    tmpname = tmp.name

result = subprocess.run(
    ["python3", "-m", "py_compile", tmpname],
    capture_output=True, text=True
)
os.unlink(tmpname)

if result.returncode != 0:
    print("ERROR: patch would create a SyntaxError — aborting to protect bot.py")
    print(result.stderr)
    sys.exit(1)

with open(BOT, "w") as f:
    f.write(content)
print("bot.py patched and syntax verified OK")
