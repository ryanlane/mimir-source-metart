"""Tests for met-art channel models — verifies mimir_utils migration."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from channels.met_art.models import ArtworkCache, Settings

_ARTWORKS = [{"object_id": 1, "title": "Starry Night", "artist": "van Gogh", "primary_image": "http://example.com/img.jpg"}]


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert len(s.galleries) == 3
        assert s.fit_mode == "letterbox"

    def test_to_dict_roundtrip(self):
        s = Settings()
        s2 = Settings.from_dict(s.to_dict())
        assert s2.fit_mode == s.fit_mode
        assert len(s2.galleries) == len(s.galleries)

    def test_from_dict_ignores_unknown(self):
        s = Settings.from_dict({"fit_mode": "fill", "nonexistent": 99})
        assert s.fit_mode == "fill"

    def test_no_secret_fields_to_mask(self):
        s = Settings()
        pub = s.to_public_dict()
        assert pub == s.to_dict()


class TestArtworkCache:
    @pytest.fixture
    def cache(self, tmp_path):
        return ArtworkCache(tmp_path / "artworks.json")

    def test_empty_state_has_galleries_key(self, cache):
        assert "galleries" in cache._data

    def test_needs_refresh_when_missing(self, cache):
        assert cache.needs_refresh("highlights", 168) is True

    def test_update_then_no_refresh(self, cache):
        cache.update("highlights", _ARTWORKS)
        assert cache.needs_refresh("highlights", 168) is False

    def test_get_artworks(self, cache):
        cache.update("highlights", _ARTWORKS)
        arts = cache.get_artworks("highlights")
        assert arts[0]["title"] == "Starry Night"

    def test_get_artworks_combined(self, cache):
        cache.update("highlights", _ARTWORKS)
        cache.update("impressionism", [{"object_id": 2, "title": "Monet"}])
        combined = cache.get_artworks_combined()
        assert len(combined) == 2

    def test_remove_gallery(self, cache):
        cache.update("highlights", _ARTWORKS)
        cache.remove_gallery("highlights")
        assert cache.get_artworks("highlights") == []

    def test_mark_stale(self, cache):
        cache.update("highlights", _ARTWORKS)
        cache.mark_stale("highlights")
        assert cache.needs_refresh("highlights", 1) is True

    def test_stats(self, cache):
        cache.update("highlights", _ARTWORKS)
        assert cache.stats()["highlights"]["count"] == 1

    def test_persists_to_disk(self, tmp_path):
        c1 = ArtworkCache(tmp_path / "a.json")
        c1.update("highlights", _ARTWORKS)
        c2 = ArtworkCache(tmp_path / "a.json")
        assert c2.get_artworks("highlights")[0]["title"] == "Starry Night"

    def test_corrupt_file_starts_with_empty_state(self, tmp_path):
        p = tmp_path / "a.json"
        p.write_text("{{bad}}")
        c = ArtworkCache(p)
        assert c._data == {"galleries": {}}
