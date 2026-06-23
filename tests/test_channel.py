"""Tests for channel.py — MetArtChannel business logic with mocked fetcher."""
import asyncio
import json
from unittest.mock import patch

import pytest

from channels.met_art.channel import MetArtChannel
from channels.met_art.models import ArtworkCache
from tests.conftest import make_artwork

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_IMAGE = b"\xff\xd8\xff\xe0" + b"X" * 2000  # > 1KB fake JPEG bytes


@pytest.fixture
def channel(tmp_path):
    return MetArtChannel(str(tmp_path))


@pytest.fixture
def channel_with_cache(tmp_path):
    ch = MetArtChannel(str(tmp_path))
    artworks = [make_artwork(i, f"Artwork {i}") for i in range(1, 11)]
    ch.cache.update("highlights", artworks)
    return ch


def _no_fetch(*args, **kwargs):
    """Stub used to assert fetch_gallery_artworks was never called."""
    raise AssertionError("fetch_gallery_artworks should not have been called")


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

class TestSettingsPersistence:
    def test_settings_saved_to_disk(self, channel, tmp_path):
        channel.settings.fit_mode = "crop"
        channel._save_settings()
        data = json.loads((tmp_path / "data" / "settings.json").read_text())
        assert data["fit_mode"] == "crop"

    def test_settings_loaded_on_init(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "settings.json").write_text(json.dumps({
            "galleries": [],
            "fit_mode": "stretch",
            "image_quality": "small",
            "cache_max_per_gallery": 50,
            "refresh_interval_hours": 24,
        }))
        ch = MetArtChannel(str(tmp_path))
        assert ch.settings.fit_mode == "stretch"
        assert ch.settings.image_quality == "small"
        assert ch.settings.cache_max_per_gallery == 50

    def test_handles_corrupt_settings_file(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "settings.json").write_text("{ invalid json }")
        ch = MetArtChannel(str(tmp_path))
        assert ch.settings.fit_mode == "letterbox"  # falls back to defaults


# ---------------------------------------------------------------------------
# _refresh_gallery
# ---------------------------------------------------------------------------

class TestRefreshGallery:
    async def test_fetches_and_updates_cache(self, channel):
        gallery = next(g for g in channel.settings.galleries if g["id"] == "highlights")
        artworks = [make_artwork(i) for i in range(3)]
        with patch("channels.met_art.fetcher.fetch_gallery_artworks", return_value=artworks):
            await channel._refresh_gallery(gallery)
        assert len(channel.cache.get_artworks("highlights")) == 3

    async def test_deduplicates_concurrent_refreshes(self, channel):
        """Two concurrent calls to _refresh_gallery for the same gallery must
        only trigger one fetch — the second sees the gallery in _refreshing and exits."""
        gallery = next(g for g in channel.settings.galleries if g["id"] == "highlights")
        fetch_count = 0

        def sync_fetch(gallery, max_count=200):
            nonlocal fetch_count
            fetch_count += 1
            return [make_artwork(1)]

        # asyncio.to_thread yields back to the event loop, giving the second
        # coroutine a chance to run and observe _refreshing before the first completes
        with patch("channels.met_art.fetcher.fetch_gallery_artworks", side_effect=sync_fetch):
            await asyncio.gather(
                channel._refresh_gallery(gallery),
                channel._refresh_gallery(gallery),
            )

        assert fetch_count == 1

    async def test_clears_refreshing_flag_on_success(self, channel):
        gallery = next(g for g in channel.settings.galleries if g["id"] == "highlights")
        with patch("channels.met_art.fetcher.fetch_gallery_artworks", return_value=[make_artwork(1)]):
            await channel._refresh_gallery(gallery)
        assert "highlights" not in channel._refreshing

    async def test_clears_refreshing_flag_on_error(self, channel):
        gallery = next(g for g in channel.settings.galleries if g["id"] == "highlights")
        with patch("channels.met_art.fetcher.fetch_gallery_artworks", side_effect=Exception("API down")):
            await channel._refresh_gallery(gallery)
        assert "highlights" not in channel._refreshing

    async def test_sets_last_error_on_fetch_failure(self, channel):
        gallery = next(g for g in channel.settings.galleries if g["id"] == "highlights")
        with patch("channels.met_art.fetcher.fetch_gallery_artworks", side_effect=Exception("net error")):
            await channel._refresh_gallery(gallery)
        assert channel.last_error is not None


