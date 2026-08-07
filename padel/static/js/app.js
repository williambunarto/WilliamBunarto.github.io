// Padel Wallet SPA — vanilla JS, no build step.
// All requests use RELATIVE paths ("api/...", "static/...") on purpose: the
// app can be mounted at any sub-path (/padel/, a Vercel/Railway preview
// root, a custom domain later) without a single hardcoded URL anywhere.

const MAX_PLAYERS_PER_HOUR = 12;
const DEFAULT_PLAYERS_PER_HOUR = 4;

const state = {
  user: null,
  tab: "dashboard",
  dataSubTab: "locations",
  locations: [],
  players: [],
  packages: [],
  rateCardsByLocation: {},
  sessions: [],
  payments: [],
  expandedPlayerId: null,
};

function api(path, opts = {}) {
  const options = {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
  };
  if (opts.body !== undefined) options.body = JSON.stringify(opts.body);
  return fetch(path, options).then(async (res) => {
    let data = null;
    try { data = await res.json(); } catch (_) { /* no body */ }
    if (!res.ok) {
      const msg = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
      throw new Error(msg);
    }
    return data;
  });
}

function toast(message, type = "success") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = `toast ${type}`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 3500);
}

function fmtMoney(n) {
  if (n === null || n === undefined) return "-";
  return "Rp " + Math.round(n).toLocaleString("id-ID");
}

function fmtDate(d) {
  if (!d) return "-";
  return new Date(d).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" });
}

function badge(text, cls) {
  return `<span class="badge ${cls}">${text}</span>`;
}

function playerOptionsHtml(selectedId) {
  const opts = state.players.map((p) => `<option value="${p.id}" ${String(p.id) === String(selectedId) ? "selected" : ""}>${p.name}</option>`);
  return `<option value="">— select player —</option>` + opts.join("");
}

function locationOptionsHtml(selectedId) {
  return state.locations.map((l) => `<option value="${l.id}" ${String(l.id) === String(selectedId) ? "selected" : ""}>${l.name}</option>`).join("");
}

// ---------------- Auth ----------------

async function checkAuth() {
  try {
    const { user } = await api("api/auth/me");
    state.user = user;
    showApp();
  } catch (_) {
    showLogin();
  }
}

function showLogin() {
  document.getElementById("login-screen").classList.remove("hidden");
  document.getElementById("app-shell").classList.add("hidden");
}

function showApp() {
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("app-shell").classList.remove("hidden");
  document.getElementById("whoami").textContent = `${state.user.name} (${state.user.role})`;
  document.querySelectorAll(".super-admin-only").forEach((el) => {
    el.classList.toggle("hidden", state.user.role !== "super_admin");
  });
  setTab(state.tab);
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  const errEl = document.getElementById("login-error");
  errEl.classList.add("hidden");
  try {
    const { user } = await api("api/auth/login", { method: "POST", body: { username, password } });
    state.user = user;
    showApp();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  await api("api/auth/logout", { method: "POST" });
  state.user = null;
  showLogin();
});

// ---------------- Tabs ----------------

document.getElementById("tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-tab]");
  if (!btn) return;
  setTab(btn.dataset.tab);
});

function setTab(tab) {
  if (tab === "users" && state.user.role !== "super_admin") tab = "dashboard";
  state.tab = tab;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  const renderers = {
    dashboard: renderDashboard,
    sessions: renderSessions,
    data: renderData,
    payments: renderPayments,
    users: renderUsers,
  };
  (renderers[tab] || renderDashboard)();
}

const content = () => document.getElementById("app-content");

async function loadCoreLists() {
  const [locations, players] = await Promise.all([api("api/locations"), api("api/players")]);
  state.locations = locations;
  state.players = players;
}

// ---------------- Dashboard ----------------

