/* app.js — shared logic across all pages */

const BASE = window.location.pathname.includes('/trade') ? '/trade' : '';

function toast(msg, dur = 2500) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), dur);
}

async function api(path, opts = {}) {
  const res = await fetch(BASE + '/api' + path, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiForm(path, data, method = 'POST') {
  const fd = new FormData();
  for (const [k, v] of Object.entries(data)) {
    if (v !== null && v !== undefined) fd.append(k, v);
  }
  return api(path, { method, body: fd });
}

const STATE_ICONS = { super_long: '⬆⬆', long: '⬆', neutral: '→', short: '⬇', super_short: '⬇⬇' };
const STATE_LABELS = { super_long: 'SUPER LONG', long: 'LONG', neutral: 'NEUTRAL', short: 'SHORT', super_short: 'SUPER SHORT' };

let _lastState = null;

async function refreshMarketBanner() {
  try {
    const d = await api('/market/state');
    _lastState = d;
    const banner = document.getElementById('market-banner');
    if (!banner) return;
    const icon   = STATE_ICONS[d.state] || '→';
    const label  = STATE_LABELS[d.state] || d.state;
    const reason = d.reason || '';
    const ts     = d.timestamp ? new Date(d.timestamp).toLocaleTimeString('en-GB', {hour:'2-digit',minute:'2-digit'}) : '';
    banner.innerHTML = `
      <span class="state-pill state-${d.state}">${icon} ${label}</span>
      <span class="banner-reason">${reason}</span>
      <span class="banner-time">↻ ${ts} UTC</span>
    `;
  } catch(e) { console.warn('[Banner] Could not load market state', e); }
}

function startBtcPriceFeed() {
  const el = document.getElementById('btc-price');
  if (!el) return;
  function connect() {
    const ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');
    ws.onopen = () => ws.send(JSON.stringify({ op: 'subscribe', args: ['tickers.BTCUSDT'] }));
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        const price = d?.data?.lastPrice;
        if (price) { el.textContent = '$' + parseFloat(price).toLocaleString('en-US', {minimumFractionDigits:0,maximumFractionDigits:0}); }
      } catch {}
    };
    ws.onclose = () => setTimeout(connect, 3000);
    ws.onerror = () => ws.close();
  }
  connect();
}

function setActiveNav() {
  const path = window.location.pathname;
  document.querySelectorAll('nav a').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === path ||
      (a.getAttribute('href') !== BASE + '/' && path.startsWith(a.getAttribute('href'))));
  });
}

function fmtUSDT(v) {
  if (v == null) return '—';
  const n = parseFloat(v);
  return (n >= 0 ? '+' : '') + n.toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2}) + ' USDT';
}
function fmtPrice(v) {
  if (v == null) return '—';
  return '$' + parseFloat(v).toLocaleString('en-US', {minimumFractionDigits:0,maximumFractionDigits:2});
}
function fmtR(v) {
  if (v == null) return '—';
  const n = parseFloat(v);
  return (n >= 0 ? '+' : '') + n.toFixed(2) + 'R';
}
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', {day:'2-digit',month:'short',year:'numeric'});
}
function outcomeBadge(o) {
  const map = {win:'badge-win',loss:'badge-loss',be:'badge-be'};
  return `<span class="badge ${map[o]||''}">${(o||'').toUpperCase()}</span>`;
}
function dirBadge(d) {
  return `<span class="badge badge-${d}">${(d||'').toUpperCase()}</span>`;
}

function initTabs(containerSelector) {
  const container = document.querySelector(containerSelector);
  if (!container) return;
  container.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      container.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      container.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const panel = container.querySelector(`#${tab.dataset.tab}`);
      if (panel) panel.classList.add('active');
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  refreshMarketBanner();
  startBtcPriceFeed();
  setActiveNav();
  setInterval(refreshMarketBanner, 5 * 60 * 1000);
});
