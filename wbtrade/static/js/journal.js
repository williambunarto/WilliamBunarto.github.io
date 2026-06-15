/* journal.js */
async function loadTrades() {
  const outcome = document.getElementById('filter-outcome')?.value || '';
  const setup   = document.getElementById('filter-setup')?.value || '';
  const tbody   = document.getElementById('trades-body');
  if (!tbody) return;
  try {
    let trades = await api('/trades/?limit=200');
    if (outcome) trades = trades.filter(t => t.outcome === outcome);
    if (setup)   trades = trades.filter(t => t.setup_tag === setup);
    if (!trades.length) { tbody.innerHTML = '<tr><td colspan="15" class="muted" style="text-align:center;padding:32px">No trades match filter</td></tr>'; return; }
    tbody.innerHTML = trades.map(t => {
      const pnlClass = t.pnl_usdt >= 0 ? 'green' : 'red';
      const rClass   = parseFloat(t.r_multiple) >= 0 ? 'green' : 'red';
      return `<tr style="cursor:pointer" onclick="openDetailModal(${t.id})">
        <td class="muted">${fmtDate(t.created_at)}</td><td>${dirBadge(t.direction)}</td>
        <td class="mono">${fmtPrice(t.entry_price)}</td>
        <td class="mono">${t.exit_price ? fmtPrice(t.exit_price) : '<span class="muted">open</span>'}</td>
        <td class="mono muted">${t.position_size_usdt ? t.position_size_usdt.toLocaleString() : '—'}</td>
        <td class="mono muted">${t.leverage ? t.leverage + 'x' : '—'}</td>
        <td class="mono muted">${t.stop_loss ? fmtPrice(t.stop_loss) : '—'}</td>
        <td class="mono ${pnlClass}">${fmtUSDT(t.pnl_usdt)}</td>
        <td class="mono ${rClass}">${fmtR(t.r_multiple)}</td>
        <td class="muted">${t.setup_tag ? t.setup_tag.replace('_',' ') : '—'}</td>
        <td class="muted">${t.volume_tag || '—'}</td>
        <td class="muted">${t.psychology_tag || '—'}</td>
        <td><span class="muted" style="font-size:11px">${t.market_state_id ? 'logged' : '—'}</span></td>
        <td>${t.outcome ? outcomeBadge(t.outcome) : '<span class="muted">open</span>'}</td>
        <td><button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();openDetailModal(${t.id})"><i class="ti ti-eye"></i></button></td>
      </tr>`;
    }).join('');
  } catch(e) { console.warn('Load trades failed', e); }
}

async function openDetailModal(id) {
  const modal = document.getElementById('trade-detail-modal');
  const content = document.getElementById('detail-content');
  modal.classList.remove('hidden');
  content.innerHTML = '<p class="muted">Loading...</p>';
  try {
    const t = await api(`/trades/${id}`);
    const pnlClass = t.pnl_usdt >= 0 ? 'green' : 'red';
    const rv = Array.isArray(t.rule_violations) ? t.rule_violations : [];
    document.getElementById('detail-title').textContent = `${t.direction?.toUpperCase()} trade — ${fmtDate(t.created_at)}`;
    content.innerHTML = `
      <div class="grid-2" style="gap:10px;margin-bottom:16px">
        <div class="stat-tile"><div class="stat-label">PnL</div><div class="stat-value mono ${pnlClass}">${fmtUSDT(t.pnl_usdt)}</div></div>
        <div class="stat-tile"><div class="stat-label">R multiple</div><div class="stat-value mono ${pnlClass}">${fmtR(t.r_multiple)}</div></div>
        <div class="stat-tile"><div class="stat-label">Entry / Exit</div><div class="mono" style="font-size:14px">${fmtPrice(t.entry_price)} → ${fmtPrice(t.exit_price)}</div></div>
        <div class="stat-tile"><div class="stat-label">Size / Leverage</div><div class="mono" style="font-size:14px">${t.position_size_usdt?.toLocaleString() || '—'} USDT · ${t.leverage || '—'}x</div></div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">${t.outcome ? outcomeBadge(t.outcome) : ''}${dirBadge(t.direction)}${t.setup_tag ? `<span class="badge badge-neutral">${t.setup_tag.replace('_',' ')}</span>` : ''}${t.psychology_tag ? `<span class="badge badge-neutral">${t.psychology_tag}</span>` : ''}</div>
      ${rv.length ? `<div style="margin-bottom:12px"><span style="font-size:11px;color:var(--loss)">⚠ Rule violations: ${rv.join(', ')}</span></div>` : ''}
      ${t.notes ? `<div style="background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:12px;margin-bottom:12px;font-size:13px;line-height:1.6">${t.notes}</div>` : ''}
      ${t.screenshot_path ? `<img src="${t.screenshot_path}" class="screenshot-thumb" onclick="window.open(this.src)">` : ''}
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px"><button class="btn btn-danger btn-sm" onclick="deleteTrade(${t.id})"><i class="ti ti-trash"></i> Delete</button></div>`;
  } catch(e) { content.innerHTML = '<p class="muted">Failed to load trade.</p>'; }
}