# ---------------------------------------------------------------------------
# _ensure_cache
# ---------------------------------------------------------------------------

class TestEnsureCache:
    async def test_fetches_artworks_when_gallery_is_stale(self, channel):
        mock_artworks = [make_artwork(i) for i in range(5)]
        with patch("channels.met_art.fetcher.fetch_gallery_artworks", return_value=mock_artworks):
            await channel._ensure_cache("highlights")
        assert len(channel.cache.get_artworks("highlights")) == 5

    async def test_skips_fetch_when_cache_is_fresh(self, channel):
        channel.cache.update("highlights", [make_artwork(1)])
        with patch("channels.met_art.fetcher.fetch_gallery_artworks", side_effect=_no_fetch):
            await channel._ensure_cache("highlights")  # should not raise

    async def test_refetches_after_mark_stale(self, channel):
        channel.cache.update("impressionism", [make_artwork(1, "Old")])
        channel.cache.mark_stale("impressionism")

        new_artworks = [make_artwork(i, f"New {i}") for i in range(10, 16)]
        with patch("channels.met_art.fetcher.fetch_gallery_artworks", return_value=new_artworks):
            await channel._ensure_cache("impressionism")
            # stale+nonempty → background task; drain inside the patch context
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        artworks = channel.cache.get_artworks("impressionism")
        assert len(artworks) == 6
        assert all("New" in a["title"] for a in artworks)

    async def test_uses_current_gallery_config_not_stale_one(self, channel):
        """Core settings-update bug: ensure_cache must use the current in-memory gallery
        config when refreshing, not any previously cached version of the config."""
        idx = next(i for i, g in enumerate(channel.settings.galleries) if g["id"] == "impressionism")
        channel.settings.galleries[idx] = {
            "id": "impressionism",
            "label": "Monet Only",
            "type": "search",
            "q": "monet",
            "is_public_domain": True,
            "department_id": None,
            "department_name": None,
            "date_begin": None,
            "date_end": None,
            "medium": "",
        }
        channel.cache.mark_stale("impressionism")

        captured = {}

        def capture_fetch(gallery, max_count=200):
            captured.update(gallery)
            return [make_artwork(99)]

        with patch("channels.met_art.fetcher.fetch_gallery_artworks", side_effect=capture_fetch):
            await channel._ensure_cache("impressionism")

        assert captured.get("q") == "monet"
        assert captured.get("label") == "Monet Only"

    async def test_refreshes_all_galleries_when_no_id_given(self, channel):
        fetch_calls = []

        def record_fetch(gallery, max_count=200):
            fetch_calls.append(gallery["id"])
            return [make_artwork(1)]

        # None of the default galleries have cached data, so all need refresh
        with patch("channels.met_art.fetcher.fetch_gallery_artworks", side_effect=record_fetch):
            await channel._ensure_cache()

        assert set(fetch_calls) == {"highlights", "impressionism", "ancient_egypt"}


# ---------------------------------------------------------------------------
# request_image
# ---------------------------------------------------------------------------

