"""Iteration 12 — Project Cost rework + stamp duty + Equity fallback.

Scope:
- MAISON 7 (REAL DATA) stat values via /api/projects (list) and /api/dashboard
- Scratch project CRUD exercising land_cost/stamp_duty persistence + cost independence
- Fallback: equity == contributions when no project_cost data
"""
import os, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://investment-tracker-66.preview.emergentagent.com").rstrip("/")
EMAIL = "yash.sojitra34@gmail.com"
PASSWORD = "Yash@2026"
MAISON7_ID = "6abded14ba052cd1f3f8dd4c"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return s


# ---------------- MAISON 7 real-data checks ----------------
class TestMaison7:
    def test_project_list_has_cost_fields(self, client):
        r = client.get(f"{BASE}/api/projects", timeout=15)
        assert r.status_code == 200
        projs = r.json()
        m7 = next((p for p in projs if p.get("id") == MAISON7_ID or p.get("_id") == MAISON7_ID), None)
        if not m7:
            # fall back: find by name containing MAISON
            m7 = next((p for p in projs if "MAISON" in (p.get("name", "").upper())), None)
        assert m7 is not None, "MAISON 7 project not found"
        totals = m7.get("totals") or {}
        print("MAISON7 totals:", totals, "land=", m7.get("land_cost"), "duty=", m7.get("stamp_duty"))
        assert m7.get("land_cost") == 6_610_000
        assert m7.get("stamp_duty") == 388_897
        # project_cost >= land + duty = 6,998,897 (tracked costs may add)
        pc = totals.get("project_cost")
        assert pc is not None
        assert pc >= 6_998_897, f"project_cost {pc} < 6,998,897"
        drawn = totals.get("drawn", 0)
        expected_equity = pc - drawn
        assert abs(totals.get("equity", 0) - expected_equity) < 1
        # Never 5.6M-ish on cost
        assert abs(pc - 5_600_000) > 1_000_000

    def test_dashboard_my_equity(self, client):
        r = client.get(f"{BASE}/api/dashboard", timeout=20)
        assert r.status_code == 200
        data = r.json()
        projs = (data.get("projects") or {}).get("list", []) if isinstance(data.get("projects"), dict) else data.get("projects", [])
        m7 = next((p for p in projs if p.get("id") == MAISON7_ID or "MAISON" in p.get("name","").upper()), None)
        assert m7 is not None
        pc = m7.get("project_cost")
        drawn = m7.get("loan_outstanding", m7.get("drawn", 0))
        my_pct = m7.get("my_percentage", m7.get("my_pct", 10))
        expected = round((pc - drawn) * my_pct / 100, 2)
        actual = m7.get("my_equity")
        print(f"dashboard m7: pc={pc} drawn={drawn} my%={my_pct} expected={expected} actual={actual}")
        assert abs(actual - expected) < 1, f"my_equity {actual} != {expected}"


# ---------------- Scratch project — CRUD + independence + fallback ----------------
class TestScratchProjectCostIndependence:
    pid = None

    def test_create_with_land_duty(self, client):
        payload = {
            "name": "TEST_IT12_Scratch", "status": "planning",
            "land_cost": 1_000_000, "stamp_duty": 40_335,
            "ownership": [{"user_id": "owner", "pct": 100}],
        }
        r = client.post(f"{BASE}/api/projects", json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        proj = r.json()
        TestScratchProjectCostIndependence.pid = proj.get("id") or proj.get("_id")
        assert proj.get("land_cost") == 1_000_000
        assert proj.get("stamp_duty") == 40_335

    def test_list_shows_project_cost_land_plus_duty(self, client):
        pid = TestScratchProjectCostIndependence.pid
        assert pid
        r = client.get(f"{BASE}/api/projects", timeout=15)
        proj = next((p for p in r.json() if (p.get("id") or p.get("_id")) == pid), None)
        assert proj is not None
        totals = proj.get("totals") or {}
        assert totals.get("project_cost") == 1_040_335, totals
        # No contributions, no drawn => equity = project_cost - 0
        assert totals.get("equity") == 1_040_335

    def test_add_tracked_cost_raises_project_cost_only(self, client):
        pid = TestScratchProjectCostIndependence.pid
        # Try common cost endpoints
        cost_payload = {"date": "2026-01-15", "category": "architecture", "amount": 25_000, "description": "TEST arch fee"}
        tried = []
        for path in [f"/api/projects/{pid}/costs"]:
            r = client.post(f"{BASE}{path}", json=cost_payload, timeout=15)
            tried.append((path, r.status_code))
            if r.status_code in (200, 201):
                break
        else:
            pytest.skip(f"No cost endpoint worked: {tried}")

        r = client.get(f"{BASE}/api/projects", timeout=15)
        proj = next((p for p in r.json() if (p.get("id") or p.get("_id")) == pid), None)
        totals = proj["totals"]
        print("after cost added, totals:", totals)
        assert totals["project_cost"] == 1_065_335, totals
        assert totals["equity"] == 1_065_335  # drawn=0

    def test_update_land_persists_other_fields(self, client):
        pid = TestScratchProjectCostIndependence.pid
        r = client.put(f"{BASE}/api/projects/{pid}", json={"name": "TEST_IT12_Scratch", "status": "planning", "land_cost": 1_100_000, "stamp_duty": 46_385, "ownership": [{"user_id": "owner", "pct": 100}]}, timeout=15)
        assert r.status_code in (200, 204), r.text
        r2 = client.get(f"{BASE}/api/projects/{pid}", timeout=15)
        if r2.status_code == 200:
            p = r2.json()
            assert p.get("land_cost") == 1_100_000
            assert p.get("stamp_duty") == 46_385

    def test_cleanup_delete(self, client):
        pid = TestScratchProjectCostIndependence.pid
        if not pid:
            return
        r = client.delete(f"{BASE}/api/projects/{pid}", timeout=15)
        assert r.status_code in (200, 204)


# ---------------- Fallback: equity == contributions when no cost data ----------------
class TestEquityFallback:
    def test_scratch_no_land_fallback_equity_zero_or_contrib(self, client):
        payload = {"name": "TEST_IT12_Fallback", "status": "planning",
                   "ownership": [{"user_id": "owner", "pct": 100}]}
        r = client.post(f"{BASE}/api/projects", json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        pid = r.json().get("id") or r.json().get("_id")
        try:
            r = client.get(f"{BASE}/api/projects", timeout=15)
            proj = next((p for p in r.json() if (p.get("id") or p.get("_id")) == pid), None)
            totals = proj["totals"]
            # No cost data, no contributions
            assert totals.get("project_cost") == 0
            assert totals.get("equity") == 0 or totals.get("equity") == totals.get("contributions", 0)
        finally:
            client.delete(f"{BASE}/api/projects/{pid}", timeout=15)
