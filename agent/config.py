"""Runtime configuration, read from environment variables.

Model IDs are deliberately NOT hard-coded: take them from the Token Factory
catalog (run `python -m agent.list_models`) and export them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    planner_model: str          # reasoning model that proposes circuits
    fast_model: str             # cheap model for explanations
    backend: str = "sim-float"  # see backends.py
    max_repairs: int = 3        # retries after a rejected / mismatching circuit
    max_rounds: int = 8         # hard cap on LLM round trips per request
    tolerance: float = 0.02     # max |p_measured - p_expected| to count as a pass

    @classmethod
    def from_env(cls) -> "Config":
        required = ("NEBIUS_API_KEY", "NEBIUS_PLANNER_MODEL", "NEBIUS_FAST_MODEL")
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise RuntimeError("Missing environment variables: " + ", ".join(missing))
        return cls(
            api_key=os.environ["NEBIUS_API_KEY"],
            base_url=os.environ.get("NEBIUS_BASE_URL", DEFAULT_BASE_URL),
            planner_model=os.environ["NEBIUS_PLANNER_MODEL"],
            fast_model=os.environ["NEBIUS_FAST_MODEL"],
            backend=os.environ.get("AGENT_BACKEND", "sim-float"),
        )
