from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .mimir_utils import JsonCache, SettingsMixin


def make_gallery_id(label: str, existing_ids: set) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "gallery"
    if slug not in existing_ids:
        return slug
    ts = str(int(time.time()))[-6:]
    return f"{slug}_{ts}"


_DEFAULT_GALLERIES: List[Dict[str, Any]] = [
    {
        "id": "highlights",
        "label": "Met Highlights",
        "type": "highlights",
        "department_id": None,
        "q": "",
        "is_public_domain": True,
        "date_begin": None,
        "date_end": None,
        "medium": "",
    },
    {
        "id": "impressionism",
        "label": "Impressionism",
        "type": "search",
        "department_id": None,
        "q": "impressionism",
        "is_public_domain": True,
        "date_begin": None,
        "date_end": None,
        "medium": "",
    },
    {
        "id": "ancient_egypt",
        "label": "Ancient Egypt",
        "type": "department",
        "department_id": 10,
        "q": "",
        "is_public_domain": True,
        "date_begin": None,
        "date_end": None,
        "medium": "",
    },
]


OVERLAY_POSITIONS = (
    "top_left", "top_right", "bottom_left", "bottom_right", "top_center", "bottom_center",
)
# Same fields the paired "details" display already renders (see templates/details.html).
OVERLAY_FIELDS_AVAILABLE = ("title", "artist", "date", "medium", "department", "culture")
_DEFAULT_OVERLAY_FIELDS = ["title", "artist"]

# Multiplier applied on top of the existing image-proportional font sizing.
OVERLAY_FONT_SCALES = ("small", "medium", "large", "x_large")
# Font families, each backed by a real TTF confirmed present in the mimir-api
# image (Playwright's Chromium dependencies pull in DejaVu/Liberation/FreeFont
# regardless of any explicit `fonts-*` apt install) — see channel.py's
# _FONT_FAMILY_PATHS for the actual file paths per family.
OVERLAY_FONT_FAMILIES = ("sans", "serif", "mono")


@dataclass
class Settings(SettingsMixin):
    galleries: List[Dict[str, Any]] = field(default_factory=lambda: list(_DEFAULT_GALLERIES))
    fit_mode: str = "letterbox"
    image_quality: str = "primary"
    cache_max_per_gallery: int = 200
    refresh_interval_hours: int = 168
    # Bake artwork details directly onto the rendered image (useful for
    # displays with no paired "details" screen).
    overlay_enabled: bool = False
    overlay_position: str = "bottom_left"
    overlay_fields: List[str] = field(default_factory=lambda: list(_DEFAULT_OVERLAY_FIELDS))
    overlay_font_scale: str = "medium"
    overlay_font_family: str = "sans"
    # Attach the same details as an X-Artwork-Metadata response header on
    # /request-image, so callers building the MQTT payload (or any other
    # integration) can read them without parsing the image.
    include_metadata_in_response: bool = False

    def __post_init__(self) -> None:
        if self.overlay_position not in OVERLAY_POSITIONS:
            self.overlay_position = "bottom_left"
        self.overlay_fields = [f for f in self.overlay_fields if f in OVERLAY_FIELDS_AVAILABLE] or list(
            _DEFAULT_OVERLAY_FIELDS
        )
        if self.overlay_font_scale not in OVERLAY_FONT_SCALES:
            self.overlay_font_scale = "medium"
        if self.overlay_font_family not in OVERLAY_FONT_FAMILIES:
            self.overlay_font_family = "sans"


class ArtworkCache(JsonCache):
    """Persists artwork metadata per gallery in a JSON file."""

    def _empty_state(self) -> Dict[str, Any]:
        return {"galleries": {}}

    def get_artworks(self, gallery_id: str) -> List[Dict[str, Any]]:
        return self._data.get("galleries", {}).get(gallery_id, {}).get("artworks", [])

    def get_artworks_combined(self, gallery_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if gallery_id:
            return self.get_artworks(gallery_id)
        combined = []
        for entry in self._data.get("galleries", {}).values():
            combined.extend(entry.get("artworks", []))
        return combined

    def needs_refresh(self, gallery_id: str, interval_hours: int) -> bool:
        entry = self._data.get("galleries", {}).get(gallery_id, {})
        return time.time() - entry.get("fetched_at", 0) > interval_hours * 3600

    def update(self, gallery_id: str, artworks: List[Dict[str, Any]]) -> None:
        self._data.setdefault("galleries", {})[gallery_id] = {
            "artworks": artworks,
            "count": len(artworks),
            "fetched_at": time.time(),
        }
        self._save()

    def remove_gallery(self, gallery_id: str) -> None:
        self._data.get("galleries", {}).pop(gallery_id, None)
        self._save()

    def mark_stale(self, gallery_id: Optional[str] = None) -> None:
        targets = [gallery_id] if gallery_id else list(self._data.get("galleries", {}).keys())
        for gid in targets:
            if gid in self._data.get("galleries", {}):
                self._data["galleries"][gid]["fetched_at"] = 0
        self._save()

    def stats(self) -> Dict[str, Dict[str, Any]]:
        return {
            gid: {"count": e.get("count", 0), "fetched_at": e.get("fetched_at")}
            for gid, e in self._data.get("galleries", {}).items()
        }
