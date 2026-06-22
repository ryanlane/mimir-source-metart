import sys
from pathlib import Path

# Ensure the plugin root is on sys.path so `channels.met_art` is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


def make_artwork(object_id: int = 1, title: str = "Test Artwork") -> dict:
    return {
        "object_id": object_id,
        "title": title,
        "artist": "Test Artist",
        "date": "1900",
        "medium": "Oil on canvas",
        "department": "European Paintings",
        "culture": "French",
        "primary_image": f"https://images.metmuseum.org/images/{object_id}.jpg",
        "small_image": f"https://images.metmuseum.org/images/{object_id}_small.jpg",
        "object_url": f"https://www.metmuseum.org/art/collection/search/{object_id}",
    }
