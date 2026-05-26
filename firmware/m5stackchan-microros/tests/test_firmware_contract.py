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
        self.assertIn("-DRMW_UXRCE_MAX_SERVICES=16", microros_meta)
        self.assertIn("-DRMW_UXRCE_MAX_PUBLISHERS=20", microros_meta)
        self.assertIn("-DRMW_UXRCE_MAX_SUBSCRIPTIONS=4", microros_meta)
        self.assertIn("-DRMW_UXRCE_MAX_CLIENTS=8", microros_meta)
        self.assertIn("-DRMW_UXRCE_MAX_HISTORY=16", microros_meta)
        self.assertIn("-DRMW_UXRCE_STREAM_HISTORY_INPUT=8", microros_meta)
        self.assertIn("-DRMW_UXRCE_STREAM_HISTORY_OUTPUT=8", microros_meta)
        self.assertIn("-DRMW_UXRCE_MAX_WAIT_SETS=8", microros_meta)
        self.assertIn("-DRMW_UXRCE_MAX_GUARD_CONDITION=8", microros_meta)
        self.assertIn("-DRMW_UXRCE_TOPIC_NAME_MAX_LENGTH=96", microros_meta)
        self.assertIn('"microxrcedds_client"', microros_meta)
        self.assertIn("-DUCLIENT_CUSTOM_TRANSPORT_MTU=1024", microros_meta)
        for helper_name in ("firmware_platformio.py", "firmware_container.py"):
            helper = (REPO_ROOT / "scripts" / helper_name).read_text()
            self.assertIn("-DRMW_UXRCE_MAX_SERVICES=16", helper)
            self.assertIn("-DRMW_UXRCE_MAX_PUBLISHERS=20", helper)
            self.assertIn("-DRMW_UXRCE_MAX_SUBSCRIPTIONS=4", helper)
            self.assertIn("-DRMW_UXRCE_MAX_CLIENTS=8", helper)
            self.assertIn("-DRMW_UXRCE_MAX_HISTORY=16", helper)
            self.assertIn("-DRMW_UXRCE_STREAM_HISTORY_INPUT=8", helper)
            self.assertIn("-DRMW_UXRCE_STREAM_HISTORY_OUTPUT=8", helper)
            self.assertIn("-DRMW_UXRCE_MAX_WAIT_SETS=8", helper)
            self.assertIn("-DRMW_UXRCE_MAX_GUARD_CONDITION=8", helper)
            self.assertIn("-DRMW_UXRCE_TOPIC_NAME_MAX_LENGTH=96", helper)
            self.assertIn('"microxrcedds_client"', helper)
            self.assertIn("-DUCLIENT_CUSTOM_TRANSPORT_MTU=1024", helper)

    def test_device_scoped_action_names_fit_microros_topic_bound(self) -> None:
        meta = (ROOT / "microros_stackchan.meta").read_text()
        match = re.search(r"-DRMW_UXRCE_TOPIC_NAME_MAX_LENGTH=(\d+)", meta)
        self.assertIsNotNone(match)
        topic_name_max = int(match.group(1))
        action_names = [
            "/stackchan/default/device/audio/capture",
            "/stackchan/default/device/camera/capture",
            "/stackchan/default/device/audio/play",
        ]
        service_suffixes = [
            "/_action/send_goal",
            "/_action/get_result",
            "/_action/cancel_goal",
        ]

        for action_name in action_names:
            for suffix in service_suffixes:
                service_name = f"{action_name}{suffix}"
                request_topic = f"rq{service_name}Request"
                reply_topic = f"rr{service_name}Reply"
                self.assertLess(len(request_topic), topic_name_max)
                self.assertLess(len(reply_topic), topic_name_max)

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
        loop_body = main[
            main.find("M5.update();", main.find("void loop() {")) :
        ]
        self.assertLess(loop_body.find("step_motion_scheduler(now);"), loop_body.find("update_servo_health_cache(now);"))
        self.assertLess(loop_body.find("step_motion_scheduler(now);"), loop_body.find("publish_status_heartbeat();"))
        self.assertLess(loop_body.find("step_motion_scheduler(now);"), loop_body.find("spin_command_executor();"))
        self.assertLess(loop_body.find("poll_capture_audio_action_server();"), loop_body.find("spin_command_executor();"))
        self.assertLess(loop_body.find("poll_play_audio_action_server();"), loop_body.find("spin_command_executor();"))
        self.assertLess(loop_body.find("spin_command_executor();"), loop_body.find("poll_capture_camera_action_server();"))
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

    def test_led_commands_route_to_k151_rgb_adapter(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()
        meta = (ROOT / "microros_stackchan.meta").read_text()
        smoke = (REPO_ROOT / "scripts" / "microros_agent_container.py").read_text()

        self.assertIn("#include <stackchan_msgs/srv/set_led.h>", main)
        self.assertIn("/stackchan/%s/device/led/set", main)
        self.assertIn("rcl_service_t led_set_service", main)
        self.assertIn("handle_led_set_service", main)
        self.assertIn("io_expander.setLedCount(kRgbLedCount)", main)
        self.assertIn("io_expander.setLedColor", main)
        self.assertIn("io_expander.refreshLeds()", main)
        self.assertIn('"progress"', main)
        self.assertIn('"listening"', main)
        self.assertIn("-DRMW_UXRCE_MAX_SERVICES=16", meta)
        self.assertIn("--led-check", smoke)
        self.assertIn("STACKCHAN_BRIDGE_LED_${{led_pattern}}_OK", smoke)
        self.assertIn("publish_status_heartbeat();", main)
        for face in ["happy", "thinking", "surprised", "sleepy", "error"]:
            self.assertIn(f'strcmp(name, "{face}") == 0', main)

    def test_raw_imu_stream_publishes_on_device_topic(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()
        publishers = (ROOT / "include" / "stackchan" / "ros_publishers.hpp").read_text()
        meta = (ROOT / "microros_stackchan.meta").read_text()

        self.assertIn("#include <stackchan_msgs/msg/imu_raw.h>", main)
        self.assertIn('constexpr const char* kDeviceImuRawTopicSuffix = "/device/imu/raw"', publishers)
        self.assertIn("DevicePublisherTopic::ImuRaw", publishers)
        self.assertIn("kDeviceImuRawQos", publishers)
        self.assertIn("publish_imu_raw", publishers)
        self.assertIn("stackchan_msgs__msg__ImuRaw imu_raw_ros_message", main)
        self.assertIn("rcl_publisher_t imu_raw_ros_publisher", main)
        self.assertIn("convert_imu_raw_message", main)
        self.assertIn("publish_imu_raw_sample(sample, now_ms)", main)
        self.assertIn("ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, ImuRaw)", main)
        self.assertIn("-DRMW_UXRCE_MAX_PUBLISHERS=20", meta)
        self.assertIn("-DRMW_UXRCE_MAX_SUBSCRIPTIONS=4", meta)
        self.assertIn("-DRMW_UXRCE_MAX_HISTORY=16", meta)
        self.assertIn("-DRMW_UXRCE_MAX_WAIT_SETS=8", meta)
        self.assertIn("-DRMW_UXRCE_MAX_GUARD_CONDITION=8", meta)
        self.assertIn("-DRMW_UXRCE_TOPIC_NAME_MAX_LENGTH=96", meta)

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

    def test_audio_contract_cpp_harness(self) -> None:
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("C++ compiler not available")

        binary = ROOT / "tests" / "audio_contract_test"
        source = ROOT / "tests" / "audio_contract_test.cpp"
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
        self.assertIn("if (!result.ok && microros_publish_failures_exceeded())", main)
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
        self.assertIn("AudioPlaybackChunkGuard", audio)
        self.assertIn('"audio playback chunk arrived without an accepted session"', audio)
        self.assertIn('"AUDIO_UNDERRUN"', audio)

    def test_audio_capture_chunk_timeout_returns_structured_result(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()
        audio = (ROOT / "include" / "stackchan" / "audio.hpp").read_text()
        events = (ROOT / "include" / "stackchan" / "events.hpp").read_text()

        self.assertIn("kAudioCaptureChunkTimeoutMs", main)
        self.assertIn("kAudioCaptureChunkMs = stackchan::kAudioChunkMs", main)
        self.assertIn("stackchan::kAudioChunkBytes", main)
        self.assertIn("kAudioPlaybackNoChunkTimeoutMs = 6000", main)
        self.assertIn("kAudioPlaybackMaxSpeakerDrainMs", main)
        self.assertIn("kAudioPlaybackPendingGapTimeoutMs = 3000", main)
        self.assertIn("kAudioPlaybackPendingChunkSlots = 24", main)
        self.assertIn("kAudioPlaybackPendingChunkBytes = stackchan::kAudioChunkBytes", main)
        self.assertIn("kAudioPlaybackLoadBufferBytes = 16 * 1024", main)
        self.assertIn("kAudioPlaybackInterChunkTimeoutMs = 6000", main)
        self.assertIn("kAudioPlaybackPullFallbackIdleMs = 450", main)
        self.assertIn("kAudioPlaybackPullTimeoutMs = 1000", main)
        self.assertNotIn("play_audio_last_chunk_ms = now_ms;", main)
        self.assertIn("play_audio_end_of_stream_seen", main)
        self.assertIn("const bool waiting_for_gap = play_audio_pending_chunk_count > 0;", main)
        self.assertIn("if (!waiting_for_gap &&", main)
        self.assertIn("audio_chunk_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT", main)
        self.assertIn(
            "audio_playback_chunk_qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE",
            main,
        )
        self.assertIn(
            "core_audio_playback_chunk_qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE",
            main,
        )
        self.assertIn("audio_playback_chunk_topic_name", main)
        self.assertIn('"/stackchan/%s/device/audio/playback/chunks"', main)
        self.assertIn("#include <stackchan_msgs/srv/next_audio_chunk.h>", main)
        self.assertIn("#include <stackchan_msgs/srv/load_audio_chunk.h>", main)
        self.assertIn("rcl_client_t audio_playback_chunk_client", main)
        self.assertIn("rcl_service_t audio_playback_load_service", main)
        self.assertIn("ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, NextAudioChunk)", main)
        self.assertIn("ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, LoadAudioChunk)", main)
        self.assertIn('"/stackchan/%s/audio/playback/next_chunk"', main)
        self.assertIn('"/stackchan/%s/device/audio/playback/load"', main)
        self.assertIn("rclc_executor_add_client", main)
        self.assertIn("rclc_executor_add_service", main)
        self.assertIn("core_executor_handles += 2", main)
        self.assertIn("microros_support.context,\n                  7,", main)
        self.assertIn("request_next_play_audio_chunk", main)
        self.assertIn("handle_audio_playback_chunk_response", main)
        self.assertIn("handle_audio_playback_load_service", main)
        self.assertIn("goal.first_chunk_present", main)
        self.assertIn("goal.first_chunk_sequence != 0", main)
        self.assertIn("request.goal.first_chunk_present", main)
        self.assertIn("accept_play_audio_pcm_chunk(", main)
        self.assertIn("&play_audio_goal_request.goal.first_chunk_pcm", main)
        self.assertIn("duplicate_chunk", audio)
        self.assertIn('"chunk_duplicate_ignored"', main)
        self.assertIn("audio_playback_diag", main)
        self.assertIn("play_audio_chunks_seen", main)
        self.assertIn("play_audio_chunks_accepted", main)
        self.assertIn("play_audio_chunks_rejected", main)
        self.assertIn("kAudioPlaybackSpeakerFrameSamples", main)
        self.assertIn("prepare_play_audio_speaker", main)
        self.assertIn("M5.Mic.end();", main)
        self.assertIn("M5.Speaker.begin()", main)
        self.assertIn("M5.Speaker.setVolume(kAudioPlaybackSpeakerVolume)", main)
        self.assertIn("append_play_audio_pcm_to_speaker_frames", main)
        self.assertIn("queue_play_audio_speaker_frame", main)
        self.assertIn("play_audio_speaker_queue_has_room", main)
        self.assertIn("PlayAudioPendingChunk", main)
        self.assertIn("play_audio_loaded_buffer", main)
        self.assertIn("step_loaded_play_audio_playback", main)
        self.assertIn("const bool use_loaded_playback", main)
        self.assertIn("reset_play_audio_loaded_buffer();", main)
        self.assertIn("log_play_audio_load_diagnostic", main)
        self.assertIn("audio_playback_load", main)
        self.assertIn('"loaded_playback_started"', main)
        self.assertIn('"loaded_playback_drained"', main)
        self.assertIn("buffer_play_audio_pending_chunk", main)
        self.assertIn("drain_play_audio_pending_chunks", main)
        self.assertIn("validate_play_audio_chunk_shape", main)
        self.assertIn("delay(play_audio_goal_active ? 1 : 10)", main)
        self.assertIn("!STACKCHAN_MICROROS_CORE_MEDIA_BRINGUP", main)
        self.assertIn("audio_playback_action", main)
        self.assertIn("audio_playback_chunk", main)
        self.assertIn("event_publisher.publish_name(", main)
        self.assertIn('"audio_playback_action"', events)
        self.assertIn('"audio_playback_chunk"', events)
        self.assertIn('"audio_playback_load"', events)
        self.assertIn('"goal_request_taken"', main)
        self.assertIn('"goal_response_sent"', main)
        self.assertIn('"first_goal_chunk_dispatch"', main)
        self.assertIn('"result_ready"', main)
        self.assertIn('"result_request_taken"', main)
        self.assertIn('"result_response_sent"', main)
        self.assertIn('"pull_requested"', main)
        self.assertIn('"pull_response_null"', main)
        self.assertIn('"pull_response_without_active_goal"', main)
        self.assertIn('"pull_empty"', main)
        self.assertIn('"pull_end_of_stream"', main)
        self.assertIn('"chunk_without_active_goal"', main)
        self.assertIn('"chunk_accepted"', main)
        self.assertIn('"speaker_frame_queued"', main)
        self.assertIn('"speaker_partial_frame_queued"', main)
        self.assertIn('"speaker_frame_failed"', main)
        self.assertIn('"speaker_queue_full"', main)
        self.assertIn('"speaker_frame_backpressure"', main)
        self.assertIn('"speaker_drain_fallback"', main)
        self.assertIn('"chunk_buffered_out_of_order"', main)
        self.assertIn('"chunk_jitter_drained"', main)
        self.assertIn('"chunk_jitter_gap_timeout"', main)
        self.assertIn('"chunk_jitter_duplicate_ignored"', main)
        self.assertIn('"chunk_jitter_chunk_too_large"', main)
        self.assertIn('\\"seq\\"', main)
        self.assertIn('\\"bytes\\"', main)
        self.assertIn('\\"seen\\"', main)
        self.assertIn('\\"ok\\"', main)
        self.assertIn('\\"rej\\"', main)
        self.assertIn('\\"next\\"', main)
        self.assertIn('\\"frames\\"', main)
        self.assertIn('\\"jitter\\"', main)
        self.assertIn('"no_chunk_timeout"', main)
        self.assertIn('"inter_chunk_timeout"', main)
        self.assertIn("clear_stale_play_audio_chunk_request();\n  if (play_audio_received_chunk", main)
        self.assertIn("play_audio_end_of_stream_seen &&", main)
        self.assertNotIn("stackchan_diag_print(chunk->pcm.data", main)
        self.assertIn('"microphone record chunk timed out"', main)
        self.assertIn("audio_capture_failed_result", main)

    def test_firmware_status_reports_audio_capabilities(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()

        self.assertIn("stackchan_msgs__msg__CapabilityStatus", main)
        self.assertIn("status_capabilities_init", main)
        self.assertIn('"audio_playback"', main)
        self.assertIn('"audio_capture"', main)
        self.assertIn("stackchan_audio_playback_initialized", main)
        self.assertIn("stackchan_audio_capture_initialized", main)
        self.assertIn("stackchan_audio_playback_transport_initialized", main)
        self.assertIn("stackchan_audio_capture_transport_initialized", main)
        self.assertIn("stackchan_led_initialized", main)
        self.assertIn('"UNSUPPORTED_FEATURE"', main)

    def test_firmware_reserves_action_feedback_strings(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()

        self.assertIn("capacity > 160", main)
        self.assertIn("char reserve[161]", main)
        self.assertIn("memset(reserve, '.', capacity)", main)
        self.assertIn(
            "reserve_ros_string(&capture_audio_feedback_message.feedback.message, 160)",
            main,
        )
        self.assertIn(
            "reserve_ros_string(&capture_camera_feedback_message.feedback.message, 160)",
            main,
        )
        self.assertNotIn("capacity > 36", main)

    def test_serial_diagnostics_are_opt_in_on_microros_transport(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()

        self.assertIn("#define STACKCHAN_SERIAL_DIAGNOSTICS 0", main)
        self.assertIn("set_microros_serial_transports(Serial)", main)
        self.assertIn("void stackchan_diag_print", main)
        self.assertIn("void stackchan_diag_println", main)
        self.assertNotIn("Serial.print(\"stackchan", main)
        self.assertNotIn("Serial.println(\"stackchan", main)

    def test_sensor_input_diagnostic_profile_is_firmware_only(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()
        helper = (REPO_ROOT / "scripts" / "firmware_platformio.py").read_text()
        firmware_doc = (REPO_ROOT / "docs" / "firmware.md").read_text()
        hardware_doc = (REPO_ROOT / "docs" / "hardware-validation.md").read_text(encoding="utf-8")

        self.assertIn("#define STACKCHAN_SENSOR_INPUT_DIAGNOSTICS 0", main)
        self.assertIn(
            "Sensor input diagnostics require STACKCHAN_SERIAL_DIAGNOSTICS=1",
            main,
        )
        self.assertIn("print_sensor_input_diagnostics", main)
        self.assertIn("run_sensor_input_diagnostic_loop", main)
        self.assertIn("pre_m5_begin", main)
        self.assertIn("m5_begin_start", main)
        self.assertIn("touch_begin_start", main)
        self.assertIn("power_begin_start", main)
        self.assertIn("ltr553_begin_start", main)
        self.assertIn("return;", main)
        self.assertIn("stackchan sensor_input_diag ms=", main)
        self.assertIn("touch_zone_mask", main)
        self.assertIn("touch_i0", main)
        self.assertIn("ltr553_bus=in_i2c", main)
        self.assertIn("kLtr553I2cFreq = 100000", main)
        self.assertIn("M5.In_I2C.readRegister", main)
        self.assertIn("ltr553_part_id_read_ok", main)
        self.assertIn("ltr553_last_ps_read_ok", main)
        self.assertIn("ltr553_last_als_read_ok", main)
        self.assertIn("in_i2c_released_for_camera", main)
        self.assertIn("stackchan_in_i2c_released_for_camera = true;", main)
        self.assertIn("--sensor-input-diagnostics", helper)
        self.assertIn("STACKCHAN_SERIAL_DIAGNOSTICS=1", helper)
        self.assertIn("STACKCHAN_SENSOR_INPUT_DIAGNOSTICS=1", helper)
        self.assertIn("--sensor-input-diagnostics", firmware_doc)
        self.assertIn("sensor_input_diag", firmware_doc)
        self.assertIn("--sensor-input-diagnostics", hardware_doc)
        self.assertIn("sensor_input_diag", hardware_doc)

    def test_microros_publish_failures_are_debounced_before_disconnect(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()

        self.assertIn("kMicrorosMaxConsecutivePublishFailures = 3", main)
        self.assertIn("microros_consecutive_publish_failures", main)
        self.assertIn("record_microros_publish_failure();", main)
        self.assertIn("record_microros_publish_success();", main)
        self.assertIn("!result.ok && microros_publish_failures_exceeded()", main)

    def test_microros_minimal_bringup_profile_is_opt_in(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()
        helper = (REPO_ROOT / "scripts" / "firmware_platformio.py").read_text()

        self.assertIn("#define STACKCHAN_MICROROS_MINIMAL_BRINGUP 0", main)
        self.assertIn("#define STACKCHAN_MICROROS_BOARD_INIT_BRINGUP 0", main)
        self.assertIn("#define STACKCHAN_MICROROS_BOARD_INIT_STAGE 0", main)
        self.assertIn("#define STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP 0", main)
        self.assertIn("#define STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP 0", main)
        self.assertIn("#define STACKCHAN_MICROROS_CORE_AUDIO_CHUNK_BRINGUP 0", main)
        self.assertIn("#define STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP 0", main)
        self.assertIn("#define STACKCHAN_MICROROS_CORE_CAPTURE_CAMERA_BRINGUP 0", main)
        self.assertIn("#define STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP 0", main)
        self.assertIn("Select only one micro-ROS bring-up profile", main)
        self.assertIn("#if STACKCHAN_MICROROS_MINIMAL_BRINGUP", main)
        self.assertIn("void initialize_minimal_microros_bringup()", main)
        self.assertIn("initialize_minimal_microros_bringup();", main)
        self.assertIn("void initialize_board_init_microros_bringup()", main)
        self.assertIn("initialize_board_init_bringup_stage()", main)
        self.assertIn("initialize_board_init_microros_bringup();", main)
        self.assertIn("#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 1", main)
        self.assertIn("#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 14", main)
        self.assertIn("void initialize_touch_adapter()", main)
        self.assertIn("void initialize_power_monitor_adapter()", main)
        self.assertIn("void initialize_ir_adapter()", main)
        self.assertIn("void initialize_audio_probe_adapters()", main)
        self.assertIn("stackchan_camera_snapshot_initialized = initialize_camera_adapter()", main)
        minimal_setup = main[
            main.find("#if STACKCHAN_MICROROS_MINIMAL_BRINGUP", main.find("void setup()"))
            : main.find("#endif", main.find("initialize_minimal_microros_bringup();"))
        ]
        self.assertIn("return;", minimal_setup)
        minimal_loop = main[
            main.find("#if STACKCHAN_MICROROS_MINIMAL_BRINGUP", main.find("void loop()"))
            : main.find("#endif", main.find("delay(10);"))
        ]
        self.assertIn("try_connect_microros_agent()", minimal_loop)
        self.assertIn("publish_status_heartbeat();", minimal_loop)
        self.assertIn("return;", minimal_loop)
        self.assertIn("#if STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP", main)
        self.assertIn("#if STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP", main)
        self.assertIn("#if STACKCHAN_MICROROS_CORE_AUDIO_SUBSCRIPTION_BRINGUP", main)
        self.assertIn("#if STACKCHAN_MICROROS_CORE_CAPTURE_CAMERA_BRINGUP", main)
        self.assertIn("rcl_action_server_options_t stackchan_action_server_options()", main)
        self.assertIn("options.goal_service_qos.depth = 1;", main)
        self.assertIn("options.cancel_service_qos.depth = 1;", main)
        self.assertIn("options.result_service_qos.depth = 1;", main)
        self.assertIn("options.feedback_topic_qos.reliability =", main)
        self.assertIn("options.status_topic_qos.reliability =", main)
        self.assertIn("options.status_topic_qos.durability =", main)
        self.assertIn("options.feedback_topic_qos.depth = 1;", main)
        self.assertIn("options.status_topic_qos.depth = 1;", main)
        self.assertIn("stackchan_action_server_options();", main)
        self.assertIn("bool try_initialize_capture_audio_action_server", main)
        self.assertIn("bool try_initialize_capture_camera_action_server", main)
        self.assertIn("bool try_initialize_play_audio_action_server", main)
        self.assertIn("(void)try_initialize_capture_audio_action_server", main)
        self.assertIn("capture_audio_action_init_failed = true;", main)
        self.assertIn("capture_camera_action_init_failed = true;", main)
        self.assertIn("play_audio_action_init_failed = true;", main)
        self.assertIn('"TRANSPORT_INIT_FAILED"', main)
        self.assertIn("audio_capture_unavailable_detail_code()", main)
        self.assertIn("camera_snapshot_unavailable_detail_code()", main)
        self.assertIn("capture_audio_action_server_initialized &&", main)
        self.assertIn("play_audio_action_server_initialized &&", main)
        self.assertIn("capture_camera_action_server_initialized,", main)
        self.assertIn("status_publisher_init", main)
        self.assertIn("stackchan_msgs__msg__StackChanStatus__init(&status_ros_message)", main)
        self.assertIn("--microros-minimal-bringup", helper)
        self.assertIn("--microros-board-init-bringup", helper)
        self.assertIn("--board-init-stage", helper)
        self.assertIn("--microros-core-command-bringup", helper)
        self.assertIn("--microros-core-raw-telemetry-bringup", helper)
        self.assertIn("--microros-core-audio-chunk-bringup", helper)
        self.assertIn("--microros-core-capture-audio-bringup", helper)
        self.assertIn("--microros-core-capture-camera-bringup", helper)
        self.assertIn("--microros-core-play-audio-bringup", helper)
        self.assertIn("STACKCHAN_MICROROS_MINIMAL_BRINGUP=1", helper)
        self.assertIn("STACKCHAN_MICROROS_BOARD_INIT_BRINGUP=1", helper)
        self.assertIn("STACKCHAN_MICROROS_BOARD_INIT_STAGE=", helper)
        self.assertIn("STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP=1", helper)
        self.assertIn("STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP=1", helper)
        self.assertIn("STACKCHAN_MICROROS_CORE_AUDIO_CHUNK_BRINGUP=1", helper)
        self.assertIn("STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP=1", helper)
        self.assertIn("STACKCHAN_MICROROS_CORE_CAPTURE_CAMERA_BRINGUP=1", helper)
        self.assertIn("STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP=1", helper)

    def test_firmware_camera_capture_action_is_bounded_and_redacted(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()

        self.assertIn("#include <esp_camera.h>", main)
        self.assertIn("#include <img_converters.h>", main)
        self.assertIn("#include <stackchan_msgs/action/capture_camera.h>", main)
        self.assertIn("CaptureCamera_SendGoal_Request", main)
        self.assertIn("build_capture_camera_action_name", main)
        self.assertIn('"/stackchan/%s/device/camera/capture"', main)
        self.assertIn("ROSIDL_GET_ACTION_TYPE_SUPPORT(stackchan_msgs, CaptureCamera)", main)
        self.assertIn("stackchan_camera_snapshot_initialized = initialize_camera_adapter()", main)
        self.assertIn("PIXFORMAT_JPEG", main)
        self.assertIn("FRAMESIZE_QVGA", main)
        self.assertIn("CAMERA_GRAB_LATEST", main)
        self.assertIn("camera_driver_quality_from_goal", main)
        self.assertIn("frame2jpg", main)
        self.assertIn("stackchan::validate_camera_quality(goal.quality)", main)
        self.assertIn("stackchan::kCameraMaxPayloadBytes", main)
        self.assertIn("camera JPEG payload exceeds 96 KiB", main)
        self.assertIn("clear_capture_camera_image_result", main)
        self.assertIn("CameraCaptureFailed", main)
        self.assertNotIn("Serial.print(jpeg_buffer", main)
        self.assertNotIn("Serial.println(jpeg_buffer", main)

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

    def test_k151_event_adapters_are_wired_without_raw_payload_logging(self) -> None:
        main = (ROOT / "src" / "main.cpp").read_text()
        events = (ROOT / "include" / "stackchan" / "events.hpp").read_text()
        publishers = (ROOT / "include" / "stackchan" / "ros_publishers.hpp").read_text()
        sweep = (REPO_ROOT / "scripts" / "microros_agent_container.py").read_text()

        self.assertIn("#include <M5UnitUnifiedNFC.h>", main)
        self.assertIn("#include <IRrecv.h>", main)
        self.assertIn("stackchan::ImuEventEstimator imu_event_estimator", main)
        self.assertIn("stackchan::TouchEventEstimator touch_event_estimator", main)
        self.assertIn("stackchan::ProximityEventEstimator proximity_event_estimator", main)
        self.assertIn("stackchan::LightEventEstimator light_event_estimator", main)
        self.assertIn("stackchan::PowerEventEstimator power_event_estimator", main)
        self.assertIn("stackchan::ButtonEventEstimator button_a_event_estimator", main)
        self.assertIn("stackchan::ButtonEventEstimator button_b_event_estimator", main)
        self.assertIn("stackchan::ButtonEventEstimator button_c_event_estimator", main)
        self.assertIn("stackchan::NfcPresenceEstimator nfc_presence_estimator", main)
        self.assertIn("M5.update();", main)
        self.assertIn("sample_button_events(now_ms)", main)
        self.assertIn("M5.BtnA.isPressed()", main)
        self.assertIn("M5.BtnB.isPressed()", main)
        self.assertIn("M5.BtnC.isPressed()", main)
        self.assertIn("m5::nfc::NFCLayerA stackchan_nfc_a", main)
        self.assertIn("initialize_nfc_adapter", main)
        self.assertIn("m5::pin_name_t::in_i2c_sda", main)
        self.assertIn("stackchan_nfc_i2c_present", main)
        self.assertIn("in_i2c", main)
        self.assertIn("M5.In_I2C", main)
        self.assertIn("stackchan_nfc_bus", main)
        self.assertIn("stackchan_nfc_detect_attempts", main)
        self.assertIn("stackchan_nfc_detect_hits", main)
        self.assertIn("stackchan_nfc_identify_failures", main)
        self.assertIn("constexpr uint16_t kIrRecvPin = 10", main)
        self.assertIn("stackchan_irrecv.enableIRIn()", main)
        self.assertIn("stackchan_ir_decode_count", main)
        self.assertIn("stackchan_ir_overflow_count", main)
        self.assertIn("sample_imu_events", main)
        self.assertIn("touch_event_estimator.update(telemetry, event_publisher)", main)
        self.assertIn("proximity_event_estimator.update(telemetry, event_publisher)", main)
        self.assertIn("light_event_estimator.update(telemetry, event_publisher)", main)
        self.assertIn("power_event_estimator.update(telemetry, event_publisher)", main)
        self.assertIn("sample_nfc_events", main)
        self.assertIn("sample_ir_events", main)
        self.assertIn("uidAsString", main)
        self.assertIn("remote_command_received(now_ms, remote_summary)", main)
        self.assertIn("should_sample_imu", publishers)
        self.assertIn("should_sample_nfc", publishers)
        self.assertIn("Result remote_button_pressed", events)
        self.assertIn("Result remote_button_released", events)
        self.assertIn("Result ir_transmit_started", events)
        self.assertIn("Result ir_transmit_finished", events)
        self.assertIn("Result ir_transmit_failed", events)
        self.assertNotIn("ir-transmit", (REPO_ROOT / "apps" / "stackchanctl" / "src" / "stackchanctl" / "contract.py").read_text())
        self.assertIn("StackChan-BSP", (ROOT / "platformio.ini").read_text())
        self.assertNotIn("Serial.println(event.payload_json)", main)
        self.assertNotIn("Serial.print(stackchan_ir_results.value)", main)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_UNSUPPORTED_SEEN", sweep)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_OK_SEEN", sweep)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OK_SEEN", sweep)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_UNSUPPORTED_SEEN", sweep)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN", sweep)
        self.assertIn("--skip-media-smoke", sweep)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_MEDIA_SMOKE_SKIPPED", sweep)
        self.assertIn("STACKCHAN_EVENT_STIMULUS_WINDOW_RAN", sweep)
        self.assertIn("run_live_stimulus_capture", sweep)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_LIVE_TOUCH_ACTIVE_SEEN", sweep)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_LIVE_PROXIMITY_NONZERO_SEEN", sweep)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_LIVE_LIGHT_NONZERO_SEEN", sweep)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_LIVE_POWER_SAMPLE_SEEN", sweep)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_LIVE_EVENT_SAMPLE_SEEN", sweep)
        self.assertIn("STACKCHAN_EVENT_STIMULUS_${{slug}}_STATUS=NOT_RUN", sweep)
        self.assertIn('classify_event_stimulus "TOUCH"', sweep)
        self.assertIn('classify_event_stimulus "PROXIMITY"', sweep)
        self.assertIn('classify_event_stimulus "LIGHT"', sweep)
        self.assertIn('classify_event_stimulus "POWER"', sweep)

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
