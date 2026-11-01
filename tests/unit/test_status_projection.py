"""Content-free voice projection contract."""

import json
from pathlib import Path

from rich.console import Console

from scribe.voice.service import VoiceTrayService
from scribe.voice.settings import TraySettings
from scribe.voice.status_projection import (
    SeenProjection,
    fields_from_owner,
    interpret,
    new_generation,
    projection_path,
    read_projection,
    write_projection,
)


def _payload(**overrides: object) -> bytes:
    body = {
        "schema_version": 1,
        "state": "idle",
        "microphone": "off",
        "generation": 10,
        "updated_at": 1_000.0,
    }
    body.update(overrides)
    return json.dumps(body).encode()


def test_recording_is_microphone_on_in_words():
    view, seen = interpret(_payload(state="recording", microphone="on"), now=1_001.0, seen=None)
    assert view.label == "MICROPHONE ON"
    assert view.outcome == "current"
    assert seen is not None and seen.generation == 10


def test_failure_never_reports_the_microphone_off(tmp_path: Path):
    missing, _ = read_projection(tmp_path / "absent.json", now=1_000.0)
    assert missing.outcome == "unavailable"
    assert missing.label == "microphone unknown"
    assert missing.microphone != "off"

    stale, _ = interpret(_payload(), now=1_006.0, seen=None)
    assert stale.label == "microphone unknown"

    huge, _ = interpret(b'{"schema_version":1}' + b"x" * 600, now=1_000.0, seen=None)
    assert huge.outcome == "unknown"

    leaked = _payload(transcript="secret words", path="/home/pueo/private")
    rejected, _ = interpret(leaked, now=1_001.0, seen=None)
    assert rejected.outcome == "unknown"
    assert "secret" not in rejected.label


def test_older_generation_is_not_shown_as_current():
    seen = SeenProjection(generation=8, updated_at=1_000.0)
    view, still = interpret(
        _payload(generation=7, updated_at=1_001.0, state="recording", microphone="on"),
        now=1_001.5,
        seen=seen,
    )
    assert view.outcome == "unknown"
    assert view.microphone != "off"
    assert still == seen


def test_previous_owner_is_not_shown_as_current():
    seen = SeenProjection(generation=3, updated_at=1_000.0)
    view, still = interpret(
        _payload(generation=4, updated_at=999.0, state="recording", microphone="on"),
        now=999.5,
        seen=seen,
    )
    assert view.outcome == "unknown"
    assert view.label == "microphone unknown"
    assert still == seen


def test_owner_projection_excludes_transcript_and_errors(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    service = VoiceTrayService(TraySettings(), Console())
    service.last_transcript = "secret transcript"
    service.error_message = "secret error /home/pueo/key"
    service.state = "idle"
    service.enable_status_projection(1_700_000_000_001)
    text = projection_path().read_text(encoding="utf-8")
    assert "secret" not in text
    assert "transcript" not in text
    assert "key" not in text
    assert "microphone" in text


def test_open_stream_is_not_described_as_off():
    assert fields_from_owner("error", stream_open=True) == ("error", "on")
    assert fields_from_owner("error", stream_open=False) == ("error", "unknown")
    assert fields_from_owner("idle", stream_open=False) == ("idle", "off")
    assert fields_from_owner("transcribing", stream_open=False) == ("processing", "off")


def test_generation_fits_in_a_javascript_safe_integer():
    assert 1 <= new_generation(1_700_000_000.0) <= 9_007_199_254_740_991


def test_projection_write_failure_stays_inside_the_owner(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    service = VoiceTrayService(TraySettings(), Console())
    service._status_generation = 1

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise ValueError("refusing status pair")

    monkeypatch.setattr("scribe.voice.status_projection.write_projection", refuse)
    service.publish_status_projection()


def test_writer_rejects_a_transcript_shaped_pair(tmp_path: Path):
    path = tmp_path / "voice-projection.json"
    write_projection(path, state="speaking", microphone="off", generation=4, updated_at=10.0)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw) == {"schema_version", "state", "microphone", "generation", "updated_at"}
    assert path.stat().st_mode & 0o777 == 0o600
