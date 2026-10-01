# Claude Code — Project Memory

## Oracle Cloud Server

- **DNS:** `williambunarto.duckdns.org`
- **User:** `ubuntu`
- **Region:** ap-singapore-1
- **SSH access:** private key is NOT stored in this repo. CI uses the GitHub Actions secret `DEPLOY_SSH_KEY`. Local access uses the key kept on William's own devices.
- **Never commit** keys, tokens or API credentials to this public repo. Use GitHub Actions secrets.

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
