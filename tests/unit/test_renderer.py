from datetime import datetime, timezone
from pathlib import Path

from pipeline.models import ExtractionResult, Ingredient, Item, ReelMetadata, TutorialStep
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


def test_render_tutorial_with_ingredients_and_steps() -> None:
    metadata = _make_metadata()
    extraction = _make_extraction(
        content_type="tutorial",
        items=[],
        ingredients=[
            Ingredient(name="spaghetti", quantity="200g"),
            Ingredient(name="egg yolks", quantity=None),
        ],
        steps=[
            TutorialStep(step_number=1, text="Boil the pasta in salted water."),
            TutorialStep(step_number=2, text="Fry the guanciale until crispy."),
        ],
    )
    result = render(metadata, extraction, captured_at=CAPTURED_AT)
    assert "type: tutorial" in result
    assert "## Ingredients" in result
    assert "- 200g spaghetti" in result
    assert "- egg yolks" in result
    assert "## Steps" in result
    assert "1. Boil the pasta in salted water." in result
    assert "2. Fry the guanciale until crispy." in result
    assert "## Items mentioned" not in result


def test_render_tutorial_without_ingredients() -> None:
    metadata = _make_metadata()
    extraction = _make_extraction(
        content_type="tutorial",
        items=[],
        ingredients=[],
        steps=[
            TutorialStep(step_number=1, text="Drill the armbar entry."),
        ],
    )
    result = render(metadata, extraction, captured_at=CAPTURED_AT)
    assert "## Ingredients" not in result
    assert "## Steps" in result
    assert "1. Drill the armbar entry." in result


def test_render_other_type() -> None:
    metadata = _make_metadata()
    extraction = _make_extraction(
        content_type="other",
        items=[],
        ingredients=[],
        steps=[],
    )
    result = render(metadata, extraction, captured_at=CAPTURED_AT)
    assert "type: other" in result
    assert "## Items mentioned" not in result
    assert "## Ingredients" not in result
    assert "## Steps" not in result


def test_render_type_none_falls_back_to_list() -> None:
    metadata = _make_metadata()
    extraction = _make_extraction(
        content_type=None,
        items=[
            Item(name="Ramen Spot", item_type="restaurant", description="Great broth."),
        ],
    )
    result = render(metadata, extraction, captured_at=CAPTURED_AT)
    assert "type: list" in result
    assert "## Items mentioned" in result
    assert "**Ramen Spot** — Great broth." in result
