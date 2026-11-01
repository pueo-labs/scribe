"""The optional Omarchy indicator stays a read-only renderer."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "packaging" / "linux" / "omarchy" / "scribe-voice-indicator"
FORBIDDEN = (
    "Process",
    "sounddevice",
    "wtype",
    "notify-send",
    "omarchy-notification",
    "scribe voice",
    "transcript",
    "api_key",
    "pynput",
    "openai",
)


def test_plugin_manifest_is_a_separate_read_only_widget():
    manifest = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "org.pueolabs.scribe-voice"
    assert manifest["kinds"] == ["bar-widget"]
    assert "record" not in manifest["description"].lower()
    source = (PLUGIN / "BarWidget.qml").read_text(encoding="utf-8")
    for token in FORBIDDEN:
        assert token not in source
    assert "MICROPHONE ON" in source
    assert "microphone unknown" in source
    assert "voice-projection.json" in source
    assert "voice-status.txt" not in source
    assert "blockLoading: false" in source
    assert "blockAllReads: false" in source
    assert "barForeground" in source
    assert "Color.foreground" in source
    assert "Color.urgent" in source
    assert "NumberAnimation" not in source
    assert "Behavior on" not in source
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    assert "does not stop the voice owner" in readme
    assert "not a tested" in readme


def test_main_install_does_not_enable_the_indicator():
    script = (ROOT / "packaging" / "linux" / "omarchy" / "install.sh").read_text(encoding="utf-8")
    assert "scribe-voice-indicator" not in script
    assert "org.pueolabs.scribe-voice" not in script
