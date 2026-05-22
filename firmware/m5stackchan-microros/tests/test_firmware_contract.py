from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]

HARDWARE_FREE_CONTRACT_MATRIX = {
    "metadata/result": "include/stackchan/contract.hpp",
    "calibration": "include/stackchan/calibration.hpp",
    "motion safety": "include/stackchan/motion_safety.hpp",
    "events": "include/stackchan/events.hpp",
    "audio policy": "include/stackchan/audio.hpp",
    "sensor policy": "include/stackchan/sensors.hpp",
    "device publishers": "include/stackchan/ros_publishers.hpp",
}


class FirmwareContractTests(unittest.TestCase):
    def test_platformio_pins_core_dependencies(self) -> None:
        platformio = (ROOT / "platformio.ini").read_text()

        self.assertIn("platform = platformio/espressif32@6.7.0", platformio)
        self.assertIn("board = m5stack-cores3", platformio)
        self.assertIn("board_microros_transport = serial", platformio)
        self.assertIn("board_microros_distro = jazzy", platformio)
        self.assertIn("board_microros_user_meta = ${PROJECT_DIR}/microros_stackchan.meta", platformio)
        self.assertIn("microros_transport = serial", platformio)
        self.assertIn("microros_distro = jazzy", platformio)
        self.assertIn("microros_user_meta = ${PROJECT_DIR}/microros_stackchan.meta", platformio)
        self.assertIn("monitor_speed = 921600", platformio)
        self.assertIn("-std=gnu++17", platformio)
        self.assertIn("UART_SCLK_DEFAULT=UART_SCLK_XTAL", platformio)
        self.assertIn("STACKCHAN_MICROROS_SERIAL_BAUD=921600", platformio)
        self.assertIn("StackChan-BSP.git#1.1.0", platformio)
        self.assertRegex(platformio, r"micro_ros_platformio\.git#[0-9a-f]{7,40}")

        microros_meta = (ROOT / "microros_stackchan.meta").read_text()
        self.assertIn("-DRMW_UXRCE_MAX_SERVICES=3", microros_meta)

    def test_hardware_free_contract_matrix_has_coverage_targets(self) -> None:
        for label, relative_path in HARDWARE_FREE_CONTRACT_MATRIX.items():
            with self.subTest(label=label):
                target = ROOT / relative_path
                self.assertTrue(target.exists(), relative_path)
                self.assertGreater(len(target.read_text()), 100)

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
        self.assertIn('"CALIBRATION_INVALID"', safety)
        self.assertIn('"SERVO_READ_FAILED"', safety)
        self.assertIn("bool calibration_valid", safety)
        self.assertIn("bool servo_read_ok", safety)
        self.assertIn("bool fault_state", safety)
        self.assertNotIn("bool calibration_valid = true", safety)
        self.assertNotIn("bool servo_read_ok = true", safety)
        self.assertNotIn("bool fault_state = false", safety)
        self.assertIn("intensity < 0.0f || intensity > 1.0f", safety)
        self.assertRegex(safety, re.compile(r"constexpr ServoLimits kDefaultServoLimits"))

    def test_head_pose_safety_rejects_external_pose_without_clamping(self) -> None:
        safety = (ROOT / "include" / "stackchan" / "motion_safety.hpp").read_text()

        self.assertIn("struct HeadPoseLimits", safety)
        self.assertIn("constexpr HeadPoseLimits kDefaultHeadPoseLimits", safety)
        self.assertIn("-128.0f", safety)
        self.assertIn("128.0f", safety)
        self.assertIn("90.0f", safety)
        self.assertIn("validate_head_pose_target", safety)
        self.assertIn('"SERVO_READ_FAILED"', safety)
        self.assertIn('"CALIBRATION_INVALID"', safety)
        self.assertIn("plan_head_home", safety)
        self.assertIn('"FIRMWARE_BUSY"', safety)
        self.assertIn("pose_slot_available", safety)
        self.assertIn("elapsed_since_last_command_ms", safety)
        self.assertNotIn("bool calibration_valid = true", safety)
        self.assertNotIn("bool servo_read_ok = true", safety)
        self.assertNotIn("bool fault_state = false", safety)
        self.assertNotIn("clamp_head_pose", safety)

    def test_calibration_store_uses_schema_checksum_and_default_invalid_gate(self) -> None:
        calibration = (ROOT / "include" / "stackchan" / "calibration.hpp").read_text()
        main = (ROOT / "src" / "main.cpp").read_text()

        self.assertIn("kCalibrationSchemaVersion = 1", calibration)
        self.assertIn("kCalibrationNvsNamespace", calibration)
        self.assertIn("kCalibrationNvsKey", calibration)
        self.assertIn("struct CalibrationRecord", calibration)
        self.assertIn("checksum", calibration)
        self.assertIn("calibration_checksum_without_checksum", calibration)
        self.assertIn("validate_calibration_record", calibration)
        self.assertIn('"CALIBRATION_INVALID"', calibration)
        self.assertIn("servo_calibration_bounds_are_safe", calibration)
        self.assertIn("kDefaultServoLimits.min_x", calibration)
        self.assertIn("kDefaultServoLimits.max_x", calibration)
        self.assertIn("kMaxCalibrationCorrection", calibration)
        self.assertNotIn("int16_t min_x", calibration)
        self.assertNotIn("int16_t max_x", calibration)
        self.assertIn("correction_x", calibration)
        self.assertIn("correction_y", calibration)
        self.assertIn("load_from_nvs_record", calibration)
        self.assertIn("void reset()", calibration)
        self.assertIn("valid_ = false", calibration)
        self.assertIn("stackchan::CalibrationStore calibration_store", main)
        self.assertIn("#include <Preferences.h>", main)
        self.assertIn("stackchan::Result load_calibration_from_nvs()", main)
        self.assertIn("calibration_preferences.begin(stackchan::kCalibrationNvsNamespace, true)", main)
        self.assertIn("getBytesLength(stackchan::kCalibrationNvsKey)", main)
        self.assertIn("getBytes(", main)
        self.assertIn("calibration_store.load_from_nvs_record(record)", main)
        self.assertIn("stackchan::Result write_calibration_to_nvs", main)
        self.assertIn("stackchan::validate_calibration_record(record)", main)
        self.assertIn("calibration_preferences.putBytes(", main)
        self.assertIn("stackchan::Result reset_calibration_nvs()", main)
        self.assertIn("calibration_preferences.remove(stackchan::kCalibrationNvsKey)", main)
        self.assertIn("STACKCHAN_CALIBRATION_MAINTENANCE_ENABLE", main)
        self.assertIn("STACKCHAN_CALIBRATION_MAINTENANCE_SEED", main)
        self.assertIn("STACKCHAN_CALIBRATION_MAINTENANCE_RESET", main)
        self.assertIn("calibration_load_result = load_calibration_from_nvs();", main)
        self.assertIn("calibration_maintenance_result = apply_calibration_maintenance_action();", main)
        self.assertIn("return calibration_store.valid();", main)
        self.assertNotIn("TODO: load kCalibrationNvsNamespace", main)
        calibration_valid_body = main[
            main.find("bool firmware_calibration_valid") :
            main.find("bool raw_servo_position_valid")
        ]
        self.assertNotIn("return true;", calibration_valid_body)

    def test_k151_servo_adapter_uses_checked_read_and_fail_closed_motion(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()

        self.assertIn("#include <drivers/FTServo_Arduino/src/SCSCL.h>", main)
        self.assertIn("#include <drivers/PY32IOExpander/PY32IOExpander.hpp>", main)
        self.assertIn("SCSCL servo_bus", main)
        self.assertIn("stackchan::Result initialize_servo_adapter()", main)
        self.assertIn("servo_bus.ReadPos(kYawServoId)", main)
        self.assertIn("servo_bus.ReadPos(kPitchServoId)", main)
        self.assertIn("raw_servo_position_valid", main)
        self.assertIn('"SERVO_READ_FAILED"', main)
        self.assertIn("servo_adapter_init_result.ok", main)
        self.assertIn("MotionSchedulerJob motion_scheduler", main)
        self.assertIn("void step_motion_scheduler(unsigned long now)", main)
        self.assertIn("stackchan::Result enqueue_motion_scheduler", main)
        self.assertIn("stackchan::Result try_motion_neutral_recovery()", main)
        self.assertIn("servo_bus.EnableTorque(kYawServoId, 1)", main)
        self.assertIn("servo_bus.WritePos(kYawServoId", main)
        self.assertIn("servo_bus.WritePos(kPitchServoId", main)
        self.assertIn("servo_position_read_available_cache", main)
        self.assertIn("void update_servo_health_cache(unsigned long now, bool force = false)", main)
        self.assertIn("const bool servo_read_ok = calibration_valid && servo_position_read_available_cache;", main)
        self.assertIn("validate_motion_servo_target(home, \"home\")", main)
        self.assertIn("validate_motion_servo_target(target, \"motion\")", main)
        self.assertIn("state_machine.fault();", main)
        self.assertIn("const bool safety_fault = is_servo_safety_fault(result);", main)
        self.assertIn("if (safety_fault || !recovery_result.ok)", main)
        self.assertIn("copy_bounded(current_motion, sizeof(current_motion), motion_scheduler.name);", main)
        self.assertIn("step_motion_scheduler(now);", main)
        loop_body = main[main.find("void loop() {") :]
        self.assertLess(loop_body.find("step_motion_scheduler(now);"), loop_body.find("update_servo_health_cache(now);"))
        self.assertLess(loop_body.find("step_motion_scheduler(now);"), loop_body.find("publish_status_heartbeat();"))
        self.assertLess(loop_body.find("step_motion_scheduler(now);"), loop_body.find("spin_command_executor();"))
        self.assertIn("move_servo_pair_to(motion_scheduler.target)", main)
        self.assertIn("move_servo_pair_to(motion_scheduler.home)", main)
        self.assertIn("fail_motion_scheduler(result);", main)
        self.assertIn("try_motion_neutral_recovery", main)
        self.assertNotIn("delay(plan.duration_ms / 2)", main)
        motion_handler = main[
            main.find("stackchan::Result handle_motion_command") :
            main.find("void handle_motion_set_service")
        ]
        self.assertNotIn("move_servo_pair_to(", motion_handler)
        self.assertNotIn("servo_position_read_available()", motion_handler)
        enqueue_body = main[
            main.find("stackchan::Result enqueue_motion_scheduler") :
            main.find("void step_motion_scheduler")
        ]
        self.assertNotIn("publish_status_heartbeat();", enqueue_body)
        self.assertNotIn("TODO: call StackChan-BSP servo adapter", main)

    def test_face_commands_render_to_display(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()

        self.assertIn("void render_face_display(const char* name)", main)
        self.assertIn("M5.Display.fillScreen", main)
        self.assertIn("M5.Display.fillRoundRect", main)
        self.assertIn("M5.Display.fillCircle", main)
        self.assertIn("M5.Display.drawFastHLine", main)
        self.assertIn("render_face_display(\"neutral\");", main)
        self.assertIn("render_face_display(name);", main)
        self.assertIn("publish_status_heartbeat();", main)
        for face in ["happy", "thinking", "surprised", "sleepy", "error"]:
            self.assertIn(f'strcmp(name, "{face}") == 0', main)

    def test_calibration_maintenance_requires_operator_confirm_and_stays_out_of_default_paths(self) -> None:
        script = (ROOT.parents[1] / "scripts" / "firmware_platformio.py").read_text()
        cli = (ROOT.parents[1] / "apps" / "stackchanctl" / "src" / "stackchanctl" / "cli.py").read_text()
        mcp = (ROOT.parents[1] / "apps" / "stackchanctl" / "src" / "stackchanctl" / "mcp_stdio.py").read_text()

        self.assertIn("--calibration-maintenance-seed", script)
        self.assertIn("--calibration-maintenance-reset", script)
        self.assertIn("--confirm-calibration-maintenance", script)
        self.assertIn("STACKCHAN_CALIBRATION_MAINTENANCE_ENABLE=1", script)
        self.assertIn("parser.error(", script)
        self.assertNotIn("calibration-maintenance-seed", cli)
        self.assertNotIn("calibration-maintenance-reset", cli)
        self.assertNotIn("calibration_maintenance_seed", mcp)
        self.assertNotIn("calibration_maintenance_reset", mcp)

    def test_calibration_contract_cpp_harness(self) -> None:
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("C++ compiler not available")

        binary = ROOT / "tests" / "calibration_contract_test"
        source = ROOT / "tests" / "calibration_contract_test.cpp"
        if binary.exists():
            binary.unlink()
        if binary.with_suffix(".exe").exists():
            binary.with_suffix(".exe").unlink()

        output = binary.with_suffix(".exe") if compiler.lower().endswith("cl.exe") else binary
        subprocess.run(
            [
                compiler,
                "-std=c++17",
                "-I",
                str(ROOT / "include"),
                str(source),
                "-o",
                str(output),
            ],
            check=True,
        )
        subprocess.run([str(output)], check=True)

    def test_ros_publishers_contract_cpp_harness(self) -> None:
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("C++ compiler not available")

        binary = ROOT / "tests" / "ros_publishers_contract_test"
        source = ROOT / "tests" / "ros_publishers_contract_test.cpp"
        if binary.exists():
            binary.unlink()
        if binary.with_suffix(".exe").exists():
            binary.with_suffix(".exe").unlink()

        output = binary.with_suffix(".exe") if compiler.lower().endswith("cl.exe") else binary
        subprocess.run(
            [
                compiler,
                "-std=c++17",
                "-I",
                str(ROOT / "include"),
                str(source),
                "-o",
                str(output),
            ],
            check=True,
        )
        subprocess.run([str(output)], check=True)

    def test_main_rejects_external_safety_priority_and_tracks_agent_health(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()

        self.assertIn('"INVALID_PRIORITY"', main)
        self.assertIn("meta.priority == stackchan::Priority::Safety", main)
        self.assertNotIn("is_cli_source", main)
        self.assertIn('strcmp(result.error_code, "SERVO_READ_FAILED") == 0', main)
        self.assertIn("publish_status_heartbeat", main)
        self.assertIn("try_connect_microros_agent", main)
        self.assertIn("update_agent_connection(false)", main)
        self.assertIn("if (!result.ok) {\n      update_agent_connection(false);", main)
        self.assertNotIn("check_microros_agent_connection", main)
        self.assertNotIn("kAgentHealthCheckIntervalMs", main)
        self.assertIn("copy_bounded", main)
        self.assertIn("stackchan::EventPublisher event_publisher", main)
        self.assertIn("stackchan::DevicePublisherRegistry device_publishers", main)
        self.assertIn("device_publishers.initialize(STACKCHAN_DEVICE_ID)", main)
        self.assertIn("device_publishers.set_publish_callback", main)
        self.assertIn("event_publisher.set_callback", main)
        self.assertIn("drain_device_events", main)
        self.assertIn("kEventDrainBudget", main)
        self.assertIn("/stackchan/<device_id>/device/events", main)
        self.assertIn("/stackchan/<device_id>/device/status", main)
        self.assertIn("ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, StackChanStatus)", main)
        self.assertIn("ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, SetFace)", main)
        self.assertIn("ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, SetHeadPose)", main)
        self.assertIn("ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, SetMotion)", main)
        self.assertIn("ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, HeadPose)", main)
        self.assertIn("/stackchan/%s/device/face/set", main)
        self.assertIn("/stackchan/%s/device/motion/pose/set", main)
        self.assertIn("/stackchan/%s/device/motion/run", main)
        self.assertIn("rclc_executor_add_service", main)
        self.assertIn("spin_command_executor", main)
        self.assertIn("handle_face_set_service", main)
        self.assertIn("handle_head_pose_set_service", main)
        self.assertIn("handle_motion_set_service", main)
        self.assertIn("reserve_face_set_request_strings", main)
        self.assertIn("reserve_head_pose_set_request_strings", main)
        self.assertIn("reserve_motion_set_request_strings", main)
        self.assertIn("request_matches_device_id", main)
        self.assertIn('"INVALID_DEVICE_ID"', main)
        self.assertIn("device_publishers.publish_status", main)
        self.assertIn("device_publishers.publish_motion_pose", main)
        self.assertIn("runtime_state_name", main)
        self.assertIn("firmware_calibration_valid", main)
        self.assertIn("servo_position_read_available", main)
        face_handler = main[
            main.find("stackchan::Result handle_face_command") : main.find("stackchan::Result handle_motion_command")
        ]
        motion_handler = main[
            main.find("stackchan::Result handle_motion_command") :
            main.find("void publish_status_heartbeat() {\n")
        ]
        self.assertLess(
            face_handler.find("meta.priority == stackchan::Priority::Safety"),
            face_handler.find("state_machine.state() == stackchan::RuntimeState::Fault"),
        )
        self.assertLess(
            motion_handler.find("meta.priority == stackchan::Priority::Safety"),
            motion_handler.find("state_machine.state() == stackchan::RuntimeState::Fault"),
        )
        self.assertIn("firmware_publish topic=", main)
        self.assertIn("return device_publishers.publish_event(event);", main)
        self.assertNotIn("publish_synthetic_telemetry", main)
        self.assertNotIn("Serial.println(stackchan::kDeviceEventsTopicSuffix)", main)
        self.assertNotIn("Serial.println(event.payload_json)", main)

    def test_resource_arbitration_and_sensitive_payload_policy_remain_documented(self) -> None:
        quality = (REPO_ROOT / "docs" / "quality-gates.md").read_text()
        firmware = (REPO_ROOT / "docs" / "firmware.md").read_text()
        main = (ROOT / "src" / "main.cpp").read_text()

        order = "safety > motion stop/neutral > audio capture/playback > command handling > camera > LED/idle"
        self.assertIn(order, quality)
        for item in (
            "1. Safety and fault handling.",
            "2. Motion stop / neutral pose.",
            "3. Audio capture and playback.",
            "4. Command handling.",
            "5. Camera capture.",
            "6. LED and idle animation.",
        ):
            self.assertIn(item, firmware)
        self.assertIn("Audio, camera, raw sensor, face, and LED adapters include bounded queues", quality)
        self.assertIn("Firmware normal diagnostics must not print raw `payload_json`", quality)
        self.assertNotIn("Serial.println(event.payload_json)", main)
        self.assertNotIn("Serial.println(audio", main)
        self.assertNotIn("Serial.println(image", main)

    def test_device_publisher_contract_names_qos_and_storage(self) -> None:
        publishers = (ROOT / "include" / "stackchan" / "ros_publishers.hpp").read_text()

        self.assertIn("kStackchanNamespacePrefix = \"/stackchan/\"", publishers)
        self.assertIn("kDeviceEventsTopicSuffix", publishers)
        self.assertIn("kDeviceStatusTopicSuffix = \"/device/status\"", publishers)
        self.assertIn("kDeviceTouchStateTopicSuffix = \"/device/touch/state\"", publishers)
        self.assertIn("kDeviceProximityRawTopicSuffix = \"/device/proximity/raw\"", publishers)
        self.assertIn("kDeviceLightRawTopicSuffix = \"/device/light/raw\"", publishers)
        self.assertIn("kDevicePowerStatusTopicSuffix = \"/device/power/status\"", publishers)
        self.assertIn("kDeviceMotionPoseTopicSuffix = \"/device/motion/pose\"", publishers)
        self.assertIn("build_device_topic_name", publishers)
        self.assertIn("is_valid_device_id", publishers)
        self.assertIn("is_valid_device_id_char", publishers)
        self.assertIn("telemetry_device_id_matches", publishers)
        self.assertIn("RosReliability::Reliable", publishers)
        self.assertIn("RosReliability::BestEffort", publishers)
        self.assertIn("kDeviceEventsQos", publishers)
        self.assertIn("32", publishers)
        self.assertIn("kDeviceStatusQos", publishers)
        self.assertIn("StackChanStatusTelemetry", publishers)
        self.assertIn("publish_status", publishers)
        self.assertIn("kDeviceTouchStateQos", publishers)
        self.assertIn("kDeviceProximityRawQos", publishers)
        self.assertIn("kDeviceLightRawQos", publishers)
        self.assertIn("kDevicePowerStatusQos", publishers)
        self.assertIn("kDeviceMotionPoseQos", publishers)
        self.assertIn("template <size_t Capacity>", publishers)
        self.assertIn("struct BoundedString", publishers)
        self.assertIn("struct BoundedSequence", publishers)
        self.assertIn("kRosTouchIntensityCapacity = 3", publishers)
        self.assertIn("StackChanEventMsg", publishers)
        self.assertIn("TouchStateMsg", publishers)
        self.assertIn("payload_json.assign", publishers)
        self.assertIn("fill_event_message", publishers)
        self.assertIn("fill_touch_state_message", publishers)
        self.assertIn("fill_proximity_raw_message", publishers)
        self.assertIn("fill_light_raw_message", publishers)
        self.assertIn("fill_power_status_message", publishers)
        self.assertIn("fill_head_pose_message", publishers)
        self.assertIn("event device_id does not match publisher namespace", publishers)
        self.assertIn("touch telemetry device_id does not match publisher namespace", publishers)
        self.assertIn("proximity telemetry device_id does not match publisher namespace", publishers)
        self.assertIn("light telemetry device_id does not match publisher namespace", publishers)
        self.assertIn("power telemetry device_id does not match publisher namespace", publishers)
        self.assertIn("head pose telemetry device_id does not match publisher namespace", publishers)
        self.assertIn("TelemetryPublishScheduler", publishers)

    def test_runtime_touch_and_power_publishers_use_real_k151_adapters(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()

        self.assertIn("m5::TouchSensor_Class stackchan_touch_sensor", main)
        self.assertIn("m5::INA226_Class stackchan_power_monitor(0x41)", main)
        self.assertIn("stackchan_touch_sensor.begin()", main)
        self.assertIn("stackchan_power_monitor.config(config)", main)
        self.assertIn("stackchan_power_monitor.begin()", main)
        self.assertIn("read_touch_state_telemetry", main)
        self.assertIn("stackchan_touch_sensor.update()", main)
        self.assertIn("stackchan_touch_sensor.getIntensities()", main)
        self.assertIn("read_power_status_telemetry", main)
        self.assertIn("M5.Power.getBatteryLevel()", main)
        self.assertIn("stackchan_power_monitor.getBusVoltage()", main)
        self.assertIn("stackchan_power_monitor.getShuntCurrent()", main)
        self.assertIn("stackchan_power_monitor.getPower()", main)
        self.assertIn("kLtr553Address = 0x23", main)
        self.assertIn("initialize_ltr553_sensor", main)
        self.assertIn("read_proximity_raw_telemetry", main)
        self.assertIn("read_light_raw_telemetry", main)
        self.assertIn("device_publishers.publish_proximity_raw(telemetry)", main)
        self.assertIn("device_publishers.publish_light_raw(telemetry)", main)
        self.assertIn("proximity_event_estimator.update(telemetry, event_publisher)", main)
        self.assertIn("light_event_estimator.update(telemetry, event_publisher)", main)
        self.assertIn("device_publishers.publish_touch_state(telemetry)", main)
        self.assertIn("device_publishers.publish_power_status(telemetry)", main)
        self.assertIn("touch_event_estimator.update(telemetry, event_publisher)", main)
        self.assertIn("power_event_estimator.update(telemetry, event_publisher)", main)
        self.assertNotIn("publish_synthetic_telemetry", main)

    def test_audio_policy_uses_baseline_chunk_contract(self) -> None:
        audio = (ROOT / "include" / "stackchan" / "audio.hpp").read_text()

        self.assertIn("kAudioSampleRate = 16000", audio)
        self.assertIn("kAudioChannels = 1", audio)
        self.assertIn("kAudioChunkMs = 20", audio)
        self.assertIn("kAudioMaxChunkMs = 40", audio)
        self.assertIn("kAudioMaxChunkBytes = 1280", audio)
        self.assertIn('"AUDIO_UNDERRUN"', audio)
        self.assertIn('"MIC_OVERRUN"', audio)
        self.assertIn("publish_audio_underrun_event", audio)
        self.assertIn("publish_mic_overrun_event", audio)
        self.assertIn("AudioCaptureEvent::Started", audio)
        self.assertIn("AudioCaptureEvent::Finished", audio)
        self.assertIn("AudioCaptureEvent::Failed", audio)

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
        self.assertIn("enum class NfcReadStatus", sensors)
        self.assertIn("NfcReadStatus::ReadFailed", sensors)
        self.assertIn("kButtonDebounceMs = 30", sensors)
        self.assertIn("kButtonHeldMs = 700", sensors)
        self.assertIn("ButtonEventEstimator", sensors)
        self.assertIn("NfcPresenceEstimator", sensors)
        self.assertIn("ImuEventEstimator", sensors)
        self.assertIn("TouchStateTelemetry", sensors)
        self.assertIn("ProximityRawTelemetry", sensors)
        self.assertIn("LightRawTelemetry", sensors)
        self.assertIn("PowerStatusTelemetry", sensors)
        self.assertIn("Battery = 1", sensors)
        self.assertIn("TouchEventEstimator", sensors)
        self.assertIn("ProximityEventEstimator", sensors)
        self.assertIn("LightEventEstimator", sensors)
        self.assertIn("PowerEventEstimator", sensors)
        self.assertIn("kProximityNearSignal", sensors)
        self.assertIn("kBatteryLowVoltageV", sensors)
        self.assertIn("kBrownoutRiskVoltageV", sensors)
        self.assertIn("DeviceEventKind::PickedUp", sensors)
        self.assertIn("DeviceEventKind::PlacedDown", sensors)
        self.assertIn("DeviceEventKind::Shaken", sensors)
        self.assertIn("DeviceEventKind::Tilted", sensors)
        self.assertIn("DeviceEventKind::FaceUp", sensors)
        self.assertIn("DeviceEventKind::FaceDown", sensors)

    def test_device_event_contract_scaffold_names_and_bounds(self) -> None:
        events = (ROOT / "include" / "stackchan" / "events.hpp").read_text()

        self.assertIn("kDeviceEventsTopicSuffix = \"/device/events\"", events)
        self.assertIn("kEventIdMaxLength = 36", events)
        self.assertIn("kEventDeviceIdMaxLength = 32", events)
        self.assertIn("kEventNameMaxLength = 32", events)
        self.assertIn("kEventSourceMaxLength = 32", events)
        self.assertIn("kFirmwareEventSource = \"firmware\"", events)
        self.assertIn("kEventCommandIdMaxLength = 36", events)
        self.assertIn("kEventPayloadJsonMaxLength = 256", events)
        self.assertIn("kEventQueueCapacity = 8", events)
        self.assertIn("struct DeviceEvent", events)
        self.assertIn("queued_count", events)
        self.assertIn("drain", events)
        self.assertIn('"device event queue is full"', events)
        self.assertIn('"device event publisher callback is not configured"', events)
        self.assertIn("EventPublishFn", events)
        self.assertIn("using EventPublishFn = Result (*)", events)
        self.assertIn("class EventPublisher", events)
        self.assertIn("is_priority_device_event_name", events)
        self.assertIn("nfc_read_failed", events)
        self.assertIn("ir_transmit_failed", events)
        self.assertIn("is_bounded_object_json", events)
        self.assertIn("is_json_hex", events)
        self.assertIn("parse_json_escape", events)
        self.assertIn("parse_json_string", events)
        self.assertIn("parse_json_value", events)
        self.assertIn("payload_json_invalid", events)
        self.assertIn("drop_oldest_low_priority_event", events)
        self.assertIn("dropped_low_priority_count", events)

        for name in (
            "button_pressed",
            "button_released",
            "button_held",
            "picked_up",
            "placed_down",
            "shaken",
            "tilted",
            "face_up",
            "face_down",
            "nfc_detected",
            "nfc_removed",
            "nfc_read_failed",
            "mic_overrun",
            "audio_playback_underrun",
            "audio_capture_started",
            "audio_capture_finished",
            "audio_capture_failed",
            "camera_capture_failed",
            "battery_low",
            "battery_recovered",
            "charging_started",
            "charging_stopped",
            "power_source_changed",
            "brownout_risk",
            "power_fault",
            "touched",
            "touch_released",
            "touch_held",
            "proximity_near",
            "proximity_clear",
            "light_changed",
            "dark_detected",
            "bright_detected",
            "remote_button_pressed",
            "remote_button_released",
            "remote_button_held",
            "remote_command_received",
            "ir_transmit_started",
            "ir_transmit_finished",
            "ir_transmit_failed",
            "transport_unstable",
            "firmware_ready",
        ):
            self.assertIn(f'"{name}"', events)

        self.assertIn("is_firmware_device_event_name", events)
        self.assertIn("event_payload_json_fits", events)
        self.assertIn("payload_json_exceeds_256_bytes", events)
        self.assertIn("make_string_payload", events)
        self.assertIn("payload_json_key_too_long", events)
        self.assertIn("max_value_length", events)
        self.assertIn("kFirmwareEventSource", events)
        self.assertIn("make_reference_payload", events)
        self.assertIn('"tag_ref"', events)
        self.assertIn('"remote_ref"', events)
        self.assertNotIn('"tag_id", tag_id', events)
        self.assertNotIn('"command", command', events)


if __name__ == "__main__":
    unittest.main()
