# Claude Code — Project Memory

## Oracle Cloud Server

- **IP:** `140.245.103.249`
- **DNS:** `williambunarto.duckdns.org`
- **User:** `ubuntu`
- **Region:** ap-singapore-1
- **SSH key (private):** `ssh-key-2026-03-30 (1).key` (in repo root)
- **SSH key (public):** `ssh-key-2026-03-30.key.pub`

### SSH command (from any device with repo cloned)
```bash
ssh -i "ssh-key-2026-03-30 (1).key" -o StrictHostKeyChecking=no ubuntu@140.245.103.249
```

### SSH command (from this Claude Code environment)
```bash
ssh -i "/home/user/WilliamBunarto.github.io/ssh-key-2026-03-30 (1).key" -o StrictHostKeyChecking=no ubuntu@140.245.103.249
```

## Server Layout

| Service | Path / Port |
|---------|-------------|
| Nginx (web) | port 80 |
| **WealthMatrix app** | `/home/ubuntu/wealthmatrix/public/index.html` → `http://williambunarto.duckdns.org/wealth/` |
| HealthOS | `/home/ubuntu/healthos/` → `/health/` |
| Telegram bot | `/home/ubuntu/bot.py` (via nohup) |
| Health API | `/home/ubuntu/health_api.py` on port 8081 |
| WBAgent terminal | ttyd on port 7681 → `/wbagent/` |

## Auto-Deploy

Every push to `wealth/**` on `main`:
1. GitHub Actions triggers `.github/workflows/deploy-duckdns.yml` — SSHes in and copies `wealth/index.html` to `/home/ubuntu/wealthmatrix/public/index.html`
2. Server cron (every 5 min) pulls from GitHub raw as backup

## GitHub Push Rule

`git push` is blocked (branch protection). Always use `mcp__github__push_files` tool to push changes to GitHub.

## WealthMatrix v2 (wealth/index.html)

- Per-investment IDR/USD currency toggle
- BTC quantity tracking with live CoinGecko price
- Assets section (property/vehicle/other with depreciation/appreciation)
- Dashboard "Include Assets" toggle
- Daily return column in portfolio list
- localStorage keys: `wm_inv`, `wm_assets`, `wm_hist`, `wm_inc_assets`
- Live at: `http://williambunarto.duckdns.org/wealth/` and `https://williambunarto.github.io/wealth/`
