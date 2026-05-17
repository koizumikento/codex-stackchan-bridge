from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FirmwareContractTests(unittest.TestCase):
    def test_platformio_pins_core_dependencies(self) -> None:
        platformio = (ROOT / "platformio.ini").read_text()

        self.assertIn("platform = platformio/espressif32@6.7.0", platformio)
        self.assertIn("board = m5stack-cores3", platformio)
        self.assertIn("board_microros_transport = serial", platformio)
        self.assertIn("board_microros_distro = jazzy", platformio)
        self.assertIn("monitor_speed = 921600", platformio)
        self.assertIn("-std=gnu++17", platformio)
        self.assertIn("UART_SCLK_DEFAULT=UART_SCLK_XTAL", platformio)
        self.assertIn("STACKCHAN_MICROROS_SERIAL_BAUD=921600", platformio)
        self.assertIn("StackChan-BSP.git#1.1.0", platformio)
        self.assertRegex(platformio, r"micro_ros_platformio\.git#[0-9a-f]{7,40}")

    def test_priority_and_result_contracts_match_shared_values(self) -> None:
        contract = (ROOT / "include" / "stackchan" / "contract.hpp").read_text()

        self.assertIn("Low = 0", contract)
        self.assertIn("Normal = 1", contract)
        self.assertIn("High = 2", contract)
        self.assertIn("Safety = 3", contract)
        self.assertIn("const char* created_at", contract)
        self.assertIn("Accepted = 1", contract)
        self.assertIn("Completed = 2", contract)
        self.assertIn("Rejected = 3", contract)
        self.assertIn("Timeout = 4", contract)

    def test_state_machine_has_degraded_and_fault_paths(self) -> None:
        state_machine = (ROOT / "include" / "stackchan" / "state_machine.hpp").read_text()

        self.assertIn("RuntimeState::Degraded", state_machine)
        self.assertIn("RuntimeState::Fault", state_machine)
        self.assertIn("agent_disconnected", state_machine)
        self.assertIn("recovered", state_machine)
        self.assertIn("state_ != RuntimeState::Fault", state_machine)

    def test_motion_safety_rejects_unknown_and_bounds_intensity(self) -> None:
        safety = (ROOT / "include" / "stackchan" / "motion_safety.hpp").read_text()

        self.assertIn('"UNKNOWN_COMMAND"', safety)
        self.assertIn('"SERVO_LIMIT_EXCEEDED"', safety)
        self.assertIn("kMinMotionDurationMs", safety)
        self.assertIn("kMaxMotionDurationMs", safety)
        self.assertIn('"MOTION_INTERRUPTED"', safety)
        self.assertIn("intensity < 0.0f || intensity > 1.0f", safety)
        self.assertRegex(safety, re.compile(r"constexpr ServoLimits kDefaultServoLimits"))

    def test_main_rejects_external_safety_priority_and_tracks_agent_health(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()

        self.assertIn('"INVALID_PRIORITY"', main)
        self.assertIn("meta.priority == stackchan::Priority::Safety", main)
        self.assertNotIn("is_cli_source", main)
        self.assertIn("publish_status_heartbeat", main)
        self.assertIn("try_connect_microros_agent", main)
        self.assertIn("check_microros_agent_connection", main)
        self.assertIn("update_agent_connection(false)", main)
        self.assertIn("copy_bounded", main)

    def test_audio_policy_uses_baseline_chunk_contract(self) -> None:
        audio = (ROOT / "include" / "stackchan" / "audio.hpp").read_text()

        self.assertIn("kAudioSampleRate = 16000", audio)
        self.assertIn("kAudioChannels = 1", audio)
        self.assertIn("kAudioChunkMs = 20", audio)
        self.assertIn("kAudioMaxChunkMs = 40", audio)
        self.assertIn("kAudioMaxChunkBytes = 1280", audio)
        self.assertIn('"AUDIO_UNDERRUN"', audio)
        self.assertIn('"MIC_OVERRUN"', audio)

    def test_sensor_policy_uses_explicit_bounds_and_errors(self) -> None:
        sensors = (ROOT / "include" / "stackchan" / "sensors.hpp").read_text()

        self.assertIn("kImuMinHz = 10.0f", sensors)
        self.assertIn("kImuMaxHz = 30.0f", sensors)
        self.assertIn("kCameraWidth = 320", sensors)
        self.assertIn("kCameraHeight = 240", sensors)
        self.assertIn("kCameraMaxQuality = 95", sensors)
        self.assertIn("kCameraMaxPayloadBytes = 98304", sensors)
        self.assertIn('"CAMERA_CAPTURE_FAILED"', sensors)
        self.assertIn('"NFC_READ_FAILED"', sensors)


if __name__ == "__main__":
    unittest.main()
