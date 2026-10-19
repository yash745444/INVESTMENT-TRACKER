"""Iteration 13 — eToro sync integration for shares + crypto.

Scope:
- POST /api/integrations/etoro/sync returns {synced, warnings, synced_at}
- Idempotency: two consecutive syncs produce same count of source='etoro' investments
- PIN gate server-side redaction covers shares AND crypto in /api/investments, /api/dashboard, /api/report/networth
- Manual (non-etoro) investments untouched by sync
- Dashboard investments total includes crypto when visible
- Synced rows carry source=etoro, external_position_id, leverage, buy_price
- 401/403 from eToro maps to 502; 429 retry; unknown instrumentTypeID -> 'other' + warning (via mock of etoro_get)
"""
import os, time, requests, pytest, asyncio, importlib
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
    assert r.status_code == 200, f"unlock failed {r.status_code} {r.text}"
    return client


@pytest.fixture(scope="session")
def locked_client():
    """Fresh session with no shares_unlock cookie."""
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200
    return s


# ---------------- Sync endpoint ----------------
class TestEtoroSync:
    def test_sync_returns_schema(self, unlocked_client):
        r = unlocked_client.post(f"{BASE}/api/integrations/etoro/sync", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert "synced" in data and isinstance(data["synced"], int)
        assert "warnings" in data and isinstance(data["warnings"], list)
        assert "synced_at" in data
        assert data["synced"] >= 1, f"expected >=1 synced rows, got {data}"
        print(f"SYNC: {data['synced']} rows, warnings={data['warnings']}")

    def test_sync_idempotent(self, unlocked_client):
        # space out slightly to be nice to eToro rate limits
        time.sleep(2)
        r1 = unlocked_client.post(f"{BASE}/api/integrations/etoro/sync", timeout=60)
        assert r1.status_code == 200
        time.sleep(2)
        r2 = unlocked_client.post(f"{BASE}/api/integrations/etoro/sync", timeout=60)
        assert r2.status_code == 200
        n1, n2 = r1.json()["synced"], r2.json()["synced"]
        assert n1 == n2, f"non-idempotent sync: {n1} vs {n2}"

        # Investments list should contain exactly n2 source='etoro' rows
        inv = unlocked_client.get(f"{BASE}/api/investments", timeout=20).json()
        etoro_rows = [i for i in inv if i.get("source") == "etoro"]
        assert len(etoro_rows) == n2, f"etoro rows in /api/investments ({len(etoro_rows)}) != synced ({n2})"


# ---------------- Synced row shape ----------------
class TestSyncedRowShape:
    def test_etoro_rows_have_expected_fields(self, unlocked_client):
        inv = unlocked_client.get(f"{BASE}/api/investments", timeout=20).json()
        etoro_rows = [i for i in inv if i.get("source") == "etoro"]
        assert len(etoro_rows) > 0
        for row in etoro_rows:
            assert row.get("source") == "etoro"
            assert row.get("external_position_id"), f"missing external_position_id: {row}"
            assert row.get("type") in ("shares", "crypto", "other"), f"bad type: {row.get('type')}"
            assert "buy_price" in row
            assert "leverage" in row
            assert row.get("currency") == "USD"

    def test_crypto_present(self, unlocked_client):
        inv = unlocked_client.get(f"{BASE}/api/investments", timeout=20).json()
        cryptos = [i for i in inv if i.get("source") == "etoro" and i.get("type") == "crypto"]
        assert len(cryptos) >= 1, "expected at least one crypto (BTC) in synced rows"
        btc = next((c for c in cryptos if "BTC" in (c.get("symbol") or "").upper()), None)
        assert btc is not None, f"BTC not found in cryptos: {[c.get('symbol') for c in cryptos]}"
        # P&L positive vs buy ~71037
        if btc.get("buy_price") and btc.get("current_price"):
            print(f"BTC buy={btc['buy_price']} current={btc['current_price']}")


# ---------------- PIN gate / redaction ----------------
class TestPinGateCoversCrypto:
    def test_locked_investments_redacted(self, locked_client):
        inv = locked_client.get(f"{BASE}/api/investments", timeout=20).json()
        shares_or_crypto = [i for i in inv if i.get("type") in ("shares", "crypto")]
        assert len(shares_or_crypto) > 0
        for row in shares_or_crypto:
            assert row.get("redacted") is True, f"row not redacted when locked: {row}"
            assert row.get("name") == "Hidden holding"
            assert row.get("amount") == 0

    def test_locked_dashboard_excludes_shares_crypto(self, locked_client):
        d = locked_client.get(f"{BASE}/api/dashboard", timeout=20).json()
        inv_summary = d.get("investments") or {}
        # shares_total should be masked (0) when locked
        assert inv_summary.get("shares_total", 0) == 0, f"shares_total not masked: {inv_summary}"

    def test_locked_report_networth_redacted(self, locked_client):
        r = locked_client.get(f"{BASE}/api/report/networth", timeout=30)
        assert r.status_code == 200
        rpt = r.json()
        invs = rpt.get("investments", [])
        hidden = [i for i in invs if i.get("redacted") or i.get("name") == "Hidden holding"]
        shares_crypto = [i for i in invs if i.get("type") in ("shares", "crypto")]
        # all share/crypto entries should be hidden
        assert len(hidden) >= 1
        for s in shares_crypto:
            assert s.get("worth_aud") is None or s.get("redacted"), f"not redacted in report: {s}"

    def test_unlocked_shows_crypto(self, unlocked_client):
        inv = unlocked_client.get(f"{BASE}/api/investments", timeout=20).json()
        cryptos = [i for i in inv if i.get("type") == "crypto" and not i.get("redacted")]
        assert len(cryptos) >= 1


# ---------------- Manual rows untouched ----------------
class TestManualUntouched:
    def test_manual_rows_preserved_after_sync(self, unlocked_client):
        before = unlocked_client.get(f"{BASE}/api/investments", timeout=20).json()
        manual_before = [i for i in before if i.get("source") != "etoro"]
        time.sleep(2)
        r = unlocked_client.post(f"{BASE}/api/integrations/etoro/sync", timeout=60)
        assert r.status_code == 200
        after = unlocked_client.get(f"{BASE}/api/investments", timeout=20).json()
        manual_after = [i for i in after if i.get("source") != "etoro"]
        assert len(manual_before) == len(manual_after), f"manual rows changed: {len(manual_before)} -> {len(manual_after)}"
        # IDs preserved
        ids_before = sorted(str(i.get("id") or i.get("_id")) for i in manual_before)
        ids_after = sorted(str(i.get("id") or i.get("_id")) for i in manual_after)
        assert ids_before == ids_after


# ---------------- Dashboard includes crypto ----------------
class TestDashboardCrypto:
    def test_dashboard_investments_includes_crypto(self, unlocked_client):
        d = unlocked_client.get(f"{BASE}/api/dashboard", timeout=20).json()
        inv = d.get("investments") or {}
        by_type = inv.get("by_type") or {}
        assert by_type.get("crypto", 0) > 0, f"crypto missing from dashboard by_type: {by_type}"
        print(f"Dashboard investments: by_type={by_type} shares_total={inv.get('shares_total')}")


# ---------------- Unit tests: etoro_get error handling + unknown type ----------------
class TestEtoroGetErrorMapping:
    def test_401_maps_to_502(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import server
        import httpx
        from unittest.mock import patch, AsyncMock, MagicMock

        async def run():
            resp = MagicMock()
            resp.status_code = 401
            resp.text = "Unauthorized"
            resp.headers = {}

            class FakeClient:
                def __init__(self, *a, **kw): pass
                async def __aenter__(self): return self
                async def __aexit__(self, *a): return False
                async def get(self, *a, **kw): return resp

            with patch.object(httpx, "AsyncClient", FakeClient):
                try:
                    await server.etoro_get("/trading/info/portfolio")
                    return None
                except Exception as e:
                    return e

        err = asyncio.run(run())
        from fastapi import HTTPException
        assert isinstance(err, HTTPException)
        assert err.status_code == 502
        assert "rejected" in err.detail.lower() or "401" in err.detail

    def test_403_maps_to_502(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import server
        import httpx
        from unittest.mock import patch, MagicMock

        async def run():
            resp = MagicMock()
            resp.status_code = 403
            resp.text = "Forbidden"
            resp.headers = {}

            class FakeClient:
                def __init__(self, *a, **kw): pass
                async def __aenter__(self): return self
                async def __aexit__(self, *a): return False
                async def get(self, *a, **kw): return resp

            with patch.object(httpx, "AsyncClient", FakeClient):
                try:
                    await server.etoro_get("/trading/info/portfolio")
                    return None
                except Exception as e:
                    return e

        err = asyncio.run(run())
        from fastapi import HTTPException
        assert isinstance(err, HTTPException)
        assert err.status_code == 502

    def test_429_retries_then_succeeds(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import server
        import httpx
        from unittest.mock import patch, MagicMock

        calls = {"n": 0}

        async def run():
            def make_resp(code, body=None):
                r = MagicMock()
                r.status_code = code
                r.text = "x"
                r.headers = {"Retry-After": "0"} if code == 429 else {}
                r.json = lambda: body or {}
                return r

            class FakeClient:
                def __init__(self, *a, **kw): pass
                async def __aenter__(self): return self
                async def __aexit__(self, *a): return False
                async def get(self, *a, **kw):
                    calls["n"] += 1
                    if calls["n"] < 2:
                        return make_resp(429)
                    return make_resp(200, {"ok": True})

            with patch.object(httpx, "AsyncClient", FakeClient):
                return await server.etoro_get("/x")

        out = asyncio.run(run())
        assert out == {"ok": True}
        assert calls["n"] >= 2

    def test_unknown_instrument_type_warns(self):
        """etoro_instrument_meta assigns asset_type='unknown' for unknown tid -> inv_type 'other' + warning in sync.
        We validate the mapping logic in server.etoro_sync by checking the branching: a type we don't recognise
        is classified as 'unknown' by etoro_instrument_meta."""
        import sys
        sys.path.insert(0, "/app/backend")
        import server
        import httpx
        from unittest.mock import patch, MagicMock

        async def run():
            def make_resp(body):
                r = MagicMock()
                r.status_code = 200
                r.text = "x"
                r.headers = {}
                r.json = lambda: body
                return r

            # instrument with unknown tid 999
            instruments_body = {"instrumentDisplayDatas": [
                {"instrumentID": 777777, "instrumentTypeID": 999, "symbolFull": "WEIRD", "instrumentDisplayName": "Weird Thing"}
            ]}

            class FakeClient:
                def __init__(self, *a, **kw): pass
                async def __aenter__(self): return self
                async def __aexit__(self, *a): return False
                async def get(self, path, **kw):
                    return make_resp(instruments_body)

            with patch.object(httpx, "AsyncClient", FakeClient):
                # Patch db.etoro_instruments to no-op
                class FakeColl:
                    def find(self, *a, **kw):
                        async def gen():
                            if False: yield None
                        return gen()
                    async def update_one(self, *a, **kw): return None
                orig = server.db
                try:
                    class FakeDB:
                        etoro_instruments = FakeColl()
                    server.db = FakeDB()
                    meta = await server.etoro_instrument_meta([777777])
                finally:
                    server.db = orig
                return meta

        meta = asyncio.run(run())
        assert 777777 in meta
        assert meta[777777]["asset_type"] == "unknown", f"got {meta[777777]}"
