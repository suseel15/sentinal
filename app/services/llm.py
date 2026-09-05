"""Minimal NVIDIA NIM-compatible LLM client.
Calls https://integrate.api.nvidia.com/v1/chat/completions when NVIDIA_API_KEY is set.
Falls back to a deterministic template-only path when the key is missing or the call fails.
Never invents facts; the LLM is only used to summarize structured evidence already collected.

Configuration (any of these work, in priority order):
  1. Real environment variable:  set NVIDIA_API_KEY=nvapi-...
  2. .env file at repo root:     NVIDIA_API_KEY=nvapi-...
  3. Leave blank → template fallback (A5 + A7 narrative_source = "TEMPLATE")
"""
import json
import logging
import os
from pathlib import Path
from typing import Any

import urllib.error
import urllib.request

log = logging.getLogger(__name__)


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader — avoids adding python-dotenv as a dependency."""
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        log.exception("failed to load .env from %s", path)


# Repo-root .env (sentinel/.env) is loaded automatically if it exists.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_load_dotenv(_REPO_ROOT / ".env")

NVIDIA_URL = os.environ.get("NVIDIA_NIM_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")


def available() -> bool:
    return bool(NVIDIA_API_KEY)


def chat(system: str, user: str, temperature: float = 0.2, max_tokens: int = 600,
         timeout: float = 25.0) -> dict | None:
    """Returns parsed JSON dict from NVIDIA NIM or None if unavailable / failed."""
    if not NVIDIA_API_KEY:
        return None
    payload = {
        "model": NVIDIA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": False,
    }
    try:
        req = urllib.request.Request(
            NVIDIA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
        obj = json.loads(raw)
        choice = (obj.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        return {
            "model": obj.get("model", NVIDIA_MODEL),
            "content": content.strip(),
            "finish_reason": choice.get("finish_reason"),
            "raw": obj,
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
        log.warning("NVIDIA LLM call failed: %s", e)
        return None
    except Exception as e:
        log.exception("NVIDIA LLM unexpected error: %s", e)
        return None