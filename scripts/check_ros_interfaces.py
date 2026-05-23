from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MSGS = ROOT / "ros" / "stackchan_msgs"

EXPECTED_INTERFACES = [
    "msg/AudioChunk.msg",
    "msg/CapabilityStatus.msg",
    "msg/CommandMeta.msg",
    "msg/CompressedImagePayload.msg",
    "msg/HeadPose.msg",
    "msg/ImuRaw.msg",
    "msg/LightRaw.msg",
    "msg/PowerStatus.msg",
    "msg/ProximityRaw.msg",
    "msg/Result.msg",
    "msg/StackChanEvent.msg",
    "msg/StackChanStatus.msg",
    "msg/TouchState.msg",
    "srv/ClearEventCursor.srv",
    "srv/GetHeadPose.srv",
    "srv/GetPowerStatus.srv",
    "srv/GetTranscript.srv",
    "srv/GetStatus.srv",
    "srv/ListEvents.srv",
    "srv/NextEvent.srv",
    "srv/SetFace.srv",
    "srv/SetHeadPose.srv",
    "srv/SetLed.srv",
    "srv/SetMotion.srv",
    "action/CaptureAudio.action",
    "action/CaptureCamera.action",
    "action/MoveHeadPose.action",
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

SERVICE_FIELDS = {
    "ListEvents.srv": [
        "uint8 MAX_EVENTS=32",
        "stackchan_msgs/CommandMeta meta",
        "uint8 limit",
        "string<=36 since_event_id",
        "stackchan_msgs/Result result",
        "stackchan_msgs/StackChanEvent[<=32] events",
        "string<=36 cursor",
    ],
    "NextEvent.srv": [
        "uint8 MAX_EVENTS=1",
        "stackchan_msgs/CommandMeta meta",
        "string<=64 consumer_id",
        "string<=36 after_event_id",
        "uint32 timeout_ms",
        "stackchan_msgs/Result result",
        "stackchan_msgs/StackChanEvent[<=1] events",
        "string<=36 cursor",
    ],
    "ClearEventCursor.srv": [
        "stackchan_msgs/CommandMeta meta",
        "string<=64 consumer_id",
        "stackchan_msgs/Result result",
        "string<=36 cursor",
    ],
    "GetTranscript.srv": [
        "uint16 MAX_TRANSCRIPT_CHARS=2048",
        "stackchan_msgs/CommandMeta meta",
        "string<=64 utterance_id",
        "stackchan_msgs/Result result",
        "string<=64 utterance_id",
        "string<=2048 transcript",
        "float32 confidence",
        "builtin_interfaces/Time expires_at",
    ],
    "GetPowerStatus.srv": [
        "stackchan_msgs/CommandMeta meta",
        "stackchan_msgs/Result result",
        "stackchan_msgs/PowerStatus status",
        "bool stale",
    ],
    "GetHeadPose.srv": [
        "stackchan_msgs/CommandMeta meta",
        "stackchan_msgs/Result result",
        "stackchan_msgs/HeadPose pose",
        "bool stale",
    ],
    "GetStatus.srv": [
        "stackchan_msgs/CommandMeta meta",
        "string<=32 device_id",
        "bool connected",
        "string<=32 state",
        "string<=32 face",
        "string<=32 motion",
        "string<=36 last_command_id",
        "stackchan_msgs/Result last_error",
        "string<=32 firmware_version",
        "stackchan_msgs/CapabilityStatus[<=16] capabilities",
    ],
    "SetMotion.srv": [
        "stackchan_msgs/CommandMeta meta",
        "string<=32 name",
        "float32 intensity",
        "uint32 duration_ms",
        "stackchan_msgs/Result result",
    ],
    "SetHeadPose.srv": [
        "stackchan_msgs/CommandMeta meta",
        "bool home",
        "float32 pan_deg",
        "float32 tilt_deg",
        "uint16 speed",
        "uint32 duration_ms",
        "stackchan_msgs/Result result",
        "stackchan_msgs/HeadPose pose",
    ],
}


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

    capability = (MSGS / "msg" / "CapabilityStatus.msg").read_text()
    for field in [
        "string<=32 name",
        "string<=16 state",
        "string<=64 detail_code",
        "bool active",
        "uint8 queued",
        "builtin_interfaces/Time last_update",
    ]:
        require(field in capability, f"CapabilityStatus missing {field}")

    status = (MSGS / "msg" / "StackChanStatus.msg").read_text()
    for field in [
        "string<=32 firmware_version",
        "stackchan_msgs/CapabilityStatus[<=16] capabilities",
    ]:
        require(field in status, f"StackChanStatus missing {field}")

    event = (MSGS / "msg" / "StackChanEvent.msg").read_text()
    for field in STACKCHAN_EVENT_FIELDS:
        require(field in event, f"StackChanEvent missing {field}")

    for service_name, fields in SERVICE_FIELDS.items():
        text = (MSGS / "srv" / service_name).read_text()
        for field in fields:
            require(field in text, f"{service_name} missing {field}")

    for action in (MSGS / "action").glob("*.action"):
        text = action.read_text()
        require("stackchan_msgs/CommandMeta meta" in text, f"{action.name} missing meta")
        require("stackchan_msgs/Result result" in text, f"{action.name} missing result")
        require("float32 progress" in text, f"{action.name} missing progress feedback")
        require("string<=160 message" in text, f"{action.name} missing message feedback")
        if action.name == "MoveHeadPose.action":
            require("bool home" in text, "MoveHeadPose missing home mode flag")
        if action.name == "PlayAudio.action":
            require("bool first_chunk_present" in text, "PlayAudio missing first chunk presence")
            require("uint32 first_chunk_sequence" in text, "PlayAudio missing first chunk sequence")
            require("uint8[<=1280] first_chunk_pcm" in text, "PlayAudio first chunk bound drifted")

    audio = (MSGS / "msg" / "AudioChunk.msg").read_text()
    require("uint8[<=1280] pcm" in audio, "AudioChunk pcm bound drifted")

    for message_name, fields in {
        "TouchState.msg": [
            "string<=32 device_id",
            "builtin_interfaces/Time stamp",
            "uint8[<=3] intensities",
            "string<=32 surface",
        ],
        "ProximityRaw.msg": [
            "string<=32 device_id",
            "builtin_interfaces/Time stamp",
            "float32 distance_m",
            "uint16 raw",
        ],
        "LightRaw.msg": [
            "string<=32 device_id",
            "builtin_interfaces/Time stamp",
            "float32 illuminance_lux",
            "uint16 raw",
        ],
        "PowerStatus.msg": [
            "string<=32 device_id",
            "builtin_interfaces/Time stamp",
            "float32 voltage_v",
            "float32 current_ma",
            "float32 power_mw",
            "float32 percentage",
            "string<=32 fault_code",
        ],
        "HeadPose.msg": [
            "string<=32 device_id",
            "builtin_interfaces/Time stamp",
            "float32 pan_deg",
            "float32 tilt_deg",
            "bool moving",
            "string<=16 frame",
        ],
    }.items():
        text = (MSGS / "msg" / message_name).read_text()
        for field in fields:
            require(field in text, f"{message_name} missing {field}")

    image = (MSGS / "msg" / "CompressedImagePayload.msg").read_text()
    require("uint8[<=98304] data" in image, "camera payload bound drifted")

    print("stackchan_msgs contract check OK")
    return 0


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


if __name__ == "__main__":
    raise SystemExit(main())
