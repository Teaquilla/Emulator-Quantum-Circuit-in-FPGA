"""Thin helpers around the OpenAI-compatible Token Factory API."""
from __future__ import annotations

import json
import re


def make_client(cfg):
    from openai import OpenAI      # imported lazily so offline tests need no dependency
    return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)


def extract_json(text: str | None) -> dict:
    """Pull one JSON object out of a model reply (handles <think> blocks and ``` fences)."""
    if not text:
        raise ValueError("empty reply")
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        a, b = t.find("{"), t.rfind("}")
        if a == -1 or b < a:
            raise ValueError("no JSON object found")
        t = t[a:b + 1]
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
