# reelkit

Shared building blocks for bots that turn Instagram Reels, TikTok videos/photo posts, and YouTube Shorts into structured data. Extracted from [reel-notes](../../README.md), which consumes it as a uv workspace member.

reelkit reads no environment variables or config files. Every setting is passed in by the caller.

## Install from another project

```bash
# local development, editable
uv add --editable ../reel-notes/packages/reelkit

# pinned to a commit
uv add "reelkit[telegram] @ git+https://github.com/<you>/reel-notes@<sha>#subdirectory=packages/reelkit"
```

The `telegram` extra pulls in aiogram for `reelkit.telegram`. Leave it out if you only need download and extraction.

## Modules

| Module | What it gives you |
|---|---|
| `reelkit.urls` | `detect_reel(text)` finds the first reel link in a message; `detect_platform`, `canonicalize`, `resolve_canonical_url` (resolves TikTok `vm.`/`vt.` shortlinks) |
| `reelkit.fetch` | `fetch(url, FetchSettings(...)) -> ReelMetadata`: yt-dlp for videos, gallery-dl for TikTok photo posts and Instagram carousels, with duration cap, cookies, and retry |
| `reelkit.gemini` | `generate_structured(client, model, paths, prompt, schema, description=...) -> dict`, plus `media_paths(metadata)`, `is_carousel`, `is_retryable_error`, `is_model_retired` |
| `reelkit.models` | `ReelMetadata` |
| `reelkit.exceptions` | `ReelCaptureError` and subclasses (`UnsupportedPlatformError`, `UnsupportedCarouselError`, `DurationCapExceeded`, `DownloadError`, `ExtractionError`) |
| `reelkit.retry` | `call_with_retry`: runs a blocking call in a thread with exponential backoff |
| `reelkit.status` | `StatusReporter` protocol (`async update(text)`) |
| `reelkit.tempfiles` | `cleanup_temp_dir(path)` |
| `reelkit.telegram` | `StatusMessage` (edits one Telegram message in place), `drain_pending` (process queued updates then exit) |

## Example

```python
from pathlib import Path

import google.genai as genai

from reelkit import gemini
from reelkit.fetch import FetchSettings, fetch

PLACES_SCHEMA = {
    "type": "object",
    "properties": {
        "places": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "area": {"type": "string"},
                    "blurb": {"type": "string"},
                },
                "required": ["name"],
            },
        }
    },
    "required": ["places"],
}


async def places_from_reel(url: str, client: genai.Client) -> dict:
    metadata = await fetch(url, FetchSettings(temp_dir=Path("tmp"), max_duration=120))
    try:
        return await gemini.generate_structured(
            client,
            "gemini-3.5-flash",
            gemini.media_paths(metadata),
            f"List every place recommended in this reel.\nCaption: {metadata.caption or ''}",
            PLACES_SCHEMA,
            description=f"places for {metadata.source_url}",
        )
    finally:
        for path in metadata.temp_paths():  # the caller owns downloaded files
            path.unlink(missing_ok=True)
```

## Tests

From the repo root, `uv run pytest` runs these alongside the app's tests.
