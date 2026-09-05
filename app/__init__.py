"""SENTINEL package init.

Loads the project-root `.env` file once at startup so every module
reads the same configuration via os.environ.
"""
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
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


_load_dotenv(_REPO_ROOT / ".env")