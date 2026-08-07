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
**Credentials** below). Set `PADEL_ROOT_PATH=` (empty) for local runs since
there's no reverse proxy stripping a `/padel` prefix; in production it
defaults to `/padel`.

## Credentials (seeded on first boot — change these)

| username | password | role |
|---|---|---|
| `owner` | `padel-owner-2026` | `super_admin` |
| `jc` | `padel-jc-2026` | `admin` |

Override the seed passwords via `PADEL_OWNER_PASSWORD` / `PADEL_JC_PASSWORD`
env vars **before the first run** (they only apply when the users table is
empty — changing them later does nothing; use the app or a DB shell to
rotate credentials post-seed). Set `PADEL_SECRET_KEY` in production
(`padel.env` on the server) or every restart invalidates existing login
sessions.

## Data model

Matches the spec 1:1 — `users`, `court_packages`, `rate_cards`, `sessions`
(`PlaySession` in code — `Session` collides with SQLAlchemy's own class),
`session_hour_slots`, `players`, `slot_participants`, `equipment_charges`,
`payments`. See `database.py` for columns.

## Business rules implemented

- **FIFO hour allocation** (`logic.allocate_hours_fifo`): active
  `court_packages` at the session's location, oldest `purchase_date` first;
  a multi-hour session automatically rolls onto the next package once one
  runs dry. Creating a session fails fast with a clear error if there
  aren't enough active hours anywhere, rather than silently leaving a slot
  unbacked by a package.
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
- **Rate cards are mutable**, restricted to `super_admin`
  (`auth.require_super_admin`); every session keeps its own price snapshot
  so editing a rate card never rewrites history — `rate_card_id` stays on
  the session purely for audit/reference.

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

**Status: live** at http://williambunarto.duckdns.org/padel/ (deployed via
`deploy-padel.yml` run #2, smoke test passed — `HTTP status: 200`).

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
- The backend's only path assumption is `PADEL_ROOT_PATH` (default
  `/padel`), an env var, used solely for OpenAPI/docs URL generation — the
  actual routes are always mounted at their bare paths (`/api/...`), so
  whatever reverse proxy sits in front decides the public prefix.
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

## Backlog (Phase 2, per spec — not built)

- WA/Telegram reminders for schedule & outstanding bills.
