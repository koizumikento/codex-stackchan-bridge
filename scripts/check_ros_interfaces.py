from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MSGS = ROOT / "ros" / "stackchan_msgs"

EXPECTED_INTERFACES = [
    "msg/AudioChunk.msg",
    "msg/CommandMeta.msg",
    "msg/CompressedImagePayload.msg",
    "msg/ImuRaw.msg",
    "msg/Result.msg",
    "msg/StackChanEvent.msg",
    "msg/StackChanStatus.msg",
    "srv/ClearEventCursor.srv",
    "srv/GetTranscript.srv",
    "srv/GetStatus.srv",
    "srv/ListEvents.srv",
    "srv/NextEvent.srv",
    "srv/SetFace.srv",
    "srv/SetLed.srv",
    "action/CaptureAudio.action",
    "action/CaptureCamera.action",
    "action/PlayAudio.action",
    "action/RunMotion.action",
    "action/Say.action",
]

COMMAND_META_FIELDS = [
    "string<=32 device_id",
    "string<=36 command_id",
    "string<=32 source",
    "builtin_interfaces/Time created_at",
    "uint8 priority",
    "uint8 PRIORITY_SAFETY=3",
]

RESULT_FIELDS = [
    "bool ok",
    "uint8 state",
    "string<=48 error_code",
    "string<=160 message",
    "bool recoverable",
    "uint8 STATE_TIMEOUT=4",
]

STACKCHAN_EVENT_FIELDS = [
    "string<=36 event_id",
    "string<=32 device_id",
    "string<=32 event_name",
    "string<=32 source",
    "builtin_interfaces/Time stamp",
    "string<=36 command_id",
    "string<=256 payload_json",
]


def main() -> int:
    cmake = (MSGS / "CMakeLists.txt").read_text()
    for interface in EXPECTED_INTERFACES:
        path = MSGS / interface
        require(path.exists(), f"missing {interface}")
        require(f'"{interface}"' in cmake, f"CMakeLists.txt missing {interface}")

    command_meta = (MSGS / "msg" / "CommandMeta.msg").read_text()
    for field in COMMAND_META_FIELDS:
        require(field in command_meta, f"CommandMeta missing {field}")

    result = (MSGS / "msg" / "Result.msg").read_text()
    for field in RESULT_FIELDS:
        require(field in result, f"Result missing {field}")

    event = (MSGS / "msg" / "StackChanEvent.msg").read_text()
    for field in STACKCHAN_EVENT_FIELDS:
        require(field in event, f"StackChanEvent missing {field}")

    list_events = (MSGS / "srv" / "ListEvents.srv").read_text()
    require("uint8 MAX_EVENTS=32" in list_events, "ListEvents missing MAX_EVENTS")
    require("stackchan_msgs/StackChanEvent[<=32] events" in list_events, "ListEvents events bound drifted")

    next_event = (MSGS / "srv" / "NextEvent.srv").read_text()
    require("string<=64 consumer_id" in next_event, "NextEvent missing consumer_id")
    require("stackchan_msgs/StackChanEvent[<=1] events" in next_event, "NextEvent events bound drifted")

    clear_cursor = (MSGS / "srv" / "ClearEventCursor.srv").read_text()
    require("string<=64 consumer_id" in clear_cursor, "ClearEventCursor missing consumer_id")

    transcript = (MSGS / "srv" / "GetTranscript.srv").read_text()
    require("string<=2048 transcript" in transcript, "GetTranscript transcript bound drifted")

    for action in (MSGS / "action").glob("*.action"):
        text = action.read_text()
        require("stackchan_msgs/CommandMeta meta" in text, f"{action.name} missing meta")
        require("stackchan_msgs/Result result" in text, f"{action.name} missing result")
        require("float32 progress" in text, f"{action.name} missing progress feedback")
        require("string<=160 message" in text, f"{action.name} missing message feedback")

    audio = (MSGS / "msg" / "AudioChunk.msg").read_text()
    require("uint8[<=1280] pcm" in audio, "AudioChunk pcm bound drifted")

    image = (MSGS / "msg" / "CompressedImagePayload.msg").read_text()
    require("uint8[<=98304] data" in image, "camera payload bound drifted")

    print("stackchan_msgs contract check OK")
    return 0


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


if __name__ == "__main__":
    raise SystemExit(main())
