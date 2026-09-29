from tests.conftest import DOWN


def add_site(client, name="Example", url="https://example.com/"):
    resp = client.post("/sites", json={"name": name, "url": url})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------- platform endpoints ----------

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


# ---------- sites ----------

def test_create_and_get_site(client):
    site = add_site(client)
    assert site["name"] == "Example"
    assert site["url"] == "https://example.com/"

    resp = client.get(f"/sites/{site['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == site["id"]


def test_list_sites(client):
    add_site(client, "One", "https://one.example/")
    add_site(client, "Two", "https://two.example/")
    names = [s["name"] for s in client.get("/sites").json()]
    assert names == ["One", "Two"]


def test_duplicate_url_rejected(client):
    add_site(client)
    resp = client.post("/sites", json={"name": "Again", "url": "https://example.com/"})
    assert resp.status_code == 409


def test_invalid_url_rejected(client):
    resp = client.post("/sites", json={"name": "Bad", "url": "not-a-url"})
    assert resp.status_code == 422


def test_empty_name_rejected(client):
    resp = client.post("/sites", json={"name": "", "url": "https://example.com/"})
    assert resp.status_code == 422


def test_missing_site_returns_404(client):
    assert client.get("/sites/999").status_code == 404
    assert client.delete("/sites/999").status_code == 404
    assert client.get("/sites/999/checks").status_code == 404


def test_delete_site_removes_it_and_its_checks(client, fake_checks):
    site = add_site(client)
    client.post("/checks/run")
    assert client.delete(f"/sites/{site['id']}").status_code == 204
    assert client.get(f"/sites/{site['id']}").status_code == 404
    assert client.get("/status").json() == []


# ---------- checks and status ----------

def test_run_checks_counts_up_and_down(client, fake_checks):
    add_site(client, "Up", "https://up.example/")
    add_site(client, "Down", "https://down.example/")
    fake_checks["https://down.example/"] = DOWN

    resp = client.post("/checks/run")
    assert resp.status_code == 200
    assert resp.json() == {"checked": 2, "up": 1, "down": 1}


def test_status_before_any_check(client):
    add_site(client)
    status = client.get("/status").json()
    assert status[0]["is_up"] is None
    assert status[0]["last_checked"] is None


def test_status_shows_latest_result(client, fake_checks):
    add_site(client)
    client.post("/checks/run")                       # up
    fake_checks["https://example.com/"] = DOWN
    client.post("/checks/run")                       # then down

    status = client.get("/status").json()[0]
    assert status["is_up"] is False
    assert status["status_code"] is None
    assert status["last_checked"] is not None


def test_site_checks_newest_first_with_limit(client, fake_checks):
    site = add_site(client)
    client.post("/checks/run")                       # up
    fake_checks["https://example.com/"] = DOWN
    client.post("/checks/run")                       # down

    checks = client.get(f"/sites/{site['id']}/checks").json()
    assert [c["is_up"] for c in checks] == [False, True]

    limited = client.get(f"/sites/{site['id']}/checks?limit=1").json()
    assert len(limited) == 1
    assert limited[0]["is_up"] is False


def test_checks_limit_validated(client):
    site = add_site(client)
    assert client.get(f"/sites/{site['id']}/checks?limit=0").status_code == 422
    assert client.get(f"/sites/{site['id']}/checks?limit=501").status_code == 422


# ---------- metrics ----------

def test_metrics_include_site_gauges(client, fake_checks):
    add_site(client, "Up", "https://up.example/")
    add_site(client, "Down", "https://down.example/")
    fake_checks["https://down.example/"] = DOWN
    client.post("/checks/run")

    body = client.get("/metrics").text
    assert 'site_up{site="Up"} 1.0' in body
    assert 'site_up{site="Down"} 0.0' in body
    assert 'site_response_ms{site="Up"} 42.0' in body
    assert "http_requests_total" in body


def test_metrics_drop_deleted_sites(client, fake_checks):
    site = add_site(client, "Gone", "https://gone.example/")
    client.post("/checks/run")
    client.delete(f"/sites/{site['id']}")

    body = client.get("/metrics").text
    assert 'site="Gone"' not in body
