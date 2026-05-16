"""Hardware-free StackChan bridge facade core."""

from __future__ import annotations

import logging
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

CLI_SOURCES = {"cli", "codex_skill", "human_cli", "stackchanctl"}


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
        for device_id in ("default",):
            self._status[device_id] = StatusSnapshot(device_id=device_id)

    def get_status(
        self, device_id: str = "default", *, command_id: str = ""
    ) -> StatusResponse:
        availability = self.registry.availability(device_id)
        status = self._status_for(device_id)
        status.connected = availability == DeviceAvailability.AVAILABLE

        if availability != DeviceAvailability.AVAILABLE:
            status.last_error = self._availability_error(availability, device_id)

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

        status = self._mark_accepted(meta, motion=name)
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

    def _validate(self, meta: CommandMeta) -> CommandResponse | None:
        if meta.priority == PRIORITY_SAFETY and meta.source in CLI_SOURCES:
            result = Result.rejected(
                "INVALID_PRIORITY",
                "CLI-originated SAFETY priority is reserved for bridge and firmware.",
            )
            self._record_error(meta, result)
            return CommandResponse(meta.device_id, meta.command_id, result)

        availability = self.registry.availability(meta.device_id)
        if availability == DeviceAvailability.AVAILABLE:
            return None

        result = self._availability_error(availability, meta.device_id)
        self._record_error(meta, result)
        return CommandResponse(meta.device_id, meta.command_id, result)

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

    def _record_error(self, meta: CommandMeta, result: Result) -> None:
        status = self._status_for(meta.device_id)
        status.connected = False
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
