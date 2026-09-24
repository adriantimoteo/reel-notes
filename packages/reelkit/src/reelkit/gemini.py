"""Gemini multimodal structured extraction: upload a reel's media, prompt with a
JSON schema, get a dict back. The prompt and schema belong to the caller."""

import json
import logging
import time
from pathlib import Path

import google.genai as genai
from google.genai import errors as genai_errors

from reelkit.exceptions import ExtractionError
from reelkit.models import ReelMetadata
from reelkit.retry import call_with_retry

logger = logging.getLogger(__name__)

MAX_POLL_ATTEMPTS = 30  # 60 seconds total at 2s intervals
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 5.0


def is_retryable_error(e: Exception) -> bool:
    """Retry Gemini 5xx errors and 429 rate limits; other 4xx errors are permanent."""
    if isinstance(e, genai_errors.ServerError):
        return True
    if isinstance(e, genai_errors.ClientError) and getattr(e, "code", None) == 429:
        return True
    return False


def is_model_retired(e: Exception) -> bool:
    """A 404 from Gemini means the configured model name no longer exists."""
    return isinstance(e, genai_errors.ClientError) and getattr(e, "code", None) == 404


def is_carousel(metadata: ReelMetadata) -> bool:
    return bool(metadata.image_paths)


def media_paths(metadata: ReelMetadata) -> list[Path]:
    """Files to upload, in prompt order: slides then optional audio for a photo
    post, otherwise the single video."""
    if is_carousel(metadata):
        paths = [*metadata.image_paths]
        if metadata.audio_path is not None:
            paths.append(metadata.audio_path)
        return paths
    return [metadata.video_path]


def _upload_and_wait(client: genai.Client, path: Path):
    file = client.files.upload(file=path)
    attempts = 0
    while file.state.name == "PROCESSING" and attempts < MAX_POLL_ATTEMPTS:
        time.sleep(2)
        file = client.files.get(name=file.name)
        attempts += 1

    if file.state.name != "ACTIVE":
        raise ExtractionError(
            cause=RuntimeError(f"Gemini file in unexpected state: {file.state.name}")
        )
    return file


def _generate_structured_sync(
    client: genai.Client, model: str, paths: list[Path], prompt: str, schema: dict
) -> dict:
    uploaded_files = [_upload_and_wait(client, path) for path in paths]
    response = client.models.generate_content(
        model=model,
        contents=[*uploaded_files, prompt],
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    return json.loads(response.text)


async def generate_structured(
    client: genai.Client,
    model: str,
    paths: list[Path],
    prompt: str,
    schema: dict,
    *,
    description: str,
) -> dict:
    """Uploads `paths`, sends them with `prompt`, and returns the JSON response
    parsed as a dict. Transient Gemini failures (5xx, 429) are retried."""
    return await call_with_retry(
        lambda: _generate_structured_sync(client, model, paths, prompt, schema),
        attempts=RETRY_ATTEMPTS,
        base_delay=RETRY_BASE_DELAY,
        is_retryable=is_retryable_error,
        description=description,
    )
