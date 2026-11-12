"""Disk cache + polite HTTP helpers shared by all connectors.

Cache layout: ``<repo>/data/cache/<source_id>/<sha1-of-request>.json`` (or ``.bin`` for binary).
Set ``ROTACAST_OFFLINE=1`` to forbid network access (raises :class:`CacheMiss` on a miss).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = REPO_ROOT / "data" / "cache"
USER_AGENT = "Rotacast-hackathon/0.1 (crop rotation decision support)"


class CacheMiss(RuntimeError):
    """Raised in offline mode when a request is not in the disk cache."""


def is_offline() -> bool:
    return os.environ.get("ROTACAST_OFFLINE", "").strip().lower() in {"1", "true", "yes"}


def request_key(url: str, params: dict | None) -> str:
    """Stable sha1 of a request (url + sorted params)."""
    items = sorted((str(k), str(v)) for k, v in (params or {}).items())
    return hashlib.sha1(json.dumps([url, items]).encode("utf-8")).hexdigest()


def cache_path(source_id: str, url: str, params: dict | None = None, suffix: str = ".json") -> Path:
    return CACHE_DIR / source_id / f"{request_key(url, params)}{suffix}"


def _download(url: str, params: dict | None, timeout: float, retries: int) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True,
                              headers={"User-Agent": USER_AGENT}) as client:
                resp = client.get(url, params=params)
            if resp.status_code == 200:
                return resp
            last = RuntimeError(f"HTTP {resp.status_code} from {url}")
            if resp.status_code < 500 and resp.status_code != 429:
                break  # client error: retrying will not help
        except httpx.HTTPError as exc:
            last = exc
        if attempt < retries - 1:
            time.sleep(2.0 * (2 ** attempt))
    raise RuntimeError(f"GET failed after {retries} attempt(s): {last}")


def cached_get_json(source_id: str, url: str, params: dict | None = None, *,
                    timeout: float = 120, retries: int = 3) -> dict:
    """GET ``url`` as JSON with an on-disk cache. Raises CacheMiss when offline and uncached."""
    path = cache_path(source_id, url, params)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if is_offline():
        raise CacheMiss(f"{source_id}: not cached ({url} {params})")
    data: Any = _download(url, params, timeout, retries).json()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)
    return data


def cached_get_bytes(source_id: str, url: str, params: dict | None = None, *,
                     timeout: float = 120, retries: int = 3) -> bytes:
    """GET ``url`` as raw bytes with an on-disk cache (``.bin``). Same offline rules as JSON."""
    path = cache_path(source_id, url, params, suffix=".bin")
    if path.exists():
        return path.read_bytes()
    if is_offline():
        raise CacheMiss(f"{source_id}: not cached ({url} {params})")
    content = _download(url, params, timeout, retries).content
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(content)
    tmp.replace(path)
    return content
