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
        # medium/culture must be present too — the "details" paired display
        # has always used them (see templates/details.html); the image
        # variant's response dict silently omitted both until this change.
        assert result["medium"] == "Oil on canvas"
        assert result["culture"] == "French"

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


# ---------------------------------------------------------------------------
# Overlay: baking artwork details onto the image
# ---------------------------------------------------------------------------

def _make_real_jpeg(width=400, height=300, color=(30, 60, 90)) -> bytes:
    """A real, PIL-decodable JPEG — FAKE_IMAGE's garbage bytes can't be used
    here since the overlay needs to actually open and composite the image."""
    from PIL import Image as PilImage
    buf = __import__("io").BytesIO()
    PilImage.new("RGB", (width, height), color).save(buf, format="JPEG")
    return buf.getvalue()


class TestOverlay:
    def test_overlay_enabled_defaults_to_false(self, channel):
        # The gate itself lives in request_image(), not in _apply_overlay()
        # (which always draws when called) — covered by
        # test_request_image_skips_overlay_when_disabled below.
        assert channel.settings.overlay_enabled is False

    def test_draws_when_fields_present_changes_pixels(self, channel):
        original = _make_real_jpeg()
        channel.settings.overlay_enabled = True
        channel.settings.overlay_fields = ["title", "artist", "date", "medium"]
        result = channel._apply_overlay(original, make_artwork(1, "A Very Long Title For Testing"))
        assert result != original
        from PIL import Image as PilImage
        before = PilImage.open(__import__("io").BytesIO(original))
        after = PilImage.open(__import__("io").BytesIO(result))
        assert after.size == before.size  # overlay must not resize the artwork

    def test_no_fields_selected_returns_bytes_unchanged(self, channel):
        original = _make_real_jpeg()
        channel.settings.overlay_fields = []  # direct assignment, bypassing __post_init__
        result = channel._apply_overlay(original, make_artwork(1))
        assert result == original

    def test_missing_fields_on_artwork_are_skipped_gracefully(self, channel):
        original = _make_real_jpeg()
        channel.settings.overlay_fields = ["title", "culture"]
        artwork = make_artwork(1)
        artwork["culture"] = ""  # falsy — should just be omitted, not raise
        result = channel._apply_overlay(original, artwork)
        assert result != original  # title still draws

    def test_all_six_positions_render_without_error(self, channel):
        from channels.met_art.models import OVERLAY_POSITIONS
        original = _make_real_jpeg()
        channel.settings.overlay_fields = ["title", "artist", "date", "medium", "department", "culture"]
        for position in OVERLAY_POSITIONS:
            channel.settings.overlay_position = position
            result = channel._apply_overlay(original, make_artwork(1, "Title " * 8))
            assert result != original, f"position={position} produced no change"

    def test_corrupt_bytes_fall_back_to_unchanged(self, channel):
        channel.settings.overlay_fields = ["title"]
        garbage = b"not a real image"
        result = channel._apply_overlay(garbage, make_artwork(1))
        assert result == garbage

    async def test_request_image_applies_overlay_when_enabled(self, channel_with_cache):
        real_jpeg = _make_real_jpeg()
        channel_with_cache.settings.overlay_enabled = True
        with patch("channels.met_art.fetcher.fetch_artwork_image", return_value=real_jpeg):
            result = await channel_with_cache.request_image({"subchannel_id": "highlights"})
        assert result["success"] is True
        assert result["bytes"] != real_jpeg

    async def test_request_image_skips_overlay_when_disabled(self, channel_with_cache):
        real_jpeg = _make_real_jpeg()
        assert channel_with_cache.settings.overlay_enabled is False
        with patch("channels.met_art.fetcher.fetch_artwork_image", return_value=real_jpeg):
            result = await channel_with_cache.request_image({"subchannel_id": "highlights"})
        assert result["bytes"] == real_jpeg