function closeDetailModal() { document.getElementById('trade-detail-modal').classList.add('hidden'); }

async function deleteTrade(id) {
  if (!confirm('Delete this trade? Cannot be undone.')) return;
  try { await api(`/trades/${id}`, { method: 'DELETE' }); toast('Trade deleted'); closeDetailModal(); loadTrades(); }
  catch { toast('Delete failed'); }
}

function openTradeModal() { document.getElementById('trade-modal').classList.remove('hidden'); }
function closeTradeModal() { document.getElementById('trade-modal').classList.add('hidden'); }

async function submitTrade(e) {
  e.preventDefault();
  const form = document.getElementById('trade-form');
  const fd   = new FormData(form);
  const violations = [...document.querySelectorAll('[name=rv]:checked')].map(c => c.value);
  fd.set('rule_violations', JSON.stringify(violations));
  try { await fetch(BASE + '/api/trades/', { method: 'POST', body: fd }); toast('Trade saved ✓'); closeTradeModal(); form.reset(); loadTrades(); }
  catch { toast('Error saving trade'); }
}

let _dayRating = '';
function setDayRating(val) {
  _dayRating = val;
  document.querySelectorAll('.day-rating').forEach(b => {
    b.classList.toggle('btn-primary',   b.dataset.val === val);
    b.classList.toggle('btn-secondary', b.dataset.val !== val);
  });
}

async function loadDailyEntry() {
  const date = document.getElementById('daily-date')?.value;
  if (!date) return;
  try {
    const entries = await api('/journal/daily?limit=60');
    const entry   = entries.find(e => e.date === date);
    document.getElementById('d-premarket').value    = entry?.pre_market_bias   || '';
    document.getElementById('d-levels').value       = entry?.key_levels        || '';
    document.getElementById('d-macro').value        = entry?.macro_notes       || '';
    document.getElementById('d-postsession').value  = entry?.post_session_notes || '';
    if (entry?.day_rating) setDayRating(entry.day_rating);
  } catch {}
}

async function saveDailyEntry() {
  const date = document.getElementById('daily-date')?.value;
  if (!date) { toast('Select a date first'); return; }
  try {
    await apiForm('/journal/daily', { entry_date: date, pre_market_bias: document.getElementById('d-premarket').value, key_levels: document.getElementById('d-levels').value, macro_notes: document.getElementById('d-macro').value, post_session_notes: document.getElementById('d-postsession').value, day_rating: _dayRating });
    toast('Day log saved ✓'); loadDailyHistory();
  } catch { toast('Save failed'); }
}

