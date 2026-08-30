import os
import pytest
import requests


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.getenv("POKEDEX_URL", "http://127.0.0.1:5003")


@pytest.fixture(scope="session")
def live_url(base_url: str) -> str:
    """Base URL of an already-running server, or skip the test."""
    try:
        if requests.get(base_url + "/", timeout=5).status_code != 200:
            pytest.skip(f"no app responding at {base_url}")
    except requests.RequestException:
        pytest.skip(f"no app at {base_url} - start it with `make run`")
    return base_url