async function renderDashboard() {
  content().innerHTML = `<p class="muted">Loading dashboard…</p>`;
  const now = new Date();
  const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  try {
    const d = await api(`api/reports/dashboard?month=${month}`);
    const locRows = Object.entries(d.by_location || {}).map(([loc, v]) => `
      <tr><td>${loc}</td><td>${v.sessions}</td><td>${v.hours_used}</td><td>${fmtMoney(v.profit_confirmed)}</td></tr>
    `).join("") || `<tr><td colspan="4" class="muted">No sessions yet this month</td></tr>`;

    content().innerHTML = `
      <div class="panel">
        <h2>Dashboard — ${d.month}</h2>
        <div class="grid grid-4">
          <div class="stat-card"><div class="label">Profit (confirmed)</div><div class="value good">${fmtMoney(d.profit_confirmed)}</div></div>
          <div class="stat-card"><div class="label">Profit (incl. pending)</div><div class="value">${fmtMoney(d.profit_incl_pending)}</div></div>
          <div class="stat-card"><div class="label">Sessions this month</div><div class="value">${d.sessions_count}</div></div>
          <div class="stat-card"><div class="label">Hours used this month</div><div class="value">${d.hours_used_this_month}</div></div>
        </div>
      </div>
      <div class="panel">
        <h2>Hour Utilization (all-time)</h2>
        <div class="grid grid-4">
          <div class="stat-card"><div class="label">Hours purchased</div><div class="value">${d.hours_purchased_total}</div></div>
          <div class="stat-card"><div class="label">Hours remaining</div><div class="value">${d.hours_remaining_total}</div></div>
          <div class="stat-card"><div class="label">Hours used</div><div class="value">${d.hours_used_total}</div></div>
          <div class="stat-card"><div class="label">Utilization</div><div class="value">${d.utilization_pct}%</div></div>
        </div>
      </div>
      <div class="panel">
        <h2>By location this month</h2>
        <table><thead><tr><th>Location</th><th>Sessions</th><th>Hours used</th><th>Profit (confirmed)</th></tr></thead>
        <tbody>${locRows}</tbody></table>
      </div>
      <div class="panel">
        <h2>Player reliability</h2>
        <div id="player-report">Loading…</div>
      </div>
    `;
    const players = await api("api/reports/players");
    const rows = players.map((p) => `
      <tr>
        <td>${p.name}</td>
        <td>${p.sessions_count}</td>
        <td>${fmtMoney(p.total_paid)}</td>
        <td>${p.outstanding > 0 ? `<span class="error">${fmtMoney(p.outstanding)}</span>` : fmtMoney(0)}</td>
        <td>${fmtDate(p.last_played)}</td>
        <td>${p.reliability_pct === null ? "-" : p.reliability_pct + "%"}</td>
      </tr>
    `).join("") || `<tr><td colspan="6" class="muted">No players yet</td></tr>`;
    document.getElementById("player-report").innerHTML = `
      <table><thead><tr><th>Player</th><th>Sessions</th><th>Total paid</th><th>Outstanding</th><th>Last played</th><th>Reliability</th></tr></thead>
      <tbody>${rows}</tbody></table>
    `;
  } catch (err) {
    content().innerHTML = `<p class="error">${err.message}</p>`;
  }
}

// ---------------- Data (Locations / Players / Packages) ----------------

async function renderData() {
  content().innerHTML = `<p class="muted">Loading data…</p>`;
  await loadCoreLists();
  state.packages = await api("api/packages");

  content().innerHTML = `
    <div class="subtabs">
      <button class="subtab ${state.dataSubTab === "locations" ? "active" : ""}" data-subtab="locations">Locations</button>
      <button class="subtab ${state.dataSubTab === "players" ? "active" : ""}" data-subtab="players">Players</button>
      <button class="subtab ${state.dataSubTab === "packages" ? "active" : ""}" data-subtab="packages">Packages</button>
    </div>
    <div id="data-content"></div>
  `;

  content().querySelectorAll(".subtab").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.dataSubTab = btn.dataset.subtab;
      renderData();
    });
  });

  const target = document.getElementById("data-content");
  if (state.dataSubTab === "locations") await renderDataLocations(target);
  else if (state.dataSubTab === "players") await renderDataPlayers(target);
  else await renderDataPackages(target);
}

