"""ROS-independent shapes used by the bridge facade.

These dataclasses intentionally mirror the shared stackchan_msgs contract
without importing ROS packages, so package tests can run on development
machines without a ROS 2 installation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PRIORITY_LOW = 0
PRIORITY_NORMAL = 1
PRIORITY_HIGH = 2
PRIORITY_SAFETY = 3

STATE_ACCEPTED = 1
STATE_COMPLETED = 2
STATE_REJECTED = 3
STATE_TIMEOUT = 4


@dataclass(frozen=True)
class CommandMeta:
    """Command correlation metadata carried by command-bearing requests."""

    device_id: str = "default"
    command_id: str = ""
    source: str = ""
    priority: int = PRIORITY_NORMAL


@dataclass(frozen=True)
class Result:
    """Structured command result matching stackchan_msgs/Result fields."""

    ok: bool
    state: int
    error_code: str = ""
    message: str = ""
    recoverable: bool = False

    @classmethod
    def accepted(cls, message: str = "accepted") -> "Result":
        return cls(ok=True, state=STATE_ACCEPTED, message=message)

    @classmethod
    def rejected(
        cls, error_code: str, message: str, *, recoverable: bool = False
    ) -> "Result":
        return cls(
            ok=False,
            state=STATE_REJECTED,
            error_code=error_code,
            message=message,
            recoverable=recoverable,
        )


@dataclass(frozen=True)
class CommandResponse:
    """Facade command response with correlation fields preserved."""

    device_id: str
    command_id: str
    result: Result


@dataclass
class StatusSnapshot:
    """Latest bridge-aggregated status for one device."""

    device_id: str = "default"
    connected: bool = True
    state: str = "ready"
    face: str = "neutral"
    motion: str = "idle"
    last_command_id: str = ""
    last_error: Result = field(default_factory=lambda: Result.accepted("ok"))


@dataclass(frozen=True)
class StatusResponse:
    """Status facade response with optional command correlation preserved."""

    device_id: str
    command_id: str
    status: StatusSnapshot
