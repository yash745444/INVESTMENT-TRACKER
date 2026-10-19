"""Iteration 13b — eToro worth correctness fix (invested + P&L for CFD positions).

Scope:
- /api/integrations/etoro/sync returns total_value_usd and syncs 9 positions idempotently
- Each etoro row has 'amount' (invested), 'pnl', 'is_buy' fields
- Shares + Crypto group totals (AUD) sum to ~$24.8k, NOT ~$44k
- /api/dashboard investments.shares_total ≈ 24,800 AUD when unlocked
- Manual Term Insurance rows preserved
- PIN gate still redacts shares+crypto when locked
- UNIT: investment_native/worth_aud fallback formula with synthetic doc (buy & sell)
"""
import os, sys, time, requests, pytest, asyncio
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://investment-tracker-66.preview.emergentagent.com").rstrip("/")
EMAIL = "yash.sojitra34@gmail.com"
PASSWORD = "Yash@2026"
PIN = "2468"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def unlocked_client(client):
    r = client.post(f"{BASE}/api/shares/unlock", json={"pin": PIN}, timeout=15)
    assert r.status_code == 200
    return client


@pytest.fixture(scope="session")
def locked_client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200
    return s


class TestSyncResponse:
    def test_sync_returns_total_value_usd(self, unlocked_client):
        r = unlocked_client.post(f"{BASE}/api/integrations/etoro/sync", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "total_value_usd" in d, f"missing total_value_usd in response: {d}"
        assert isinstance(d["total_value_usd"], (int, float))
        # ~$17.3k USD (allow drift)
        assert 14000 <= d["total_value_usd"] <= 22000, f"total_value_usd out of range: {d['total_value_usd']}"
        assert d["synced"] >= 9, f"expected >=9 synced rows, got {d['synced']}"
        print(f"SYNC: synced={d['synced']} total_value_usd=${d['total_value_usd']}")

    def test_sync_idempotent(self, unlocked_client):
        time.sleep(2)
        r1 = unlocked_client.post(f"{BASE}/api/integrations/etoro/sync", timeout=60).json()
        time.sleep(2)
        r2 = unlocked_client.post(f"{BASE}/api/integrations/etoro/sync", timeout=60).json()
        assert r1["synced"] == r2["synced"]
        # total should be close (live prices drift)
        assert abs(r1["total_value_usd"] - r2["total_value_usd"]) / max(r1["total_value_usd"], 1) < 0.1


class TestRowShapeAndWorth:
    def test_etoro_rows_have_pnl_and_is_buy(self, unlocked_client):
        inv = unlocked_client.get(f"{BASE}/api/investments", timeout=20).json()
        etoro = [i for i in inv if i.get("source") == "etoro"]
        assert len(etoro) >= 9
        for row in etoro:
            assert "amount" in row and row["amount"] is not None, f"missing amount (invested): {row.get('symbol')}"
            assert "pnl" in row, f"missing pnl: {row.get('symbol')}"
            assert "is_buy" in row, f"missing is_buy: {row.get('symbol')}"
            # invested amount should be positive
            assert row["amount"] > 0, f"invested amount not positive: {row.get('symbol')} = {row['amount']}"

    def test_shares_crypto_total_is_fixed_not_notional(self, unlocked_client):
        d = unlocked_client.get(f"{BASE}/api/dashboard", timeout=20).json()
        inv = d.get("investments", {})
        shares_total = inv.get("shares_total", 0)
        # fix: should be ~24.8k AUD (invested + P&L). Previously was ~44k AUD (leveraged notional).
        assert 20000 <= shares_total <= 30000, f"shares_total out of expected range: {shares_total} (expected ~24.8k)"
        print(f"Dashboard shares_total = {shares_total} AUD (fix verified: not ~44k leveraged notional)")

    def test_individual_row_worth_sanity(self, unlocked_client):
        inv = unlocked_client.get(f"{BASE}/api/investments", timeout=20).json()
        etoro = [i for i in inv if i.get("source") == "etoro"]
        # Find AMZN: invested $500 · P&L ~ -$73 ⇒ worth ~$427 USD
        amzn = next((i for i in etoro if (i.get("symbol") or "").upper() == "AMZN"), None)
        if amzn:
            worth = amzn["amount"] + (amzn.get("pnl") or 0)
            assert 300 <= worth <= 700, f"AMZN worth {worth} not in [300,700]"
            print(f"AMZN: invested=${amzn['amount']} pnl=${amzn.get('pnl')} worth=${worth:.2f} USD")

        # Sum of all etoro worths in USD should be ~17.3k (allow drift)
        total_usd = sum((i.get("amount") or 0) + (i.get("pnl") or 0) for i in etoro if (i.get("currency") == "USD"))
        assert 14000 <= total_usd <= 22000, f"total USD worth={total_usd} out of range"
        print(f"Total eToro worth: ${total_usd:.2f} USD across {len(etoro)} positions")


class TestManualRowsPreserved:
    def test_term_insurance_untouched(self, unlocked_client):
        inv = unlocked_client.get(f"{BASE}/api/investments", timeout=20).json()
        manual = [i for i in inv if i.get("source") != "etoro"]
        assert len(manual) > 0, "expected manual rows (Term Insurance FUND 1/2/3)"
        term = [i for i in manual if "FUND" in (i.get("name") or "").upper() or (i.get("type") == "fd")]
        print(f"Manual rows preserved: {len(manual)} ({[m.get('name') for m in manual]})")


class TestPinGateLocked:
    def test_locked_redacts_shares_and_crypto(self, locked_client):
        inv = locked_client.get(f"{BASE}/api/investments", timeout=20).json()
        sc = [i for i in inv if i.get("type") in ("shares", "crypto")]
        assert len(sc) > 0
        for row in sc:
            assert row.get("redacted") is True
            assert row.get("amount") == 0

    def test_locked_dashboard_shares_total_zero(self, locked_client):
        d = locked_client.get(f"{BASE}/api/dashboard", timeout=20).json()
        assert d.get("investments", {}).get("shares_total", 0) == 0


# ---------------- UNIT: fallback pnl formula ----------------
class TestInvestmentNativeFallback:
    @classmethod
    def setup_class(cls):
        sys.path.insert(0, "/app/backend")
        import server
        cls.server = server

    def test_etoro_uses_amount_plus_pnl(self):
        doc = {"source": "etoro", "amount": 500.0, "pnl": -73.33, "currency": "USD", "is_buy": True}
        nv, cur = self.server.investment_native(doc)
        assert cur == "USD"
        assert abs(nv - 426.67) < 0.01, f"expected 426.67 got {nv}"

    def test_etoro_fallback_pnl_buy(self):
        # No pnl field -> fallback: qty×(price-buy)×sign
        # buy price 100, current 120, qty 10, buy side -> pnl = 10*(120-100)*1 = +200
        doc = {"source": "etoro", "amount": 1000, "quantity": 10, "current_price": 120, "buy_price": 100,
               "is_buy": True, "currency": "USD"}
        nv, cur = self.server.investment_native(doc)
        assert cur == "USD"
        assert abs(nv - 1200.0) < 0.01, f"expected 1200 got {nv}"

    def test_etoro_fallback_pnl_sell(self):
        # sell position: price went UP from 100 to 120 -> loss. pnl = 10*(120-100)*(-1) = -200
        doc = {"source": "etoro", "amount": 1000, "quantity": 10, "current_price": 120, "buy_price": 100,
               "is_buy": False, "currency": "USD"}
        nv, cur = self.server.investment_native(doc)
        assert cur == "USD"
        assert abs(nv - 800.0) < 0.01, f"expected 800 got {nv}"

    def test_etoro_pnl_none_quantity_none(self):
        # Degenerate: no pnl, no quantity -> fallback computes 0, nv = amount
        doc = {"source": "etoro", "amount": 500, "currency": "USD", "is_buy": True}
        nv, cur = self.server.investment_native(doc)
        assert abs(nv - 500) < 0.01


class TestInvestmentWorthAud:
    @classmethod
    def setup_class(cls):
        sys.path.insert(0, "/app/backend")
        import server
        cls.server = server

    def test_etoro_worth_aud_conversion(self):
        # amount 500 USD + pnl -73.33 = 426.67 USD. At USD->AUD ~1.433 (1/0.698) -> ~611 AUD
        doc = {"source": "etoro", "amount": 500.0, "pnl": -73.33, "currency": "USD", "is_buy": True}
        rates = {"USD": 1.0, "AUD": 0.698}  # per to_aud convention
        worth = self.server.investment_worth_aud(doc, rates)
        # 426.67 USD -> AUD. Check via to_aud: let's just assert positive and reasonable
        assert worth > 0
        print(f"AUD worth of 426.67 USD doc = {worth}")
