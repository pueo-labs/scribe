import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Read-only view of the resident owner's content-free projection.
// This file must not start a process, open audio, or display captured speech.
// The Python contract is src/scribe/voice/status_projection.py.
BarWidget {
  id: root
  moduleName: "org.pueolabs.scribe-voice"

  readonly property int maxBytes: 512
  readonly property real maxAgeMs: 5000
  readonly property real maxFutureMs: 2000
  readonly property string projectionPath: {
    var stateHome = String(Quickshell.env("XDG_STATE_HOME") || "")
    if (stateHome.length === 0 || stateHome.charAt(0) !== "/")
      stateHome = String(Quickshell.env("HOME") || "") + "/.local/state"
    return stateHome + "/scribe/voice-projection.json"
  }

  property string outcome: "unavailable"
  property string stateName: "unavailable"
  property string microphone: "unknown"
  property string label: "microphone unknown"
  property var seenGeneration: null
  property real seenUpdated: 0

  // Theme colors follow the bar. The words stay the proof, so a theme swap
  // cannot be the only signal that the microphone is on. There is no
  // animation: a reduced-motion theme has nothing to suppress.
  readonly property color quietText: bar && bar.barForeground.a > 0
    ? bar.barForeground : Commons.Color.foreground
  readonly property color liveFill: bar && bar.urgent.a > 0
    ? bar.urgent : Commons.Color.urgent

  implicitWidth: caption.implicitWidth + 16
  implicitHeight: vertical ? caption.implicitHeight + 8 : barSize

  function markUnknown() {
    outcome = "unknown"
    stateName = "unknown"
    microphone = "unknown"
    label = "microphone unknown"
  }

  function markUnavailable() {
    outcome = "unavailable"
    stateName = "unavailable"
    microphone = "unknown"
    label = "microphone unknown"
  }

  function allowedPair(state, microphone) {
    if (state === "recording" && microphone === "on") return true
    if (state === "idle" && microphone === "off") return true
    if ((state === "processing" || state === "speaking") && (microphone === "on" || microphone === "off"))
      return true
    if (state === "error" && (microphone === "on" || microphone === "unknown")) return true
    if ((state === "unknown" || state === "unavailable") && microphone === "unknown") return true
    if (state === "unavailable" && microphone === "on") return true
    return false
  }

  function applyText(content) {
    var raw = String(content || "")
    if (raw.length === 0) {
      markUnknown()
      return
    }
    if (raw.length > maxBytes) {
      markUnknown()
      return
    }
    var parsed
    try {
      parsed = JSON.parse(raw)
    } catch (error) {
      markUnknown()
      return
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      markUnknown()
      return
    }
    var allowed = {
      "schema_version": true,
      "state": true,
      "microphone": true,
      "generation": true,
      "updated_at": true
    }
    for (var key in parsed) {
      if (!allowed[key]) {
        markUnknown()
        return
      }
    }
    if (parsed.schema_version !== 1) {
      markUnknown()
      return
    }
    var state = parsed.state
    var mic = parsed.microphone
    var generation = parsed.generation
    var updatedAt = parsed.updated_at
    if (typeof state !== "string" || typeof mic !== "string" || !allowedPair(state, mic)) {
      markUnknown()
      return
    }
    if (typeof generation !== "number" || !isFinite(generation) || Math.floor(generation) !== generation || generation < 1 || generation > 9007199254740991) {
      markUnknown()
      return
    }
    if (typeof updatedAt !== "number" || !isFinite(updatedAt)) {
      markUnknown()
      return
    }
    var ageMs = Date.now() - (updatedAt * 1000)
    if (ageMs > maxAgeMs || ageMs < -maxFutureMs) {
      markUnknown()
      return
    }
    if (seenGeneration !== null && generation < seenGeneration) {
      markUnknown()
      return
    }
    if (seenGeneration !== null && updatedAt < seenUpdated && generation !== seenGeneration) {
      markUnknown()
      return
    }
    if (seenGeneration !== null && generation === seenGeneration && updatedAt < seenUpdated) {
      markUnknown()
      return
    }
    seenGeneration = generation
    seenUpdated = updatedAt
    outcome = "current"
    stateName = state
    microphone = mic
    label = mic === "on" ? "MICROPHONE ON" : (mic === "off" ? "microphone off" : "microphone unknown")
  }

  function considerAge() {
    if (outcome !== "current") return
    var ageMs = Date.now() - (seenUpdated * 1000)
    if (ageMs > maxAgeMs)
      markUnknown()
  }

  Timer {
    interval: 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: {
      root.considerAge()
      projectionFile.reload()
    }
  }

  FileView {
    id: projectionFile
    path: root.projectionPath
    // Reads stay asynchronous. A slow or missing file must not stall the shell.
    preload: false
    blockLoading: false
    blockAllReads: false
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.applyText(text())
    onLoadFailed: root.markUnavailable()
  }

  Rectangle {
    anchors.fill: parent
    color: root.microphone === "on" ? root.liveFill : "transparent"
  }

  Text {
    id: caption
    anchors.centerIn: parent
    text: root.label
    color: root.microphone === "on" ? "white" : root.quietText
    font.family: root.bar && root.bar.fontFamily ? root.bar.fontFamily : Style.font.family
    font.pixelSize: Style.font.body
    font.bold: root.microphone === "on"
  }
}
