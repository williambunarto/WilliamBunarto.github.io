/* dashboard.js */
const STATE_COLORS = { super_long: '#22c55e', long: '#86efac', neutral: '#fbbf24', short: '#f97316', super_short: '#ef4444' };

function renderSignalBar(barId, valId, score) {
  const bar = document.getElementById(barId);
  const val = document.getElementById(valId);
  if (!bar || !val) return;
  const pct    = ((score + 2) / 4) * 100;
  const center = 50;
  const color  = score >= 0 ? '#22c55e' : '#ef4444';
  if (score >= 0) { bar.style.left = center + '%'; bar.style.width = (pct - center) + '%'; }
  else { bar.style.left = pct + '%'; bar.style.width = (center - pct) + '%'; }
  bar.style.background = color;
  val.textContent = (score >= 0 ? '+' : '') + score.toFixed(2);
  val.style.color = color;
}

async function loadMarketState() {
  try {
    const d = await api('/market/state');
    const color = STATE_COLORS[d.state] || '#fbbf24';
    const labels = { super_long:'Super Long', long:'Long', neutral:'Neutral', short:'Short', super_short:'Super Short' };
    const lbl = document.getElementById('ms-label');
    if (lbl) { lbl.textContent = labels[d.state] || d.state; lbl.style.color = color; }
    const reason = document.getElementById('ms-reason');
    if (reason) reason.textContent = d.reason || '';
    const risk = document.getElementById('ms-risk');
    if (risk) risk.textContent = d.risk_note ? '⚠ ' + d.risk_note : '';
    const upd = document.getElementById('ms-updated');
    if (upd && d.timestamp) { const t = new Date(d.timestamp); upd.textContent = 'Updated ' + t.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}) + ' UTC'; }
    renderSignalBar('bar-ema',  'val-ema',  d.ema_score  || 0);
    renderSignalBar('bar-vol',  'val-vol',  d.volume_score || 0);
    renderSignalBar('bar-fund', 'val-fund', d.funding_score || 0);
    renderSignalBar('bar-fng',  'val-fng',  d.fng_score  || 0);
    const msFund = document.getElementById('ms-funding');
    if (msFund) msFund.textContent = d.funding_rate != null ? (d.funding_rate * 100).toFixed(4) + '%' : '—';
    const msFng = document.getElementById('ms-fng');
    if (msFng) msFng.textContent = d.fng_value != null ? d.fng_value + '/100' : '—';
    const calcEntry = document.getElementById('calc-entry');
    if (calcEntry && !calcEntry.value && d.btc_price) { calcEntry.value = d.btc_price; calcPosition(); }
  } catch(e) { console.warn('Market state load failed', e); }
}

async function loadStats() {
  try {
    const s = await api('/stats/summary');
    const pnlEl = document.getElementById('s-pnl');
    if (pnlEl) { pnlEl.textContent = (s.total_pnl >= 0 ? '+' : '') + s.total_pnl.toFixed(2) + ' USDT'; pnlEl.className = 'stat-value mono ' + (s.total_pnl >= 0 ? 'green' : 'red'); }
    const wrEl = document.getElementById('s-wr'); if (wrEl) wrEl.textContent = s.win_rate + '%';
    const trEl = document.getElementById('s-trades'); if (trEl) trEl.textContent = s.total + ' trades';
    const wlEl = document.getElementById('s-wl'); if (wlEl) wlEl.textContent = s.wins + 'W / ' + s.losses + 'L';
    const rEl = document.getElementById('s-r'); if (rEl) rEl.textContent = (s.avg_r >= 0 ? '+' : '') + s.avg_r + 'R';
    const bestEl = document.getElementById('s-best'); if (bestEl) bestEl.textContent = '+' + s.best_trade.toFixed(2) + ' USDT';
    const worstEl = document.getElementById('s-worst'); if (worstEl) worstEl.textContent = s.worst_trade.toFixed(2) + ' USDT';
  } catch(e) { console.warn('Stats load failed', e); }
}

