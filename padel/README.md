# Padel Wallet — Court Payment & Wallet Tracking System

Phase-1 implementation of the spec: buy 30-hour court packages, resell hours
per session to community players, track wallet balance with FIFO
consumption, split costs per hour with exact rounding, confirm manual
transfers, and report profit/utilization.

## Stack

- **Backend:** FastAPI + SQLAlchemy + SQLite (`padel.db`), session-cookie auth.
- **Frontend:** a single vanilla-JS page (`static/`), no build step.
- **Why this stack, not Vercel/Railway/Next.js:** the spec's suggested hosts
  need an account connection (OAuth/dashboard) that isn't available to this
  session — no Vercel/Railway credentials or MCP tool exist here. This repo
  already runs several apps the same way (`wbtrade/`, HealthOS) on the
  owner's own Oracle Cloud VM behind nginx, with a working GitHub Actions
  deploy pipeline and a real domain (`williambunarto.duckdns.org`) already
  in place. Reusing that pattern for `/padel` gets a real, persistent
  deployment today instead of a half-finished Vercel connection. Nothing
  about the app is tied to that host, though — see "Moving hosts" below.

## Running locally

```bash
cd padel
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# open http://127.0.0.1:8000/
```

First run auto-creates `data/padel.db` and seeds two users (see
**Credentials** below). Every route is defined and matched at its bare path
(`/api/...`, `/static/...`) — there is no app-level path prefix to
configure; whatever reverse proxy sits in front (nginx in prod) is what
decides the public `/padel` prefix, by stripping it before forwarding.

## Credentials (seeded on first boot — change these)

| username | password | role |
|---|---|---|
| `superadmin` | `superadmin` | `super_admin` |
| `admin` | `admin` | `admin` |

Set by the owner deliberately for convenience on this internal tool — the
super_admin can add proper accounts for real use any time via **Users**
(see below), and delete/rotate these seed ones once real accounts exist.

