"""Content-free resident voice status for an optional Omarchy indicator.

The projection is a tiny JSON object. It carries state, microphone words,
instance generation, and a timestamp. It never carries a transcript, prompt,
path, window title, selection, credential, or raw error. A missing, stale,
malformed, or oversized read is unknown or unavailable. Neither of those
outcomes is evidence that the microphone is off.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from scribe.paths import state_dir

SCHEMA_VERSION = 1
MAX_BYTES = 512
MAX_AGE_SECONDS = 5.0
MAX_FUTURE_SKEW_SECONDS = 2.0
JS_MAX_SAFE_INTEGER = 9_007_199_254_740_991
PROJECTION_NAME = "voice-projection.json"

STATES = frozenset(
    {"idle", "recording", "processing", "speaking", "error", "unknown", "unavailable"}
)
MICROPHONES = frozenset({"on", "off", "unknown"})
ALLOWED_PAIRS = frozenset(
    {
        ("idle", "off"),
        ("recording", "on"),
        ("processing", "off"),
        ("processing", "on"),
        ("speaking", "off"),
        ("speaking", "on"),
        ("error", "on"),
        ("error", "unknown"),
        ("unknown", "unknown"),
        ("unavailable", "on"),
        ("unavailable", "unknown"),
    }
)
FIELDS = frozenset({"schema_version", "state", "microphone", "generation", "updated_at"})

Outcome = Literal["current", "unknown", "unavailable"]


@dataclass(frozen=True)
class StatusView:
    """What an indicator may display after one read."""

    outcome: Outcome
    state: str
    microphone: str
    label: str
    generation: int | None


@dataclass(frozen=True)
class SeenProjection:
    """The last accepted generation, used only to reject out-of-order writes."""

    generation: int
    updated_at: float


def projection_path(home: Path | None = None) -> Path:
    """Return the owner-published projection file."""
    return state_dir(home) / PROJECTION_NAME


def new_generation(now: float | None = None) -> int:
    """Return a new owner generation that stays inside a JavaScript safe integer."""
    millis = int((time.time() if now is None else now) * 1000)
    return (millis << 10) + secrets.randbits(10)


def validate_generation(generation: int) -> None:
    if isinstance(generation, bool) or not isinstance(generation, int):
        raise ValueError("status generation must be an integer")
    if generation < 1 or generation > JS_MAX_SAFE_INTEGER:
        raise ValueError("status generation is outside the safe integer range")


def fields_from_owner(service_state: str, *, stream_open: bool) -> tuple[str, str]:
    """Map resident voice state to a projection pair.

    An open stream is microphone on, including when the state is an error or
    the owner is stopping. A closed stream during an error is unknown, not off.
    """
    if service_state == "stopped":
        return ("unavailable", "on" if stream_open else "unknown")
    if service_state == "error":
        return ("error", "on" if stream_open else "unknown")
    if service_state == "recording" or stream_open:
        if service_state == "transcribing":
            return ("processing", "on")
        if service_state == "speaking":
            return ("speaking", "on")
        return ("recording", "on")
    if service_state == "transcribing":
        return ("processing", "off")
    if service_state == "speaking":
        return ("speaking", "off")
    if service_state == "idle":
        return ("idle", "off")
    return ("unknown", "unknown")


def microphone_label(microphone: str) -> str:
    """Words for the microphone. Color is never the only signal."""
    if microphone == "on":
        return "MICROPHONE ON"
    if microphone == "off":
        return "microphone off"
    return "microphone unknown"


def _unknown() -> StatusView:
    return StatusView("unknown", "unknown", "unknown", "microphone unknown", None)


def _unavailable() -> StatusView:
    return StatusView("unavailable", "unavailable", "unknown", "microphone unknown", None)


def write_projection(
    path: Path,
    *,
    state: str,
    microphone: str,
    generation: int,
    updated_at: float | None = None,
) -> None:
    """Atomically publish one allowlisted projection."""
    validate_generation(generation)
    if (state, microphone) not in ALLOWED_PAIRS:
        raise ValueError(f"refusing status pair {(state, microphone)}")
    stamp = time.time() if updated_at is None else updated_at
    if isinstance(stamp, bool) or not isinstance(stamp, int | float):
        raise ValueError("updated_at must be a number")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "microphone": microphone,
        "generation": generation,
        "updated_at": stamp,
    }
    if set(payload) != FIELDS:
        raise ValueError("projection fields drifted from the allowlist")
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(body) > MAX_BYTES:
        raise ValueError("projection exceeds the size limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(body)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def interpret(
    payload: bytes,
    *,
    now: float,
    seen: SeenProjection | None,
) -> tuple[StatusView, SeenProjection | None]:
    """Parse one payload. Failure does not return the previous owner's state."""
    if len(payload) > MAX_BYTES:
        return _unknown(), seen
    try:
        parsed = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _unknown(), seen
    if not isinstance(parsed, dict) or set(parsed) != FIELDS:
        return _unknown(), seen
    if parsed["schema_version"] != SCHEMA_VERSION:
        return _unknown(), seen
    state = parsed["state"]
    microphone = parsed["microphone"]
    generation = parsed["generation"]
    updated_at = parsed["updated_at"]
    if not isinstance(state, str) or not isinstance(microphone, str):
        return _unknown(), seen
    if (state, microphone) not in ALLOWED_PAIRS:
        return _unknown(), seen
    if isinstance(generation, bool) or not isinstance(generation, int):
        return _unknown(), seen
    if generation < 1 or generation > JS_MAX_SAFE_INTEGER:
        return _unknown(), seen
    if isinstance(updated_at, bool) or not isinstance(updated_at, int | float):
        return _unknown(), seen
    updated = float(updated_at)
    age = now - updated
    if age > MAX_AGE_SECONDS or age < -MAX_FUTURE_SKEW_SECONDS:
        return _unknown(), seen
    if seen is not None and generation < seen.generation:
        return _unknown(), seen
    if seen is not None and updated < seen.updated_at and generation != seen.generation:
        return _unknown(), seen
    if seen is not None and generation == seen.generation and updated < seen.updated_at:
        return _unknown(), seen
    view = StatusView("current", state, microphone, microphone_label(microphone), generation)
    return view, SeenProjection(generation, updated)


def read_projection(
    path: Path,
    *,
    now: float | None = None,
    seen: SeenProjection | None = None,
) -> tuple[StatusView, SeenProjection | None]:
    """Read one projection. A missing file means no owner, not microphone off."""
    current = time.time() if now is None else now
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return _unavailable(), seen
    except OSError:
        return _unknown(), seen
    return interpret(payload, now=current, seen=seen)
