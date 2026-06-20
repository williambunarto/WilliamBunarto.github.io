import urllib.request, urllib.error, json, subprocess

print('=== API TEST ===')
try:
    resp = urllib.request.urlopen('http://127.0.0.1:8001/api/trades/')
    data = json.loads(resp.read())
    print('HTTP 200, trades:', len(data))
    if data:
        print('Keys:', sorted(data[0].keys()))
        print('Has market:', 'market' in data[0])
        print('Has trade_datetime:', 'trade_datetime' in data[0])
except urllib.error.HTTPError as e:
    body = e.read().decode('utf-8', errors='replace')[:3000]
    print(f'HTTP {e.code}: {repr(body)}')
except Exception as ex:
    print(f'Error: {ex}')

print('=== JOURNAL ===')
result = subprocess.run(
    ['sudo', 'journalctl', '-u', 'wbtrade', '-n', '30', '--no-pager', '--output=short'],
    capture_output=True, text=True
)
print(result.stdout[-3000:])
