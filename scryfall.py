"""Scryfall image URL helpers and set name resolution for MTG cards."""

import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote

import requests

# Real MTG set codes are 2–6 uppercase alphanumeric characters.
# Full set names stored as fallback (e.g. "The Lost Caverns of Ixalan Commander")
# will not match this pattern and should not be passed to the set/number endpoint.
_SET_CODE_RE = re.compile(r'^[A-Z0-9]{2,6}$')

# --------------------------------------------------------------------------
# Set name → code lookup (lazy-loaded, thread-safe)
# --------------------------------------------------------------------------
_set_name_to_code: dict[str, str] | None = None
_set_lock = threading.Lock()

# Cache lives next to this file; refreshed weekly
_CACHE_DIR = Path(__file__).parent / ".cache"
_CACHE_FILE = _CACHE_DIR / "scryfall_sets.json"
_CACHE_MAX_AGE = 7 * 24 * 3600  # 1 week


def _load_set_map() -> dict[str, str]:
    """Load set name → code map from cache or Scryfall API."""
    # Try cache first
    if _CACHE_FILE.exists():
        try:
            age = time.time() - _CACHE_FILE.stat().st_mtime
            if age < _CACHE_MAX_AGE:
                with open(_CACHE_FILE) as f:
                    cached = json.load(f)
                print(f"[scryfall] Loaded {len(cached)} sets from cache")
                return cached
        except Exception:
            pass  # Corrupt cache, refetch

    # Fetch from API
    mapping: dict[str, str] = {}
    try:
        resp = requests.get(
            "https://api.scryfall.com/sets",
            headers={"User-Agent": "MTGCardScraper/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        for s in resp.json().get("data", []):
            name = s.get("name", "").strip().lower()
            code = s.get("code", "").upper()
            if name and code:
                mapping[name] = code
        # Save to cache
        _CACHE_DIR.mkdir(exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(mapping, f)
        print(f"[scryfall] Fetched {len(mapping)} sets from API, cached to {_CACHE_FILE}")
    except Exception as e:
        print(f"[scryfall] Failed to load set list: {e}")
    return mapping


def get_set_code(full_name: str) -> str | None:
    """
    Resolve a full set name (e.g. "Commander 2016") to its Scryfall set code ("C16").
    Returns None if not found. Lazy-loads the set list on first call (cached to disk for 1 week).
    """
    global _set_name_to_code
    with _set_lock:
        if _set_name_to_code is None:
            _set_name_to_code = _load_set_map()
    return _set_name_to_code.get(full_name.strip().lower())


def _is_real_set_code(value: str) -> bool:
    return bool(_SET_CODE_RE.match(value))


def get_image_url(
    name: str,
    set_code: str | None = None,
    collector_number: str | None = None,
    version: str = "small",
) -> str:
    """
    Build a direct Scryfall image URL (302 redirect, no API call needed).

    Args:
        name: Card name (used as fallback when set/collector unknown)
        set_code: MTG set code (e.g. "2XM") or full set name — only real codes
                  are used for precise lookups; full names fall back to name search.
        collector_number: Collector number (e.g. "141")
        version: Image size — "small" (146x204), "normal" (488x680), "png" (745x1040)

    Returns:
        URL that redirects to the card image on Scryfall's CDN
    """
    if set_code and collector_number and _is_real_set_code(set_code):
        return (
            f"https://api.scryfall.com/cards/"
            f"{quote(set_code.lower())}/{quote(collector_number)}"
            f"?format=image&version={version}"
        )
    if set_code and _is_real_set_code(set_code):
        return (
            f"https://api.scryfall.com/cards/named"
            f"?exact={quote(name)}&set={quote(set_code.lower())}"
            f"&format=image&version={version}"
        )
    return (
        f"https://api.scryfall.com/cards/named"
        f"?exact={quote(name)}&format=image&version={version}"
    )
