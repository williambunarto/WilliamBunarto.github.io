# WealthMatrix v2
**Personal Investment Intelligence System**

---

## Features

| Module | What it does |
|--------|-------------|
| Dashboard | Aggregated portfolio value, P&L, history chart, allocation donut |
| Portfolio | Full CRUD for Saham / Crypto / Deposito investments |
| Forecast | 3M/6M/12M/5Y/10Y/15Y/20Y projections · 3 scenarios · Per-asset breakdown |
| Goals | Financial targets with progress tracking and required PMT calculation |
| PDF Import | Upload Ajaib or Bybit statements, auto-parse, review, then import |
| Market | Live BTC price (IDR/USD) · 10-year Indonesia inflation history · Real return analysis |

---

## Quick Deploy to Oracle Cloud

```bash
# 1. SSH into your Oracle VM
ssh -i ~/.ssh/oracle.key ubuntu@140.245.103.249

# 2. Upload the zip or git clone
scp -i ~/.ssh/oracle.key wealthmatrix-v2.zip ubuntu@140.245.103.249:~
unzip wealthmatrix-v2.zip -d ~/wealthmatrix

# 3. Run deploy script
cd ~/wealthmatrix
bash deploy.sh
```

Then open: `http://140.245.103.249` — Login: `williambunarto / william123`

---

## Manual Setup

### Prerequisites
- Node.js 18+ (`node -v`)
- PM2 (`npm install -g pm2`)
- Nginx (optional, for port 80)

### Local Development

```bash
npm install
node server.js
# Open http://localhost:3000
```

### Production (PM2 + Nginx)

```bash
npm install --production
pm2 start server.js --name wealthmatrix
pm2 save
pm2 startup
```

---

## Stack

```
Backend    : Node.js 18+ · Express 4 · better-sqlite3
Auth       : express-session · connect-sqlite3 (7-day cookie)
PDF Parse  : pdf-parse (Ajaib + Bybit pattern extraction)
BTC Price  : CoinGecko free API · 24h auto-cache in SQLite
Frontend   : Vanilla JS SPA · Chart.js 4 · Sora + JetBrains Mono
Deploy     : PM2 process manager · Nginx reverse proxy
```

---

## Database

SQLite file at `./data/wealthmatrix.db` — auto-created on first run.

**Backup:**
```bash
cp ~/wealthmatrix/data/wealthmatrix.db ~/backup-$(date +%Y%m%d).db
```

---

## PDF Parsing Notes

| Source | What's extracted | Confidence |
|--------|-----------------|------------|
| Ajaib | Stock code, quantity (lot), estimated value | Medium |
| Bybit | BTC/USDT balance and quantity | Medium |

Always review parsed data before importing. PDF formats vary — if auto-parse fails, the raw extracted text is shown for manual reference.

---

## PM2 Commands

```bash
pm2 status                   # See running processes
pm2 logs wealthmatrix        # Live logs
pm2 restart wealthmatrix     # Restart app
pm2 stop wealthmatrix        # Stop app
pm2 delete wealthmatrix      # Remove from PM2
```

---

## Credential Change

To change the password, edit `server.js` line:
```js
const hash = bcrypt.hashSync('william123', 10);
```
Replace `william123` with your new password, then run `npm install && pm2 restart wealthmatrix`.

Or via SQLite CLI:
```bash
node -e "const b=require('bcryptjs');console.log(b.hashSync('NEWPASS',10))"
sqlite3 ~/wealthmatrix/data/wealthmatrix.db "UPDATE users SET password_hash='HASH' WHERE username='williambunarto'"
pm2 restart wealthmatrix
```

---

## Forecast Math

```
FV = PV × (1 + r/12)^n  +  PMT × [(1 + r/12)^n − 1] / (r/12)

Where:
  PV  = Current portfolio value
  r   = Annual return rate (weighted average of all investments)
  n   = Number of months
  PMT = Monthly contribution

Scenarios:
  Conservative = r × 0.7  (−30% from base)
  Base         = r
  Optimistic   = r × 1.3  (+30% from base)
```
