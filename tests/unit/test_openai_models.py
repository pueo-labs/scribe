"""OpenAI model lifecycle and file-transcription request shape."""

from datetime import date
from types import SimpleNamespace

import pytest

from scribe.providers.openai_models import (
    TRANSCRIBE_MODEL,
    VISION_MODEL,
    RetiredModelError,
    audio_transcription_fields,
    catalog_model_or_none,
    ensure_usable,
    notice_for_configured_model,
)


def test_file_default_uses_languages_and_not_the_singular_field():
    fields = audio_transcription_fields(
        TRANSCRIBE_MODEL,
        language="es",
        prompt="names",
        include_chunking=False,
    )
    assert fields == {"languages": ["es"], "prompt": "names"}
    assert "language" not in fields
    assert "response_format" not in fields


def test_diarize_override_keeps_speaker_json_until_shutdown():
    fields = audio_transcription_fields(
        "gpt-4o-transcribe-diarize",
        language="es",
        prompt="ignored",
        include_chunking=True,
    )
    assert fields["response_format"] == "diarized_json"
    assert fields["chunking_strategy"] == "auto"
    assert fields["language"] == "es"
    assert "prompt" not in fields


def test_retired_model_names_its_replacement():
    with pytest.raises(RetiredModelError, match="gpt-image-2") as caught:
        ensure_usable("dall-e-3", today=date(2026, 10, 31))
    assert caught.value.replacement == "gpt-image-2"


def test_scheduled_model_remains_usable_before_shutdown():
    notice = ensure_usable("whisper-1", today=date(2026, 10, 31))
    assert notice is not None
    assert notice.retired is False
    assert notice.replacement == TRANSCRIBE_MODEL


def test_scheduled_model_is_refused_on_its_shutdown_date():
    with pytest.raises(RetiredModelError, match="gpt-transcribe"):
        ensure_usable("gpt-4o-transcribe-diarize", today=date(2027, 2, 26))


def test_live_shutdown_date_overrides_a_missing_table_entry():
    page = SimpleNamespace(data=[SimpleNamespace(id="custom-speech", shutdown_date="2026-11-02")])
    notice = notice_for_configured_model("custom-speech", page, today=date(2026, 10, 31))
    assert notice is not None
    assert notice.retired is False
    assert notice.shutdown == date(2026, 11, 2)


def test_live_date_cannot_revive_a_retired_model():
    page = SimpleNamespace(data=[SimpleNamespace(id="dall-e-3", shutdown_date="2027-01-01")])
    notice = notice_for_configured_model("dall-e-3", page, today=date(2026, 10, 31))
    assert notice is not None
    assert notice.retired is True
    assert notice.replacement == "gpt-image-2"


def test_mock_model_page_does_not_invent_a_shutdown():
    assert notice_for_configured_model(TRANSCRIBE_MODEL, object(), today=date(2026, 10, 31)) is None


def test_config_default_matches_the_file_model():
    from scribe.models.config import ScribeConfig

    assert ScribeConfig.model_fields["openai_model"].default == TRANSCRIBE_MODEL


def test_openai_ids_are_not_forwarded_to_another_provider():
    assert catalog_model_or_none("gpt-4") is None
    assert catalog_model_or_none("gpt-4-turbo") is None
    assert catalog_model_or_none("gpt-4o") is None
    assert catalog_model_or_none("gpt-5.6-sol") is None
    assert catalog_model_or_none(VISION_MODEL) is None
    assert catalog_model_or_none("a-local-model") == "a-local-model"
