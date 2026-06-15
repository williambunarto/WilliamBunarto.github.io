/* playbook.js */
const STATE_LABELS = { super_long:'Super Long', long:'Long', neutral:'Neutral', short:'Short', super_short:'Super Short', any:'Any' };

async function loadPlaybook() {
  try {
    const setups = await api('/playbook/');
    const grid   = document.getElementById('playbook-grid');
    if (!grid) return;
    let statsMap = {};
    try { const stats = await api('/stats/by-setup'); stats.forEach(s => { statsMap[s.setup] = s; }); } catch {}
    if (!setups.length) {
      grid.innerHTML = `<div class="card" style="text-align:center;padding:40px;grid-column:1/-1"><div style="font-size:32px;margin-bottom:12px">📋</div><div style="font-weight:500;margin-bottom:8px">No setups yet</div><p class="muted" style="font-size:13px">Document your first setup.</p></div>`;
      return;
    }
    grid.innerHTML = setups.map(s => {
      const stateLabel = STATE_LABELS[s.best_market_state] || s.best_market_state || 'Any';
      const conds = Array.isArray(s.conditions) ? s.conditions : [];
      const perf  = statsMap[s.name?.toLowerCase().replace(/\s/g,'_')] || statsMap[s.name] || null;
      return `<div class="card">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
          <div><div style="font-weight:600;font-size:15px">${s.name}</div><div style="font-size:11px;color:var(--text3);margin-top:2px">Best state: ${stateLabel}</div></div>
          ${perf ? `<div style="text-align:right"><div class="mono ${perf.win_rate >= 55 ? 'green' : 'red'}" style="font-size:14px">${perf.win_rate}% WR</div><div style="font-size:11px;color:var(--text3)">${perf.total} trades</div></div>` : '<span style="font-size:11px;color:var(--text3)">No trades yet</span>'}
        </div>
        ${s.description ? `<p style="font-size:13px;color:var(--text2);margin-bottom:12px;line-height:1.5">${s.description}</p>` : ''}
        ${conds.length ? `<div style="margin-bottom:12px"><div style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text3);margin-bottom:6px">Required conditions</div>${conds.map(c => `<div style="display:flex;align-items:flex-start;gap:8px;font-size:12px;color:var(--text2);margin-bottom:4px"><span style="color:var(--accent);flex-shrink:0">✓</span><span>${c}</span></div>`).join('')}</div>` : ''}
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px"><button class="btn btn-secondary btn-sm" onclick="deleteSetup(${s.id})"><i class="ti ti-trash"></i></button></div>
      </div>`;
    }).join('');
  } catch(e) { console.warn('Playbook load failed', e); }
}

function openPlaybookModal() { document.getElementById('playbook-modal').classList.remove('hidden'); }

async function submitSetup(e) {
  e.preventDefault();
  const fd = new FormData(document.getElementById('playbook-form'));
  try {
    await fetch(BASE + '/api/playbook/', { method: 'POST', body: fd });
    toast('Setup saved ✓');
    document.getElementById('playbook-modal').classList.add('hidden');
    document.getElementById('playbook-form').reset();
    loadPlaybook();
  } catch { toast('Save failed'); }
}

async function deleteSetup(id) {
  if (!confirm('Delete this setup?')) return;
  try { await api(`/playbook/${id}`, { method: 'DELETE' }); toast('Deleted'); loadPlaybook(); }
  catch { toast('Delete failed'); }
}

document.addEventListener('DOMContentLoaded', loadPlaybook);