# ---------------------------------------------------------------------------
# Text wrapping — replaces the old single-line ellipsis truncation so every
# field displays in full, never cut off.
# ---------------------------------------------------------------------------

class TestWrapToWidth:
    @staticmethod
    def _draw():
        from PIL import Image as PilImage, ImageDraw as PilImageDraw
        img = PilImage.new("RGB", (10, 10))
        return PilImageDraw.Draw(img)

    def _font(self, size=20):
        from channels.met_art.channel import _load_font
        return _load_font(size)

    def test_short_text_fits_on_one_line(self, channel):
        draw = self._draw()
        lines = channel._wrap_to_width(draw, "Short title", self._font(), max_width=1000)
        assert lines == ["Short title"]

    def test_empty_text_returns_empty_list(self, channel):
        draw = self._draw()
        assert channel._wrap_to_width(draw, "", self._font(), max_width=1000) == []

    def test_long_text_wraps_to_multiple_lines(self, channel):
        draw = self._draw()
        font = self._font(28)
        text = "A Very Long Museum Object Title That Cannot Possibly Fit On One Line"
        lines = channel._wrap_to_width(draw, text, font, max_width=200)
        assert len(lines) > 1
        for line in lines:
            assert draw.textlength(line, font=font) <= 200

    def test_wrapping_preserves_every_word_no_information_lost(self, channel):
        """The whole point: unlike the old ellipsis truncation, nothing is
        dropped — rejoining the wrapped lines reconstructs the input exactly."""
        draw = self._draw()
        font = self._font(28)
        text = "Terracotta fragment of a kylix attributed to the Kleophrades Painter"
        lines = channel._wrap_to_width(draw, text, font, max_width=180)
        assert len(lines) > 1
        assert " ".join(lines) == text

    def test_single_unbreakable_word_force_breaks_by_character(self, channel):
        draw = self._draw()
        font = self._font(28)
        text = "Supercalifragilisticexpialidocioussupercalifragilistic"
        lines = channel._wrap_to_width(draw, text, font, max_width=100)
        assert len(lines) > 1
        assert "".join(lines) == text  # character-split — no spaces to rejoin
        for line in lines:
            assert draw.textlength(line, font=font) <= 100

    def test_zero_max_width_returns_text_unwrapped(self, channel):
        draw = self._draw()
        assert channel._wrap_to_width(draw, "Some title", self._font(), max_width=0) == ["Some title"]


# ---------------------------------------------------------------------------
# Font family + relative size
# ---------------------------------------------------------------------------