async function loadDailyHistory() {
  try {
    const entries = await api('/journal/daily?limit=14');
    const el = document.getElementById('daily-history');
    if (!el) return;
    if (!entries.length) { el.innerHTML = '<p class="muted" style="padding:8px 0">No entries yet</p>'; return; }
    el.innerHTML = entries.map(e => {
      const ratingColor = {good:'var(--win)',neutral:'var(--neutral)',bad:'var(--loss)'}[e.day_rating] || 'var(--text2)';
      return `<div style="border-bottom:1px solid var(--border);padding:10px 0;cursor:pointer" onclick="selectDay('${e.date}')">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:13px;font-weight:500">${fmtDate(e.date + 'T00:00:00')}</span>
          ${e.day_rating ? `<span style="font-size:11px;color:${ratingColor};text-transform:uppercase">${e.day_rating}</span>` : ''}
        </div>
        ${e.pre_market_bias ? `<p style="font-size:12px;color:var(--text2);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${e.pre_market_bias}</p>` : ''}
      </div>`;
    }).join('');
  } catch {}
}

function selectDay(date) { document.getElementById('daily-date').value = date; loadDailyEntry(); }

async function loadMonthlyEntry() {
  const year = document.getElementById('m-year')?.value;
  const month = document.getElementById('m-month')?.value;
  if (!year || !month) return;
  try {
    const entries = await api('/journal/monthly');
    const e = entries.find(r => r.year == year && r.month == month);
    document.getElementById('m-start').value    = e?.start_balance    || '';
    document.getElementById('m-end').value      = e?.end_balance      || '';
    document.getElementById('m-goals').value    = e?.goals_set        || '';
    document.getElementById('m-achieved').value = e?.goals_achieved   || '';
    document.getElementById('m-lessons').value  = e?.lessons          || '';
    document.getElementById('m-next').value     = e?.next_goals       || '';
    document.getElementById('m-emotion').value  = e?.emotional_pattern || '';
  } catch {}
}

async function saveMonthlyEntry() {
  const year = document.getElementById('m-year')?.value;
  const month = document.getElementById('m-month')?.value;
  try {
    await apiForm('/journal/monthly', { year, month, start_balance: document.getElementById('m-start').value, end_balance: document.getElementById('m-end').value, goals_set: document.getElementById('m-goals').value, goals_achieved: document.getElementById('m-achieved').value, lessons: document.getElementById('m-lessons').value, next_goals: document.getElementById('m-next').value, emotional_pattern: document.getElementById('m-emotion').value });
    toast('Monthly review saved ✓'); loadMonthlyHistory();
  } catch { toast('Save failed'); }
}

async function loadMonthlyHistory() {
  try {
    const entries = await api('/journal/monthly');
    const el = document.getElementById('monthly-history');
    if (!el) return;
    if (!entries.length) { el.innerHTML = '<p class="muted" style="padding:8px 0">No reviews yet</p>'; return; }
    const months = ['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    el.innerHTML = entries.map(e => {
      const growth = e.start_balance && e.end_balance ? ((e.end_balance - e.start_balance) / e.start_balance * 100).toFixed(1) : null;
      return `<div style="border-bottom:1px solid var(--border);padding:10px 0">
        <div style="display:flex;justify-content:space-between">
          <span style="font-weight:500">${months[e.month]} ${e.year}</span>
          ${growth ? `<span class="mono ${growth >= 0 ? 'green' : 'red'}">${growth >= 0 ? '+' : ''}${growth}%</span>` : ''}
        </div></div>`;
    }).join('');
  } catch {}
}

document.addEventListener('DOMContentLoaded', () => {
  initTabs('#journal-tabs');
  const today = new Date().toISOString().split('T')[0];
  const dateEl = document.getElementById('daily-date');
  if (dateEl) { dateEl.value = today; loadDailyEntry(); }
  const now = new Date();
  const yearEl = document.getElementById('m-year');
  if (yearEl) {
    for (let y = now.getFullYear(); y >= 2024; y--) { const opt = document.createElement('option'); opt.value = y; opt.textContent = y; yearEl.appendChild(opt); }
    document.getElementById('m-month').value = now.getMonth() + 1;
    loadMonthlyEntry();
  }
  loadTrades(); loadDailyHistory(); loadMonthlyHistory();
  api('/market/state').then(d => { const lbl = document.getElementById('d-system-label'); if (lbl) lbl.textContent = d.label || d.state || '—'; }).catch(() => {});
});
