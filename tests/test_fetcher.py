"""Tests for fetcher.py — all HTTP calls are mocked via unittest.mock."""
from unittest.mock import MagicMock, patch

import pytest

from channels.met_art import fetcher


def _mock_response(status_code=200, json_data=None, content=b"", content_type="image/jpeg"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.content = content
    resp.headers = {"content-type": content_type}
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# fetch_departments
# ---------------------------------------------------------------------------

class TestFetchDepartments:
    def test_returns_department_list(self):
        data = {"departments": [
            {"departmentId": 1, "displayName": "American Decorative Arts"},
            {"departmentId": 10, "displayName": "Egyptian Art"},
        ]}
        with patch("channels.met_art.fetcher.requests.get", return_value=_mock_response(json_data=data)):
            result = fetcher.fetch_departments()
        assert len(result) == 2
        assert result[0]["departmentId"] == 1
        assert result[1]["displayName"] == "Egyptian Art"

    def test_returns_empty_list_on_network_error(self):
        with patch("channels.met_art.fetcher.requests.get", side_effect=Exception("timeout")):
            result = fetcher.fetch_departments()
        assert result == []

    def test_returns_empty_list_on_http_error(self):
        resp = _mock_response(status_code=503)
        resp.raise_for_status.side_effect = Exception("503 Service Unavailable")
        with patch("channels.met_art.fetcher.requests.get", return_value=resp):
            result = fetcher.fetch_departments()
        assert result == []


# ---------------------------------------------------------------------------
# _build_objects_params
# ---------------------------------------------------------------------------

class TestBuildObjectsParams:
    def test_always_includes_has_images(self):
        params = fetcher._build_objects_params({"type": "highlights"})
        assert params["hasImages"] == "true"

    def test_highlights_type_adds_is_highlight(self):
        params = fetcher._build_objects_params({"type": "highlights", "is_public_domain": True})
        assert params["isHighlight"] == "true"

    def test_non_highlights_type_omits_is_highlight(self):
        params = fetcher._build_objects_params({"type": "department", "department_id": 10})
        assert "isHighlight" not in params

    def test_public_domain_flag(self):
        params = fetcher._build_objects_params({"type": "highlights", "is_public_domain": True})
        assert params["isPublicDomain"] == "true"

    def test_department_id_included(self):
        params = fetcher._build_objects_params({"type": "department", "department_id": 10})
        assert params["departmentIds"] == "10"

    def test_date_range_included(self):
        params = fetcher._build_objects_params({
            "type": "highlights",
            "date_begin": 1800,
            "date_end": 1900,
        })
        assert params["dateBegin"] == "1800"
        assert params["dateEnd"] == "1900"

    def test_medium_included_when_set(self):
        params = fetcher._build_objects_params({"type": "department", "department_id": 11, "medium": "Oil on canvas"})
        assert params["medium"] == "Oil on canvas"

    def test_medium_excluded_when_empty(self):
        params = fetcher._build_objects_params({"type": "highlights", "medium": ""})
        assert "medium" not in params

    def test_medium_excluded_when_whitespace_only(self):
        params = fetcher._build_objects_params({"type": "highlights", "medium": "   "})
        assert "medium" not in params


# ---------------------------------------------------------------------------
# fetch_object_ids
# ---------------------------------------------------------------------------

class TestFetchObjectIds:
    def test_search_type_uses_search_endpoint(self):
        gallery = {"id": "test", "type": "search", "q": "impressionism", "is_public_domain": True}
        resp = _mock_response(json_data={"objectIDs": [1, 2, 3]})
        with patch("channels.met_art.fetcher.requests.get", return_value=resp) as mock_get:
            ids = fetcher.fetch_object_ids(gallery)
        url = mock_get.call_args[0][0]
        assert url.endswith("/search")
        assert ids == [1, 2, 3]

    def test_search_passes_keyword_as_q_param(self):
        gallery = {"id": "test", "type": "search", "q": "monet", "is_public_domain": True}
        resp = _mock_response(json_data={"objectIDs": [1]})
        with patch("channels.met_art.fetcher.requests.get", return_value=resp) as mock_get:
            fetcher.fetch_object_ids(gallery)
        params = mock_get.call_args[1]["params"]
        assert params["q"] == "monet"

    def test_highlights_type_uses_objects_endpoint(self):
        gallery = {"id": "test", "type": "highlights", "is_public_domain": True}
        resp = _mock_response(json_data={"objectIDs": [10, 20, 30]})
        with patch("channels.met_art.fetcher.requests.get", return_value=resp) as mock_get:
            ids = fetcher.fetch_object_ids(gallery)
        url = mock_get.call_args[0][0]
        assert url.endswith("/objects")
        assert ids == [10, 20, 30]

    def test_department_type_uses_objects_endpoint(self):
        gallery = {"id": "test", "type": "department", "department_id": 10, "is_public_domain": True}
        resp = _mock_response(json_data={"objectIDs": [5, 6, 7]})
        with patch("channels.met_art.fetcher.requests.get", return_value=resp) as mock_get:
            ids = fetcher.fetch_object_ids(gallery)
        url = mock_get.call_args[0][0]
        assert url.endswith("/objects")
        assert ids == [5, 6, 7]

    def test_handles_null_objectIDs_field(self):
        gallery = {"id": "test", "type": "highlights", "is_public_domain": True}
        resp = _mock_response(json_data={"objectIDs": None})
        with patch("channels.met_art.fetcher.requests.get", return_value=resp):
            ids = fetcher.fetch_object_ids(gallery)
        assert ids == []

    def test_returns_empty_list_on_network_error(self):
        gallery = {"id": "test", "type": "search", "q": "impressionism"}
        with patch("channels.met_art.fetcher.requests.get", side_effect=Exception("network error")):
            ids = fetcher.fetch_object_ids(gallery)
        assert ids == []

    def test_search_without_q_falls_back_to_objects_endpoint(self):
        # A search gallery with no query string should use /objects not /search
        gallery = {"id": "test", "type": "search", "q": "", "is_public_domain": True}
        resp = _mock_response(json_data={"objectIDs": [1]})
        with patch("channels.met_art.fetcher.requests.get", return_value=resp) as mock_get:
            fetcher.fetch_object_ids(gallery)
        url = mock_get.call_args[0][0]
        assert url.endswith("/objects")


# ---------------------------------------------------------------------------
# fetch_object_detail
# ---------------------------------------------------------------------------

class TestFetchObjectDetail:
    def _artwork_response(self, object_id=123):
        return {
            "objectID": object_id,
            "title": "Water Lilies",
            "artistDisplayName": "Claude Monet",
            "objectDate": "1906",
            "medium": "Oil on canvas",
            "department": "European Paintings",
            "culture": "French",
            "primaryImage": "https://images.metmuseum.org/primary.jpg",
            "primaryImageSmall": "https://images.metmuseum.org/small.jpg",
            "objectURL": f"https://www.metmuseum.org/art/collection/search/{object_id}",
        }

    def test_returns_all_expected_fields(self):
        resp = _mock_response(json_data=self._artwork_response(123))
        with patch("channels.met_art.fetcher.requests.get", return_value=resp):
            result = fetcher.fetch_object_detail(123)
        assert result is not None
        assert result["object_id"] == 123
        assert result["title"] == "Water Lilies"
        assert result["artist"] == "Claude Monet"
        assert result["date"] == "1906"
        assert result["medium"] == "Oil on canvas"
        assert result["department"] == "European Paintings"
        assert result["culture"] == "French"
        assert result["primary_image"] == "https://images.metmuseum.org/primary.jpg"
        assert result["small_image"] == "https://images.metmuseum.org/small.jpg"
        assert result["object_url"] == "https://www.metmuseum.org/art/collection/search/123"

    def test_returns_none_when_no_primary_image(self):
        data = self._artwork_response()
        data["primaryImage"] = ""
        resp = _mock_response(json_data=data)
        with patch("channels.met_art.fetcher.requests.get", return_value=resp):
            result = fetcher.fetch_object_detail(123)
        assert result is None

    def test_returns_none_on_404(self):
        resp = _mock_response(status_code=404)
        with patch("channels.met_art.fetcher.requests.get", return_value=resp):
            result = fetcher.fetch_object_detail(999)
        assert result is None

    def test_returns_none_on_network_error(self):
        with patch("channels.met_art.fetcher.requests.get", side_effect=Exception("timeout")):
            result = fetcher.fetch_object_detail(123)
        assert result is None

    def test_falls_back_primary_image_when_small_is_empty(self):
        data = self._artwork_response()
        data["primaryImageSmall"] = ""
        resp = _mock_response(json_data=data)
        with patch("channels.met_art.fetcher.requests.get", return_value=resp):
            result = fetcher.fetch_object_detail(123)
        assert result["small_image"] == result["primary_image"]


# ---------------------------------------------------------------------------
# fetch_artwork_image
# ---------------------------------------------------------------------------

class TestFetchArtworkImage:
    def test_returns_bytes_for_valid_jpeg(self):
        img_bytes = b"\xff\xd8\xff" + b"X" * 1200
        resp = _mock_response(status_code=200, content=img_bytes, content_type="image/jpeg")
        with patch("channels.met_art.fetcher.requests.get", return_value=resp):
            result = fetcher.fetch_artwork_image("https://example.com/img.jpg")
        assert result == img_bytes

    def test_returns_bytes_for_valid_png(self):
        img_bytes = b"\x89PNG" + b"X" * 1200
        resp = _mock_response(status_code=200, content=img_bytes, content_type="image/png")
        with patch("channels.met_art.fetcher.requests.get", return_value=resp):
            result = fetcher.fetch_artwork_image("https://example.com/img.png")
        assert result == img_bytes

    def test_returns_none_for_non_200_status(self):
        resp = _mock_response(status_code=404, content=b"not found", content_type="image/jpeg")
        with patch("channels.met_art.fetcher.requests.get", return_value=resp):
            result = fetcher.fetch_artwork_image("https://example.com/img.jpg")
        assert result is None

    def test_returns_none_for_wrong_content_type(self):
        resp = _mock_response(status_code=200, content=b"x" * 2000, content_type="text/html")
        with patch("channels.met_art.fetcher.requests.get", return_value=resp):
            result = fetcher.fetch_artwork_image("https://example.com/page.html")
        assert result is None

    def test_returns_none_when_content_under_1kb(self):
        resp = _mock_response(status_code=200, content=b"tiny", content_type="image/jpeg")
        with patch("channels.met_art.fetcher.requests.get", return_value=resp):
            result = fetcher.fetch_artwork_image("https://example.com/img.jpg")
        assert result is None

    def test_returns_none_for_empty_url(self):
        result = fetcher.fetch_artwork_image("")
        assert result is None

    def test_returns_none_on_network_error(self):
        with patch("channels.met_art.fetcher.requests.get", side_effect=Exception("connection refused")):
            result = fetcher.fetch_artwork_image("https://example.com/img.jpg")
        assert result is None


# ---------------------------------------------------------------------------
# fetch_gallery_artworks
# ---------------------------------------------------------------------------

class TestFetchGalleryArtworks:
    def _make_detail(self, oid, sess=None):
        return {
            "object_id": oid,
            "title": f"Artwork {oid}",
            "artist": "Test Artist",
            "date": "1900",
            "medium": "Oil",
            "department": "Paintings",
            "culture": "",
            "primary_image": f"https://example.com/{oid}.jpg",
            "small_image": f"https://example.com/{oid}_small.jpg",
            "object_url": f"https://met.org/{oid}",
        }

    def test_returns_up_to_max_count_artworks(self):
        ids = list(range(1, 101))
        gallery = {"id": "test", "type": "highlights", "is_public_domain": True}
        with patch.object(fetcher, "fetch_object_ids", return_value=ids), \
             patch.object(fetcher, "fetch_object_detail", side_effect=self._make_detail), \
             patch("time.sleep"):
            artworks = fetcher.fetch_gallery_artworks(gallery, max_count=10)
        assert len(artworks) == 10

    def test_returns_empty_list_when_no_ids(self):
        gallery = {"id": "test", "type": "search", "q": "noresults", "is_public_domain": True}
        with patch.object(fetcher, "fetch_object_ids", return_value=[]):
            artworks = fetcher.fetch_gallery_artworks(gallery)
        assert artworks == []

    def test_skips_objects_without_images(self):
        ids = [1, 2, 3, 4, 5]

        def detail_with_gaps(oid, sess=None):
            return None if oid % 2 == 0 else self._make_detail(oid)

        gallery = {"id": "test", "type": "department", "department_id": 10, "is_public_domain": True}
        with patch.object(fetcher, "fetch_object_ids", return_value=ids), \
             patch.object(fetcher, "fetch_object_detail", side_effect=detail_with_gaps), \
             patch("time.sleep"):
            artworks = fetcher.fetch_gallery_artworks(gallery, max_count=10)

        assert len(artworks) == 3
        assert all(a["object_id"] % 2 == 1 for a in artworks)

    def test_search_gallery_preserves_id_order(self):
        """Search results should use API order (relevance), not random sample."""
        ids = list(range(1, 51))
        gallery = {"id": "test", "type": "search", "q": "monet", "is_public_domain": True}
        fetched_ids = []

        def track_detail(oid, sess=None):
            fetched_ids.append(oid)
            return self._make_detail(oid)

        with patch.object(fetcher, "fetch_object_ids", return_value=ids), \
             patch.object(fetcher, "fetch_object_detail", side_effect=track_detail), \
             patch("time.sleep"):
            fetcher.fetch_gallery_artworks(gallery, max_count=5)

        # Should have fetched IDs 1, 2, 3, 4, 5 in order (not a random sample)
        assert fetched_ids[:5] == [1, 2, 3, 4, 5]
