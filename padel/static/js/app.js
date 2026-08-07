// Padel Wallet SPA — vanilla JS, no build step.
// All requests use RELATIVE paths ("api/...", "static/...") on purpose: the
// app can be mounted at any sub-path (/padel/, a Vercel/Railway preview
// root, a custom domain later) without a single hardcoded URL anywhere.

const state = {
  user: null,
  tab: "dashboard",
  players: [],
  packages: [],
  rateCards: [],
  sessions: [],
  payments: [],
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
  state.tab = tab;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  const renderers = {
    dashboard: renderDashboard,
    sessions: renderSessions,
    packages: renderPackages,
    "rate-cards": renderRateCards,
    players: renderPlayers,
    payments: renderPayments,
  };
  (renderers[tab] || renderDashboard)();
}

const content = () => document.getElementById("app-content");

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

// ---------------- Players ----------------

async function renderPlayers() {
  content().innerHTML = `<p class="muted">Loading players…</p>`;
  state.players = await api("api/players");
  const rows = state.players.map((p) => `
    <tr><td>${p.name}</td><td>${p.contact || "-"}</td></tr>
  `).join("") || `<tr><td colspan="2" class="muted">No players yet</td></tr>`;

  content().innerHTML = `
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
      renderPlayers();
    } catch (err) { toast(err.message, "error"); }
  });
}

// ---------------- Packages ----------------

async function renderPackages() {
  content().innerHTML = `<p class="muted">Loading packages…</p>`;
  state.packages = await api("api/packages");
  const rows = state.packages.map((p) => `
    <tr>
      <td>${fmtDate(p.purchase_date)}</td>
      <td>${p.location}</td>
      <td>${p.hours_remaining} / ${p.total_hours}</td>
      <td>${fmtMoney(p.price_paid)}</td>
      <td>${fmtMoney(p.cost_per_hour)}</td>
      <td>${badge(p.is_active ? "active" : "inactive", p.is_active ? "active" : "cancelled")}</td>
      <td>${p.is_active ? `<button class="btn small secondary" data-deactivate="${p.id}">Deactivate</button>` : ""}</td>
    </tr>
  `).join("") || `<tr><td colspan="7" class="muted">No packages yet</td></tr>`;

  content().innerHTML = `
    <div class="panel">
      <h2>Buy a 30-hour Package</h2>
      <form id="package-form" class="grid grid-4">
        <div class="form-row"><label>Location</label><input name="location" required placeholder="e.g. GOR Senayan"></div>
        <div class="form-row"><label>Total hours</label><input name="total_hours" type="number" value="30" required></div>
        <div class="form-row"><label>Price paid (IDR)</label><input name="price_paid" type="number" step="1" required></div>
        <div class="form-row"><label>Purchase date</label><input name="purchase_date" type="date"></div>
        <div><button class="btn" type="submit">Add package</button></div>
      </form>
    </div>
    <div class="panel">
      <h2>Packages / Court-hour Wallet</h2>
      <table><thead><tr><th>Purchased</th><th>Location</th><th>Hours left/total</th><th>Price paid</th><th>Cost/hour</th><th>Status</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table>
    </div>
  `;

  document.getElementById("package-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api("api/packages", {
        method: "POST",
        body: {
          location: fd.get("location"),
          total_hours: Number(fd.get("total_hours")),
          price_paid: Number(fd.get("price_paid")),
          purchase_date: fd.get("purchase_date") || null,
        },
      });
      toast("Package added");
      renderPackages();
    } catch (err) { toast(err.message, "error"); }
  });

  content().querySelectorAll("[data-deactivate]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api(`api/packages/${btn.dataset.deactivate}/deactivate`, { method: "POST" });
        toast("Package deactivated");
        renderPackages();
      } catch (err) { toast(err.message, "error"); }
    });
  });
}

// ---------------- Rate Cards ----------------

async function renderRateCards() {
  content().innerHTML = `<p class="muted">Loading rate cards…</p>`;
  state.rateCards = await api("api/rate-cards");
  const canEdit = state.user.role === "super_admin";
  const rows = state.rateCards.map((c) => `
    <tr>
      <td>${c.location}</td><td>${c.day_type}</td><td>${c.time_band}</td>
      <td>${c.time_start}–${c.time_end}</td><td>${fmtMoney(c.sell_price_per_hour)}</td>
      <td>${canEdit ? `<button class="btn small secondary" data-edit="${c.id}">Edit</button>` : ""}</td>
    </tr>
  `).join("") || `<tr><td colspan="6" class="muted">No rate cards yet</td></tr>`;

  content().innerHTML = `
    ${canEdit ? `
    <div class="panel">
      <h2 id="rc-form-title">New Rate Card</h2>
      <form id="rc-form" class="grid grid-4">
        <input type="hidden" name="id">
        <div class="form-row"><label>Location</label><input name="location" required></div>
        <div class="form-row"><label>Day type</label>
          <select name="day_type"><option value="weekday">weekday</option><option value="weekend">weekend</option></select>
        </div>
        <div class="form-row"><label>Time band label</label><input name="time_band" placeholder="e.g. Peak" required></div>
        <div class="form-row"><label>Start (HH:MM)</label><input name="time_start" placeholder="18:00" required></div>
        <div class="form-row"><label>End (HH:MM)</label><input name="time_end" placeholder="22:00" required></div>
        <div class="form-row"><label>Sell price / hour (IDR)</label><input name="sell_price_per_hour" type="number" required></div>
        <div><button class="btn" type="submit">Save</button> <button type="button" id="rc-cancel-edit" class="btn secondary hidden">Cancel edit</button></div>
      </form>
    </div>` : `<p class="muted">Only the super_admin (owner) can change rate cards.</p>`}
    <div class="panel">
      <h2>Rate Cards</h2>
      <table><thead><tr><th>Location</th><th>Day type</th><th>Band</th><th>Time</th><th>Sell price/hr</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table>
    </div>
  `;

  if (!canEdit) return;

  const form = document.getElementById("rc-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const id = fd.get("id");
    const body = {
      location: fd.get("location"), day_type: fd.get("day_type"), time_band: fd.get("time_band"),
      time_start: fd.get("time_start"), time_end: fd.get("time_end"),
      sell_price_per_hour: Number(fd.get("sell_price_per_hour")),
    };
    try {
      if (id) await api(`api/rate-cards/${id}`, { method: "PUT", body });
      else await api("api/rate-cards", { method: "POST", body });
      toast("Rate card saved");
      renderRateCards();
    } catch (err) { toast(err.message, "error"); }
  });

  document.getElementById("rc-cancel-edit").addEventListener("click", () => renderRateCards());

  content().querySelectorAll("[data-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = state.rateCards.find((c) => c.id === Number(btn.dataset.edit));
      document.getElementById("rc-form-title").textContent = `Edit Rate Card #${card.id}`;
      form.id.value = card.id;
      form.location.value = card.location;
      form.day_type.value = card.day_type;
      form.time_band.value = card.time_band;
      form.time_start.value = card.time_start;
      form.time_end.value = card.time_end;
      form.sell_price_per_hour.value = card.sell_price_per_hour;
      document.getElementById("rc-cancel-edit").classList.remove("hidden");
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

// ---------------- Payments ----------------

async function renderPayments() {
  content().innerHTML = `<p class="muted">Loading payments…</p>`;
  state.payments = await api("api/payments");
  const rows = state.payments.map((p) => `
    <tr>
      <td>#${p.session_id}</td><td>${p.player_name}</td>
      <td>${fmtMoney(p.amount_due)}</td><td>${fmtMoney(p.amount_paid)}</td>
      <td>${badge(p.status, p.status)}</td>
      <td>${p.status === "pending" ? `<button class="btn small" data-confirm="${p.id}" data-due="${p.amount_due}">Confirm</button>` : (p.status === "confirmed" ? `<button class="btn small secondary" data-unconfirm="${p.id}">Undo</button>` : "")}</td>
    </tr>
  `).join("") || `<tr><td colspan="6" class="muted">No payments yet</td></tr>`;

  content().innerHTML = `
    <div class="panel">
      <h2>Payments</h2>
      <table><thead><tr><th>Session</th><th>Player</th><th>Due</th><th>Paid</th><th>Status</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table>
    </div>
  `;

  content().querySelectorAll("[data-confirm]").forEach((btn) => {
    btn.addEventListener("click", async () => {
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
  content().querySelectorAll("[data-unconfirm]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api(`api/payments/${btn.dataset.unconfirm}/unconfirm`, { method: "POST" });
        toast("Payment confirmation undone");
        renderPayments();
      } catch (err) { toast(err.message, "error"); }
    });
  });
}

// ---------------- Sessions ----------------

async function renderSessions() {
  content().innerHTML = `<p class="muted">Loading sessions…</p>`;
  const [sessions, players] = await Promise.all([api("api/sessions"), api("api/players")]);
  state.sessions = sessions;
  state.players = players;

  content().innerHTML = `
    <div class="panel">
      <h2>New Session</h2>
      <form id="session-form" class="grid grid-4">
        <div class="form-row"><label>Date</label><input name="date" type="date" required></div>
        <div class="form-row"><label>Location</label><input name="location" required></div>
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
  const playerOptions = players.map((p) => `<option value="${p.id}">${p.name}</option>`).join("");

  function renderHourPickers() {
    const n = Math.max(1, Number(totalHoursInput.value) || 1);
    let html = `<p class="muted" style="margin-top:0">Assign players per hour (optional at creation — you can add players to a slot later too).</p>`;
    for (let i = 0; i < n; i++) {
      html += `
        <div class="form-row">
          <label>Hour ${i + 1} players</label>
          <select multiple size="4" data-hour="${i}">${playerOptions}</select>
        </div>`;
    }
    hourParticipantsEl.innerHTML = html || `<p class="muted">No players yet — add some in the Players tab.</p>`;
  }
  renderHourPickers();
  totalHoursInput.addEventListener("input", renderHourPickers);

  document.getElementById("session-submit").addEventListener("click", async () => {
    const form = document.getElementById("session-form");
    const fd = new FormData(form);
    const totalHours = Number(fd.get("total_hours"));
    const participantsByHour = [];
    hourParticipantsEl.querySelectorAll("select[data-hour]").forEach((sel) => {
      participantsByHour.push(Array.from(sel.selectedOptions).map((o) => Number(o.value)));
    });
    try {
      await api("api/sessions", {
        method: "POST",
        body: {
          date: fd.get("date"), location: fd.get("location"), start_time: fd.get("start_time"),
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
  const playerOptions = state.players.map((p) => `<option value="${p.id}">${p.name}</option>`).join("");
  const slots = s.hour_slots.map((slot) => `
    <div class="hour-slot">
      <div class="slot-head">
        <strong>Hour ${slot.hour_index}</strong>
        <span class="muted">${slot.start_time}–${slot.end_time} · package #${slot.package_id ?? "—"}</span>
      </div>
      ${slot.participants.map((p) => `
        <div class="participant-row">
          <span>${p.player_name} ${badge(p.status, p.status)}</span>
          <span>${fmtMoney(p.cost_share)}
            ${p.status === "active" && s.status === "active" ? `<button class="btn small danger" data-session-id="${s.id}" data-cancel-participant="${p.id}">Cancel</button>` : ""}
          </span>
        </div>
      `).join("") || `<p class="muted" style="margin:4px 0">No players assigned yet</p>`}
      ${s.status === "active" ? `
      <form data-add-participant data-session-id="${s.id}" data-slot-id="${slot.id}" style="display:flex;gap:6px;margin-top:6px">
        <select required>${playerOptions}</select>
        <button class="btn small secondary" type="submit">Add player to this hour</button>
      </form>` : ""}
    </div>
  `).join("");

  const equipment = s.equipment_charges.map((e) => `<li>${e.item}: ${fmtMoney(e.amount)} (owner-absorbed)</li>`).join("");

  return `
    <div class="session-card">
      <div class="session-summary">
        <span><strong>${fmtDate(s.date)}</strong> · ${s.location} · ${s.start_time}–${s.end_time} (${s.total_hours}h) ${badge(s.status, s.status)}</span>
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
