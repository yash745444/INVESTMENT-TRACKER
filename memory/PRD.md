# Yash Wealth Command Center — PRD

## Original Problem Statement
Personal wealth & construction project finance tracker:
1. Personal wealth dashboard from input data
2. Multiple construction project tracking with dated contributions
3. Two dashboards per project: overall project + 4-partner view (Yash, Sanjay, Pranay, Max)
4. Ownership percentage input per project
5. Money management tracker for the 4 partners (paid-on-behalf, settle-up, who owes whom, shareable report)
6. Personal investments (shares, term insurance, other) multi-currency USD/AUD/INR
7. Per-project cost/cash tracker
8. Per-project loan tracker with drawdowns, interest-only or amortizing repayments, repayment schedule
9. Net worth dashboard aggregating projects, debt, investments
10. Pairwise ledger report to explain to the other partners
11. Investment properties: current rent, purchase date, debt

## User Choices
- Auth: simple email/password login (owner: yash.sojitra34@gmail.com)
- FX: auto-fetched live rates (open.er-api.com, AUD base, cached 12h in Mongo)
- Base currency: AUD
- Loans: both interest-only and amortizing, chosen per loan
- Theme: sophisticated, subtle fonts (Outfit/Inter/JetBrains Mono), light/dark switchable

## Architecture
- FastAPI + MongoDB (motor) backend: /app/backend/server.py (all routes /api/*)
- React + Tailwind + shadcn/ui frontend: /app/frontend/src/{pages,components,context,lib}
- Auth: JWT httpOnly cookies (access 60min + refresh 7d), bcrypt, brute-force lockout (5 attempts / 15min)
- FX: RateService caches AUD-based rates, refreshes every 12h, stale fallback

## User Personas
- Yash (owner, single user): property developer managing joint ventures + personal wealth

## Implemented (2026-09-06)
- Login/logout, session persistence, theme toggle (light/dark)
- Net worth dashboard: AUD total, FX ticker, allocation pie, project positions table
- Projects CRUD with partner % validation (sums to 100)
- Project detail tabs: Overview, 4-Partner View, Contributions, Cost Tracker (6 categories), Loans
- Loans: interest-only & amortizing, drawdowns auto-update repayments, 12-month schedule
- Partner Ledger: paid-on-behalf + settlement transactions, pairwise who-owes-whom matrix, net position cards, report dialog + .txt download
- Investments: shares/term insurance/other, USD/AUD/INR with live AUD conversion
- Properties: rent, purchase date, price, current value, debt, equity
- Testing: 20/20 backend pytest green, all critical UI flows verified (iteration_1)

## Implemented (2026-09-06, iteration 2)
- Properties: partnership section per property (add/remove any partners with name + %, chips on card); all date inputs replaced with calendar-popover DatePicker
- Shares: market search (yfinance, US/ASX/NSE), auto price fetch + Refresh Prices, leverage 1×/2×/5× (worth = qty×price, exposure = worth×leverage), hover card shows worth (1px rounded)
- Shares privacy: hidden by default, 4-digit PIN (2468, env SHARES_PIN) unlocks for 12h via signed httpOnly cookie — server-side redaction in /api/investments + /api/dashboard (net worth excludes shares until unlocked)
- Projects: dynamic partners (add beyond core 4, % must sum 100); partners tab shows project partners; equity math removed — only "Invested" shown; loans shown as info only (not deducted)
- Dashboard: 4 stat cards clickable → section nav; custom gold cursor with trailing ring; PIN unlock dialog
- Partner Ledger: "Company Settlement" wording — Take from Company / Pay to Company per partner, report + .txt download use same wording
- Sidebar shows "Signed in as Yash"
- Testing: iteration_2 — 30/30 backend (20 old + 10 new), all UI flows green
- Fix: frontend/.env pointed at stale preview URL causing CORS failures — corrected and restarted
- Fix (2026-09-06, iteration 3): login "Network Error" — axios baseURL changed to same-origin relative `/api` so API calls work from any preview/deploy hostname (ingress routes /api → backend). Verified: 0 cross-origin requests, login + PIN flow green.

## Implemented (2026-09-06, iteration 4 — multi-user)
- Google login for all (Emergent-managed OAuth): login page Google button → session_id callback → /api/auth/google/session → session_token cookie (7d, db.user_sessions); same email links to existing admin account
- Admin backend for Yash: /admin page — list users, approve/reject/delete (delete purges all their data); pending users see "Awaiting Approval" and get 403 pending_approval on all data endpoints
- Multi-user data isolation: user_id on every collection; all queries user-scoped; existing data migrated to admin
- Project linking: partner entries carry optional email — matching registered users see the project with a "Shared" badge, READ-ONLY; owner-only writes (contributions/costs/loans/delete) enforced server-side
- Projects deletable by owner (UI + backend)
- Feasibility section (/feasibility): land, construction, bond, council/permits, design, finance/interest, legal, marketing, contingency %, other + expected revenue → live total cost, profit, margin %, ROI %, FEASIBLE verdict (profit>0, margin≥15%); savable/listable/deletable
- Partner Ledger: Personal Debts section (direction I paid/They paid, free-text person) — separate from company pool; "Sanjay owes me $X" pairs; included in report dialog + .txt download
- Testing: iteration_4 — 19/19 backend, 100% critical UI flows, isolation + sharing + gating verified

## eToro note
eToro has NO public API for portfolio sync. Shares holdings are entered once (symbol + qty + leverage); prices update live via Yahoo Finance (US/ASX/NSE) with Refresh Prices — functionally equivalent to live rates.
- eToro: no public API; manual holdings + live Yahoo prices (see note above)

## Backlog
- P1: Edit project (name/partners %) from UI; settle-up shortcut button per pair
- P1: Editable/manual FX rate override
- P2: Cash-flow history chart on dashboard; PDF report export
- P2: Import from the original Excel (32-34 CADMAN) format
- P3: Per-project currency support; server.py router split if more features added

## Next Tasks
1. Gather user feedback on MVP
2. Add edit-project UI + settle-up shortcuts
3. Optional Excel import for existing tracking data
