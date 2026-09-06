"""Iteration 2: tests for new features - market data, shares unlock,
project multi-partner, property partners, dashboard shares_total, ledger totals."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://42c879b8-ebe5-42e4-882b-1c4e236579b3.preview.emergentagent.com").rstrip("/")
EMAIL = "yash.sojitra34@gmail.com"
PASSWORD = "Yash@2026"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return s


# ---------- shares/unlock ----------

class TestSharesUnlock:
    def test_unlock_correct_pin(self, session):
        r = session.post(f"{BASE_URL}/api/shares/unlock", json={"pin": "2468"}, timeout=10)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_unlock_wrong_pin(self, session):
        r = session.post(f"{BASE_URL}/api/shares/unlock", json={"pin": "0000"}, timeout=10)
        assert r.status_code == 403

    def test_unlock_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/shares/unlock", json={"pin": "2468"}, timeout=10)
        assert r.status_code == 401


# ---------- market data (yfinance live) ----------

class TestMarket:
    def test_search_apple(self, session):
        r = session.get(f"{BASE_URL}/api/market/search", params={"q": "apple"}, timeout=30)
        assert r.status_code == 200, r.text
        results = r.json().get("results", [])
        assert len(results) > 0
        # AAPL should appear
        symbols = [x["symbol"] for x in results]
        assert any("AAPL" in s for s in symbols)

    def test_quote_aapl(self, session):
        r = session.get(f"{BASE_URL}/api/market/quote/AAPL", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["symbol"] == "AAPL"
        assert isinstance(d["price"], (int, float)) and d["price"] > 0

    def test_quote_invalid_ticker_chars(self, session):
        r = session.get(f"{BASE_URL}/api/market/quote/BAD!TICK", timeout=10)
        assert r.status_code == 400


# ---------- projects multi-partner ----------

class TestProjectPartners:
    def test_project_with_five_partners(self, session):
        payload = {
            "name": "TEST_5partners",
            "partners": [
                {"name": "Yash", "percentage": 20},
                {"name": "Sanjay", "percentage": 20},
                {"name": "Pranay", "percentage": 20},
                {"name": "Max", "percentage": 20},
                {"name": "Romani", "percentage": 20},
            ],
        }
        r = session.post(f"{BASE_URL}/api/projects", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        try:
            g = session.get(f"{BASE_URL}/api/projects/{pid}", timeout=10)
            assert g.status_code == 200
            names = [p["name"] for p in g.json()["partners"]]
            assert "Romani" in names and len(names) == 5

            # my_percentage in dashboard uses Yash
            d = session.get(f"{BASE_URL}/api/dashboard", timeout=15).json()
            proj = next((p for p in d["projects"]["list"] if p["id"] == pid), None)
            assert proj is not None
            assert proj["my_percentage"] == 20
        finally:
            session.delete(f"{BASE_URL}/api/projects/{pid}", timeout=10)


# ---------- property partners ----------

class TestPropertyPartners:
    def test_property_with_partners(self, session):
        payload = {
            "name": "TEST_PropPartners", "current_value": 1000000, "debt": 400000,
            "purchase_price": 800000, "monthly_rent": 3000, "currency": "AUD",
            "partners": [
                {"name": "Pranay", "percentage": 50},
                {"name": "Sanjay", "percentage": 50},
            ],
        }
        r = session.post(f"{BASE_URL}/api/properties", json=payload, timeout=15)
        assert r.status_code == 200
        pid = r.json()["id"]
        try:
            got = session.get(f"{BASE_URL}/api/properties", timeout=10).json()
            found = next((p for p in got if p["id"] == pid), None)
            assert found is not None
            assert len(found["partners"]) == 2
            assert {p["name"] for p in found["partners"]} == {"Pranay", "Sanjay"}
        finally:
            session.delete(f"{BASE_URL}/api/properties/{pid}", timeout=10)


# ---------- dashboard shares_total + net worth logic ----------

class TestDashboardSharesTotal:
    def test_shares_total_returned(self, session):
        # add a share investment
        r = session.post(f"{BASE_URL}/api/investments", json={
            "type": "shares", "name": "TEST_AAPL", "currency": "USD", "amount": 0,
            "symbol": "AAPL", "quantity": 10, "leverage": 1, "current_price": 200,
            "price_currency": "USD",
        }, timeout=10)
        assert r.status_code == 200
        iid = r.json()["id"]
        try:
            d = session.get(f"{BASE_URL}/api/dashboard", timeout=15).json()
            assert "shares_total" in d["investments"]
            assert d["investments"]["shares_total"] > 0
            assert "my_contributions" in d["projects"]
            assert "loans_outstanding" in d["projects"]
        finally:
            session.delete(f"{BASE_URL}/api/investments/{iid}", timeout=10)


# ---------- ledger totals still work ----------

class TestLedgerTotals:
    def test_ledger_totals_shape(self, session):
        r = session.get(f"{BASE_URL}/api/ledger/balances", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "totals" in d
        for p in ("Yash", "Sanjay", "Pranay", "Max"):
            assert p in d["totals"]
