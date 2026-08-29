'use strict';
// ═══════════════════════════════════════════════════════════
//  WealthMatrix v2 — Backend Server
//  Node.js + Express + SQLite
// ═══════════════════════════════════════════════════════════

const express     = require('express');
const session     = require('express-session');
const SQLiteStore = require('connect-sqlite3')(session);
const Database    = require('better-sqlite3');
const multer      = require('multer');
const pdfParse    = require('pdf-parse');
const bcrypt      = require('bcryptjs');
const path        = require('path');
const fs          = require('fs');
const crypto      = require('crypto');

const app  = express();
const PORT = process.env.PORT || 3000;

// ── Directory setup ──────────────────────────────────────────
['./data', './uploads', './public'].forEach(d => {
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
});

// ── Database init ─────────────────────────────────────────────
const db = new Database('./data/wealthmatrix.db');
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS investments (
    id                TEXT PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id),
    type              TEXT NOT NULL,
    name              TEXT NOT NULL,
    institution       TEXT DEFAULT '',
    principal_idr     REAL DEFAULT 0,
    current_value_idr REAL DEFAULT 0,
    quantity          REAL DEFAULT 0,
    unit              TEXT DEFAULT 'IDR',
    expected_return   REAL DEFAULT 15,
    start_date        TEXT,
    notes             TEXT DEFAULT '',
    created_at        TEXT DEFAULT (datetime('now')),
    updated_at        TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS snapshots (
    id             TEXT PRIMARY KEY,
    investment_id  TEXT NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
    value_idr      REAL NOT NULL,
    quantity       REAL DEFAULT 0,
    price_per_unit REAL,
    snapshot_date  TEXT NOT NULL,
    source         TEXT DEFAULT 'manual',
    notes          TEXT DEFAULT '',
    created_at     TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS goals (
    id             TEXT PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id),
    name           TEXT NOT NULL,
    target_amount  REAL NOT NULL,
    target_date    TEXT,
    monthly_pmt    REAL DEFAULT 0,
    color          TEXT DEFAULT '#10d4a8',
    icon           TEXT DEFAULT '🎯',
    notes          TEXT DEFAULT '',
    created_at     TEXT DEFAULT (datetime('now')),
    updated_at     TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS price_cache (
    symbol       TEXT PRIMARY KEY,
    price_idr    REAL,
    price_usd    REAL,
    change_24h   REAL,
    market_cap   REAL,
    last_updated TEXT
  );

  CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER NOT NULL REFERENCES users(id),
    key     TEXT NOT NULL,
    value   TEXT,
    PRIMARY KEY (user_id, key)
  );

  CREATE TABLE IF NOT EXISTS pdf_uploads (
    id           TEXT PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    filename     TEXT,
    source_type  TEXT,
    raw_text     TEXT,
    parsed_data  TEXT,
    upload_date  TEXT DEFAULT (datetime('now')),
    status       TEXT DEFAULT 'pending'
  );

  CREATE INDEX IF NOT EXISTS idx_snapshots_inv ON snapshots(investment_id, snapshot_date);
  CREATE INDEX IF NOT EXISTS idx_investments_user ON investments(user_id);
