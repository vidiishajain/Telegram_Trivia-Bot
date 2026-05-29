"""Media models (image, audio, video, 3d, speech-to-text, ...), via fal.ai.

fal hosts thousands of models with *different* input and output shapes. Rather
than hand-writing a wrapper per model, we lean on two facts:

  1. You drive any model with `generate(model_id, inputs)`.
  2. fal's outputs follow a few conventions ({"images":[{"url"}]}, {"audio":{"url"}},
     {"text": "..."}, ...), so one extractor normalizes them into `MediaResult`.

So **adding a model is usually zero new code** — just call `generate()` with its
inputs. To find a model's inputs/outputs, read its machine-readable spec at:

    https://fal.ai/models/<model-id>/llms.txt      (great for Claude to look up)

Common modalities have thin named helpers (text_to_image, text_to_speech,
speech_to_text). For an exotic output shape, pass your own `extract=` function to
`generate()`, or read `result.raw`.

Set `persist=True` to copy generated files into your R2 bucket (UUID key) and get
back durable URLs — fal's own URLs are temporary.

Client docs: https://fal.ai/docs/clients/python
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import fal_client
from pydantic import BaseModel, Field

from agent.config import get_settings

# Default models per modality — swap here and every helper follows.
IMAGE_MODEL = "fal-ai/nano-banana-2"
TTS_MODEL = "fal-ai/gemini-3.1-flash-tts"
STT_MODEL = "fal-ai/whisper"

# Output keys fal commonly uses for files vs. text.
_FILE_KEYS = ("images", "image", "audio", "video", "files", "file")
_TEXT_KEYS = ("text", "transcription", "transcript", "output")


class MediaFile(BaseModel):
    """One output file from a model."""

    url: str  # fal-hosted (temporary) — or your R2 URL once persisted
    content_type: str | None = None
    stored_key: str | None = None  # set when the file was uploaded to your bucket


class MediaResult(BaseModel):
    """A normalized result that fits any modality."""

    text: str | None = None  # for stt / captions / descriptions (nothing to upload)
    files: list[MediaFile] = Field(default_factory=list)  # image / audio / video / 3d
    raw: dict[str, Any] = Field(default_factory=dict)  # full fal response, for the exotic cases


def _ensure_key() -> None:
    if not get_settings().fal_key:
        raise RuntimeError("FAL_KEY is not set. Add it to your .env to use fal models.")


async def run(application: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run any fal model and wait for the raw result dict. The lowest-level call."""
    _ensure_key()
    return await fal_client.subscribe_async(application, arguments=arguments)


def _files_from(value: Any) -> list[MediaFile]:
    items = value if isinstance(value, list) else [value]
    files: list[MediaFile] = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("url"), str):
            files.append(MediaFile(url=item["url"], content_type=item.get("content_type")))
    return files


def extract(raw: dict[str, Any]) -> MediaResult:
    """Normalize a fal response into a MediaResult using common output conventions."""
    files: list[MediaFile] = []
    for key in _FILE_KEYS:
        if key in raw:
            files.extend(_files_from(raw[key]))
    text: str | None = None
    for key in _TEXT_KEYS:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            text = value
            break
    return MediaResult(text=text, files=files, raw=raw)


def _suffix_for(file: MediaFile) -> str:
    """Best-guess file extension from the URL (e.g. '.png', '.mp3')."""
    path = file.url.split("?", 1)[0]
    dot = path.rfind(".")
    return path[dot:] if dot > path.rfind("/") else ""


async def _persist(file: MediaFile, prefix: str) -> MediaFile:
    """Download a generated file and re-upload it to R2, returning durable info."""
    import httpx  # local import; persisting is the only thing that needs it

    from agent.services import storage  # media depends on storage only when persisting

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(file.url)
        response.raise_for_status()

    key = await storage.store_bytes(
        response.content, suffix=_suffix_for(file), prefix=prefix, content_type=file.content_type
    )
    url = (
        storage.public_url(key)
        if get_settings().r2_public_base_url
        else await storage.presigned_url(key)
    )
    return MediaFile(url=url, content_type=file.content_type, stored_key=key)


async def generate(
    model: str,
    inputs: dict[str, Any],
    *,
    persist: bool = False,
    prefix: str = "",
    extract_fn: Callable[[dict[str, Any]], MediaResult] = extract,
) -> MediaResult:
    """Run a fal model and return a normalized MediaResult.

    Set `persist=True` to copy any output files into your R2 bucket (under `prefix`)
    and rewrite their URLs to durable ones. Pass `extract_fn` only for models whose
    output shape the default extractor doesn't understand.
    """
    raw = await run(model, inputs)
    result = extract_fn(raw)
    if persist and result.files:
        result.files = [await _persist(file, prefix) for file in result.files]
    return result


# --- Named helpers for the common modalities (thin sugar over generate) ------


async def text_to_image(
    prompt: str,
    *,
    model: str = IMAGE_MODEL,
    persist: bool = False,
    prefix: str = "",
    **arguments: Any,
) -> MediaResult:
    """Generate image(s) from text. result.files[0].url is your image."""
    return await generate(model, {"prompt": prompt, **arguments}, persist=persist, prefix=prefix)


async def text_to_speech(
    prompt: str,
    *,
    model: str = TTS_MODEL,
    persist: bool = False,
    prefix: str = "",
    **arguments: Any,
) -> MediaResult:
    """Speak text aloud. result.files[0].url is your audio. Supports cues like [sigh]."""
    return await generate(model, {"prompt": prompt, **arguments}, persist=persist, prefix=prefix)


async def speech_to_text(audio_url: str, *, model: str = STT_MODEL, **arguments: Any) -> str:
    """Transcribe audio to text. Returns the transcript string."""
    result = await generate(model, {"audio_url": audio_url, **arguments})
    return result.text or ""


async def upload_file(path: str | Path) -> str:
    """Upload a local file to fal and return a URL usable as model input."""
    _ensure_key()
    return await fal_client.upload_file_async(Path(path))
