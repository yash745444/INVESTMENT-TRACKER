"""Iteration 6.1 — Contribution edit (PUT /api/contributions/{cid}) owner-only."""
import os, pytest, requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
ADMIN = {"email": "yash.sojitra34@gmail.com", "password": "Yash@2026"}


@pytest.fixture(scope="module")
def admin_sess():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def maison7(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/projects", timeout=20)
    assert r.status_code == 200
    projects = r.json()
    p = next((x for x in projects if "MAISON 7" in x.get("name", "").upper() or "MAISON7" in x.get("name","").upper()), None)
    if not p:
        p = next((x for x in projects if "maison" in x.get("name","").lower()), None)
    assert p, f"MAISON 7 project not found. Available: {[x.get('name') for x in projects]}"
    return p


def test_create_edit_delete_contribution(admin_sess, maison7):
    pid = maison7["id"]
    partner_name = maison7["partners"][0]["name"]
    # CREATE
    payload = {"partner": partner_name, "date": "2026-01-15", "amount": 1000.0,
               "description": "TEST_EDIT_61"}
    r = admin_sess.post(f"{BASE_URL}/api/projects/{pid}/contributions", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    c = r.json()
    cid = c["id"]
    assert c["amount"] == 1000.0 and c["description"] == "TEST_EDIT_61"

    try:
        # EDIT via PUT
        new_partner = maison7["partners"][1]["name"] if len(maison7["partners"]) > 1 else partner_name
        upd = {"partner": new_partner, "date": "2026-02-20", "amount": 2500.0,
               "description": "TEST_EDIT_61_UPDATED"}
        r = admin_sess.put(f"{BASE_URL}/api/contributions/{cid}", json=upd, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["amount"] == 2500.0
        assert d["description"] == "TEST_EDIT_61_UPDATED"
        assert d["partner"] == new_partner
        assert d["date"] == "2026-02-20"

        # Verify persistence via list
        r = admin_sess.get(f"{BASE_URL}/api/projects/{pid}/contributions", timeout=20)
        row = next((x for x in r.json() if x["id"] == cid), None)
        assert row and row["amount"] == 2500.0 and row["partner"] == new_partner
    finally:
        # DELETE cleanup
        r = admin_sess.delete(f"{BASE_URL}/api/contributions/{cid}", timeout=20)
        assert r.status_code == 200


def test_edit_unauth_returns_401_or_403(maison7, admin_sess):
    """Unauthenticated session cannot PUT."""
    pid = maison7["id"]
    partner_name = maison7["partners"][0]["name"]
    r = admin_sess.post(f"{BASE_URL}/api/projects/{pid}/contributions",
                        json={"partner": partner_name, "date": "2026-01-15",
                              "amount": 10.0, "description": "TEST_EDIT_61_UNAUTH"}, timeout=20)
    cid = r.json()["id"]
    try:
        anon = requests.Session()
        r = anon.put(f"{BASE_URL}/api/contributions/{cid}",
                     json={"partner": partner_name, "date": "2026-01-15",
                           "amount": 99.0, "description": "x"}, timeout=20)
        assert r.status_code in (401, 403), f"got {r.status_code}"
    finally:
        admin_sess.delete(f"{BASE_URL}/api/contributions/{cid}", timeout=20)


def test_edit_nonexistent_returns_403(admin_sess):
    r = admin_sess.put(f"{BASE_URL}/api/contributions/507f1f77bcf86cd799439011",
                       json={"partner": "x", "date": "2026-01-01", "amount": 1.0, "description": "x"},
                       timeout=20)
    assert r.status_code == 403
