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

## API

Built on the [Met Museum Collection API](https://metmuseum.github.io/). Uses:
- `GET /objects` — fetch object IDs by department, highlight status, filters
- `GET /search` — keyword search across the full collection
- `GET /objects/{objectID}` — fetch object details and image URLs
- `GET /departments` — list all Met departments

## Attribution

This product uses data from [The Metropolitan Museum of Art Collection API](https://metmuseum.github.io/).  
Images are provided under [CC0 1.0 Universal Public Domain Dedication](https://creativecommons.org/publicdomain/zero/1.0/).
