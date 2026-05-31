from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from stackchan_bridge.event_buffer import EventRecord
from stackchan_bridge.ros_node import (
    AUDIO_CHUNK_FORMAT_ID_IMA_ADPCM_4BIT,
    AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES_ENV,
    AUDIO_PLAYBACK_BUFFER_MAX_CHUNKS,
    AUDIO_PLAYBACK_ACK_FIRST_CHUNK_RETRY_COUNT_ENV,
    AUDIO_PLAYBACK_ACK_REPUBLISH_MIN_INTERVAL_SEC_ENV,
    AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC_ENV,
    AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES_ENV,
    AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC_ENV,
    AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC_ENV,
    AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC_ENV,
    AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS_ENV,
    AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES_ENV,
    AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_ENV,
    AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS_ENV,
    AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS_ENV,
    MEDIA_ACTION_SETTLE_SEC_ENV,
    _coerce_telemetry_device_id,
    _copy_command_meta,
    _copy_power_status,
    _copy_head_pose,
    _copy_status_with_type,
    _copy_event_record,
    _configured_device_records,
    _event_matches_device_id,
    _mark_device_available_from_event,
    _mark_device_available_from_status,
    _snapshot_from_power_status,
    _snapshot_from_head_pose,
    _snapshot_from_stackchan_status,
    _audio_playback_pull_lookahead_chunks,
    _audio_playback_ack_first_chunk_retry_count,
    _audio_playback_loaded_topic_complete_timeout_sec,
    _audio_playback_loaded_topic_progress_retries,
    _audio_playback_loaded_topic_progress_timeout_sec,
    _audio_playback_loaded_topic_publish_interval_sec,
    _audio_playback_loaded_topic_settle_sec,
    _audio_playback_loaded_topic_window_chunks,
    _audio_playback_command_loaded_max_decoded_bytes,
    _media_action_settle_sec,
    _audio_playback_load_chunk_bytes,
    _audio_playback_load_chunk_bytes_for_format,
    _audio_playback_topic_initial_window_chunks,
    _command_playback_audio_from_complete_chunks,
    _loaded_playback_completion_from_events,
    _loaded_audio_transfer_candidates,
    _loaded_audio_topic_buffered_chunks,
    _loaded_audio_topic_error_code,
    _next_audio_chunk_transport_control,
    _records_after_event_id,
    _sequence_for_event_id,
    _select_playback_chunk_for_pull,
    _select_playback_chunks_for_topic_window,
    _should_republish_audio_window_for_ack,
    _meta_from_ros,
    _normalize_device_ids,
    _reject_external_safety_priority,
    _relay_telemetry_message,
    _status_matches_device_id,
    MediaActionGate,
)
from stackchan_bridge.models import CapabilitySnapshot, Result, StatusSnapshot
from stackchan_bridge.registry import DeviceAvailability, DeviceRecord, DeviceRegistry
from stackchan_bridge.telemetry import HeadPoseSnapshot, PowerStatusSnapshot
from stackchan_bridge.tts_provider import AUDIO_CHUNK_FORMAT_ID, TtsAudio


ROOT = Path(__file__).resolve().parents[1]


