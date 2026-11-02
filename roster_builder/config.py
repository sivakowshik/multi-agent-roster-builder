"""Azure OpenAI settings from the environment. The key never has a default."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_MODEL",
)


class MissingConfig(SystemExit):
    pass


@dataclass(frozen=True)
class Settings:
    endpoint: str
    api_key: str
    deployment: str
    model: str
    api_version: str


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    missing = [name for name in REQUIRED if not os.environ.get(name, "").strip()]
    if missing:
        raise MissingConfig(
            "Missing "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in the Azure OpenAI resource. "
            + "For a run with no keys, use python offline_demo.py."
        )
    return Settings(
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"].strip().rstrip("/"),
        api_key=os.environ["AZURE_OPENAI_API_KEY"].strip(),
        deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"].strip(),
        model=os.environ["AZURE_OPENAI_MODEL"].strip(),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21").strip(),
    )
