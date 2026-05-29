"""Integration test: the media (fal.ai) service, in isolation.

Covers the generic generate() + auto-extract pattern across modalities:
  - upload a local file (cheap, no model runs)
  - text -> image (cheap flux/schnell), and the same with persist -> R2
  - text -> speech (returns an audio file)
  - speech -> text (returns a transcript string, no files)

    uv run pytest -m integration scripts/tests/test_media_service.py

Skips automatically if FAL_KEY isn't set. The persist test also needs R2.
"""

import pytest

from agent.config import get_settings

CHEAP_IMAGE_MODEL = "fal-ai/flux/schnell"  # fast & cheap, for tests
# A short public sample clip from fal's whisper docs.
SAMPLE_AUDIO = (
    "https://storage.googleapis.com/falserverless/model_tests/whisper/dinner_conversation.mp3"
)


def _fal_ready() -> bool:
    try:
        return bool(get_settings().fal_key)
    except Exception:
        return False


def _r2_ready() -> bool:
    try:
        s = get_settings()
    except Exception:
        return False
    return bool(s.r2_account_id and s.r2_access_key_id and s.r2_secret_access_key and s.r2_bucket)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _fal_ready(), reason="FAL_KEY not set in .env"),
]


async def test_upload_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from agent.services import media

    local = tmp_path / "note.txt"
    local.write_text("hello fal")
    url = await media.upload_file(local)
    assert url.startswith("http")


async def test_text_to_image() -> None:
    from agent.services import media

    result = await media.text_to_image("a single red dot on white", model=CHEAP_IMAGE_MODEL)
    assert result.files
    assert result.files[0].url.startswith("http")


async def test_text_to_speech() -> None:
    from agent.services import media

    result = await media.text_to_speech("Hello, this is a short test.")
    assert result.files
    assert result.files[0].url.startswith("http")


async def test_speech_to_text() -> None:
    from agent.services import media

    transcript = await media.speech_to_text(SAMPLE_AUDIO)
    assert transcript.strip()  # got a non-empty transcription


@pytest.mark.skipif(not _r2_ready(), reason="R2 not configured (needed to persist)")
async def test_text_to_image_persisted_to_r2() -> None:
    from agent.services import media, storage

    result = await media.text_to_image(
        "a single blue dot on white", model=CHEAP_IMAGE_MODEL, persist=True, prefix="_tests"
    )
    file = result.files[0]
    assert file.stored_key is not None and file.stored_key.startswith("_tests/")
    assert file.url.startswith("http")
    # clean up the object we just stored
    await storage.delete_key(file.stored_key)