async function renderDataLocations(target) {
  const canEdit = state.user.role === "super_admin";
  const rows = state.locations.map((l) => `
    <div class="location-card">
      <div class="location-head" data-toggle-location="${l.id}">
        <strong>${l.name}</strong>
        <span class="muted">${l.notes || ""}</span>
      </div>
      <div class="location-body" id="location-body-${l.id}"></div>
    </div>
  `).join("") || `<p class="muted">No locations yet — add one above.</p>`;

  target.innerHTML = `
    <div class="panel">
      <h2>Register a Court / Venue</h2>
      <form id="location-form" class="grid grid-3">
        <div class="form-row"><label>Name</label><input name="name" required placeholder="e.g. GOR Senayan"></div>
        <div class="form-row"><label>Notes (optional)</label><input name="notes" placeholder="address, contact, etc."></div>
        <div><button class="btn" type="submit">Add location</button></div>
      </form>
    </div>
    <div class="panel">
      <h2>Locations (${state.locations.length})</h2>
      <p class="muted">Each court manages its own rate cards — click a location to expand.</p>
      ${rows}
    </div>
  `;

  document.getElementById("location-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api("api/locations", { method: "POST", body: { name: fd.get("name"), notes: fd.get("notes") || null } });
      toast("Location added");
      renderData();
    } catch (err) { toast(err.message, "error"); }
  });

  target.querySelectorAll("[data-toggle-location]").forEach((head) => {
    head.addEventListener("click", async () => {
      const card = head.closest(".location-card");
      const wasOpen = card.classList.contains("open");
      target.querySelectorAll(".location-card.open").forEach((c) => c.classList.remove("open"));
      if (wasOpen) return;
      card.classList.add("open");
      const locId = head.dataset.toggleLocation;
      const body = document.getElementById(`location-body-${locId}`);
      body.innerHTML = `<p class="muted">Loading rate cards…</p>`;
      const cards = await api(`api/rate-cards?location_id=${locId}`);
      state.rateCardsByLocation[locId] = cards;
      body.innerHTML = rateCardSectionHtml(locId, cards, canEdit);
      wireRateCardSection(body, locId, canEdit);
    });
  });
}

function rateCardSectionHtml(locId, cards, canEdit) {
  const rows = cards.map((c) => `
    <tr>
      <td>${c.day_type}</td><td>${c.time_band}</td><td>${c.time_start}–${c.time_end}</td>
      <td>${fmtMoney(c.sell_price_per_hour)}</td>
      <td>${canEdit ? `<button class="btn small secondary" data-edit-rc="${c.id}">Edit</button> <button class="btn small danger" data-delete-rc="${c.id}">Delete</button>` : ""}</td>
    </tr>
  `).join("") || `<tr><td colspan="5" class="muted">No rate cards for this court yet${canEdit ? " — add one below" : ""}.</td></tr>`;

  return `
    <table><thead><tr><th>Day type</th><th>Band</th><th>Time</th><th>Price/hr</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table>
    ${canEdit ? `
    <form data-rc-form data-location-id="${locId}" class="grid grid-4" style="margin-top:10px">
      <input type="hidden" name="id">
      <div class="form-row"><label>Day type</label>
        <select name="day_type"><option value="weekday">weekday</option><option value="weekend">weekend</option></select>
      </div>
      <div class="form-row"><label>Band label</label><input name="time_band" placeholder="e.g. Peak" required></div>
      <div class="form-row"><label>Start (HH:MM)</label><input name="time_start" placeholder="18:00" required></div>
      <div class="form-row"><label>End (HH:MM)</label><input name="time_end" placeholder="22:00" required></div>
      <div class="form-row"><label>Price/hour (IDR)</label><input name="sell_price_per_hour" type="number" required></div>
      <div><button class="btn small" type="submit">Save rate card</button> <button type="button" class="btn small secondary hidden" data-rc-cancel-edit>Cancel edit</button></div>
    </form>` : `<p class="muted">Only super_admin can change rate cards.</p>`}
  `;
}

function wireRateCardSection(body, locId, canEdit) {
  if (!canEdit) return;
  const form = body.querySelector("[data-rc-form]");
  const cancelBtn = body.querySelector("[data-rc-cancel-edit]");

  async function refresh() {
    const cards = await api(`api/rate-cards?location_id=${locId}`);
    state.rateCardsByLocation[locId] = cards;
    body.innerHTML = rateCardSectionHtml(locId, cards, canEdit);
    wireRateCardSection(body, locId, canEdit);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const id = fd.get("id");
    const payload = {
      location_id: Number(locId), day_type: fd.get("day_type"), time_band: fd.get("time_band"),
      time_start: fd.get("time_start"), time_end: fd.get("time_end"),
      sell_price_per_hour: Number(fd.get("sell_price_per_hour")),
    };
    try {
      if (id) await api(`api/rate-cards/${id}`, { method: "PUT", body: payload });
      else await api("api/rate-cards", { method: "POST", body: payload });
      toast("Rate card saved");
      await refresh();
    } catch (err) { toast(err.message, "error"); }
  });

  cancelBtn.addEventListener("click", refresh);

  body.querySelectorAll("[data-edit-rc]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = state.rateCardsByLocation[locId].find((c) => c.id === Number(btn.dataset.editRc));
      form.id.value = card.id;
      form.day_type.value = card.day_type;
      form.time_band.value = card.time_band;
      form.time_start.value = card.time_start;
      form.time_end.value = card.time_end;
      form.sell_price_per_hour.value = card.sell_price_per_hour;
      cancelBtn.classList.remove("hidden");
    });
  });
  body.querySelectorAll("[data-delete-rc]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this rate card?")) return;
      try {
        await api(`api/rate-cards/${btn.dataset.deleteRc}`, { method: "DELETE" });
        toast("Rate card deleted");
        await refresh();
      } catch (err) { toast(err.message, "error"); }
    });
  });
}

