"""Scryfall image URL helpers for MTG card thumbnails."""

import re
from urllib.parse import quote

# Real MTG set codes are 2–6 uppercase alphanumeric characters.
# Full set names stored as fallback (e.g. "The Lost Caverns of Ixalan Commander")
# will not match this pattern and should not be passed to the set/number endpoint.
_SET_CODE_RE = re.compile(r'^[A-Z0-9]{2,6}$')


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
    return (
        f"https://api.scryfall.com/cards/named"
        f"?exact={quote(name)}&format=image&version={version}"
    )
