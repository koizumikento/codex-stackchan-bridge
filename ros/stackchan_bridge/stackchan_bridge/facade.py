"""Hardware-free StackChan bridge facade core."""

from __future__ import annotations

import logging
import math
from typing import Any

from stackchan_bridge.logging import log_structured
from stackchan_bridge.models import (
    PRIORITY_SAFETY,
    CommandMeta,
    CommandResponse,
    Result,
    StatusResponse,
    StatusSnapshot,
)
from stackchan_bridge.registry import DeviceAvailability, DeviceRegistry

AVAILABILITY_ERROR_CODES = {
    "DEVICE_NOT_FOUND",
    "TRANSPORT_DISCONNECTED",
    "DEVICE_ID_CONFLICT",
}
PAN_MIN_DEG = -128.0
PAN_MAX_DEG = 128.0
TILT_MIN_DEG = 0.0
TILT_MAX_DEG = 90.0
SPEED_MIN = 0
SPEED_MAX = 1000
MIN_NONZERO_DURATION_MS = 100
MAX_DURATION_MS = 2000
AUDIO_FORMAT = "pcm_s16le"
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
MAX_AUDIO_CAPTURE_MS = 15000
CAMERA_FORMAT = "jpeg"
CAMERA_WIDTH = 320
CAMERA_HEIGHT = 240
CAMERA_MIN_QUALITY = 1
CAMERA_MAX_QUALITY = 95


