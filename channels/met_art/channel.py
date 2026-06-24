"""Met Museum Art channel for Mimir Platform.

Serves artwork images from The Metropolitan Museum of Art's open collection
(collectionapi.metmuseum.org). No API key required — the Met's Collection API
is free and public.

Each configured gallery (highlights, department, or keyword search) is a
sub-channel. Users can create multiple galleries with different filters.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import random
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .models import ArtworkCache, Settings, make_gallery_id
from . import fetcher as _fetcher

_PLUGIN_DIR = Path(__file__).parent
logger = logging.getLogger("mimir.channels.metart")

try:
    from PIL import Image as _PilImage
    _PIL = True
except ImportError:
    _PIL = False
    logger.warning("[MetArt] Pillow not installed — image resizing disabled")

try:
    import base64 as _base64
    import requests as _req
except ImportError:
    _req = None  # type: ignore[assignment]


class MetArtChannel:
    def __init__(self, channel_dir: str):
        self.channel_dir = Path(channel_dir)
        self.data_dir = self.channel_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        plugin_json = self.channel_dir / "plugin.json"
        self._meta: Dict[str, Any] = {}
        if plugin_json.exists():
            try:
                self._meta = json.loads(plugin_json.read_text())
            except Exception:
                pass

        self.settings = self._load_settings()
        self.cache = ArtworkCache(self.data_dir / "artworks_cache.json")
        self.last_error: Optional[str] = None
        self._recently_shown: Dict[str, deque] = {}
        self._refreshing: set = set()  # gallery IDs currently being refreshed
        self._last_shown: Dict[str, Dict] = {}  # gallery_id → last artwork shown (for details sync)
        self._jinja = self._make_jinja()

        logger.info("[MetArt] Initialized at %s", self.channel_dir)

    def _make_jinja(self):
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
            tpl_dir = _PLUGIN_DIR / "templates"
            tpl_dir.mkdir(exist_ok=True)
            return Environment(
                loader=FileSystemLoader(str(tpl_dir)),
                autoescape=select_autoescape(["html"]),
            )
        except ImportError:
            logger.warning("[MetArt] jinja2 not installed — details variant unavailable")
            return None

    @property
    def id(self) -> str:
        return self._meta.get("id", "com.metmuseum.art")

    # ------------------------------------------------------------------
    # Settings

    def _settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    def _load_settings(self) -> Settings:
        p = self._settings_path()
        if p.exists():
            try:
                return Settings.from_dict(json.loads(p.read_text()))
            except Exception as exc:
                logger.warning("[MetArt] Settings load failed: %s", exc)
        return Settings()

    def _save_settings(self) -> None:
        self._settings_path().write_text(json.dumps(self.settings.to_dict(), indent=2))

    # ------------------------------------------------------------------
    # Artwork selection

    def _pick_artwork(self, artworks: List[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
        if not artworks:
            return None
        window = min(50, max(1, len(artworks) // 2))
        recent = self._recently_shown.setdefault(key, deque(maxlen=window))
        recent_ids = set(recent)
        candidates = [a for a in artworks if a["object_id"] not in recent_ids]
        if not candidates:
            recent.clear()
            candidates = artworks
        chosen = random.choice(candidates)
        recent.append(chosen["object_id"])
        return chosen

    # ------------------------------------------------------------------
    # Image resizing

    def _resize(self, img_bytes: bytes, target: tuple, fit_mode: str) -> bytes:
        if not _PIL or not target:
            return img_bytes
        try:
            img = _PilImage.open(io.BytesIO(img_bytes)).convert("RGB")
            tw, th = target
            iw, ih = img.size

            if fit_mode == "crop":
                scale = max(tw / iw, th / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                img = img.resize((nw, nh), _PilImage.LANCZOS)
                left = (nw - tw) // 2
                top = (nh - th) // 2
                img = img.crop((left, top, left + tw, top + th))
            elif fit_mode == "stretch":
                img = img.resize((tw, th), _PilImage.LANCZOS)
            else:  # letterbox
                scale = min(tw / iw, th / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                resized = img.resize((nw, nh), _PilImage.LANCZOS)
                canvas = _PilImage.new("RGB", (tw, th), (0, 0, 0))
                canvas.paste(resized, ((tw - nw) // 2, (th - nh) // 2))
                img = canvas

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92, optimize=True)
            return buf.getvalue()
        except Exception as exc:
            logger.warning("[MetArt] Resize failed: %s", exc)
            return img_bytes

    # ------------------------------------------------------------------
    # Cache management

    async def _refresh_gallery(self, gallery: Dict[str, Any]) -> None:
        """Fetch and persist artworks for one gallery. No-ops if already in progress."""
        gid = gallery["id"]
        if gid in self._refreshing:
            return
        self._refreshing.add(gid)
        logger.info("[MetArt] Refreshing cache for gallery '%s'", gid)
        try:
            artworks = await asyncio.to_thread(
                _fetcher.fetch_gallery_artworks,
                gallery,
                self.settings.cache_max_per_gallery,
            )
            self.cache.update(gid, artworks)
            self.last_error = None
        except Exception as exc:
            logger.error("[MetArt] Cache refresh failed for '%s': %s", gid, exc)
            self.last_error = str(exc)
        finally:
            self._refreshing.discard(gid)

    async def _ensure_cache(self, gallery_id: Optional[str] = None) -> None:
        """Ensure galleries have cached artworks.

        If a gallery is stale but already has artworks, the refresh runs in the
        background so request_image is never blocked by a slow Met API crawl.
        Only blocks when the gallery cache is completely empty (initial fill).
        """
        galleries = (
            [g for g in self.settings.galleries if g["id"] == gallery_id]
            if gallery_id
            else self.settings.galleries
        )
        for gallery in galleries:
            gid = gallery["id"]
            if not self.cache.needs_refresh(gid, self.settings.refresh_interval_hours):
                continue
            if gid in self._refreshing:
                continue
            if self.cache.get_artworks(gid):
                # Stale but non-empty: serve existing artworks, refresh in background
                asyncio.create_task(self._refresh_gallery(gallery))
            else:
                # Empty: must block until we have something to serve
                await self._refresh_gallery(gallery)

    # ------------------------------------------------------------------
    # Mimir channel protocol

    def get_manifest(self) -> Dict[str, Any]:
        stats = self.cache.stats()
        total = sum(v["count"] for v in stats.values())
        return {
            "id": self.id,
            "name": self._meta.get("name", "Met Museum Art"),
            "version": self._meta.get("version", "1.0.0"),
            "description": self._meta.get("description", ""),
            "icon": self._meta.get("icon", "landmark"),
            "capabilities": {
                "supports_upload": False,
                "supports_subchannels": True,
                "content_variants": [
                    {"id": "image",   "label": "Artwork Image"},
                    {"id": "details", "label": "Artwork Details"},
                ],
            },
            "ui": {
                "components": {"manager": f"/api/channels/{self.id}/ui/manage.esm.js"},
                "elements": {"manager": "x-met-art-manager"},
            },
            "healthy": self.last_error is None,
            "gallery_count": len(self.settings.galleries),
            "total_artworks_cached": total,
        }

    def supports_subchannels(self) -> bool:
        return True

    def get_subchannel_config(self) -> Dict[str, Any]:
        return {
            "label": "Galleries",
            "singular": "Gallery",
            "description": "Each gallery is a curated pool of artworks (highlights, department, or search)",
            "can_create": False,
            "can_delete": False,
            "can_update": False,
        }

    def get_subchannels(self) -> List[Dict[str, Any]]:
        stats = self.cache.stats()
        return [
            {
                "id": g["id"],
                "name": g["label"],
                "image_count": stats.get(g["id"], {}).get("count", 0),
                "type": "subchannel",
                "gallery_type": g.get("type", "highlights"),
            }
            for g in self.settings.galleries
        ]

    def get_subchannel(self, subchannel_id: str) -> Optional[Dict[str, Any]]:
        for sc in self.get_subchannels():
            if sc["id"] == subchannel_id:
                return sc
        return None

    # ------------------------------------------------------------------
    # Details variant helpers

    def _thumb_b64(self, artwork: Dict) -> Optional[str]:
        if _req is None:
            return None
        url = artwork.get("small_image") or artwork.get("primary_image")
        if not url:
            return None
        try:
            resp = _req.get(url, timeout=8)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            return f"data:{ct};base64,{_base64.b64encode(resp.content).decode()}"
        except Exception as exc:
            logger.debug("[MetArt] thumb fetch failed: %s", exc)
            return None

    async def _render_details(self, artwork: Dict, width: int, height: int) -> Optional[bytes]:
        if self._jinja is None:
            return None
        try:
            from app.services.html_renderer import html_renderer_service
        except ImportError:
            return None
        if not html_renderer_service.available:
            return None

        aspect = width / height if height else 1.0
        if aspect >= 1.2:
            layout = "landscape"
        elif aspect <= 0.85:
            layout = "portrait"
        else:
            layout = "square"

        thumb = await asyncio.to_thread(self._thumb_b64, artwork)
        template = self._jinja.get_template("details.html")
        html = template.render(
            layout=layout,
            width=width,
            height=height,
            title=artwork.get("title", "Unknown"),
            artist=artwork.get("artist", ""),
            date=artwork.get("date", ""),
            medium=artwork.get("medium", ""),
            department=artwork.get("department", ""),
            culture=artwork.get("culture", ""),
            object_url=artwork.get("object_url", ""),
            thumb=thumb,
        )
        return await html_renderer_service.render(html, width, height)

    # ------------------------------------------------------------------
    # Image request

    async def request_image(self, request_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = request_data or {}
        settings_block = data.get("settings") or {}
        gallery_id = (
            data.get("subchannel_id")
            or data.get("gallery_id")
            or settings_block.get("subChannelId")
        ) or None

        known_ids = {g["id"] for g in self.settings.galleries}
        if gallery_id and gallery_id not in known_ids:
            gallery_id = None

        content_variant = settings_block.get("content_variant") or "image"
        cache_key = gallery_id or "__all__"

        # Details variant: render text card for the last-shown artwork
        if content_variant == "details":
            resolution = settings_block.get("resolution") or data.get("resolution")
            width, height = 800, 480
            if resolution and len(resolution) == 2:
                try:
                    width, height = int(resolution[0]), int(resolution[1])
                except (TypeError, ValueError):
                    pass

            artwork = self._last_shown.get(cache_key)
            if not artwork:
                # Cold start: pick one so both displays can sync on next tick
                await self._ensure_cache(gallery_id)
                artworks = self.cache.get_artworks_combined(gallery_id)
                if not artworks:
                    return {"success": False, "error": "No artworks cached yet"}
                artwork = self._pick_artwork(artworks, cache_key)
                if artwork:
                    self._last_shown[cache_key] = artwork

            if not artwork:
                return {"success": False, "error": "No artwork available for details"}

            img_bytes = await self._render_details(artwork, width, height)
            if not img_bytes:
                return {"success": False, "error": "Details renderer unavailable (Playwright not running)"}

            self.last_error = None
            return {
                "success": True,
                "bytes": img_bytes,
                "content_type": "image/jpeg",
                "preferred_transport": "bytes",
                "title": artwork.get("title", ""),
                "artist": artwork.get("artist", ""),
                "gallery": gallery_id,
                "content_variant": "details",
            }

        # Image variant (default): pick artwork, render image, update _last_shown
        await self._ensure_cache(gallery_id)

        artworks = self.cache.get_artworks_combined(gallery_id)
        if not artworks:
            return {
                "success": False,
                "error": "No artworks cached yet — open the channel manager and click Refresh",
            }

        resolution = settings_block.get("resolution") or data.get("resolution")
        target_size: Optional[tuple] = None
        if resolution and len(resolution) == 2:
            try:
                target_size = (int(resolution[0]), int(resolution[1]))
            except (TypeError, ValueError):
                pass

        chosen = self._pick_artwork(artworks, cache_key)

        for _ in range(5):
            if not chosen:
                break
            img_url = (
                chosen["primary_image"]
                if self.settings.image_quality == "primary"
                else chosen.get("small_image") or chosen["primary_image"]
            )
            img_bytes = await asyncio.to_thread(_fetcher.fetch_artwork_image, img_url)
            if img_bytes:
                if target_size:
                    img_bytes = self._resize(img_bytes, target_size, self.settings.fit_mode)
                self._last_shown[cache_key] = chosen  # keep details in sync
                self.last_error = None
                return {
                    "success": True,
                    "bytes": img_bytes,
                    "content_type": "image/jpeg",
                    "preferred_transport": "bytes",
                    "title": chosen.get("title", ""),
                    "artist": chosen.get("artist", ""),
                    "date": chosen.get("date", ""),
                    "department": chosen.get("department", ""),
                    "object_id": chosen["object_id"],
                    "object_url": chosen.get("object_url", ""),
                    "gallery": gallery_id,
                }
            chosen = self._pick_artwork(artworks, cache_key)

        self.last_error = "Artwork image fetch failed after retries"
        return {"success": False, "error": self.last_error}

    # ------------------------------------------------------------------
    # Router

    def get_router(self) -> APIRouter:
        router = APIRouter()
        _ui_dir = _PLUGIN_DIR / "ui"

        @router.get("/ui/{filename:path}")
        async def serve_ui(filename: str):
            file_path = (_ui_dir / filename).resolve()
            try:
                file_path.relative_to(_ui_dir.resolve())
            except ValueError:
                raise HTTPException(403, "Forbidden")
            if not file_path.exists():
                raise HTTPException(404, f"Not found: {filename}")
            ctype = "application/javascript" if filename.endswith(".js") else "text/css"
            return Response(
                content=file_path.read_bytes(),
                media_type=ctype,
                headers={"Cache-Control": "no-cache"},
            )

        @router.get("/manifest")
        async def get_manifest_route():
            return JSONResponse(self.get_manifest())

        @router.get("/subchannels")
        async def list_subchannels():
            return JSONResponse(self.get_subchannels())

        @router.get("/settings")
        async def get_settings():
            return JSONResponse(self.settings.to_dict())

        @router.put("/settings")
        async def update_settings(request: Request):
            body = await request.json()
            allowed = {
                "fit_mode", "image_quality", "cache_max_per_gallery",
                "refresh_interval_hours", "galleries",
            }
            for k in allowed:
                if k in body:
                    setattr(self.settings, k, body[k])
            self._save_settings()
            return JSONResponse({"success": True, "settings": self.settings.to_dict()})

        @router.post("/galleries")
        async def create_gallery(request: Request):
            body = await request.json()
            label = (body.get("label") or "").strip()
            if not label:
                raise HTTPException(400, "label is required")

            gtype = body.get("type", "highlights")
            if gtype not in ("highlights", "department", "search"):
                raise HTTPException(400, f"Unknown gallery type: {gtype}")

            existing_ids = {g["id"] for g in self.settings.galleries}
            gid = make_gallery_id(label, existing_ids)

            gallery: Dict[str, Any] = {
                "id": gid,
                "label": label,
                "type": gtype,
                "department_id": body.get("department_id") or None,
                "department_name": (body.get("department_name") or "").strip() or None,
                "q": (body.get("q") or "").strip(),
                "is_public_domain": bool(body.get("is_public_domain", True)),
                "date_begin": body.get("date_begin") or None,
                "date_end": body.get("date_end") or None,
                "medium": (body.get("medium") or "").strip(),
            }

            self.settings.galleries.append(gallery)
            self._save_settings()

            asyncio.create_task(self._refresh_gallery(gallery))
            return JSONResponse({
                "success": True,
                "gallery": gallery,
                "settings": self.settings.to_dict(),
            })

        @router.put("/galleries/{gallery_id}")
        async def update_gallery(gallery_id: str, request: Request):
            gallery_index = next(
                (i for i, g in enumerate(self.settings.galleries) if g["id"] == gallery_id),
                None,
            )
            if gallery_index is None:
                raise HTTPException(404, f"Gallery '{gallery_id}' not found")

            body = await request.json()
            label = (body.get("label") or "").strip()
            if not label:
                raise HTTPException(400, "label is required")

            gtype = body.get("type", self.settings.galleries[gallery_index].get("type", "highlights"))
            if gtype not in ("highlights", "department", "search"):
                raise HTTPException(400, f"Unknown gallery type: {gtype}")

            updated: Dict[str, Any] = {
                "id": gallery_id,
                "label": label,
                "type": gtype,
                "department_id": body.get("department_id") or None,
                "department_name": (body.get("department_name") or "").strip() or None,
                "q": (body.get("q") or "").strip(),
                "is_public_domain": bool(body.get("is_public_domain", True)),
                "date_begin": body.get("date_begin") or None,
                "date_end": body.get("date_end") or None,
                "medium": (body.get("medium") or "").strip(),
            }

            self.settings.galleries[gallery_index] = updated
            self._save_settings()
            self.cache.mark_stale(gallery_id)
            asyncio.create_task(self._refresh_gallery(updated))
            return JSONResponse({
                "success": True,
                "gallery": updated,
                "settings": self.settings.to_dict(),
            })

        @router.delete("/galleries/{gallery_id}")
        async def delete_gallery(gallery_id: str):
            original = len(self.settings.galleries)
            self.settings.galleries = [
                g for g in self.settings.galleries if g["id"] != gallery_id
            ]
            if len(self.settings.galleries) == original:
                raise HTTPException(404, f"Gallery '{gallery_id}' not found")
            self._save_settings()
            self.cache.remove_gallery(gallery_id)
            self._recently_shown.pop(gallery_id, None)
            return JSONResponse({"success": True, "settings": self.settings.to_dict()})

        @router.get("/departments")
        async def list_departments():
            depts = await asyncio.to_thread(_fetcher.fetch_departments)
            return JSONResponse(depts)

        @router.get("/status")
        async def get_status():
            stats = self.cache.stats()
            return JSONResponse({
                "galleries": self.get_subchannels(),
                "cache_stats": stats,
                "last_error": self.last_error,
                "settings": self.settings.to_dict(),
            })

        @router.post("/refresh")
        async def refresh_cache(request: Request):
            body: Dict[str, Any] = {}
            try:
                body = await request.json()
            except Exception:
                pass
            gallery_id = body.get("gallery") or None
            self.cache.mark_stale(gallery_id)
            asyncio.create_task(self._ensure_cache(gallery_id))
            return JSONResponse({
                "success": True,
                "message": f"Refresh started for {gallery_id or 'all galleries'}",
            })

        @router.post("/count-estimate")
        async def count_estimate(request: Request):
            body: Dict[str, Any] = {}
            try:
                body = await request.json()
            except Exception:
                pass
            gtype = body.get("type", "highlights")
            if gtype not in ("highlights", "department", "search"):
                raise HTTPException(400, f"Unknown gallery type: {gtype}")
            gallery_config: Dict[str, Any] = {
                "id": "__preview__",
                "type": gtype,
                "q": (body.get("q") or "").strip(),
                "department_id": body.get("department_id") or None,
                "is_public_domain": bool(body.get("is_public_domain", True)),
                "date_begin": body.get("date_begin") or None,
                "date_end": body.get("date_end") or None,
                "medium": (body.get("medium") or "").strip(),
            }
            try:
                ids = await asyncio.to_thread(_fetcher.fetch_object_ids, gallery_config)
                return JSONResponse({"count": len(ids)})
            except Exception as exc:
                logger.warning("[MetArt] count_estimate failed: %s", exc)
                raise HTTPException(500, "Failed to estimate count")

        @router.post("/request-image")
        async def request_image_binary(request: Request):
            body: Dict[str, Any] = {}
            try:
                body = await request.json()
            except Exception:
                pass
            result = await self.request_image(body)
            if not result.get("success"):
                raise HTTPException(500, result.get("error", "request_image failed"))
            img_bytes = result.get("bytes")
            if not img_bytes:
                raise HTTPException(500, "No image bytes produced")
            fingerprint = hashlib.sha256(img_bytes).hexdigest()[:32]
            return Response(
                content=img_bytes,
                media_type=result.get("content_type", "image/jpeg"),
                headers={
                    "X-Content-Fingerprint": fingerprint,
                    "Cache-Control": "no-store",
                },
            )

        logger.info("[MetArt] Router registered, %d galleries configured", len(self.settings.galleries))
        return router


ChannelClass = MetArtChannel
