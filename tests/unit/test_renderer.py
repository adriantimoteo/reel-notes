from datetime import datetime, timezone
from pathlib import Path

from pipeline.models import ExtractionResult, Item, ReelMetadata
from output.renderer import generate_filename, render

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "expected_note.md"


def _make_metadata(**overrides) -> ReelMetadata:
    defaults = dict(
        source_url="https://instagram.com/reel/abc123",
        platform="instagram",
        author="Travel.Jane",
        posted_at=datetime(2026, 3, 12),
        title="Tokyo Food Tour",
        caption="The best ramen spots",
        video_path=Path("/tmp/abc.mp4"),
        hashtags=["tokyo", "ramen"],
    )
    defaults.update(overrides)
    return ReelMetadata(**defaults)


def _make_extraction(**overrides) -> ExtractionResult:
    defaults = dict(
        transcription="Today we visit the best ramen spots in Tokyo.",
        ocr_text="Ichiran Ramen | Open 24h",
        summary="A tour of Tokyo's best ramen restaurants.",
        title="Best Tokyo Ramen Tour",
        items=[
            Item(name="Ichiran Ramen", item_type="restaurant", description="Famous solo-booth ramen chain."),
        ],
    )
    defaults.update(overrides)
    return ExtractionResult(**defaults)


CAPTURED_AT = datetime(2026, 5, 27, 14, 30, 12, tzinfo=timezone.utc)


def test_generate_filename_format() -> None:
    metadata = _make_metadata()
    extraction = _make_extraction(title="Best Tokyo Ramen Tour")
    result = generate_filename(metadata, extraction, captured_at=CAPTURED_AT)
    assert result.startswith("best-tokyo-ramen-tour-")
    assert result.endswith(".md")


def test_generate_filename_timestamp() -> None:
    metadata = _make_metadata()
    extraction = _make_extraction(title="Some Title")
    result = generate_filename(metadata, extraction, captured_at=CAPTURED_AT)
    assert "20260527143012" in result


def test_render_matches_fixture() -> None:
    metadata = _make_metadata()
    extraction = _make_extraction()
    result = render(metadata, extraction, captured_at=CAPTURED_AT)

    expected_raw = FIXTURE_PATH.read_text(encoding="utf-8")
    result_lines = [line.rstrip() for line in result.splitlines()]
    expected_lines = [line.rstrip() for line in expected_raw.splitlines()]
    assert result_lines == expected_lines


def test_render_empty_items() -> None:
    metadata = _make_metadata()
    extraction = _make_extraction(items=[])
    result = render(metadata, extraction, captured_at=CAPTURED_AT)
    assert "*(none)*" in result


def test_render_empty_hashtags() -> None:
    metadata = _make_metadata(hashtags=[])
    extraction = _make_extraction()
    result = render(metadata, extraction, captured_at=CAPTURED_AT)
    lines = result.splitlines()
    tags_line = next(line for line in lines if line.startswith("tags:"))
    assert tags_line == "tags: []"


def test_render_posted_at_none() -> None:
    metadata = _make_metadata(posted_at=None)
    extraction = _make_extraction()
    result = render(metadata, extraction, captured_at=CAPTURED_AT)
    lines = result.splitlines()
    posted_line = next(line for line in lines if line.startswith("posted:"))
    assert posted_line == "posted: unknown"