`);

// Seed default user
if (!db.prepare('SELECT id FROM users WHERE username = ?').get('williambunarto')) {
  const hash = bcrypt.hashSync('william123', 10);
  db.prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)').run('williambunarto', hash);
  console.log('[DB] Default user created: williambunarto');
}

// ── Middleware ────────────────────────────────────────────────
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));
app.use(session({
  store: new SQLiteStore({ db: 'sessions.db', dir: './data' }),
  secret: process.env.SESSION_SECRET || 'wm-secret-wbunarto-2025',
  resave: false,
  saveUninitialized: false,
  cookie: { maxAge: 7 * 24 * 60 * 60 * 1000, httpOnly: true }
}));

// Auth guard
const auth = (req, res, next) => {
  if (req.session?.userId) return next();
  res.status(401).json({ error: 'Unauthorized' });
};

// ── Utilities ─────────────────────────────────────────────────
const uid = () => crypto.randomBytes(8).toString('hex');
const today = () => new Date().toISOString().split('T')[0];

const getSetting = (userId, key, dflt = null) => {
  const r = db.prepare('SELECT value FROM settings WHERE user_id=? AND key=?').get(userId, key);
  return r ? r.value : dflt;
};
const setSetting = (userId, key, value) => {
  db.prepare('INSERT OR REPLACE INTO settings (user_id,key,value) VALUES(?,?,?)').run(userId, key, String(value));
};

// Compound interest: FV = PV*(1+r/12)^n + PMT*((1+r/12)^n - 1)/(r/12)
const project = (pv, annualRatePct, months, pmt = 0) => {
  const r = annualRatePct / 100 / 12;
  if (r === 0) return pv + pmt * months;
  const g = Math.pow(1 + r, months);
  return pv * g + pmt * ((g - 1) / r);
};

// Required PMT to reach target
const requiredPMT = (pv, target, annualRatePct, months) => {
  const r = annualRatePct / 100 / 12;
  if (months <= 0) return 0;
  if (r === 0) return Math.max(0, (target - pv) / months);
  const g = Math.pow(1 + r, months);
  return Math.max(0, (target - pv * g) * r / (g - 1));
};

// ── BTC Price ─────────────────────────────────────────────────
async function fetchBTCPrice() {
  try {
    const url = 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=idr,usd&include_24hr_change=true&include_market_cap=true';
    const res  = await fetch(url, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    const btc  = data.bitcoin;
    db.prepare(`
      INSERT OR REPLACE INTO price_cache (symbol,price_idr,price_usd,change_24h,market_cap,last_updated)
      VALUES ('BTC',?,?,?,?,datetime('now'))
    `).run(btc.idr, btc.usd, btc.usd_24h_change, btc.usd_market_cap ?? 0);
    console.log(`[BTC] $${btc.usd?.toLocaleString()} | IDR ${btc.idr?.toLocaleString()}`);
    return { price_idr: btc.idr, price_usd: btc.usd, change_24h: btc.usd_24h_change };
  } catch (e) {
    console.error('[BTC] Fetch failed:', e.message);
    return null;
  }
}

async function maybeRefreshBTC() {
  const cached = db.prepare("SELECT * FROM price_cache WHERE symbol='BTC'").get();
  if (!cached) { await fetchBTCPrice(); return; }
  const ageH = (Date.now() - new Date(cached.last_updated).getTime()) / 3600000;
  if (ageH >= 24) await fetchBTCPrice();
}

// Auto-update crypto investment values when BTC price refreshes
function syncBTCInvestments() {
  const btc = db.prepare("SELECT * FROM price_cache WHERE symbol='BTC'").get();
  if (!btc?.price_idr) return;
  const cryptoInvs = db.prepare("SELECT * FROM investments WHERE unit='BTC' AND quantity > 0").all();
  cryptoInvs.forEach(inv => {
    const newVal = inv.quantity * btc.price_idr;
    db.prepare("UPDATE investments SET current_value_idr=?, updated_at=datetime('now') WHERE id=?").run(newVal, inv.id);
    // Snapshot if today not already logged
    const existing = db.prepare("SELECT id FROM snapshots WHERE investment_id=? AND snapshot_date=?").get(inv.id, today());
    if (!existing) {
      db.prepare("INSERT INTO snapshots (id,investment_id,value_idr,quantity,price_per_unit,snapshot_date,source) VALUES(?,?,?,?,?,'auto')")
        .run(uid(), inv.id, newVal, inv.quantity, btc.price_idr, today());
    }
  });
}

// ── PDF Parsers ───────────────────────────────────────────────
function parseAjaibPDF(text) {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const stocks = [];
  let portfolioTotal = null;

  // Common Ajaib patterns
  const codePattern    = /^([A-Z]{4})\b/;
  const numberPattern  = /[\d,.]+/g;
  const totalPattern   = /(?:Total|Nilai)\s+(?:Aset|Portfolio|Investasi)[:\s]+([\d,.]+)/i;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const totalMatch = line.match(totalPattern);
    if (totalMatch) {
      portfolioTotal = parseInt(totalMatch[1].replace(/[,.]/g, '').replace(/\.(\d{1,2})$/, ''));
    }
    const codeMatch = line.match(codePattern);
    if (codeMatch && line.length < 120) {
      const nums = line.match(numberPattern) || [];
      if (nums.length >= 2) {
        const value = parseInt(nums[nums.length - 1].replace(/[,.]/g, ''));
        const qty   = parseInt(nums[0].replace(/[,.]/g, ''));
        if (value > 0) {
          stocks.push({ code: codeMatch[1], qty: qty || 0, estimated_value_idr: value, raw: line });
        }
      }
    }
  }

  return { type: 'ajaib', stocks, portfolioTotal, confidence: stocks.length > 0 ? 'medium' : 'low', preview: lines.slice(0, 40) };
}

function parseBybitPDF(text) {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const assets = [];

  const btcPattern  = /BTC\s+([\d.]+)\s+(?:\$\s*)?([\d,.]+)/i;
  const usdtPattern = /USDT\s+([\d,.]+)/i;
  const totalPattern = /(?:Total|Account\s+Value)[:\s]+(?:\$\s*)?([\d,.]+)/i;

  let totalUSD = null;

  for (const line of lines) {
    const btcM = line.match(btcPattern);
    if (btcM) assets.push({ symbol: 'BTC', quantity: parseFloat(btcM[1]), usd_value: parseFloat(btcM[2].replace(/,/g,'')) });

    const usdtM = line.match(usdtPattern);
    if (usdtM) assets.push({ symbol: 'USDT', quantity: parseFloat(usdtM[1].replace(/,/g,'')), usd_value: parseFloat(usdtM[1].replace(/,/g,'')) });

    const totM = line.match(totalPattern);
    if (totM) totalUSD = parseFloat(totM[1].replace(/,/g,''));
  }

  return { type: 'bybit', assets, totalUSD, confidence: assets.length > 0 ? 'medium' : 'low', preview: lines.slice(0, 40) };
}

// ── Static: Indonesia Inflation (BPS) ────────────────────────
const INFLATION_DATA = [
  { year:2024, rate:2.84 }, { year:2023, rate:3.69 }, { year:2022, rate:5.51 },
  { year:2021, rate:1.87 }, { year:2020, rate:1.68 }, { year:2019, rate:2.72 },
  { year:2018, rate:3.13 }, { year:2017, rate:3.61 }, { year:2016, rate:3.02 },
  { year:2015, rate:3.35 }
];

// ── Route Helpers ─────────────────────────────────────────────
function getPortfolioStats(userId) {
  const invs      = db.prepare('SELECT * FROM investments WHERE user_id=?').all(userId);
  const curTotal  = invs.reduce((a, i) => a + i.current_value_idr, 0);
  const prinTotal = invs.reduce((a, i) => a + i.principal_idr, 0);
  const pnl       = curTotal - prinTotal;
  let wRet        = 0;
  if (curTotal > 0) invs.forEach(i => { wRet += (i.current_value_idr / curTotal) * i.expected_return; });
  const pmt       = parseFloat(getSetting(userId, 'monthly_pmt', '0')) || 0;
  return { invs, curTotal, prinTotal, pnl, pnlPct: prinTotal > 0 ? (pnl / prinTotal) * 100 : 0, wRet, pmt, count: invs.length };
}

// ═══════════════════════════════════════════════════════════
//  ROUTES
// ═══════════════════════════════════════════════════════════

// ── Auth ──────────────────────────────────────────────────────
app.post('/api/auth/login', (req, res) => {
  const { username, password } = req.body;
  if (!username || !password) return res.status(400).json({ error: 'Missing credentials' });
  const user = db.prepare('SELECT * FROM users WHERE username=?').get(username?.toLowerCase().trim());
  if (!user || !bcrypt.compareSync(password, user.password_hash))
    return res.status(401).json({ error: 'Invalid username or password' });
  req.session.userId   = user.id;
  req.session.username = user.username;
  res.json({ ok: true, username: user.username });
});

app.post('/api/auth/logout', (req, res) => {
  req.session.destroy(() => res.json({ ok: true }));
});

app.get('/api/auth/me', auth, (req, res) => {
  res.json({ userId: req.session.userId, username: req.session.username });
});

// ── Dashboard ─────────────────────────────────────────────────
app.get('/api/dashboard', auth, (req, res) => {
  const s      = getPortfolioStats(req.session.userId);
  const btc    = db.prepare("SELECT * FROM price_cache WHERE symbol='BTC'").get();
  const goals  = db.prepare('SELECT * FROM goals WHERE user_id=?').all(req.session.userId);
  const hist   = getPortfolioHistory(req.session.userId);
  res.json({ portfolio: s, btcPrice: btc, goalsCount: goals.length, history: hist, ts: new Date().toISOString() });
});

function getPortfolioHistory(userId) {
  const invIds = db.prepare('SELECT id FROM investments WHERE user_id=?').all(userId).map(i => i.id);
  if (!invIds.length) return [];
  const ph = invIds.map(() => '?').join(',');
  return db.prepare(`
    SELECT snapshot_date as date, SUM(value_idr) as value
    FROM snapshots WHERE investment_id IN (${ph})
    GROUP BY snapshot_date ORDER BY snapshot_date ASC
  `).all(...invIds);
}

// ── Investments ───────────────────────────────────────────────
app.get('/api/investments', auth, (req, res) => {
  const invs = db.prepare('SELECT * FROM investments WHERE user_id=? ORDER BY created_at DESC').all(req.session.userId);
  // Attach latest BTC price to crypto quantities
  const btc = db.prepare("SELECT price_idr FROM price_cache WHERE symbol='BTC'").get();
  const result = invs.map(i => ({
    ...i,
    live_price_idr: (i.unit === 'BTC' && btc) ? btc.price_idr : null
  }));
  res.json(result);
});

app.post('/api/investments', auth, (req, res) => {
  const { type, name, institution, principal_idr, current_value_idr, quantity, unit, expected_return, start_date, notes } = req.body;
  if (!type || !name) return res.status(400).json({ error: 'type and name are required' });
  const id  = uid();
  const sd  = start_date || today();
  const cur = parseFloat(current_value_idr) || parseFloat(principal_idr) || 0;

  db.prepare(`
    INSERT INTO investments (id,user_id,type,name,institution,principal_idr,current_value_idr,quantity,unit,expected_return,start_date,notes)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
  `).run(id, req.session.userId, type, name, institution||'', parseFloat(principal_idr)||0, cur, parseFloat(quantity)||0, unit||'IDR', parseFloat(expected_return)||15, sd, notes||'');

  // Initial snapshot
  db.prepare('INSERT INTO snapshots (id,investment_id,value_idr,quantity,snapshot_date,source) VALUES(?,?,?,?,?,\'manual\')')
    .run(uid(), id, cur, parseFloat(quantity)||0, sd);

  res.json({ ok: true, id });
});

app.put('/api/investments/:id', auth, (req, res) => {
  const inv = db.prepare('SELECT * FROM investments WHERE id=? AND user_id=?').get(req.params.id, req.session.userId);
  if (!inv) return res.status(404).json({ error: 'Not found' });
  const f = req.body;
  db.prepare(`
    UPDATE investments SET type=?,name=?,institution=?,principal_idr=?,current_value_idr=?,quantity=?,unit=?,expected_return=?,start_date=?,notes=?,updated_at=datetime('now')
    WHERE id=? AND user_id=?
  `).run(
    f.type??inv.type, f.name??inv.name, f.institution??inv.institution,
    f.principal_idr!=null?parseFloat(f.principal_idr):inv.principal_idr,
    f.current_value_idr!=null?parseFloat(f.current_value_idr):inv.current_value_idr,
    f.quantity!=null?parseFloat(f.quantity):inv.quantity,
    f.unit||inv.unit,
    f.expected_return!=null?parseFloat(f.expected_return):inv.expected_return,
    f.start_date||inv.start_date, f.notes??inv.notes, req.params.id, req.session.userId
  );
  res.json({ ok: true });
});

app.delete('/api/investments/:id', auth, (req, res) => {
  if (!db.prepare('SELECT id FROM investments WHERE id=? AND user_id=?').get(req.params.id, req.session.userId))
    return res.status(404).json({ error: 'Not found' });
  db.prepare('DELETE FROM investments WHERE id=?').run(req.params.id);
  res.json({ ok: true });
});

// Update value / add snapshot
app.post('/api/investments/:id/snapshot', auth, (req, res) => {
  const inv = db.prepare('SELECT * FROM investments WHERE id=? AND user_id=?').get(req.params.id, req.session.userId);
  if (!inv) return res.status(404).json({ error: 'Not found' });
  const { value_idr, quantity, price_per_unit, snapshot_date, notes } = req.body;
  const d    = snapshot_date || today();
  const val  = parseFloat(value_idr);
  const qty  = quantity != null ? parseFloat(quantity) : inv.quantity;
  if (isNaN(val)) return res.status(400).json({ error: 'Invalid value_idr' });

  const existing = db.prepare('SELECT id FROM snapshots WHERE investment_id=? AND snapshot_date=?').get(inv.id, d);
  if (existing) {
    db.prepare('UPDATE snapshots SET value_idr=?,quantity=?,price_per_unit=?,notes=?,source=\'manual\' WHERE id=?')
      .run(val, qty, parseFloat(price_per_unit)||null, notes||'', existing.id);
  } else {
    db.prepare("INSERT INTO snapshots (id,investment_id,value_idr,quantity,price_per_unit,snapshot_date,source,notes) VALUES(?,?,?,?,?,?,?,?)")
      .run(uid(), inv.id, val, qty, parseFloat(price_per_unit)||null, d, 'manual', notes||'');
  }
  db.prepare("UPDATE investments SET current_value_idr=?,quantity=?,updated_at=datetime('now') WHERE id=?").run(val, qty, inv.id);
  res.json({ ok: true });
});

app.get('/api/investments/:id/history', auth, (req, res) => {
  const inv = db.prepare('SELECT * FROM investments WHERE id=? AND user_id=?').get(req.params.id, req.session.userId);
  if (!inv) return res.status(404).json({ error: 'Not found' });
  const history = db.prepare('SELECT * FROM snapshots WHERE investment_id=? ORDER BY snapshot_date ASC').all(inv.id);
  res.json({ investment: inv, history });
});

// ── Goals ────────────────────────────────────────────────────
app.get('/api/goals', auth, (req, res) => {
  res.json(db.prepare('SELECT * FROM goals WHERE user_id=? ORDER BY target_date ASC NULLS LAST').all(req.session.userId));
});

app.post('/api/goals', auth, (req, res) => {
  const { name, target_amount, target_date, monthly_pmt, color, icon, notes } = req.body;
  if (!name || !target_amount) return res.status(400).json({ error: 'name and target_amount required' });
  const id = uid();
  db.prepare('INSERT INTO goals (id,user_id,name,target_amount,target_date,monthly_pmt,color,icon,notes) VALUES(?,?,?,?,?,?,?,?,?)')
    .run(id, req.session.userId, name, parseFloat(target_amount), target_date||null, parseFloat(monthly_pmt)||0, color||'#10d4a8', icon||'🎯', notes||'');
  res.json({ ok: true, id });
});

app.put('/api/goals/:id', auth, (req, res) => {
  const g = db.prepare('SELECT * FROM goals WHERE id=? AND user_id=?').get(req.params.id, req.session.userId);
  if (!g) return res.status(404).json({ error: 'Not found' });
  const f = req.body;
  db.prepare("UPDATE goals SET name=?,target_amount=?,target_date=?,monthly_pmt=?,color=?,icon=?,notes=?,updated_at=datetime('now') WHERE id=? AND user_id=?")
    .run(f.name||g.name, f.target_amount!=null?parseFloat(f.target_amount):g.target_amount, f.target_date!==undefined?f.target_date:g.target_date,
      f.monthly_pmt!=null?parseFloat(f.monthly_pmt):g.monthly_pmt, f.color||g.color, f.icon||g.icon, f.notes!=null?f.notes:g.notes,
      req.params.id, req.session.userId);
  res.json({ ok: true });
});

app.delete('/api/goals/:id', auth, (req, res) => {
  db.prepare('DELETE FROM goals WHERE id=? AND user_id=?').run(req.params.id, req.session.userId);
  res.json({ ok: true });
});

// ── Forecast ──────────────────────────────────────────────────
app.get('/api/forecast', auth, (req, res) => {
  const s     = getPortfolioStats(req.session.userId);
  const goals = db.prepare('SELECT * FROM goals WHERE user_id=?').all(req.session.userId);
  const pv    = s.curTotal;
  const r     = s.wRet;
  const pmt   = s.pmt;

  const scenarios = (months) => ({
    conservative: project(pv, r * 0.7, months, pmt),
    base:         project(pv, r,       months, pmt),
    optimistic:   project(pv, r * 1.3, months, pmt)
  });

  // Chart data arrays
  const shortPts = [0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3].map(m => ({
    label: m === 0 ? 'Now' : m < 1 ? `${Math.round(m * 4)}W` : `${m}M`,
    months: m, ...scenarios(m)
  }));

  const midPts = Array.from({ length: 13 }, (_, i) => i).map(m => ({
    label: m === 0 ? 'Now' : `M${m}`, months: m, ...scenarios(m)
  }));

  const longYears = [0, 1, 2, 3, 5, 7, 10, 12, 15, 20];
  const longPts   = longYears.map(y => ({
    label: y === 0 ? 'Now' : `Y${y}`, months: y * 12,
    ...scenarios(y * 12),
    pmt_only: project(0, r, y * 12, pmt)
  }));

  // Per-investment 12M and 5Y projection
  const invProjections = s.invs.map(i => ({
    id: i.id, name: i.name, type: i.type, institution: i.institution,
    current: i.current_value_idr, rate: i.expected_return,
    proj3m:  project(i.current_value_idr, i.expected_return, 3, 0),
    proj6m:  project(i.current_value_idr, i.expected_return, 6, 0),
    proj12m: project(i.current_value_idr, i.expected_return, 12, 0),
    proj5y:  project(i.current_value_idr, i.expected_return, 60, 0),
    proj10y: project(i.current_value_idr, i.expected_return, 120, 0)
  }));

  // Goal projection overlay
  const goalOverlay = goals.map(g => {
    const ms = g.target_date
      ? Math.max(1, Math.round((new Date(g.target_date) - Date.now()) / (1000 * 60 * 60 * 24 * 30.44)))
      : null;
    const projected   = ms ? project(pv, r, ms, pmt) : null;
    const req_pmt     = ms ? requiredPMT(pv, g.target_amount, r, ms) : null;
    return { ...g, monthsLeft: ms, projected, onTrack: projected != null ? projected >= g.target_amount : null, required_pmt: req_pmt };
  });

  // Milestone table
  const milestones = [
    { label: '3 Months', months: 3 }, { label: '6 Months', months: 6 },
    { label: '1 Year', months: 12 }, { label: '2 Years', months: 24 },
    { label: '5 Years', months: 60 }, { label: '10 Years', months: 120 },
    { label: '15 Years', months: 180 }, { label: '20 Years', months: 240 }
  ].map(m => ({ ...m, ...scenarios(m.months), pmt_only: project(0, r, m.months, pmt) }));

  res.json({ portfolio: { pv, r, pmt }, invProjections, goalOverlay, milestones, charts: { short: shortPts, mid: midPts, long: longPts } });
});

// ── Prices ────────────────────────────────────────────────────
app.get('/api/prices/btc', auth, async (req, res) => {
  await maybeRefreshBTC();
  const cached = db.prepare("SELECT * FROM price_cache WHERE symbol='BTC'").get();
  res.json(cached || { error: 'Unavailable' });
});

app.post('/api/prices/refresh', auth, async (req, res) => {
  const result = await fetchBTCPrice();
  if (result) syncBTCInvestments();
  res.json(result ? { ok: true, ...result } : { error: 'Failed' });
});

// ── Settings ─────────────────────────────────────────────────
app.get('/api/settings', auth, (req, res) => {
  const rows = db.prepare('SELECT key,value FROM settings WHERE user_id=?').all(req.session.userId);
  const s = {}; rows.forEach(r => { s[r.key] = r.value; });
  res.json(s);
});

app.put('/api/settings', auth, (req, res) => {
  const allowed = ['monthly_pmt', 'risk_profile', 'currency_display'];
  allowed.forEach(k => { if (req.body[k] !== undefined) setSetting(req.session.userId, k, req.body[k]); });
  res.json({ ok: true });
});

// ── PDF Upload ───────────────────────────────────────────────
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 25 * 1024 * 1024 } });

app.post('/api/upload/pdf', auth, upload.single('pdf'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });
  const sourceType = req.body.source_type || 'unknown';
  try {
    const data   = await pdfParse(req.file.buffer);
    const text   = data.text || '';
    let parsed   = {};
    if (sourceType === 'ajaib')     parsed = parseAjaibPDF(text);
    else if (sourceType === 'bybit') parsed = parseBybitPDF(text);
    else parsed = { type: 'raw', preview: text.split('\n').slice(0, 60).map(l => l.trim()).filter(Boolean) };

    const id = uid();
    db.prepare('INSERT INTO pdf_uploads (id,user_id,filename,source_type,raw_text,parsed_data) VALUES(?,?,?,?,?,?)')
      .run(id, req.session.userId, req.file.originalname, sourceType, text.slice(0, 8000), JSON.stringify(parsed));
    res.json({ ok: true, id, parsed, pages: data.numpages });
  } catch (e) {
    res.status(500).json({ error: 'PDF parse error: ' + e.message });
  }
});

app.get('/api/upload/history', auth, (req, res) => {
  res.json(db.prepare('SELECT id,filename,source_type,upload_date,status FROM pdf_uploads WHERE user_id=? ORDER BY upload_date DESC LIMIT 20').all(req.session.userId));
});

// ── Inflation ─────────────────────────────────────────────────
app.get('/api/inflation', (req, res) => {
  const avg10 = INFLATION_DATA.reduce((a, i) => a + i.rate, 0) / INFLATION_DATA.length;
  const avg5  = INFLATION_DATA.slice(0, 5).reduce((a, i) => a + i.rate, 0) / 5;
  res.json({ data: INFLATION_DATA, avg10: +avg10.toFixed(2), avg5: +avg5.toFixed(2), current: INFLATION_DATA[0] });
});

// ── Portfolio History ─────────────────────────────────────────
app.get('/api/history', auth, (req, res) => {
  res.json(getPortfolioHistory(req.session.userId));
});

// ── SPA entry ────────────────────────────────────────────────
// Supports both root access (port 3000 direct) and /wealth/ subpath (via Nginx)
const BASE = process.env.BASE_PATH || '';

app.get(['/', BASE+'/', BASE], (req, res) => {
  if (!req.session?.userId) return res.sendFile(path.join(__dirname, 'public', 'login.html'));
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});
app.get(['/app', BASE+'/app'], (req, res) => {
  if (!req.session?.userId) return res.redirect((BASE||'/')+'/');
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});
app.get('*', (req, res) => res.redirect((BASE||'/') + '/'));

// ── Start ────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n╔══════════════════════════════════════╗`);
  console.log(`║  WealthMatrix v2 — Port ${PORT}        ║`);
  console.log(`║  Login: williambunarto / william123  ║`);
  console.log(`╚══════════════════════════════════════╝\n`);
  maybeRefreshBTC().then(syncBTCInvestments).catch(console.error);
});