async function renderDataPlayers(target) {
  const rows = state.players.map((p) => `
    <tr><td>${p.name}</td><td>${p.contact || "-"}</td></tr>
  `).join("") || `<tr><td colspan="2" class="muted">No players yet</td></tr>`;

  target.innerHTML = `
    <div class="panel">
      <h2>Add Player</h2>
      <form id="player-form" class="grid grid-2">
        <div class="form-row"><label>Name</label><input name="name" required></div>
        <div class="form-row"><label>Contact (WA/phone)</label><input name="contact"></div>
        <div><button class="btn" type="submit">Add player</button></div>
      </form>
    </div>
    <div class="panel">
      <h2>Players (${state.players.length})</h2>
      <table><thead><tr><th>Name</th><th>Contact</th></tr></thead><tbody>${rows}</tbody></table>
    </div>
  `;

  document.getElementById("player-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api("api/players", { method: "POST", body: { name: fd.get("name"), contact: fd.get("contact") || null } });
      toast("Player added");
      renderData();
    } catch (err) { toast(err.message, "error"); }
  });
}

async function renderDataPackages(target) {
  const rows = state.packages.map((p) => `
    <tr>
      <td>${fmtDate(p.purchase_date)}</td>
      <td>${p.location_name}</td>
      <td>${p.hours_remaining} / ${p.total_hours}</td>
      <td>${fmtMoney(p.price_paid)}</td>
      <td>${fmtMoney(p.cost_per_hour)}</td>
      <td>${badge(p.is_active ? "active" : "inactive", p.is_active ? "active" : "cancelled")}</td>
      <td>${p.is_active ? `<button class="btn small secondary" data-deactivate="${p.id}">Deactivate</button>` : ""}</td>
    </tr>
  `).join("") || `<tr><td colspan="7" class="muted">No packages yet</td></tr>`;

  target.innerHTML = `
    <div class="panel">
      <h2>Buy an Hour Package <span class="muted" style="font-weight:400">(optional — sessions can run without one)</span></h2>
      ${state.locations.length === 0 ? `<p class="muted">Register a location first.</p>` : `
      <form id="package-form" class="grid grid-4">
        <div class="form-row"><label>Location</label><select name="location_id" required>${locationOptionsHtml()}</select></div>
        <div class="form-row"><label>Total hours</label><input name="total_hours" type="number" value="30" required></div>
        <div class="form-row"><label>Price paid (IDR)</label><input name="price_paid" type="number" step="1" required></div>
        <div class="form-row"><label>Purchase date</label><input name="purchase_date" type="date"></div>
        <div><button class="btn" type="submit">Add package</button></div>
      </form>`}
    </div>
    <div class="panel">
      <h2>Packages / Court-hour Wallet</h2>
      <table><thead><tr><th>Purchased</th><th>Location</th><th>Hours left/total</th><th>Price paid</th><th>Cost/hour</th><th>Status</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table>
    </div>
  `;

  const form = document.getElementById("package-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      try {
        await api("api/packages", {
          method: "POST",
          body: {
            location_id: Number(fd.get("location_id")),
            total_hours: Number(fd.get("total_hours")),
            price_paid: Number(fd.get("price_paid")),
            purchase_date: fd.get("purchase_date") || null,
          },
        });
        toast("Package added");
        renderData();
      } catch (err) { toast(err.message, "error"); }
    });
  }

  target.querySelectorAll("[data-deactivate]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api(`api/packages/${btn.dataset.deactivate}/deactivate`, { method: "POST" });
        toast("Package deactivated");
        renderData();
      } catch (err) { toast(err.message, "error"); }
    });
  });
}

// ---------------- Payments ----------------

