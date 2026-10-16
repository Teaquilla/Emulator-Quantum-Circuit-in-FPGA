"""Runtime configuration, read from environment variables.

Model IDs are deliberately NOT hard-coded: take them from the Token Factory
catalog (run `python -m agent.list_models`) and export them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"


def load_dotenv(paths=None) -> list[str]:
    """Minimal .env loader (no dependency). Reads KEY=VALUE lines from the first of
    ./.env and <repo root>/.env that exist; real environment variables always win.
    Returns the names it set (never the values)."""
    candidates = paths or [Path.cwd() / ".env", Path(__file__).resolve().parents[1] / ".env"]
    loaded: list[str] = []
    for path in candidates:
        path = Path(path)
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip().removeprefix("export ").strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            if key and key not in os.environ:
                os.environ[key] = val
                loaded.append(key)
        break                                  # first .env found wins
    return loaded


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    planner_model: str          # reasoning model that proposes circuits
    fast_model: str             # cheap model for explanations
    backend: str = "ref-fixed"  # see backends.py
    max_repairs: int = 3        # retries after a rejected / mismatching circuit
    max_rounds: int = 8         # hard cap on LLM round trips per request
    tolerance: float = 0.02     # max |p_measured - p_expected| to count as a pass

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        required = ("NEBIUS_API_KEY", "NEBIUS_PLANNER_MODEL", "NEBIUS_FAST_MODEL")
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise RuntimeError("Missing environment variables: " + ", ".join(missing))
        return cls(
            api_key=os.environ["NEBIUS_API_KEY"],
            base_url=os.environ.get("NEBIUS_BASE_URL", DEFAULT_BASE_URL),
            planner_model=os.environ["NEBIUS_PLANNER_MODEL"],
            fast_model=os.environ["NEBIUS_FAST_MODEL"],
            backend=os.environ.get("AGENT_BACKEND", "ref-fixed"),
        )
