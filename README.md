# mimir-source-metart

A Mimir source plugin that serves artwork images from [The Metropolitan Museum of Art's open collection](https://www.metmuseum.org/art/collection). No API key required.

## Features

- **No API key** — the Met's Collection API is fully public
- **Multiple gallery types:**
  - **Highlights** — the Met's hand-picked featured artworks
  - **Department** — filter by any of the Met's 19 departments (Egyptian Art, European Paintings, Asian Art, etc.)
  - **Search** — keyword search across the full collection
- **Flexible filters** — public domain, date range, medium
- **Multiple galleries** — create as many sub-channels as you want, each with different settings
- **Image quality** — full-resolution original or web-large thumbnail
- **Fit modes** — letterbox, crop, or stretch to display resolution
- **Baked-in details overlay** — optionally draw title/artist/date/etc. directly onto the artwork image (any corner/edge), for setups with no paired details display
- **Metadata response header** — optionally expose the same artwork details as an `X-Artwork-Metadata` header on `/request-image`, for integrations that want them without parsing the image

## Default Galleries

Three galleries are pre-configured:

| Gallery | Type | Description |
|---------|------|-------------|
| Met Highlights | Highlights | The Met's curated highlight artworks |
| Impressionism | Search | Keyword search for impressionism |
| Ancient Egypt | Department | Egyptian Art department (Dept 10) |

## Gallery Configuration Options

| Setting | Description |
|---------|-------------|
| Type | `highlights`, `department`, or `search` |
| Department | Met department ID (shown in the manager UI) |
| Keyword | Search term for the `search` type |
| Public domain | Filter to CC0 images (recommended; default on) |
| Date range | Filter by object creation year |
| Medium | Filter by material/technique (e.g. "Oil on canvas") |

## Plugin Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Fit Mode | letterbox | How to fit artwork to display: letterbox / crop / stretch |
| Image Quality | primary | `primary` = full-resolution, `small` = web-large thumbnail |
| Max Artworks / Gallery | 200 | How many artwork details to pre-cache per gallery |
| Refresh Interval | 168h (weekly) | How often to rebuild the artwork cache |
| Bake Details onto Image | off | Draws a details panel directly onto the artwork image |
| Overlay Position | bottom_left | `top_left` / `top_right` / `bottom_left` / `bottom_right` / `top_center` / `bottom_center` |
| Overlay Fields | title, artist | Any of: `title`, `artist`, `date`, `medium`, `department`, `culture` — the same fields the paired "details" display already uses |
| Include Metadata in Response Header | off | Attaches title/artist/date/etc. as a base64-encoded JSON `X-Artwork-Metadata` header on `/request-image` |

### About the metadata header

`X-Artwork-Metadata` is set at the plugin's HTTP boundary — it's available to
anything that calls `/request-image` directly. **It does not currently reach
the MQTT message a display client receives**: Mimir's core render pipeline
(`scene_refresh_service` → the MQTT publisher) only forwards image bytes and a
content fingerprint today, for every channel, not just this one. Wiring artwork
metadata into the actual outbound MQTT payload is a separate, larger change to
the server's shared render/publish path — this header is the plugin-side half
of that, ready for the day that wiring exists.

## API

Built on the [Met Museum Collection API](https://metmuseum.github.io/). Uses:
- `GET /objects` — fetch object IDs by department, highlight status, filters
- `GET /search` — keyword search across the full collection
- `GET /objects/{objectID}` — fetch object details and image URLs
- `GET /departments` — list all Met departments

## Attribution

This product uses data from [The Metropolitan Museum of Art Collection API](https://metmuseum.github.io/).  
Images are provided under [CC0 1.0 Universal Public Domain Dedication](https://creativecommons.org/publicdomain/zero/1.0/).
