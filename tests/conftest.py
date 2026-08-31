import os
import pytest
import requests


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.getenv("POKEDEX_URL", "http://127.0.0.1:5003")


@pytest.fixture(scope="session")
def live_url(base_url: str) -> str:
    """Base URL of an already-running server.

    Fails (does not skip) when nothing answers. Every e2e test depends on
    this fixture, so a forgotten server — or an app so broken it cannot even
    bind its port — must make the suite fail loudly. A skip here would let
    `make test-e2e` report green while zero of its tests actually ran, which
    defeats its purpose as the reorg's safety net.
    """
    try:
        resp = requests.get(base_url + "/", timeout=5)
    except requests.RequestException as exc:
        pytest.fail(f"no app at {base_url} - start it with `make run` ({exc})")
    if resp.status_code != 200:
        pytest.fail(f"app at {base_url} returned {resp.status_code}, expected 200")
    return base_url
