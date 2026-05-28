from datetime import datetime
from pathlib import Path

import pytest

from pipeline.models import ExtractionResult, Item, ReelMetadata


class TestReelMetadata:
    def test_instantiation_with_all_fields(self):
        posted = datetime(2024, 6, 15, 12, 0, 0)
        meta = ReelMetadata(
            source_url="https://www.instagram.com/reel/abc123/",
            platform="instagram",
            author="testuser",
            posted_at=posted,
            title="Weekend market finds",
            caption="Great spots #food #travel",
            video_path=Path("/tmp/video.mp4"),
            hashtags=["food", "travel"],
        )
        assert meta.source_url == "https://www.instagram.com/reel/abc123/"
        assert meta.platform == "instagram"
        assert meta.author == "testuser"
        assert meta.posted_at == posted
        assert meta.title == "Weekend market finds"
        assert meta.caption == "Great spots #food #travel"
        assert meta.video_path == Path("/tmp/video.mp4")
        assert meta.hashtags == ["food", "travel"]

    def test_hashtags_defaults_to_empty_list(self):
        meta = ReelMetadata(
            source_url="https://www.tiktok.com/@user/video/999",
            platform="tiktok",
            author="creator",
            posted_at=None,
            title=None,
            caption=None,
            video_path=Path("/tmp/vid.mp4"),
        )
        assert meta.hashtags == []

    def test_hashtags_default_is_not_shared(self):
        meta1 = ReelMetadata(
            source_url="https://example.com/1",
            platform="youtube",
            author=None,
            posted_at=None,
            title=None,
            caption=None,
            video_path=Path("/tmp/a.mp4"),
        )
        meta2 = ReelMetadata(
            source_url="https://example.com/2",
            platform="youtube",
            author=None,
            posted_at=None,
            title=None,
            caption=None,
            video_path=Path("/tmp/b.mp4"),
        )
        meta1.hashtags.append("foo")
        assert meta2.hashtags == []

    def test_video_path_is_pathlib_path(self):
        meta = ReelMetadata(
            source_url="https://example.com/reel",
            platform="instagram",
            author=None,
            posted_at=None,
            title=None,
            caption=None,
            video_path=Path("/downloads/clip.mp4"),
        )
        assert isinstance(meta.video_path, Path)

    def test_posted_at_accepts_none(self):
        meta = ReelMetadata(
            source_url="https://example.com/reel",
            platform="tiktok",
            author=None,
            posted_at=None,
            title=None,
            caption=None,
            video_path=Path("/tmp/v.mp4"),
        )
        assert meta.posted_at is None

    def test_posted_at_accepts_datetime(self):
        dt = datetime(2025, 1, 20, 9, 30)
        meta = ReelMetadata(
            source_url="https://example.com/reel",
            platform="youtube",
            author="channelname",
            posted_at=dt,
            title="My vlog",
            caption=None,
            video_path=Path("/tmp/v.mp4"),
        )
        assert meta.posted_at == dt
        assert isinstance(meta.posted_at, datetime)


class TestItem:
    def test_instantiation_with_representative_values(self):
        item = Item(
            name="Blue Bottle Coffee",
            item_type="restaurant",
            description="Specialty coffee shop known for pour-overs.",
        )
        assert item.name == "Blue Bottle Coffee"
        assert item.item_type == "restaurant"
        assert item.description == "Specialty coffee shop known for pour-overs."

    def test_all_item_types(self):
        for item_type in ("place", "restaurant", "activity", "tip"):
            item = Item(name="X", item_type=item_type, description="desc")
            assert item.item_type == item_type


class TestExtractionResult:
    def test_instantiation_with_all_fields(self):
        items = [Item(name="Tartine", item_type="restaurant", description="Famous bakery.")]
        result = ExtractionResult(
            transcription="Check out this amazing bakery.",
            ocr_text="TARTINE BAKERY",
            summary="A visit to a famous San Francisco bakery.",
            items=items,
        )
        assert result.transcription == "Check out this amazing bakery."
        assert result.ocr_text == "TARTINE BAKERY"
        assert result.summary == "A visit to a famous San Francisco bakery."
        assert len(result.items) == 1
        assert isinstance(result.items[0], Item)

    def test_items_defaults_to_empty_list(self):
        result = ExtractionResult(
            transcription="Some spoken words.",
            ocr_text="",
            summary="A short summary.",
        )
        assert result.items == []

    def test_items_is_list_of_item(self):
        item = Item(name="Dolores Park", item_type="place", description="Popular park in SF.")
        result = ExtractionResult(
            transcription="Visit Dolores Park.",
            ocr_text="DOLORES PARK",
            summary="Park recommendation.",
            items=[item],
        )
        assert isinstance(result.items, list)
        assert all(isinstance(i, Item) for i in result.items)

    def test_items_default_is_not_shared(self):
        r1 = ExtractionResult(transcription="a", ocr_text="", summary="s")
        r2 = ExtractionResult(transcription="b", ocr_text="", summary="s")
        r1.items.append(Item(name="X", item_type="tip", description="tip"))
        assert r2.items == []