class RosNodeHelperTests(unittest.TestCase):
    def test_select_playback_chunk_for_pull_is_idempotent_for_same_sequence(self) -> None:
        queue = [
            SimpleNamespace(sequence=4, pcm=b"old"),
            SimpleNamespace(sequence=5, pcm=b"five"),
            SimpleNamespace(sequence=6, pcm=b"six"),
        ]

        first, buffered = _select_playback_chunk_for_pull(queue, 5)
        retry, retry_buffered = _select_playback_chunk_for_pull(queue, 5)

        self.assertEqual(first.pcm, b"five")
        self.assertEqual(retry.pcm, b"five")
        self.assertEqual(buffered, 2)
        self.assertEqual(retry_buffered, 2)
        self.assertEqual([chunk.sequence for chunk in queue], [5, 6])

    def test_loaded_audio_transfer_candidates_prefers_adpcm_then_pcm(self) -> None:
        with mock.patch.dict(os.environ, {"STACKCHAN_TTS_LOADED_ADPCM": "1"}):
            candidates = _loaded_audio_transfer_candidates(TtsAudio(pcm=b"\x00\x00\x01\x00"))

        self.assertEqual([candidate.encoding for candidate in candidates], [
            "ima_adpcm_4bit",
            "pcm_s16le",
        ])
        self.assertEqual(candidates[0].format_id, 2)
        self.assertEqual(candidates[0].payload, b"\x00\x00\x00\x00\x01")
        self.assertEqual(candidates[0].decoded_bytes, 4)
        self.assertEqual(candidates[1].format_id, AUDIO_CHUNK_FORMAT_ID)
        self.assertEqual(candidates[1].payload, b"\x00\x00\x01\x00")

    def test_loaded_audio_transfer_candidates_can_disable_adpcm(self) -> None:
        with mock.patch.dict(os.environ, {"STACKCHAN_TTS_LOADED_ADPCM": "0"}):
            candidates = _loaded_audio_transfer_candidates(TtsAudio(pcm=b"\x00\x00\x01\x00"))

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].encoding, "pcm_s16le")

    def test_select_playback_chunk_for_pull_discards_acknowledged_sequences(self) -> None:
        queue = [
            SimpleNamespace(sequence=5, pcm=b"five"),
            SimpleNamespace(sequence=6, pcm=b"six"),
        ]

        chunk, buffered = _select_playback_chunk_for_pull(queue, 6)

        self.assertEqual(chunk.pcm, b"six")
        self.assertEqual(buffered, 1)
        self.assertEqual([item.sequence for item in queue], [6])

    def test_select_playback_chunks_for_topic_window_limits_future_chunks(self) -> None:
        queue = [SimpleNamespace(sequence=index) for index in range(2, 12)]

        window = _select_playback_chunks_for_topic_window(queue, 4, 3)

        self.assertEqual([chunk.sequence for chunk in window], [4, 5, 6])
        self.assertEqual([chunk.sequence for chunk in queue[:3]], [2, 3, 4])

    def test_select_playback_chunks_for_topic_window_allows_zero_capacity(self) -> None:
        queue = [SimpleNamespace(sequence=index) for index in range(2, 5)]

        window = _select_playback_chunks_for_topic_window(queue, 2, 0)

        self.assertEqual(window, [])
        self.assertEqual([chunk.sequence for chunk in queue], [2, 3, 4])

    def test_command_playback_audio_from_complete_chunks_builds_loaded_audio(self) -> None:
        request = SimpleNamespace(
            format="pcm_s16le",
            sample_rate=16000,
            channels=1,
            first_chunk_present=False,
            first_chunk_sequence=0,
            first_chunk_pcm=b"",
        )
        chunks = [
            SimpleNamespace(
                direction=1,
                sequence=0,
                total_bytes=6,
                format=AUDIO_CHUNK_FORMAT_ID,
                sample_rate=16000,
                channels=1,
                end_of_stream=False,
                pcm=b"aa",
            ),
            SimpleNamespace(
                direction=1,
                sequence=1,
                total_bytes=6,
                format=AUDIO_CHUNK_FORMAT_ID,
                sample_rate=16000,
                channels=1,
                end_of_stream=False,
                pcm=b"bb",
            ),
            SimpleNamespace(
                direction=1,
                sequence=2,
                total_bytes=6,
                format=AUDIO_CHUNK_FORMAT_ID,
                sample_rate=16000,
                channels=1,
                end_of_stream=True,
                pcm=b"cc",
            ),
        ]

        audio, state = _command_playback_audio_from_complete_chunks(request, chunks)

        self.assertEqual(state, "complete")
        self.assertIsNotNone(audio)
        self.assertEqual(audio.pcm, b"aabbcc")

    def test_command_playback_audio_waits_for_eos_and_contiguous_chunks(self) -> None:
        request = SimpleNamespace(
            format="pcm_s16le",
            sample_rate=16000,
            channels=1,
            first_chunk_present=True,
            first_chunk_sequence=0,
            first_chunk_pcm=b"aa",
        )
        incomplete_chunks = [
            SimpleNamespace(
                direction=1,
                sequence=2,
                total_bytes=6,
                format=AUDIO_CHUNK_FORMAT_ID,
                sample_rate=16000,
                channels=1,
                end_of_stream=True,
                pcm=b"cc",
            ),
        ]

        audio, state = _command_playback_audio_from_complete_chunks(
            request,
            incomplete_chunks,
        )

        self.assertIsNone(audio)
        self.assertEqual(state, "incomplete")

    def test_command_playback_audio_skips_payload_above_loaded_buffer(self) -> None:
        request = SimpleNamespace(
            format="pcm_s16le",
            sample_rate=16000,
            channels=1,
            first_chunk_present=False,
            first_chunk_sequence=0,
            first_chunk_pcm=b"",
        )
        chunks = [
            SimpleNamespace(
                direction=1,
                sequence=0,
                total_bytes=40000,
                format=AUDIO_CHUNK_FORMAT_ID,
                sample_rate=16000,
                channels=1,
                end_of_stream=True,
                pcm=b"aa",
            )
        ]

        audio, state = _command_playback_audio_from_complete_chunks(request, chunks)

        self.assertIsNone(audio)
        self.assertEqual(state, "too_large")

    def test_loaded_playback_completion_from_events_accepts_drain_marker(self) -> None:
        records = [
            EventRecord(
                sequence=1,
                event_id="evt-1",
                device_id="default",
                event_name="audio_playback_chunk",
                stamp=1.0,
                command_id="other",
                source="firmware",
                payload={"stage": "loaded_playback_drained", "result": "OK"},
            ),
            EventRecord(
                sequence=2,
                event_id="evt-2",
                device_id="default",
                event_name="audio_playback_chunk",
                stamp=2.0,
                command_id="cmd-1",
                source="firmware",
                payload={"stage": "loaded_playback_drained", "result": "OK"},
            ),
        ]

        result = _loaded_playback_completion_from_events(records, "cmd-1")

        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertEqual(result.message, "audio playback completed from loaded playback drain")

    def test_loaded_playback_completion_from_events_ignores_non_ok_marker(self) -> None:
        records = [
            EventRecord(
                sequence=1,
                event_id="evt-1",
                device_id="default",
                event_name="audio_playback_chunk",
                stamp=1.0,
                command_id="cmd-1",
                source="firmware",
                payload={"stage": "loaded_playback_drained", "result": "TIMEOUT"},
            )
        ]

        self.assertIsNone(_loaded_playback_completion_from_events(records, "cmd-1"))

    def test_audio_playback_topic_window_env_is_bounded(self) -> None:
        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS_ENV: "999999"},
        ):
            self.assertEqual(
                _audio_playback_topic_initial_window_chunks(),
                AUDIO_PLAYBACK_BUFFER_MAX_CHUNKS,
            )

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS_ENV: "0"},
        ):
            self.assertEqual(_audio_playback_topic_initial_window_chunks(), 1)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS_ENV: "invalid"},
        ):
            self.assertEqual(_audio_playback_topic_initial_window_chunks(), 8)

    def test_audio_playback_pull_lookahead_env_is_bounded(self) -> None:
        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS_ENV: "12"},
        ):
            self.assertEqual(_audio_playback_pull_lookahead_chunks(), 12)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS_ENV: "-4"},
        ):
            self.assertEqual(_audio_playback_pull_lookahead_chunks(), 1)

    def test_audio_playback_ack_republish_interval_env_is_bounded(self) -> None:
        from stackchan_bridge.ros_node import _audio_playback_ack_republish_min_interval_sec

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_ACK_REPUBLISH_MIN_INTERVAL_SEC_ENV: "0.25"},
        ):
            self.assertEqual(_audio_playback_ack_republish_min_interval_sec(), 0.25)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_ACK_REPUBLISH_MIN_INTERVAL_SEC_ENV: "99"},
        ):
            self.assertEqual(_audio_playback_ack_republish_min_interval_sec(), 2.0)

    def test_audio_playback_ack_first_chunk_retry_env_is_bounded(self) -> None:
        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_ACK_FIRST_CHUNK_RETRY_COUNT_ENV: "1"},
        ):
            self.assertEqual(_audio_playback_ack_first_chunk_retry_count(), 1)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_ACK_FIRST_CHUNK_RETRY_COUNT_ENV: "99"},
        ):
            self.assertEqual(_audio_playback_ack_first_chunk_retry_count(), 3)

    def test_audio_playback_loaded_topic_settle_env_is_bounded(self) -> None:
        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC_ENV: "0.25"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_settle_sec(), 0.25)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC_ENV: "99"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_settle_sec(), 2.0)

    def test_audio_playback_loaded_topic_publish_interval_env_is_bounded(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_audio_playback_loaded_topic_publish_interval_sec(), 0.6)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC_ENV: "0.01"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_publish_interval_sec(), 0.01)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC_ENV: "99"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_publish_interval_sec(), 2.0)

    def test_audio_playback_loaded_topic_complete_timeout_env_is_bounded(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_audio_playback_loaded_topic_complete_timeout_sec(), 30.0)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC_ENV: "12"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_complete_timeout_sec(), 12.0)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC_ENV: "99"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_complete_timeout_sec(), 60.0)

    def test_audio_playback_loaded_topic_window_env_is_bounded(self) -> None:
        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS_ENV: "2"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_window_chunks(), 2)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS_ENV: "0"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_window_chunks(), 1)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS_ENV: "99"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_window_chunks(), 8)

    def test_audio_playback_loaded_topic_progress_timeout_env_is_bounded(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_audio_playback_loaded_topic_progress_timeout_sec(), 0.0)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC_ENV: "2.5"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_progress_timeout_sec(), 2.5)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC_ENV: "0"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_progress_timeout_sec(), 0.0)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC_ENV: "99"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_progress_timeout_sec(), 10.0)

    def test_audio_playback_loaded_topic_progress_retries_env_is_bounded(self) -> None:
        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES_ENV: "2"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_progress_retries(), 2)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES_ENV: "-1"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_progress_retries(), 0)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES_ENV: "99"},
        ):
            self.assertEqual(_audio_playback_loaded_topic_progress_retries(), 8)

    def test_audio_playback_command_loaded_limit_env_is_bounded(self) -> None:
        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES_ENV: "16000"},
        ):
            self.assertEqual(_audio_playback_command_loaded_max_decoded_bytes(), 16000)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES_ENV: "-1"},
        ):
            self.assertEqual(_audio_playback_command_loaded_max_decoded_bytes(), 0)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES_ENV: "999999"},
        ):
            self.assertEqual(
                _audio_playback_command_loaded_max_decoded_bytes(),
                32 * 1024,
            )

    def test_loaded_audio_topic_payload_helpers_support_progress_and_errors(self) -> None:
        self.assertEqual(
            _loaded_audio_topic_buffered_chunks({"expected_seq": 3, "buf_chunks": 2}),
            3,
        )
        self.assertEqual(
            _loaded_audio_topic_buffered_chunks({"buf_chunks": 2}),
            2,
        )
        self.assertEqual(_loaded_audio_topic_buffered_chunks({"expected_seq": "bad"}), 0)
        self.assertEqual(_loaded_audio_topic_error_code({"result": ""}), "")
        self.assertEqual(_loaded_audio_topic_error_code({"result": "OK"}), "")
        self.assertEqual(
            _loaded_audio_topic_error_code({"result": "MALFORMED_AUDIO_CHUNK"}),
            "MALFORMED_AUDIO_CHUNK",
        )

    def test_media_action_settle_env_is_bounded(self) -> None:
        with mock.patch.dict(os.environ, {MEDIA_ACTION_SETTLE_SEC_ENV: "0.5"}):
            self.assertEqual(_media_action_settle_sec(), 0.5)

        with mock.patch.dict(os.environ, {MEDIA_ACTION_SETTLE_SEC_ENV: "99"}):
            self.assertEqual(_media_action_settle_sec(), 30.0)

    def test_media_action_gate_blocks_after_timeout_until_settled(self) -> None:
        now = 100.0
        gate = MediaActionGate(3.0, clock=lambda: now)

        self.assertIsNone(gate.begin("default", "cmd-1", "audio playback"))
        gate.finish(
            "default",
            "cmd-1",
            "audio playback",
            Result(False, 4, "TIMEOUT", "firmware audio playback timed out", True),
        )

        blocked = gate.begin("default", "cmd-2", "audio playback")
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked.error_code, "FIRMWARE_BUSY")
        self.assertIn("cmd-1", blocked.message)

        now = 104.0
        self.assertIsNone(gate.begin("default", "cmd-2", "audio playback"))

    def test_media_action_gate_releases_immediately_after_success(self) -> None:
        gate = MediaActionGate(3.0, clock=lambda: 10.0)

        self.assertIsNone(gate.begin("default", "cmd-1", "audio playback"))
        gate.finish(
            "default",
            "cmd-1",
            "audio playback",
            Result.completed("audio playback completed"),
        )

        self.assertIsNone(gate.begin("default", "cmd-2", "audio capture"))

    def test_media_action_gate_releases_audio_when_status_reports_idle(self) -> None:
        now = 20.0
        gate = MediaActionGate(3.0, clock=lambda: now, idle_release_grace_sec=0.5)

        self.assertIsNone(gate.begin("default", "cmd-1", "audio playback"))
        now = 20.4
        self.assertIsNone(
            gate.release_if_capability_idle(
                "default",
                [CapabilitySnapshot("audio_playback", "available", active=False)],
            )
        )
        self.assertIsNotNone(gate.begin("default", "cmd-2", "audio capture"))

        now = 20.5
        self.assertIsNone(
            gate.release_if_capability_idle(
                "default",
                [CapabilitySnapshot("audio_playback", "available", active=True)],
            )
        )

        now = 20.6
        released = gate.release_if_capability_idle(
            "default",
            [CapabilitySnapshot("audio_playback", "available", active=False)],
        )

        self.assertIsNotNone(released)
        self.assertEqual(released.command_id, "cmd-1")
        self.assertEqual(released.capability, "audio_playback")
        self.assertIsNone(gate.begin("default", "cmd-2", "audio capture"))

    def test_media_action_gate_keeps_audio_when_status_reports_active(self) -> None:
        now = 30.0
        gate = MediaActionGate(3.0, clock=lambda: now, idle_release_grace_sec=0.0)

        self.assertIsNone(gate.begin("default", "cmd-1", "audio capture"))
        now = 31.0
        released = gate.release_if_capability_idle(
            "default",
            [CapabilitySnapshot("audio_capture", "available", active=True)],
        )

        self.assertIsNone(released)
        blocked = gate.begin("default", "cmd-2", "audio playback")
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked.error_code, "FIRMWARE_BUSY")

    def test_media_action_gate_can_release_after_action_accept_without_active_sample(self) -> None:
        gate = MediaActionGate(3.0, clock=lambda: 35.0, idle_release_grace_sec=0.0)

        self.assertIsNone(gate.begin("default", "cmd-1", "audio playback"))
        gate.mark_busy_seen("default", "cmd-1")
        released = gate.release_if_capability_idle(
            "default",
            [CapabilitySnapshot("audio_playback", "available", active=False)],
        )

        self.assertIsNotNone(released)
        self.assertEqual(released.command_id, "cmd-1")

    def test_media_action_gate_ignores_late_timeout_after_status_release(self) -> None:
        now = 50.0
        gate = MediaActionGate(3.0, clock=lambda: now, idle_release_grace_sec=0.0)

        self.assertIsNone(gate.begin("default", "cmd-1", "audio playback"))
        self.assertIsNone(
            gate.release_if_capability_idle(
                "default",
                [CapabilitySnapshot("audio_playback", "available", active=True)],
            )
        )
        released = gate.release_if_capability_idle(
            "default",
            [CapabilitySnapshot("audio_playback", "available", active=False)],
        )
        self.assertIsNotNone(released)
        gate.finish(
            "default",
            "cmd-1",
            "audio playback",
            Result(False, 4, "TIMEOUT", "late firmware audio playback timed out", True),
        )

        self.assertIsNone(gate.begin("default", "cmd-2", "audio capture"))

    def test_media_action_gate_does_not_release_camera_from_status_idle(self) -> None:
        gate = MediaActionGate(3.0, clock=lambda: 40.0, idle_release_grace_sec=0.0)

        self.assertIsNone(gate.begin("default", "cmd-1", "camera capture"))
        released = gate.release_if_capability_idle(
            "default",
            [CapabilitySnapshot("camera_snapshot", "available", active=False)],
        )

        self.assertIsNone(released)
        blocked = gate.begin("default", "cmd-2", "audio playback")
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked.error_code, "FIRMWARE_BUSY")

    def test_audio_playback_load_chunk_defaults_keep_pcm_small_and_adpcm_validated(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_audio_playback_load_chunk_bytes(), 64)
            self.assertEqual(
                _audio_playback_load_chunk_bytes_for_format(AUDIO_CHUNK_FORMAT_ID),
                64,
            )
            self.assertEqual(
                _audio_playback_load_chunk_bytes_for_format(
                    AUDIO_CHUNK_FORMAT_ID_IMA_ADPCM_4BIT
                ),
                128,
            )

    def test_audio_playback_load_chunk_envs_are_bounded_for_loaded_service(self) -> None:
        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_ENV: "2049"},
            clear=True,
        ):
            self.assertEqual(_audio_playback_load_chunk_bytes(), 1280)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES_ENV: "7"},
            clear=True,
        ):
            self.assertEqual(
                _audio_playback_load_chunk_bytes_for_format(
                    AUDIO_CHUNK_FORMAT_ID_IMA_ADPCM_4BIT
                ),
                6,
            )

    def test_next_audio_chunk_transport_control_uses_ack_and_missing_sequence(self) -> None:
        request = SimpleNamespace(
            next_sequence=2,
            has_acknowledgement=True,
            acknowledged_sequence=4,
            has_missing_sequence=True,
            missing_sequence=6,
            free_buffer_chunks=3,
        )

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS_ENV: "8"},
        ):
            next_sequence, window_count = _next_audio_chunk_transport_control(request)

        self.assertEqual(next_sequence, 6)
        self.assertEqual(window_count, 3)

    def test_next_audio_chunk_transport_control_defaults_to_legacy_request(self) -> None:
        request = SimpleNamespace(next_sequence=7)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS_ENV: "5"},
        ):
            next_sequence, window_count = _next_audio_chunk_transport_control(request)

        self.assertEqual(next_sequence, 7)
        self.assertEqual(window_count, 5)

    def test_next_audio_chunk_transport_control_respects_zero_free_buffer(self) -> None:
        request = SimpleNamespace(next_sequence=7, free_buffer_chunks=0)

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS_ENV: "5"},
        ):
            next_sequence, window_count = _next_audio_chunk_transport_control(request)

        self.assertEqual(next_sequence, 7)
        self.assertEqual(window_count, 0)

    def test_next_audio_chunk_transport_control_accepts_ack_topic_shape(self) -> None:
        ack = SimpleNamespace(
            has_acknowledgement=True,
            acknowledged_sequence=8,
            has_missing_sequence=True,
            missing_sequence=10,
            free_buffer_chunks=2,
        )

        with mock.patch.dict(
            os.environ,
            {AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS_ENV: "8"},
        ):
            next_sequence, window_count = _next_audio_chunk_transport_control(ack)

        self.assertEqual(next_sequence, 10)
        self.assertEqual(window_count, 2)

    def test_ack_republish_throttle_suppresses_same_window(self) -> None:
        stats = {}

        first = _should_republish_audio_window_for_ack(stats, 4, 2, 10.0, 0.5)
        repeated = _should_republish_audio_window_for_ack(stats, 4, 2, 10.1, 0.5)
        later = _should_republish_audio_window_for_ack(stats, 4, 2, 10.6, 0.5)

        self.assertTrue(first)
        self.assertFalse(repeated)
        self.assertTrue(later)

    def test_ack_republish_throttle_allows_larger_window(self) -> None:
        stats = {}

        first = _should_republish_audio_window_for_ack(stats, 4, 1, 10.0, 0.5)
        larger_window = _should_republish_audio_window_for_ack(stats, 4, 2, 10.1, 0.5)

        self.assertTrue(first)
        self.assertTrue(larger_window)

    def test_status_copy_includes_capability_messages(self) -> None:
        class CapabilityMessage:
            def __init__(self) -> None:
                self.name = ""
                self.state = ""
                self.detail_code = ""
                self.active = False
                self.queued = 0
                self.last_update = SimpleNamespace(sec=0, nanosec=0)

        response = SimpleNamespace(
            last_error=SimpleNamespace(ok=False, state=0, error_code="", message="", recoverable=False),
            firmware_version="",
            capabilities=[],
        )
        status = StatusSnapshot(
            device_id="default",
            firmware_version="bridge-test",
            last_error=Result.accepted(""),
            capabilities=[
                CapabilitySnapshot(
                    "audio_playback",
                    "degraded",
                    detail_code="QUEUE_BACKPRESSURE",
                    active=True,
                    queued=2,
                    last_update=1778889601.25,
                )
            ],
        )

        _copy_status_with_type(response, status, CapabilityMessage)

        self.assertEqual(response.firmware_version, "bridge-test")
        self.assertEqual(response.capabilities[0].name, "audio_playback")
        self.assertEqual(response.capabilities[0].state, "degraded")
        self.assertEqual(response.capabilities[0].queued, 2)
        self.assertEqual(response.capabilities[0].last_update.sec, 1778889601)
        self.assertEqual(response.capabilities[0].last_update.nanosec, 250000000)

    def test_meta_falls_back_to_namespace_device_id(self) -> None:
        stamp = SimpleNamespace(sec=1778889601, nanosec=250000000)
        meta = SimpleNamespace(
            device_id="",
            command_id="cmd-test-0001",
            source="human_cli",
            created_at=stamp,
            priority=1,
        )

        converted = _meta_from_ros(meta, "desk")

        self.assertEqual(converted.device_id, "desk")
        self.assertEqual(converted.created_at, "1778889601.250000000")

    def test_meta_uses_namespace_device_id_over_caller_supplied_device_id(self) -> None:
        stamp = SimpleNamespace(sec=1778889601, nanosec=250000000)
        meta = SimpleNamespace(
            device_id="desk",
            command_id="cmd-test-0001",
            source="human_cli",
            created_at=stamp,
            priority=1,
        )

        converted = _meta_from_ros(meta, "default")

        self.assertEqual(converted.device_id, "default")

    def test_copy_command_meta_preserves_bridge_namespace_device_id(self) -> None:
        target = SimpleNamespace(created_at=None)
        stamp = SimpleNamespace(sec=1778889601, nanosec=250000000)
        meta = _meta_from_ros(
            SimpleNamespace(
                device_id="desk",
                command_id="cmd-test-0001",
                source="human_cli",
                created_at=stamp,
                priority=2,
            ),
            "default",
        )

        _copy_command_meta(target, meta, stamp)

        self.assertEqual(target.device_id, "default")
        self.assertEqual(target.command_id, "cmd-test-0001")
        self.assertEqual(target.source, "human_cli")
        self.assertIs(target.created_at, stamp)
        self.assertEqual(target.priority, 2)

    def test_safety_priority_rejection_helper_clears_result_response_payloads(self) -> None:
        meta = SimpleNamespace(device_id="default", command_id="cmd-test-0001", priority=3)
        response = SimpleNamespace(
            result=SimpleNamespace(ok=True, state=2, error_code="", message="", recoverable=False),
            events=[object()],
            cursor="evt-1",
            stale=True,
            transcript="private",
            confidence=1.0,
        )

        rejected = _reject_external_safety_priority(meta, response)

        self.assertTrue(rejected)
        self.assertFalse(response.result.ok)
        self.assertEqual(response.result.error_code, "INVALID_PRIORITY")
        self.assertEqual(response.events, [])
        self.assertEqual(response.cursor, "")
        self.assertFalse(response.stale)
        self.assertEqual(response.transcript, "")
        self.assertEqual(response.confidence, 0.0)

    def test_safety_priority_rejection_helper_handles_status_response_shape(self) -> None:
        meta = SimpleNamespace(device_id="default", command_id="cmd-test-0001", priority=3)
        response = SimpleNamespace(
            last_error=SimpleNamespace(ok=True, state=1, error_code="", message="", recoverable=False)
        )

        rejected = _reject_external_safety_priority(meta, response)

        self.assertTrue(rejected)
        self.assertFalse(response.last_error.ok)
        self.assertEqual(response.last_error.error_code, "INVALID_PRIORITY")

    def test_device_ids_are_normalized_for_node_resources_and_registry(self) -> None:
        self.assertEqual(
            _normalize_device_ids(["default", "desk", "desk", ""]),
            ["default", "desk"],
        )
        self.assertEqual(_normalize_device_ids("desk"), ["desk"])
        self.assertEqual(_normalize_device_ids([]), ["default"])

    def test_configured_records_can_start_disconnected_without_hardware(self) -> None:
        records = _configured_device_records(["default", "desk"], connected=False)

        self.assertEqual([record.device_id for record in records], ["default", "desk"])
        self.assertFalse(records[0].connected)
        self.assertFalse(records[1].connected)

    def test_firmware_event_marks_configured_device_available(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=False)])
        event = SimpleNamespace(
            device_id="default",
            event_name="firmware_ready",
            source="firmware",
        )

        changed = _mark_device_available_from_event(registry, "default", event)

        self.assertTrue(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.AVAILABLE,
        )

    def test_firmware_event_liveness_rejects_device_id_mismatch(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=False)])
        event = SimpleNamespace(
            device_id="desk",
            event_name="firmware_ready",
            source="firmware",
        )

        self.assertFalse(_event_matches_device_id("default", event))
        changed = _mark_device_available_from_event(registry, "default", event)

        self.assertFalse(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.DISCONNECTED,
        )

    def test_bridge_origin_events_do_not_mark_device_available(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=False)])
        event = SimpleNamespace(
            device_id="default",
            event_name="device_connected",
            source="bridge",
        )

        changed = _mark_device_available_from_event(registry, "default", event)

        self.assertFalse(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.DISCONNECTED,
        )

    def test_firmware_status_marks_configured_device_available(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=False)])
        status = SimpleNamespace(device_id="default", connected=True)

        changed = _mark_device_available_from_status(registry, "default", status)

        self.assertTrue(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.AVAILABLE,
        )

    def test_firmware_status_can_mark_available_device_disconnected(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=True)])
        status = SimpleNamespace(device_id="default", connected=False)

        changed = _mark_device_available_from_status(registry, "default", status)

        self.assertFalse(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.DISCONNECTED,
        )

    def test_firmware_status_liveness_rejects_device_id_mismatch(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=False)])
        status = SimpleNamespace(device_id="desk", connected=True)

        self.assertFalse(_status_matches_device_id("default", status))
        changed = _mark_device_available_from_status(registry, "default", status)

        self.assertFalse(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.DISCONNECTED,
        )

    def test_stackchan_status_snapshot_copies_liveness_fields(self) -> None:
        last_error = SimpleNamespace(
            ok=False,
            state=3,
            error_code="TRANSPORT_DISCONNECTED",
            message="lost heartbeat",
            recoverable=True,
        )
        capability = SimpleNamespace(
            name="face",
            state="available",
            detail_code="",
            active=True,
            queued=0,
            last_update=SimpleNamespace(sec=42, nanosec=250000000),
        )
        status = SimpleNamespace(
            device_id="",
            connected=False,
            state="degraded",
            face="neutral",
            motion="idle",
            last_command_id="cmd-1",
            last_error=last_error,
            firmware_version="bringup",
            capabilities=[capability],
        )

        snapshot = _snapshot_from_stackchan_status(status, fallback_device_id="default")

        self.assertEqual(snapshot.device_id, "default")
        self.assertFalse(snapshot.connected)
        self.assertEqual(snapshot.state, "degraded")
        self.assertEqual(snapshot.last_error.error_code, "TRANSPORT_DISCONNECTED")
        self.assertTrue(snapshot.last_error.recoverable)
        self.assertEqual(snapshot.capabilities[0].name, "face")
        self.assertEqual(snapshot.capabilities[0].last_update, 42.25)

    def test_event_record_copies_to_ros_shape_with_compact_payload(self) -> None:
        target = SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=0))
        record = EventRecord(
            sequence=1,
            event_id="evt-0001",
            device_id="default",
            event_name="picked_up",
            source="firmware",
            stamp=1778889601.25,
            command_id="cmd-0001",
            payload={"utterance_id": "utt-1"},
        )

        _copy_event_record(target, record)

        self.assertEqual(target.event_id, "evt-0001")
        self.assertEqual(target.device_id, "default")
        self.assertEqual(target.event_name, "picked_up")
        self.assertEqual(target.source, "firmware")
        self.assertEqual(target.stamp.sec, 1778889601)
        self.assertEqual(target.stamp.nanosec, 250000000)
        self.assertEqual(target.command_id, "cmd-0001")
        self.assertEqual(target.payload_json, '{"utterance_id":"utt-1"}')

    def test_records_after_event_id_supports_since_and_unknown_replay(self) -> None:
        records = (
            EventRecord(1, "evt-1", "default", "one", 1.0),
            EventRecord(2, "evt-2", "default", "two", 2.0),
        )

        self.assertEqual(_records_after_event_id(records, "evt-1"), records[1:])
        self.assertEqual(_records_after_event_id(records, "missing"), records)
        self.assertEqual(_sequence_for_event_id(records, "evt-1"), 1)
        self.assertIsNone(_sequence_for_event_id(records, "missing"))

    def test_bridge_node_source_wires_event_services_and_topics(self) -> None:
        source = (ROOT / "stackchan_bridge" / "ros_node.py").read_text()

        for name in (
            "ListEvents",
            "NextEvent",
            "NextAudioChunk",
            "AudioPlaybackAck",
            "ClearEventCursor",
            "GetTranscript",
            "GetPowerStatus",
            "GetHeadPose",
            "SetHeadPose",
            "TouchState",
            "HeadPose",
            "ImuRaw",
            "ProximityRaw",
            "LightRaw",
            "PowerStatus",
            "StackChanEvent",
            "StackChanStatus",
            "LoadAudioChunk",
            "EVENT_QOS_DEPTH = 32",
            "DEFAULT_LIVENESS_TIMEOUT_SEC = 3.5",
            "device_command_timeout_sec",
            "device_media_action_timeout_sec",
            'self.declare_parameter("device_media_action_timeout_sec", 35.0)',
            'self.declare_parameter("asr_enabled", _env_bool(ASR_ENABLED_ENV, False))',
            "STACKCHAN_ASR_ENDPOINT",
            "WhisperHttpAsrEngine",
            'self.declare_parameter(\n                "tts_speed_scale",',
            "STACKCHAN_TTS_SPEED_SCALE",
            "STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD",
            "MultiThreadedExecutor",
            "ReentrantCallbackGroup",
            "ActionClient",
            "reliable_depth_4 = QoSProfile(depth=4)",
            "reliable_depth_8 = QoSProfile(depth=8)",
            "reliable_depth_64 = QoSProfile(depth=64)",
            "AUDIO_PLAYBACK_FIRST_CHUNK_RETRY_COUNT = 3",
            "AUDIO_PLAYBACK_FIRST_CHUNK_RETRY_INTERVAL_SEC = 0.03",
            "AUDIO_PLAYBACK_SUBSCRIPTION_MATCH_TIMEOUT_SEC = 1.5",
            "AUDIO_PLAYBACK_INPUT_IDLE_EOS_SEC = 0.35",
            "AUDIO_PLAYBACK_BUFFERED_PUBLISH_INTERVAL_SEC = 0.15",
            "AUDIO_PLAYBACK_TOPIC_CHUNK_RETRY_COUNT = 1",
            "AUDIO_PLAYBACK_PULL_REPUBLISH_RETRY_COUNT = 3",
            "AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS = 2",
            "STACKCHAN_AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS",
            "AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS = 8",
            "AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS = 8",
            "STACKCHAN_AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS",
            "STACKCHAN_AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS",
            "AUDIO_PLAYBACK_ACK_REPUBLISH_MIN_INTERVAL_SEC = 0.0",
            "STACKCHAN_AUDIO_PLAYBACK_ACK_REPUBLISH_MIN_INTERVAL_SEC",
            "AUDIO_PLAYBACK_ACK_FIRST_CHUNK_RETRY_COUNT = 2",
            "STACKCHAN_AUDIO_PLAYBACK_ACK_FIRST_CHUNK_RETRY_COUNT",
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC",
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC",
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC",
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS",
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC",
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES",
            "STACKCHAN_AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES",
            "TTS_SPEED_SCALE_DEFAULT = 1.0",
            "TTS_PRE_PHONEME_LENGTH_DEFAULT = 0.03",
            "TTS_POST_PHONEME_LENGTH_DEFAULT = 0.03",
            "TTS_SILENCE_TRIM_THRESHOLD_DEFAULT = 256",
            "TTS_SILENCE_TRIM_MARGIN_MS_DEFAULT = 30.0",
            "_publish_device_audio_chunk_with_retries",
            "_republish_device_audio_chunk_for_pull",
            "_select_playback_chunks_for_topic_window",
            "_next_audio_chunk_transport_control",
            "AUDIO_PLAYBACK_FIRST_GOAL_BYTES_DEFAULT = 64",
            "AUDIO_PLAYBACK_CHUNK_BYTES_DEFAULT = 160",
            "AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_DEFAULT = 64",
            "AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES_DEFAULT = 128",
            "AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_MAX = 1280",
            "STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES",
            "STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES",
            "STACKCHAN_AUDIO_PLAYBACK_LOAD_CHUNK_BYTES",
            "STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES",
            "STACKCHAN_AUDIO_PLAYBACK_PULL_ONLY",
            "STACKCHAN_TTS_LOADED_PLAYBACK",
            "STACKCHAN_TTS_LOADED_ADPCM",
            "STACKCHAN_TTS_LOADED_TRANSPORT",
            "AUDIO_CHUNK_FORMAT_ID_IMA_ADPCM_4BIT",
            "encode_ima_adpcm_4bit",
            "_loaded_audio_transfer_candidates",
            "_publish_loaded_audio_playback",
            "audio playback compressed load unsupported; falling back to PCM",
            "_loaded_playback_completion_from_events",
            "_audio_playback_load_chunk_bytes",
            "_audio_playback_load_chunk_bytes_for_format",
            "_audio_playback_pull_service_fallback_after_nacks",
            "_audio_playback_topic_initial_window_chunks",
            "_audio_playback_pull_lookahead_chunks",
            "_audio_playback_ack_republish_min_interval_sec",
            "_audio_playback_ack_first_chunk_retry_count",
            "_audio_playback_loaded_topic_settle_sec",
            "_audio_playback_loaded_topic_publish_interval_sec",
            "_audio_playback_loaded_topic_complete_timeout_sec",
            "_audio_playback_pull_only",
            "_audio_playback_loaded_tts",
            "_wait_for_device_audio_playback_subscription",
            "audio playback relay subscription match",
            "action_status_best_effort_depth_1",
            "feedback_sub_qos_profile=action_status_best_effort_depth_1",
            "status_sub_qos_profile=action_status_best_effort_depth_1",
            "_copy_compressed_image_payload",
            "_make_camera_capture_failed_result",
            "_mark_device_available_from_event(",
            "_mark_device_available_from_status(",
            "_device_audio_capture_clients",
            "_device_audio_load_clients",
            "_device_audio_play_clients",
            "_device_audio_chunk_publishers",
            "_cmd_audio_chunk_subscriptions",
            "_device_audio_playback_ack_subscriptions",
            "_pending_playback_chunks",
            "_handle_next_audio_chunk",
            "_handle_audio_playback_ack",
            "_should_republish_audio_window_for_ack",
            "/audio/playback/next_chunk",
            "/device/audio/playback/acks",
            "audio playback pull served first chunk",
            "_active_playback_sessions",
            "_closed_playback_sessions",
            "_pull_only_playback_sessions",
            "_prebuffered_topic_playback_sessions",
            "input_drained = prebuffered_topic",
            'close_reason = "drained" if input_drained else "idle"',
            "pull_only = key in self._pull_only_playback_sessions",
            "audio playback pull republished chunk on topic",
            "audio playback ack republished topic window",
            "lookahead=",
            "audio playback pull served fallback chunk",
            "_republish_device_audio_chunk_for_pull_async",
            "_publish_device_audio_window_for_ack_async",
            "_playback_relay_stats",
            "pull_nack_counts",
            "last_received_monotonic",
            "activated_monotonic",
            "audio playback pull closed input",
            "_playback_chunk_lock",
            "_audio_chunk_pcm_size",
            "_device_camera_capture_clients",
            "_device_face_clients",
            "_device_led_clients",
            "_device_head_pose_clients",
            "_device_motion_clients",
            "_call_device_face_set",
            "_run_say_face_hint",
            "_run_say_motion_hint",
            "_run_say_after_face",
            "_resolve_say_after_face",
            "after_face_hint",
            '"surprised": "happy"',
            '"error": "thinking"',
            "_set_led_type = SetLed",
            "_call_device_audio_capture",
            "_call_device_audio_play",
            "_load_device_audio_playback",
            "audio playback load service unavailable; falling back to topic relay",
            "audio playback load chunk request",
            "audio playback load chunk timeout",
            "audio playback load chunk response",
            "audio playback loaded before play action",
            "goal.first_chunk_present",
            "goal.first_chunk_sequence",
            "goal.first_chunk_pcm = bytes",
            "next_chunk_sequence",
            "next_chunk_offset",
            "_handle_cmd_audio_chunk",
            "_activate_playback_chunk_relay",
            "_finish_playback_chunk_relay",
            "_publish_device_audio_chunk",
            "audio playback relay buffered first chunk",
            "audio playback relay activated",
            "audio playback relay topic start",
            "pull_only=_audio_playback_pull_only()",
            "audio playback relay published first chunk",
            "audio playback relay finished",
            "_call_device_camera_capture",
            "_send_device_camera_capture_goal",
            "_call_device_led_set",
            "_call_device_head_pose",
            "_call_device_motion_run",
            "_send_device_action_goal",
            "cancel_on_result_timeout=True",
            "cancel_goal_async()",
            "firmware media action cancel timed out",
            "timeout_sec=self._device_media_action_timeout_sec",
            "(goal.duration_ms / 1000.0) + 2.0",
            "/events/list",
            "/events/next",
            "/events/clear_cursor",
            "/speech/transcript/get",
            "/power/status",
            "/motion/status",
            "/motion/pose",
            "imu/raw",
            "/status",
            "/events",
            "/device/events",
            "/device/status",
            "/device/audio/capture",
            "/device/audio/play",
            "/device/audio/playback/load",
            "/device/audio/playback/chunks",
            "/cmd/audio/chunks",
            "/device/camera/capture",
            "/device/face/set",
            "/device/led/set",
            "/device/motion/pose/set",
            "/device/motion/run",
            "device/{tail}",
        ):
            self.assertIn(name, source)

        self.assertIn(
            "record = self.event_aggregator.add(\n                device_id,",
            source,
        )
        self.assertIn(
            "command_response = self.facade.run_motion(\n"
            "                meta,\n"
            "                request.name,\n"
            "                request.intensity,\n"
            "                request.duration_ms,\n"
            "            )\n"
            "            self._publish_status(device_id)",
            source,
        )
        self.assertIn(
            "for device_id in self.facade.registry.device_ids():\n"
            "                self._publish_status(device_id)",
            source,
        )

    def test_power_status_helpers_copy_ros_like_shapes(self) -> None:
        message = type(
            "Power",
            (),
            {
                "device_id": "",
                "stamp": type("Stamp", (), {"sec": 1778889601, "nanosec": 0})(),
                "voltage_v": 4.9,
                "current_ma": 180.0,
                "power_mw": 882.0,
                "percentage": float("nan"),
                "power_source": 2,
                "charging": True,
                "powered": True,
                "low_battery": False,
                "brownout_risk": False,
                "fault_code": "",
            },
        )()

        snapshot = _snapshot_from_power_status(message, fallback_device_id="default")

        self.assertEqual(snapshot.device_id, "default")
        self.assertEqual(snapshot.power_source, 2)

        target = type("Target", (), {"stamp": type("Stamp", (), {"sec": 0, "nanosec": 0})()})()
        _copy_power_status(target, PowerStatusSnapshot("desk", voltage_v=3.7, stamp=1.5))

        self.assertEqual(target.device_id, "desk")
        self.assertEqual(target.voltage_v, 3.7)
        self.assertEqual(target.stamp.sec, 1)
        self.assertEqual(target.stamp.nanosec, 500000000)

    def test_head_pose_helpers_copy_ros_like_shapes(self) -> None:
        message = type(
            "Pose",
            (),
            {
                "device_id": "",
                "stamp": type("Stamp", (), {"sec": 1778889601, "nanosec": 0})(),
                "pan_deg": 30.0,
                "tilt_deg": 20.0,
                "moving": True,
                "frame": "home",
            },
        )()

        snapshot = _snapshot_from_head_pose(message, fallback_device_id="default")

        self.assertEqual(snapshot.device_id, "default")
        self.assertEqual(snapshot.pan_deg, 30.0)
        self.assertTrue(snapshot.moving)

        target = type("Target", (), {"stamp": type("Stamp", (), {"sec": 0, "nanosec": 0})()})()
        _copy_head_pose(target, HeadPoseSnapshot("desk", pan_deg=5.0, tilt_deg=6.0, stamp=1.5))

        self.assertEqual(target.device_id, "desk")
        self.assertEqual(target.pan_deg, 5.0)
        self.assertEqual(target.tilt_deg, 6.0)
        self.assertEqual(target.frame, "home")

    def test_telemetry_device_id_is_filled_but_mismatch_is_rejected(self) -> None:
        missing = SimpleNamespace(device_id="")
        self.assertTrue(_coerce_telemetry_device_id(missing, "default"))
        self.assertEqual(missing.device_id, "default")

        matching = SimpleNamespace(device_id="default")
        self.assertTrue(_coerce_telemetry_device_id(matching, "default"))
        self.assertEqual(matching.device_id, "default")

        mismatched = SimpleNamespace(device_id="desk")
        self.assertFalse(_coerce_telemetry_device_id(mismatched, "default"))
        self.assertEqual(mismatched.device_id, "desk")

    def test_power_telemetry_relay_fills_device_id_stores_and_publishes(self) -> None:
        class Publisher:
            def __init__(self) -> None:
                self.messages = []

            def publish(self, message) -> None:
                self.messages.append(message)

        message = SimpleNamespace(
            device_id="",
            stamp=SimpleNamespace(sec=12, nanosec=0),
            voltage_v=4.9,
            current_ma=180.0,
            power_mw=882.0,
            percentage=float("nan"),
            power_source=2,
            charging=True,
            powered=True,
            low_battery=False,
            brownout_risk=False,
            fault_code="",
        )
        publisher = Publisher()
        store = type("Store", (), {"snapshots": [], "update": lambda self, snapshot: self.snapshots.append(snapshot)})()

        relayed = _relay_telemetry_message(
            "default",
            "power/status",
            message,
            publisher,
            power_store=store,
        )

        self.assertTrue(relayed)
        self.assertEqual(message.device_id, "default")
        self.assertEqual(publisher.messages, [message])
        self.assertEqual(store.snapshots[0].device_id, "default")

    def test_head_pose_relay_fills_device_id_stores_and_publishes(self) -> None:
        class Publisher:
            def __init__(self) -> None:
                self.messages = []

            def publish(self, message) -> None:
                self.messages.append(message)

        message = SimpleNamespace(
            device_id="",
            stamp=SimpleNamespace(sec=12, nanosec=0),
            pan_deg=30.0,
            tilt_deg=20.0,
            moving=False,
            frame="home",
        )
        publisher = Publisher()
        store = type("Store", (), {"snapshots": [], "update": lambda self, snapshot: self.snapshots.append(snapshot)})()

        relayed = _relay_telemetry_message(
            "default",
            "motion/pose",
            message,
            publisher,
            head_pose_store=store,
        )

        self.assertTrue(relayed)
        self.assertEqual(message.device_id, "default")
        self.assertEqual(publisher.messages, [message])
        self.assertEqual(store.snapshots[0].pan_deg, 30.0)

    def test_telemetry_relay_drops_device_id_mismatch(self) -> None:
        class Publisher:
            def publish(self, message) -> None:
                raise AssertionError(f"unexpected publish: {message}")

        conflicts = []
        message = SimpleNamespace(device_id="desk")

        relayed = _relay_telemetry_message(
            "default",
            "touch/state",
            message,
            Publisher(),
            conflict_handler=lambda device_id, tail, msg: conflicts.append((device_id, tail, msg.device_id)),
        )

        self.assertFalse(relayed)
        self.assertEqual(conflicts, [("default", "touch/state", "desk")])


if __name__ == "__main__":
    unittest.main()
