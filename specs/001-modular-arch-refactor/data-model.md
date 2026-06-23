# Data Model: Modular Architecture Refactor

## Layer Contracts

### SourceProvider (protocol)

```python
class SearchResult(TypedDict):
    title: str
    url: str
    provider_id: int
    provider_name: str

class EpisodeInfo(TypedDict):
    episode: int
    page_url: str

class StreamResult(TypedDict):
    url: str
    quality: str  # "1080p", "720p", "480p", "auto"
    provider_id: int
```

| Field | Type | Description |
|-------|------|-------------|
| SearchResult.title | string | Display title of the anime |
| SearchResult.url | string | URL to the anime's page on the provider |
| SearchResult.provider_id | int | Numeric provider identifier |
| SearchResult.provider_name | string | Human-readable provider name |
| EpisodeInfo.episode | int | Episode number |
| EpisodeInfo.page_url | string | URL to the episode page |
| StreamResult.url | string | Resolved stream URL (.mp4, .m3u8) |
| StreamResult.quality | string | Resolution label |
| StreamResult.provider_id | int | Numeric provider identifier |

### CacheEntry

| Field | Type | Description |
|-------|------|-------------|
| slug | string | Provider-specific anime identifier |
| episode | int | Episode number |
| stream_url | string | Cached resolved stream URL |
| quality | string | Resolution label |
| fetched_at | float | Unix timestamp of cache write |
| provider_id | int | Numeric provider identifier |

### PlaybackRequest

| Field | Type | Description |
|-------|------|-------------|
| stream_urls | string[] | Ordered list of stream URLs |
| player_name | string | Preferred player ("mpv", "vlc", etc.) |
| slug | string or null | Anime slug for progress tracking |
| episode | int or null | Episode number for progress tracking |
| fullscreen | bool | Whether to launch in fullscreen |
| extra_args | string[] | Additional player arguments |

### Layer Boundaries

```
User Input
    │
    ▼
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│   UI     │────▶│  Providers   │────▶│ External Web │
│ (CLI/TUI)│     │  (scraping)  │     │   Sites      │
└──────────┘     └──────────────┘     └──────────────┘
    │                   │
    │                   ▼
    │            ┌──────────────┐
    │            │    Cache     │
    │            │  (streams)   │
    │            └──────────────┘
    │                   │
    ▼                   ▼
┌──────────┐     ┌──────────────┐
│ Playback │     │   DB Layer   │
│ (player) │     │  (persist)   │
└──────────┘     └──────────────┘
    │
    ▼
 External Player (VLC/MPV)
```

### Validation Rules

- Provider IDs MUST be unique across all registered providers
- Stream URLs MUST start with `http://`, `https://`, or be valid HLS playlists
- Cache entries older than 24 hours SHOULD be considered stale (configurable)
- Playback requests MUST include at least one stream URL
- UI layer MUST NOT import provider implementation details — only the SourceProvider protocol
