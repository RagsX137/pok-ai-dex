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
