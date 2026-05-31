# Speech Processing Design

The PC bridge owns speech processing. Firmware owns reliable microphone and
speaker I/O; the bridge owns VAD, echo control, utterance assembly, local ASR,
transcript TTL, and `voice_semantic_event` generation.

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

`transcript_ready` contains only `utterance_id`. Full text is returned only from
`GetTranscript`. Event payloads, normal logs, and MCP/CLI event results must not
carry transcript text.

PCM payloads, speech text, transcript text, and raw audio bytes must not appear
in normal events, logs, CLI JSON, or MCP tool results. CLI/MCP may expose
bounded metadata such as command id, path, utterance id, duration, byte count,
sample rate, channels, and structured errors.

Low-confidence ASR does not execute robot actions. It produces metadata through
`voice_semantic_event` with `suppressed_reason=low_confidence`.

## Local ASR Provider Boundary

Local Whisper servers may be used as operator-owned bridge-side ASR providers.
The default compose helper exposes an OpenAI-compatible transcription endpoint
for future bridge adapters, but it remains optional and local. The bridge must
send only VAD-bounded utterance audio to the ASR provider, not continuous raw
microphone streams.

ASR provider configuration belongs to bridge-local parameters or environment
variables. Firmware, CLI results, MCP tool results, public events, and normal
logs must not expose provider endpoints, raw model identifiers, request bodies,
PCM bytes, or transcript text. Provider failures should be mapped into the
existing structured ASR result codes: `ASR_UNAVAILABLE`, `ASR_TIMEOUT`,
`ASR_WORKER_FAILED`, `ASR_EMPTY_RESULT`, and `ASR_INVALID_OUTPUT`.

## Safety Keywords

Immediate direct safety commands such as `止まって`, `ストップ`, `停止`, and
`やめて` can be classified locally before Codex is consulted. Quoted,
explanatory, command-design, or negative contexts such as `止まらないで` are not
treated as immediate safety stops.

The bridge marks this classification in `voice_semantic_event.safety_action`;
the firmware still owns the final hardware safety limits.
