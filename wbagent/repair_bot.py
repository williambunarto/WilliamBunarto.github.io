"""repair_bot.py — restore bot.py from backup if it has a SyntaxError."""
import os
import shutil
import subprocess
import sys

BOT = "/home/ubuntu/bot.py"
BAK = BOT + ".pre_btc_signal.bak"

if not os.path.exists(BOT):
    print("WARN: bot.py not found")
    sys.exit(0)

result = subprocess.run(
    ["python3", "-m", "py_compile", BOT],
    capture_output=True, text=True
)

if result.returncode == 0:
    print("bot.py syntax OK — no repair needed")
    sys.exit(0)

print("SYNTAX ERROR detected in bot.py:")
print(result.stderr)

if not os.path.exists(BAK):
    print("ERROR: no backup found at", BAK)
    sys.exit(1)

print("Restoring from backup:", BAK)
shutil.copy(BAK, BOT)

result2 = subprocess.run(
    ["python3", "-m", "py_compile", BOT],
    capture_output=True, text=True
)
if result2.returncode == 0:
    print("Backup restored — bot.py syntax OK")
else:
    print("ERROR: backup is also broken:", result2.stderr)
    sys.exit(1)
