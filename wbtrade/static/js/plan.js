/* plan.js */
let _planDir = '';
let _currentBias = '';

function setDir(dir) {
  _planDir = dir;
  document.getElementById('plan-direction').value = dir;
  document.getElementById('dir-long').className  = 'btn ' + (dir === 'long'  ? 'btn-primary' : 'btn-secondary');
  document.getElementById('dir-short').className = 'btn ' + (dir === 'short' ? 'btn-danger'  : 'btn-secondary');
  updatePlanCalc();
}

function updatePlanCalc() {
  const entryLow = parseFloat(document.querySelector('[name=entry_zone_low]')?.value)  || 0;
  const entryHi  = parseFloat(document.querySelector('[name=entry_zone_high]')?.value) || 0;
  const sl       = parseFloat(document.querySelector('[name=stop_loss]')?.value)       || 0;
  const tp1      = parseFloat(document.querySelector('[name=tp1]')?.value)             || 0;
  const tp2      = parseFloat(document.querySelector('[name=tp2]')?.value)             || 0;
  const entry    = entryLow > 0 ? (entryLow + entryHi) / 2 || entryLow : 0;
  if (!entry || !sl) { document.getElementById('plan-rr-preview').style.display = 'none'; return; }
  const slDist = Math.abs(entry - sl);
  const slPct  = (slDist / entry * 100).toFixed(2);
  const rr1    = tp1 ? (Math.abs(tp1 - entry) / slDist).toFixed(2) : null;
  const rr2    = tp2 ? (Math.abs(tp2 - entry) / slDist).toFixed(2) : null;
  document.getElementById('pp-sl').textContent  = `${slPct}% — $${slDist.toFixed(0)}`;
  document.getElementById('pp-rr1').textContent = rr1 ? rr1 + ':1' : '—';
  document.getElementById('pp-rr2').textContent = rr2 ? rr2 + ':1' : '—';
  document.getElementById('pp-bias').textContent = _currentBias || '—';
  document.getElementById('plan-rr-preview').style.display = 'block';
}

async function submitPlan(e) {
  e.preventDefault();
  if (!_planDir) { toast('Select direction first'); return; }
  const fd = new FormData(document.getElementById('plan-form'));
  fd.set('market_state_at_plan', _currentBias);
  try {
    await fetch(BASE + '/api/plans/', { method: 'POST', body: fd });
    toast('Plan saved ✓');
    document.getElementById('plan-form').reset();
    _planDir = '';
    document.getElementById('dir-long').className  = 'btn btn-secondary';
    document.getElementById('dir-short').className = 'btn btn-secondary';
    loadPlans();
  } catch { toast('Save failed'); }
}

async function loadPlans() {
  try {
    const plans = await api('/plans/');
    const openEl = document.getElementById('plans-list');
    const pastEl = document.getElementById('plans-past');
    const open   = plans.filter(p => p.status === 'open');
    const past   = plans.filter(p => p.status !== 'open');
    if (!open.length) { openEl.innerHTML = '<p class="muted" style="padding:8px 0">No open plans</p>'; }
    else { openEl.innerHTML = open.map(p => planCard(p)).join(''); }
    if (!past.length) { pastEl.innerHTML = '<p class="muted" style="padding:8px 0">No history yet</p>'; }
    else { pastEl.innerHTML = past.slice(0,5).map(p => planCard(p, true)).join(''); }
  } catch {}
}

function planCard(p, compact = false) {
  const dirColor = p.direction === 'long' ? 'var(--win)' : 'var(--loss)';
  return `<div style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:10px">
    <div style="display:flex;justify-content:space-between;margin-bottom:8px">
      <span style="font-weight:500;color:${dirColor}">${p.direction?.toUpperCase()} ${p.market_state_at_plan ? '· ' + p.market_state_at_plan : ''}</span>
      <span style="font-size:11px;color:var(--text3)">${fmtDate(p.created_at)} · ${p.status}</span>
    </div>
    ${p.thesis ? `<p style="font-size:12px;color:var(--text2);margin-bottom:8px">${p.thesis}</p>` : ''}
    <div style="display:flex;gap:16px;font-size:12px;font-family:var(--mono)">
      <span class="muted">Entry: $${p.entry_zone_low?.toLocaleString()}–$${p.entry_zone_high?.toLocaleString()}</span>
      <span class="red">SL: $${p.stop_loss?.toLocaleString()}</span>
      ${p.tp1 ? `<span class="green">TP1: $${p.tp1?.toLocaleString()}</span>` : ''}
    </div>
    ${!compact && p.status === 'open' ? `<div style="display:flex;gap:6px;margin-top:10px"><button class="btn btn-secondary btn-sm" onclick="updatePlanStatus(${p.id},'executed')">Executed</button><button class="btn btn-secondary btn-sm" onclick="updatePlanStatus(${p.id},'cancelled')" style="color:var(--text3)">Cancel</button></div>` : ''}
  </div>`;
}

async function updatePlanStatus(id, status) {
  const fd = new FormData(); fd.append('status', status);
  try { await fetch(BASE + '/api/plans/' + id + '/status', { method: 'PUT', body: fd }); toast('Plan updated'); loadPlans(); }
  catch { toast('Update failed'); }
}

document.addEventListener('DOMContentLoaded', () => {
  loadPlans();
  api('/market/state').then(d => { _currentBias = d.label || d.state || ''; document.getElementById('pp-bias').textContent = _currentBias; }).catch(() => {});
});
