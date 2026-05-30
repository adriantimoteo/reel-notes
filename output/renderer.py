"""Note rendering logic."""

import logging
import re
from datetime import datetime, timezone

from pipeline.models import ExtractionResult, ReelMetadata

logger = logging.getLogger(__name__)


def generate_filename(
    metadata: ReelMetadata,
    extraction: ExtractionResult,
    captured_at: datetime | None = None,
) -> str:
    ts = captured_at if captured_at is not None else datetime.now(timezone.utc)
    timestamp = ts.strftime("%Y%m%d%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", extraction.title.lower()).strip("-")[:40]
    return f"{slug}-{timestamp}.md"


def render(
    metadata: ReelMetadata,
    extraction: ExtractionResult,
    captured_at: datetime | None = None,
) -> str:
    ts = captured_at if captured_at is not None else datetime.now(timezone.utc)

    author_display = metadata.author if metadata.author is not None else "unknown"
    posted = metadata.posted_at.strftime("%Y-%m-%d") if metadata.posted_at is not None else "unknown"
    captured = ts.strftime("%Y-%m-%d")
    tags = ", ".join(metadata.hashtags)

    if extraction.items:
        items_block = "\n".join(
            f"- **{item.name}** — {item.description}" for item in extraction.items
        )
    else:
        items_block = "*(none)*"

    return (
        f"---\n"
        f'source: "{metadata.source_url}"\n'
        f"platform: {metadata.platform}\n"
        f'author: "@{author_display}"\n'
        f"posted: {posted}\n"
        f"captured: {captured}\n"
        f"tags: [{tags}]\n"
        f"---\n"
        f"\n"
        f"## Summary\n"
        f"{extraction.summary}\n"
        f"\n"
        f"## Items mentioned\n"
        f"{items_block}\n"
        f"\n"
        f"## Transcription\n"
        f"> {extraction.transcription}\n"
        f"\n"
        f"## On-screen text\n"
        f"> {extraction.ocr_text}\n"
        f"\n"
        f"## Caption\n"
        f"> {metadata.caption or '(none)'}"
    )
