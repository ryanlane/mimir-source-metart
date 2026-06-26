"""Met Museum Collection API HTTP helpers.

All network I/O is synchronous (requests library); callers wrap with
asyncio.to_thread so the FastAPI event loop is never blocked.

API docs: https://metmuseum.github.io/
Rate limit: no hard limit stated — use small delays to be respectful.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, List, Optional

import requests

from .mimir_utils import http_session

logger = logging.getLogger("mimir.channels.metart.fetcher")

_API_BASE = "https://collectionapi.metmuseum.org/public/collection/v1"
_USER_AGENT = "MimirMetArt/1.0 (https://github.com/ryanlane/mimir-source-metart)"
_DETAIL_DELAY = 0.05   # 50ms between object detail fetches
_MAX_ATTEMPTS = 400    # hard cap on detail fetch attempts per gallery build


def _session() -> requests.Session:
    return http_session(_USER_AGENT)


def fetch_departments() -> List[Dict[str, Any]]:
    """Return [{departmentId, displayName}, ...] from the Met API."""
    try:
        resp = requests.get(
            f"{_API_BASE}/departments",
            headers={"User-Agent": _USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("departments", [])
    except Exception as exc:
        logger.warning("[MetArt] Department list fetch failed: %s", exc)
        return []


def _build_objects_params(gallery: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a gallery config dict into /objects query params."""
    params: Dict[str, Any] = {"hasImages": "true"}
    if gallery.get("is_public_domain", True):
        params["isPublicDomain"] = "true"
    if gallery.get("type") == "highlights":
        params["isHighlight"] = "true"
    if gallery.get("department_id"):
        params["departmentIds"] = str(gallery["department_id"])
    if gallery.get("date_begin"):
        params["dateBegin"] = str(gallery["date_begin"])
    if gallery.get("date_end"):
        params["dateEnd"] = str(gallery["date_end"])
    if gallery.get("medium", "").strip():
        params["medium"] = gallery["medium"].strip()
    return params


def fetch_object_ids(gallery: Dict[str, Any]) -> List[int]:
    """
    Return a list of Met object IDs matching the gallery config.
    Uses /search for keyword galleries, /objects for everything else.
    """
    gtype = gallery.get("type", "highlights")
    q = (gallery.get("q") or "").strip()

    try:
        if gtype == "search" and q:
            params: Dict[str, Any] = {
                "q": q,
                "hasImages": "true",
            }
            if gallery.get("is_public_domain", True):
                params["isPublicDomain"] = "true"
            if gallery.get("department_id"):
                params["departmentId"] = str(gallery["department_id"])
            if gallery.get("date_begin"):
                params["dateBegin"] = str(gallery["date_begin"])
            if gallery.get("date_end"):
                params["dateEnd"] = str(gallery["date_end"])
            if gallery.get("medium", "").strip():
                params["medium"] = gallery["medium"].strip()
            resp = requests.get(
                f"{_API_BASE}/search",
                params=params,
                headers={"User-Agent": _USER_AGENT},
                timeout=20,
            )
        else:
            params = _build_objects_params(gallery)
            resp = requests.get(
                f"{_API_BASE}/objects",
                params=params,
                headers={"User-Agent": _USER_AGENT},
                timeout=20,
            )
        resp.raise_for_status()
        body = resp.json()
        ids = body.get("objectIDs") or []
        logger.info("[MetArt] %d object IDs for gallery '%s'", len(ids), gallery.get("id"))
        return ids
    except Exception as exc:
        logger.warning("[MetArt] Object ID fetch failed for '%s': %s", gallery.get("id"), exc)
        return []


def fetch_object_detail(object_id: int, sess: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
    """Fetch a single object's details. Returns None if no primary image."""
    try:
        r = (sess or requests).get(
            f"{_API_BASE}/objects/{object_id}",
            headers={"User-Agent": _USER_AGENT},
            timeout=15,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        primary = data.get("primaryImage", "")
        if not primary:
            return None
        return {
            "object_id": object_id,
            "title": data.get("title", ""),
            "artist": data.get("artistDisplayName", ""),
            "date": data.get("objectDate", ""),
            "medium": data.get("medium", ""),
            "department": data.get("department", ""),
            "culture": data.get("culture", ""),
            "primary_image": primary,
            "small_image": data.get("primaryImageSmall", "") or primary,
            "object_url": data.get("objectURL", ""),
        }
    except Exception as exc:
        logger.debug("[MetArt] Detail fetch failed for %d: %s", object_id, exc)
        return None


def fetch_gallery_artworks(
    gallery: Dict[str, Any],
    max_count: int = 200,
) -> List[Dict[str, Any]]:
    """
    Build a pre-cached artwork list for a gallery.

    Strategy:
      1. Fetch all matching object IDs (single API call)
      2. Randomly sample up to 2 * max_count IDs (oversampling for rejects)
      3. Fetch each object's detail to get the image URL; skip objects with no image
      4. Stop once we have max_count valid artworks or exhaust attempts

    Rate-limited with small inter-request delays.
    """
    all_ids = fetch_object_ids(gallery)
    if not all_ids:
        return []

    sample_size = min(max_count * 2, _MAX_ATTEMPTS, len(all_ids))
    gtype = gallery.get("type", "highlights")
    if gtype == "search":
        # Search results may be relevance-ranked; keep the API's order so the
        # most representative items are fetched first rather than a random slice.
        sampled = all_ids[:sample_size]
    else:
        sampled = random.sample(all_ids, sample_size)

    sess = _session()
    artworks: List[Dict[str, Any]] = []

    for i, oid in enumerate(sampled):
        if len(artworks) >= max_count:
            break
        detail = fetch_object_detail(oid, sess)
        if detail:
            artworks.append(detail)
        # Slightly longer pause every 20 requests
        time.sleep(_DETAIL_DELAY * 3 if (i + 1) % 20 == 0 else _DETAIL_DELAY)

    logger.info(
        "[MetArt] Gallery '%s': %d artworks from %d attempts (pool of %d)",
        gallery.get("id"), len(artworks), min(len(sampled), len(artworks) * 2 + 10), len(all_ids),
    )
    return artworks


def fetch_artwork_image(image_url: str) -> Optional[bytes]:
    """Fetch image bytes from a Met Museum CDN URL."""
    if not image_url:
        return None
    try:
        resp = requests.get(
            image_url,
            headers={"User-Agent": _USER_AGENT},
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        ct = resp.headers.get("content-type", "")
        if not any(t in ct for t in ("image/jpeg", "image/png", "image/webp")):
            return None
        if len(resp.content) < 1000:
            return None
        return resp.content
    except Exception as exc:
        logger.warning("[MetArt] Image fetch failed url=%s…: %s", image_url[:80], exc)
        return None