class TestRequestImage:
    async def test_returns_error_when_no_artworks_cached(self, channel):
        with patch("channels.met_art.fetcher.fetch_gallery_artworks", return_value=[]):
            result = await channel.request_image({"subchannel_id": "highlights"})
        assert result["success"] is False
        assert "No artworks cached" in result["error"]

    async def test_returns_success_with_bytes_and_metadata(self, channel_with_cache):
        with patch("channels.met_art.fetcher.fetch_artwork_image", return_value=FAKE_IMAGE):
            result = await channel_with_cache.request_image({"subchannel_id": "highlights"})
        assert result["success"] is True
        assert result["bytes"] == FAKE_IMAGE
        assert result["content_type"] == "image/jpeg"
        assert "title" in result
        assert "artist" in result
        assert "object_id" in result
        assert "object_url" in result

    async def test_object_id_comes_from_cached_artworks(self, channel_with_cache):
        valid_ids = {a["object_id"] for a in channel_with_cache.cache.get_artworks("highlights")}
        with patch("channels.met_art.fetcher.fetch_artwork_image", return_value=FAKE_IMAGE):
            result = await channel_with_cache.request_image({"subchannel_id": "highlights"})
        assert result["object_id"] in valid_ids

    async def test_uses_updated_gallery_config_after_settings_change(self, channel):
        """After editing settings, request_image must NOT block waiting for the new
        cache build (avoids the scene_refresh_service TimeoutError seen in production).
        It serves existing artworks immediately and triggers a background refresh
        with the new gallery config."""
        old_artworks = [make_artwork(i, f"Old {i}") for i in range(1, 6)]
        channel.cache.update("highlights", old_artworks)

        idx = next(i for i, g in enumerate(channel.settings.galleries) if g["id"] == "highlights")
        channel.settings.galleries[idx] = {
            "id": "highlights",
            "label": "European Paintings",
            "type": "department",
            "department_id": 11,
            "department_name": "European Paintings",
            "q": "",
            "is_public_domain": True,
            "date_begin": None,
            "date_end": None,
            "medium": "",
        }
        channel._save_settings()
        channel.cache.mark_stale("highlights")

        new_artworks = [make_artwork(i, f"European {i}") for i in range(100, 106)]
        fetch_calls = []

        def capture_fetch(gallery, max_count=200):
            fetch_calls.append(dict(gallery))
            return new_artworks

        with patch("channels.met_art.fetcher.fetch_gallery_artworks", side_effect=capture_fetch), \
             patch("channels.met_art.fetcher.fetch_artwork_image", return_value=FAKE_IMAGE):
            # First request after settings change: returns immediately with old artworks
            result = await channel.request_image({"subchannel_id": "highlights"})
            assert result["success"] is True
            assert result["object_id"] in range(1, 6)  # old artworks served, no timeout

            # Drain background refresh tasks within the patch context
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        # Background fetch used the new gallery config
        assert len(fetch_calls) == 1
        assert fetch_calls[0]["type"] == "department"
        assert fetch_calls[0]["department_id"] == 11

        # New artworks are now in cache for subsequent requests
        assert all(a["object_id"] in range(100, 106) for a in channel.cache.get_artworks("highlights"))

    async def test_falls_back_to_all_galleries_for_unknown_subchannel(self, channel_with_cache):
        with patch("channels.met_art.fetcher.fetch_gallery_artworks", return_value=[]), \
             patch("channels.met_art.fetcher.fetch_artwork_image", return_value=FAKE_IMAGE):
            result = await channel_with_cache.request_image({"subchannel_id": "does_not_exist"})
        # highlights artworks are still in the combined pool
        assert result["success"] is True

    async def test_retries_on_image_fetch_failure(self, channel_with_cache):
        call_count = 0

        def flaky_fetch(url):
            nonlocal call_count
            call_count += 1
            return None if call_count < 3 else FAKE_IMAGE

        with patch("channels.met_art.fetcher.fetch_artwork_image", side_effect=flaky_fetch):
            result = await channel_with_cache.request_image({"subchannel_id": "highlights"})

        assert result["success"] is True
        assert call_count >= 3

    async def test_returns_error_after_exhausting_retries(self, tmp_path):
        ch = MetArtChannel(str(tmp_path))
        # Only 1 artwork in cache so retries can't pick a different one
        ch.cache.update("highlights", [make_artwork(1)])

        with patch("channels.met_art.fetcher.fetch_artwork_image", return_value=None):
            result = await ch.request_image({"subchannel_id": "highlights"})

        assert result["success"] is False
        assert "failed" in result["error"].lower()

    async def test_respects_subchannel_id_in_response(self, channel_with_cache):
        with patch("channels.met_art.fetcher.fetch_artwork_image", return_value=FAKE_IMAGE):
            result = await channel_with_cache.request_image({"subchannel_id": "highlights"})
        assert result["gallery"] == "highlights"

    async def test_uses_image_quality_setting(self, channel_with_cache):
        """When image_quality='small', the small_image URL should be fetched."""
        channel_with_cache.settings.image_quality = "small"
        fetched_urls = []

        def capture_url(url):
            fetched_urls.append(url)
            return FAKE_IMAGE

        with patch("channels.met_art.fetcher.fetch_artwork_image", side_effect=capture_url):
            result = await channel_with_cache.request_image({"subchannel_id": "highlights"})

        assert result["success"] is True
        # small_image URLs from make_artwork contain "_small"
        assert "_small" in fetched_urls[0]


