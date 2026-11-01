"""OpenAI model ids Scribe will send, and the shutdown dates that constrain them.

Dates were checked against https://developers.openai.com/api/docs/deprecations
on 2026-10-31. A scheduled id stays available as an explicit override until its
shutdown date. A retired id is refused. Local Whisper is unaffected.

``gpt-transcribe`` is the file-transcription default. It does not return
speaker labels. ``gpt-4o-transcribe-diarize`` still does, until 2027-02-26.
``gpt-live-transcribe`` is the live-audio replacement and is not the file default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

TRANSCRIBE_MODEL = "gpt-transcribe"
VISION_MODEL = "gpt-6-luna"
IMAGE_MODEL = "gpt-image-2"

# Chat and image ids that belong to OpenAI. Passing one through to another
# provider selects that provider's catalog default instead.
FACTORY_IGNORED_MODELS = frozenset(
    {
        "",
        "dall-e-3",
        "gpt-4",
        "gpt-4-0613",
        "gpt-4-turbo",
        "gpt-4o",
        "gpt-4o-2024-08-06",
        "gpt-4o-2024-11-20",
        "gpt-4o-mini-transcribe",
        "gpt-4o-mini-transcribe-2025-03-20",
        "gpt-4o-transcribe",
        "gpt-4o-transcribe-diarize",
        "gpt-5",
        "gpt-5.2",
        "gpt-5.4",
        "gpt-5.5",
        "gpt-5.6-sol",
        "gpt-6-luna",
        "gpt-image-1",
        "gpt-image-2",
        "gpt-live-transcribe",
        "gpt-transcribe",
        "whisper-1",
    }
)

_FILE_TRANSCRIPTION_MODELS = frozenset({"gpt-transcribe", "gpt-live-transcribe"})

_SCHEDULED: dict[str, tuple[date, str]] = {
    "gpt-4o": (date(2027, 1, 14), VISION_MODEL),
    "gpt-4o-2024-08-06": (date(2027, 1, 14), VISION_MODEL),
    "gpt-4o-2024-11-20": (date(2027, 1, 14), VISION_MODEL),
    "whisper-1": (date(2027, 2, 26), TRANSCRIBE_MODEL),
    "gpt-4o-transcribe": (date(2027, 2, 26), TRANSCRIBE_MODEL),
    "gpt-4o-mini-transcribe": (date(2027, 2, 26), TRANSCRIBE_MODEL),
    "gpt-4o-mini-transcribe-2025-03-20": (date(2027, 1, 20), TRANSCRIBE_MODEL),
    "gpt-4o-transcribe-diarize": (date(2027, 2, 26), TRANSCRIBE_MODEL),
}

_RETIRED: dict[str, tuple[date, str]] = {
    "gpt-4": (date(2026, 10, 23), "gpt-5.6-sol"),
    "gpt-4-0613": (date(2026, 10, 23), "gpt-5.6-sol"),
    "gpt-4-turbo": (date(2026, 10, 23), "gpt-5.6-sol"),
    "dall-e-3": (date(2026, 5, 12), IMAGE_MODEL),
    "gpt-image-1": (date(2026, 10, 23), IMAGE_MODEL),
}

_warned: set[str] = set()


class RetiredModelError(ValueError):
    """The requested OpenAI model has already shut down."""

    def __init__(self, model: str, replacement: str, shutdown: date) -> None:
        self.model = model
        self.replacement = replacement
        self.shutdown = shutdown
        super().__init__(
            f"OpenAI model {model} shut down on {shutdown.isoformat()}. Use {replacement}."
        )


@dataclass(frozen=True)
class ModelNotice:
    """One scheduled or retired model, with the replacement Scribe will name."""

    model: str
    shutdown: date
    replacement: str
    retired: bool

    @property
    def message(self) -> str:
        when = self.shutdown.isoformat()
        if self.retired:
            return f"OpenAI model {self.model} shut down on {when}. Use {self.replacement}."
        return (
            f"OpenAI model {self.model} shuts down on {when}. "
            f"It remains an explicit override until then. Replacement: {self.replacement}."
        )


def catalog_model_or_none(model: str | None) -> str | None:
    """Drop an OpenAI id so the provider factory can choose its own default."""
    if model is None or model in FACTORY_IGNORED_MODELS:
        return None
    return model


def local_notice(model: str, *, today: date | None = None) -> ModelNotice | None:
    """Return the curated shutdown record for an exact model id."""
    current = today or date.today()
    retired = _RETIRED.get(model)
    if retired is not None:
        shutdown, replacement = retired
        return ModelNotice(model, shutdown, replacement, current >= shutdown)
    scheduled = _SCHEDULED.get(model)
    if scheduled is None:
        return None
    shutdown, replacement = scheduled
    return ModelNotice(model, shutdown, replacement, current >= shutdown)


def ensure_usable(model: str, *, today: date | None = None) -> ModelNotice | None:
    """Refuse a shut-down model and warn once for one that is still an override."""
    notice = local_notice(model, today=today)
    if notice is None:
        return None
    if notice.retired:
        raise RetiredModelError(notice.model, notice.replacement, notice.shutdown)
    if model not in _warned:
        _warned.add(model)
        logger.warning("%s", notice.message)
    return notice


def audio_transcription_fields(
    model: str,
    *,
    language: str | None,
    prompt: str | None,
    include_chunking: bool,
) -> dict[str, Any]:
    """Arguments for ``audio.transcriptions`` besides the file and model.

    ``gpt-transcribe`` takes ``languages`` and rejects a sibling ``language``
    field. The deprecated diarize model takes ``diarized_json`` and no prompt.
    """
    ensure_usable(model)
    if "diarize" in model:
        fields: dict[str, Any] = {"response_format": "diarized_json"}
        if include_chunking:
            fields["chunking_strategy"] = "auto"
        if language:
            fields["language"] = language
        return fields
    if model in _FILE_TRANSCRIPTION_MODELS:
        fields = {}
        if language:
            fields["languages"] = [language]
        if prompt:
            fields["prompt"] = prompt
        return fields
    fields = {"response_format": "text"}
    if language:
        fields["language"] = language
    if prompt:
        fields["prompt"] = prompt
    return fields


def _record_value(record: object, name: str) -> object:
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def _parse_shutdown(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def remote_shutdown(page: object, model: str) -> date | None:
    """Read ``shutdown_date`` for ``model`` from a ``GET /v1/models`` page.

    A mock or an unexpected payload has no usable date and returns None.
    """
    data = page if isinstance(page, list) else _record_value(page, "data")
    if not isinstance(data, list):
        return None
    for record in data:
        record_id = _record_value(record, "id")
        if record_id != model:
            continue
        return _parse_shutdown(_record_value(record, "shutdown_date"))
    return None


def notice_for_configured_model(
    model: str,
    page: object | None = None,
    *,
    today: date | None = None,
) -> ModelNotice | None:
    """Prefer a live ``shutdown_date`` and fall back to the curated table."""
    current = today or date.today()
    remote = remote_shutdown(page, model) if page is not None else None
    curated = local_notice(model, today=current)
    if remote is None:
        return curated
    replacement = curated.replacement if curated is not None else "a current OpenAI model"
    shutdown = remote
    retired = current >= remote
    if curated is not None:
        if curated.shutdown < shutdown:
            shutdown = curated.shutdown
        retired = retired or current >= curated.shutdown
    return ModelNotice(model, shutdown, replacement, retired)
