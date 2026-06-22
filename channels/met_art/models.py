from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


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


@dataclass
class Settings:
    galleries: List[Dict[str, Any]] = field(default_factory=lambda: list(_DEFAULT_GALLERIES))
    fit_mode: str = "letterbox"
    image_quality: str = "primary"
    cache_max_per_gallery: int = 200
    refresh_interval_hours: int = 168

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


class ArtworkCache:
    """Persists artwork metadata per gallery in a JSON file."""

    def __init__(self, cache_path: Path):
        self._path = cache_path
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except Exception:
                pass
        return {"galleries": {}}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

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
