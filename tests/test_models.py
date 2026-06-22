"""Tests for models.py — Settings, ArtworkCache, make_gallery_id."""
import json
import time

import pytest

from channels.met_art.models import ArtworkCache, Settings, make_gallery_id
from tests.conftest import make_artwork


# ---------------------------------------------------------------------------
# make_gallery_id
# ---------------------------------------------------------------------------

def test_make_gallery_id_simple():
    assert make_gallery_id("My Gallery", set()) == "my_gallery"


def test_make_gallery_id_dedup():
    gid = make_gallery_id("My Gallery", {"my_gallery"})
    assert gid.startswith("my_gallery_")
    assert gid != "my_gallery"


def test_make_gallery_id_strips_special_chars():
    assert make_gallery_id("Impressionism & Realism!", set()) == "impressionism_realism"


def test_make_gallery_id_handles_empty_label():
    gid = make_gallery_id("", set())
    assert gid == "gallery"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.fit_mode == "letterbox"
        assert s.image_quality == "primary"
        assert s.cache_max_per_gallery == 200
        assert s.refresh_interval_hours == 168
        assert len(s.galleries) == 3

    def test_round_trip(self):
        s = Settings()
        s.fit_mode = "crop"
        s.image_quality = "small"
        s2 = Settings.from_dict(s.to_dict())
        assert s2.fit_mode == "crop"
        assert s2.image_quality == "small"
        assert len(s2.galleries) == len(s.galleries)

    def test_from_dict_ignores_unknown_keys(self):
        s = Settings.from_dict({"fit_mode": "stretch", "unknown_key": "should_be_ignored"})
        assert s.fit_mode == "stretch"

    def test_galleries_are_independent_across_instances(self):
        s1 = Settings()
        s2 = Settings()
        s1.galleries.append({"id": "extra"})
        assert len(s2.galleries) == 3

    def test_default_galleries_have_required_fields(self):
        for g in Settings().galleries:
            assert "id" in g
            assert "label" in g
            assert "type" in g


# ---------------------------------------------------------------------------
# ArtworkCache
# ---------------------------------------------------------------------------

class TestArtworkCacheNeedsRefresh:
    def test_true_for_unknown_gallery(self, tmp_path):
        cache = ArtworkCache(tmp_path / "cache.json")
        assert cache.needs_refresh("nonexistent", 168) is True

    def test_false_immediately_after_update(self, tmp_path):
        cache = ArtworkCache(tmp_path / "cache.json")
        cache.update("g1", [make_artwork(1)])
        assert cache.needs_refresh("g1", 168) is False

    def test_true_after_mark_stale(self, tmp_path):
        cache = ArtworkCache(tmp_path / "cache.json")
        cache.update("g1", [make_artwork(1)])
        cache.mark_stale("g1")
        assert cache.needs_refresh("g1", 168) is True

    def test_true_when_fetched_at_is_zero(self, tmp_path):
        cache = ArtworkCache(tmp_path / "cache.json")
        cache.update("g1", [make_artwork(1)])
        cache._data["galleries"]["g1"]["fetched_at"] = 0
        assert cache.needs_refresh("g1", 1) is True


class TestArtworkCacheMarkStale:
    def test_sets_fetched_at_to_zero(self, tmp_path):
        cache = ArtworkCache(tmp_path / "cache.json")
        cache.update("g1", [make_artwork(1)])
        cache.mark_stale("g1")
        assert cache._data["galleries"]["g1"]["fetched_at"] == 0

    def test_marks_all_galleries_when_no_id_given(self, tmp_path):
        cache = ArtworkCache(tmp_path / "cache.json")
        cache.update("g1", [make_artwork(1)])
        cache.update("g2", [make_artwork(2)])
        cache.mark_stale()
        assert cache.needs_refresh("g1", 168) is True
        assert cache.needs_refresh("g2", 168) is True

    def test_does_not_clear_artworks(self, tmp_path):
        """mark_stale resets the timestamp but preserves the artwork list."""
        cache = ArtworkCache(tmp_path / "cache.json")
        artworks = [make_artwork(i) for i in range(5)]
        cache.update("g1", artworks)
        cache.mark_stale("g1")
        assert len(cache.get_artworks("g1")) == 5

    def test_persists_stale_flag_to_disk(self, tmp_path):
        path = tmp_path / "cache.json"
        cache = ArtworkCache(path)
        cache.update("g1", [make_artwork(1)])
        cache.mark_stale("g1")

        reloaded = ArtworkCache(path)
        assert reloaded.needs_refresh("g1", 168) is True


class TestArtworkCacheGetArtworks:
    def test_get_artworks_for_specific_gallery(self, tmp_path):
        cache = ArtworkCache(tmp_path / "cache.json")
        cache.update("g1", [make_artwork(1, "A")])
        cache.update("g2", [make_artwork(2, "B")])
        result = cache.get_artworks("g1")
        assert len(result) == 1
        assert result[0]["title"] == "A"

    def test_get_artworks_returns_empty_for_missing_gallery(self, tmp_path):
        cache = ArtworkCache(tmp_path / "cache.json")
        assert cache.get_artworks("missing") == []

    def test_get_artworks_combined_no_filter_returns_all(self, tmp_path):
        cache = ArtworkCache(tmp_path / "cache.json")
        cache.update("g1", [make_artwork(1), make_artwork(2)])
        cache.update("g2", [make_artwork(3)])
        combined = cache.get_artworks_combined()
        assert len(combined) == 3

    def test_get_artworks_combined_with_gallery_id(self, tmp_path):
        cache = ArtworkCache(tmp_path / "cache.json")
        cache.update("g1", [make_artwork(1)])
        cache.update("g2", [make_artwork(2)])
        result = cache.get_artworks_combined("g1")
        assert len(result) == 1
        assert result[0]["object_id"] == 1


class TestArtworkCachePersistence:
    def test_reloads_from_disk_on_init(self, tmp_path):
        path = tmp_path / "cache.json"
        c1 = ArtworkCache(path)
        c1.update("gallery1", [make_artwork(42, "Persisted")])

        c2 = ArtworkCache(path)
        artworks = c2.get_artworks("gallery1")
        assert len(artworks) == 1
        assert artworks[0]["object_id"] == 42
        assert artworks[0]["title"] == "Persisted"

    def test_handles_missing_cache_file_gracefully(self, tmp_path):
        cache = ArtworkCache(tmp_path / "nonexistent.json")
        assert cache.get_artworks_combined() == []

    def test_handles_corrupt_cache_file(self, tmp_path):
        path = tmp_path / "cache.json"
        path.write_text("{ not valid json }")
        cache = ArtworkCache(path)
        assert cache.get_artworks_combined() == []

    def test_remove_gallery_clears_artworks_and_persists(self, tmp_path):
        path = tmp_path / "cache.json"
        cache = ArtworkCache(path)
        cache.update("g1", [make_artwork(1)])
        cache.remove_gallery("g1")
        assert cache.get_artworks("g1") == []

        reloaded = ArtworkCache(path)
        assert reloaded.get_artworks("g1") == []

    def test_stats_reflects_update(self, tmp_path):
        cache = ArtworkCache(tmp_path / "cache.json")
        cache.update("g1", [make_artwork(1), make_artwork(2)])
        stats = cache.stats()
        assert stats["g1"]["count"] == 2
        assert stats["g1"]["fetched_at"] > 0