class TestFontFamilyAndScale:
    def test_each_family_loads_a_distinct_real_font(self, channel):
        from channels.met_art.channel import _load_font
        sans = _load_font(24, family="sans")
        serif = _load_font(24, family="serif")
        mono = _load_font(24, family="mono")
        assert "Sans" in sans.getname()[0]
        assert "Serif" in serif.getname()[0]
        assert "Mono" in mono.getname()[0]

    def test_bold_variant_differs_from_regular(self, channel):
        from channels.met_art.channel import _load_font
        regular = _load_font(24, bold=False, family="serif")
        bold = _load_font(24, bold=True, family="serif")
        assert regular.getname() != bold.getname()

    def test_unknown_family_falls_back_to_sans(self, channel):
        from channels.met_art.channel import _load_font
        font = _load_font(24, family="not-a-real-family")
        assert "Sans" in font.getname()[0]

    def test_font_scale_factors_are_ordered(self):
        from channels.met_art.channel import FONT_SCALE_FACTORS
        assert (
            FONT_SCALE_FACTORS["small"]
            < FONT_SCALE_FACTORS["medium"]
            < FONT_SCALE_FACTORS["large"]
            < FONT_SCALE_FACTORS["x_large"]
        )

    def test_larger_scale_requests_larger_font_sizes(self, channel, monkeypatch):
        """_apply_overlay must actually thread overlay_font_scale into the
        pixel sizes it asks _load_font for — not just accept the setting."""
        requested_sizes = []

        def spy_load_font(size, bold=False, family="sans"):
            requested_sizes.append(size)
            from channels.met_art.channel import _load_font as real_load_font
            return real_load_font(size, bold=bold, family=family)

        monkeypatch.setattr("channels.met_art.channel._load_font", spy_load_font)

        original = _make_real_jpeg(800, 600)
        artwork = make_artwork(1, "Test Title")

        channel.settings.overlay_fields = ["title"]
        channel.settings.overlay_font_scale = "small"
        channel._apply_overlay(original, artwork)
        small_sizes = list(requested_sizes)

        requested_sizes.clear()
        channel.settings.overlay_font_scale = "x_large"
        channel._apply_overlay(original, artwork)
        large_sizes = list(requested_sizes)

        assert max(large_sizes) > max(small_sizes)

    def test_font_family_setting_used_by_apply_overlay(self, channel, monkeypatch):
        requested_families = []

        def spy_load_font(size, bold=False, family="sans"):
            requested_families.append(family)
            from channels.met_art.channel import _load_font as real_load_font
            return real_load_font(size, bold=bold, family=family)

        monkeypatch.setattr("channels.met_art.channel._load_font", spy_load_font)

        original = _make_real_jpeg(800, 600)
        channel.settings.overlay_fields = ["title"]
        channel.settings.overlay_font_family = "mono"
        channel._apply_overlay(original, make_artwork(1, "Test Title"))

        assert requested_families and all(f == "mono" for f in requested_families)


# ---------------------------------------------------------------------------
# X-Artwork-Metadata response header
# ---------------------------------------------------------------------------

class TestMetadataHeader:
    async def test_header_present_when_enabled(self, channel_with_cache):
        channel_with_cache.settings.include_metadata_in_response = True
        with patch("channels.met_art.fetcher.fetch_artwork_image", return_value=FAKE_IMAGE):
            from fastapi.testclient import TestClient
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(channel_with_cache.get_router(), prefix=f"/api/channels/{channel_with_cache.id}")
            client = TestClient(app)
            resp = client.post(
                f"/api/channels/{channel_with_cache.id}/request-image",
                json={"subchannel_id": "highlights"},
            )
        assert resp.status_code == 200
        assert "X-Artwork-Metadata" in resp.headers

        import base64
        import json
        decoded = json.loads(base64.urlsafe_b64decode(resp.headers["X-Artwork-Metadata"]))
        assert decoded["artist"] == "Test Artist"
        assert decoded["medium"] == "Oil on canvas"
        assert decoded["culture"] == "French"
        assert "title" in decoded
        # A client rendering its own overlay needs to know where to draw it.
        assert decoded["overlay_position"] == channel_with_cache.settings.overlay_position

    async def test_header_absent_when_disabled(self, channel_with_cache):
        assert channel_with_cache.settings.include_metadata_in_response is False
        with patch("channels.met_art.fetcher.fetch_artwork_image", return_value=FAKE_IMAGE):
            from fastapi.testclient import TestClient
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(channel_with_cache.get_router(), prefix=f"/api/channels/{channel_with_cache.id}")
            client = TestClient(app)
            resp = client.post(
                f"/api/channels/{channel_with_cache.id}/request-image",
                json={"subchannel_id": "highlights"},
            )
        assert resp.status_code == 200
        assert "X-Artwork-Metadata" not in resp.headers

    async def test_settings_put_validates_overlay_position(self, channel):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(channel.get_router(), prefix=f"/api/channels/{channel.id}")
        client = TestClient(app)
        resp = client.put(
            f"/api/channels/{channel.id}/settings",
            json={"overlay_position": "not-a-real-position", "overlay_fields": ["title", "bogus"]},
        )
        assert resp.status_code == 200
        assert resp.json()["settings"]["overlay_position"] == "bottom_left"
        assert resp.json()["settings"]["overlay_fields"] == ["title"]