class StackChanBridgeFacade:
    """Validate and route CLI-facing commands to configured devices.

    This first implementation is intentionally hardware-free. It accepts the
    baseline commands for an available default device and records enough state
    for status/observe flows while preserving command correlation metadata.
    """

    def __init__(
        self,
        registry: DeviceRegistry | None = None,
        logger: Any | None = None,
    ) -> None:
        self.registry = registry or DeviceRegistry()
        self.logger = logger or logging.getLogger(__name__)
        self._status: dict[str, StatusSnapshot] = {}
        for device_id in self.registry.device_ids():
            self._status[device_id] = StatusSnapshot(device_id=device_id)

    def get_status(
        self, device_id: str = "default", *, command_id: str = ""
    ) -> StatusResponse:
        availability = self.registry.availability(device_id)
        status = self._status_for(device_id)
        status.connected = availability == DeviceAvailability.AVAILABLE

        if availability != DeviceAvailability.AVAILABLE:
            status.last_error = self._availability_error(availability, device_id)
        elif status.last_error.error_code in AVAILABILITY_ERROR_CODES:
            status.last_error = Result.accepted("")

        return StatusResponse(device_id=device_id, command_id=command_id, status=status)

    def set_face(
        self, meta: CommandMeta, name: str, duration_ms: int = 0
    ) -> CommandResponse:
        checked = self._validate(meta)
        if checked is not None:
            return checked

        status = self._mark_accepted(meta, face=name)
        log_structured(
            self.logger,
            logging.INFO,
            "face_set_accepted",
            device_id=meta.device_id,
            command_id=meta.command_id,
            source=meta.source,
            duration_ms=duration_ms,
        )
        return CommandResponse(meta.device_id, meta.command_id, status.last_error)

    def set_led(
        self,
        meta: CommandMeta,
        pattern: str,
        color: str = "",
        duration_ms: int = 0,
    ) -> CommandResponse:
        checked = self._validate(meta)
        if checked is not None:
            return checked

        status = self._mark_accepted(meta)
        log_structured(
            self.logger,
            logging.INFO,
            "led_set_accepted",
            device_id=meta.device_id,
            command_id=meta.command_id,
            source=meta.source,
            pattern=pattern,
            color=color,
            duration_ms=duration_ms,
        )
        return CommandResponse(meta.device_id, meta.command_id, status.last_error)

    def run_motion(
        self,
        meta: CommandMeta,
        name: str,
        intensity: float = 1.0,
        duration_ms: int = 0,
    ) -> CommandResponse:
        checked = self._validate(meta)
        if checked is not None:
            return checked

        status = self._mark_completed(meta, motion=name)
        log_structured(
            self.logger,
            logging.INFO,
            "motion_run_accepted",
            device_id=meta.device_id,
            command_id=meta.command_id,
            source=meta.source,
            motion=name,
            intensity=intensity,
            duration_ms=duration_ms,
        )
        return CommandResponse(meta.device_id, meta.command_id, status.last_error)

    def move_head_pose(
        self,
        meta: CommandMeta,
        pan_deg: float,
        tilt_deg: float,
        speed: int = 0,
        duration_ms: int = 0,
    ) -> CommandResponse:
        checked = self._validate(meta)
        if checked is not None:
            return checked
        validation = self._validate_head_pose(pan_deg, tilt_deg, speed, duration_ms)
        if validation is not None:
            self._record_error(meta, validation, connected=True)
            return CommandResponse(meta.device_id, meta.command_id, validation)

        status = self._mark_completed(meta, motion="pose")
        log_structured(
            self.logger,
            logging.INFO,
            "motion_pose_accepted",
            device_id=meta.device_id,
            command_id=meta.command_id,
            source=meta.source,
            pan_deg=pan_deg,
            tilt_deg=tilt_deg,
            speed=speed,
            duration_ms=duration_ms,
        )
        return CommandResponse(meta.device_id, meta.command_id, status.last_error)

    def home_head_pose(
        self,
        meta: CommandMeta,
        speed: int = 0,
        duration_ms: int = 0,
    ) -> CommandResponse:
        checked = self._validate(meta)
        if checked is not None:
            return checked
        validation = self._validate_head_pose_timing(speed, duration_ms)
        if validation is not None:
            self._record_error(meta, validation, connected=True)
            return CommandResponse(meta.device_id, meta.command_id, validation)

        status = self._mark_completed(meta, motion="home")
        log_structured(
            self.logger,
            logging.INFO,
            "motion_home_accepted",
            device_id=meta.device_id,
            command_id=meta.command_id,
            source=meta.source,
            speed=speed,
            duration_ms=duration_ms,
        )
        return CommandResponse(meta.device_id, meta.command_id, status.last_error)

    def say(self, meta: CommandMeta, text: str) -> CommandResponse:
        checked = self._validate(meta)
        if checked is not None:
            return checked

        del text
        status = self._mark_accepted(meta)
        return CommandResponse(meta.device_id, meta.command_id, status.last_error)

    def play_audio(
        self,
        meta: CommandMeta,
        *,
        format: str = AUDIO_FORMAT,
        sample_rate: int = AUDIO_SAMPLE_RATE,
        channels: int = AUDIO_CHANNELS,
    ) -> CommandResponse:
        checked = self._validate(meta)
        if checked is not None:
            return checked

        validation = self._validate_audio_contract(format, sample_rate, channels)
        if validation is not None:
            self._record_error(meta, validation, connected=True)
            return CommandResponse(meta.device_id, meta.command_id, validation)

        result = Result.rejected(
            "UNSUPPORTED_FEATURE",
            "audio playback requires firmware-confirmed device transport.",
        )
        self._record_error(meta, result, connected=True)
        return CommandResponse(meta.device_id, meta.command_id, result)

    def capture_audio(
        self,
        meta: CommandMeta,
        *,
        format: str = AUDIO_FORMAT,
        sample_rate: int = AUDIO_SAMPLE_RATE,
        channels: int = AUDIO_CHANNELS,
        duration_ms: int = 0,
    ) -> CommandResponse:
        checked = self._validate(meta)
        if checked is not None:
            return checked

        validation = self._validate_audio_contract(format, sample_rate, channels)
        if validation is None and (duration_ms < 1 or duration_ms > MAX_AUDIO_CAPTURE_MS):
            validation = Result.rejected(
                "AUDIO_CAPTURE_FAILED",
                "audio capture duration must be between 1 and 15000 ms",
                recoverable=True,
            )
        if validation is not None:
            self._record_error(meta, validation, connected=True)
            return CommandResponse(meta.device_id, meta.command_id, validation)

        result = Result.rejected(
            "UNSUPPORTED_FEATURE",
            "audio capture requires firmware-confirmed device transport.",
        )
        self._record_error(meta, result, connected=True)
        return CommandResponse(meta.device_id, meta.command_id, result)

    def capture_camera(
        self,
        meta: CommandMeta,
        *,
        format: str = CAMERA_FORMAT,
        width: int = CAMERA_WIDTH,
        height: int = CAMERA_HEIGHT,
        quality: int = 80,
    ) -> CommandResponse:
        checked = self._validate(meta)
        if checked is not None:
            return checked

        validation = self._validate_camera_contract(format, width, height, quality)
        if validation is not None:
            self._record_error(meta, validation, connected=True)
            return CommandResponse(meta.device_id, meta.command_id, validation)

        result = Result.rejected(
            "UNSUPPORTED_FEATURE",
            "camera capture requires firmware-confirmed device transport.",
        )
        self._record_error(meta, result, connected=True)
        return CommandResponse(meta.device_id, meta.command_id, result)

    def _validate(self, meta: CommandMeta) -> CommandResponse | None:
        availability = self.registry.availability(meta.device_id)
        if meta.priority == PRIORITY_SAFETY:
            result = Result.rejected(
                "INVALID_PRIORITY",
                "SAFETY priority is reserved for bridge and firmware internals.",
            )
            self._record_error(
                meta,
                result,
                connected=availability == DeviceAvailability.AVAILABLE,
            )
            return CommandResponse(meta.device_id, meta.command_id, result)

        if availability == DeviceAvailability.AVAILABLE:
            return None

        result = self._availability_error(availability, meta.device_id)
        self._record_error(meta, result, connected=False)
        return CommandResponse(meta.device_id, meta.command_id, result)

    @staticmethod
    def _validate_head_pose(
        pan_deg: float,
        tilt_deg: float,
        speed: int,
        duration_ms: int,
    ) -> Result | None:
        if not math.isfinite(pan_deg) or not math.isfinite(tilt_deg):
            return Result.rejected(
                "SERVO_LIMIT_EXCEEDED",
                "motion pose angles must be finite",
                recoverable=True,
            )
        if pan_deg < PAN_MIN_DEG or pan_deg > PAN_MAX_DEG:
            return Result.rejected(
                "SERVO_LIMIT_EXCEEDED",
                "motion pose pan_deg is outside -128..128",
                recoverable=True,
            )
        if tilt_deg < TILT_MIN_DEG or tilt_deg > TILT_MAX_DEG:
            return Result.rejected(
                "SERVO_LIMIT_EXCEEDED",
                "motion pose tilt_deg is outside 0..90",
                recoverable=True,
            )
        return StackChanBridgeFacade._validate_head_pose_timing(speed, duration_ms)

    @staticmethod
    def _validate_head_pose_timing(
        speed: int,
        duration_ms: int,
    ) -> Result | None:
        if speed < SPEED_MIN or speed > SPEED_MAX:
            return Result.rejected(
                "SERVO_LIMIT_EXCEEDED",
                "motion speed must be between 0 and 1000",
                recoverable=True,
            )
        if duration_ms != 0 and (
            duration_ms < MIN_NONZERO_DURATION_MS or duration_ms > MAX_DURATION_MS
        ):
            return Result.rejected(
                "MOTION_INTERRUPTED",
                "motion duration must be 0 or between 100 and 2000 ms",
                recoverable=True,
            )
        return None

    @staticmethod
    def _validate_audio_contract(
        format: str,
        sample_rate: int,
        channels: int,
    ) -> Result | None:
        if format != AUDIO_FORMAT:
            return Result.rejected(
                "AUDIO_FORMAT_UNSUPPORTED",
                "audio action only accepts pcm_s16le",
                recoverable=True,
            )
        if sample_rate != AUDIO_SAMPLE_RATE or channels != AUDIO_CHANNELS:
            return Result.rejected(
                "AUDIO_FORMAT_UNSUPPORTED",
                "audio action only accepts 16 kHz mono",
                recoverable=True,
            )
        return None

    @staticmethod
    def _validate_camera_contract(
        format: str,
        width: int,
        height: int,
        quality: int,
    ) -> Result | None:
        if format != CAMERA_FORMAT:
            return Result.rejected(
                "CAMERA_CAPTURE_FAILED",
                "camera capture only accepts jpeg",
                recoverable=True,
            )
        if width != CAMERA_WIDTH or height != CAMERA_HEIGHT:
            return Result.rejected(
                "CAMERA_CAPTURE_FAILED",
                "camera capture only accepts QVGA 320x240",
                recoverable=True,
            )
        if quality < CAMERA_MIN_QUALITY or quality > CAMERA_MAX_QUALITY:
            return Result.rejected(
                "CAMERA_CAPTURE_FAILED",
                "camera quality must be between 1 and 95",
                recoverable=True,
            )
        return None

    def _mark_accepted(
        self,
        meta: CommandMeta,
        *,
        face: str | None = None,
        motion: str | None = None,
    ) -> StatusSnapshot:
        status = self._status_for(meta.device_id)
        status.connected = True
        status.state = "ready"
        if face is not None:
            status.face = face
        if motion is not None:
            status.motion = motion
        status.last_command_id = meta.command_id
        status.last_error = Result.accepted()
        return status

    def _mark_completed(
        self,
        meta: CommandMeta,
        *,
        face: str | None = None,
        motion: str | None = None,
    ) -> StatusSnapshot:
        status = self._mark_accepted(meta, face=face, motion=motion)
        status.last_error = Result.completed()
        return status

    def _record_error(
        self,
        meta: CommandMeta,
        result: Result,
        *,
        connected: bool,
    ) -> None:
        status = self._status_for(meta.device_id)
        status.connected = connected
        status.last_command_id = meta.command_id
        status.last_error = result
        log_structured(
            self.logger,
            logging.WARNING,
            "command_rejected",
            device_id=meta.device_id,
            command_id=meta.command_id,
            source=meta.source,
            error_code=result.error_code,
            error_message=result.message,
            recoverable=result.recoverable,
        )

    def _status_for(self, device_id: str) -> StatusSnapshot:
        if device_id not in self._status:
            self._status[device_id] = StatusSnapshot(
                device_id=device_id,
                connected=False,
                state="unknown",
            )
        return self._status[device_id]

    @staticmethod
    def _availability_error(
        availability: DeviceAvailability, device_id: str
    ) -> Result:
        if availability == DeviceAvailability.NOT_FOUND:
            return Result.rejected(
                "DEVICE_NOT_FOUND",
                f"Device '{device_id}' is not configured.",
            )
        if availability == DeviceAvailability.DISCONNECTED:
            return Result.rejected(
                "TRANSPORT_DISCONNECTED",
                f"Device '{device_id}' is configured but disconnected.",
                recoverable=True,
            )
        if availability == DeviceAvailability.CONFLICT:
            return Result.rejected(
                "DEVICE_ID_CONFLICT",
                f"Multiple physical devices map to device_id '{device_id}'.",
                recoverable=True,
            )
        return Result.accepted()