# ---------------------------------------------------------------------------
# count_estimate (via request_image route's underlying logic)
# ---------------------------------------------------------------------------

class TestCountEstimate:
    async def test_returns_count_from_fetch_object_ids(self, channel):
        with patch("channels.met_art.fetcher.fetch_object_ids", return_value=list(range(42))):
            from fastapi.testclient import TestClient
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(channel.get_router(), prefix=f"/api/channels/{channel.id}")
            client = TestClient(app)
            resp = client.post(
                f"/api/channels/{channel.id}/count-estimate",
                json={"type": "search", "q": "monet", "is_public_domain": True},
            )
        assert resp.status_code == 200
        assert resp.json()["count"] == 42

    async def test_returns_zero_when_no_matches(self, channel):
        with patch("channels.met_art.fetcher.fetch_object_ids", return_value=[]):
            from fastapi.testclient import TestClient
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(channel.get_router(), prefix=f"/api/channels/{channel.id}")
            client = TestClient(app)
            resp = client.post(
                f"/api/channels/{channel.id}/count-estimate",
                json={"type": "highlights", "is_public_domain": True},
            )
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    async def test_rejects_unknown_gallery_type(self, channel):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(channel.get_router(), prefix=f"/api/channels/{channel.id}")
        client = TestClient(app)
        resp = client.post(
            f"/api/channels/{channel.id}/count-estimate",
            json={"type": "invalid_type"},
        )
        assert resp.status_code == 400

    async def test_passes_gallery_config_to_fetcher(self, channel):
        captured = {}

        def capture(gallery):
            captured.update(gallery)
            return list(range(10))

        with patch("channels.met_art.fetcher.fetch_object_ids", side_effect=capture):
            from fastapi.testclient import TestClient
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(channel.get_router(), prefix=f"/api/channels/{channel.id}")
            client = TestClient(app)
            client.post(
                f"/api/channels/{channel.id}/count-estimate",
                json={
                    "type": "search",
                    "q": "impressionism",
                    "is_public_domain": True,
                    "department_id": 11,
                    "date_begin": 1860,
                    "date_end": 1920,
                    "medium": "Oil on canvas",
                },
            )

        assert captured["type"] == "search"
        assert captured["q"] == "impressionism"
        assert captured["department_id"] == 11
        assert captured["date_begin"] == 1860
        assert captured["date_end"] == 1920
        assert captured["medium"] == "Oil on canvas"
        assert captured["is_public_domain"] is True


# ---------------------------------------------------------------------------
# _pick_artwork
# ---------------------------------------------------------------------------

class TestPickArtwork:
    def test_returns_none_for_empty_list(self, channel):
        assert channel._pick_artwork([], "key") is None

    def test_returns_artwork_from_list(self, channel):
        artworks = [make_artwork(i) for i in range(5)]
        result = channel._pick_artwork(artworks, "key")
        assert result in artworks

    def test_avoids_recently_shown_ids(self, channel):
        artworks = [make_artwork(i) for i in range(10)]
        seen = set()
        for _ in range(len(artworks)):
            chosen = channel._pick_artwork(artworks, "key")
            seen.add(chosen["object_id"])
        # With 10 artworks we should eventually see more than 1
        assert len(seen) > 1

    def test_resets_deque_when_all_shown(self, channel):
        artworks = [make_artwork(i) for i in range(3)]
        # Fill the recently_shown window beyond the list size
        for _ in range(20):
            channel._pick_artwork(artworks, "key")
        # After reset it should still return an artwork, not None
        result = channel._pick_artwork(artworks, "key")
        assert result is not None

    def test_separate_keys_have_independent_history(self, channel):
        artworks = [make_artwork(i) for i in range(10)]
        result_a = channel._pick_artwork(artworks, "gallery_a")
        result_b = channel._pick_artwork(artworks, "gallery_b")
        # Both keys work independently; both return valid artworks
        assert result_a in artworks
        assert result_b in artworks
