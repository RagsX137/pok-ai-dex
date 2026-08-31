from pathlib import Path


def test_coveo_base_uses_org_subdomain(monkeypatch):
    monkeypatch.setenv("COVEO_ORGANIZATION_ID", "myorg")
    from pokedex.config import load_settings
    s = load_settings()
    assert s.coveo_base == "https://myorg.org.coveo.com"


def test_coveo_base_falls_back_without_org(monkeypatch):
    monkeypatch.delenv("COVEO_ORGANIZATION_ID", raising=False)
    from pokedex.config import load_settings
    s = load_settings()
    assert s.coveo_base == "https://platform.cloud.coveo.com"


def test_rga_pipeline_falls_back_to_pipeline(monkeypatch):
    monkeypatch.delenv("COVEO_RGA_PIPELINE", raising=False)
    monkeypatch.setenv("COVEO_PIPELINE", "custom")
    from pokedex.config import load_settings
    assert load_settings().coveo_rga_pipeline == "custom"


def test_paths_resolve_to_real_directories():
    from pokedex.config import settings
    assert settings.frontend_dir.is_dir()
    assert settings.images_dir.is_dir()
    assert (settings.repo_root / "pyproject.toml").is_file()


def test_port_is_5003():
    from pokedex.config import settings
    assert settings.port == 5003
