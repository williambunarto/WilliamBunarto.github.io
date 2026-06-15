/* stats.js */
const CHART_DEFAULTS = { color: '#e8eaed', gridColor: 'rgba(255,255,255,0.06)', font: { family: "'JetBrains Mono', monospace", size: 11 } };

function chartOpts(extra = {}) {
  return {
    responsive: true, maintainAspectRatio: true,
    plugins: { legend: { display: false }, tooltip: { bodyFont: CHART_DEFAULTS.font } },
    scales: {
      x: { ticks: { color: '#556070', font: CHART_DEFAULTS.font }, grid: { color: CHART_DEFAULTS.gridColor } },
      y: { ticks: { color: '#556070', font: CHART_DEFAULTS.font }, grid: { color: CHART_DEFAULTS.gridColor } },
    },
    ...extra,
  };
}

async function loadSummary() {
  try {
    const s = await api('/stats/summary');
    const pnlEl = document.getElementById('s-pnl');
    if (pnlEl) { pnlEl.textContent = (s.total_pnl >= 0 ? '+' : '') + s.total_pnl.toFixed(2) + ' USDT'; pnlEl.className = 'stat-value mono ' + (s.total_pnl >= 0 ? 'green' : 'red'); }
    const wrEl = document.getElementById('s-wr'); if (wrEl) wrEl.textContent = s.win_rate + '%';
    const trEl = document.getElementById('s-trades'); if (trEl) trEl.textContent = s.total + ' closed trades';
    const wlEl = document.getElementById('s-wl'); if (wlEl) wlEl.textContent = s.wins + 'W / ' + s.losses + 'L';
    const rEl  = document.getElementById('s-r');
    if (rEl) { rEl.textContent = (s.avg_r >= 0 ? '+' : '') + s.avg_r + 'R'; rEl.className = 'stat-value mono ' + (s.avg_r >= 0 ? 'green' : 'red'); }
    const bestEl  = document.getElementById('s-best');  if (bestEl)  bestEl.textContent  = '+' + s.best_trade.toFixed(2) + ' USDT';
    const worstEl = document.getElementById('s-worst'); if (worstEl) worstEl.textContent = s.worst_trade.toFixed(2) + ' USDT';
  } catch(e) { console.warn('Summary failed', e); }
}

async function loadEquityChart() {
  try {
    const data = await api('/stats/equity-curve');
    const ctx  = document.getElementById('chart-equity')?.getContext('2d');
    if (!ctx || !data.length) return;
    const labels = data.map(d => d.date);
    const values = data.map(d => d.cumulative);
    const positive = values[values.length - 1] >= 0;
    new Chart(ctx, { type: 'line', data: { labels, datasets: [{ data: values, borderColor: positive ? '#22c55e' : '#ef4444', borderWidth: 2, pointRadius: data.length < 20 ? 4 : 0, pointBackgroundColor: positive ? '#22c55e' : '#ef4444', fill: true, backgroundColor: positive ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)', tension: 0.3 }] }, options: chartOpts({ scales: { ...chartOpts().scales, y: { ...chartOpts().scales.y, ticks: { ...chartOpts().scales.y.ticks, callback: v => (v >= 0 ? '+' : '') + v.toFixed(0) + ' USDT' } } } }) });
  } catch(e) { console.warn('Equity chart failed', e); }
}

async function loadMonthlyChart() {
  try {
    const data = await api('/stats/monthly-pnl');
    const ctx  = document.getElementById('chart-monthly')?.getContext('2d');
    if (!ctx || !data.length) return;
    new Chart(ctx, { type: 'bar', data: { labels: data.map(d => d.month), datasets: [{ data: data.map(d => d.pnl), backgroundColor: data.map(d => d.pnl >= 0 ? 'rgba(34,197,94,0.7)' : 'rgba(239,68,68,0.7)'), borderRadius: 4 }] }, options: chartOpts({ scales: { ...chartOpts().scales, y: { ...chartOpts().scales.y, ticks: { ...chartOpts().scales.y.ticks, callback: v => (v >= 0 ? '+' : '') + v.toFixed(0) } } } }) });
  } catch(e) { console.warn('Monthly chart failed', e); }
}

async function loadSetupStats() {
  try {
    const data  = await api('/stats/by-setup');
    const tbody = document.getElementById('setup-body');
    if (!tbody) return;
    if (!data.length) { tbody.innerHTML = '<tr><td colspan="5" class="muted" style="text-align:center;padding:24px">No data yet</td></tr>'; return; }
    tbody.innerHTML = data.map(d => {
      const pnlClass = d.total_pnl >= 0 ? 'green' : 'red';
      return `<tr><td>${d.setup.replace('_',' ')}</td><td class="mono muted">${d.total}</td><td><span class="mono ${d.win_rate >= 55 ? 'green' : d.win_rate >= 45 ? 'amber' : 'red'}">${d.win_rate}%</span></td><td class="mono ${pnlClass}">${(d.total_pnl >= 0 ? '+' : '') + d.total_pnl.toFixed(2)} USDT</td><td class="mono ${d.avg_r >= 0 ? 'green' : 'red'}">${(d.avg_r >= 0 ? '+' : '') + d.avg_r}R</td></tr>`;
    }).join('');
  } catch(e) { console.warn('Setup stats failed', e); }
}

async function loadPsychStats() {
  try {
    const data  = await api('/stats/by-psychology');
    const tbody = document.getElementById('psych-body');
    if (!tbody) return;
    if (!data.length) { tbody.innerHTML = '<tr><td colspan="4" class="muted" style="text-align:center;padding:24px">No data yet</td></tr>'; return; }
    tbody.innerHTML = data.map(d => {
      const pnlClass = d.total_pnl >= 0 ? 'green' : 'red';
      const stateIcon = { disciplined:'✓', focused:'◎', distracted:'⚠', fomo:'!', revenge:'✗', overconfident:'!' }[d.psychology] || '';
      return `<tr><td>${stateIcon} ${d.psychology}</td><td class="mono muted">${d.total}</td><td><span class="mono ${d.win_rate >= 55 ? 'green' : d.win_rate >= 45 ? 'amber' : 'red'}">${d.win_rate}%</span></td><td class="mono ${pnlClass}">${(d.total_pnl >= 0 ? '+' : '') + d.total_pnl.toFixed(2)} USDT</td></tr>`;
    }).join('');
  } catch(e) { console.warn('Psych stats failed', e); }
}

document.addEventListener('DOMContentLoaded', () => { loadSummary(); loadEquityChart(); loadMonthlyChart(); loadSetupStats(); loadPsychStats(); });