async function loadRecentTrades() {
  try {
    const trades = await api('/trades/?limit=10');
    const tbody  = document.getElementById('recent-trades-body');
    if (!tbody) return;
    if (!trades.length) { tbody.innerHTML = '<tr><td colspan="9" class="muted" style="text-align:center;padding:32px">No trades yet</td></tr>'; return; }
    tbody.innerHTML = trades.map(t => `<tr>
      <td class="muted">${fmtDate(t.created_at)}</td><td>${dirBadge(t.direction)}</td>
      <td class="mono">${fmtPrice(t.entry_price)}</td><td class="mono">${fmtPrice(t.exit_price)}</td>
      <td class="mono">${t.position_size_usdt ? t.position_size_usdt.toLocaleString() + ' USDT' : '—'}</td>
      <td class="mono ${t.pnl_usdt >= 0 ? 'green' : 'red'}">${fmtUSDT(t.pnl_usdt)}</td>
      <td class="mono ${parseFloat(t.r_multiple) >= 0 ? 'green' : 'red'}">${fmtR(t.r_multiple)}</td>
      <td class="muted">${t.setup_tag || '—'}</td>
      <td>${t.outcome ? outcomeBadge(t.outcome) : '<span class="muted">open</span>'}</td>
    </tr>`).join('');
  } catch(e) { console.warn('Trades load failed', e); }
}

async function loadCalcSettings() {
  try {
    const s = await api('/settings/');
    const bal = document.getElementById('calc-balance');
    const risk = document.getElementById('calc-risk');
    if (bal && s.account_balance) bal.value = s.account_balance;
    if (risk && s.risk_percent)   risk.value = s.risk_percent;
    calcPosition();
  } catch {}
}

function calcPosition() {
  const balance = parseFloat(document.getElementById('calc-balance')?.value) || 0;
  const riskPct = parseFloat(document.getElementById('calc-risk')?.value)    || 1;
  const entry   = parseFloat(document.getElementById('calc-entry')?.value)   || 0;
  const sl      = parseFloat(document.getElementById('calc-sl')?.value)      || 0;
  const tp      = parseFloat(document.getElementById('calc-tp')?.value)      || 0;
  const lev     = parseFloat(document.getElementById('calc-lev')?.value)     || 10;
  if (!balance || !entry || !sl) { document.getElementById('calc-output').style.display = 'none'; return; }
  const riskUsdt = balance * (riskPct / 100);
  const slPct    = Math.abs(entry - sl) / entry;
  const posSize  = slPct > 0 ? riskUsdt / slPct : 0;
  const posBtc   = entry > 0 ? posSize / entry : 0;
  let rr = '—';
  if (tp && sl && entry) { const gain = Math.abs(tp - entry); const risk = Math.abs(entry - sl); rr = risk > 0 ? (gain / risk).toFixed(2) + ':1' : '—'; }
  document.getElementById('co-risk').textContent = riskUsdt.toFixed(2) + ' USDT';
  document.getElementById('co-size').textContent = posSize.toFixed(2)  + ' USDT';
  document.getElementById('co-btc').textContent  = posBtc.toFixed(6)   + ' BTC';
  document.getElementById('co-rr').textContent   = rr;
  document.getElementById('calc-output').style.display = 'grid';
}

async function saveCalcSettings() {
  const balance = document.getElementById('calc-balance')?.value;
  const risk    = document.getElementById('calc-risk')?.value;
  try { await apiForm('/settings/', { account_balance: balance, risk_percent: risk }, 'PUT'); toast('Defaults saved'); }
  catch { toast('Save failed'); }
}

function openTradeModal() {
  document.getElementById('trade-modal').classList.remove('hidden');
  const calcEntry = document.getElementById('calc-entry')?.value;
  const formEntry = document.querySelector('#trade-form [name=entry_price]');
  if (calcEntry && formEntry && !formEntry.value) formEntry.value = calcEntry;
}
function closeTradeModal() { document.getElementById('trade-modal').classList.add('hidden'); }

async function submitTrade(e) {
  e.preventDefault();
  const form = document.getElementById('trade-form');
  const fd   = new FormData(form);
  try {
    await fetch(BASE + '/api/trades/', { method: 'POST', body: fd });
    toast('Trade saved ✓'); closeTradeModal(); form.reset(); loadRecentTrades(); loadStats();
  } catch(err) { toast('Error: ' + err.message); }
}

document.addEventListener('DOMContentLoaded', () => {
  loadMarketState(); loadStats(); loadRecentTrades(); loadCalcSettings();
  setInterval(loadMarketState, 60 * 1000);
});
