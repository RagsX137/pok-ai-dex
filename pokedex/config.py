"""The single definition of where things live and how to reach them.

Every port, base URL, pipeline name and directory in this project is defined
here exactly once. Before this module they were copied across nine files.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]

# macOS Monterey+ reserves port 5000 for AirPlay Receiver.
DEFAULT_PORT = 5003


@dataclass(frozen=True)
class Settings:
    coveo_org: str
    coveo_token: str
    coveo_base: str
    coveo_pipeline: str
    coveo_rga_pipeline: str
    coveo_search_hub: str
    coveo_passage_hub: str
    ollama_base_url: str
    ollama_model: str
    port: int
    repo_root: Path
    frontend_dir: Path
    images_dir: Path


def load_settings() -> Settings:
    org = os.getenv("COVEO_ORGANIZATION_ID", "")
    pipeline = os.getenv("COVEO_PIPELINE", "default")
    return Settings(
        coveo_org=org,
        coveo_token=os.getenv("COVEO_ACCESS_TOKEN", ""),
        coveo_base=(
            f"https://{org}.org.coveo.com" if org else "https://platform.cloud.coveo.com"
        ),
        coveo_pipeline=pipeline,
        coveo_rga_pipeline=os.getenv("COVEO_RGA_PIPELINE", pipeline),
        coveo_search_hub=os.getenv("COVEO_SEARCH_HUB", "PokedexUI"),
        # The Passage Retrieval API (/rest/search/v3) rejects a searchHub that
        # disagrees with the one baked into the API key, with
        # "400 Conflicting searchHub value". /rest/search/v2 tolerates the same
        # mismatch, which is why this is a second setting rather than a fix to
        # coveo_search_hub: changing that one would re-label all search
        # analytics. Set COVEO_PASSAGE_SEARCH_HUB to whatever the key is bound
        # to — scripts/probe_passage_retrieval.py prints it.
        # Deliberately NOT falling back to COVEO_SEARCH_HUB: that is PokedexUI,
        # the value v3 rejects. An unset variable must not silently 400.
        coveo_passage_hub=os.getenv("COVEO_PASSAGE_SEARCH_HUB", "AdminConsole"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3"),
        port=int(os.getenv("POKEDEX_PORT", DEFAULT_PORT)),
        repo_root=REPO_ROOT,
        frontend_dir=REPO_ROOT / "frontend",
        images_dir=REPO_ROOT / "data" / "images",
    )


settings = load_settings()


def app_url() -> str:
    """Base URL of the running app, for harnesses and tests."""
    return os.getenv("POKEDEX_URL", f"http://127.0.0.1:{settings.port}")