async function renderPayments() {
  content().innerHTML = `<p class="muted">Loading payments…</p>`;
  const players = await api("api/reports/players");
  // Unpaid-first: sort by outstanding desc, then name.
  players.sort((a, b) => (b.outstanding - a.outstanding) || a.name.localeCompare(b.name));

  const rows = players.map((p) => `
    <tr class="player-row" data-player-row="${p.player_id}">
      <td>${p.name}</td>
      <td>${p.sessions_count}</td>
      <td>${fmtMoney(p.total_paid)}</td>
      <td>${p.outstanding > 0 ? `<span class="error"><strong>${fmtMoney(p.outstanding)}</strong></span>` : fmtMoney(0)}</td>
      <td>${p.reliability_pct === null ? "-" : p.reliability_pct + "%"}</td>
    </tr>
    <tr class="player-detail-row hidden" id="player-detail-${p.player_id}"><td colspan="5"></td></tr>
  `).join("") || `<tr><td colspan="5" class="muted">No players yet</td></tr>`;

  content().innerHTML = `
    <div class="panel">
      <h2>Payments — who hasn't paid</h2>
      <p class="muted">Sorted by outstanding balance. Click a player for the full breakdown.</p>
      <table>
        <thead><tr><th>Player</th><th>Sessions</th><th>Total paid</th><th>Outstanding</th><th>Reliability</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;

  content().querySelectorAll("[data-player-row]").forEach((row) => {
    row.addEventListener("click", () => togglePlayerDetail(row.dataset.playerRow));
  });

  if (state.expandedPlayerId) {
    await togglePlayerDetail(state.expandedPlayerId, true);
  }
}

async function togglePlayerDetail(playerId, forceOpen = false) {
  const detailRow = document.getElementById(`player-detail-${playerId}`);
  if (!detailRow) return;
  const isOpen = !detailRow.classList.contains("hidden");
  if (isOpen && !forceOpen) {
    detailRow.classList.add("hidden");
    state.expandedPlayerId = null;
    return;
  }
  document.querySelectorAll(".player-detail-row").forEach((r) => r.classList.add("hidden"));
  state.expandedPlayerId = playerId;
  detailRow.classList.remove("hidden");
  const cell = detailRow.querySelector("td");
  cell.innerHTML = `<p class="muted">Loading…</p>`;

  try {
    const detail = await api(`api/reports/players/${playerId}`);
    const payRows = detail.payments.map((p) => `
      <tr>
        <td>${fmtDate(p.session_date)}</td><td>${p.session_location || "-"}</td>
        <td>${fmtMoney(p.amount_due)}</td><td>${fmtMoney(p.amount_paid)}</td>
        <td>${badge(p.status, p.status)}</td>
        <td>${p.status === "pending" ? `<button class="btn small" data-confirm="${p.id}" data-due="${p.amount_due}">Confirm</button>` : (p.status === "confirmed" ? `<button class="btn small secondary" data-unconfirm="${p.id}">Undo</button>` : "")}</td>
      </tr>
    `).join("") || `<tr><td colspan="6" class="muted">No payments recorded</td></tr>`;

    cell.innerHTML = `
      <div class="player-detail-panel">
        <div class="grid grid-4">
          <div class="stat-card"><div class="label">Total paid</div><div class="value good">${fmtMoney(detail.total_paid)}</div></div>
          <div class="stat-card"><div class="label">Outstanding</div><div class="value ${detail.outstanding > 0 ? "bad" : ""}">${fmtMoney(detail.outstanding)}</div></div>
          <div class="stat-card"><div class="label">Sessions played</div><div class="value">${detail.sessions_count}</div></div>
          <div class="stat-card"><div class="label">Reliability</div><div class="value">${detail.reliability_pct === null ? "-" : detail.reliability_pct + "%"}</div></div>
        </div>
        <table style="margin-top:10px">
          <thead><tr><th>Date</th><th>Location</th><th>Due</th><th>Paid</th><th>Status</th><th></th></tr></thead>
          <tbody>${payRows}</tbody>
        </table>
      </div>
    `;

    cell.querySelectorAll("[data-confirm]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const due = btn.dataset.due;
        const amount = prompt("Amount received (IDR):", due);
        if (amount === null) return;
        const note = prompt("Proof note (optional, e.g. transfer ref):", "") || null;
        try {
          await api(`api/payments/${btn.dataset.confirm}/confirm`, {
            method: "POST", body: { amount_paid: Number(amount), proof_note: note },
          });
          toast("Payment confirmed");
          renderPayments();
        } catch (err) { toast(err.message, "error"); }
      });
    });
    cell.querySelectorAll("[data-unconfirm]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          await api(`api/payments/${btn.dataset.unconfirm}/unconfirm`, { method: "POST" });
          toast("Payment confirmation undone");
          renderPayments();
        } catch (err) { toast(err.message, "error"); }
      });
    });
  } catch (err) {
    cell.innerHTML = `<p class="error">${err.message}</p>`;
  }
}

// ---------------- Users (super_admin only) ----------------

async function renderUsers() {
  content().innerHTML = `<p class="muted">Loading users…</p>`;
  const users = await api("api/users");
  const rows = users.map((u) => `
    <tr>
      <td>${u.name}</td><td>${u.username}</td><td>${badge(u.role, u.role === "super_admin" ? "confirmed" : "pending")}</td>
      <td>
        <button class="btn small secondary" data-edit-user="${u.id}">Edit</button>
        ${u.id !== state.user.id ? `<button class="btn small danger" data-delete-user="${u.id}">Delete</button>` : `<span class="muted">(you)</span>`}
      </td>
    </tr>
  `).join("") || `<tr><td colspan="4" class="muted">No users</td></tr>`;

  content().innerHTML = `
    <div class="panel">
      <h2 id="user-form-title">New Admin User</h2>
      <form id="user-form" class="grid grid-4">
        <input type="hidden" name="id">
        <div class="form-row"><label>Name</label><input name="name" required></div>
        <div class="form-row"><label>Username</label><input name="username" required></div>
        <div class="form-row"><label>Password <span class="muted" id="pw-hint"></span></label><input name="password" type="text"></div>
        <div class="form-row"><label>Role</label>
          <select name="role"><option value="admin">admin</option><option value="super_admin">super_admin</option></select>
        </div>
        <div><button class="btn" type="submit">Save user</button> <button type="button" id="user-cancel-edit" class="btn secondary hidden">Cancel edit</button></div>
      </form>
    </div>
    <div class="panel">
      <h2>Users (${users.length})</h2>
      <table><thead><tr><th>Name</th><th>Username</th><th>Role</th><th></th></tr></thead><tbody>${rows}</tbody></table>
    </div>
  `;

  const form = document.getElementById("user-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const id = fd.get("id");
    const body = { name: fd.get("name"), username: fd.get("username"), role: fd.get("role") };
    if (fd.get("password")) body.password = fd.get("password");
    try {
      if (id) {
        await api(`api/users/${id}`, { method: "PUT", body });
      } else {
        if (!body.password) throw new Error("Password is required for a new user");
        await api("api/users", { method: "POST", body });
      }
      toast("User saved");
      renderUsers();
    } catch (err) { toast(err.message, "error"); }
  });

  document.getElementById("user-cancel-edit").addEventListener("click", renderUsers);

  content().querySelectorAll("[data-edit-user]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const u = users.find((x) => x.id === Number(btn.dataset.editUser));
      document.getElementById("user-form-title").textContent = `Edit ${u.username}`;
      form.id.value = u.id;
      form.name.value = u.name;
      form.username.value = u.username;
      form.role.value = u.role;
      form.password.value = "";
      document.getElementById("pw-hint").textContent = "(leave blank to keep current password)";
      document.getElementById("user-cancel-edit").classList.remove("hidden");
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
  content().querySelectorAll("[data-delete-user]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this user? This cannot be undone.")) return;
      try {
        await api(`api/users/${btn.dataset.deleteUser}`, { method: "DELETE" });
        toast("User deleted");
        renderUsers();
      } catch (err) { toast(err.message, "error"); }
    });
  });
}

// ---------------- Sessions ----------------

async function renderSessions() {
  content().innerHTML = `<p class="muted">Loading sessions…</p>`;
  const [sessions] = await Promise.all([api("api/sessions")]);
  await loadCoreLists();
  state.sessions = sessions;

  if (state.locations.length === 0) {
    content().innerHTML = `<div class="panel"><p class="muted">No locations registered yet. Go to <strong>Data &gt; Locations</strong> to register a court first.</p></div>`;
    return;
  }

  content().innerHTML = `
    <div class="panel">
      <h2>New Session</h2>
      <form id="session-form" class="grid grid-4">
        <div class="form-row"><label>Date</label><input name="date" type="date" required></div>
        <div class="form-row"><label>Location</label><select name="location_id" required>${locationOptionsHtml()}</select></div>
        <div class="form-row"><label>Start time (HH:MM)</label><input name="start_time" placeholder="18:00" required></div>
        <div class="form-row"><label>Total hours</label><input name="total_hours" type="number" min="1" value="1" required></div>
      </form>
      <div id="hour-participants"></div>
      <button id="session-submit" class="btn">Create session</button>
    </div>
    <div class="panel">
      <h2>Sessions (${sessions.length})</h2>
      <div id="sessions-list"></div>
    </div>
  `;

  const totalHoursInput = document.querySelector('#session-form [name="total_hours"]');
  const hourParticipantsEl = document.getElementById("hour-participants");

  function slotHtml(hourIdx, slotIdx) {
    return `
      <div class="player-slot" data-slot>
        <select data-player-select>${playerOptionsHtml()}</select>
        <button type="button" class="btn small danger" data-remove-slot title="Remove this slot">×</button>
      </div>`;
  }

  function renderHourPickers() {
    const n = Math.max(1, Number(totalHoursInput.value) || 1);
    let html = `<p class="muted" style="margin-top:0">Each hour defaults to ${DEFAULT_PLAYERS_PER_HOUR} players (max ${MAX_PLAYERS_PER_HOUR}). Leave a slot on "— select player —" to fill in later.</p>`;
    for (let h = 0; h < n; h++) {
      html += `
        <div class="form-row hour-picker" data-hour="${h}">
          <label>Hour ${h + 1} players</label>
          <div class="player-slots" data-hour-slots="${h}">
            ${Array.from({ length: DEFAULT_PLAYERS_PER_HOUR }).map((_, i) => slotHtml(h, i)).join("")}
          </div>
          <button type="button" class="btn small secondary" data-add-slot="${h}">+ Add player</button>
        </div>`;
    }
    hourParticipantsEl.innerHTML = html;
    wireSlotButtons();
  }

  function wireSlotButtons() {
    hourParticipantsEl.querySelectorAll("[data-add-slot]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const container = hourParticipantsEl.querySelector(`[data-hour-slots="${btn.dataset.addSlot}"]`);
        const count = container.querySelectorAll("[data-slot]").length;
        if (count >= MAX_PLAYERS_PER_HOUR) {
          toast(`Max ${MAX_PLAYERS_PER_HOUR} players per hour`, "error");
          return;
        }
        container.insertAdjacentHTML("beforeend", slotHtml(btn.dataset.addSlot, count));
        wireSlotButtons();
      });
    });
    hourParticipantsEl.querySelectorAll("[data-remove-slot]").forEach((btn) => {
      btn.addEventListener("click", () => btn.closest("[data-slot]").remove());
    });
  }

  renderHourPickers();
  totalHoursInput.addEventListener("input", renderHourPickers);

  document.getElementById("session-submit").addEventListener("click", async () => {
    const form = document.getElementById("session-form");
    const fd = new FormData(form);
    const totalHours = Number(fd.get("total_hours"));
    const participantsByHour = [];
    for (let h = 0; h < totalHours; h++) {
      const container = hourParticipantsEl.querySelector(`[data-hour-slots="${h}"]`);
      const ids = Array.from(container.querySelectorAll("[data-player-select]"))
        .map((s) => s.value).filter((v) => v !== "").map(Number);
      const dupes = ids.length !== new Set(ids).size;
      if (dupes) {
        toast(`Hour ${h + 1} has the same player selected twice`, "error");
        return;
      }
      participantsByHour.push(ids);
    }
    try {
      await api("api/sessions", {
        method: "POST",
        body: {
          date: fd.get("date"), location_id: Number(fd.get("location_id")), start_time: fd.get("start_time"),
          total_hours: totalHours, participants_by_hour: participantsByHour,
        },
      });
      toast("Session created");
      renderSessions();
    } catch (err) { toast(err.message, "error"); }
  });

  renderSessionsList();
}

function renderSessionsList() {
  const el = document.getElementById("sessions-list");
  if (!state.sessions.length) {
    el.innerHTML = `<p class="muted">No sessions yet</p>`;
    return;
  }
  el.innerHTML = state.sessions.map((s) => sessionCardHtml(s)).join("");

  el.querySelectorAll(".session-summary").forEach((row) => {
    row.addEventListener("click", () => row.closest(".session-card").classList.toggle("open"));
  });
  el.querySelectorAll("[data-cancel-session]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Fully cancel this session? Allocated hours will be returned to their packages.")) return;
      try {
        await api(`api/sessions/${btn.dataset.cancelSession}/cancel`, { method: "POST" });
        toast("Session cancelled");
        renderSessions();
      } catch (err) { toast(err.message, "error"); }
    });
  });
  el.querySelectorAll("[data-cancel-participant]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Cancel this player for this hour? The hour stays used; cost is re-split among the rest.")) return;
      try {
        await api(`api/sessions/${btn.dataset.sessionId}/participants/${btn.dataset.cancelParticipant}/cancel`, { method: "POST" });
        toast("Participant cancelled");
        renderSessions();
      } catch (err) { toast(err.message, "error"); }
    });
  });
  el.querySelectorAll("[data-add-participant]").forEach((form) => {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const sel = form.querySelector("select");
      try {
        await api(`api/sessions/${form.dataset.sessionId}/slots/${form.dataset.slotId}/participants`, {
          method: "POST", body: { player_id: Number(sel.value) },
        });
        toast("Player added to hour");
        renderSessions();
      } catch (err) { toast(err.message, "error"); }
    });
  });
  el.querySelectorAll("[data-equipment-form]").forEach((form) => {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const fd = new FormData(form);
      try {
        await api(`api/sessions/${form.dataset.sessionId}/equipment`, {
          method: "POST", body: { item: fd.get("item"), amount: Number(fd.get("amount")) },
        });
        toast("Equipment cost added");
        renderSessions();
      } catch (err) { toast(err.message, "error"); }
    });
  });
}

function sessionCardHtml(s) {
  const slots = s.hour_slots.map((slot) => {
    const activeCount = slot.participants.filter((p) => p.status === "active").length;
    return `
    <div class="hour-slot">
      <div class="slot-head">
        <strong>Hour ${slot.hour_index}</strong>
        <span class="muted">${slot.start_time}–${slot.end_time} · ${slot.package_id ? `package #${slot.package_id}` : "no package (unbacked)"} · ${activeCount} player${activeCount === 1 ? "" : "s"}</span>
      </div>
      ${slot.participants.map((p) => `
        <div class="participant-row">
          <span>${p.player_name} ${badge(p.status, p.status)}</span>
          <span>${fmtMoney(p.cost_share)}
            ${p.status === "active" && s.status === "active" ? `<button class="btn small danger" data-session-id="${s.id}" data-cancel-participant="${p.id}">Cancel</button>` : ""}
          </span>
        </div>
      `).join("") || `<p class="muted" style="margin:4px 0">No players assigned yet</p>`}
      ${s.status === "active" && activeCount < MAX_PLAYERS_PER_HOUR ? `
      <form data-add-participant data-session-id="${s.id}" data-slot-id="${slot.id}" style="display:flex;gap:6px;margin-top:6px">
        <select required>${playerOptionsHtml()}</select>
        <button class="btn small secondary" type="submit">Add player to this hour</button>
      </form>` : ""}
    </div>
  `;
  }).join("");

  const equipment = s.equipment_charges.map((e) => `<li>${e.item}: ${fmtMoney(e.amount)} (owner-absorbed)</li>`).join("");

  return `
    <div class="session-card">
      <div class="session-summary">
        <span><strong>${fmtDate(s.date)}</strong> · ${s.location_name} · ${s.start_time}–${s.end_time} (${s.total_hours}h) ${badge(s.status, s.status)}</span>
        <span>${fmtMoney(s.profit.profit_confirmed)} profit</span>
      </div>
      <div class="session-body">
        <p class="muted">Sell price snapshot: ${fmtMoney(s.sell_price_per_hour_snapshot)}/hour · rate_card #${s.rate_card_id ?? "-"}</p>
        <div class="grid grid-3">
          <div class="stat-card"><div class="label">Revenue confirmed</div><div class="value good">${fmtMoney(s.profit.revenue_confirmed)}</div></div>
          <div class="stat-card"><div class="label">Package cost</div><div class="value">${fmtMoney(s.profit.package_cost)}</div></div>
          <div class="stat-card"><div class="label">Equipment cost</div><div class="value">${fmtMoney(s.profit.equipment_cost)}</div></div>
        </div>
        <h3>Hour slots</h3>
        ${slots}
        <h3>Equipment (owner-absorbed)</h3>
        <ul>${equipment || "<li class='muted'>None</li>"}</ul>
        ${s.status === "active" ? `
        <form data-equipment-form data-session-id="${s.id}" style="display:flex;gap:6px;align-items:flex-end;margin-bottom:12px">
          <div class="form-row"><label>Item</label><input name="item" placeholder="Bola padel" required></div>
          <div class="form-row"><label>Amount</label><input name="amount" type="number" required></div>
          <button class="btn small secondary" type="submit">Add equipment cost</button>
        </form>
        <button class="btn danger small" data-cancel-session="${s.id}">Fully cancel session</button>
        ` : `<p class="muted">Session cancelled${s.cancelled_at ? " at " + fmtDate(s.cancelled_at) : ""}.</p>`}
      </div>
    </div>
  `;
}

checkAuth();