Override the seed passwords via `PADEL_SUPERADMIN_PASSWORD` /
`PADEL_ADMIN_PASSWORD` env vars **before the first run** (they only apply
when the users table is empty — changing them later does nothing; use the
app's own **Users** tab or a DB shell to rotate credentials post-seed). Set
`PADEL_SECRET_KEY` in production (`padel.env` on the server) or every
restart invalidates existing login sessions.

## Data model

Extends the original spec with a `locations` table and a few corrections
requested after the first round (see "Corrections" below): `users`,
`locations`, `court_packages`, `rate_cards`, `sessions` (`PlaySession` in
code — `Session` collides with SQLAlchemy's own class), `session_hour_slots`,
`players`, `slot_participants`, `equipment_charges`, `payments`. See
`database.py` for columns.

## Corrections (round 2 — implemented after initial delivery)

The owner asked for five corrections after using the first version; all
five are implemented and tested:

1. **Per-hour player count: 4 default, 12 max.** The session form now
   shows 4 player-select dropdowns per hour by default, with a "+ Add
   player" button (up to 12) and a per-slot remove button. The 12-player
   cap is enforced server-side too (`sessions_router.create_session` /
   `add_participant`), including a duplicate-player-in-the-same-hour check
   — the UI default of 4 is a convenience, not a hard minimum, so a
   session can still be created before every slot is confirmed and filled
   in later.
2. **Locations are now a registered entity, like players** — a new
   `locations` table (`locations_router.py`), CRUD'd from **Data →
   Locations**, and a `<select>` (not free text) on the session form.
   `court_packages`, `rate_cards`, and `sessions` all reference
   `location_id` now instead of a free-text string. The **Data** tab
   consolidates Locations, Players, and Packages into one page with
   sub-tabs (previously three separate top-level tabs).
3. **Packages are optional; rate cards live inside their location.**
   `logic.allocate_hours_fifo` no longer errors when a location has no (or
   insufficient) active packages — it backs as many hours as it can and
   leaves the rest `package_id = None` ("unbacked"), so a session can be
   created and billed with zero packages purchased; the profit calc simply
   counts no package cost for those hours (see the `hours_used`
   clarification in `logic.session_profit` — it tracks wallet-hours
   consumed specifically, not total hours played, since that's what the
   utilization metric is actually about). Rate cards moved from a
   standalone top-level page into each location's expandable row under
   **Data → Locations** ("every court has its own rate cards"), still
   mutable. Originally `super_admin`-only to change, per a later correction
   `admin` can now create/edit/delete rate cards too (`rate_cards_router.py`
   uses `get_current_user`, not `require_super_admin`) — the only
   remaining `super_admin`-only surface is **Users**.
4. **Payments page tracks who hasn't paid, with drill-down totals.** The
   page now lists players sorted by outstanding balance (unpaid-first)
   instead of a flat payment log; clicking a player calls
   `GET /api/reports/players/{id}` (new endpoint) and expands a panel with
   sum total paid, sum outstanding, sessions played, reliability %, and
   the itemized list of every payment for that player.
5. **New credentials + user management.** Seed accounts changed to
   `superadmin`/`superadmin` and `admin`/`admin` (see Credentials above).
   `super_admin` gets a new **Users** tab (hidden entirely for `admin` —
   checked both client-side for UI and server-side via `require_super_admin`
   on every `/api/users/*` route) with full CRUD for admin accounts:
   create, edit (name/username/role/password — blank password leaves it
   unchanged), and delete, with guards against deleting your own account
   or removing the last remaining `super_admin` (would lock everyone out).

## Business rules implemented

- **FIFO hour allocation** (`logic.allocate_hours_fifo`): active
  `court_packages` at the session's location, oldest `purchase_date` first;
  a multi-hour session automatically rolls onto the next package once one
  runs dry. **Packages are optional** (round-2 correction): if a location
  has no active packages, or not enough hours left to cover the whole
  session, the shortfall is simply left `package_id = None` ("unbacked")
  rather than blocking session creation.
- **Rate card resolution**: pass `rate_card_id` explicitly, or let the
  session auto-match by `location` + `day_type` (Sat/Sun = weekend) +
  the card whose `[time_start, time_end)` covers the session's start time.
  The **entire session** uses one snapshot price (`sell_price_per_hour_snapshot`),
  even if it spans hours that would fall under a different band —
  matching the spec's single snapshot field per session.
- **Cost split** (`logic.split_cost_ceil`): each hour's `sell_price_per_hour_snapshot`
  is divided by the number of *active* participants in that hour and
  **rounded up**. The rounding remainder is extra margin, never a shortfall
  the owner absorbs, per spec.
- **Cancellation**:
  - *Full cancel* (`POST /api/sessions/{id}/cancel`) — nobody played.
    Every allocated hour is returned to its `court_packages` row
    (`hours_remaining += 1`, reactivated if it had hit zero). Every
    participant is marked cancelled and every **pending** payment is voided.
    **Confirmed** payments are left alone — money already confirmed needs a
    human refund decision, not an automatic reversal.
  - *Partial cancel* (`POST /api/sessions/{id}/participants/{id}/cancel`) —
    one player backs out of one hour. The hour stays consumed (spec:
    "jam tetap terpakai, tidak dikembalikan"); the remaining active players
    in that hour slot are re-split for the hour's full price. Cancelling
    down to zero active players in a slot is allowed (the hour's cost then
    has nobody to bill — a real edge case worth a manual look, which is why
    it's not silently blocked).
- **Payments** are aggregated per (player, session) — `logic.sync_payments_for_session`
  recomputes `amount_due` from currently-active participation any time
  participants change, but never touches a payment already `confirmed`.
- **Profit** (`logic.session_profit`) exactly follows the spec formula:
  `Σ(confirmed cost_share) − (hours_used × cost_per_hour) − Σ(equipment_charges)`.
  Also reports a `profit_incl_pending` figure for a same-page optimistic view.
- **Rate cards are mutable**, open to both roles (`admin` and `super_admin`
  — changed from the original spec's `super_admin`-only restriction per a
  later correction); every session keeps its own price snapshot so editing
  a rate card never rewrites history — `rate_card_id` stays on the session
  purely for audit/reference.
- **Per-hour headcount**: 4–12 players per hour. 12 is a hard server-side
  cap (`MAX_PLAYERS_PER_HOUR` in `database.py`) enforced on both session
  creation and `add_participant`; 4 is only the UI's default slot count,
  not a server-enforced minimum (see Corrections #1 above).

## Assumptions / extensions beyond the spec (flagging these explicitly)

- Added a third payment status, `cancelled` (spec only lists
  `pending | confirmed`), used when a full session cancel voids a payment
  that was never collected. Needed somewhere to put "this was never going
  to be paid" that isn't `pending` (which would still show as outstanding).
- Package creation isn't restricted to `super_admin` — the spec restricts
  only `rate_cards` mutation to the owner; recording a package purchase
  (`court_packages`) is left open to both roles since JC may need to log
  one day-to-day.
- `is_active` on `court_packages` is auto-flipped to `false` when
  `hours_remaining` hits 0, and back to `true` on a full-cancel refund. It
  can also be flipped manually (`POST /api/packages/{id}/deactivate`) to
  retire a package recorded in error, without deleting its history.
- Day type (weekday/weekend) is derived from the session date
  (Sat/Sun = weekend) rather than a stored field, since the spec doesn't
  define a holiday calendar.
- Location CRUD is open to both roles (like players), not restricted to
  `super_admin`. Rate cards nested inside a location were originally
  `super_admin`-only too (matching the original spec), but a later owner
  correction opened them to `admin` as well — **Users** is now the only
  `super_admin`-exclusive area of the app.
- **No schema migrations** — `init_db()` only calls `Base.metadata.create_all()`,
  which creates missing tables but never alters existing ones. The round-2
  schema change (free-text `location` strings → `location_id` foreign
  keys) is a breaking change for any existing SQLite file; the production
  DB had to be wiped once by hand for this update (see git history / the
  session notes for the one-off "reset the padel DB" step). Any future
  schema change needs the same manual wipe-and-reseed until a real
  migration tool is worth adopting.
- Deleting a user (`DELETE /api/users/{id}`) doesn't touch historical
  `sessions.created_by` / `payments.confirmed_by` references to that user
  — SQLite doesn't enforce foreign keys by default in this setup, so those
  columns are left as a harmless dangling id rather than blocked or
  cascaded. Not shown anywhere in the UI today, so it's cosmetic for now.

## Deployment

This app deploys to the same Oracle Cloud VM as `wbtrade/`/HealthOS
(see the repo's root `CLAUDE.md`), reverse-proxied at `/padel/`:

- `padel.service` — systemd unit, runs `uvicorn` on `127.0.0.1:8002`.
- `scripts/patch_nginx.py` — idempotent patcher that inserts an
  `/padel/` location block into the existing `healthos` nginx site
  (mirrors `wbtrade/scripts/patch_nginx.py`).
- `.github/workflows/deploy-padel.yml` — copies the app to the server,
  installs deps into a venv, installs/restarts the systemd unit, patches
  nginx, and smoke-tests `http://williambunarto.duckdns.org/padel/`.
  Triggers on push to `main` under `padel/**`, or manually via
  **Actions → Deploy Padel Wallet to Server → Run workflow**.

**Status: live** at http://williambunarto.duckdns.org/padel/, running the
round-2 schema (locations, optional packages, users management — see
"Corrections" above) as of commit `673a090`, with the production DB
migrated via a one-off wipe (see the "No schema migrations" note above)
and fully re-verified — logins, RBAC, and static assets all green end to
end (see "Round 2 verification" below).

This session's own outbound network is HTTPS-only (no port 22 to the
server) and its GitHub API token gets a 403 on `workflow_dispatch`, so the
deploy couldn't be triggered directly from here — instead this branch was
merged into `main` (with explicit go-ahead), which fired the workflow the
normal way. Run #1 actually failed the smoke test: `patch_nginx.py` was
only editing `/etc/nginx/sites-available/healthos`, but on this server
`sites-enabled/healthos` is a **separate plain file, not a symlink** to
it (same quirk `wbtrade`'s deploy workflow already works around) — nginx
loads the sites-enabled copy, so the `/padel/` location block never
actually took effect even though `nginx -t` validated fine and the app
itself was healthy. Fixed by patching both copies; run #2 is green.

To redeploy after future changes, just push to `main` under `padel/**` —
same workflow, no manual steps needed. To run it manually instead:
**Actions → Deploy Padel Wallet to Server → Run workflow**.

Before trusting this with real money, set two things on the server that
aren't in git (secrets don't belong in the repo — the seed defaults below
are what it's running on right now):
```bash
# /home/ubuntu/padel/padel.env  (systemd reads this via EnvironmentFile=-)
PADEL_SECRET_KEY=<random 32+ byte string>
PADEL_OWNER_PASSWORD=<pick something better than the seed default>
PADEL_JC_PASSWORD=<pick something better than the seed default>
```
(`EnvironmentFile=-...` — the leading `-` means the unit still starts fine
before this file exists, using the seed defaults above; add it before
anyone relies on this for real money.)

### Moving hosts later (Vercel/Railway/custom domain)

Nothing in the app hardcodes `williambunarto.duckdns.org` or `/padel`:
- The frontend (`static/js/app.js`) makes every API/asset request with a
  **relative** path (`api/...`, `static/...`), resolved by the browser
  against whatever URL the page was loaded from. Move the whole app to a
  Vercel/Railway subdomain, or a brand-new custom domain, and the frontend
  needs zero changes.
- The backend has zero path-prefix configuration at all — every route,
  including the static-file mount, is defined at its bare path. We
  deliberately do **not** pass `FastAPI(root_path=...)`: with it set,
  Starlette's `Mount` (what `app.mount("/static", ...)` uses) starts
  requiring the prefix in the incoming path to match, while ordinary
  `@app.get(...)` routes don't — a real bug we hit (see below) where
  `/padel/` and every `/api/...` endpoint returned 200 through nginx but
  `/padel/static/js/app.js` 404'd, breaking the actual page. Whatever
  reverse proxy sits in front just needs to strip its own prefix before
  forwarding, same as it already does for the API routes.
- `PADEL_DB` is a plain SQLite file path today; swapping
  `create_engine(...)` in `database.py` for a Postgres DSN (e.g. Vercel
  Postgres, Railway Postgres, Neon) is the only change needed to move off
  SQLite — the ORM models don't change.

## What was verified in this session

Ran the app locally (`uvicorn` on a temp SQLite DB) and exercised the full
flow end-to-end with `curl` + a headless-browser pass (Playwright) over the
actual UI:
- login as both roles; `admin` correctly gets `403` on rate-card mutation
- package purchase, rate card creation, 3-hour session creation with
  per-hour participants
- cost split rounding (`Rp 100.000 ÷ 3 → Rp 33.334 × 3`, `Rp 2` margin)
- payment aggregation per player across hours, and payment confirmation
- **partial cancel**: a player leaving one hour re-splits that hour's cost
  onto whoever's left, without touching other hours or confirmed payments
- **full cancel**: allocated hours returned to the package
  (`hours_remaining` back to 30), pending payments voided, confirmed
  payments untouched
- **FIFO rollover**: a 1-hour package purchased earlier gets drained first,
  then a 3-hour session automatically rolls onto the next package for the
  remaining 2 hours
- **insufficient-hours guard**: requesting more hours than any active
  package covers fails with a clear 400, not a partially-created session
- dashboard/utilization/player-reliability reports
- the SPA itself in a real browser (dashboard, sessions, packages, rate
  cards, players, payments tabs all render and round-trip through the API
  with no console errors beyond the expected pre-login 401)
- the actual live deploy: systemd unit healthy, nginx serving `/padel/`
  with a 200, confirmed both by the workflow's own smoke test and by
  reading back the patched `sites-enabled`/`sites-available` config over SSH

A second, deeper pass (a scripted 85-check regression suite plus another
Playwright pass through the real UI) on top of that first pass found two
more real bugs, both fixed and redeployed:

- **`add_participant` left the new player's `cost_share` at 0.**
  `slot.participants` was already lazy-loaded (and cached in memory) by the
  duplicate-active-player check right above the insert. The new row was
  then created via a bare `db.add(SlotParticipant(hour_slot_id=slot.id,
  ...))` instead of through the ORM relationship, so SQLAlchemy never
  spliced it into that already-loaded collection — the cost-split
  recompute right after only saw the old participants, re-split the price
  across the old headcount, and left the new player's share at its
  creation default of 0 while everyone else kept a now-wrong share too.
  Fixed by appending to `slot.participants` directly (`routers/
  sessions_router.py`). Reproduced and confirmed fixed both via the
  regression script and visually in the browser (adding a 2nd player to
  an hour correctly re-split `Rp 80.000` solo → `Rp 40.000`/`Rp 40.000`).
- **Static assets 404'd through nginx in production despite `/padel/`
  itself returning 200.** Root cause: passing `FastAPI(root_path="/padel")`
  makes Starlette's `Mount` (used by `app.mount("/static", ...)`) require
  the `/padel` prefix in the incoming path to match, while ordinary
  `@app.get(...)` routes don't — an asymmetry that only showed up once
  something actually hit the static mount through the proxy (every other
  smoke test we'd run so far happened to be an API call or the SPA
  catch-all route, both unaffected). Confirmed by reproducing locally with
  the same env var the server uses, and by curling the app directly on its
  own port on the server (bypassing nginx) — same 404 either way, ruling
  nginx out. Fixed by dropping `root_path` entirely (`main.py`,
  `padel.service`) since it bought nothing we depended on.

Neither bug was caught by the first, shallower pass — the first pass never
added a *second* player to an already-populated hour slot, and never
exercised a live static-asset request end-to-end (only the SPA's root
document, which isn't served through the affected `Mount`). Worth keeping
in mind for future changes: adding a player to an existing hour and
loading the page's own JS/CSS through the real proxy are exactly the paths
that need explicit coverage, not just "the API responds."

### Round 2 verification (after the five corrections above)

A fresh 50-check regression script plus another Playwright pass through
every tab of the redesigned UI, all green:
- new credentials (`superadmin`/`superadmin`, `admin`/`admin`) work; old
  ones (`owner`/`jc`) correctly rejected
- locations: create, duplicate-name rejection, rename, both roles can
  create (not `super_admin`-restricted)
- rate cards: nested under a location, `GET ?location_id=` filtering,
  `admin` still gets `403` on mutation
- **a session created with zero active packages anywhere succeeds**
  (previously would have been impossible), hour slot has `package_id: null`,
  `package_cost: 0`, and — deliberately — `hours_used: 0` for that hour
  (utilization tracks wallet consumption, not gameplay volume); buying a
  package afterward correctly backs the *next* session
- duplicate player within one hour rejected; 13 players in one hour
  rejected; a 5th distinct player added post-creation correctly re-splits
  5-way and stays under the 12 cap
- `GET /api/reports/players/{id}` drill-down returns correct totals and
  itemized payments
- user management: `admin` blocked (`403`) from every `/api/users/*`
  route; create/login-as-new-user round-trip; duplicate username rejected;
  blank-password update leaves the password unchanged; can't delete your
  own account or the last `super_admin`
- full/partial cancel still correct with the new optional-package model
  (cancelling an already-unbacked session doesn't error trying to "return"
  hours that were never allocated)
- browser pass: 4 default player-select slots per hour confirmed by
  count, "+ Add player" appends a 5th, the per-slot "×" removes it back to
  4, location is a real `<select>`, Data tab's Locations sub-tab expands
  to show nested rate cards, Payments page sorts unpaid-first and expands
  a per-player breakdown panel on click, Users tab visible for
  `super_admin` and confirmed **not** rendered at all for `admin`

### Round 3 (rate cards opened to `admin`)

Owner correction: `admin` can now create/edit/delete rate cards, not just
view them (Users remains the only `super_admin`-exclusive area). Changed
`rate_cards_router.py`'s three mutation routes from `require_super_admin`
to `get_current_user`, and removed the now-dead `canEdit` gating in
`app.js`'s Locations rate-card UI. Verified: `admin` gets `200` (not
`403`) creating/updating/deleting a rate card via `curl`, and a Playwright
pass confirms the Edit/Delete buttons and the add-rate-card form render
for a logged-in `admin` under Data → Locations.

## Backlog (Phase 2, per spec — not built)

- WA/Telegram reminders for schedule & outstanding bills.
