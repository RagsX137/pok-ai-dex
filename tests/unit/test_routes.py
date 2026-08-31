import pytest


@pytest.fixture
def client():
    from pokedex.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_all_routes_are_registered(client):
    rules = {r.rule for r in client.application.url_map.iter_rules()}
    for expected in [
        "/", "/dashboard", "/readme",
        "/frontend/<path:filename>", "/images/<filename>",
        "/api/coveo-token", "/api/coveo-proxy",
        "/api/rga", "/api/rga-coveo", "/api/ask",
        "/api/set-model", "/api/models",
    ]:
        assert expected in rules, f"route {expected} disappeared"


def test_dashboard_renders_with_org_injected(client, monkeypatch):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert b"{{ COVEO_ORGANIZATION_ID }}" not in r.data


def test_coveo_proxy_rejects_paths_outside_search(client):
    r = client.post("/api/coveo-proxy",
                    json={"path": "/rest/organizations/x/apikeys", "body": {}})
    assert r.status_code == 400
