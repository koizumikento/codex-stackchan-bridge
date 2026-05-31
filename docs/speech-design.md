# Speech Processing Design

The PC bridge owns speech processing. Firmware owns reliable microphone and
speaker I/O; the bridge owns VAD, echo control, utterance assembly, local ASR,
transcript TTL, and `voice_semantic_event` generation.

Speech input is an observation pipeline, not an action policy. The bridge may
publish bounded speech events and store transcripts for explicit lookup, but it
must not turn microphone audio, ASR text, or speech classification into
`say`, `face`, `motion`, `led`, `audio`, or other `/stackchan/<device_id>/cmd/...`
commands on its own.

## Pipeline

```text
/stackchan/<device_id>/device/audio/chunks
  -> echo controller
  -> VAD state machine
  -> utterance assembly
  -> local ASR worker
  -> memory-only transcript store
  -> speech_detected / transcript_ready / transcript_failed / voice_semantic_event
```

The bridge processes microphone audio as 10 ms internal frames. ROS
`AudioChunk` remains 20 ms by default and 40 ms maximum; the speech processor
splits capture chunks before echo control and VAD.

Playback and capture chunks share the audio chunk topic only when every chunk
carries `device_id`, `command_id`, `direction`, and monotonic `sequence`.
The baseline permits at most one playback and one capture session per device;
same-direction concurrent sessions are rejected with `FIRMWARE_BUSY`. Sequence
gaps, wrong direction, wrong command id, malformed chunk size, disconnects,
overrun, and underrun are structured result/event conditions rather than
unbounded retries.

## Echo Control

The target AEC backend is a reference-aware WebRTC Audio Processing Module /
AEC3-style worker. It stays behind a process boundary so worker crashes,
timeouts, or invalid output do not bring down the command facade.

`EchoGateFallback` is only a fallback. It suppresses normal ASR while playback
or playback hangover may still be audible. This is not equivalent to AEC.
PipeWire/GStreamer echo-cancel remains a comparison or diagnostic option, not
the standard implementation.

## ASR And Privacy

ASR runs only after VAD has produced an utterance. The baseline keeps cloud ASR
out of the default path and stores transcripts only in memory with TTL.
Audio chunk callbacks enqueue bounded speech-processing work and must not wait
for VAD, echo control, a slow ASR provider, or an unavailable ASR provider.

`transcript_ready` contains only `utterance_id`. Full text is returned only from
`GetTranscript`. Event payloads, normal logs, and MCP/CLI event results must not
carry transcript text.

PCM payloads, speech text, transcript text, and raw audio bytes must not appear
in normal events, logs, CLI JSON, or MCP tool results. CLI/MCP may expose
bounded metadata such as command id, path, utterance id, duration, byte count,
sample rate, channels, and structured errors.

ASR confidence, echo state, and suppression reasons are observation metadata.
They do not authorize robot actions. `voice_semantic_event` must not carry
execution-oriented fields such as `safety_action`, `requires_codex`, or command
intent hints.

## Action Boundary

The normal speech path has no safety-keyword exception. Phrases that sound like
commands are still observations until an explicit user or operator decision
routes a command through the documented `stackchanctl -> stackchan_bridge
facade -> firmware` path.

If a future emergency-stop design needs to react directly to microphone input,
it must be specified as a separate minimal safety contract. That design must not
reuse ordinary transcript or semantic event fields as implicit command triggers.
