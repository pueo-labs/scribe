# Scribe voice indicator

Optional Omarchy bar widget. It reads one content-free status file published by
the resident `scribe voice serve` owner:

`$XDG_STATE_HOME/scribe/voice-projection.json`

The file may contain only a schema version, a state, a microphone value,
a generation, and a timestamp. The widget shows `MICROPHONE ON`,
`microphone off`, or `microphone unknown`. A missing owner, a stale file, a
failed read, or a malformed file is unknown or unavailable. Those outcomes do
not mean the microphone is off.

This widget does not start Scribe, open a microphone, load a model, dictate,
paste, read aloud, or call a provider. It runs with the user's Quickshell
authority. Registry validation is not a security review.

The main Omarchy install script does not copy or enable this widget. To try it
from a checkout:

```bash
omarchy plugin validate packaging/linux/omarchy/scribe-voice-indicator
mkdir -p ~/.config/omarchy/plugins/org.pueolabs.scribe-voice
cp -a packaging/linux/omarchy/scribe-voice-indicator/. \
  ~/.config/omarchy/plugins/org.pueolabs.scribe-voice/
omarchy plugin enable org.pueolabs.scribe-voice
```

Remove only the plugin directory. That does not stop the voice owner, change
hotkeys, or delete Scribe's state files. A visible indicator is not a tested
microphone, focus, or recovery record.
