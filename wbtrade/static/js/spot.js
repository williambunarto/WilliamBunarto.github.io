/* spot.js */
let _btcLivePrice = 0;

async function loadSpotEntries() {
  try {
    const entries = await api('/spot/entries');
    const tbody   = document.getElementById('spot-body');
    if (!tbody) return;
    if (!entries.length) { tbody.innerHTML = '<tr><td colspan="7" class="muted" style="text-align:center;padding:24px">No DCA entries yet</td></tr>'; updatePortfolioSummary(0, 0, 0); return; }
    tbody.innerHTML = entries.map(e => `<tr>
      <td class="muted">${e.date}</td>
      <td>${e.action === 'buy' ? '<span class="badge badge-long">BUY</span>' : '<span class="badge badge-short">SELL</span>'}</td>
      <td class="mono">${e.btc_amount.toFixed(8)}</td>
      <td class="mono">${fmtPrice(e.price_usdt)}</td>
      <td class="mono muted">${e.usdt_spent ? e.usdt_spent.toLocaleString() + ' USDT' : '—'}</td>
      <td class="mono muted">${e.running_avg ? fmtPrice(e.running_avg) : '—'}</td>
      <td class="muted" style="font-size:12px">${e.thesis_tag ? e.thesis_tag.replace(/_/g,' ') : '—'}</td>
    </tr>`).join('');
    const last = entries[entries.length - 1];
    updatePortfolioSummary(last.running_btc, last.running_avg, _btcLivePrice);
  } catch(e) { console.warn('Spot entries failed', e); }
}

function updatePortfolioSummary(totalBtc, avgPrice, livePrice) {
  document.getElementById('sp-btc').textContent = totalBtc.toFixed(8) + ' BTC';
  document.getElementById('sp-avg').textContent = fmtPrice(avgPrice);
  const value = totalBtc * livePrice;
  const cost  = totalBtc * avgPrice;
  const pnl   = value - cost;
  const pnlPct = cost > 0 ? ((pnl / cost) * 100).toFixed(1) : 0;
  const valueEl = document.getElementById('sp-value');
  const pnlEl   = document.getElementById('sp-pnl');
  if (valueEl) valueEl.textContent = livePrice > 0 ? fmtPrice(value) + ' USDT' : '—';
  if (pnlEl) { pnlEl.textContent = livePrice > 0 ? (pnl >= 0 ? '+' : '') + pnl.toFixed(2) + ' USDT (' + pnlPct + '%)' : '—'; pnlEl.className = 'stat-value mono ' + (pnl >= 0 ? 'green' : 'red'); }
}

async function loadTargets() {
  try {
    const targets = await api('/spot/targets');
    const el = document.getElementById('targets-list');
    if (!el) return;
    if (!targets.length) { el.innerHTML = '<p class="muted" style="padding:8px 0">No exit targets set</p>'; return; }
    el.innerHTML = targets.map(t => {
      const statusColor = { active:'var(--text2)', hit:'var(--win)', cancelled:'var(--text3)' }[t.status] || 'var(--text2)';
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border)">
        <div><div style="font-weight:500;font-size:13px">${t.label}</div><div style="font-family:var(--mono);font-size:14px;margin-top:2px">${fmtPrice(t.price_usdt)}</div><div style="font-size:11px;color:var(--text3)">Sell ${t.btc_percent_to_sell}% of holdings</div></div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
          <span style="font-size:11px;color:${statusColor};text-transform:uppercase">${t.status}</span>
          <div style="display:flex;gap:4px"><button class="btn btn-secondary btn-sm" onclick="markTarget(${t.id},'hit')">Hit ✓</button><button class="btn btn-secondary btn-sm" onclick="markTarget(${t.id},'cancelled')" style="color:var(--text3)">Cancel</button></div>
        </div>
      </div>`;
    }).join('');
    renderPriceLadder(targets);
  } catch(e) { console.warn('Targets failed', e); }
}

function renderPriceLadder(targets) {
  const el = document.getElementById('price-ladder');
  if (!el) return;
  const active = targets.filter(t => t.status === 'active').sort((a, b) => a.price_usdt - b.price_usdt);
  const price  = _btcLivePrice;
  if (!active.length) { el.innerHTML = '<p class="muted" style="font-size:12px">No active targets</p>'; return; }
  el.innerHTML = active.map(t => {
    const pct  = price > 0 ? ((t.price_usdt - price) / price * 100).toFixed(1) : null;
    const above = price > 0 ? t.price_usdt > price : true;
    const dist  = pct ? (above ? `+${pct}% from now` : `${pct}% below`) : '';
    return `<div style="display:flex;align-items:center;justify-content:space-between;padding:7px 0;font-size:12px;border-bottom:1px solid var(--border)">
      <span style="color:var(--text2)">${t.label}</span><span class="mono">${fmtPrice(t.price_usdt)}</span>
      <span style="color:${above ? 'var(--win)' : 'var(--loss)'}">${dist}</span>
      <span style="color:var(--text3)">Sell ${t.btc_percent_to_sell}%</span>
    </div>`;
  }).join('');
}

async function markTarget(id, status) {
  const fd = new FormData(); fd.append('status', status);
  try { await fetch(BASE + '/api/spot/targets/' + id, { method: 'PUT', body: fd }); toast('Target updated'); loadTargets(); }
  catch { toast('Update failed'); }
}

function openSpotModal() {
  const today = new Date().toISOString().split('T')[0];
  document.querySelector('#spot-form [name=entry_date]').value = today;
  const priceEl = document.querySelector('#spot-form [name=price_usdt]');
  if (_btcLivePrice && !priceEl.value) priceEl.value = _btcLivePrice;
  document.getElementById('spot-modal').classList.remove('hidden');
}

async function submitSpotEntry(e) {
  e.preventDefault();
  const fd = new FormData(document.getElementById('spot-form'));
  const btc = parseFloat(fd.get('btc_amount')); const price = parseFloat(fd.get('price_usdt'));
  if (!fd.get('usdt_spent') && btc && price) fd.set('usdt_spent', (btc * price).toFixed(2));
  try { await fetch(BASE + '/api/spot/entries', { method: 'POST', body: fd }); toast('Entry saved ✓'); document.getElementById('spot-modal').classList.add('hidden'); document.getElementById('spot-form').reset(); loadSpotEntries(); }
  catch { toast('Save failed'); }
}

function openTargetModal() { document.getElementById('target-modal').classList.remove('hidden'); }

async function submitTarget(e) {
  e.preventDefault();
  const fd = new FormData(document.getElementById('target-form'));
  try { await fetch(BASE + '/api/spot/targets', { method: 'POST', body: fd }); toast('Target added ✓'); document.getElementById('target-modal').classList.add('hidden'); document.getElementById('target-form').reset(); loadTargets(); }
  catch { toast('Save failed'); }
}

document.addEventListener('DOMContentLoaded', () => {
  const el = document.getElementById('btc-price');
  const observer = new MutationObserver(() => {
    const text = el?.textContent?.replace('$','').replace(/,/g,'');
    const p = parseFloat(text);
    if (p && p !== _btcLivePrice) { _btcLivePrice = p; loadSpotEntries(); loadTargets(); }
  });
  if (el) observer.observe(el, { childList: true, subtree: true, characterData: true });
  loadSpotEntries(); loadTargets();
});
