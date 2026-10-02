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

## Implemented (2026-09-27, iteration 5)
- Private Loans page (/loans): personal loans from private lenders — interest type (annual %, accrued = amount × rate × years) or profit-share type (linked to project; lender share = loan ÷ basis [default: my project contributions, optional override]; return = share × project final_profit; verified: $100k/$450k/$200k → 22.22% → $44,444.44)
- Project Outcome card on project Overview (owner-only) sets final_profit driving lender returns
- Shares: fractional quantity — input by quantity OR by total invested + buy price (qty auto-computed); P&L% vs buy price shown per row
- Custom cursor only — OS cursor hidden on desktop (cursor:none, pointer:fine)
- Equity by percentage: property equity uses my % from property partners; project equity = my% × (contributions + drawn − costs), shown as "My Equity" column on dashboard
- Partner profiles: admin sees 4 partner profile cards (position, projects, personal debts) with detail dialog; non-admin linked partners (admin sets partner_name in /admin) see a self-only view — their position, their projects, their debts, no other partners
- Feasibility v2: project types (single dwelling/duplex/multi-dwelling/subdivision + hints), 20 grouped cost fields (acquisition, approvals & design, construction, holding & finance, selling, other), loan amount → cash required, ROI on cash; FEASIBLE = profit > 0 AND ROI on cash ≥ 50%
- Dashboard: net worth toggle With debts / Without debts + debts breakdown (property / project loans / private loans)
- Testing: iteration_5 — 17/17 backend, 100% critical UI flows

## Implemented (2026-09-27, iteration 6)
- BUG FIX: property equity with partners now splits by % (was defaulting 100%); shared properties flow to partners' accounts via partner email, their dashboards show their % share; read-only for non-owners
- DatePicker: year/month dropdowns (1990–2100), caption deduped via CSS
- Partner Ledger: external lender transaction type (free-text lender → loan to Company); Company Settlement shows external/Company rows
- People page (/people, admin-only, backend-enforced): individual profiles — name, email, per-section visibility toggles (projects/properties/debts/loans); profile dialog aggregates position, projects, properties, personal debts, private loans
- Partner overview: admin sees profiles for core 4 + all people; linked partners get self-only view filtered by admin-set visibility flags
- Members can add their OWN contributions on shared projects (name locked, enforced server-side); everything else view-only for them; their private data never visible to admin
- Contributions: duplicate button per row (prefills dialog, just switch partner); edit button per row (PUT /api/contributions/{cid}, owner-only) — amounts editable after creation
- Testing: iteration_6 — 13/14 backend (1 spec gap now fixed), 100% UI flows; reported property-share bug verified fixed at API + UI

## Implemented (2026-10-02, iteration 7)
- Bulk expenses: project Cost Tracker "Bulk Add" dialog — multi-row entry (date/category/description/amount), POST /api/projects/{pid}/costs/bulk, owner-only
- Net worth report: Dashboard "Net worth report" button → full itemized report (investments w/ FX conversions, properties w/ equity shares, projects w/ invested+equity, private loans, partner positions, debts summary) — view in dialog + download .txt; any user generates their own; shares redacted unless PIN-unlocked
- People-linked inputs: ledger from/to selects = core 4 + People names; personal-debt person = dropdown + Custom; private-loan lender + project/property partner names have datalist suggestions from People
- Name migration: full names everywhere (Yash Sojitra, Sanjay Jogani, Pranay Jetani, Max Ma) — idempotent startup migration across ledger/contributions/costs/projects/properties/loans/people + admin user; FIXED latent bug where MAISON 7 equity/invested ($67k at 10%) didn't credit to Yash
- Verified: linked partners see only their own stance; People profiles editable
- Testing: iteration_7 — 11/11 backend, 100% UI flows

## Implemented (2026-10-02, iteration 8 — universal editing)
- Every input section now editable in place (owner-only, linked partners stay read-only): projects (name/address/partners/value via UI, PUT /api/projects/{pid} — frontend echoes final_profit so it is never wiped), costs (PUT /api/costs/{cid}), project loans (PUT /api/loans/{lid} — pops drawdowns so edits never wipe them; schedule/outstanding/monthly recalc live), drawdowns (PUT+DELETE /api/loans/{lid}/drawdowns/{idx}), ledger entries incl. settlements/personal debts/external lender (PUT /api/ledger/{tid}), private loans (PUT /api/personal-loans/{lid}, recomputes accrued/profit-share), feasibility studies (PUT /api/feasibility/{fid}, recomputes verdict)
- UX: all edit dialogs prefill and read "Save Changes"; Edit Project dialog capped at 85vh scrollable
- Testing: iteration_8 — 13/13 backend pytest (/app/backend/tests/test_iteration8.py), 100% UI flows incl. profit-preservation flow on MAISON 7

## Implemented (2026-10-02, iteration 9 — company split + project value)
- Company contributions: Add Contribution partner dropdown gains "Company — split by ownership %" → POST /api/projects/{pid}/contributions/split creates one row per partner (amount × %, remainder-to-last-partner keeps total exact; 400 if no partners; owner-only); live per-partner split preview in the dialog; option hidden in edit mode and for linked members
- Project value (as at): ProjectIn.current_value — editable in New/Edit Project dialog, shown as "Project Value" on project cards and 6th stat card on Project Detail
- Testing: iteration_9 — 5/5 backend (/app/backend/tests/test_iteration9.py), 100% UI flows; MAISON 7 real data untouched

## Backlog
- P2: split server.py (1558 lines) into routers (auth/projects/report/ledger)
- P1: Edit project (name/partners %) from UI; settle-up shortcut button per pair
- P1: Editable/manual FX rate override
- P2: Cash-flow history chart on dashboard; PDF report export
- P2: Import from the original Excel (32-34 CADMAN) format
- P3: Per-project currency support; server.py router split if more features added

## Next Tasks
1. Gather user feedback on MVP
2. Add edit-project UI + settle-up shortcuts
3. Optional Excel import for existing tracking data
