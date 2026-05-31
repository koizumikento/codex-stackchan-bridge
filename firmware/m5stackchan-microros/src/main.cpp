#include <Arduino.h>
#include <IRrecv.h>
#include <IRremoteESP8266.h>
#include <IRutils.h>
#include <M5Unified.hpp>
#include <M5UnitUnified.h>
#include <M5UnitUnifiedNFC.h>
#include <Preferences.h>
#include <Wire.h>
#include <drivers/FTServo_Arduino/src/SCSCL.h>
#include <drivers/PY32IOExpander/PY32IOExpander.hpp>
#include <esp_camera.h>
#include <utility/power/INA226_Class.hpp>
#include <utils/touch_sensor/touch_sensor.h>
#include <img_converters.h>
#include <math.h>
#include <micro_ros_platformio.h>
#include <rcl/client.h>
#include <rcl/error_handling.h>
#include <rcl/publisher.h>
#include <rcl/service.h>
#include <rcl/subscription.h>
#include <rcl/time.h>
#include <rcl_action/rcl_action.h>
#include <rclc/node.h>
#include <rclc/client.h>
#include <rclc/executor.h>
#include <rclc/publisher.h>
#include <rclc/rclc.h>
#include <rclc/service.h>
#include <rclc/subscription.h>
#include <rmw/qos_profiles.h>
#include <rmw_microros/ping.h>
#include <rosidl_runtime_c/primitives_sequence_functions.h>
#include <rosidl_runtime_c/string_functions.h>
#include <stackchan_msgs/action/capture_audio.h>
#include <stackchan_msgs/action/capture_camera.h>
#include <stackchan_msgs/action/play_audio.h>
#include <stackchan_msgs/msg/audio_chunk.h>
#include <stackchan_msgs/msg/audio_playback_ack.h>
#include <stackchan_msgs/msg/camera_frame_chunk.h>
#include <stackchan_msgs/msg/capability_status.h>
#include <stackchan_msgs/msg/head_pose.h>
#include <stackchan_msgs/msg/imu_raw.h>
#include <stackchan_msgs/msg/light_raw.h>
#include <stackchan_msgs/msg/power_status.h>
#include <stackchan_msgs/msg/proximity_raw.h>
#include <stackchan_msgs/msg/stack_chan_event.h>
#include <stackchan_msgs/msg/stack_chan_status.h>
#include <stackchan_msgs/msg/touch_state.h>
#include <stackchan_msgs/srv/set_face.h>
#include <stackchan_msgs/srv/set_head_pose.h>
#include <stackchan_msgs/srv/set_led.h>
#include <stackchan_msgs/srv/set_motion.h>
#include <stackchan_msgs/srv/load_audio_chunk.h>
#include <stackchan_msgs/srv/next_audio_chunk.h>
#include <stdlib.h>
#include <string.h>
#include <vector>

#include "stackchan/adpcm.hpp"
#include "stackchan/audio.hpp"
#include "stackchan/calibration.hpp"
#include "stackchan/contract.hpp"
#include "stackchan/events.hpp"
#include "stackchan/motion_safety.hpp"
#include "stackchan/ros_publishers.hpp"
#include "stackchan/sensors.hpp"
#include "stackchan/state_machine.hpp"

#ifndef STACKCHAN_DEVICE_ID
#define STACKCHAN_DEVICE_ID "default"
#endif

#ifndef STACKCHAN_MICROROS_SERIAL_BAUD
#define STACKCHAN_MICROROS_SERIAL_BAUD 115200
#endif

#ifndef STACKCHAN_SERIAL_DIAGNOSTICS
#define STACKCHAN_SERIAL_DIAGNOSTICS 0
#endif

#ifndef STACKCHAN_SENSOR_INPUT_DIAGNOSTICS
#define STACKCHAN_SENSOR_INPUT_DIAGNOSTICS 0
#endif

#ifndef STACKCHAN_MOTION_DIAGNOSTICS
#define STACKCHAN_MOTION_DIAGNOSTICS 0
#endif

#if STACKCHAN_SENSOR_INPUT_DIAGNOSTICS && !STACKCHAN_SERIAL_DIAGNOSTICS
#error "Sensor input diagnostics require STACKCHAN_SERIAL_DIAGNOSTICS=1"
#endif

#ifndef STACKCHAN_MICROROS_MINIMAL_BRINGUP
#define STACKCHAN_MICROROS_MINIMAL_BRINGUP 0
#endif

#ifndef STACKCHAN_MICROROS_BOARD_INIT_BRINGUP
#define STACKCHAN_MICROROS_BOARD_INIT_BRINGUP 0
#endif

#ifndef STACKCHAN_MICROROS_BOARD_INIT_STAGE
#define STACKCHAN_MICROROS_BOARD_INIT_STAGE 0
#endif

#ifndef STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP
#define STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP 0
#endif

#ifndef STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP
#define STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP 0
#endif

#ifndef STACKCHAN_MICROROS_CORE_AUDIO_CHUNK_BRINGUP
#define STACKCHAN_MICROROS_CORE_AUDIO_CHUNK_BRINGUP 0
#endif

#ifndef STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP
#define STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP 0
#endif

#ifndef STACKCHAN_MICROROS_CORE_CAPTURE_CAMERA_BRINGUP
#define STACKCHAN_MICROROS_CORE_CAPTURE_CAMERA_BRINGUP 0
#endif

#ifndef STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP
#define STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP 0
#endif

#if STACKCHAN_MICROROS_MINIMAL_BRINGUP && \
    (STACKCHAN_MICROROS_BOARD_INIT_BRINGUP || STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP)
#error "Select only one micro-ROS bring-up profile"
#endif

#if STACKCHAN_MICROROS_BOARD_INIT_BRINGUP && STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP
#error "Select only one micro-ROS bring-up profile"
#endif

#define STACKCHAN_MICROROS_CORE_AUDIO_TOPIC_BRINGUP \
  (STACKCHAN_MICROROS_CORE_AUDIO_CHUNK_BRINGUP || STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP)
#define STACKCHAN_MICROROS_CORE_AUDIO_SUBSCRIPTION_BRINGUP \
  (STACKCHAN_MICROROS_CORE_AUDIO_CHUNK_BRINGUP || STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP)
#define STACKCHAN_MICROROS_CORE_MEDIA_BRINGUP \
  (STACKCHAN_MICROROS_CORE_AUDIO_CHUNK_BRINGUP || \
   STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP || \
   STACKCHAN_MICROROS_CORE_CAPTURE_CAMERA_BRINGUP || \
   STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP)
#define STACKCHAN_MICROROS_STATUS_ONLY_BRINGUP \
  (STACKCHAN_MICROROS_MINIMAL_BRINGUP || STACKCHAN_MICROROS_BOARD_INIT_BRINGUP)

#if STACKCHAN_MICROROS_CORE_MEDIA_BRINGUP && !STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP
#error "Core media diagnostic profiles extend the core raw telemetry bring-up profile"
#endif

#ifndef STACKCHAN_CALIBRATION_SEED_HOME_X
#define STACKCHAN_CALIBRATION_SEED_HOME_X 0
#endif

#ifndef STACKCHAN_CALIBRATION_SEED_HOME_Y
#define STACKCHAN_CALIBRATION_SEED_HOME_Y 0
#endif

#ifndef STACKCHAN_CALIBRATION_SEED_CORRECTION_X
#define STACKCHAN_CALIBRATION_SEED_CORRECTION_X 0
#endif

#ifndef STACKCHAN_CALIBRATION_SEED_CORRECTION_Y
#define STACKCHAN_CALIBRATION_SEED_CORRECTION_Y 0
#endif

namespace {

template <typename T>
void stackchan_diag_print(const T& value) {
#if STACKCHAN_SERIAL_DIAGNOSTICS
  Serial.print(value);
#else
  (void)value;
#endif
}

template <typename T>
void stackchan_diag_println(const T& value) {
#if STACKCHAN_SERIAL_DIAGNOSTICS
  Serial.println(value);
#else
  (void)value;
#endif
}

void stackchan_diag_flush() {
#if STACKCHAN_SERIAL_DIAGNOSTICS
  Serial.flush();
#endif
}

stackchan::StateMachine state_machine;
char current_face[16] = "neutral";
char current_motion[16] = "idle";
char last_command_id[37] = "";
stackchan::Result last_error = stackchan::Result::accepted("ok");
unsigned long last_heartbeat_ms = 0;
unsigned long last_agent_attempt_ms = 0;
unsigned long microros_connected_since_ms = 0;
unsigned long last_bringup_event_enqueue_ms = 0;
unsigned long last_sensor_input_diag_ms = 0;
unsigned long last_sensor_input_diag_report_ms = 0;
unsigned long sensor_input_diag_stage_started_ms = 0;
constexpr uint8_t kMicrorosMaxConsecutivePublishFailures = 3;
bool microros_connected = false;
uint8_t sensor_input_diag_stage = 0;
uint8_t microros_bringup_event_enqueue_count = 0;
uint32_t microros_bringup_event_total_enqueue_count = 0;
uint32_t microros_publish_attempt_count = 0;
uint32_t microros_publish_ok_count = 0;
uint32_t microros_publish_failed_count = 0;
uint8_t microros_consecutive_publish_failures = 0;
rcl_ret_t last_microros_publish_result = RCL_RET_OK;
stackchan::CalibrationStore calibration_store;
const stackchan::AudioChunkPolicy audio_policy = stackchan::baseline_audio_policy();
stackchan::EventPublisher event_publisher(STACKCHAN_DEVICE_ID);
stackchan::DevicePublisherRegistry device_publishers;
stackchan::TelemetryPublishScheduler telemetry_publish_scheduler;
stackchan::TouchEventEstimator touch_event_estimator;
stackchan::ButtonEventEstimator button_a_event_estimator;
stackchan::ButtonEventEstimator button_b_event_estimator;
stackchan::ButtonEventEstimator button_c_event_estimator;
stackchan::ProximityEventEstimator proximity_event_estimator;
stackchan::LightEventEstimator light_event_estimator;
stackchan::PowerEventEstimator power_event_estimator;
stackchan::ImuEventEstimator imu_event_estimator;
stackchan::NfcPresenceEstimator nfc_presence_estimator;
SCSCL servo_bus;
m5::PY32IOExpander_Class io_expander;
m5::TouchSensor_Class stackchan_touch_sensor;
m5::INA226_Class stackchan_power_monitor(0x41);
m5::unit::UnitUnified stackchan_units;
m5::unit::UnitNFC stackchan_nfc_unit;
m5::nfc::NFCLayerA stackchan_nfc_a(stackchan_nfc_unit);
stackchan::Result calibration_load_result =
    stackchan::Result::rejected("CALIBRATION_INVALID", "calibration not loaded", true);
stackchan::Result calibration_maintenance_result =
    stackchan::Result::accepted("calibration maintenance inactive");
stackchan::Result servo_adapter_init_result =
    stackchan::Result::rejected("SERVO_READ_FAILED", "servo adapter not initialized", true);
constexpr size_t kEventDrainBudget = 2;
constexpr unsigned long kBringupEventDelayMs = 500;
constexpr unsigned long kBringupEventRetryMs = 1000;
constexpr uint8_t kBringupEventMaxEnqueues = 1;
constexpr unsigned long kServoHealthCheckIntervalMs = 100;
constexpr unsigned long kMotionFinalSettleMinMs = 250;
constexpr unsigned long kMotionFinalSettleTimeoutMs = 1200;
constexpr unsigned long kMotionSegmentTickIntervalMs = 25;
constexpr uint16_t kMotionSegmentTickServoTimeMs = 55;
constexpr uint16_t kShakeTrajectoryTickServoTimeMs = 160;
constexpr unsigned long kShakeTrajectoryDurationMs = 3000;
constexpr float kShakeTrajectoryCycles = 5.0f;
constexpr float kShakeTrajectoryYawAmplitudeDeg = 86.0f;
constexpr float kShakeTrajectoryYawTaperRatio = 0.12f;
constexpr float kShakeTrajectoryPitchBaseDeg = 8.0f;
constexpr float kShakeTrajectoryPitchAmplitudeDeg = 3.0f;
constexpr float kMotionPi = 3.14159265358979323846f;
constexpr unsigned long kAudioPlaybackNoChunkTimeoutMs = 6000;
constexpr unsigned long kAudioPlaybackDrainTimeoutMs = 180;
constexpr unsigned long kAudioPlaybackMaxSpeakerDrainMs = 1500;
constexpr unsigned long kAudioPlaybackInterChunkTimeoutMs = 6000;
constexpr unsigned long kAudioPlaybackPullIntervalMs = 2;
constexpr unsigned long kAudioPlaybackPullFallbackIdleMs = 450;
constexpr unsigned long kAudioPlaybackPullTimeoutMs = 2500;
constexpr unsigned long kAudioPlaybackAckPublishIntervalMs = 50;
constexpr unsigned long kAudioPlaybackPendingGapTimeoutMs = 5000;
constexpr unsigned long kAudioPlaybackTerminalStaleSuppressMs = 5000;
constexpr uint32_t kAudioPlaybackChunkDiagnosticSampleInterval = 16;
constexpr size_t kAudioPlaybackChunkSubscriptionDepth = 16;
#ifndef STACKCHAN_AUDIO_TOPIC_RELAY_EXTENDED_BUFFER
#define STACKCHAN_AUDIO_TOPIC_RELAY_EXTENDED_BUFFER 0
#endif
#if STACKCHAN_AUDIO_TOPIC_RELAY_EXTENDED_BUFFER
constexpr size_t kAudioPlaybackPendingChunkSlots = 24;
#else
constexpr size_t kAudioPlaybackPendingChunkSlots = 8;
#endif
constexpr size_t kAudioPlaybackPendingChunkBytes = stackchan::kAudioChunkBytes;
constexpr size_t kAudioPlaybackLoadBufferBytes = 32 * 1024;
constexpr uint8_t kAudioPlaybackSpeakerVolume = 192;
constexpr uint32_t kAudioPlaybackSpeakerFrameBytes = stackchan::kAudioChunkBytes;
constexpr uint32_t kAudioPlaybackSpeakerFrameSamples =
    kAudioPlaybackSpeakerFrameBytes / 2;
constexpr uint32_t kAudioCaptureMaxDurationMs = 15000;
constexpr uint32_t kAudioCaptureChunkTimeoutMs = 250;
constexpr uint32_t kAudioCaptureSessionTimeoutGraceMs = 5000;
constexpr uint32_t kAudioCaptureFeedbackEveryChunks = 10;
constexpr uint32_t kAudioCaptureChunkMs = stackchan::kAudioChunkMs;
constexpr uint32_t kAudioCaptureChunkSamples = stackchan::kAudioChunkBytes / 2;
constexpr uint32_t kCameraCaptureTimeoutMs = 2500;
constexpr uint8_t kCameraWarmupFrames = 3;
constexpr unsigned long kCameraWarmupFrameDelayMs = 100;
constexpr unsigned long kCameraWarmupMaxMs = 700;
constexpr unsigned long kCameraFrameChunkPublishIntervalMs = 4;
constexpr bool kCameraHorizontalMirror = false;
constexpr int kYawServoId = 1;
constexpr int kPitchServoId = 2;
constexpr int kYawDefaultZeroPos = 460;
constexpr int kPitchDefaultZeroPos = 620;
constexpr int kServoRawMin = 0;
constexpr int kServoRawMax = 1000;
constexpr int kServoTime = 140;
constexpr int kServoSpeed = 0;
constexpr int kServoUartBaud = 1000000;
constexpr int kServoTxPin = 6;
constexpr int kServoRxPin = 7;
constexpr uint8_t kRgbLedCount = 12;
constexpr uint16_t kIrRecvPin = 10;
constexpr uint16_t kIrCaptureBufferSize = 1024;
constexpr uint8_t kIrTimeoutMs = 15;
constexpr uint16_t kIrMinUnknownSize = 12;
constexpr uint8_t kIrTolerancePercentage = kTolerance;
constexpr uint8_t kCameraDriverBestQuality = 8;
constexpr uint8_t kCameraDriverLowestQuality = 48;
constexpr unsigned long kIoExpanderInitTimeoutMs = 1200;
constexpr uint8_t kLtr553Address = 0x23;
constexpr uint8_t kLtr553AlsContr = 0x80;
constexpr uint8_t kLtr553PsContr = 0x81;
constexpr uint8_t kLtr553PsMeasRate = 0x84;
constexpr uint8_t kLtr553AlsMeasRate = 0x85;
constexpr uint8_t kLtr553PartId = 0x86;
constexpr uint8_t kLtr553ManufacturerId = 0x87;
constexpr uint8_t kLtr553AlsDataCh1Low = 0x88;
constexpr uint8_t kLtr553PsDataLow = 0x8D;
constexpr uint8_t kLtr553ExpectedManufacturerId = 0x05;
constexpr uint32_t kLtr553I2cFreq = 100000;
constexpr float kLtr553PsFullScale = 2047.0f;
constexpr float kLtr553AlsIntegrationFactor = 2.0f;
enum class MotionSchedulerPhase {
  Idle,
  ShakeTrajectory,
  MoveWaypoint,
  HoldWaypoint,
  ReturnHome,
  FinalSettle,
};

struct MotionSchedulerJob {
  bool active;
  MotionSchedulerPhase phase;
  stackchan::ServoTarget home;
  stackchan::MotionWaypoint waypoints[stackchan::kMaxMotionWaypoints];
  size_t waypoint_count;
  size_t waypoint_index;
  uint16_t servo_time_ms;
  bool segment_initialized;
  stackchan::ServoTarget segment_start;
  stackchan::ServoTarget segment_end;
  stackchan::MotionEasing segment_easing;
  uint16_t segment_duration_ms;
  unsigned long segment_started_ms;
  unsigned long last_retarget_ms;
  unsigned long phase_started_ms;
  char name[16];
  char command_id[37];
};

struct PlayAudioPendingChunk {
  bool occupied;
  uint32_t sequence;
  uint8_t format;
  uint32_t sample_rate;
  uint8_t channels;
  uint16_t pcm_size;
  uint32_t received_ms;
  char command_id[37];
  uint8_t pcm[kAudioPlaybackPendingChunkBytes];
};

MotionSchedulerJob motion_scheduler{
    false,
    MotionSchedulerPhase::Idle,
    stackchan::kNeutralTarget,
    {},
    0,
    0,
    stackchan::kDefaultNamedMotionServoTimeMs,
    false,
    stackchan::kNeutralTarget,
    stackchan::kNeutralTarget,
    stackchan::MotionEasing::EaseInOutCubic,
    stackchan::kDefaultNamedMotionServoTimeMs,
    0,
    0,
    0,
    "",
    "",
};
bool microros_transport_configured = false;
bool microros_entities_initialized = false;
bool servo_position_read_available_cache = false;
bool motion_status_publish_pending = false;
struct MotionDiagnosticSummary {
  bool active;
  char name[16];
  char command_id[stackchan::kEventCommandIdMaxLength + 1];
  int home_x;
  int home_y;
  int plan_min_x;
  int plan_max_x;
  int plan_min_y;
  int plan_max_y;
  int target_min_x;
  int target_max_x;
  int target_min_y;
  int target_max_y;
  int raw_min_x;
  int raw_max_x;
  int raw_min_y;
  int raw_max_y;
  int time_min_ms;
  int time_max_ms;
  uint32_t write_count;
};
MotionDiagnosticSummary motion_diagnostic{};
unsigned long last_servo_health_check_ms = 0;
rcl_allocator_t microros_allocator;
rclc_support_t microros_support;
rcl_node_t microros_node;
rcl_publisher_t event_ros_publisher;
rcl_publisher_t imu_raw_ros_publisher;
rcl_publisher_t light_raw_ros_publisher;
rcl_publisher_t motion_pose_ros_publisher;
rcl_publisher_t power_status_ros_publisher;
rcl_publisher_t proximity_raw_ros_publisher;
rcl_publisher_t status_ros_publisher;
rcl_publisher_t touch_state_ros_publisher;
rcl_publisher_t audio_chunk_ros_publisher;
rcl_publisher_t audio_playback_ack_ros_publisher;
rcl_publisher_t camera_frame_chunk_ros_publisher;
rcl_subscription_t audio_chunk_subscription;
rcl_client_t audio_playback_chunk_client;
rcl_service_t audio_playback_load_service;
rcl_action_server_t capture_audio_action_server;
rcl_action_server_t capture_camera_action_server;
rcl_action_server_t play_audio_action_server;
rcl_service_t face_set_service;
rcl_service_t head_pose_set_service;
rcl_service_t led_set_service;
rcl_service_t motion_set_service;
rclc_executor_t microros_executor;
stackchan_msgs__msg__StackChanEvent event_ros_message;
stackchan_msgs__msg__HeadPose motion_pose_ros_message;
stackchan_msgs__msg__ImuRaw imu_raw_ros_message;
stackchan_msgs__msg__LightRaw light_raw_ros_message;
stackchan_msgs__msg__PowerStatus power_status_ros_message;
stackchan_msgs__msg__ProximityRaw proximity_raw_ros_message;
stackchan_msgs__msg__StackChanStatus status_ros_message;
stackchan_msgs__msg__TouchState touch_state_ros_message;
stackchan_msgs__msg__AudioChunk audio_chunk_ros_message;
stackchan_msgs__msg__AudioChunk audio_capture_chunk_ros_message;
stackchan_msgs__msg__AudioPlaybackAck audio_playback_ack_ros_message;
stackchan_msgs__msg__CameraFrameChunk camera_frame_chunk_ros_message;
stackchan_msgs__action__CaptureAudio_SendGoal_Request capture_audio_goal_request;
stackchan_msgs__action__CaptureAudio_SendGoal_Response capture_audio_goal_response;
stackchan_msgs__action__CaptureAudio_GetResult_Request capture_audio_result_request;
stackchan_msgs__action__CaptureAudio_GetResult_Response capture_audio_result_response;
stackchan_msgs__action__CaptureAudio_FeedbackMessage capture_audio_feedback_message;
stackchan_msgs__action__CaptureCamera_SendGoal_Request capture_camera_goal_request;
stackchan_msgs__action__CaptureCamera_SendGoal_Response capture_camera_goal_response;
stackchan_msgs__action__CaptureCamera_GetResult_Request capture_camera_result_request;
stackchan_msgs__action__CaptureCamera_GetResult_Response capture_camera_result_response;
stackchan_msgs__action__CaptureCamera_FeedbackMessage capture_camera_feedback_message;
stackchan_msgs__action__PlayAudio_SendGoal_Request play_audio_goal_request;
stackchan_msgs__action__PlayAudio_SendGoal_Response play_audio_goal_response;
stackchan_msgs__action__PlayAudio_GetResult_Request play_audio_result_request;
stackchan_msgs__action__PlayAudio_GetResult_Response play_audio_result_response;
stackchan_msgs__srv__NextAudioChunk_Request audio_playback_chunk_request;
stackchan_msgs__srv__NextAudioChunk_Response audio_playback_chunk_response;
stackchan_msgs__srv__LoadAudioChunk_Request audio_playback_load_request;
stackchan_msgs__srv__LoadAudioChunk_Response audio_playback_load_response;
stackchan_msgs__srv__SetFace_Request face_set_request;
stackchan_msgs__srv__SetFace_Response face_set_response;
stackchan_msgs__srv__SetHeadPose_Request head_pose_set_request;
stackchan_msgs__srv__SetHeadPose_Response head_pose_set_response;
stackchan_msgs__srv__SetLed_Request led_set_request;
stackchan_msgs__srv__SetLed_Response led_set_response;
stackchan_msgs__srv__SetMotion_Request motion_set_request;
stackchan_msgs__srv__SetMotion_Response motion_set_response;
char microros_node_namespace[64] = "";
char face_set_service_name[96] = "";
char head_pose_set_service_name[96] = "";
char led_set_service_name[96] = "";
char motion_set_service_name[96] = "";
char audio_chunk_topic_name[96] = "";
char audio_playback_chunk_topic_name[96] = "";
char audio_playback_ack_topic_name[96] = "";
char camera_frame_chunk_topic_name[96] = "";
char audio_playback_chunk_service_name[96] = "";
char audio_playback_load_service_name[96] = "";
char capture_audio_action_name[96] = "";
char capture_camera_action_name[96] = "";
char play_audio_action_name[96] = "";
bool microros_executor_initialized = false;
bool capture_audio_action_server_initialized = false;
bool capture_camera_action_server_initialized = false;
bool play_audio_action_server_initialized = false;
bool audio_playback_load_service_initialized = false;
bool capture_audio_action_init_failed = false;
bool capture_camera_action_init_failed = false;
bool play_audio_action_init_failed = false;
bool stackchan_touch_sensor_initialized = false;
bool stackchan_touch_output_read_ok = false;
uint8_t stackchan_touch_output_raw = 0;
uint32_t stackchan_touch_output_read_failures = 0;
bool stackchan_power_monitor_initialized = false;
bool ltr553_sensor_initialized = false;
bool ltr553_part_id_read_ok = false;
bool ltr553_manufacturer_id_read_ok = false;
uint8_t ltr553_part_id = 0;
uint8_t ltr553_manufacturer_id = 0;
bool ltr553_last_ps_read_ok = false;
bool ltr553_last_als_read_ok = false;
bool stackchan_led_initialized = false;
bool stackchan_imu_initialized = false;
bool stackchan_nfc_initialized = false;
bool stackchan_ir_initialized = false;
bool stackchan_audio_playback_initialized = false;
bool stackchan_audio_capture_initialized = false;
bool stackchan_audio_playback_transport_initialized = false;
bool stackchan_audio_capture_transport_initialized = false;
bool stackchan_camera_snapshot_initialized = false;
bool stackchan_in_i2c_released_for_camera = false;
camera_config_t stackchan_camera_config;
sensor_t* stackchan_camera_sensor = nullptr;
esp_err_t stackchan_camera_init_error = ESP_OK;
char stackchan_nfc_bus[24] = "uninitialized";
int8_t stackchan_nfc_sda_pin = -1;
int8_t stackchan_nfc_scl_pin = -1;
bool stackchan_nfc_i2c_present = false;
uint32_t stackchan_nfc_detect_attempts = 0;
uint32_t stackchan_nfc_detect_hits = 0;
uint32_t stackchan_nfc_identify_failures = 0;
uint32_t stackchan_ir_decode_count = 0;
uint32_t stackchan_ir_overflow_count = 0;
IRrecv stackchan_irrecv(kIrRecvPin, kIrCaptureBufferSize, kIrTimeoutMs, true);
decode_results stackchan_ir_results;
stackchan::AudioPlaybackChunkGuard audio_playback_guard;
bool audio_capture_session_active = false;
char audio_capture_command_id[37]{};
uint32_t audio_capture_duration_ms = 0;
uint32_t audio_capture_started_ms = 0;
uint32_t audio_capture_last_chunk_ms = 0;
uint32_t audio_capture_sequence = 0;
uint32_t audio_capture_target_chunks = 0;
uint32_t audio_capture_published_chunks = 0;
uint8_t audio_capture_buffer_index = 0;
bool audio_capture_recording_chunk = false;
int16_t audio_capture_buffers[2][stackchan::kAudioChunkBytes / 2]{};
rcl_action_goal_handle_t* capture_audio_active_goal_handle = nullptr;
rcl_action_goal_info_t capture_audio_active_goal_info;
rcl_action_goal_info_t capture_audio_terminal_goal_info;
rmw_request_id_t capture_audio_result_request_header;
stackchan::Result capture_audio_terminal_result =
    stackchan::Result::accepted("audio capture idle");
int8_t capture_audio_terminal_status = GOAL_STATE_UNKNOWN;
bool capture_audio_goal_active = false;
bool capture_audio_result_ready = false;
bool capture_audio_result_request_pending = false;
rcl_action_goal_handle_t* capture_camera_active_goal_handle = nullptr;
rcl_action_goal_info_t capture_camera_active_goal_info;
rcl_action_goal_info_t capture_camera_terminal_goal_info;
rmw_request_id_t capture_camera_result_request_header;
stackchan::Result capture_camera_terminal_result =
    stackchan::Result::accepted("camera capture idle");
int8_t capture_camera_terminal_status = GOAL_STATE_UNKNOWN;
bool capture_camera_goal_active = false;
bool capture_camera_result_ready = false;
bool capture_camera_result_request_pending = false;
rcl_action_goal_handle_t* play_audio_active_goal_handle = nullptr;
rcl_action_goal_info_t play_audio_active_goal_info;
rcl_action_goal_info_t play_audio_terminal_goal_info;
rmw_request_id_t play_audio_result_request_header;
stackchan::Result play_audio_terminal_result =
    stackchan::Result::accepted("audio playback idle");
int8_t play_audio_terminal_status = GOAL_STATE_UNKNOWN;
bool play_audio_goal_active = false;
bool play_audio_received_chunk = false;
bool play_audio_end_of_stream_seen = false;
bool play_audio_result_ready = false;
bool play_audio_result_request_pending = false;
bool play_audio_chunk_client_initialized = false;
bool play_audio_chunk_request_pending = false;
int64_t play_audio_chunk_request_sequence_number = 0;
uint32_t play_audio_next_pull_sequence = 0;
uint32_t play_audio_last_pull_request_ms = 0;
uint32_t play_audio_last_ack_publish_ms = 0;
uint32_t play_audio_started_ms = 0;
uint32_t play_audio_last_chunk_ms = 0;
uint32_t play_audio_last_speaker_frame_ms = 0;
uint32_t play_audio_pending_gap_started_ms = 0;
uint8_t play_audio_buffer_index = 0;
size_t play_audio_buffer_fill_samples = 0;
int16_t play_audio_buffers[4][stackchan::kAudioMaxChunkBytes / 2]{};
char play_audio_diagnostic_command_id[37] = "";
char play_audio_terminal_stale_command_id[37] = "";
uint32_t play_audio_terminal_stale_until_ms = 0;
uint32_t play_audio_chunks_seen = 0;
uint32_t play_audio_chunks_accepted = 0;
uint32_t play_audio_chunks_rejected = 0;
uint32_t play_audio_speaker_frames_queued = 0;
uint32_t play_audio_speaker_frames_failed = 0;
bool play_audio_speaker_session_active = false;
bool play_audio_speaker_queue_full_logged = false;
PlayAudioPendingChunk play_audio_pending_chunks[kAudioPlaybackPendingChunkSlots]{};
uint8_t play_audio_pending_chunk_count = 0;
alignas(int16_t) uint8_t play_audio_loaded_buffer[kAudioPlaybackLoadBufferBytes]{};
char play_audio_loaded_command_id[37] = "";
uint32_t play_audio_loaded_total_bytes = 0;
uint32_t play_audio_loaded_total_chunks = 0;
uint32_t play_audio_loaded_expected_sequence = 0;
uint8_t play_audio_loaded_format = stackchan_msgs__msg__AudioChunk__PCM_S16LE;
uint32_t play_audio_loaded_play_offset = 0;
uint32_t play_audio_loaded_last_write_ms = 0;
uint32_t play_audio_loaded_first_rx_ms = 0;
uint32_t play_audio_loaded_last_rx_ms = 0;
uint32_t play_audio_loaded_last_rx_gap_ms = 0;
uint32_t play_audio_loaded_decode_total_ms = 0;
uint32_t play_audio_loaded_last_decode_ms = 0;
bool play_audio_loaded_complete = false;
bool play_audio_loaded_playing = false;
uint32_t play_audio_loaded_direct_playback_ms = 0;
stackchan::ImaAdpcmDecoderState play_audio_loaded_adpcm_state;

void publish_status_heartbeat();
void finish_play_audio_goal(const stackchan::Result& result, int8_t action_status);
void reset_rcl_error();
bool assign_ros_string(rosidl_runtime_c__String* destination, const char* value);
bool firmware_publish_callback(
    stackchan::DevicePublisherTopic topic,
    const void* message,
    void* user_data);
stackchan::Result load_calibration_from_nvs();
stackchan::Result apply_calibration_maintenance_action();
void update_servo_health_cache(unsigned long now, bool force);
void show_neutral_face();
stackchan::Result validate_motion_servo_target(
    const stackchan::ServoTarget& target,
    const char* label,
    bool normal_operation = false);
stackchan::ServoTarget apply_motion_offset(
    const stackchan::ServoTarget& home,
    const stackchan::ServoTarget& offset);
void motion_diag_record_write(
    const stackchan::ServoTarget& target,
    int yaw_raw,
    int pitch_raw,
    int servo_time_ms);

void copy_bounded(char* destination, size_t size, const char* source) {
  if (size == 0) {
    return;
  }
  strncpy(destination, source == nullptr ? "" : source, size - 1);
  destination[size - 1] = '\0';
}

void reset_play_audio_diagnostics(const char* command_id) {
  copy_bounded(
      play_audio_diagnostic_command_id,
      sizeof(play_audio_diagnostic_command_id),
      command_id);
  play_audio_chunks_seen = 0;
  play_audio_chunks_accepted = 0;
  play_audio_chunks_rejected = 0;
  play_audio_speaker_frames_queued = 0;
  play_audio_speaker_frames_failed = 0;
  play_audio_speaker_queue_full_logged = false;
}

void clear_play_audio_terminal_stale_suppression() {
  play_audio_terminal_stale_command_id[0] = '\0';
  play_audio_terminal_stale_until_ms = 0;
}

void remember_play_audio_terminal_stale_suppression() {
  copy_bounded(
      play_audio_terminal_stale_command_id,
      sizeof(play_audio_terminal_stale_command_id),
      play_audio_diagnostic_command_id);
  play_audio_terminal_stale_until_ms =
      millis() + kAudioPlaybackTerminalStaleSuppressMs;
}

bool recent_terminal_play_audio_command(const char* command_id) {
  if (command_id == nullptr || command_id[0] == '\0' ||
      play_audio_terminal_stale_command_id[0] == '\0') {
    return false;
  }
  if (strcmp(command_id, play_audio_terminal_stale_command_id) != 0) {
    return false;
  }
  return static_cast<int32_t>(play_audio_terminal_stale_until_ms - millis()) > 0;
}

void reset_play_audio_pending_chunks() {
  for (auto& chunk : play_audio_pending_chunks) {
    chunk.occupied = false;
    chunk.sequence = 0;
    chunk.format = 0;
    chunk.sample_rate = 0;
    chunk.channels = 0;
    chunk.pcm_size = 0;
    chunk.received_ms = 0;
    chunk.command_id[0] = '\0';
  }
  play_audio_pending_chunk_count = 0;
  play_audio_pending_gap_started_ms = 0;
}

void reset_play_audio_loaded_buffer() {
  play_audio_loaded_command_id[0] = '\0';
  play_audio_loaded_total_bytes = 0;
  play_audio_loaded_total_chunks = 0;
  play_audio_loaded_expected_sequence = 0;
  play_audio_loaded_format = stackchan_msgs__msg__AudioChunk__PCM_S16LE;
  play_audio_loaded_play_offset = 0;
  play_audio_loaded_last_write_ms = 0;
  play_audio_loaded_first_rx_ms = 0;
  play_audio_loaded_last_rx_ms = 0;
  play_audio_loaded_last_rx_gap_ms = 0;
  play_audio_loaded_decode_total_ms = 0;
  play_audio_loaded_last_decode_ms = 0;
  play_audio_loaded_complete = false;
  play_audio_loaded_playing = false;
  play_audio_loaded_direct_playback_ms = 0;
  play_audio_loaded_adpcm_state = stackchan::ImaAdpcmDecoderState{};
}

int find_play_audio_pending_chunk(uint32_t sequence) {
  for (size_t index = 0; index < kAudioPlaybackPendingChunkSlots; ++index) {
    if (play_audio_pending_chunks[index].occupied &&
        play_audio_pending_chunks[index].sequence == sequence) {
      return static_cast<int>(index);
    }
  }
  return -1;
}

uint32_t oldest_play_audio_pending_age_ms(uint32_t now_ms) {
  uint32_t oldest_age = 0;
  for (const auto& chunk : play_audio_pending_chunks) {
    if (!chunk.occupied) {
      continue;
    }
    const uint32_t age = now_ms - chunk.received_ms;
    if (age > oldest_age) {
      oldest_age = age;
    }
  }
  return oldest_age;
}

void refresh_play_audio_pending_gap_timer(uint32_t now_ms) {
  if (play_audio_pending_chunk_count == 0) {
    play_audio_pending_gap_started_ms = 0;
  } else {
    play_audio_pending_gap_started_ms = now_ms;
  }
}

uint32_t play_audio_free_pending_chunk_slots() {
  return play_audio_pending_chunk_count >= kAudioPlaybackPendingChunkSlots
             ? 0
             : kAudioPlaybackPendingChunkSlots - play_audio_pending_chunk_count;
}

void publish_play_audio_ack_window(bool has_missing_sequence) {
  if (!play_audio_goal_active) {
    return;
  }
  const uint32_t now_ms = millis();
  if (play_audio_last_ack_publish_ms != 0 &&
      now_ms - play_audio_last_ack_publish_ms < kAudioPlaybackAckPublishIntervalMs) {
    return;
  }
  assign_ros_string(&audio_playback_ack_ros_message.device_id, STACKCHAN_DEVICE_ID);
  assign_ros_string(
      &audio_playback_ack_ros_message.command_id,
      play_audio_diagnostic_command_id);
  audio_playback_ack_ros_message.has_acknowledgement =
      play_audio_next_pull_sequence > 0;
  audio_playback_ack_ros_message.acknowledged_sequence =
      play_audio_next_pull_sequence > 0 ? play_audio_next_pull_sequence - 1 : 0;
  audio_playback_ack_ros_message.has_missing_sequence = has_missing_sequence;
  audio_playback_ack_ros_message.missing_sequence = play_audio_next_pull_sequence;
  audio_playback_ack_ros_message.free_buffer_chunks =
      play_audio_free_pending_chunk_slots();
  const rcl_ret_t publish_result =
      rcl_publish(&audio_playback_ack_ros_publisher, &audio_playback_ack_ros_message, nullptr);
  if (publish_result == RCL_RET_OK) {
    play_audio_last_ack_publish_ms = now_ms;
    return;
  }
  reset_rcl_error();
}

void log_play_audio_chunk_diagnostic(
    const char* stage,
    const char* command_id,
    uint32_t sequence,
    uint32_t bytes,
    const char* result_code) {
  const char* safe_stage = stage == nullptr ? "" : stage;
  const char* safe_result = result_code == nullptr ? "" : result_code;
  const bool publish_event =
      strcmp(safe_result, "OK") != 0 ||
      strcmp(safe_stage, "chunk_accepted") == 0 ||
      strcmp(safe_stage, "pull_end_of_stream") == 0 ||
      strcmp(safe_stage, "speaker_frame_queued") == 0 ||
      strcmp(safe_stage, "speaker_partial_frame_queued") == 0 ||
      strcmp(safe_stage, "loaded_playback_started") == 0 ||
      strcmp(safe_stage, "loaded_playback_queued") == 0 ||
      strcmp(safe_stage, "loaded_playback_drained") == 0 ||
      sequence <= 1 ||
      (kAudioPlaybackChunkDiagnosticSampleInterval > 0 &&
       sequence % kAudioPlaybackChunkDiagnosticSampleInterval == 0);
  if (publish_event) {
    char payload[stackchan::kEventPayloadJsonMaxLength + 1];
    snprintf(
        payload,
        sizeof(payload),
        "{\"stage\":\"%s\",\"seq\":%lu,\"bytes\":%lu,\"result\":\"%s\","
        "\"seen\":%lu,\"ok\":%lu,\"rej\":%lu,\"active\":%s,"
        "\"pending\":%s,\"next\":%lu,\"frames\":%lu,\"jitter\":%u}",
        safe_stage,
        static_cast<unsigned long>(sequence),
        static_cast<unsigned long>(bytes),
        safe_result,
        static_cast<unsigned long>(play_audio_chunks_seen),
        static_cast<unsigned long>(play_audio_chunks_accepted),
        static_cast<unsigned long>(play_audio_chunks_rejected),
        play_audio_goal_active ? "true" : "false",
        play_audio_chunk_request_pending ? "true" : "false",
        static_cast<unsigned long>(play_audio_next_pull_sequence),
        static_cast<unsigned long>(play_audio_speaker_frames_queued),
        play_audio_pending_chunk_count);
    event_publisher.publish_name(
        "audio_playback_chunk",
        millis(),
        command_id,
        payload);
  }
  stackchan_diag_print("stackchan audio_playback_diag stage=");
  stackchan_diag_print(safe_stage);
  stackchan_diag_print(" command_id=");
  stackchan_diag_print(command_id == nullptr ? "" : command_id);
  stackchan_diag_print(" sequence=");
  stackchan_diag_print(sequence);
  stackchan_diag_print(" bytes=");
  stackchan_diag_print(bytes);
  stackchan_diag_print(" result=");
  stackchan_diag_print(safe_result);
  stackchan_diag_print(" frames=");
  stackchan_diag_print(play_audio_speaker_frames_queued);
  stackchan_diag_print(" jitter=");
  stackchan_diag_println(play_audio_pending_chunk_count);
}

void log_play_audio_session_diagnostic(
    const char* stage,
    const stackchan::Result& result) {
  stackchan_diag_print("stackchan audio_playback_diag stage=");
  stackchan_diag_print(stage == nullptr ? "" : stage);
  stackchan_diag_print(" command_id=");
  stackchan_diag_print(play_audio_diagnostic_command_id);
  stackchan_diag_print(" seen=");
  stackchan_diag_print(play_audio_chunks_seen);
  stackchan_diag_print(" accepted=");
  stackchan_diag_print(play_audio_chunks_accepted);
  stackchan_diag_print(" rejected=");
  stackchan_diag_print(play_audio_chunks_rejected);
  stackchan_diag_print(" speaker_frames=");
  stackchan_diag_print(play_audio_speaker_frames_queued);
  stackchan_diag_print(" result=");
  stackchan_diag_println(result.error_code);
}

void log_play_audio_action_diagnostic(
    const char* stage,
    const char* command_id,
    bool accepted,
    bool first_chunk_present,
    uint32_t first_chunk_bytes) {
  char payload[stackchan::kEventPayloadJsonMaxLength + 1];
  snprintf(
      payload,
      sizeof(payload),
      "{\"stage\":\"%s\",\"accepted\":%s,\"first_chunk\":%s,"
      "\"first_chunk_bytes\":%lu,\"goal_active\":%s,"
      "\"result_ready\":%s,\"result_request_pending\":%s}",
      stage == nullptr ? "" : stage,
      accepted ? "true" : "false",
      first_chunk_present ? "true" : "false",
      static_cast<unsigned long>(first_chunk_bytes),
      play_audio_goal_active ? "true" : "false",
      play_audio_result_ready ? "true" : "false",
      play_audio_result_request_pending ? "true" : "false");
  event_publisher.publish_name(
      "audio_playback_action",
      millis(),
      command_id,
      payload);
  stackchan_diag_print("stackchan audio_playback_action stage=");
  stackchan_diag_print(stage == nullptr ? "" : stage);
  stackchan_diag_print(" command_id=");
  stackchan_diag_print(command_id == nullptr ? "" : command_id);
  stackchan_diag_print(" accepted=");
  stackchan_diag_print(accepted ? "true" : "false");
  stackchan_diag_print(" first_chunk=");
  stackchan_diag_print(first_chunk_present ? "true" : "false");
  stackchan_diag_print(" first_chunk_bytes=");
  stackchan_diag_print(first_chunk_bytes);
  stackchan_diag_print(" goal_active=");
  stackchan_diag_print(play_audio_goal_active ? "true" : "false");
  stackchan_diag_print(" result_ready=");
  stackchan_diag_print(play_audio_result_ready ? "true" : "false");
  stackchan_diag_print(" result_request_pending=");
  stackchan_diag_println(play_audio_result_request_pending ? "true" : "false");
}

const char* audio_load_result_detail(const stackchan::Result& result) {
  if (result.ok || result.message == nullptr) {
    return "";
  }
  if (strstr(result.message, "sequence is not contiguous") != nullptr) {
    return "sequence_gap";
  }
  if (strstr(result.message, "final counters") != nullptr) {
    return "counter_mismatch";
  }
  if (strstr(result.message, "header") != nullptr) {
    return "adpcm_header";
  }
  if (strstr(result.message, "byte length") != nullptr) {
    return "byte_length";
  }
  if (strstr(result.message, "format") != nullptr) {
    return "format";
  }
  if (strstr(result.message, "buffer") != nullptr ||
      strstr(result.message, "size") != nullptr) {
    return "buffer";
  }
  return "other";
}

void log_play_audio_load_diagnostic(
    const char* stage,
    const char* command_id,
    uint32_t sequence,
    uint32_t bytes,
    uint32_t total_chunks,
    uint32_t buffered_bytes,
    uint32_t buffered_chunks,
    bool complete,
    const stackchan::Result& result) {
  const bool topic_stage = stage != nullptr && strcmp(stage, "topic") == 0;
  const bool should_log =
      complete ||
      !result.ok ||
      (!topic_stage &&
       (sequence <= 1 ||
        (kAudioPlaybackChunkDiagnosticSampleInterval > 0 &&
         sequence % kAudioPlaybackChunkDiagnosticSampleInterval == 0)));
  if (!should_log) {
    return;
  }
  char payload[stackchan::kEventPayloadJsonMaxLength + 1];
  const uint32_t loaded_rx_elapsed_ms =
      play_audio_loaded_first_rx_ms > 0 &&
              play_audio_loaded_last_rx_ms >= play_audio_loaded_first_rx_ms
          ? play_audio_loaded_last_rx_ms - play_audio_loaded_first_rx_ms
          : 0;
  snprintf(
      payload,
      sizeof(payload),
      "{\"stage\":\"%s\",\"seq\":%lu,\"bytes\":%lu,\"chunks\":%lu,"
      "\"buf\":%lu,\"buf_chunks\":%lu,\"expected_seq\":%lu,"
      "\"received_seq\":%lu,\"complete\":%s,\"result\":\"%s\","
      "\"detail\":\"%s\",\"rx_ms\":%lu,\"gap_ms\":%lu,"
      "\"dec_ms\":%lu,\"last_dec_ms\":%lu}",
      stage == nullptr ? "" : stage,
      static_cast<unsigned long>(sequence),
      static_cast<unsigned long>(bytes),
      static_cast<unsigned long>(total_chunks),
      static_cast<unsigned long>(buffered_bytes),
      static_cast<unsigned long>(buffered_chunks),
      static_cast<unsigned long>(buffered_chunks),
      static_cast<unsigned long>(sequence),
      complete ? "true" : "false",
      result.error_code,
      audio_load_result_detail(result),
      static_cast<unsigned long>(loaded_rx_elapsed_ms),
      static_cast<unsigned long>(play_audio_loaded_last_rx_gap_ms),
      static_cast<unsigned long>(play_audio_loaded_decode_total_ms),
      static_cast<unsigned long>(play_audio_loaded_last_decode_ms));
  event_publisher.publish_name(
      "audio_playback_load",
      millis(),
      command_id,
      payload);
  stackchan_diag_print("stackchan audio_playback_load stage=");
  stackchan_diag_print(stage == nullptr ? "" : stage);
  stackchan_diag_print(" command_id=");
  stackchan_diag_print(command_id == nullptr ? "" : command_id);
  stackchan_diag_print(" sequence=");
  stackchan_diag_print(sequence);
  stackchan_diag_print(" bytes=");
  stackchan_diag_print(bytes);
  stackchan_diag_print(" chunks=");
  stackchan_diag_print(total_chunks);
  stackchan_diag_print(" buffered_bytes=");
  stackchan_diag_print(buffered_bytes);
  stackchan_diag_print(" buffered_chunks=");
  stackchan_diag_print(buffered_chunks);
  stackchan_diag_print(" complete=");
  stackchan_diag_print(complete ? "true" : "false");
  stackchan_diag_print(" rx_ms=");
  stackchan_diag_print(loaded_rx_elapsed_ms);
  stackchan_diag_print(" gap_ms=");
  stackchan_diag_print(play_audio_loaded_last_rx_gap_ms);
  stackchan_diag_print(" decode_ms=");
  stackchan_diag_print(play_audio_loaded_decode_total_ms);
  stackchan_diag_print(" result=");
  stackchan_diag_println(result.error_code);
}

bool is_known_face(const char* name) {
  return strcmp(name, "neutral") == 0 ||
         strcmp(name, "happy") == 0 ||
         strcmp(name, "thinking") == 0 ||
         strcmp(name, "surprised") == 0 ||
         strcmp(name, "sleepy") == 0 ||
         strcmp(name, "error") == 0;
}

bool is_known_led_pattern(const char* pattern) {
  return strcmp(pattern, "off") == 0 ||
         strcmp(pattern, "progress") == 0 ||
         strcmp(pattern, "success") == 0 ||
         strcmp(pattern, "warning") == 0 ||
         strcmp(pattern, "error") == 0 ||
         strcmp(pattern, "listening") == 0;
}

uint16_t face_color(uint8_t red, uint8_t green, uint8_t blue) {
  return M5.Display.color565(red, green, blue);
}

void draw_open_eye(int x, int y, int radius, uint16_t color) {
  M5.Display.fillCircle(x, y, radius, color);
}

void draw_closed_eye(int x, int y, int radius, uint16_t color) {
  const int half_width = radius + radius / 2;
  for (int offset = -1; offset <= 1; ++offset) {
    M5.Display.drawFastHLine(x - half_width, y + offset, half_width * 2, color);
  }
}

void draw_x_eye(int x, int y, int radius, uint16_t color) {
  for (int offset = -1; offset <= 1; ++offset) {
    M5.Display.drawLine(x - radius, y - radius + offset, x + radius, y + radius + offset, color);
    M5.Display.drawLine(x - radius, y + radius + offset, x + radius, y - radius + offset, color);
  }
}

void draw_flat_mouth(int center_x, int y, int width, uint16_t color) {
  for (int offset = -2; offset <= 2; ++offset) {
    M5.Display.drawFastHLine(center_x - width / 2, y + offset, width, color);
  }
}

void draw_happy_mouth(int center_x, int y, int width, int height, uint16_t color) {
  for (int offset = 0; offset < 4; ++offset) {
    M5.Display.drawLine(center_x - width / 2, y + offset, center_x - width / 4, y + height + offset, color);
    M5.Display.drawLine(center_x - width / 4, y + height + offset, center_x + width / 4, y + height + offset, color);
    M5.Display.drawLine(center_x + width / 4, y + height + offset, center_x + width / 2, y + offset, color);
  }
}

void draw_surprised_mouth(int center_x, int y, int radius, uint16_t color) {
  M5.Display.fillCircle(center_x, y, radius, color);
}

void draw_thinking_mark(int x, int y, int unit, uint16_t color) {
  M5.Display.fillCircle(x, y, unit / 4, color);
  M5.Display.fillCircle(x + unit / 2, y - unit / 2, unit / 6, color);
  M5.Display.fillCircle(x + unit, y - unit, unit / 8, color);
}

void render_face_display(const char* name) {
  const int width = M5.Display.width();
  const int height = M5.Display.height();
  const int unit = (width < height ? width : height) / 10;
  const int center_x = width / 2;
  const int eye_y = height * 42 / 100;
  const int eye_dx = width * 18 / 100;
  const int mouth_y = height * 65 / 100;
  const int eye_radius = unit / 2;
  const int mouth_width = unit * 3;
  const uint16_t face_bg = face_color(16, 24, 30);
  const uint16_t panel = face_color(28, 38, 44);
  const uint16_t white = face_color(246, 248, 243);
  const uint16_t accent = face_color(255, 215, 84);
  const uint16_t blue = face_color(88, 178, 255);
  const uint16_t red = face_color(220, 56, 64);

  M5.Display.fillScreen(face_bg);
  M5.Display.fillRoundRect(unit, unit, width - unit * 2, height - unit * 2, unit, panel);

  if (strcmp(name, "error") == 0) {
    M5.Display.fillRoundRect(unit, unit, width - unit * 2, height - unit * 2, unit, red);
    draw_x_eye(center_x - eye_dx, eye_y, eye_radius, white);
    draw_x_eye(center_x + eye_dx, eye_y, eye_radius, white);
    draw_flat_mouth(center_x, mouth_y, mouth_width, white);
    return;
  }

  if (strcmp(name, "sleepy") == 0) {
    draw_closed_eye(center_x - eye_dx, eye_y, eye_radius, white);
    draw_closed_eye(center_x + eye_dx, eye_y, eye_radius, white);
    draw_flat_mouth(center_x, mouth_y, mouth_width / 2, white);
    return;
  }

  if (strcmp(name, "thinking") == 0) {
    draw_open_eye(center_x - eye_dx, eye_y, eye_radius, white);
    draw_closed_eye(center_x + eye_dx, eye_y, eye_radius, white);
    draw_flat_mouth(center_x, mouth_y, mouth_width / 2, white);
    draw_thinking_mark(center_x + eye_dx + unit, eye_y - unit, unit, blue);
    return;
  }

  if (strcmp(name, "surprised") == 0) {
    draw_open_eye(center_x - eye_dx, eye_y, eye_radius + unit / 5, white);
    draw_open_eye(center_x + eye_dx, eye_y, eye_radius + unit / 5, white);
    draw_surprised_mouth(center_x, mouth_y, unit / 2, white);
    return;
  }

  draw_open_eye(center_x - eye_dx, eye_y, eye_radius, white);
  draw_open_eye(center_x + eye_dx, eye_y, eye_radius, white);
  if (strcmp(name, "happy") == 0) {
    M5.Display.fillCircle(center_x - eye_dx - unit, mouth_y - unit / 2, unit / 4, accent);
    M5.Display.fillCircle(center_x + eye_dx + unit, mouth_y - unit / 2, unit / 4, accent);
    draw_happy_mouth(center_x, mouth_y - unit / 3, mouth_width, unit / 2, white);
    return;
  }
  draw_flat_mouth(center_x, mouth_y, mouth_width, white);
}

bool is_servo_safety_fault(const stackchan::Result& result) {
  return strcmp(result.error_code, "SERVO_LIMIT_EXCEEDED") == 0 ||
         strcmp(result.error_code, "SERVO_READ_FAILED") == 0 ||
         strcmp(result.error_code, "MOTION_INTERRUPTED") == 0;
}

bool firmware_calibration_valid() {
  return calibration_store.valid();
}

bool raw_servo_position_valid(int raw_position) {
  return raw_position >= kServoRawMin && raw_position <= kServoRawMax;
}

bool read_servo_raw_positions(int* yaw_raw, int* pitch_raw) {
  if (yaw_raw == nullptr || pitch_raw == nullptr) {
    return false;
  }
  const int yaw = servo_bus.ReadPos(kYawServoId);
  const int pitch = servo_bus.ReadPos(kPitchServoId);
  if (!raw_servo_position_valid(yaw) || !raw_servo_position_valid(pitch)) {
    return false;
  }
  *yaw_raw = yaw;
  *pitch_raw = pitch;
  return true;
}

bool servo_pair_moving(bool* moving) {
  if (moving == nullptr || !servo_adapter_init_result.ok) {
    return false;
  }
  const int yaw_moving = servo_bus.ReadMove(kYawServoId);
  const int pitch_moving = servo_bus.ReadMove(kPitchServoId);
  if (yaw_moving < 0 || pitch_moving < 0) {
    return false;
  }
  *moving = yaw_moving != 0 || pitch_moving != 0;
  return true;
}

int servo_degrees_to_raw(int default_zero_pos, int degrees) {
  const int deci_degrees = degrees * 10;
  return default_zero_pos + deci_degrees * 16 / 50;
}

stackchan::Result initialize_m5_bsp_adapter() {
  M5.begin();
  return stackchan::Result::accepted("M5 BSP initialized");
}

stackchan::Result initialize_io_expander_adapter() {
  const unsigned long start_ms = millis();
  while (!io_expander.begin()) {
    if (millis() - start_ms > kIoExpanderInitTimeoutMs) {
      return stackchan::Result::rejected(
          "SERVO_READ_FAILED",
          "StackChan IO expander initialization timed out",
          true);
    }
    delay(200);
  }
  io_expander.setDirection(0, true);
  io_expander.setPullMode(0, true);
  io_expander.digitalWrite(0, true);
  io_expander.setLedCount(kRgbLedCount);
  stackchan_led_initialized = true;
  delay(200);
  return stackchan::Result::accepted("StackChan IO expander initialized");
}

stackchan::Result initialize_servo_uart_adapter() {
  if (!servo_bus.begin(UART_NUM_1, kServoUartBaud, kServoTxPin, kServoRxPin)) {
    return stackchan::Result::rejected(
        "SERVO_READ_FAILED",
        "StackChan servo UART initialization failed",
        true);
  }
  return stackchan::Result::accepted("StackChan servo UART initialized");
}

stackchan::Result verify_servo_position_read() {
  int yaw_raw = -1;
  int pitch_raw = -1;
  if (!read_servo_raw_positions(&yaw_raw, &pitch_raw)) {
    return stackchan::Result::rejected(
        "SERVO_READ_FAILED",
        "servo current position read failed",
        true);
  }

  return stackchan::Result::accepted("servo adapter initialized");
}

stackchan::Result initialize_servo_adapter() {
  stackchan::Result result = initialize_m5_bsp_adapter();
  if (!result.ok) {
    return result;
  }
  result = initialize_io_expander_adapter();
  if (!result.ok) {
    return result;
  }
  result = initialize_servo_uart_adapter();
  if (!result.ok) {
    return result;
  }
  return verify_servo_position_read();
}

bool ltr553_write_register(uint8_t reg, uint8_t value) {
  return M5.In_I2C.writeRegister8(kLtr553Address, reg, value, kLtr553I2cFreq);
}

bool ltr553_read_register(uint8_t reg, uint8_t* value) {
  if (value == nullptr) {
    return false;
  }
  return M5.In_I2C.readRegister(
      kLtr553Address,
      reg,
      value,
      1,
      kLtr553I2cFreq);
}

bool ltr553_read_block(uint8_t start_reg, uint8_t* values, size_t length) {
  if (values == nullptr || length == 0 || length > 8) {
    return false;
  }
  return M5.In_I2C.readRegister(
      kLtr553Address,
      start_reg,
      values,
      length,
      kLtr553I2cFreq);
}

bool si12t_read_output_register(uint8_t* value) {
  if (value == nullptr) {
    return false;
  }
  return M5.In_I2C.readRegister(
      SI12T_GND_ADDRESS,
      SI12T_OUTPUT1_ADDR,
      value,
      1,
      100000);
}

float calculate_ltr553_lux(uint16_t ch0, uint16_t ch1) {
  const uint32_t total = static_cast<uint32_t>(ch0) + ch1;
  if (total == 0) {
    return 0.0f;
  }
  const float ratio = static_cast<float>(ch1) / static_cast<float>(total);
  float lux = 0.0f;
  if (ratio < 0.45f) {
    lux = 1.7743f * static_cast<float>(ch0) + 1.1059f * static_cast<float>(ch1);
  } else if (ratio < 0.64f) {
    lux = 4.2785f * static_cast<float>(ch0) - 1.9548f * static_cast<float>(ch1);
  } else if (ratio < 0.85f) {
    lux = 0.5926f * static_cast<float>(ch0) + 0.1185f * static_cast<float>(ch1);
  }
  lux /= kLtr553AlsIntegrationFactor;
  return lux < 0.0f ? 0.0f : lux;
}

bool initialize_ltr553_sensor() {
  ltr553_part_id = 0;
  ltr553_manufacturer_id = 0;
  ltr553_last_ps_read_ok = false;
  ltr553_last_als_read_ok = false;
  ltr553_part_id_read_ok = ltr553_read_register(kLtr553PartId, &ltr553_part_id);
  ltr553_manufacturer_id_read_ok =
      ltr553_read_register(kLtr553ManufacturerId, &ltr553_manufacturer_id);
  if (!ltr553_part_id_read_ok || !ltr553_manufacturer_id_read_ok) {
    return false;
  }
  if (ltr553_manufacturer_id != kLtr553ExpectedManufacturerId) {
    return false;
  }

  bool ok = true;
  ok = ltr553_write_register(kLtr553AlsContr, 0x00) && ok;
  ok = ltr553_write_register(kLtr553PsContr, 0x00) && ok;
  ok = ltr553_write_register(kLtr553PsMeasRate, 0x02) && ok;
  ok = ltr553_write_register(kLtr553AlsMeasRate, 0x12) && ok;
  ok = ltr553_write_register(kLtr553AlsContr, 0x01) && ok;
  ok = ltr553_write_register(kLtr553PsContr, 0x03) && ok;
  return ok;
}

bool initialize_nfc_adapter() {
  stackchan_nfc_sda_pin = M5.getPin(m5::pin_name_t::in_i2c_sda);
  stackchan_nfc_scl_pin = M5.getPin(m5::pin_name_t::in_i2c_scl);
  if (stackchan_nfc_sda_pin < 0 || stackchan_nfc_scl_pin < 0) {
    copy_bounded(stackchan_nfc_bus, sizeof(stackchan_nfc_bus), "in_i2c_unavailable");
    return false;
  }

  stackchan_nfc_i2c_present = true;
  copy_bounded(stackchan_nfc_bus, sizeof(stackchan_nfc_bus), "in_i2c");
  return stackchan_units.add(stackchan_nfc_unit, M5.In_I2C) && stackchan_units.begin();
}

camera_config_t make_core_s3_camera_config(pixformat_t pixel_format = PIXFORMAT_JPEG) {
  camera_config_t config{};
  config.pin_pwdn = -1;
  config.pin_reset = -1;
  config.pin_xclk = -1;
  config.pin_sccb_sda = 12;
  config.pin_sccb_scl = 11;
  config.pin_d7 = 47;
  config.pin_d6 = 48;
  config.pin_d5 = 16;
  config.pin_d4 = 15;
  config.pin_d3 = 42;
  config.pin_d2 = 41;
  config.pin_d1 = 40;
  config.pin_d0 = 39;
  config.pin_vsync = 46;
  config.pin_href = 38;
  config.pin_pclk = 45;
  config.xclk_freq_hz = 20000000;
  config.ledc_timer = LEDC_TIMER_0;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.pixel_format = pixel_format;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = pixel_format == PIXFORMAT_JPEG ? 18 : 0;
  config.fb_count = pixel_format == PIXFORMAT_JPEG ? 1 : 2;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode =
      pixel_format == PIXFORMAT_JPEG ? CAMERA_GRAB_LATEST : CAMERA_GRAB_WHEN_EMPTY;
  config.sccb_i2c_port = -1;
  return config;
}

bool initialize_camera_adapter() {
  stackchan_camera_config = make_core_s3_camera_config();
  stackchan_in_i2c_released_for_camera = true;
  M5.In_I2C.release();
  stackchan_camera_init_error = esp_camera_init(&stackchan_camera_config);
  if (stackchan_camera_init_error != ESP_OK) {
    stackchan_camera_config = make_core_s3_camera_config(PIXFORMAT_RGB565);
    stackchan_camera_init_error = esp_camera_init(&stackchan_camera_config);
  }
  if (stackchan_camera_init_error != ESP_OK) {
    stackchan_camera_sensor = nullptr;
    return false;
  }
  stackchan_camera_sensor = esp_camera_sensor_get();
  if (stackchan_camera_sensor == nullptr) {
    return false;
  }
  stackchan_camera_sensor->set_framesize(stackchan_camera_sensor, FRAMESIZE_QVGA);
  stackchan_camera_sensor->set_hmirror(
      stackchan_camera_sensor,
      kCameraHorizontalMirror ? 1 : 0);
  return true;
}

void initialize_touch_adapter() {
  stackchan_touch_sensor.begin();
  stackchan_touch_sensor_initialized = true;
}

void initialize_imu_adapter() {
  stackchan_imu_initialized = M5.Imu.isEnabled();
}

void initialize_power_monitor_adapter() {
  m5::INA226_Class::config_t config;
  config.shunt_res = 0.01f;
  config.max_expected_current = 8.19f;
  stackchan_power_monitor.config(config);
  stackchan_power_monitor_initialized = stackchan_power_monitor.begin();
}

void initialize_ir_adapter() {
  stackchan_irrecv.setUnknownThreshold(kIrMinUnknownSize);
  stackchan_irrecv.setTolerance(kIrTolerancePercentage);
  stackchan_irrecv.enableIRIn();
  stackchan_ir_initialized = true;
}

void initialize_audio_probe_adapters() {
  stackchan_audio_playback_initialized = M5.Speaker.isEnabled();
  stackchan_audio_capture_initialized = M5.Mic.isEnabled();
}

void initialize_sensor_adapters() {
  initialize_touch_adapter();
  initialize_imu_adapter();
  initialize_power_monitor_adapter();
  ltr553_sensor_initialized = initialize_ltr553_sensor();
  initialize_ir_adapter();
  initialize_audio_probe_adapters();
  stackchan_camera_snapshot_initialized = initialize_camera_adapter();
  stackchan_nfc_initialized = initialize_nfc_adapter();
}

#if STACKCHAN_SENSOR_INPUT_DIAGNOSTICS
void print_sensor_input_diagnostics(uint32_t now_ms);

void print_sensor_input_diag_stage(const char* stage) {
  stackchan_diag_print("stackchan sensor_input_diag_stage ms=");
  stackchan_diag_print(millis());
  stackchan_diag_print(" stage=");
  stackchan_diag_println(stage);
  stackchan_diag_flush();
}

void run_sensor_input_diagnostic_loop(uint32_t now_ms) {
  constexpr unsigned long kSensorInputDiagStartupHoldMs = 8000;
  constexpr unsigned long kSensorInputDiagPeriodMs = 250;
  if (now_ms - last_sensor_input_diag_ms < kSensorInputDiagPeriodMs) {
    return;
  }
  last_sensor_input_diag_ms = now_ms;

  if (sensor_input_diag_stage == 0) {
    print_sensor_input_diag_stage("pre_m5_begin");
    if (now_ms - sensor_input_diag_stage_started_ms >= kSensorInputDiagStartupHoldMs) {
      sensor_input_diag_stage = 1;
    }
    return;
  }

  if (sensor_input_diag_stage == 1) {
    print_sensor_input_diag_stage("m5_begin_start");
    M5.begin();
    Serial.begin(STACKCHAN_MICROROS_SERIAL_BAUD);
    print_sensor_input_diag_stage("m5_begin_done");
    sensor_input_diag_stage = 2;
    return;
  }

  if (sensor_input_diag_stage == 2) {
    print_sensor_input_diag_stage("touch_begin_start");
    stackchan_touch_sensor.begin();
    stackchan_touch_sensor_initialized = true;
    print_sensor_input_diag_stage("touch_begin_done");
    sensor_input_diag_stage = 3;
    return;
  }

  if (sensor_input_diag_stage == 3) {
    print_sensor_input_diag_stage("power_begin_start");
    m5::INA226_Class::config_t config;
    config.shunt_res = 0.01f;
    config.max_expected_current = 8.19f;
    stackchan_power_monitor.config(config);
    stackchan_power_monitor_initialized = stackchan_power_monitor.begin();
    print_sensor_input_diag_stage(
        stackchan_power_monitor_initialized ? "power_begin_done" : "power_begin_failed");
    sensor_input_diag_stage = 4;
    return;
  }

  if (sensor_input_diag_stage == 4) {
    print_sensor_input_diag_stage("ltr553_begin_start");
    ltr553_sensor_initialized = initialize_ltr553_sensor();
    print_sensor_input_diag_stage(
        ltr553_sensor_initialized ? "ltr553_begin_done" : "ltr553_begin_failed");
    sensor_input_diag_stage = 5;
    return;
  }

  M5.update();
  print_sensor_input_diagnostics(now_ms);
}
#endif

#if STACKCHAN_MICROROS_STATUS_ONLY_BRINGUP
void initialize_minimal_microros_bringup() {
  stackchan::Result publisher_result =
      device_publishers.initialize(STACKCHAN_DEVICE_ID);
  if (!publisher_result.ok) {
    last_error = publisher_result;
  }
  device_publishers.set_publish_callback(firmware_publish_callback);
  state_machine.booted();
}
#endif

#if STACKCHAN_MICROROS_BOARD_INIT_BRINGUP
stackchan::Result initialize_board_init_bringup_stage() {
  stackchan::Result result = stackchan::Result::accepted("board init stage skipped");
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 1
  result = initialize_m5_bsp_adapter();
  if (!result.ok) {
    return result;
  }
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 2
  result = initialize_io_expander_adapter();
  if (!result.ok) {
    return result;
  }
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 3
  result = initialize_servo_uart_adapter();
  if (!result.ok) {
    return result;
  }
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 4
  result = verify_servo_position_read();
  if (!result.ok) {
    return result;
  }
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 5
  initialize_touch_adapter();
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 6
  initialize_imu_adapter();
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 7
  initialize_power_monitor_adapter();
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 8
  ltr553_sensor_initialized = initialize_ltr553_sensor();
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 9
  stackchan_nfc_initialized = initialize_nfc_adapter();
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 10
  initialize_ir_adapter();
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 11
  initialize_audio_probe_adapters();
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 12
  stackchan_camera_snapshot_initialized = initialize_camera_adapter();
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 13
  calibration_maintenance_result = apply_calibration_maintenance_action();
  if (!calibration_maintenance_result.ok) {
    return calibration_maintenance_result;
  }
  calibration_load_result = load_calibration_from_nvs();
  if (!calibration_load_result.ok) {
    return calibration_load_result;
  }
  update_servo_health_cache(millis(), true);
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_STAGE >= 14
  show_neutral_face();
#endif
  return result;
}

void initialize_board_init_microros_bringup() {
  stackchan::Result board_init_result = initialize_board_init_bringup_stage();
  stackchan::Result publisher_result =
      device_publishers.initialize(STACKCHAN_DEVICE_ID);
  if (!board_init_result.ok) {
    last_error = board_init_result;
  } else if (!publisher_result.ok) {
    last_error = publisher_result;
  }
  device_publishers.set_publish_callback(firmware_publish_callback);
  state_machine.booted();
}
#endif

stackchan::TouchStateTelemetry read_touch_state_telemetry(uint32_t now_ms) {
  stackchan::TouchStateTelemetry telemetry{};
  copy_bounded(telemetry.device_id, sizeof(telemetry.device_id), STACKCHAN_DEVICE_ID);
  telemetry.stamp_ms = now_ms;
  copy_bounded(telemetry.surface, sizeof(telemetry.surface), "stackchan_head");

  if (!stackchan_touch_sensor_initialized) {
    stackchan_touch_output_read_ok = false;
    return telemetry;
  }

  stackchan_touch_sensor.update();
  const auto& intensities = stackchan_touch_sensor.getIntensities();
  telemetry.zone_count = stackchan::kTouchMaxZones;
  for (uint8_t index = 0; index < stackchan::kTouchMaxZones; ++index) {
    const uint8_t intensity = intensities[index];
    telemetry.intensities[index] = intensity;
    if (intensity > 0) {
      telemetry.zone_mask |= static_cast<uint8_t>(1U << index);
    }
  }
  uint8_t output_raw = 0;
  stackchan_touch_output_read_ok = si12t_read_output_register(&output_raw);
  if (stackchan_touch_output_read_ok) {
    stackchan_touch_output_raw = output_raw;
  } else {
    stackchan_touch_output_raw = 0;
    ++stackchan_touch_output_read_failures;
  }
  if (telemetry.zone_mask == 0 && stackchan_touch_output_read_ok && output_raw != 0) {
    for (uint8_t sensor_index = 0; sensor_index < stackchan::kTouchMaxZones; ++sensor_index) {
      const uint8_t intensity = (output_raw >> (sensor_index * 2)) & 0x03;
      const uint8_t zone_index = (stackchan::kTouchMaxZones - 1) - sensor_index;
      telemetry.intensities[zone_index] = intensity;
      if (intensity > 0) {
        telemetry.zone_mask |= static_cast<uint8_t>(1U << zone_index);
      }
    }
  }
  return telemetry;
}

stackchan::ProximityRawTelemetry read_proximity_raw_telemetry(uint32_t now_ms) {
  stackchan::ProximityRawTelemetry telemetry{};
  copy_bounded(telemetry.device_id, sizeof(telemetry.device_id), STACKCHAN_DEVICE_ID);
  telemetry.stamp_ms = now_ms;
  telemetry.sensor_index = 0;
  telemetry.distance_m = NAN;

  if (!ltr553_sensor_initialized) {
    ltr553_last_ps_read_ok = false;
    return telemetry;
  }

  uint8_t data[2] = {0, 0};
  if (!ltr553_read_block(kLtr553PsDataLow, data, sizeof(data))) {
    ltr553_last_ps_read_ok = false;
    return telemetry;
  }
  ltr553_last_ps_read_ok = true;
  const uint16_t raw = static_cast<uint16_t>(((data[1] & 0x07u) << 8) | data[0]);
  telemetry.raw = raw;
  telemetry.signal = static_cast<float>(raw) / kLtr553PsFullScale;
  telemetry.saturated = (data[1] & 0x80u) != 0;
  return telemetry;
}

stackchan::LightRawTelemetry read_light_raw_telemetry(uint32_t now_ms) {
  stackchan::LightRawTelemetry telemetry{};
  copy_bounded(telemetry.device_id, sizeof(telemetry.device_id), STACKCHAN_DEVICE_ID);
  telemetry.stamp_ms = now_ms;
  telemetry.sensor_index = 0;

  if (!ltr553_sensor_initialized) {
    ltr553_last_als_read_ok = false;
    return telemetry;
  }

  uint8_t data[4] = {0, 0, 0, 0};
  if (!ltr553_read_block(kLtr553AlsDataCh1Low, data, sizeof(data))) {
    ltr553_last_als_read_ok = false;
    return telemetry;
  }
  ltr553_last_als_read_ok = true;
  const uint16_t ch1 = static_cast<uint16_t>((data[1] << 8) | data[0]);
  const uint16_t ch0 = static_cast<uint16_t>((data[3] << 8) | data[2]);
  telemetry.raw = ch0;
  telemetry.illuminance_lux = calculate_ltr553_lux(ch0, ch1);
  telemetry.saturated = ch0 == 0xFFFFu || ch1 == 0xFFFFu;
  return telemetry;
}

stackchan::PowerStatusTelemetry read_power_status_telemetry(uint32_t now_ms) {
  stackchan::PowerStatusTelemetry telemetry{};
  copy_bounded(telemetry.device_id, sizeof(telemetry.device_id), STACKCHAN_DEVICE_ID);
  telemetry.stamp_ms = now_ms;
  telemetry.power_source = stackchan::PowerSource::Unknown;

  const int32_t battery_level = M5.Power.getBatteryLevel();
  if (battery_level >= 0 && battery_level <= 100) {
    telemetry.percentage = static_cast<float>(battery_level);
  }

  const auto charging_state = M5.Power.isCharging();
  telemetry.charging = charging_state == m5::Power_Class::is_charging;

  if (stackchan_power_monitor_initialized) {
    const float voltage_v = stackchan_power_monitor.getBusVoltage();
    const float current_a = stackchan_power_monitor.getShuntCurrent();
    const float power_w = stackchan_power_monitor.getPower();
    telemetry.voltage_v = voltage_v;
    telemetry.current_ma = current_a * 1000.0f;
    telemetry.power_mw = power_w * 1000.0f;
    telemetry.powered = voltage_v > 0.0f;
  } else {
    const int16_t battery_mv = M5.Power.getBatteryVoltage();
    if (battery_mv > 0) {
      telemetry.voltage_v = static_cast<float>(battery_mv) / 1000.0f;
      telemetry.powered = true;
    }
    const int32_t battery_ma = M5.Power.getBatteryCurrent();
    telemetry.current_ma = static_cast<float>(battery_ma);
    telemetry.power_mw = telemetry.voltage_v * telemetry.current_ma;
  }

  const int16_t vbus_mv = M5.Power.getVBUSVoltage();
  if (vbus_mv > 0 || telemetry.charging) {
    telemetry.power_source = stackchan::PowerSource::Usb;
  } else if (telemetry.powered) {
    telemetry.power_source = stackchan::PowerSource::Battery;
  }
  telemetry.low_battery =
      telemetry.voltage_v > 0.0f && telemetry.voltage_v <= stackchan::kBatteryLowVoltageV;
  telemetry.brownout_risk =
      telemetry.voltage_v > 0.0f && telemetry.voltage_v <= stackchan::kBrownoutRiskVoltageV;
  return telemetry;
}

#if STACKCHAN_SENSOR_INPUT_DIAGNOSTICS
void print_sensor_input_diagnostics(uint32_t now_ms) {
  constexpr unsigned long kSensorInputDiagPeriodMs = 250;
  if (now_ms - last_sensor_input_diag_report_ms < kSensorInputDiagPeriodMs) {
    return;
  }
  last_sensor_input_diag_report_ms = now_ms;

  const stackchan::TouchStateTelemetry touch = read_touch_state_telemetry(now_ms);
  const stackchan::ProximityRawTelemetry proximity =
      read_proximity_raw_telemetry(now_ms);
  const stackchan::LightRawTelemetry light = read_light_raw_telemetry(now_ms);
  const stackchan::PowerStatusTelemetry power = read_power_status_telemetry(now_ms);

  stackchan_diag_print("stackchan sensor_input_diag ms=");
  stackchan_diag_print(now_ms);
  stackchan_diag_print(" touch_init=");
  stackchan_diag_print(stackchan_touch_sensor_initialized ? "true" : "false");
  stackchan_diag_print(" touch_zone_mask=");
  stackchan_diag_print(static_cast<int>(touch.zone_mask));
  stackchan_diag_print(" touch_i0=");
  stackchan_diag_print(static_cast<int>(touch.intensities[0]));
  stackchan_diag_print(" touch_i1=");
  stackchan_diag_print(static_cast<int>(touch.intensities[1]));
  stackchan_diag_print(" touch_i2=");
  stackchan_diag_print(static_cast<int>(touch.intensities[2]));
  stackchan_diag_print(" touch_output_read_ok=");
  stackchan_diag_print(stackchan_touch_output_read_ok ? "true" : "false");
  stackchan_diag_print(" touch_output_raw=");
  stackchan_diag_print(static_cast<int>(stackchan_touch_output_raw));
  stackchan_diag_print(" touch_output_read_failures=");
  stackchan_diag_print(stackchan_touch_output_read_failures);
  stackchan_diag_print(" ltr553_init=");
  stackchan_diag_print(ltr553_sensor_initialized ? "true" : "false");
  stackchan_diag_print(" ltr553_bus=in_i2c");
  stackchan_diag_print(" ltr553_part_ok=");
  stackchan_diag_print(ltr553_part_id_read_ok ? "true" : "false");
  stackchan_diag_print(" ltr553_part_id=");
  stackchan_diag_print(static_cast<int>(ltr553_part_id));
  stackchan_diag_print(" ltr553_manufacturer_ok=");
  stackchan_diag_print(ltr553_manufacturer_id_read_ok ? "true" : "false");
  stackchan_diag_print(" ltr553_manufacturer_id=");
  stackchan_diag_print(static_cast<int>(ltr553_manufacturer_id));
  stackchan_diag_print(" ps_read_ok=");
  stackchan_diag_print(ltr553_last_ps_read_ok ? "true" : "false");
  stackchan_diag_print(" ps_raw=");
  stackchan_diag_print(proximity.raw);
  stackchan_diag_print(" ps_signal=");
  stackchan_diag_print(proximity.signal);
  stackchan_diag_print(" als_read_ok=");
  stackchan_diag_print(ltr553_last_als_read_ok ? "true" : "false");
  stackchan_diag_print(" als_raw=");
  stackchan_diag_print(light.raw);
  stackchan_diag_print(" als_lux=");
  stackchan_diag_print(light.illuminance_lux);
  stackchan_diag_print(" power_init=");
  stackchan_diag_print(stackchan_power_monitor_initialized ? "true" : "false");
  stackchan_diag_print(" power_voltage_v=");
  stackchan_diag_print(power.voltage_v);
  stackchan_diag_print(" power_current_ma=");
  stackchan_diag_print(power.current_ma);
  stackchan_diag_print(" power_source=");
  stackchan_diag_print(static_cast<int>(power.power_source));
  stackchan_diag_print(" in_i2c_released_for_camera=");
  stackchan_diag_print(stackchan_in_i2c_released_for_camera ? "true" : "false");
  stackchan_diag_print(" camera_probe_ok=");
  stackchan_diag_print(stackchan_camera_snapshot_initialized ? "true" : "false");
  stackchan_diag_print(" camera_init_error=");
  stackchan_diag_println(static_cast<int>(stackchan_camera_init_error));
}
#endif

bool read_imu_sample(stackchan::ImuSample* sample) {
  if (sample == nullptr || !stackchan_imu_initialized) {
    return false;
  }
  if (!M5.Imu.update()) {
    return false;
  }
  float accel_x = 0.0f;
  float accel_y = 0.0f;
  float accel_z = 0.0f;
  float gyro_x = 0.0f;
  float gyro_y = 0.0f;
  float gyro_z = 0.0f;
  if (!M5.Imu.getAccel(&accel_x, &accel_y, &accel_z) ||
      !M5.Imu.getGyro(&gyro_x, &gyro_y, &gyro_z)) {
    return false;
  }
  constexpr float kGravityMps2 = 9.80665f;
  sample->accel_x = accel_x * kGravityMps2;
  sample->accel_y = accel_y * kGravityMps2;
  sample->accel_z = accel_z * kGravityMps2;
  sample->gyro_x = gyro_x;
  sample->gyro_y = gyro_y;
  sample->gyro_z = gyro_z;
  return true;
}

stackchan::Result publish_imu_raw_sample(
    const stackchan::ImuSample& sample,
    uint32_t now_ms) {
  stackchan::ImuRawMsg telemetry{};
  telemetry.device_id.assign(STACKCHAN_DEVICE_ID);
  telemetry.stamp = stackchan::ros_time_from_ms(now_ms);
  telemetry.accel_x = sample.accel_x;
  telemetry.accel_y = sample.accel_y;
  telemetry.accel_z = sample.accel_z;
  telemetry.gyro_x = sample.gyro_x;
  telemetry.gyro_y = sample.gyro_y;
  telemetry.gyro_z = sample.gyro_z;
  telemetry.mag_x = 0.0f;
  telemetry.mag_y = 0.0f;
  telemetry.mag_z = 0.0f;
  telemetry.temperature = NAN;
  return device_publishers.publish_imu_raw(telemetry);
}

stackchan::Result sample_imu_events(uint32_t now_ms) {
  stackchan::ImuSample sample{};
  if (!read_imu_sample(&sample)) {
    return stackchan::Result::accepted("IMU unavailable");
  }
  stackchan::Result result = publish_imu_raw_sample(sample, now_ms);
  if (!result.ok) {
    return result;
  }
  return imu_event_estimator.update(sample, now_ms, event_publisher);
}

stackchan::Result sample_button_events(uint32_t now_ms) {
  stackchan::Result result =
      button_a_event_estimator.update(M5.BtnA.isPressed(), now_ms, event_publisher, "a");
  if (!result.ok) {
    return result;
  }
  result = button_b_event_estimator.update(M5.BtnB.isPressed(), now_ms, event_publisher, "b");
  if (!result.ok) {
    return result;
  }
  return button_c_event_estimator.update(M5.BtnC.isPressed(), now_ms, event_publisher, "c");
}

stackchan::Result sample_nfc_events(uint32_t now_ms) {
  if (!stackchan_nfc_initialized) {
    return stackchan::Result::accepted("NFC unavailable");
  }
  ++stackchan_nfc_detect_attempts;
  stackchan_units.update();
  std::vector<m5::nfc::a::PICC> piccs;
  if (!stackchan_nfc_a.detect(piccs)) {
    return nfc_presence_estimator.update(false, "", now_ms, event_publisher);
  }
  if (piccs.empty()) {
    stackchan_nfc_a.deactivate();
    return nfc_presence_estimator.update(false, "", now_ms, event_publisher);
  }
  ++stackchan_nfc_detect_hits;
  for (auto& picc : piccs) {
    if (stackchan_nfc_a.identify(picc)) {
      const std::string uid = picc.uidAsString();
      const stackchan::Result result =
          nfc_presence_estimator.update(true, uid.c_str(), now_ms, event_publisher);
      stackchan_nfc_a.deactivate();
      return result;
    }
  }
  ++stackchan_nfc_identify_failures;
  stackchan_nfc_a.deactivate();
  return nfc_presence_estimator.update(
      true,
      "",
      now_ms,
      event_publisher,
      stackchan::NfcReadStatus::ReadFailed);
}

stackchan::Result sample_ir_events(uint32_t now_ms) {
  if (!stackchan_ir_initialized || !stackchan_irrecv.decode(&stackchan_ir_results)) {
    return stackchan::Result::accepted("no IR event");
  }
  ++stackchan_ir_decode_count;
  if (stackchan_ir_results.overflow) {
    ++stackchan_ir_overflow_count;
  }
  char remote_summary[48];
  snprintf(
      remote_summary,
      sizeof(remote_summary),
      "%s:%u",
      typeToString(stackchan_ir_results.decode_type, false).c_str(),
      static_cast<unsigned>(stackchan_ir_results.bits));
  stackchan::Result result = event_publisher.remote_button_pressed(now_ms);
  if (result.ok) {
    result = event_publisher.remote_command_received(now_ms, remote_summary);
  }
  stackchan_irrecv.resume();
  return result;
}

stackchan::Result enable_servo_pair_torque() {
  if (!servo_adapter_init_result.ok) {
    return servo_adapter_init_result;
  }
  if (servo_bus.EnableTorque(kYawServoId, 1) != 1 ||
      servo_bus.EnableTorque(kPitchServoId, 1) != 1) {
    return stackchan::Result::rejected(
        "MOTION_INTERRUPTED",
        "servo torque enable failed",
        true);
  }
  return stackchan::Result::accepted("servo torque enabled");
}

stackchan::Result disable_servo_pair_torque() {
  if (!servo_adapter_init_result.ok) {
    return servo_adapter_init_result;
  }
  if (servo_bus.EnableTorque(kYawServoId, 0) != 1 ||
      servo_bus.EnableTorque(kPitchServoId, 0) != 1) {
    return stackchan::Result::rejected(
        "MOTION_INTERRUPTED",
        "servo torque disable failed",
        true);
  }
  return stackchan::Result::accepted("servo torque disabled");
}

stackchan::Result move_servo_pair_to(
    int target_x_deg,
    int target_y_deg,
    int servo_time_ms = kServoTime,
    bool ensure_torque = true) {
  if (!servo_adapter_init_result.ok) {
    return servo_adapter_init_result;
  }

  const int yaw_raw = servo_degrees_to_raw(kYawDefaultZeroPos, target_x_deg);
  const int pitch_raw = servo_degrees_to_raw(kPitchDefaultZeroPos, target_y_deg);
  if (!raw_servo_position_valid(yaw_raw) || !raw_servo_position_valid(pitch_raw)) {
    return stackchan::Result::rejected(
        "SERVO_LIMIT_EXCEEDED",
        "servo target exceeds raw hardware limits",
        true);
  }

  if (ensure_torque) {
    const stackchan::Result torque_result = enable_servo_pair_torque();
    if (!torque_result.ok) {
      return torque_result;
    }
  }
  motion_diag_record_write(
      stackchan::ServoTarget{target_x_deg, target_y_deg},
      yaw_raw,
      pitch_raw,
      servo_time_ms);

  u8 servo_ids[] = {
      static_cast<u8>(kYawServoId),
      static_cast<u8>(kPitchServoId),
  };
  u16 positions[] = {
      static_cast<u16>(yaw_raw),
      static_cast<u16>(pitch_raw),
  };
  u16 times[] = {
      static_cast<u16>(servo_time_ms),
      static_cast<u16>(servo_time_ms),
  };
  u16 speeds[] = {
      static_cast<u16>(kServoSpeed),
      static_cast<u16>(kServoSpeed),
  };
  servo_bus.SyncWritePos(servo_ids, 2, positions, times, speeds);
  return stackchan::Result::accepted("servo move accepted");
}

void motion_diag_reset() {
  motion_diagnostic = {};
  motion_diagnostic.plan_min_x = 0;
  motion_diagnostic.plan_max_x = 0;
  motion_diagnostic.plan_min_y = 0;
  motion_diagnostic.plan_max_y = 0;
  motion_diagnostic.target_min_x = 0;
  motion_diagnostic.target_max_x = 0;
  motion_diagnostic.target_min_y = 0;
  motion_diagnostic.target_max_y = 0;
  motion_diagnostic.raw_min_x = 0;
  motion_diagnostic.raw_max_x = 0;
  motion_diagnostic.raw_min_y = 0;
  motion_diagnostic.raw_max_y = 0;
  motion_diagnostic.time_min_ms = 0;
  motion_diagnostic.time_max_ms = 0;
}

void motion_diag_include_plan_target(const stackchan::ServoTarget& target) {
  if (motion_diagnostic.plan_min_x > motion_diagnostic.plan_max_x) {
    motion_diagnostic.plan_min_x = target.x;
    motion_diagnostic.plan_max_x = target.x;
    motion_diagnostic.plan_min_y = target.y;
    motion_diagnostic.plan_max_y = target.y;
    return;
  }
  if (target.x < motion_diagnostic.plan_min_x) motion_diagnostic.plan_min_x = target.x;
  if (target.x > motion_diagnostic.plan_max_x) motion_diagnostic.plan_max_x = target.x;
  if (target.y < motion_diagnostic.plan_min_y) motion_diagnostic.plan_min_y = target.y;
  if (target.y > motion_diagnostic.plan_max_y) motion_diagnostic.plan_max_y = target.y;
}

void motion_diag_publish_plan() {
#if STACKCHAN_MOTION_DIAGNOSTICS
  if (!motion_diagnostic.active) {
    return;
  }
  char payload[stackchan::kEventPayloadJsonMaxLength + 1];
  snprintf(
      payload,
      sizeof(payload),
      "{\"motion\":\"%s\",\"home_x\":%d,\"home_y\":%d,"
      "\"plan_min_x\":%d,\"plan_max_x\":%d,\"plan_min_y\":%d,\"plan_max_y\":%d,"
      "\"duration_ms\":%lu,\"amp_deg\":%d}",
      motion_diagnostic.name,
      motion_diagnostic.home_x,
      motion_diagnostic.home_y,
      motion_diagnostic.plan_min_x,
      motion_diagnostic.plan_max_x,
      motion_diagnostic.plan_min_y,
      motion_diagnostic.plan_max_y,
      static_cast<unsigned long>(kShakeTrajectoryDurationMs),
      static_cast<int>(kShakeTrajectoryYawAmplitudeDeg));
  event_publisher.publish_name(
      "motion_diag_plan",
      static_cast<uint32_t>(millis()),
      motion_diagnostic.command_id,
      payload);
#endif
}

void motion_diag_start(
    const char* name,
    const char* command_id,
    const stackchan::ServoTarget& home,
    const stackchan::MotionPlan& plan) {
  motion_diag_reset();
#if STACKCHAN_MOTION_DIAGNOSTICS
  if (strcmp(name, "shake") != 0) {
    return;
  }
  motion_diagnostic.active = true;
  copy_bounded(motion_diagnostic.name, sizeof(motion_diagnostic.name), name);
  copy_bounded(
      motion_diagnostic.command_id,
      sizeof(motion_diagnostic.command_id),
      command_id);
  motion_diagnostic.home_x = home.x;
  motion_diagnostic.home_y = home.y;
  motion_diagnostic.plan_min_x = 1;
  motion_diagnostic.plan_max_x = 0;
  for (size_t index = 0; index < plan.waypoint_count; ++index) {
    motion_diag_include_plan_target(apply_motion_offset(home, plan.waypoints[index].offset));
  }
  motion_diag_publish_plan();
#else
  (void)name;
  (void)command_id;
  (void)home;
  (void)plan;
#endif
}

void motion_diag_record_write(
    const stackchan::ServoTarget& target,
    int yaw_raw,
    int pitch_raw,
    int servo_time_ms) {
#if STACKCHAN_MOTION_DIAGNOSTICS
  if (!motion_diagnostic.active) {
    return;
  }
  if (motion_diagnostic.write_count == 0) {
    motion_diagnostic.target_min_x = target.x;
    motion_diagnostic.target_max_x = target.x;
    motion_diagnostic.target_min_y = target.y;
    motion_diagnostic.target_max_y = target.y;
    motion_diagnostic.raw_min_x = yaw_raw;
    motion_diagnostic.raw_max_x = yaw_raw;
    motion_diagnostic.raw_min_y = pitch_raw;
    motion_diagnostic.raw_max_y = pitch_raw;
    motion_diagnostic.time_min_ms = servo_time_ms;
    motion_diagnostic.time_max_ms = servo_time_ms;
  } else {
    if (target.x < motion_diagnostic.target_min_x) motion_diagnostic.target_min_x = target.x;
    if (target.x > motion_diagnostic.target_max_x) motion_diagnostic.target_max_x = target.x;
    if (target.y < motion_diagnostic.target_min_y) motion_diagnostic.target_min_y = target.y;
    if (target.y > motion_diagnostic.target_max_y) motion_diagnostic.target_max_y = target.y;
    if (yaw_raw < motion_diagnostic.raw_min_x) motion_diagnostic.raw_min_x = yaw_raw;
    if (yaw_raw > motion_diagnostic.raw_max_x) motion_diagnostic.raw_max_x = yaw_raw;
    if (pitch_raw < motion_diagnostic.raw_min_y) motion_diagnostic.raw_min_y = pitch_raw;
    if (pitch_raw > motion_diagnostic.raw_max_y) motion_diagnostic.raw_max_y = pitch_raw;
    if (servo_time_ms < motion_diagnostic.time_min_ms) {
      motion_diagnostic.time_min_ms = servo_time_ms;
    }
    if (servo_time_ms > motion_diagnostic.time_max_ms) {
      motion_diagnostic.time_max_ms = servo_time_ms;
    }
  }
  motion_diagnostic.write_count += 1;
#else
  (void)target;
  (void)yaw_raw;
  (void)pitch_raw;
  (void)servo_time_ms;
#endif
}

void motion_diag_publish_writes() {
#if STACKCHAN_MOTION_DIAGNOSTICS
  if (!motion_diagnostic.active) {
    return;
  }
  char payload[stackchan::kEventPayloadJsonMaxLength + 1];
  snprintf(
      payload,
      sizeof(payload),
      "{\"writes\":%lu,\"target_min_x\":%d,\"target_max_x\":%d,"
      "\"target_min_y\":%d,\"target_max_y\":%d,"
      "\"raw_min_x\":%d,\"raw_max_x\":%d,\"raw_min_y\":%d,\"raw_max_y\":%d,"
      "\"time_min_ms\":%d,\"time_max_ms\":%d}",
      static_cast<unsigned long>(motion_diagnostic.write_count),
      motion_diagnostic.target_min_x,
      motion_diagnostic.target_max_x,
      motion_diagnostic.target_min_y,
      motion_diagnostic.target_max_y,
      motion_diagnostic.raw_min_x,
      motion_diagnostic.raw_max_x,
      motion_diagnostic.raw_min_y,
      motion_diagnostic.raw_max_y,
      motion_diagnostic.time_min_ms,
      motion_diagnostic.time_max_ms);
  event_publisher.publish_name(
      "motion_diag_writes",
      static_cast<uint32_t>(millis()),
      motion_diagnostic.command_id,
      payload);
#endif
}

stackchan::ServoTarget calibrated_home_target() {
  const stackchan::ServoCalibration& servo = calibration_store.record().servo;
  return {
      servo.home_x + servo.correction_x,
      servo.home_y + servo.correction_y,
  };
}

stackchan::ServoTarget apply_motion_offset(
    const stackchan::ServoTarget& home,
    const stackchan::ServoTarget& offset) {
  return {
      home.x + offset.x,
      home.y + offset.y,
  };
}

stackchan::Result move_servo_pair_to(
    const stackchan::ServoTarget& target,
    int servo_time_ms = kServoTime,
    bool ensure_torque = true) {
  return move_servo_pair_to(target.x, target.y, servo_time_ms, ensure_torque);
}

uint32_t ease_out_cubic_progress(uint32_t t) {
  constexpr uint32_t kScale = 1000;
  const uint32_t inverse = kScale - t;
  return kScale - (inverse * inverse * inverse) / (kScale * kScale);
}

uint32_t ease_in_out_cubic_progress(uint32_t t) {
  constexpr uint32_t kScale = 1000;
  if (t < kScale / 2) {
    return (4 * t * t * t) / (kScale * kScale);
  }
  const uint32_t inverse = kScale - t;
  return kScale - (4 * inverse * inverse * inverse) / (kScale * kScale);
}

uint32_t ease_out_sine_progress(uint32_t t) {
  constexpr uint32_t kScale = 1000;
  return (t * (2 * kScale - t)) / kScale;
}

uint32_t eased_motion_progress(
    uint32_t elapsed_ms,
    uint32_t duration_ms,
    stackchan::MotionEasing easing) {
  constexpr uint32_t kScale = 1000;
  if (duration_ms == 0 || elapsed_ms >= duration_ms) {
    return kScale;
  }
  const uint32_t t = (elapsed_ms * kScale) / duration_ms;
  switch (easing) {
    case stackchan::MotionEasing::Linear:
      return t;
    case stackchan::MotionEasing::EaseOutSine:
      return ease_out_sine_progress(t);
    case stackchan::MotionEasing::EaseOutBackLike:
      return ease_out_cubic_progress(t);
    case stackchan::MotionEasing::EaseInOutCubic:
    default:
      return ease_in_out_cubic_progress(t);
  }
}

int interpolate_motion_axis(int start, int end, uint32_t progress) {
  constexpr int32_t kScale = 1000;
  const int32_t delta = end - start;
  const int32_t weighted = delta * static_cast<int32_t>(progress);
  const int32_t rounded = weighted >= 0
                              ? (weighted + kScale / 2) / kScale
                              : (weighted - kScale / 2) / kScale;
  return start + rounded;
}

stackchan::ServoTarget interpolate_motion_target(
    const stackchan::ServoTarget& start,
    const stackchan::ServoTarget& end,
    uint32_t progress) {
  return {
      interpolate_motion_axis(start.x, end.x, progress),
      interpolate_motion_axis(start.y, end.y, progress),
  };
}

int rounded_float_to_int(float value) {
  return static_cast<int>(value >= 0.0f ? value + 0.5f : value - 0.5f);
}

float sinusoidal_motion_wave(float phase) {
  return sinf(phase * 2.0f * kMotionPi);
}

stackchan::ServoTarget continuous_shake_target(
    const stackchan::ServoTarget& home,
    uint32_t elapsed_ms) {
  float normalized =
      static_cast<float>(elapsed_ms) / static_cast<float>(kShakeTrajectoryDurationMs);
  if (normalized < 0.0f) {
    normalized = 0.0f;
  }
  if (normalized > 1.0f) {
    normalized = 1.0f;
  }

  const float wave = sinusoidal_motion_wave(normalized * kShakeTrajectoryCycles);
  const float taper = 1.0f - kShakeTrajectoryYawTaperRatio * normalized;
  const float side_emphasis = wave * wave;
  const int x_offset = rounded_float_to_int(kShakeTrajectoryYawAmplitudeDeg * taper * wave);
  const int y_offset =
      rounded_float_to_int(kShakeTrajectoryPitchBaseDeg +
                           kShakeTrajectoryPitchAmplitudeDeg * side_emphasis);
  return {
      home.x + x_offset,
      home.y + y_offset,
  };
}

stackchan::ServoTarget motion_segment_start_target(size_t waypoint_index) {
  if (waypoint_index == 0 || waypoint_index > motion_scheduler.waypoint_count) {
    return motion_scheduler.home;
  }
  return apply_motion_offset(
      motion_scheduler.home,
      motion_scheduler.waypoints[waypoint_index - 1].offset);
}

stackchan::ServoTarget motion_return_home_start_target() {
  if (strcmp(motion_scheduler.name, "shake") == 0) {
    return continuous_shake_target(motion_scheduler.home, kShakeTrajectoryDurationMs);
  }
  return motion_segment_start_target(motion_scheduler.waypoint_count);
}

uint32_t motion_axis_distance(int start, int end) {
  return start > end
             ? static_cast<uint32_t>(start - end)
             : static_cast<uint32_t>(end - start);
}

uint16_t clamp_motion_segment_duration(uint32_t duration_ms) {
  constexpr uint16_t kCheerfulMotionDistanceDurationMaxMs = 1200;
  if (duration_ms > kCheerfulMotionDistanceDurationMaxMs) {
    return kCheerfulMotionDistanceDurationMaxMs;
  }
  return static_cast<uint16_t>(duration_ms);
}

uint16_t cheerful_distance_adjusted_segment_duration(
    const stackchan::ServoTarget& start,
    const stackchan::ServoTarget& end,
    uint16_t style_floor_ms) {
  constexpr uint16_t kCheerfulMotionDistanceBaseMs = 190;
  constexpr uint16_t kCheerfulMotionMsPerDegree = 7;
  const uint32_t dx = motion_axis_distance(start.x, end.x);
  const uint32_t dy = motion_axis_distance(start.y, end.y);
  const uint32_t max_axis_distance = dx > dy ? dx : dy;
  const uint32_t distance_duration_ms =
      kCheerfulMotionDistanceBaseMs + max_axis_distance * kCheerfulMotionMsPerDegree;
  const uint32_t adjusted_duration_ms =
      distance_duration_ms > style_floor_ms ? distance_duration_ms : style_floor_ms;
  return clamp_motion_segment_duration(adjusted_duration_ms);
}

void start_motion_segment(
    const stackchan::ServoTarget& start,
    const stackchan::ServoTarget& end,
    stackchan::MotionEasing easing,
    uint16_t duration_ms,
    unsigned long now) {
  motion_scheduler.segment_initialized = true;
  motion_scheduler.segment_start = start;
  motion_scheduler.segment_end = end;
  motion_scheduler.segment_easing = easing;
  motion_scheduler.segment_duration_ms =
      strcmp(motion_scheduler.name, "cheerful") == 0
          ? cheerful_distance_adjusted_segment_duration(start, end, duration_ms)
          : duration_ms;
  motion_scheduler.segment_started_ms = now;
  motion_scheduler.last_retarget_ms = 0;
}

stackchan::Result advance_motion_segment(unsigned long now, bool* completed) {
  if (completed == nullptr) {
    return stackchan::Result::rejected("MOTION_INTERRUPTED", "motion segment state invalid", true);
  }
  *completed = false;
  if (!motion_scheduler.segment_initialized) {
    return stackchan::Result::rejected("MOTION_INTERRUPTED", "motion segment not initialized", true);
  }

  uint32_t elapsed_ms = static_cast<uint32_t>(now - motion_scheduler.segment_started_ms);
  if (elapsed_ms >= motion_scheduler.segment_duration_ms) {
    *completed = true;
    if (strcmp(motion_scheduler.name, "shake") == 0 &&
        motion_scheduler.phase == MotionSchedulerPhase::MoveWaypoint) {
      return stackchan::Result::accepted("motion segment completed");
    }
    return move_servo_pair_to(
        motion_scheduler.segment_end,
        kMotionSegmentTickServoTimeMs,
        false);
  }

  if (motion_scheduler.last_retarget_ms != 0 &&
      now - motion_scheduler.last_retarget_ms < kMotionSegmentTickIntervalMs) {
    return stackchan::Result::accepted("motion segment waiting");
  }

  if (motion_scheduler.last_retarget_ms == 0 &&
      elapsed_ms < kMotionSegmentTickIntervalMs) {
    elapsed_ms = kMotionSegmentTickIntervalMs;
  }
  const uint32_t progress =
      eased_motion_progress(
          elapsed_ms,
          motion_scheduler.segment_duration_ms,
          motion_scheduler.segment_easing);
  const stackchan::ServoTarget target =
      interpolate_motion_target(
          motion_scheduler.segment_start,
          motion_scheduler.segment_end,
          progress);
  const stackchan::Result result =
      move_servo_pair_to(target, kMotionSegmentTickServoTimeMs, false);
  if (result.ok) {
    motion_scheduler.last_retarget_ms = now;
  }
  return result;
}

void reset_motion_scheduler() {
  motion_scheduler.active = false;
  motion_status_publish_pending = false;
  motion_scheduler.phase = MotionSchedulerPhase::Idle;
  motion_scheduler.home = stackchan::kNeutralTarget;
  for (size_t index = 0; index < stackchan::kMaxMotionWaypoints; ++index) {
    motion_scheduler.waypoints[index] = {
        stackchan::kNeutralTarget,
        0,
        stackchan::kDefaultNamedMotionServoTimeMs,
        stackchan::MotionEasing::EaseInOutCubic};
  }
  motion_scheduler.waypoint_count = 0;
  motion_scheduler.waypoint_index = 0;
  motion_scheduler.servo_time_ms = stackchan::kDefaultNamedMotionServoTimeMs;
  motion_scheduler.segment_initialized = false;
  motion_scheduler.segment_start = stackchan::kNeutralTarget;
  motion_scheduler.segment_end = stackchan::kNeutralTarget;
  motion_scheduler.segment_easing = stackchan::MotionEasing::EaseInOutCubic;
  motion_scheduler.segment_duration_ms = stackchan::kDefaultNamedMotionServoTimeMs;
  motion_scheduler.segment_started_ms = 0;
  motion_scheduler.last_retarget_ms = 0;
  motion_scheduler.phase_started_ms = 0;
  copy_bounded(motion_scheduler.name, sizeof(motion_scheduler.name), "");
  copy_bounded(motion_scheduler.command_id, sizeof(motion_scheduler.command_id), "");
  motion_diag_reset();
}

stackchan::Result try_motion_neutral_recovery() {
  if (!firmware_calibration_valid()) {
    return stackchan::Result::rejected(
        "CALIBRATION_INVALID",
        "neutral recovery calibration is invalid",
        true);
  }
  return move_servo_pair_to(calibrated_home_target());
}

void finish_motion_scheduler(const stackchan::Result& result) {
  stackchan::Result final_result = result;
  if (result.ok) {
    const stackchan::Result torque_result = disable_servo_pair_torque();
    if (!torque_result.ok) {
      final_result = torque_result;
    }
  }
  last_error = final_result;
  copy_bounded(current_motion, sizeof(current_motion), "idle");
  if (state_machine.state() == stackchan::RuntimeState::Acting) {
    state_machine.command_finished();
  }
  motion_diag_publish_writes();
  reset_motion_scheduler();
  publish_status_heartbeat();
}

void fail_motion_scheduler(const stackchan::Result& result) {
  const bool safety_fault = is_servo_safety_fault(result);
  const stackchan::Result recovery_result = try_motion_neutral_recovery();
  last_error = result;
  if (safety_fault || !recovery_result.ok) {
    state_machine.fault();
  } else {
    if (state_machine.state() == stackchan::RuntimeState::Acting) {
      state_machine.command_finished();
    }
  }
  copy_bounded(current_motion, sizeof(current_motion), "idle");
  motion_diag_publish_writes();
  reset_motion_scheduler();
  publish_status_heartbeat();
}

stackchan::Result enqueue_motion_scheduler(
    const stackchan::MotionPlan& plan,
    const char* name,
    const char* command_id,
    unsigned long now) {
  if (motion_scheduler.active || state_machine.state() == stackchan::RuntimeState::Acting) {
    return stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "motion scheduler already has an active command",
        true);
  }

  if (plan.waypoint_count == 0) {
    copy_bounded(current_motion, sizeof(current_motion), "idle");
    last_error = stackchan::Result::accepted("motion idle accepted");
    publish_status_heartbeat();
    return stackchan::Result::accepted("motion accepted");
  }

  const stackchan::ServoTarget home = calibrated_home_target();
  stackchan::Result target_result = validate_motion_servo_target(home, "home");
  if (!target_result.ok) {
    return target_result;
  }

  for (size_t index = 0; index < plan.waypoint_count; ++index) {
    const stackchan::ServoTarget target = apply_motion_offset(home, plan.waypoints[index].offset);
    target_result = validate_motion_servo_target(target, "motion", true);
    if (!target_result.ok) {
      return target_result;
    }
  }

  const stackchan::Result torque_result = enable_servo_pair_torque();
  if (!torque_result.ok) {
    return torque_result;
  }

  motion_scheduler.active = true;
  motion_scheduler.phase =
      strcmp(name, "shake") == 0 ? MotionSchedulerPhase::ShakeTrajectory
                                 : MotionSchedulerPhase::MoveWaypoint;
  motion_scheduler.home = home;
  for (size_t index = 0; index < stackchan::kMaxMotionWaypoints; ++index) {
    motion_scheduler.waypoints[index] = index < plan.waypoint_count
                                            ? plan.waypoints[index]
                                            : stackchan::MotionWaypoint{
                                                  stackchan::kNeutralTarget,
                                                  0,
                                                  stackchan::kDefaultNamedMotionServoTimeMs,
                                                  stackchan::MotionEasing::EaseInOutCubic};
  }
  motion_scheduler.waypoint_count = plan.waypoint_count;
  motion_scheduler.waypoint_index = 0;
  motion_scheduler.servo_time_ms = plan.servo_time_ms;
  motion_scheduler.phase_started_ms = now;
  copy_bounded(motion_scheduler.name, sizeof(motion_scheduler.name), name);
  copy_bounded(motion_scheduler.command_id, sizeof(motion_scheduler.command_id), command_id);
  motion_diag_start(name, command_id, home, plan);
  state_machine.command_started();
  copy_bounded(current_motion, sizeof(current_motion), motion_scheduler.name);
  motion_status_publish_pending = true;
  last_error = stackchan::Result::accepted("motion scheduled");
  return stackchan::Result::accepted("motion accepted");
}

void step_motion_scheduler(unsigned long now) {
  if (!motion_scheduler.active) {
    return;
  }

  if (motion_status_publish_pending) {
    motion_status_publish_pending = false;
    publish_status_heartbeat();
  }

  if (state_machine.state() == stackchan::RuntimeState::Fault) {
    fail_motion_scheduler(
        stackchan::Result::rejected(
            "MOTION_INTERRUPTED",
            "motion interrupted by firmware fault",
            true));
    return;
  }

  if (motion_scheduler.phase == MotionSchedulerPhase::FinalSettle) {
    const unsigned long elapsed_ms = now - motion_scheduler.phase_started_ms;
    if (elapsed_ms < kMotionFinalSettleMinMs) {
      return;
    }
    bool moving = true;
    if (servo_pair_moving(&moving) && !moving) {
      finish_motion_scheduler(stackchan::Result::accepted("motion completed"));
      return;
    }
    if (elapsed_ms >= kMotionFinalSettleTimeoutMs) {
      finish_motion_scheduler(stackchan::Result::accepted("motion completed"));
    }
    return;
  }

  if (motion_scheduler.phase == MotionSchedulerPhase::ShakeTrajectory) {
    const unsigned long elapsed_ms = now - motion_scheduler.phase_started_ms;
    if (elapsed_ms >= kShakeTrajectoryDurationMs) {
      motion_scheduler.phase = MotionSchedulerPhase::ReturnHome;
      motion_scheduler.phase_started_ms = now;
      motion_scheduler.segment_initialized = false;
      step_motion_scheduler(now);
      return;
    }
    if (motion_scheduler.last_retarget_ms != 0 &&
        now - motion_scheduler.last_retarget_ms < kMotionSegmentTickIntervalMs) {
      return;
    }
    const uint32_t target_elapsed_ms =
        elapsed_ms < kMotionSegmentTickIntervalMs
            ? kMotionSegmentTickIntervalMs
            : static_cast<uint32_t>(elapsed_ms);
    const stackchan::ServoTarget target =
        continuous_shake_target(motion_scheduler.home, target_elapsed_ms);
    const stackchan::Result result =
        move_servo_pair_to(target, kShakeTrajectoryTickServoTimeMs, false);
    if (!result.ok) {
      fail_motion_scheduler(result);
      return;
    }
    motion_scheduler.last_retarget_ms = now;
    return;
  }

  if (motion_scheduler.phase == MotionSchedulerPhase::MoveWaypoint &&
      motion_scheduler.waypoint_index >= motion_scheduler.waypoint_count) {
    motion_scheduler.phase = MotionSchedulerPhase::ReturnHome;
    motion_scheduler.phase_started_ms = now;
    motion_scheduler.segment_initialized = false;
  }

  if (motion_scheduler.phase == MotionSchedulerPhase::ReturnHome) {
    if (!motion_scheduler.segment_initialized) {
      start_motion_segment(
          motion_return_home_start_target(),
          motion_scheduler.home,
          stackchan::MotionEasing::EaseInOutCubic,
          motion_scheduler.servo_time_ms,
          now);
    }
    bool completed = false;
    const stackchan::Result result = advance_motion_segment(now, &completed);
    if (!result.ok) {
      fail_motion_scheduler(result);
      return;
    }
    if (!completed) {
      return;
    }
    motion_scheduler.segment_initialized = false;
    motion_scheduler.phase = MotionSchedulerPhase::FinalSettle;
    motion_scheduler.phase_started_ms = now;
    return;
  }

  if (motion_scheduler.phase == MotionSchedulerPhase::MoveWaypoint) {
    const stackchan::MotionWaypoint& waypoint =
        motion_scheduler.waypoints[motion_scheduler.waypoint_index];
    const stackchan::ServoTarget target = apply_motion_offset(motion_scheduler.home, waypoint.offset);
    const uint16_t servo_time_ms =
        waypoint.servo_time_ms == 0 ? motion_scheduler.servo_time_ms : waypoint.servo_time_ms;
    if (!motion_scheduler.segment_initialized) {
      start_motion_segment(
          motion_segment_start_target(motion_scheduler.waypoint_index),
          target,
          waypoint.easing,
          servo_time_ms,
          now);
    }
    bool completed = false;
    const stackchan::Result result = advance_motion_segment(now, &completed);
    if (!result.ok) {
      fail_motion_scheduler(result);
      return;
    }
    if (!completed) {
      return;
    }
    motion_scheduler.segment_initialized = false;
    if (waypoint.hold_ms == 0) {
      motion_scheduler.waypoint_index += 1;
      if (motion_scheduler.waypoint_index >= motion_scheduler.waypoint_count) {
        motion_scheduler.phase = MotionSchedulerPhase::ReturnHome;
      } else {
        motion_scheduler.phase = MotionSchedulerPhase::MoveWaypoint;
      }
      motion_scheduler.phase_started_ms = now;
      step_motion_scheduler(now);
      return;
    }
    motion_scheduler.phase = MotionSchedulerPhase::HoldWaypoint;
    motion_scheduler.phase_started_ms = now;
    return;
  }

  if (motion_scheduler.phase == MotionSchedulerPhase::HoldWaypoint) {
    const stackchan::MotionWaypoint& waypoint =
        motion_scheduler.waypoints[motion_scheduler.waypoint_index];
    if (now - motion_scheduler.phase_started_ms < waypoint.hold_ms) {
      return;
    }
    motion_scheduler.waypoint_index += 1;
    if (motion_scheduler.waypoint_index >= motion_scheduler.waypoint_count) {
      motion_scheduler.phase = MotionSchedulerPhase::ReturnHome;
      motion_scheduler.phase_started_ms = now;
      motion_scheduler.segment_initialized = false;
      step_motion_scheduler(now);
      return;
    }
    motion_scheduler.phase = MotionSchedulerPhase::MoveWaypoint;
    motion_scheduler.segment_initialized = false;
    step_motion_scheduler(now);
  }
}

stackchan::Result load_calibration_from_nvs() {
  calibration_store.reset();
  Preferences calibration_preferences;
  if (!calibration_preferences.begin(stackchan::kCalibrationNvsNamespace, true)) {
    return stackchan::Result::rejected(
        "CALIBRATION_INVALID",
        "calibration nvs unavailable",
        true);
  }

  const size_t record_size =
      calibration_preferences.getBytesLength(stackchan::kCalibrationNvsKey);
  if (record_size == 0) {
    calibration_preferences.end();
    return stackchan::Result::rejected(
        "CALIBRATION_INVALID",
        "calibration record missing",
        true);
  }
  if (record_size != sizeof(stackchan::CalibrationRecord)) {
    calibration_preferences.end();
    return stackchan::Result::rejected(
        "CALIBRATION_INVALID",
        "calibration record size mismatch",
        true);
  }

  stackchan::CalibrationRecord record{};
  const size_t read_size =
      calibration_preferences.getBytes(
          stackchan::kCalibrationNvsKey,
          &record,
          sizeof(record));
  calibration_preferences.end();
  if (read_size != sizeof(record)) {
    return stackchan::Result::rejected(
        "CALIBRATION_INVALID",
        "calibration record read failed",
        true);
  }

  return calibration_store.load_from_nvs_record(record);
}

stackchan::Result write_calibration_to_nvs(const stackchan::CalibrationRecord& record) {
  const stackchan::Result validation = stackchan::validate_calibration_record(record);
  if (!validation.ok) {
    calibration_store.reset();
    return validation;
  }

  Preferences calibration_preferences;
  if (!calibration_preferences.begin(stackchan::kCalibrationNvsNamespace, false)) {
    calibration_store.reset();
    return stackchan::Result::rejected(
        "CALIBRATION_INVALID",
        "calibration nvs unavailable",
        true);
  }

  const size_t write_size =
      calibration_preferences.putBytes(
          stackchan::kCalibrationNvsKey,
          &record,
          sizeof(record));
  calibration_preferences.end();
  if (write_size != sizeof(record)) {
    calibration_store.reset();
    return stackchan::Result::rejected(
        "CALIBRATION_INVALID",
        "calibration record write failed",
        true);
  }

  return calibration_store.load_from_nvs_record(record);
}

stackchan::Result reset_calibration_nvs() {
  Preferences calibration_preferences;
  if (!calibration_preferences.begin(stackchan::kCalibrationNvsNamespace, false)) {
    calibration_store.reset();
    return stackchan::Result::rejected(
        "CALIBRATION_INVALID",
        "calibration nvs unavailable",
        true);
  }

  calibration_preferences.remove(stackchan::kCalibrationNvsKey);
  calibration_preferences.end();
  calibration_store.reset();
  return stackchan::Result::accepted("calibration reset");
}

stackchan::Result apply_calibration_maintenance_action() {
#if defined(STACKCHAN_CALIBRATION_MAINTENANCE_ENABLE) && defined(STACKCHAN_CALIBRATION_MAINTENANCE_RESET)
  return reset_calibration_nvs();
#elif defined(STACKCHAN_CALIBRATION_MAINTENANCE_ENABLE) && defined(STACKCHAN_CALIBRATION_MAINTENANCE_SEED)
  const stackchan::ServoCalibration servo{
      STACKCHAN_CALIBRATION_SEED_HOME_X,
      STACKCHAN_CALIBRATION_SEED_HOME_Y,
      STACKCHAN_CALIBRATION_SEED_CORRECTION_X,
      STACKCHAN_CALIBRATION_SEED_CORRECTION_Y,
      0,
      0,
  };
  const stackchan::CalibrationRecord record =
      stackchan::make_calibration_record(servo);
  return write_calibration_to_nvs(record);
#else
  return stackchan::Result::accepted("calibration maintenance inactive");
#endif
}

const char* runtime_state_name(stackchan::RuntimeState state) {
  switch (state) {
    case stackchan::RuntimeState::Booting:
      return "booting";
    case stackchan::RuntimeState::WaitingForAgent:
      return "waiting_for_agent";
    case stackchan::RuntimeState::Idle:
      return "ready";
    case stackchan::RuntimeState::Acting:
      return "acting";
    case stackchan::RuntimeState::Degraded:
      return "degraded";
    case stackchan::RuntimeState::Fault:
      return "fault";
  }
  return "unknown";
}

bool servo_position_read_available() {
  int yaw_raw = -1;
  int pitch_raw = -1;
  return servo_adapter_init_result.ok &&
         read_servo_raw_positions(&yaw_raw, &pitch_raw);
}

void update_servo_health_cache(unsigned long now, bool force = false) {
  if (!firmware_calibration_valid() || !servo_adapter_init_result.ok) {
    servo_position_read_available_cache = false;
    last_servo_health_check_ms = now;
    return;
  }
  if (!force &&
      last_servo_health_check_ms != 0 &&
      now - last_servo_health_check_ms < kServoHealthCheckIntervalMs) {
    return;
  }
  servo_position_read_available_cache = servo_position_read_available();
  last_servo_health_check_ms = now;
}

bool servo_target_within_limits(
    const stackchan::ServoTarget& target,
    stackchan::ServoLimits limits = stackchan::kDefaultServoLimits) {
  return target.x >= limits.min_x &&
         target.x <= limits.max_x &&
         target.y >= limits.min_y &&
         target.y <= limits.max_y;
}

stackchan::Result validate_motion_servo_target(
    const stackchan::ServoTarget& target,
    const char* label,
    bool normal_operation) {
  const bool hard_limits_ok = servo_target_within_limits(target);
  const bool normal_limits_ok =
      !normal_operation ||
      target.y == stackchan::kNeutralTarget.y ||
      (target.y >= stackchan::kNormalServoMinY &&
       target.y <= stackchan::kNormalServoMaxY);
  if (hard_limits_ok && normal_limits_ok) {
    return stackchan::Result::accepted("servo target accepted");
  }
  char message[96] = "";
  snprintf(
      message,
      sizeof(message),
      "%s servo target exceeds firmware %s limits",
      label == nullptr ? "motion" : label,
      hard_limits_ok ? "normal-operation" : "degree");
  return stackchan::Result::rejected("SERVO_LIMIT_EXCEEDED", message, true);
}

void reset_rcl_error() {
  if (rcl_error_is_set()) {
    rcl_reset_error();
  }
}

void record_microros_publish_failure() {
  ++microros_publish_failed_count;
  if (microros_consecutive_publish_failures < 255) {
    ++microros_consecutive_publish_failures;
  }
}

void record_microros_publish_success() {
  ++microros_publish_ok_count;
  microros_consecutive_publish_failures = 0;
}

bool microros_publish_failures_exceeded() {
  return microros_consecutive_publish_failures >=
         kMicrorosMaxConsecutivePublishFailures;
}

bool rcl_ok(rcl_ret_t result, const char* step) {
  if (result == RCL_RET_OK) {
    return true;
  }
  stackchan_diag_print("stackchan micro_ros_step=");
  stackchan_diag_print(step);
  stackchan_diag_print(" result=");
  stackchan_diag_println(result);
  reset_rcl_error();
  return false;
}

void build_node_namespace() {
  snprintf(
      microros_node_namespace,
      sizeof(microros_node_namespace),
      "/stackchan/%s/device",
      STACKCHAN_DEVICE_ID);
  microros_node_namespace[sizeof(microros_node_namespace) - 1] = '\0';
}

rmw_qos_profile_t qos_profile_for(stackchan::DevicePublisherTopic topic) {
  rmw_qos_profile_t profile = rmw_qos_profile_default;
  const stackchan::DevicePublisherQos qos = device_publishers.qos(topic);
  profile.depth = qos.depth;
  profile.reliability =
      qos.reliability == stackchan::RosReliability::BestEffort
          ? RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT
          : RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  profile.durability =
      qos.transient_local
          ? RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL
          : RMW_QOS_POLICY_DURABILITY_VOLATILE;
  return profile;
}

rcl_action_server_options_t stackchan_action_server_options() {
  rcl_action_server_options_t options = rcl_action_server_get_default_options();
  options.goal_service_qos.depth = 1;
  options.cancel_service_qos.depth = 1;
  options.result_service_qos.depth = 1;
  options.feedback_topic_qos.reliability =
      RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  options.feedback_topic_qos.durability =
      RMW_QOS_POLICY_DURABILITY_VOLATILE;
  options.feedback_topic_qos.depth = 1;
  options.status_topic_qos.reliability =
      RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  options.status_topic_qos.durability =
      RMW_QOS_POLICY_DURABILITY_VOLATILE;
  options.status_topic_qos.depth = 1;
  options.result_timeout.nanoseconds = RCL_MS_TO_NS(5000);
  return options;
}

bool assign_ros_string(rosidl_runtime_c__String* destination, const char* value) {
  return rosidl_runtime_c__String__assign(destination, value == nullptr ? "" : value);
}

bool reserve_ros_string(rosidl_runtime_c__String* destination, size_t capacity) {
  if (destination == nullptr || capacity > 160) {
    return false;
  }
  char reserve[161] = "";
  memset(reserve, '.', capacity);
  reserve[capacity] = '\0';
  if (!rosidl_runtime_c__String__assignn(destination, reserve, capacity)) {
    return false;
  }
  destination->size = 0;
  destination->data[0] = '\0';
  return true;
}

bool reserve_face_set_request_strings() {
  return reserve_ros_string(&face_set_request.meta.device_id, 32) &&
         reserve_ros_string(&face_set_request.meta.command_id, 36) &&
         reserve_ros_string(&face_set_request.meta.source, 32) &&
         reserve_ros_string(&face_set_request.name, 32);
}

bool reserve_led_set_request_strings() {
  return reserve_ros_string(&led_set_request.meta.device_id, 32) &&
         reserve_ros_string(&led_set_request.meta.command_id, 36) &&
         reserve_ros_string(&led_set_request.meta.source, 32) &&
         reserve_ros_string(&led_set_request.pattern, 32) &&
         reserve_ros_string(&led_set_request.color, 16);
}

bool reserve_motion_set_request_strings() {
  return reserve_ros_string(&motion_set_request.meta.device_id, 32) &&
         reserve_ros_string(&motion_set_request.meta.command_id, 36) &&
         reserve_ros_string(&motion_set_request.meta.source, 32) &&
         reserve_ros_string(&motion_set_request.name, 32);
}

bool reserve_head_pose_set_request_strings() {
  return reserve_ros_string(&head_pose_set_request.meta.device_id, 32) &&
         reserve_ros_string(&head_pose_set_request.meta.command_id, 36) &&
         reserve_ros_string(&head_pose_set_request.meta.source, 32);
}

bool reserve_play_audio_goal_strings() {
  rosidl_runtime_c__uint8__Sequence__fini(
      &play_audio_goal_request.goal.first_chunk_pcm);
  return reserve_ros_string(&play_audio_goal_request.goal.meta.device_id, 32) &&
         reserve_ros_string(&play_audio_goal_request.goal.meta.command_id, 36) &&
         reserve_ros_string(&play_audio_goal_request.goal.meta.source, 32) &&
         reserve_ros_string(&play_audio_goal_request.goal.format, 16) &&
         rosidl_runtime_c__uint8__Sequence__init(
             &play_audio_goal_request.goal.first_chunk_pcm,
             stackchan::kAudioMaxChunkBytes) &&
         reserve_ros_string(&play_audio_goal_request.goal.face_hint, 32) &&
         reserve_ros_string(&play_audio_goal_request.goal.motion_hint, 32);
}

bool reserve_audio_playback_chunk_service_storage() {
  rosidl_runtime_c__uint8__Sequence__fini(
      &audio_playback_chunk_response.chunk.pcm);
  return reserve_ros_string(&audio_playback_chunk_request.meta.device_id, 32) &&
         reserve_ros_string(&audio_playback_chunk_request.meta.command_id, 36) &&
         reserve_ros_string(&audio_playback_chunk_request.meta.source, 32) &&
         reserve_ros_string(&audio_playback_chunk_response.result.error_code, 48) &&
         reserve_ros_string(&audio_playback_chunk_response.result.message, 160) &&
         reserve_ros_string(&audio_playback_chunk_response.chunk.device_id, 32) &&
         reserve_ros_string(&audio_playback_chunk_response.chunk.command_id, 36) &&
         rosidl_runtime_c__uint8__Sequence__init(
             &audio_playback_chunk_response.chunk.pcm,
             stackchan::kAudioMaxChunkBytes);
}

bool reserve_audio_playback_ack_message_storage() {
  return reserve_ros_string(&audio_playback_ack_ros_message.device_id, 32) &&
         reserve_ros_string(&audio_playback_ack_ros_message.command_id, 36);
}

bool reserve_audio_playback_load_service_storage() {
  rosidl_runtime_c__uint8__Sequence__fini(&audio_playback_load_request.pcm);
  return reserve_ros_string(&audio_playback_load_request.meta.device_id, 32) &&
         reserve_ros_string(&audio_playback_load_request.meta.command_id, 36) &&
         reserve_ros_string(&audio_playback_load_request.meta.source, 32) &&
         rosidl_runtime_c__uint8__Sequence__init(
             &audio_playback_load_request.pcm,
             stackchan::kAudioMaxChunkBytes) &&
         reserve_ros_string(&audio_playback_load_response.result.error_code, 48) &&
         reserve_ros_string(&audio_playback_load_response.result.message, 160);
}

bool reserve_capture_audio_goal_strings() {
  return reserve_ros_string(&capture_audio_goal_request.goal.meta.device_id, 32) &&
         reserve_ros_string(&capture_audio_goal_request.goal.meta.command_id, 36) &&
         reserve_ros_string(&capture_audio_goal_request.goal.meta.source, 32) &&
         reserve_ros_string(&capture_audio_goal_request.goal.format, 16) &&
         reserve_ros_string(&capture_audio_feedback_message.feedback.message, 160);
}

bool reserve_capture_camera_goal_strings() {
  return reserve_ros_string(&capture_camera_goal_request.goal.meta.device_id, 32) &&
         reserve_ros_string(&capture_camera_goal_request.goal.meta.command_id, 36) &&
         reserve_ros_string(&capture_camera_goal_request.goal.meta.source, 32) &&
         reserve_ros_string(&capture_camera_goal_request.goal.format, 16) &&
         reserve_ros_string(&capture_camera_feedback_message.feedback.message, 160);
}

bool reserve_capture_camera_result_storage() {
  return reserve_ros_string(&capture_camera_result_response.result.image.format, 16);
}

bool reserve_camera_frame_chunk_message_storage() {
  rosidl_runtime_c__uint8__Sequence__fini(&camera_frame_chunk_ros_message.data);
  return reserve_ros_string(&camera_frame_chunk_ros_message.device_id, 32) &&
         reserve_ros_string(&camera_frame_chunk_ros_message.command_id, 36) &&
         rosidl_runtime_c__uint8__Sequence__init(
             &camera_frame_chunk_ros_message.data,
             stackchan::kCameraFrameChunkBytes);
}

bool reserve_audio_chunk_message_storage() {
  rosidl_runtime_c__uint8__Sequence__fini(&audio_chunk_ros_message.pcm);
  return reserve_ros_string(&audio_chunk_ros_message.device_id, 32) &&
         reserve_ros_string(&audio_chunk_ros_message.command_id, 36) &&
         rosidl_runtime_c__uint8__Sequence__init(
             &audio_chunk_ros_message.pcm,
             stackchan::kAudioMaxChunkBytes);
}

bool reserve_audio_capture_chunk_message_storage() {
  rosidl_runtime_c__uint8__Sequence__fini(&audio_capture_chunk_ros_message.pcm);
  return reserve_ros_string(&audio_capture_chunk_ros_message.device_id, 32) &&
         reserve_ros_string(&audio_capture_chunk_ros_message.command_id, 36) &&
         rosidl_runtime_c__uint8__Sequence__init(
             &audio_capture_chunk_ros_message.pcm,
             stackchan::kAudioChunkBytes);
}

bool convert_event_message(
    const stackchan::StackChanEventMsg& source,
    stackchan_msgs__msg__StackChanEvent* destination) {
  if (destination == nullptr) {
    return false;
  }
  destination->stamp.sec = source.stamp.sec;
  destination->stamp.nanosec = source.stamp.nanosec;
  return assign_ros_string(&destination->event_id, source.event_id.data) &&
         assign_ros_string(&destination->device_id, source.device_id.data) &&
         assign_ros_string(&destination->event_name, source.event_name.data) &&
         assign_ros_string(&destination->source, source.source.data) &&
         assign_ros_string(&destination->command_id, source.command_id.data) &&
         assign_ros_string(&destination->payload_json, source.payload_json.data);
}

bool convert_result_message(
    const stackchan::ResultMsg& source,
    stackchan_msgs__msg__Result* destination) {
  if (destination == nullptr) {
    return false;
  }
  destination->ok = source.ok;
  destination->state = source.state;
  destination->recoverable = source.recoverable;
  return assign_ros_string(&destination->error_code, source.error_code.data) &&
         assign_ros_string(&destination->message, source.message.data);
}

bool convert_command_result(
    const stackchan::Result& source,
    stackchan_msgs__msg__Result* destination) {
  if (destination == nullptr) {
    return false;
  }
  destination->ok = source.ok;
  destination->state = static_cast<uint8_t>(source.state);
  destination->recoverable = source.recoverable;
  return assign_ros_string(&destination->error_code, source.error_code) &&
         assign_ros_string(&destination->message, source.message);
}

stackchan::Result result_from_ros(const stackchan_msgs__msg__Result& source) {
  return {
      source.ok,
      static_cast<stackchan::ResultState>(source.state),
      source.error_code.data != nullptr ? source.error_code.data : "",
      source.message.data != nullptr ? source.message.data : "",
      source.recoverable,
  };
}

bool assign_capability_status(
    stackchan_msgs__msg__CapabilityStatus* destination,
    const char* name,
    bool available,
    bool active = false,
    uint8_t queued = 0,
    const char* unavailable_detail_code = "UNSUPPORTED_FEATURE") {
  if (destination == nullptr) {
    return false;
  }
  destination->active = active;
  destination->queued = queued;
  destination->last_update.sec = 0;
  destination->last_update.nanosec = 0;
  return assign_ros_string(&destination->name, name) &&
         assign_ros_string(&destination->state, available ? "available" : "unavailable") &&
         assign_ros_string(
             &destination->detail_code,
             available ? "" : unavailable_detail_code);
}

const char* audio_playback_unavailable_detail_code() {
  if (stackchan_audio_playback_initialized && play_audio_action_init_failed) {
    return "TRANSPORT_INIT_FAILED";
  }
  return "UNSUPPORTED_FEATURE";
}

const char* audio_capture_unavailable_detail_code() {
  if (stackchan_audio_capture_initialized && capture_audio_action_init_failed) {
    return "TRANSPORT_INIT_FAILED";
  }
  return "UNSUPPORTED_FEATURE";
}

const char* camera_snapshot_unavailable_detail_code() {
  if (stackchan_camera_snapshot_initialized && capture_camera_action_init_failed) {
    return "TRANSPORT_INIT_FAILED";
  }
  return "UNSUPPORTED_FEATURE";
}

bool assign_status_capabilities(stackchan_msgs__msg__StackChanStatus* destination) {
  if (destination == nullptr || destination->capabilities.capacity < 6) {
    return false;
  }
  destination->capabilities.size = 6;
  return assign_capability_status(&destination->capabilities.data[0], "face", true) &&
         assign_capability_status(&destination->capabilities.data[1], "motion", servo_adapter_init_result.ok) &&
         assign_capability_status(&destination->capabilities.data[2], "led", stackchan_led_initialized) &&
         assign_capability_status(
             &destination->capabilities.data[3],
             "audio_playback",
             stackchan_audio_playback_transport_initialized,
             audio_playback_guard.active(),
             audio_playback_guard.active() ? 1 : 0,
             audio_playback_unavailable_detail_code()) &&
         assign_capability_status(
             &destination->capabilities.data[4],
             "audio_capture",
             stackchan_audio_capture_transport_initialized,
             audio_capture_session_active,
             audio_capture_session_active ? 1 : 0,
             audio_capture_unavailable_detail_code()) &&
         assign_capability_status(
             &destination->capabilities.data[5],
             "camera_snapshot",
             stackchan_camera_snapshot_initialized &&
                 capture_camera_action_server_initialized,
             false,
             0,
             camera_snapshot_unavailable_detail_code());
}

bool convert_status_message(
    const stackchan::StackChanStatusMsg& source,
    stackchan_msgs__msg__StackChanStatus* destination) {
  if (destination == nullptr) {
    return false;
  }
  destination->connected = source.connected;
  return assign_ros_string(&destination->device_id, source.device_id.data) &&
         assign_ros_string(&destination->state, source.state.data) &&
         assign_ros_string(&destination->face, source.face.data) &&
         assign_ros_string(&destination->motion, source.motion.data) &&
         assign_ros_string(&destination->last_command_id, source.last_command_id.data) &&
         convert_result_message(source.last_error, &destination->last_error) &&
         assign_ros_string(&destination->firmware_version, source.firmware_version.data) &&
         assign_status_capabilities(destination);
}

bool convert_head_pose_message(
    const stackchan::HeadPoseMsg& source,
    stackchan_msgs__msg__HeadPose* destination) {
  if (destination == nullptr) {
    return false;
  }
  destination->stamp.sec = source.stamp.sec;
  destination->stamp.nanosec = source.stamp.nanosec;
  destination->pan_deg = source.pan_deg;
  destination->tilt_deg = source.tilt_deg;
  destination->moving = source.moving;
  return assign_ros_string(&destination->device_id, source.device_id.data) &&
         assign_ros_string(&destination->frame, source.frame.data);
}

bool convert_imu_raw_message(
    const stackchan::ImuRawMsg& source,
    stackchan_msgs__msg__ImuRaw* destination) {
  if (destination == nullptr) {
    return false;
  }
  destination->stamp.sec = source.stamp.sec;
  destination->stamp.nanosec = source.stamp.nanosec;
  destination->accel.x = source.accel_x;
  destination->accel.y = source.accel_y;
  destination->accel.z = source.accel_z;
  destination->gyro.x = source.gyro_x;
  destination->gyro.y = source.gyro_y;
  destination->gyro.z = source.gyro_z;
  destination->mag.x = source.mag_x;
  destination->mag.y = source.mag_y;
  destination->mag.z = source.mag_z;
  destination->temperature = source.temperature;
  return assign_ros_string(&destination->device_id, source.device_id.data);
}

bool assign_uint8_sequence(
    rosidl_runtime_c__uint8__Sequence* destination,
    const stackchan::BoundedSequence<uint8_t, stackchan::kRosTouchIntensityCapacity>& source) {
  if (destination == nullptr ||
      source.size > stackchan::kRosTouchIntensityCapacity) {
    return false;
  }
  if (destination->capacity < source.size) {
    rosidl_runtime_c__uint8__Sequence__fini(destination);
    if (!rosidl_runtime_c__uint8__Sequence__init(destination, source.size)) {
      return false;
    }
  }
  destination->size = source.size;
  for (size_t index = 0; index < source.size; ++index) {
    destination->data[index] = source.data[index];
  }
  return true;
}

bool convert_touch_state_message(
    const stackchan::TouchStateMsg& source,
    stackchan_msgs__msg__TouchState* destination) {
  if (destination == nullptr) {
    return false;
  }
  destination->stamp.sec = source.stamp.sec;
  destination->stamp.nanosec = source.stamp.nanosec;
  destination->zone_mask = source.zone_mask;
  destination->zone_count = source.zone_count;
  return assign_ros_string(&destination->device_id, source.device_id.data) &&
         assign_uint8_sequence(&destination->intensities, source.intensities) &&
         assign_ros_string(&destination->surface, source.surface.data);
}

bool convert_proximity_raw_message(
    const stackchan::ProximityRawMsg& source,
    stackchan_msgs__msg__ProximityRaw* destination) {
  if (destination == nullptr) {
    return false;
  }
  destination->stamp.sec = source.stamp.sec;
  destination->stamp.nanosec = source.stamp.nanosec;
  destination->sensor_index = source.sensor_index;
  destination->distance_m = source.distance_m;
  destination->signal = source.signal;
  destination->raw = source.raw;
  destination->saturated = source.saturated;
  return assign_ros_string(&destination->device_id, source.device_id.data);
}

bool convert_light_raw_message(
    const stackchan::LightRawMsg& source,
    stackchan_msgs__msg__LightRaw* destination) {
  if (destination == nullptr) {
    return false;
  }
  destination->stamp.sec = source.stamp.sec;
  destination->stamp.nanosec = source.stamp.nanosec;
  destination->sensor_index = source.sensor_index;
  destination->illuminance_lux = source.illuminance_lux;
  destination->raw = source.raw;
  destination->saturated = source.saturated;
  return assign_ros_string(&destination->device_id, source.device_id.data);
}

bool convert_power_status_message(
    const stackchan::PowerStatusMsg& source,
    stackchan_msgs__msg__PowerStatus* destination) {
  if (destination == nullptr) {
    return false;
  }
  destination->stamp.sec = source.stamp.sec;
  destination->stamp.nanosec = source.stamp.nanosec;
  destination->voltage_v = source.voltage_v;
  destination->current_ma = source.current_ma;
  destination->power_mw = source.power_mw;
  destination->percentage = source.percentage;
  destination->power_source = source.power_source;
  destination->charging = source.charging;
  destination->powered = source.powered;
  destination->low_battery = source.low_battery;
  destination->brownout_risk = source.brownout_risk;
  return assign_ros_string(&destination->device_id, source.device_id.data) &&
         assign_ros_string(&destination->fault_code, source.fault_code.data);
}

stackchan::Priority priority_from_ros(uint8_t priority) {
  switch (priority) {
    case 0:
      return stackchan::Priority::Low;
    case 2:
      return stackchan::Priority::High;
    case 3:
      return stackchan::Priority::Safety;
    case 1:
    default:
      return stackchan::Priority::Normal;
  }
}

bool request_matches_device_id(const rosidl_runtime_c__String& device_id) {
  return device_id.data == nullptr ||
         device_id.size == 0 ||
         strcmp(device_id.data, STACKCHAN_DEVICE_ID) == 0;
}

void build_face_set_service_name() {
  snprintf(
      face_set_service_name,
      sizeof(face_set_service_name),
      "/stackchan/%s/device/face/set",
      STACKCHAN_DEVICE_ID);
  face_set_service_name[sizeof(face_set_service_name) - 1] = '\0';
}

void build_head_pose_set_service_name() {
  snprintf(
      head_pose_set_service_name,
      sizeof(head_pose_set_service_name),
      "/stackchan/%s/device/motion/pose/set",
      STACKCHAN_DEVICE_ID);
  head_pose_set_service_name[sizeof(head_pose_set_service_name) - 1] = '\0';
}

void build_led_set_service_name() {
  snprintf(
      led_set_service_name,
      sizeof(led_set_service_name),
      "/stackchan/%s/device/led/set",
      STACKCHAN_DEVICE_ID);
  led_set_service_name[sizeof(led_set_service_name) - 1] = '\0';
}

void build_motion_set_service_name() {
  snprintf(
      motion_set_service_name,
      sizeof(motion_set_service_name),
      "/stackchan/%s/device/motion/run",
      STACKCHAN_DEVICE_ID);
  motion_set_service_name[sizeof(motion_set_service_name) - 1] = '\0';
}

void build_audio_chunk_topic_name() {
  snprintf(
      audio_chunk_topic_name,
      sizeof(audio_chunk_topic_name),
      "/stackchan/%s/device/audio/chunks",
      STACKCHAN_DEVICE_ID);
  audio_chunk_topic_name[sizeof(audio_chunk_topic_name) - 1] = '\0';
}

void build_audio_playback_chunk_topic_name() {
  snprintf(
      audio_playback_chunk_topic_name,
      sizeof(audio_playback_chunk_topic_name),
      "/stackchan/%s/device/audio/playback/chunks",
      STACKCHAN_DEVICE_ID);
  audio_playback_chunk_topic_name[sizeof(audio_playback_chunk_topic_name) - 1] = '\0';
}

void build_audio_playback_ack_topic_name() {
  snprintf(
      audio_playback_ack_topic_name,
      sizeof(audio_playback_ack_topic_name),
      "/stackchan/%s/device/audio/playback/acks",
      STACKCHAN_DEVICE_ID);
  audio_playback_ack_topic_name[sizeof(audio_playback_ack_topic_name) - 1] = '\0';
}

void build_camera_frame_chunk_topic_name() {
  snprintf(
      camera_frame_chunk_topic_name,
      sizeof(camera_frame_chunk_topic_name),
      "/stackchan/%s/device/camera/chunks",
      STACKCHAN_DEVICE_ID);
  camera_frame_chunk_topic_name[sizeof(camera_frame_chunk_topic_name) - 1] = '\0';
}

void build_audio_playback_chunk_service_name() {
  snprintf(
      audio_playback_chunk_service_name,
      sizeof(audio_playback_chunk_service_name),
      "/stackchan/%s/audio/playback/next_chunk",
      STACKCHAN_DEVICE_ID);
  audio_playback_chunk_service_name[sizeof(audio_playback_chunk_service_name) - 1] = '\0';
}

void build_audio_playback_load_service_name() {
  snprintf(
      audio_playback_load_service_name,
      sizeof(audio_playback_load_service_name),
      "/stackchan/%s/device/audio/playback/load",
      STACKCHAN_DEVICE_ID);
  audio_playback_load_service_name[sizeof(audio_playback_load_service_name) - 1] = '\0';
}

void build_play_audio_action_name() {
  snprintf(
      play_audio_action_name,
      sizeof(play_audio_action_name),
      "/stackchan/%s/device/audio/play",
      STACKCHAN_DEVICE_ID);
  play_audio_action_name[sizeof(play_audio_action_name) - 1] = '\0';
}

void build_capture_audio_action_name() {
  snprintf(
      capture_audio_action_name,
      sizeof(capture_audio_action_name),
      "/stackchan/%s/device/audio/capture",
      STACKCHAN_DEVICE_ID);
  capture_audio_action_name[sizeof(capture_audio_action_name) - 1] = '\0';
}

void build_capture_camera_action_name() {
  snprintf(
      capture_camera_action_name,
      sizeof(capture_camera_action_name),
      "/stackchan/%s/device/camera/capture",
      STACKCHAN_DEVICE_ID);
  capture_camera_action_name[sizeof(capture_camera_action_name) - 1] = '\0';
}

bool try_initialize_capture_audio_action_server(const char* step) {
  build_capture_audio_action_name();
  rcl_action_server_options_t options = stackchan_action_server_options();
  if (!rcl_ok(rcl_action_server_init(
                  &capture_audio_action_server,
                  &microros_node,
                  &microros_support.clock,
                  ROSIDL_GET_ACTION_TYPE_SUPPORT(stackchan_msgs, CaptureAudio),
                  capture_audio_action_name,
                  &options),
              step)) {
    capture_audio_action_server_initialized = false;
    capture_audio_action_init_failed = true;
    return false;
  }
  capture_audio_action_server_initialized = true;
  capture_audio_action_init_failed = false;
  return true;
}

bool try_initialize_capture_camera_action_server(const char* step) {
  build_capture_camera_action_name();
  rcl_action_server_options_t options = stackchan_action_server_options();
  if (!rcl_ok(rcl_action_server_init(
                  &capture_camera_action_server,
                  &microros_node,
                  &microros_support.clock,
                  ROSIDL_GET_ACTION_TYPE_SUPPORT(stackchan_msgs, CaptureCamera),
                  capture_camera_action_name,
                  &options),
              step)) {
    capture_camera_action_server_initialized = false;
    capture_camera_action_init_failed = true;
    return false;
  }
  capture_camera_action_server_initialized = true;
  capture_camera_action_init_failed = false;
  return true;
}

bool try_initialize_play_audio_action_server(const char* step) {
  build_play_audio_action_name();
  rcl_action_server_options_t options = stackchan_action_server_options();
  if (!rcl_ok(rcl_action_server_init(
                  &play_audio_action_server,
                  &microros_node,
                  &microros_support.clock,
                  ROSIDL_GET_ACTION_TYPE_SUPPORT(stackchan_msgs, PlayAudio),
                  play_audio_action_name,
                  &options),
              step)) {
    play_audio_action_server_initialized = false;
    play_audio_action_init_failed = true;
    return false;
  }
  play_audio_action_server_initialized = true;
  play_audio_action_init_failed = false;
  return true;
}

void handle_face_set_service(const void* request, void* response);
void handle_head_pose_set_service(const void* request, void* response);
void handle_led_set_service(const void* request, void* response);
void handle_motion_set_service(const void* request, void* response);
void handle_audio_chunk_subscription(const void* message);
void handle_audio_playback_chunk_response(const void* response);
void handle_audio_playback_load_service(const void* request, void* response);
bool is_loaded_audio_topic_chunk(const stackchan_msgs__msg__AudioChunk* chunk);
void handle_loaded_audio_topic_chunk(const stackchan_msgs__msg__AudioChunk* chunk);
void accept_play_audio_pcm_chunk(
    const char* chunk_command_id,
    uint32_t sequence,
    uint8_t format,
    uint32_t sample_rate,
    uint8_t channels,
    const uint8_t* pcm_data,
    size_t pcm_size);
void poll_capture_audio_action_server();
void poll_capture_camera_action_server();
void poll_play_audio_action_server();
void publish_status_heartbeat();

bool initialize_microros_entities() {
  microros_allocator = rcl_get_default_allocator();
  memset(&microros_support, 0, sizeof(microros_support));
  microros_node = rcl_get_zero_initialized_node();
  event_ros_publisher = rcl_get_zero_initialized_publisher();
  imu_raw_ros_publisher = rcl_get_zero_initialized_publisher();
  light_raw_ros_publisher = rcl_get_zero_initialized_publisher();
  motion_pose_ros_publisher = rcl_get_zero_initialized_publisher();
  power_status_ros_publisher = rcl_get_zero_initialized_publisher();
  proximity_raw_ros_publisher = rcl_get_zero_initialized_publisher();
  status_ros_publisher = rcl_get_zero_initialized_publisher();
  touch_state_ros_publisher = rcl_get_zero_initialized_publisher();
  audio_chunk_ros_publisher = rcl_get_zero_initialized_publisher();
  audio_playback_ack_ros_publisher = rcl_get_zero_initialized_publisher();
  camera_frame_chunk_ros_publisher = rcl_get_zero_initialized_publisher();
  audio_chunk_subscription = rcl_get_zero_initialized_subscription();
  audio_playback_chunk_client = rcl_get_zero_initialized_client();
  audio_playback_load_service = rcl_get_zero_initialized_service();
  capture_audio_action_server = rcl_action_get_zero_initialized_server();
  capture_camera_action_server = rcl_action_get_zero_initialized_server();
  play_audio_action_server = rcl_action_get_zero_initialized_server();
  capture_audio_action_init_failed = false;
  capture_camera_action_init_failed = false;
  play_audio_action_init_failed = false;
  audio_playback_load_service_initialized = false;
  play_audio_chunk_client_initialized = false;
  play_audio_chunk_request_pending = false;
  face_set_service = rcl_get_zero_initialized_service();
  head_pose_set_service = rcl_get_zero_initialized_service();
  led_set_service = rcl_get_zero_initialized_service();
  motion_set_service = rcl_get_zero_initialized_service();
  microros_executor = rclc_executor_get_zero_initialized_executor();
  memset(&event_ros_message, 0, sizeof(event_ros_message));
  memset(&imu_raw_ros_message, 0, sizeof(imu_raw_ros_message));
  memset(&light_raw_ros_message, 0, sizeof(light_raw_ros_message));
  memset(&motion_pose_ros_message, 0, sizeof(motion_pose_ros_message));
  memset(&power_status_ros_message, 0, sizeof(power_status_ros_message));
  memset(&proximity_raw_ros_message, 0, sizeof(proximity_raw_ros_message));
  memset(&status_ros_message, 0, sizeof(status_ros_message));
  memset(&touch_state_ros_message, 0, sizeof(touch_state_ros_message));
  memset(&audio_chunk_ros_message, 0, sizeof(audio_chunk_ros_message));
  memset(&audio_capture_chunk_ros_message, 0, sizeof(audio_capture_chunk_ros_message));
  memset(&audio_playback_ack_ros_message, 0, sizeof(audio_playback_ack_ros_message));
  memset(&camera_frame_chunk_ros_message, 0, sizeof(camera_frame_chunk_ros_message));
  memset(&capture_audio_goal_request, 0, sizeof(capture_audio_goal_request));
  memset(&capture_audio_goal_response, 0, sizeof(capture_audio_goal_response));
  memset(&capture_audio_result_request, 0, sizeof(capture_audio_result_request));
  memset(&capture_audio_result_response, 0, sizeof(capture_audio_result_response));
  memset(&capture_audio_feedback_message, 0, sizeof(capture_audio_feedback_message));
  memset(&capture_camera_goal_request, 0, sizeof(capture_camera_goal_request));
  memset(&capture_camera_goal_response, 0, sizeof(capture_camera_goal_response));
  memset(&capture_camera_result_request, 0, sizeof(capture_camera_result_request));
  memset(&capture_camera_result_response, 0, sizeof(capture_camera_result_response));
  memset(&capture_camera_feedback_message, 0, sizeof(capture_camera_feedback_message));
  memset(&play_audio_goal_request, 0, sizeof(play_audio_goal_request));
  memset(&play_audio_goal_response, 0, sizeof(play_audio_goal_response));
  memset(&play_audio_result_request, 0, sizeof(play_audio_result_request));
  memset(&play_audio_result_response, 0, sizeof(play_audio_result_response));
  memset(&audio_playback_chunk_request, 0, sizeof(audio_playback_chunk_request));
  memset(&audio_playback_chunk_response, 0, sizeof(audio_playback_chunk_response));
  memset(&audio_playback_load_request, 0, sizeof(audio_playback_load_request));
  memset(&audio_playback_load_response, 0, sizeof(audio_playback_load_response));
  memset(&face_set_request, 0, sizeof(face_set_request));
  memset(&face_set_response, 0, sizeof(face_set_response));
  memset(&head_pose_set_request, 0, sizeof(head_pose_set_request));
  memset(&head_pose_set_response, 0, sizeof(head_pose_set_response));
  memset(&led_set_request, 0, sizeof(led_set_request));
  memset(&led_set_response, 0, sizeof(led_set_response));
  memset(&motion_set_request, 0, sizeof(motion_set_request));
  memset(&motion_set_response, 0, sizeof(motion_set_response));

  if (!rcl_ok(rclc_support_init(&microros_support, 0, nullptr, &microros_allocator),
              "support_init")) {
    return false;
  }
  build_node_namespace();
  if (!rcl_ok(rclc_node_init_default(
                  &microros_node,
                  "stackchan_firmware",
                  microros_node_namespace,
                  &microros_support),
              "node_init")) {
    return false;
  }
  rmw_qos_profile_t event_qos =
      qos_profile_for(stackchan::DevicePublisherTopic::Events);
  // Firmware-owned events publish under /stackchan/<device_id>/device/events.
  if (!rcl_ok(rclc_publisher_init(
                  &event_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, StackChanEvent),
                  device_publishers.topic_name(stackchan::DevicePublisherTopic::Events),
                  &event_qos),
               "event_publisher_init")) {
    return false;
  }
  rmw_qos_profile_t status_qos =
      qos_profile_for(stackchan::DevicePublisherTopic::Status);
  // Firmware-owned status heartbeat publishes under /stackchan/<device_id>/device/status.
  if (!rcl_ok(rclc_publisher_init(
                  &status_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, StackChanStatus),
                  device_publishers.topic_name(stackchan::DevicePublisherTopic::Status),
                  &status_qos),
              "status_publisher_init")) {
    return false;
  }
#if STACKCHAN_MICROROS_STATUS_ONLY_BRINGUP
  if (!stackchan_msgs__msg__StackChanStatus__init(&status_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=status_message_init result=false");
    return false;
  }
  stackchan_msgs__msg__CapabilityStatus__Sequence__fini(&status_ros_message.capabilities);
  if (!stackchan_msgs__msg__CapabilityStatus__Sequence__init(&status_ros_message.capabilities, 6)) {
    stackchan_diag_println("stackchan micro_ros_step=status_capabilities_init result=false");
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
  microros_entities_initialized = true;
  stackchan_audio_playback_transport_initialized = false;
  stackchan_audio_capture_transport_initialized = false;
  return true;
#endif
#if STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP
  build_face_set_service_name();
  if (!rcl_ok(rclc_service_init_default(
                  &face_set_service,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, SetFace),
                  face_set_service_name),
              "face_set_service_init")) {
    return false;
  }
  build_head_pose_set_service_name();
  if (!rcl_ok(rclc_service_init_default(
                  &head_pose_set_service,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, SetHeadPose),
                  head_pose_set_service_name),
              "head_pose_set_service_init")) {
    return false;
  }
  build_led_set_service_name();
  if (!rcl_ok(rclc_service_init_default(
                  &led_set_service,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, SetLed),
                  led_set_service_name),
              "led_set_service_init")) {
    return false;
  }
  build_motion_set_service_name();
  if (!rcl_ok(rclc_service_init_default(
                  &motion_set_service,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, SetMotion),
                  motion_set_service_name),
              "motion_set_service_init")) {
    return false;
  }
#if STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP
  {
    rmw_qos_profile_t motion_pose_qos =
        qos_profile_for(stackchan::DevicePublisherTopic::MotionPose);
    if (!rcl_ok(rclc_publisher_init(
                    &motion_pose_ros_publisher,
                    &microros_node,
                    ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, HeadPose),
                    device_publishers.topic_name(stackchan::DevicePublisherTopic::MotionPose),
                    &motion_pose_qos),
                "motion_pose_publisher_init")) {
      return false;
    }
    rmw_qos_profile_t touch_qos =
        qos_profile_for(stackchan::DevicePublisherTopic::TouchState);
    if (!rcl_ok(rclc_publisher_init(
                    &touch_state_ros_publisher,
                    &microros_node,
                    ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, TouchState),
                    device_publishers.topic_name(stackchan::DevicePublisherTopic::TouchState),
                    &touch_qos),
                "touch_state_publisher_init")) {
      return false;
    }
    rmw_qos_profile_t imu_raw_qos =
        qos_profile_for(stackchan::DevicePublisherTopic::ImuRaw);
    if (!rcl_ok(rclc_publisher_init(
                    &imu_raw_ros_publisher,
                    &microros_node,
                    ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, ImuRaw),
                    device_publishers.topic_name(stackchan::DevicePublisherTopic::ImuRaw),
                    &imu_raw_qos),
                "imu_raw_publisher_init")) {
      return false;
    }
    rmw_qos_profile_t proximity_qos =
        qos_profile_for(stackchan::DevicePublisherTopic::ProximityRaw);
    if (!rcl_ok(rclc_publisher_init(
                    &proximity_raw_ros_publisher,
                    &microros_node,
                    ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, ProximityRaw),
                    device_publishers.topic_name(stackchan::DevicePublisherTopic::ProximityRaw),
                    &proximity_qos),
                "proximity_raw_publisher_init")) {
      return false;
    }
    rmw_qos_profile_t light_qos =
        qos_profile_for(stackchan::DevicePublisherTopic::LightRaw);
    if (!rcl_ok(rclc_publisher_init(
                    &light_raw_ros_publisher,
                    &microros_node,
                    ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, LightRaw),
                    device_publishers.topic_name(stackchan::DevicePublisherTopic::LightRaw),
                    &light_qos),
                "light_raw_publisher_init")) {
      return false;
    }
    rmw_qos_profile_t power_qos =
        qos_profile_for(stackchan::DevicePublisherTopic::PowerStatus);
    if (!rcl_ok(rclc_publisher_init(
                    &power_status_ros_publisher,
                    &microros_node,
                    ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, PowerStatus),
                    device_publishers.topic_name(stackchan::DevicePublisherTopic::PowerStatus),
                    &power_qos),
                "power_status_publisher_init")) {
      return false;
    }
  }
#endif
#if STACKCHAN_MICROROS_CORE_MEDIA_BRINGUP
  build_audio_chunk_topic_name();
  build_audio_playback_chunk_topic_name();
  build_audio_playback_ack_topic_name();
  build_camera_frame_chunk_topic_name();
  build_audio_playback_chunk_service_name();
  build_audio_playback_load_service_name();
  rmw_qos_profile_t core_audio_chunk_qos = rmw_qos_profile_default;
  core_audio_chunk_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  core_audio_chunk_qos.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  core_audio_chunk_qos.depth = 8;
  rmw_qos_profile_t core_audio_playback_chunk_qos = rmw_qos_profile_default;
  core_audio_playback_chunk_qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  core_audio_playback_chunk_qos.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  core_audio_playback_chunk_qos.depth = kAudioPlaybackChunkSubscriptionDepth;
  rmw_qos_profile_t core_audio_playback_ack_qos = rmw_qos_profile_default;
  core_audio_playback_ack_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  core_audio_playback_ack_qos.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  core_audio_playback_ack_qos.depth = 8;
  rmw_qos_profile_t core_camera_frame_chunk_qos = rmw_qos_profile_default;
  core_camera_frame_chunk_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  core_camera_frame_chunk_qos.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  core_camera_frame_chunk_qos.depth = 16;
#if STACKCHAN_MICROROS_CORE_AUDIO_TOPIC_BRINGUP
  if (!rcl_ok(rclc_publisher_init(
                  &audio_chunk_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, AudioChunk),
                  audio_chunk_topic_name,
                  &core_audio_chunk_qos),
              "audio_chunk_publisher_init")) {
    return false;
  }
#endif
#if STACKCHAN_MICROROS_CORE_AUDIO_SUBSCRIPTION_BRINGUP
  if (!rcl_ok(rclc_subscription_init(
                  &audio_chunk_subscription,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, AudioChunk),
                  audio_playback_chunk_topic_name,
                  &core_audio_playback_chunk_qos),
              "audio_chunk_subscription_init")) {
    return false;
  }
#endif
#if STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP
  (void)try_initialize_capture_audio_action_server(
      "capture_audio_action_server_init");
#endif
#if STACKCHAN_MICROROS_CORE_CAPTURE_CAMERA_BRINGUP
  if (!rcl_ok(rclc_publisher_init(
                  &camera_frame_chunk_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, CameraFrameChunk),
                  camera_frame_chunk_topic_name,
                  &core_camera_frame_chunk_qos),
              "camera_frame_chunk_publisher_init")) {
    return false;
  }
  (void)try_initialize_capture_camera_action_server(
      "capture_camera_action_server_init");
#endif
#if STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP
  if (!rcl_ok(rclc_publisher_init(
                  &audio_playback_ack_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, AudioPlaybackAck),
                  audio_playback_ack_topic_name,
                  &core_audio_playback_ack_qos),
              "audio_playback_ack_publisher_init")) {
    return false;
  }
  if (!rcl_ok(rclc_client_init_default(
                  &audio_playback_chunk_client,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, NextAudioChunk),
                  audio_playback_chunk_service_name),
              "audio_playback_chunk_client_init")) {
    return false;
  }
  play_audio_chunk_client_initialized = true;
  if (!rcl_ok(rclc_service_init_default(
                  &audio_playback_load_service,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, LoadAudioChunk),
                  audio_playback_load_service_name),
              "audio_playback_load_service_init")) {
    return false;
  }
  audio_playback_load_service_initialized = true;
  (void)try_initialize_play_audio_action_server(
      "play_audio_action_server_init");
#endif
#endif
  if (!stackchan_msgs__msg__StackChanStatus__init(&status_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=status_message_init result=false");
    return false;
  }
  stackchan_msgs__msg__CapabilityStatus__Sequence__fini(&status_ros_message.capabilities);
  if (!stackchan_msgs__msg__CapabilityStatus__Sequence__init(&status_ros_message.capabilities, 6)) {
    stackchan_diag_println("stackchan micro_ros_step=status_capabilities_init result=false");
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
#if STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP
  if (!stackchan_msgs__msg__HeadPose__init(&motion_pose_ros_message) ||
      !stackchan_msgs__msg__TouchState__init(&touch_state_ros_message) ||
      !stackchan_msgs__msg__ImuRaw__init(&imu_raw_ros_message) ||
      !stackchan_msgs__msg__ProximityRaw__init(&proximity_raw_ros_message) ||
      !stackchan_msgs__msg__LightRaw__init(&light_raw_ros_message) ||
      !stackchan_msgs__msg__PowerStatus__init(&power_status_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=raw_telemetry_messages_init result=false");
    stackchan_msgs__msg__PowerStatus__fini(&power_status_ros_message);
    stackchan_msgs__msg__LightRaw__fini(&light_raw_ros_message);
    stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
#endif
#if STACKCHAN_MICROROS_CORE_AUDIO_SUBSCRIPTION_BRINGUP
  if (!stackchan_msgs__msg__AudioChunk__init(&audio_chunk_ros_message) ||
      !reserve_audio_chunk_message_storage()) {
    stackchan_diag_println("stackchan micro_ros_step=audio_chunk_message_init result=false");
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
#endif
#if STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP
  if (!stackchan_msgs__msg__AudioChunk__init(&audio_capture_chunk_ros_message) ||
      !reserve_audio_capture_chunk_message_storage()) {
    stackchan_diag_println("stackchan micro_ros_step=audio_capture_chunk_message_init result=false");
    stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
  if (!stackchan_msgs__action__CaptureAudio_SendGoal_Request__init(&capture_audio_goal_request) ||
      !stackchan_msgs__action__CaptureAudio_SendGoal_Response__init(&capture_audio_goal_response) ||
      !stackchan_msgs__action__CaptureAudio_GetResult_Request__init(&capture_audio_result_request) ||
      !stackchan_msgs__action__CaptureAudio_GetResult_Response__init(&capture_audio_result_response) ||
      !stackchan_msgs__action__CaptureAudio_FeedbackMessage__init(&capture_audio_feedback_message) ||
      !reserve_capture_audio_goal_strings()) {
    stackchan_diag_println("stackchan micro_ros_step=capture_audio_action_messages_init result=false");
    stackchan_msgs__action__CaptureAudio_FeedbackMessage__fini(&capture_audio_feedback_message);
    stackchan_msgs__action__CaptureAudio_GetResult_Response__fini(&capture_audio_result_response);
    stackchan_msgs__action__CaptureAudio_GetResult_Request__fini(&capture_audio_result_request);
    stackchan_msgs__action__CaptureAudio_SendGoal_Response__fini(&capture_audio_goal_response);
    stackchan_msgs__action__CaptureAudio_SendGoal_Request__fini(&capture_audio_goal_request);
    stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
#endif
#if STACKCHAN_MICROROS_CORE_CAPTURE_CAMERA_BRINGUP
  if (!stackchan_msgs__msg__CameraFrameChunk__init(&camera_frame_chunk_ros_message) ||
      !reserve_camera_frame_chunk_message_storage()) {
    stackchan_diag_println("stackchan micro_ros_step=camera_frame_chunk_message_init result=false");
    stackchan_msgs__msg__CameraFrameChunk__fini(&camera_frame_chunk_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
  if (!stackchan_msgs__action__CaptureCamera_SendGoal_Request__init(&capture_camera_goal_request) ||
      !stackchan_msgs__action__CaptureCamera_SendGoal_Response__init(&capture_camera_goal_response) ||
      !stackchan_msgs__action__CaptureCamera_GetResult_Request__init(&capture_camera_result_request) ||
      !stackchan_msgs__action__CaptureCamera_GetResult_Response__init(&capture_camera_result_response) ||
      !stackchan_msgs__action__CaptureCamera_FeedbackMessage__init(&capture_camera_feedback_message) ||
      !reserve_capture_camera_goal_strings() ||
      !reserve_capture_camera_result_storage()) {
    stackchan_diag_println("stackchan micro_ros_step=capture_camera_action_messages_init result=false");
    stackchan_msgs__action__CaptureCamera_FeedbackMessage__fini(&capture_camera_feedback_message);
    stackchan_msgs__action__CaptureCamera_GetResult_Response__fini(&capture_camera_result_response);
    stackchan_msgs__action__CaptureCamera_GetResult_Request__fini(&capture_camera_result_request);
    stackchan_msgs__action__CaptureCamera_SendGoal_Response__fini(&capture_camera_goal_response);
    stackchan_msgs__action__CaptureCamera_SendGoal_Request__fini(&capture_camera_goal_request);
    stackchan_msgs__msg__CameraFrameChunk__fini(&camera_frame_chunk_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
#endif
#if STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP
  if (!stackchan_msgs__action__PlayAudio_SendGoal_Request__init(&play_audio_goal_request) ||
      !reserve_play_audio_goal_strings() ||
      !stackchan_msgs__action__PlayAudio_SendGoal_Response__init(&play_audio_goal_response) ||
      !stackchan_msgs__action__PlayAudio_GetResult_Request__init(&play_audio_result_request) ||
      !stackchan_msgs__action__PlayAudio_GetResult_Response__init(&play_audio_result_response) ||
      !stackchan_msgs__srv__NextAudioChunk_Request__init(&audio_playback_chunk_request) ||
      !stackchan_msgs__srv__NextAudioChunk_Response__init(&audio_playback_chunk_response) ||
      !reserve_audio_playback_chunk_service_storage() ||
      !stackchan_msgs__msg__AudioPlaybackAck__init(&audio_playback_ack_ros_message) ||
      !reserve_audio_playback_ack_message_storage() ||
      !stackchan_msgs__srv__LoadAudioChunk_Request__init(&audio_playback_load_request) ||
      !stackchan_msgs__srv__LoadAudioChunk_Response__init(&audio_playback_load_response) ||
      !reserve_audio_playback_load_service_storage()) {
    stackchan_diag_println("stackchan micro_ros_step=play_audio_action_messages_init result=false");
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
#endif
  if (!stackchan_msgs__srv__SetFace_Request__init(&face_set_request) ||
      !reserve_face_set_request_strings() ||
      !stackchan_msgs__srv__SetFace_Response__init(&face_set_response)) {
    stackchan_diag_println("stackchan micro_ros_step=face_set_messages_init result=false");
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetHeadPose_Request__init(&head_pose_set_request) ||
      !reserve_head_pose_set_request_strings() ||
      !stackchan_msgs__srv__SetHeadPose_Response__init(&head_pose_set_response)) {
    stackchan_diag_println("stackchan micro_ros_step=head_pose_set_messages_init result=false");
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetLed_Request__init(&led_set_request) ||
      !reserve_led_set_request_strings() ||
      !stackchan_msgs__srv__SetLed_Response__init(&led_set_response)) {
    stackchan_diag_println("stackchan micro_ros_step=led_set_messages_init result=false");
    stackchan_msgs__srv__SetLed_Response__fini(&led_set_response);
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetMotion_Request__init(&motion_set_request) ||
      !reserve_motion_set_request_strings() ||
      !stackchan_msgs__srv__SetMotion_Response__init(&motion_set_response)) {
    stackchan_diag_println("stackchan micro_ros_step=motion_set_messages_init result=false");
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetLed_Response__fini(&led_set_response);
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
  size_t core_executor_handles = 4;
#if STACKCHAN_MICROROS_CORE_AUDIO_SUBSCRIPTION_BRINGUP
  ++core_executor_handles;
#endif
#if STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP
  core_executor_handles += 2;
#endif
  if (!rcl_ok(rclc_executor_init(
                  &microros_executor,
                  &microros_support.context,
                  core_executor_handles,
                  &microros_allocator),
              "executor_init")) {
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetLed_Response__fini(&led_set_response);
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
  microros_executor_initialized = true;
  if (!rcl_ok(rclc_executor_add_service(
                  &microros_executor,
                  &face_set_service,
                  &face_set_request,
                  &face_set_response,
                  handle_face_set_service),
              "executor_add_face_set_service") ||
      !rcl_ok(rclc_executor_add_service(
                  &microros_executor,
                  &head_pose_set_service,
                  &head_pose_set_request,
                  &head_pose_set_response,
                  handle_head_pose_set_service),
              "executor_add_head_pose_set_service") ||
      !rcl_ok(rclc_executor_add_service(
                  &microros_executor,
                  &led_set_service,
                  &led_set_request,
                  &led_set_response,
                  handle_led_set_service),
              "executor_add_led_set_service") ||
      !rcl_ok(rclc_executor_add_service(
                  &microros_executor,
                  &motion_set_service,
                  &motion_set_request,
                  &motion_set_response,
                  handle_motion_set_service),
              "executor_add_motion_set_service")) {
    rclc_executor_fini(&microros_executor);
    microros_executor_initialized = false;
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetLed_Response__fini(&led_set_response);
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
#if STACKCHAN_MICROROS_CORE_AUDIO_SUBSCRIPTION_BRINGUP
  if (!rcl_ok(rclc_executor_add_subscription(
                  &microros_executor,
                  &audio_chunk_subscription,
                  &audio_chunk_ros_message,
                  handle_audio_chunk_subscription,
                  ON_NEW_DATA),
              "executor_add_audio_chunk_subscription")) {
    rclc_executor_fini(&microros_executor);
    microros_executor_initialized = false;
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetLed_Response__fini(&led_set_response);
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
#endif
#if STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP
  if (!rcl_ok(rclc_executor_add_client(
                  &microros_executor,
                  &audio_playback_chunk_client,
                  &audio_playback_chunk_response,
                  handle_audio_playback_chunk_response),
              "executor_add_audio_playback_chunk_client")) {
    rclc_executor_fini(&microros_executor);
    microros_executor_initialized = false;
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetLed_Response__fini(&led_set_response);
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
  if (!rcl_ok(rclc_executor_add_service(
                  &microros_executor,
                  &audio_playback_load_service,
                  &audio_playback_load_request,
                  &audio_playback_load_response,
                  handle_audio_playback_load_service),
              "executor_add_audio_playback_load_service")) {
    rclc_executor_fini(&microros_executor);
    microros_executor_initialized = false;
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetLed_Response__fini(&led_set_response);
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
#endif
  microros_entities_initialized = true;
  stackchan_audio_playback_transport_initialized =
      STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP &&
      play_audio_action_server_initialized &&
      play_audio_chunk_client_initialized &&
      stackchan_audio_playback_initialized;
  stackchan_audio_capture_transport_initialized =
      STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP &&
      capture_audio_action_server_initialized &&
      stackchan_audio_capture_initialized;
  return true;
#endif
  rmw_qos_profile_t motion_pose_qos =
      qos_profile_for(stackchan::DevicePublisherTopic::MotionPose);
  if (!rcl_ok(rclc_publisher_init(
                  &motion_pose_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, HeadPose),
                  device_publishers.topic_name(stackchan::DevicePublisherTopic::MotionPose),
                  &motion_pose_qos),
              "motion_pose_publisher_init")) {
    return false;
  }
  rmw_qos_profile_t touch_qos =
      qos_profile_for(stackchan::DevicePublisherTopic::TouchState);
  if (!rcl_ok(rclc_publisher_init(
                  &touch_state_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, TouchState),
                  device_publishers.topic_name(stackchan::DevicePublisherTopic::TouchState),
                  &touch_qos),
              "touch_state_publisher_init")) {
    return false;
  }
  rmw_qos_profile_t imu_raw_qos =
      qos_profile_for(stackchan::DevicePublisherTopic::ImuRaw);
  if (!rcl_ok(rclc_publisher_init(
                  &imu_raw_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, ImuRaw),
                  device_publishers.topic_name(stackchan::DevicePublisherTopic::ImuRaw),
                  &imu_raw_qos),
              "imu_raw_publisher_init")) {
    return false;
  }
  rmw_qos_profile_t proximity_qos =
      qos_profile_for(stackchan::DevicePublisherTopic::ProximityRaw);
  if (!rcl_ok(rclc_publisher_init(
                  &proximity_raw_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, ProximityRaw),
                  device_publishers.topic_name(stackchan::DevicePublisherTopic::ProximityRaw),
                  &proximity_qos),
              "proximity_raw_publisher_init")) {
    return false;
  }
  rmw_qos_profile_t light_qos =
      qos_profile_for(stackchan::DevicePublisherTopic::LightRaw);
  if (!rcl_ok(rclc_publisher_init(
                  &light_raw_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, LightRaw),
                  device_publishers.topic_name(stackchan::DevicePublisherTopic::LightRaw),
                  &light_qos),
              "light_raw_publisher_init")) {
    return false;
  }
  rmw_qos_profile_t power_qos =
      qos_profile_for(stackchan::DevicePublisherTopic::PowerStatus);
  if (!rcl_ok(rclc_publisher_init(
                  &power_status_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, PowerStatus),
                  device_publishers.topic_name(stackchan::DevicePublisherTopic::PowerStatus),
                  &power_qos),
              "power_status_publisher_init")) {
    return false;
  }
  build_audio_chunk_topic_name();
  build_audio_playback_chunk_topic_name();
  build_audio_playback_ack_topic_name();
  build_camera_frame_chunk_topic_name();
  build_audio_playback_chunk_service_name();
  build_audio_playback_load_service_name();
  rmw_qos_profile_t audio_chunk_qos = rmw_qos_profile_default;
  audio_chunk_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  audio_chunk_qos.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  audio_chunk_qos.depth = 8;
  rmw_qos_profile_t audio_playback_chunk_qos = rmw_qos_profile_default;
  audio_playback_chunk_qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  audio_playback_chunk_qos.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  audio_playback_chunk_qos.depth = kAudioPlaybackChunkSubscriptionDepth;
  rmw_qos_profile_t audio_playback_ack_qos = rmw_qos_profile_default;
  audio_playback_ack_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  audio_playback_ack_qos.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  audio_playback_ack_qos.depth = 8;
  rmw_qos_profile_t camera_frame_chunk_qos = rmw_qos_profile_default;
  camera_frame_chunk_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  camera_frame_chunk_qos.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  camera_frame_chunk_qos.depth = 16;
  if (!rcl_ok(rclc_publisher_init(
                  &audio_chunk_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, AudioChunk),
                  audio_chunk_topic_name,
                  &audio_chunk_qos),
              "audio_chunk_publisher_init")) {
    return false;
  }
  if (!rcl_ok(rclc_subscription_init(
                  &audio_chunk_subscription,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, AudioChunk),
                  audio_playback_chunk_topic_name,
                  &audio_playback_chunk_qos),
              "audio_chunk_subscription_init")) {
    return false;
  }
  if (!rcl_ok(rclc_publisher_init(
                  &audio_playback_ack_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, AudioPlaybackAck),
                  audio_playback_ack_topic_name,
                  &audio_playback_ack_qos),
              "audio_playback_ack_publisher_init")) {
    return false;
  }
  if (!rcl_ok(rclc_client_init_default(
                  &audio_playback_chunk_client,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, NextAudioChunk),
                  audio_playback_chunk_service_name),
              "audio_playback_chunk_client_init")) {
    return false;
  }
  play_audio_chunk_client_initialized = true;
  if (!rcl_ok(rclc_service_init_default(
                  &audio_playback_load_service,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, LoadAudioChunk),
                  audio_playback_load_service_name),
              "audio_playback_load_service_init")) {
    return false;
  }
  audio_playback_load_service_initialized = true;
  if (!rcl_ok(rclc_publisher_init(
                  &camera_frame_chunk_ros_publisher,
                  &microros_node,
                  ROSIDL_GET_MSG_TYPE_SUPPORT(stackchan_msgs, msg, CameraFrameChunk),
                  camera_frame_chunk_topic_name,
                  &camera_frame_chunk_qos),
              "camera_frame_chunk_publisher_init")) {
    return false;
  }
  (void)try_initialize_capture_audio_action_server(
      "capture_audio_action_server_init");
  (void)try_initialize_capture_camera_action_server(
      "capture_camera_action_server_init");
  (void)try_initialize_play_audio_action_server(
      "play_audio_action_server_init");
  build_face_set_service_name();
  if (!rcl_ok(rclc_service_init_default(
                  &face_set_service,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, SetFace),
                  face_set_service_name),
              "face_set_service_init")) {
    return false;
  }
  build_head_pose_set_service_name();
  if (!rcl_ok(rclc_service_init_default(
                  &head_pose_set_service,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, SetHeadPose),
                  head_pose_set_service_name),
              "head_pose_set_service_init")) {
    return false;
  }
  build_led_set_service_name();
  if (!rcl_ok(rclc_service_init_default(
                  &led_set_service,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, SetLed),
                  led_set_service_name),
              "led_set_service_init")) {
    return false;
  }
  build_motion_set_service_name();
  if (!rcl_ok(rclc_service_init_default(
                  &motion_set_service,
                  &microros_node,
                  ROSIDL_GET_SRV_TYPE_SUPPORT(stackchan_msgs, srv, SetMotion),
                  motion_set_service_name),
              "motion_set_service_init")) {
    return false;
  }
  if (!stackchan_msgs__msg__StackChanEvent__init(&event_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=event_message_init result=false");
    return false;
  }
  if (!stackchan_msgs__msg__HeadPose__init(&motion_pose_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=motion_pose_message_init result=false");
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__msg__StackChanStatus__init(&status_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=status_message_init result=false");
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  stackchan_msgs__msg__CapabilityStatus__Sequence__fini(&status_ros_message.capabilities);
  if (!stackchan_msgs__msg__CapabilityStatus__Sequence__init(&status_ros_message.capabilities, 6)) {
    stackchan_diag_println("stackchan micro_ros_step=status_capabilities_init result=false");
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__msg__TouchState__init(&touch_state_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=touch_state_message_init result=false");
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__msg__ImuRaw__init(&imu_raw_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=imu_raw_message_init result=false");
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__msg__ProximityRaw__init(&proximity_raw_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=proximity_raw_message_init result=false");
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__msg__LightRaw__init(&light_raw_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=light_raw_message_init result=false");
    stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__msg__PowerStatus__init(&power_status_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=power_status_message_init result=false");
    stackchan_msgs__msg__LightRaw__fini(&light_raw_ros_message);
    stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__msg__AudioChunk__init(&audio_chunk_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=audio_chunk_message_init result=false");
    stackchan_msgs__msg__PowerStatus__fini(&power_status_ros_message);
    stackchan_msgs__msg__LightRaw__fini(&light_raw_ros_message);
    stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!reserve_audio_chunk_message_storage()) {
    stackchan_diag_println("stackchan micro_ros_step=audio_chunk_message_reserve result=false");
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__msg__PowerStatus__fini(&power_status_ros_message);
    stackchan_msgs__msg__LightRaw__fini(&light_raw_ros_message);
    stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__msg__AudioChunk__init(&audio_capture_chunk_ros_message)) {
    stackchan_diag_println("stackchan micro_ros_step=audio_capture_chunk_message_init result=false");
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__msg__PowerStatus__fini(&power_status_ros_message);
    stackchan_msgs__msg__LightRaw__fini(&light_raw_ros_message);
    stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!reserve_audio_capture_chunk_message_storage()) {
    stackchan_diag_println("stackchan micro_ros_step=audio_capture_chunk_message_reserve result=false");
    stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__msg__PowerStatus__fini(&power_status_ros_message);
    stackchan_msgs__msg__LightRaw__fini(&light_raw_ros_message);
    stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__action__CaptureAudio_SendGoal_Request__init(&capture_audio_goal_request) ||
      !stackchan_msgs__action__CaptureAudio_SendGoal_Response__init(&capture_audio_goal_response) ||
      !stackchan_msgs__action__CaptureAudio_GetResult_Request__init(&capture_audio_result_request) ||
      !stackchan_msgs__action__CaptureAudio_GetResult_Response__init(&capture_audio_result_response) ||
      !stackchan_msgs__action__CaptureAudio_FeedbackMessage__init(&capture_audio_feedback_message) ||
      !reserve_capture_audio_goal_strings()) {
    stackchan_diag_println("stackchan micro_ros_step=capture_audio_action_messages_init result=false");
    stackchan_msgs__action__CaptureAudio_FeedbackMessage__fini(&capture_audio_feedback_message);
    stackchan_msgs__action__CaptureAudio_GetResult_Response__fini(&capture_audio_result_response);
    stackchan_msgs__action__CaptureAudio_GetResult_Request__fini(&capture_audio_result_request);
    stackchan_msgs__action__CaptureAudio_SendGoal_Response__fini(&capture_audio_goal_response);
    stackchan_msgs__action__CaptureAudio_SendGoal_Request__fini(&capture_audio_goal_request);
    stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__msg__PowerStatus__fini(&power_status_ros_message);
    stackchan_msgs__msg__LightRaw__fini(&light_raw_ros_message);
    stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__action__PlayAudio_SendGoal_Request__init(&play_audio_goal_request) ||
      !reserve_play_audio_goal_strings() ||
      !stackchan_msgs__action__PlayAudio_SendGoal_Response__init(&play_audio_goal_response) ||
      !stackchan_msgs__action__PlayAudio_GetResult_Request__init(&play_audio_result_request) ||
      !stackchan_msgs__action__PlayAudio_GetResult_Response__init(&play_audio_result_response) ||
      !stackchan_msgs__srv__NextAudioChunk_Request__init(&audio_playback_chunk_request) ||
      !stackchan_msgs__srv__NextAudioChunk_Response__init(&audio_playback_chunk_response) ||
      !reserve_audio_playback_chunk_service_storage() ||
      !stackchan_msgs__msg__AudioPlaybackAck__init(&audio_playback_ack_ros_message) ||
      !reserve_audio_playback_ack_message_storage() ||
      !stackchan_msgs__srv__LoadAudioChunk_Request__init(&audio_playback_load_request) ||
      !stackchan_msgs__srv__LoadAudioChunk_Response__init(&audio_playback_load_response) ||
      !reserve_audio_playback_load_service_storage()) {
    stackchan_diag_println("stackchan micro_ros_step=play_audio_action_messages_init result=false");
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__CaptureAudio_FeedbackMessage__fini(&capture_audio_feedback_message);
    stackchan_msgs__action__CaptureAudio_GetResult_Response__fini(&capture_audio_result_response);
    stackchan_msgs__action__CaptureAudio_GetResult_Request__fini(&capture_audio_result_request);
    stackchan_msgs__action__CaptureAudio_SendGoal_Response__fini(&capture_audio_goal_response);
    stackchan_msgs__action__CaptureAudio_SendGoal_Request__fini(&capture_audio_goal_request);
    stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__msg__PowerStatus__fini(&power_status_ros_message);
    stackchan_msgs__msg__LightRaw__fini(&light_raw_ros_message);
    stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__msg__CameraFrameChunk__init(&camera_frame_chunk_ros_message) ||
      !reserve_camera_frame_chunk_message_storage()) {
    stackchan_diag_println("stackchan micro_ros_step=camera_frame_chunk_message_init result=false");
    stackchan_msgs__msg__CameraFrameChunk__fini(&camera_frame_chunk_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__action__CaptureAudio_FeedbackMessage__fini(&capture_audio_feedback_message);
    stackchan_msgs__action__CaptureAudio_GetResult_Response__fini(&capture_audio_result_response);
    stackchan_msgs__action__CaptureAudio_GetResult_Request__fini(&capture_audio_result_request);
    stackchan_msgs__action__CaptureAudio_SendGoal_Response__fini(&capture_audio_goal_response);
    stackchan_msgs__action__CaptureAudio_SendGoal_Request__fini(&capture_audio_goal_request);
    stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    return false;
  }
  if (!stackchan_msgs__action__CaptureCamera_SendGoal_Request__init(&capture_camera_goal_request) ||
      !stackchan_msgs__action__CaptureCamera_SendGoal_Response__init(&capture_camera_goal_response) ||
      !stackchan_msgs__action__CaptureCamera_GetResult_Request__init(&capture_camera_result_request) ||
      !stackchan_msgs__action__CaptureCamera_GetResult_Response__init(&capture_camera_result_response) ||
      !stackchan_msgs__action__CaptureCamera_FeedbackMessage__init(&capture_camera_feedback_message) ||
      !reserve_capture_camera_goal_strings() ||
      !reserve_capture_camera_result_storage()) {
    stackchan_diag_println("stackchan micro_ros_step=capture_camera_action_messages_init result=false");
    stackchan_msgs__action__CaptureCamera_FeedbackMessage__fini(&capture_camera_feedback_message);
    stackchan_msgs__action__CaptureCamera_GetResult_Response__fini(&capture_camera_result_response);
    stackchan_msgs__action__CaptureCamera_GetResult_Request__fini(&capture_camera_result_request);
    stackchan_msgs__action__CaptureCamera_SendGoal_Response__fini(&capture_camera_goal_response);
    stackchan_msgs__action__CaptureCamera_SendGoal_Request__fini(&capture_camera_goal_request);
    stackchan_msgs__msg__CameraFrameChunk__fini(&camera_frame_chunk_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__action__CaptureAudio_FeedbackMessage__fini(&capture_audio_feedback_message);
    stackchan_msgs__action__CaptureAudio_GetResult_Response__fini(&capture_audio_result_response);
    stackchan_msgs__action__CaptureAudio_GetResult_Request__fini(&capture_audio_result_request);
    stackchan_msgs__action__CaptureAudio_SendGoal_Response__fini(&capture_audio_goal_response);
    stackchan_msgs__action__CaptureAudio_SendGoal_Request__fini(&capture_audio_goal_request);
    stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__msg__PowerStatus__fini(&power_status_ros_message);
    stackchan_msgs__msg__LightRaw__fini(&light_raw_ros_message);
    stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetFace_Request__init(&face_set_request)) {
    stackchan_diag_println("stackchan micro_ros_step=face_set_request_init result=false");
    stackchan_msgs__msg__PowerStatus__fini(&power_status_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!reserve_face_set_request_strings()) {
    stackchan_diag_println("stackchan micro_ros_step=face_set_request_reserve result=false");
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetFace_Response__init(&face_set_response)) {
    stackchan_diag_println("stackchan micro_ros_step=face_set_response_init result=false");
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetHeadPose_Request__init(&head_pose_set_request)) {
    stackchan_diag_println("stackchan micro_ros_step=head_pose_set_request_init result=false");
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!reserve_head_pose_set_request_strings()) {
    stackchan_diag_println("stackchan micro_ros_step=head_pose_set_request_reserve result=false");
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetHeadPose_Response__init(&head_pose_set_response)) {
    stackchan_diag_println("stackchan micro_ros_step=head_pose_set_response_init result=false");
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetLed_Request__init(&led_set_request)) {
    stackchan_diag_println("stackchan micro_ros_step=led_set_request_init result=false");
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!reserve_led_set_request_strings()) {
    stackchan_diag_println("stackchan micro_ros_step=led_set_request_reserve result=false");
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetLed_Response__init(&led_set_response)) {
    stackchan_diag_println("stackchan micro_ros_step=led_set_response_init result=false");
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetMotion_Request__init(&motion_set_request)) {
    stackchan_diag_println("stackchan micro_ros_step=motion_set_request_init result=false");
    stackchan_msgs__srv__SetLed_Response__fini(&led_set_response);
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!reserve_motion_set_request_strings()) {
    stackchan_diag_println("stackchan micro_ros_step=motion_set_request_reserve result=false");
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetMotion_Response__init(&motion_set_response)) {
    stackchan_diag_println("stackchan micro_ros_step=motion_set_response_init result=false");
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!rcl_ok(rclc_executor_init(
                  &microros_executor,
                  &microros_support.context,
                  7,
                  &microros_allocator),
              "executor_init")) {
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  microros_executor_initialized = true;
  if (!rcl_ok(rclc_executor_add_service(
                  &microros_executor,
                  &face_set_service,
                  &face_set_request,
                  &face_set_response,
                  handle_face_set_service),
              "executor_add_face_set_service")) {
    rclc_executor_fini(&microros_executor);
    microros_executor_initialized = false;
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!rcl_ok(rclc_executor_add_service(
                  &microros_executor,
                  &head_pose_set_service,
                  &head_pose_set_request,
                  &head_pose_set_response,
                  handle_head_pose_set_service),
              "executor_add_head_pose_set_service")) {
    rclc_executor_fini(&microros_executor);
    microros_executor_initialized = false;
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!rcl_ok(rclc_executor_add_service(
                  &microros_executor,
                  &led_set_service,
                  &led_set_request,
                  &led_set_response,
                  handle_led_set_service),
              "executor_add_led_set_service")) {
    rclc_executor_fini(&microros_executor);
    microros_executor_initialized = false;
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__srv__SetLed_Response__fini(&led_set_response);
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!rcl_ok(rclc_executor_add_service(
                  &microros_executor,
                  &motion_set_service,
                  &motion_set_request,
                  &motion_set_response,
                  handle_motion_set_service),
              "executor_add_motion_set_service")) {
    rclc_executor_fini(&microros_executor);
    microros_executor_initialized = false;
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!rcl_ok(rclc_executor_add_subscription(
                  &microros_executor,
                  &audio_chunk_subscription,
                  &audio_chunk_ros_message,
                  handle_audio_chunk_subscription,
                  ON_NEW_DATA),
              "executor_add_audio_chunk_subscription")) {
    rclc_executor_fini(&microros_executor);
    microros_executor_initialized = false;
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__action__CaptureCamera_FeedbackMessage__fini(&capture_camera_feedback_message);
    stackchan_msgs__action__CaptureCamera_GetResult_Response__fini(&capture_camera_result_response);
    stackchan_msgs__action__CaptureCamera_GetResult_Request__fini(&capture_camera_result_request);
    stackchan_msgs__action__CaptureCamera_SendGoal_Response__fini(&capture_camera_goal_response);
    stackchan_msgs__action__CaptureCamera_SendGoal_Request__fini(&capture_camera_goal_request);
    stackchan_msgs__action__CaptureAudio_FeedbackMessage__fini(&capture_audio_feedback_message);
    stackchan_msgs__action__CaptureAudio_GetResult_Response__fini(&capture_audio_result_response);
    stackchan_msgs__action__CaptureAudio_GetResult_Request__fini(&capture_audio_result_request);
    stackchan_msgs__action__CaptureAudio_SendGoal_Response__fini(&capture_audio_goal_response);
    stackchan_msgs__action__CaptureAudio_SendGoal_Request__fini(&capture_audio_goal_request);
    stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!rcl_ok(rclc_executor_add_client(
                  &microros_executor,
                  &audio_playback_chunk_client,
                  &audio_playback_chunk_response,
                  handle_audio_playback_chunk_response),
              "executor_add_audio_playback_chunk_client")) {
    rclc_executor_fini(&microros_executor);
    microros_executor_initialized = false;
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!rcl_ok(rclc_executor_add_service(
                  &microros_executor,
                  &audio_playback_load_service,
                  &audio_playback_load_request,
                  &audio_playback_load_response,
                  handle_audio_playback_load_service),
              "executor_add_audio_playback_load_service")) {
    rclc_executor_fini(&microros_executor);
    microros_executor_initialized = false;
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  microros_entities_initialized = true;
  stackchan_audio_playback_transport_initialized =
      play_audio_action_server_initialized &&
      play_audio_chunk_client_initialized &&
      stackchan_audio_playback_initialized;
  stackchan_audio_capture_transport_initialized =
      capture_audio_action_server_initialized && stackchan_audio_capture_initialized;
  return true;
}

void destroy_microros_entities() {
  if (microros_entities_initialized) {
#if STACKCHAN_MICROROS_STATUS_ONLY_BRINGUP
    {
      stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
      rcl_ret_t fini_result =
          rcl_publisher_fini(&status_ros_publisher, &microros_node);
      fini_result = rcl_node_fini(&microros_node);
      fini_result = rclc_support_fini(&microros_support);
      (void)fini_result;
      microros_entities_initialized = false;
      microros_executor_initialized = false;
      stackchan_audio_playback_transport_initialized = false;
      stackchan_audio_capture_transport_initialized = false;
      reset_rcl_error();
      return;
    }
#endif
#if STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP
    {
      if (microros_executor_initialized) {
        rcl_ret_t executor_fini_result = rclc_executor_fini(&microros_executor);
        (void)executor_fini_result;
        microros_executor_initialized = false;
      }
      stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
      stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
      stackchan_msgs__srv__SetLed_Response__fini(&led_set_response);
      stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
      stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
      stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
      stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
      stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
#if STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP
      stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
      stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
      stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
      stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
      stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
      stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
      stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
      stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
      stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
#endif
#if STACKCHAN_MICROROS_CORE_CAPTURE_CAMERA_BRINGUP
      stackchan_msgs__action__CaptureCamera_FeedbackMessage__fini(&capture_camera_feedback_message);
      stackchan_msgs__action__CaptureCamera_GetResult_Response__fini(&capture_camera_result_response);
      stackchan_msgs__action__CaptureCamera_GetResult_Request__fini(&capture_camera_result_request);
      stackchan_msgs__action__CaptureCamera_SendGoal_Response__fini(&capture_camera_goal_response);
      stackchan_msgs__action__CaptureCamera_SendGoal_Request__fini(&capture_camera_goal_request);
      stackchan_msgs__msg__CameraFrameChunk__fini(&camera_frame_chunk_ros_message);
#endif
#if STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP
      stackchan_msgs__action__CaptureAudio_FeedbackMessage__fini(&capture_audio_feedback_message);
      stackchan_msgs__action__CaptureAudio_GetResult_Response__fini(&capture_audio_result_response);
      stackchan_msgs__action__CaptureAudio_GetResult_Request__fini(&capture_audio_result_request);
      stackchan_msgs__action__CaptureAudio_SendGoal_Response__fini(&capture_audio_goal_response);
      stackchan_msgs__action__CaptureAudio_SendGoal_Request__fini(&capture_audio_goal_request);
      stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
#endif
#if STACKCHAN_MICROROS_CORE_AUDIO_SUBSCRIPTION_BRINGUP
      stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
#endif
#if STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP
      stackchan_msgs__msg__PowerStatus__fini(&power_status_ros_message);
      stackchan_msgs__msg__LightRaw__fini(&light_raw_ros_message);
      stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
      stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
      stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
      stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
#endif
      stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
      rcl_ret_t fini_result =
          rcl_service_fini(&motion_set_service, &microros_node);
      fini_result = rcl_service_fini(&led_set_service, &microros_node);
      fini_result = rcl_service_fini(&head_pose_set_service, &microros_node);
      fini_result = rcl_service_fini(&face_set_service, &microros_node);
#if STACKCHAN_MICROROS_CORE_AUDIO_SUBSCRIPTION_BRINGUP
      fini_result = rcl_subscription_fini(&audio_chunk_subscription, &microros_node);
#endif
#if STACKCHAN_MICROROS_CORE_AUDIO_TOPIC_BRINGUP
      fini_result = rcl_publisher_fini(&audio_chunk_ros_publisher, &microros_node);
#endif
#if STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP
      if (capture_audio_action_server_initialized) {
        fini_result = rcl_action_server_fini(&capture_audio_action_server, &microros_node);
        capture_audio_action_server_initialized = false;
      }
#endif
#if STACKCHAN_MICROROS_CORE_CAPTURE_CAMERA_BRINGUP
      if (capture_camera_action_server_initialized) {
        fini_result = rcl_action_server_fini(&capture_camera_action_server, &microros_node);
        capture_camera_action_server_initialized = false;
      }
      fini_result = rcl_publisher_fini(&camera_frame_chunk_ros_publisher, &microros_node);
#endif
#if STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP
      if (audio_playback_load_service_initialized) {
        fini_result = rcl_service_fini(&audio_playback_load_service, &microros_node);
        audio_playback_load_service_initialized = false;
      }
      if (play_audio_chunk_client_initialized) {
        fini_result = rcl_client_fini(&audio_playback_chunk_client, &microros_node);
        play_audio_chunk_client_initialized = false;
      }
      fini_result = rcl_publisher_fini(&audio_playback_ack_ros_publisher, &microros_node);
      if (play_audio_action_server_initialized) {
        fini_result = rcl_action_server_fini(&play_audio_action_server, &microros_node);
        play_audio_action_server_initialized = false;
      }
#endif
#if STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP
      fini_result = rcl_publisher_fini(&power_status_ros_publisher, &microros_node);
      fini_result = rcl_publisher_fini(&light_raw_ros_publisher, &microros_node);
      fini_result = rcl_publisher_fini(&proximity_raw_ros_publisher, &microros_node);
      fini_result = rcl_publisher_fini(&imu_raw_ros_publisher, &microros_node);
      fini_result = rcl_publisher_fini(&touch_state_ros_publisher, &microros_node);
      fini_result = rcl_publisher_fini(&motion_pose_ros_publisher, &microros_node);
#endif
      fini_result = rcl_publisher_fini(&status_ros_publisher, &microros_node);
      fini_result = rcl_node_fini(&microros_node);
      fini_result = rclc_support_fini(&microros_support);
      (void)fini_result;
      microros_entities_initialized = false;
      stackchan_audio_playback_transport_initialized = false;
      stackchan_audio_capture_transport_initialized = false;
      audio_playback_guard.finish_session();
      play_audio_goal_active = false;
      play_audio_end_of_stream_seen = false;
      play_audio_result_ready = false;
      play_audio_result_request_pending = false;
      play_audio_chunk_request_pending = false;
      reset_rcl_error();
      return;
    }
#endif
    if (microros_executor_initialized) {
      rcl_ret_t fini_result = rclc_executor_fini(&microros_executor);
      (void)fini_result;
      microros_executor_initialized = false;
    }
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetLed_Response__fini(&led_set_response);
    stackchan_msgs__srv__SetLed_Request__fini(&led_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__srv__LoadAudioChunk_Response__fini(&audio_playback_load_response);
    stackchan_msgs__srv__LoadAudioChunk_Request__fini(&audio_playback_load_request);
    stackchan_msgs__srv__NextAudioChunk_Response__fini(&audio_playback_chunk_response);
    stackchan_msgs__srv__NextAudioChunk_Request__fini(&audio_playback_chunk_request);
    stackchan_msgs__msg__AudioPlaybackAck__fini(&audio_playback_ack_ros_message);
    stackchan_msgs__action__PlayAudio_GetResult_Response__fini(&play_audio_result_response);
    stackchan_msgs__action__PlayAudio_GetResult_Request__fini(&play_audio_result_request);
    stackchan_msgs__action__PlayAudio_SendGoal_Response__fini(&play_audio_goal_response);
    stackchan_msgs__action__PlayAudio_SendGoal_Request__fini(&play_audio_goal_request);
    stackchan_msgs__action__CaptureCamera_FeedbackMessage__fini(&capture_camera_feedback_message);
    stackchan_msgs__action__CaptureCamera_GetResult_Response__fini(&capture_camera_result_response);
    stackchan_msgs__action__CaptureCamera_GetResult_Request__fini(&capture_camera_result_request);
    stackchan_msgs__action__CaptureCamera_SendGoal_Response__fini(&capture_camera_goal_response);
    stackchan_msgs__action__CaptureCamera_SendGoal_Request__fini(&capture_camera_goal_request);
    stackchan_msgs__action__CaptureAudio_FeedbackMessage__fini(&capture_audio_feedback_message);
    stackchan_msgs__action__CaptureAudio_GetResult_Response__fini(&capture_audio_result_response);
    stackchan_msgs__action__CaptureAudio_GetResult_Request__fini(&capture_audio_result_request);
    stackchan_msgs__action__CaptureAudio_SendGoal_Response__fini(&capture_audio_goal_response);
    stackchan_msgs__action__CaptureAudio_SendGoal_Request__fini(&capture_audio_goal_request);
    stackchan_msgs__msg__AudioChunk__fini(&audio_capture_chunk_ros_message);
    stackchan_msgs__msg__AudioChunk__fini(&audio_chunk_ros_message);
    stackchan_msgs__msg__PowerStatus__fini(&power_status_ros_message);
    stackchan_msgs__msg__LightRaw__fini(&light_raw_ros_message);
    stackchan_msgs__msg__ProximityRaw__fini(&proximity_raw_ros_message);
    stackchan_msgs__msg__ImuRaw__fini(&imu_raw_ros_message);
    stackchan_msgs__msg__TouchState__fini(&touch_state_ros_message);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    rcl_ret_t fini_result = rcl_publisher_fini(&event_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&imu_raw_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&light_raw_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&motion_pose_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&power_status_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&proximity_raw_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&status_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&touch_state_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&audio_chunk_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&audio_playback_ack_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&camera_frame_chunk_ros_publisher, &microros_node);
    fini_result = rcl_subscription_fini(&audio_chunk_subscription, &microros_node);
    if (capture_audio_action_server_initialized) {
      fini_result = rcl_action_server_fini(&capture_audio_action_server, &microros_node);
      capture_audio_action_server_initialized = false;
    }
    if (capture_camera_action_server_initialized) {
      fini_result = rcl_action_server_fini(&capture_camera_action_server, &microros_node);
      capture_camera_action_server_initialized = false;
    }
    if (play_audio_action_server_initialized) {
      fini_result = rcl_action_server_fini(&play_audio_action_server, &microros_node);
      play_audio_action_server_initialized = false;
    }
    if (play_audio_chunk_client_initialized) {
      fini_result = rcl_client_fini(&audio_playback_chunk_client, &microros_node);
      play_audio_chunk_client_initialized = false;
    }
    if (audio_playback_load_service_initialized) {
      fini_result = rcl_service_fini(&audio_playback_load_service, &microros_node);
      audio_playback_load_service_initialized = false;
    }
    fini_result = rcl_service_fini(&face_set_service, &microros_node);
    fini_result = rcl_service_fini(&head_pose_set_service, &microros_node);
    fini_result = rcl_service_fini(&led_set_service, &microros_node);
    fini_result = rcl_service_fini(&motion_set_service, &microros_node);
    fini_result = rcl_node_fini(&microros_node);
    fini_result = rclc_support_fini(&microros_support);
    (void)fini_result;
    microros_entities_initialized = false;
    stackchan_audio_playback_transport_initialized = false;
    stackchan_audio_capture_transport_initialized = false;
    audio_capture_session_active = false;
    audio_capture_recording_chunk = false;
    capture_audio_goal_active = false;
    capture_audio_result_ready = false;
    capture_audio_result_request_pending = false;
    capture_camera_goal_active = false;
    capture_camera_result_ready = false;
    capture_camera_result_request_pending = false;
    audio_playback_guard.finish_session();
    play_audio_goal_active = false;
    play_audio_end_of_stream_seen = false;
    play_audio_result_ready = false;
    play_audio_result_request_pending = false;
    play_audio_chunk_request_pending = false;
  }
  reset_rcl_error();
}

bool try_connect_microros_agent() {
  if (!microros_transport_configured) {
    set_microros_serial_transports(Serial);
    microros_transport_configured = true;
  }
  if (microros_entities_initialized) {
    return true;
  }
  if (rmw_uros_ping_agent(100, 1) != RMW_RET_OK) {
    return false;
  }
  if (!initialize_microros_entities()) {
    destroy_microros_entities();
    return false;
  }
  return true;
}

bool firmware_publish_callback(
    stackchan::DevicePublisherTopic topic,
    const void* message,
    void*) {
  if (!microros_connected || !microros_entities_initialized) {
    return false;
  }

#if STACKCHAN_MICROROS_STATUS_ONLY_BRINGUP || \
    (STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP && !STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP)
  if (topic != stackchan::DevicePublisherTopic::Status) {
    return true;
  }
#elif STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP && \
    STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP && \
    !STACKCHAN_MICROROS_CORE_MEDIA_BRINGUP
  if (topic == stackchan::DevicePublisherTopic::Events) {
    return true;
  }
#endif

  if (message == nullptr) {
    stackchan_diag_print("stackchan firmware_publish topic=");
    stackchan_diag_print(device_publishers.topic_name(topic));
    stackchan_diag_print(" qos_depth=");
    stackchan_diag_println(device_publishers.qos(topic).depth);
    record_microros_publish_failure();
    return false;
  }

  const void* ros_message = nullptr;
  rcl_publisher_t* publisher = nullptr;
  if (topic == stackchan::DevicePublisherTopic::Events) {
    const auto* event_message =
        static_cast<const stackchan::StackChanEventMsg*>(message);
    if (!convert_event_message(*event_message, &event_ros_message)) {
      record_microros_publish_failure();
      return false;
    }
    ros_message = &event_ros_message;
    publisher = &event_ros_publisher;
  } else if (topic == stackchan::DevicePublisherTopic::Status) {
    const auto* status_message =
        static_cast<const stackchan::StackChanStatusMsg*>(message);
    if (!convert_status_message(*status_message, &status_ros_message)) {
      record_microros_publish_failure();
      return false;
    }
    ros_message = &status_ros_message;
    publisher = &status_ros_publisher;
  } else if (topic == stackchan::DevicePublisherTopic::MotionPose) {
    const auto* pose_message =
        static_cast<const stackchan::HeadPoseMsg*>(message);
    if (!convert_head_pose_message(*pose_message, &motion_pose_ros_message)) {
      record_microros_publish_failure();
      return false;
    }
    ros_message = &motion_pose_ros_message;
    publisher = &motion_pose_ros_publisher;
  } else if (topic == stackchan::DevicePublisherTopic::TouchState) {
    const auto* touch_message =
        static_cast<const stackchan::TouchStateMsg*>(message);
    if (!convert_touch_state_message(*touch_message, &touch_state_ros_message)) {
      record_microros_publish_failure();
      return false;
    }
    ros_message = &touch_state_ros_message;
    publisher = &touch_state_ros_publisher;
  } else if (topic == stackchan::DevicePublisherTopic::ImuRaw) {
    const auto* imu_message =
        static_cast<const stackchan::ImuRawMsg*>(message);
    if (!convert_imu_raw_message(*imu_message, &imu_raw_ros_message)) {
      record_microros_publish_failure();
      return false;
    }
    ros_message = &imu_raw_ros_message;
    publisher = &imu_raw_ros_publisher;
  } else if (topic == stackchan::DevicePublisherTopic::ProximityRaw) {
    const auto* proximity_message =
        static_cast<const stackchan::ProximityRawMsg*>(message);
    if (!convert_proximity_raw_message(*proximity_message, &proximity_raw_ros_message)) {
      record_microros_publish_failure();
      return false;
    }
    ros_message = &proximity_raw_ros_message;
    publisher = &proximity_raw_ros_publisher;
  } else if (topic == stackchan::DevicePublisherTopic::LightRaw) {
    const auto* light_message =
        static_cast<const stackchan::LightRawMsg*>(message);
    if (!convert_light_raw_message(*light_message, &light_raw_ros_message)) {
      record_microros_publish_failure();
      return false;
    }
    ros_message = &light_raw_ros_message;
    publisher = &light_raw_ros_publisher;
  } else if (topic == stackchan::DevicePublisherTopic::PowerStatus) {
    const auto* power_message =
        static_cast<const stackchan::PowerStatusMsg*>(message);
    if (!convert_power_status_message(*power_message, &power_status_ros_message)) {
      record_microros_publish_failure();
      return false;
    }
    ros_message = &power_status_ros_message;
    publisher = &power_status_ros_publisher;
  } else {
    stackchan_diag_print("stackchan firmware_publish topic=");
    stackchan_diag_print(device_publishers.topic_name(topic));
    stackchan_diag_print(" qos_depth=");
    stackchan_diag_println(device_publishers.qos(topic).depth);
    record_microros_publish_failure();
    return false;
  }
  ++microros_publish_attempt_count;
  const rcl_ret_t result = rcl_publish(publisher, ros_message, nullptr);
  last_microros_publish_result = result;
  if (result != RCL_RET_OK) {
    record_microros_publish_failure();
    reset_rcl_error();
    return false;
  }
  record_microros_publish_success();
  return true;
}

stackchan::Result publish_device_event_ros(
    const stackchan::DeviceEvent& event,
    void*) {
  if (!microros_connected) {
    return stackchan::Result::rejected(
        "TRANSPORT_DISCONNECTED",
        "micro-ROS publisher is disconnected",
        true);
  }

  return device_publishers.publish_event(event);
}

void update_agent_connection(bool connected) {
  if (!connected && microros_entities_initialized) {
    destroy_microros_entities();
  }
  microros_connected = connected;
  if (connected) {
    microros_consecutive_publish_failures = 0;
    state_machine.agent_connected();
    microros_connected_since_ms = millis();
    last_bringup_event_enqueue_ms = 0;
    microros_bringup_event_enqueue_count = 0;
  } else {
    microros_consecutive_publish_failures = 0;
    microros_connected_since_ms = 0;
    last_bringup_event_enqueue_ms = 0;
    microros_bringup_event_enqueue_count = 0;
    state_machine.agent_disconnected();
  }
}

void queue_bringup_event_if_ready(unsigned long now) {
#if STACKCHAN_MICROROS_STATUS_ONLY_BRINGUP || \
    (STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP && !STACKCHAN_MICROROS_CORE_MEDIA_BRINGUP)
  (void)now;
  return;
#endif
  if (!microros_connected ||
      microros_bringup_event_enqueue_count >= kBringupEventMaxEnqueues ||
      microros_connected_since_ms == 0 ||
      now - microros_connected_since_ms < kBringupEventDelayMs ||
      event_publisher.queued_count() > 0) {
    return;
  }
  if (last_bringup_event_enqueue_ms != 0 &&
      now - last_bringup_event_enqueue_ms < kBringupEventRetryMs) {
    return;
  }

  const stackchan::Result result =
      event_publisher.publish(
          stackchan::DeviceEventKind::FirmwareReady,
          now,
          "",
          "{\"transport\":\"serial\",\"agent\":\"micro_ros\"}");
  if (result.ok) {
    last_bringup_event_enqueue_ms = now;
    ++microros_bringup_event_enqueue_count;
    ++microros_bringup_event_total_enqueue_count;
  } else {
    last_error = result;
  }
}

void drain_device_events() {
  if (!microros_connected || event_publisher.queued_count() == 0) {
    return;
  }

  const stackchan::Result result = event_publisher.drain(kEventDrainBudget);
  if (!result.ok && strcmp(result.error_code, "TRANSPORT_DISCONNECTED") != 0) {
    last_error = result;
  }
}

void show_neutral_face() {
  render_face_display("neutral");
  copy_bounded(current_face, sizeof(current_face), "neutral");
}

stackchan::Result handle_face_command(
    const stackchan::CommandMeta& meta,
    const char* name) {
  if (meta.priority == stackchan::Priority::Safety) {
    last_error = stackchan::Result::rejected(
        "INVALID_PRIORITY",
        "SAFETY priority is reserved for firmware-internal fault handling");
    return last_error;
  }

  if (state_machine.state() == stackchan::RuntimeState::Fault) {
    last_error = stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "firmware is in fault state; recover before accepting face commands",
        true);
    return last_error;
  }

  if (!is_known_face(name)) {
    last_error = stackchan::Result::rejected("UNKNOWN_COMMAND", "unknown face name");
    return last_error;
  }

  render_face_display(name);
  copy_bounded(current_face, sizeof(current_face), name);
  copy_bounded(last_command_id, sizeof(last_command_id), meta.command_id);
  last_error = stackchan::Result::accepted("face accepted");
  publish_status_heartbeat();
  return last_error;
}

stackchan::Result audio_playback_completed_result() {
  return {true, stackchan::ResultState::Completed, "", "audio playback completed", false};
}

void fill_builtin_time_now(builtin_interfaces__msg__Time* destination) {
  if (destination == nullptr) {
    return;
  }
  destination->sec = millis() / 1000;
  destination->nanosec = (millis() % 1000) * 1000000;
}

bool goal_id_matches(
    const unique_identifier_msgs__msg__UUID& left,
    const unique_identifier_msgs__msg__UUID& right) {
  return memcmp(left.uuid, right.uuid, sizeof(left.uuid)) == 0;
}

void copy_goal_id(
    unique_identifier_msgs__msg__UUID* destination,
    const unique_identifier_msgs__msg__UUID& source) {
  if (destination == nullptr) {
    return;
  }
  memcpy(destination->uuid, source.uuid, sizeof(destination->uuid));
}

void copy_goal_info_from_request(
    rcl_action_goal_info_t* destination,
    const stackchan_msgs__action__PlayAudio_SendGoal_Request& request) {
  if (destination == nullptr) {
    return;
  }
  copy_goal_id(&destination->goal_id, request.goal_id);
  fill_builtin_time_now(&destination->stamp);
}

void copy_goal_info_from_request(
    rcl_action_goal_info_t* destination,
    const stackchan_msgs__action__CaptureAudio_SendGoal_Request& request) {
  if (destination == nullptr) {
    return;
  }
  copy_goal_id(&destination->goal_id, request.goal_id);
  fill_builtin_time_now(&destination->stamp);
}

void copy_goal_info_from_request(
    rcl_action_goal_info_t* destination,
    const stackchan_msgs__action__CaptureCamera_SendGoal_Request& request) {
  if (destination == nullptr) {
    return;
  }
  copy_goal_id(&destination->goal_id, request.goal_id);
  fill_builtin_time_now(&destination->stamp);
}

stackchan::Result audio_capture_completed_result() {
  return {true, stackchan::ResultState::Completed, "", "audio capture completed", false};
}

stackchan::Result audio_capture_failed_result(const char* message) {
  return stackchan::Result::rejected(
      "AUDIO_CAPTURE_FAILED",
      message == nullptr ? "audio capture failed" : message,
      true);
}

stackchan::Result camera_capture_completed_result() {
  return {true, stackchan::ResultState::Completed, "", "camera capture completed", false};
}

stackchan::Result camera_capture_failed_result(const char* message) {
  return stackchan::Result::rejected(
      "CAMERA_CAPTURE_FAILED",
      message == nullptr ? "camera capture failed" : message,
      true);
}

void clear_capture_camera_image_result() {
  assign_ros_string(&capture_camera_result_response.result.image.format, "jpeg");
  capture_camera_result_response.result.image.data.size = 0;
}

bool capture_camera_goal_valid(
    const stackchan_msgs__action__CaptureCamera_Goal& goal,
    stackchan::Result* result) {
  const char* goal_device_id =
      goal.meta.device_id.data != nullptr ? goal.meta.device_id.data : "";
  const char* goal_format = goal.format.data != nullptr ? goal.format.data : "";
  if (strcmp(goal_device_id, STACKCHAN_DEVICE_ID) != 0) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "UNKNOWN_COMMAND",
          "camera capture goal device_id mismatch",
          true);
    }
    return false;
  }
  if (!stackchan_camera_snapshot_initialized) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "UNSUPPORTED_FEATURE",
          "camera snapshot is not available",
          false);
    }
    return false;
  }
  if (strcmp(goal_format, "jpeg") != 0 ||
      goal.width != stackchan::kCameraWidth ||
      goal.height != stackchan::kCameraHeight) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "UNSUPPORTED_FEATURE",
          "camera capture goal format is unsupported",
          false);
    }
    return false;
  }
  const stackchan::Result quality_result =
      stackchan::validate_camera_quality(goal.quality);
  if (!quality_result.ok) {
    if (result != nullptr) {
      *result = quality_result;
    }
    return false;
  }
  if (capture_camera_goal_active || capture_camera_result_ready) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "FIRMWARE_BUSY",
          "camera capture already active",
          true);
    }
    return false;
  }
  if (result != nullptr) {
    *result = stackchan::Result::accepted("camera capture goal accepted");
  }
  return true;
}

void finish_capture_camera_goal(const stackchan::Result& result, int8_t action_status) {
  if (capture_camera_goal_active && capture_camera_active_goal_handle != nullptr) {
    rcl_ok(
        rcl_action_update_goal_state(
            capture_camera_active_goal_handle,
            result.ok ? GOAL_EVENT_SUCCEED : GOAL_EVENT_ABORT),
        "capture_camera_update_terminal_goal_state");
    rcl_ok(
        rcl_action_notify_goal_done(&capture_camera_action_server),
        "capture_camera_notify_goal_done");
  }
  capture_camera_terminal_goal_info = capture_camera_active_goal_info;
  capture_camera_terminal_result = result;
  capture_camera_terminal_status = action_status;
  capture_camera_result_ready = true;
  capture_camera_goal_active = false;
  capture_camera_active_goal_handle = nullptr;
  if (!result.ok) {
    event_publisher.publish(
        stackchan::DeviceEventKind::CameraCaptureFailed,
        millis(),
        last_command_id);
  }
}

void send_capture_camera_result_if_ready() {
  if (!capture_camera_result_ready || !capture_camera_result_request_pending) {
    return;
  }
  if (!goal_id_matches(
          capture_camera_result_request.goal_id,
          capture_camera_terminal_goal_info.goal_id)) {
    return;
  }
  capture_camera_result_response.status = capture_camera_terminal_status;
  if (!convert_command_result(
          capture_camera_terminal_result,
          &capture_camera_result_response.result.result)) {
    stackchan_diag_println("stackchan micro_ros_step=capture_camera_result_assign result=false");
    return;
  }
  if (!capture_camera_terminal_result.ok) {
    clear_capture_camera_image_result();
  }
  if (rcl_ok(rcl_action_send_result_response(
                 &capture_camera_action_server,
                 &capture_camera_result_request_header,
                 &capture_camera_result_response),
             "capture_camera_send_result_response")) {
    capture_camera_result_request_pending = false;
    capture_camera_result_ready = false;
    clear_capture_camera_image_result();
  }
}

void publish_capture_camera_feedback(float progress, const char* message) {
  copy_goal_id(
      &capture_camera_feedback_message.goal_id,
      capture_camera_active_goal_info.goal_id);
  capture_camera_feedback_message.feedback.progress = progress;
  assign_ros_string(
      &capture_camera_feedback_message.feedback.message,
      message == nullptr ? "" : message);
  rcl_ok(
      rcl_action_publish_feedback(
          &capture_camera_action_server,
          &capture_camera_feedback_message),
      "capture_camera_publish_feedback");
}

bool publish_capture_camera_frame_chunks(
    const uint8_t* data,
    size_t length,
    uint8_t quality,
    const char* command_id) {
  if (data == nullptr || length == 0 || length > stackchan::kCameraMaxPayloadBytes ||
      camera_frame_chunk_ros_message.data.capacity < stackchan::kCameraFrameChunkBytes) {
    return false;
  }
  const uint32_t total_chunks =
      static_cast<uint32_t>(
          (length + stackchan::kCameraFrameChunkBytes - 1) /
          stackchan::kCameraFrameChunkBytes);
  assign_ros_string(&camera_frame_chunk_ros_message.device_id, STACKCHAN_DEVICE_ID);
  assign_ros_string(
      &camera_frame_chunk_ros_message.command_id,
      command_id == nullptr ? "" : command_id);
  camera_frame_chunk_ros_message.total_chunks = total_chunks;
  camera_frame_chunk_ros_message.total_bytes = static_cast<uint32_t>(length);
  camera_frame_chunk_ros_message.format =
      stackchan_msgs__msg__CameraFrameChunk__JPEG;
  camera_frame_chunk_ros_message.width = stackchan::kCameraWidth;
  camera_frame_chunk_ros_message.height = stackchan::kCameraHeight;
  camera_frame_chunk_ros_message.quality = quality;
  for (uint32_t sequence = 0; sequence < total_chunks; ++sequence) {
    const size_t offset =
        static_cast<size_t>(sequence) * stackchan::kCameraFrameChunkBytes;
    const size_t remaining = length - offset;
    const size_t chunk_length =
        remaining < stackchan::kCameraFrameChunkBytes
            ? remaining
            : stackchan::kCameraFrameChunkBytes;
    camera_frame_chunk_ros_message.sequence = sequence;
    camera_frame_chunk_ros_message.end_of_stream = sequence + 1 == total_chunks;
    memcpy(camera_frame_chunk_ros_message.data.data, data + offset, chunk_length);
    camera_frame_chunk_ros_message.data.size = chunk_length;
    if (!rcl_ok(
            rcl_publish(
                &camera_frame_chunk_ros_publisher,
                &camera_frame_chunk_ros_message,
                nullptr),
            "camera_frame_chunk_publish")) {
      camera_frame_chunk_ros_message.data.size = 0;
      return false;
    }
    delay(kCameraFrameChunkPublishIntervalMs);
  }
  camera_frame_chunk_ros_message.data.size = 0;
  return true;
}

uint8_t camera_driver_quality_from_goal(uint8_t quality) {
  const uint8_t clamped =
      quality < stackchan::kCameraMinQuality
          ? stackchan::kCameraMinQuality
          : (quality > stackchan::kCameraMaxQuality
                 ? stackchan::kCameraMaxQuality
                 : quality);
  const uint32_t span = kCameraDriverLowestQuality - kCameraDriverBestQuality;
  return kCameraDriverLowestQuality -
         static_cast<uint8_t>(
             (static_cast<uint32_t>(clamped - stackchan::kCameraMinQuality) * span) /
             (stackchan::kCameraMaxQuality - stackchan::kCameraMinQuality));
}

bool drain_camera_warmup_frames(uint32_t started_ms) {
  for (uint8_t frame_index = 0; frame_index < kCameraWarmupFrames; ++frame_index) {
    const unsigned long elapsed_ms = millis() - started_ms;
    if (elapsed_ms > kCameraWarmupMaxMs || elapsed_ms > kCameraCaptureTimeoutMs) {
      return false;
    }
    camera_fb_t* warmup_frame = esp_camera_fb_get();
    if (warmup_frame == nullptr) {
      return false;
    }
    esp_camera_fb_return(warmup_frame);
    delay(kCameraWarmupFrameDelayMs);
  }
  return true;
}

stackchan::Result capture_camera_frame_to_result(uint8_t quality, const char* command_id) {
  const uint32_t started_ms = millis();
  if (stackchan_camera_sensor != nullptr) {
    stackchan_camera_sensor->set_quality(
        stackchan_camera_sensor,
        camera_driver_quality_from_goal(quality));
  }
  if (!drain_camera_warmup_frames(started_ms)) {
    return camera_capture_failed_result("camera warmup frame drain failed");
  }
  camera_fb_t* frame = esp_camera_fb_get();
  if (frame == nullptr) {
    return camera_capture_failed_result("camera frame capture failed");
  }
  if (frame->width != stackchan::kCameraWidth ||
      frame->height != stackchan::kCameraHeight) {
    esp_camera_fb_return(frame);
    return camera_capture_failed_result("camera frame dimensions are unsupported");
  }
  if (frame->format == PIXFORMAT_JPEG) {
    const size_t jpeg_length = frame->len;
    if (millis() - started_ms > kCameraCaptureTimeoutMs) {
      esp_camera_fb_return(frame);
      return camera_capture_failed_result("camera capture timed out");
    }
    if (jpeg_length > stackchan::kCameraMaxPayloadBytes) {
      esp_camera_fb_return(frame);
      return camera_capture_failed_result("camera JPEG payload exceeds 96 KiB");
    }
    if (!publish_capture_camera_frame_chunks(frame->buf, jpeg_length, quality, command_id)) {
      esp_camera_fb_return(frame);
      return camera_capture_failed_result("camera JPEG chunk publish failed");
    }
    esp_camera_fb_return(frame);
    return camera_capture_completed_result();
  }

  uint8_t* jpeg_buffer = nullptr;
  size_t jpeg_length = 0;
  const bool encoded = frame2jpg(frame, quality, &jpeg_buffer, &jpeg_length);
  esp_camera_fb_return(frame);
  if (!encoded || jpeg_buffer == nullptr || jpeg_length == 0) {
    if (jpeg_buffer != nullptr) {
      free(jpeg_buffer);
    }
    return camera_capture_failed_result("camera JPEG encode failed");
  }
  if (millis() - started_ms > kCameraCaptureTimeoutMs) {
    free(jpeg_buffer);
    return camera_capture_failed_result("camera capture timed out");
  }
  if (jpeg_length > stackchan::kCameraMaxPayloadBytes) {
    free(jpeg_buffer);
    return camera_capture_failed_result("camera JPEG payload exceeds 96 KiB");
  }
  if (!publish_capture_camera_frame_chunks(jpeg_buffer, jpeg_length, quality, command_id)) {
    free(jpeg_buffer);
    return camera_capture_failed_result("camera JPEG chunk publish failed");
  }
  free(jpeg_buffer);
  return camera_capture_completed_result();
}

void start_capture_camera_goal(
    rcl_action_goal_handle_t* goal_handle,
    const stackchan_msgs__action__CaptureCamera_SendGoal_Request& request) {
  capture_camera_active_goal_handle = goal_handle;
  copy_goal_info_from_request(&capture_camera_active_goal_info, request);
  capture_camera_goal_active = true;
  rcl_ok(
      rcl_action_update_goal_state(capture_camera_active_goal_handle, GOAL_EVENT_EXECUTE),
      "capture_camera_update_execute_goal_state");
  copy_bounded(
      last_command_id,
      sizeof(last_command_id),
      request.goal.meta.command_id.data != nullptr
          ? request.goal.meta.command_id.data
          : "");
  clear_capture_camera_image_result();
  publish_capture_camera_feedback(0.0f, "capture started");
  publish_status_heartbeat();
  const stackchan::Result result =
      capture_camera_frame_to_result(
          request.goal.quality,
          request.goal.meta.command_id.data != nullptr
              ? request.goal.meta.command_id.data
              : "");
  publish_capture_camera_feedback(result.ok ? 1.0f : 0.0f, result.message);
  const int8_t action_status =
      result.ok
          ? static_cast<int8_t>(GOAL_STATE_SUCCEEDED)
          : static_cast<int8_t>(GOAL_STATE_ABORTED);
  finish_capture_camera_goal(result, action_status);
  send_capture_camera_result_if_ready();
}

void poll_capture_camera_goal_request() {
  rmw_request_id_t request_header;
  rcl_ret_t take_result = rcl_action_take_goal_request(
      &capture_camera_action_server,
      &request_header,
      &capture_camera_goal_request);
  if (take_result == RCL_RET_ACTION_SERVER_TAKE_FAILED) {
    reset_rcl_error();
    return;
  }
  if (take_result != RCL_RET_OK) {
    rcl_ok(take_result, "capture_camera_take_goal_request");
    return;
  }

  rcl_action_goal_info_t goal_info =
      rcl_action_get_zero_initialized_goal_info();
  copy_goal_info_from_request(&goal_info, capture_camera_goal_request);
  if (capture_camera_goal_active || capture_camera_result_ready) {
    capture_camera_goal_response.accepted = false;
    capture_camera_goal_response.stamp = goal_info.stamp;
    rcl_ok(
        rcl_action_send_goal_response(
            &capture_camera_action_server,
            &request_header,
            &capture_camera_goal_response),
        "capture_camera_send_busy_goal_response");
    return;
  }
  rcl_action_goal_handle_t* goal_handle =
      rcl_action_accept_new_goal(&capture_camera_action_server, &goal_info);
  capture_camera_goal_response.accepted = goal_handle != nullptr;
  capture_camera_goal_response.stamp = goal_info.stamp;
  rcl_ok(
      rcl_action_send_goal_response(
          &capture_camera_action_server,
          &request_header,
          &capture_camera_goal_response),
      "capture_camera_send_goal_response");
  if (goal_handle == nullptr) {
    reset_rcl_error();
    return;
  }

  stackchan::Result validation_result;
  if (!capture_camera_goal_valid(capture_camera_goal_request.goal, &validation_result)) {
    capture_camera_active_goal_handle = goal_handle;
    copy_goal_info_from_request(&capture_camera_active_goal_info, capture_camera_goal_request);
    capture_camera_goal_active = true;
    rcl_ok(
        rcl_action_update_goal_state(capture_camera_active_goal_handle, GOAL_EVENT_EXECUTE),
        "capture_camera_update_invalid_goal_state");
    clear_capture_camera_image_result();
    finish_capture_camera_goal(validation_result, GOAL_STATE_ABORTED);
    return;
  }
  start_capture_camera_goal(goal_handle, capture_camera_goal_request);
}

void poll_capture_camera_result_request() {
  rmw_request_id_t request_header;
  rcl_ret_t take_result = rcl_action_take_result_request(
      &capture_camera_action_server,
      &request_header,
      &capture_camera_result_request);
  if (take_result == RCL_RET_ACTION_SERVER_TAKE_FAILED) {
    reset_rcl_error();
    return;
  }
  if (take_result != RCL_RET_OK) {
    rcl_ok(take_result, "capture_camera_take_result_request");
    return;
  }
  capture_camera_result_request_header = request_header;
  capture_camera_result_request_pending = true;
  send_capture_camera_result_if_ready();
}

void poll_capture_camera_action_server() {
  if (!capture_camera_action_server_initialized) {
    return;
  }
  poll_capture_camera_goal_request();
  poll_capture_camera_result_request();
  send_capture_camera_result_if_ready();
}

bool capture_audio_goal_valid(
    const stackchan_msgs__action__CaptureAudio_Goal& goal,
    stackchan::Result* result) {
  const char* goal_device_id =
      goal.meta.device_id.data != nullptr ? goal.meta.device_id.data : "";
  const char* goal_format = goal.format.data != nullptr ? goal.format.data : "";
  if (strcmp(goal_device_id, STACKCHAN_DEVICE_ID) != 0) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "UNKNOWN_COMMAND",
          "audio capture goal device_id mismatch",
          true);
    }
    return false;
  }
  if (!stackchan_audio_capture_initialized) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "UNSUPPORTED_FEATURE",
          "microphone is not available",
          false);
    }
    return false;
  }
  if (strcmp(goal_format, "pcm_s16le") != 0 ||
      goal.sample_rate != stackchan::kAudioSampleRate ||
      goal.channels != stackchan::kAudioChannels) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "UNSUPPORTED_FEATURE",
          "audio capture goal format is unsupported",
          false);
    }
    return false;
  }
  if (goal.duration_ms == 0 || goal.duration_ms > kAudioCaptureMaxDurationMs) {
    if (result != nullptr) {
      *result = audio_capture_failed_result(
          "audio capture duration must be between 1 and 15000 ms");
    }
    return false;
  }
  if (audio_capture_session_active) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "FIRMWARE_BUSY",
          "audio capture already active",
          true);
    }
    return false;
  }
  if (audio_playback_guard.active()) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "FIRMWARE_BUSY",
          "audio playback already active",
          true);
    }
    return false;
  }
  if (result != nullptr) {
    *result = stackchan::Result::accepted("audio capture goal accepted");
  }
  return true;
}

void recover_capture_mic_after_abort(const char* stage) {
  if (!stackchan_audio_capture_initialized) {
    return;
  }
  stackchan_diag_print("stackchan audio_capture_diag stage=");
  stackchan_diag_print(stage == nullptr ? "mic_recover" : stage);
  stackchan_diag_print(" command_id=");
  stackchan_diag_println(audio_capture_command_id);
  M5.Mic.end();
  delay(5);
  stackchan_audio_capture_initialized = M5.Mic.begin();
  stackchan_diag_print("stackchan audio_capture_diag stage=mic_recovered available=");
  stackchan_diag_println(stackchan_audio_capture_initialized ? "true" : "false");
}

void finish_capture_audio_goal(const stackchan::Result& result, int8_t action_status) {
  const bool recover_mic = !result.ok && audio_capture_session_active;
  if (capture_audio_goal_active && capture_audio_active_goal_handle != nullptr) {
    rcl_ok(
        rcl_action_update_goal_state(
            capture_audio_active_goal_handle,
            result.ok ? GOAL_EVENT_SUCCEED : GOAL_EVENT_ABORT),
        "capture_audio_update_terminal_goal_state");
    rcl_ok(
        rcl_action_notify_goal_done(&capture_audio_action_server),
        "capture_audio_notify_goal_done");
  }
  capture_audio_terminal_goal_info = capture_audio_active_goal_info;
  capture_audio_terminal_result = result;
  capture_audio_terminal_status = action_status;
  capture_audio_result_ready = true;
  capture_audio_goal_active = false;
  capture_audio_active_goal_handle = nullptr;
  if (recover_mic) {
    recover_capture_mic_after_abort("capture_abort");
  }
  audio_capture_session_active = false;
  audio_capture_recording_chunk = false;
  char finished_command_id[37]{};
  copy_bounded(finished_command_id, sizeof(finished_command_id), audio_capture_command_id);
  if (result.ok) {
    stackchan::publish_audio_capture_event(
        event_publisher,
        stackchan::AudioCaptureEvent::Finished,
        millis(),
        finished_command_id);
  } else {
    stackchan::publish_audio_capture_event(
        event_publisher,
        stackchan::AudioCaptureEvent::Failed,
        millis(),
        finished_command_id);
  }
  copy_bounded(audio_capture_command_id, sizeof(audio_capture_command_id), "");
}

void send_capture_audio_result_if_ready() {
  if (!capture_audio_result_ready || !capture_audio_result_request_pending) {
    return;
  }
  if (!goal_id_matches(
          capture_audio_result_request.goal_id,
          capture_audio_terminal_goal_info.goal_id)) {
    return;
  }
  capture_audio_result_response.status = capture_audio_terminal_status;
  if (!convert_command_result(
          capture_audio_terminal_result,
          &capture_audio_result_response.result.result)) {
    stackchan_diag_println("stackchan micro_ros_step=capture_audio_result_assign result=false");
    return;
  }
  if (rcl_ok(rcl_action_send_result_response(
                 &capture_audio_action_server,
                 &capture_audio_result_request_header,
                 &capture_audio_result_response),
             "capture_audio_send_result_response")) {
    capture_audio_result_request_pending = false;
    capture_audio_result_ready = false;
  }
}

void publish_capture_audio_feedback(float progress, const char* message) {
  copy_goal_id(
      &capture_audio_feedback_message.goal_id,
      capture_audio_active_goal_info.goal_id);
  capture_audio_feedback_message.feedback.progress = progress;
  assign_ros_string(
      &capture_audio_feedback_message.feedback.message,
      message == nullptr ? "" : message);
  rcl_ok(
      rcl_action_publish_feedback(
          &capture_audio_action_server,
          &capture_audio_feedback_message),
      "capture_audio_publish_feedback");
}

bool publish_capture_audio_chunk(const int16_t* samples, size_t sample_count) {
  if (samples == nullptr ||
      sample_count == 0 ||
      sample_count > kAudioCaptureChunkSamples ||
      audio_capture_chunk_ros_message.pcm.capacity < sample_count * 2) {
    return false;
  }
  assign_ros_string(&audio_capture_chunk_ros_message.device_id, STACKCHAN_DEVICE_ID);
  assign_ros_string(&audio_capture_chunk_ros_message.command_id, audio_capture_command_id);
  audio_capture_chunk_ros_message.direction = stackchan_msgs__msg__AudioChunk__CAPTURE;
  audio_capture_chunk_ros_message.sequence = audio_capture_sequence;
  audio_capture_chunk_ros_message.format = stackchan_msgs__msg__AudioChunk__PCM_S16LE;
  audio_capture_chunk_ros_message.sample_rate = stackchan::kAudioSampleRate;
  audio_capture_chunk_ros_message.channels = stackchan::kAudioChannels;
  audio_capture_chunk_ros_message.pcm.size = sample_count * 2;
  for (size_t index = 0; index < sample_count; ++index) {
    const uint16_t value = static_cast<uint16_t>(samples[index]);
    const size_t byte_index = index * 2;
    audio_capture_chunk_ros_message.pcm.data[byte_index] =
        static_cast<uint8_t>(value & 0xFF);
    audio_capture_chunk_ros_message.pcm.data[byte_index + 1] =
        static_cast<uint8_t>((value >> 8) & 0xFF);
  }
  const rcl_ret_t publish_result =
      rcl_publish(&audio_chunk_ros_publisher, &audio_capture_chunk_ros_message, nullptr);
  if (publish_result != RCL_RET_OK) {
    last_microros_publish_result = publish_result;
    reset_rcl_error();
    return false;
  }
  ++audio_capture_sequence;
  ++audio_capture_published_chunks;
  const bool publish_progress =
      audio_capture_published_chunks == 1 ||
      audio_capture_published_chunks >= audio_capture_target_chunks ||
      audio_capture_published_chunks % kAudioCaptureFeedbackEveryChunks == 0;
  if (publish_progress) {
    const float progress =
        audio_capture_target_chunks == 0
            ? 1.0f
            : static_cast<float>(audio_capture_published_chunks) /
                  static_cast<float>(audio_capture_target_chunks);
    publish_capture_audio_feedback(progress > 1.0f ? 1.0f : progress, "capturing");
  }
  return true;
}

bool start_next_capture_audio_chunk() {
  if (!audio_capture_session_active ||
      audio_capture_recording_chunk ||
      audio_capture_published_chunks >= audio_capture_target_chunks) {
    return true;
  }
  int16_t* samples = audio_capture_buffers[audio_capture_buffer_index];
  if (!M5.Mic.record(samples, kAudioCaptureChunkSamples, stackchan::kAudioSampleRate, false)) {
    return false;
  }
  audio_capture_recording_chunk = true;
  audio_capture_last_chunk_ms = millis();
  return true;
}

void step_capture_audio_session() {
  if (!audio_capture_session_active) {
    send_capture_audio_result_if_ready();
    return;
  }
  if (audio_capture_recording_chunk && M5.Mic.isRecording() == 0) {
    int16_t* samples = audio_capture_buffers[audio_capture_buffer_index];
    if (!publish_capture_audio_chunk(samples, kAudioCaptureChunkSamples)) {
      stackchan::publish_mic_overrun_event(
          event_publisher,
          millis(),
          audio_capture_command_id);
      finish_capture_audio_goal(stackchan::mic_overrun(), GOAL_STATE_ABORTED);
      send_capture_audio_result_if_ready();
      return;
    }
    audio_capture_buffer_index = (audio_capture_buffer_index + 1) % 2;
    audio_capture_recording_chunk = false;
  }
  const uint32_t now_ms = millis();
  if (now_ms - audio_capture_started_ms >=
      audio_capture_duration_ms + kAudioCaptureSessionTimeoutGraceMs) {
    stackchan_diag_print("stackchan audio_capture_diag stage=session_timeout command_id=");
    stackchan_diag_print(audio_capture_command_id);
    stackchan_diag_print(" published_chunks=");
    stackchan_diag_print(audio_capture_published_chunks);
    stackchan_diag_print(" target_chunks=");
    stackchan_diag_println(audio_capture_target_chunks);
    finish_capture_audio_goal(
        audio_capture_failed_result("audio capture session timed out"),
        GOAL_STATE_ABORTED);
    send_capture_audio_result_if_ready();
    return;
  }
  if (audio_capture_recording_chunk &&
      now_ms - audio_capture_last_chunk_ms >= kAudioCaptureChunkTimeoutMs) {
    finish_capture_audio_goal(
        audio_capture_failed_result("microphone record chunk timed out"),
        GOAL_STATE_ABORTED);
    send_capture_audio_result_if_ready();
    return;
  }
  if (audio_capture_published_chunks >= audio_capture_target_chunks) {
    publish_capture_audio_feedback(1.0f, "capture complete");
    finish_capture_audio_goal(audio_capture_completed_result(), GOAL_STATE_SUCCEEDED);
    send_capture_audio_result_if_ready();
    return;
  }
  if (!audio_capture_recording_chunk && !start_next_capture_audio_chunk()) {
    finish_capture_audio_goal(
        audio_capture_failed_result("microphone record request failed"),
        GOAL_STATE_ABORTED);
  }
  send_capture_audio_result_if_ready();
}

void start_capture_audio_goal(
    rcl_action_goal_handle_t* goal_handle,
    const stackchan_msgs__action__CaptureAudio_SendGoal_Request& request) {
  capture_audio_active_goal_handle = goal_handle;
  copy_goal_info_from_request(&capture_audio_active_goal_info, request);
  capture_audio_goal_active = true;
  rcl_ok(
      rcl_action_update_goal_state(capture_audio_active_goal_handle, GOAL_EVENT_EXECUTE),
      "capture_audio_update_execute_goal_state");
  copy_bounded(
      audio_capture_command_id,
      sizeof(audio_capture_command_id),
      request.goal.meta.command_id.data != nullptr
          ? request.goal.meta.command_id.data
          : "");
  copy_bounded(last_command_id, sizeof(last_command_id), audio_capture_command_id);
  audio_capture_duration_ms = request.goal.duration_ms;
  audio_capture_target_chunks =
      (audio_capture_duration_ms + kAudioCaptureChunkMs - 1) /
      kAudioCaptureChunkMs;
  if (audio_capture_target_chunks == 0) {
    audio_capture_target_chunks = 1;
  }
  audio_capture_started_ms = millis();
  audio_capture_last_chunk_ms = audio_capture_started_ms;
  audio_capture_sequence = 0;
  audio_capture_published_chunks = 0;
  audio_capture_buffer_index = 0;
  audio_capture_recording_chunk = false;
  audio_capture_session_active = true;
  stackchan::publish_audio_capture_event(
      event_publisher,
      stackchan::AudioCaptureEvent::Started,
      audio_capture_started_ms,
      audio_capture_command_id);
  publish_capture_audio_feedback(0.0f, "capture started");
  publish_status_heartbeat();
  if (!start_next_capture_audio_chunk()) {
    finish_capture_audio_goal(
        audio_capture_failed_result("microphone record request failed"),
        GOAL_STATE_ABORTED);
  }
}

void poll_capture_audio_goal_request() {
  rmw_request_id_t request_header;
  rcl_ret_t take_result = rcl_action_take_goal_request(
      &capture_audio_action_server,
      &request_header,
      &capture_audio_goal_request);
  if (take_result == RCL_RET_ACTION_SERVER_TAKE_FAILED) {
    reset_rcl_error();
    return;
  }
  if (take_result != RCL_RET_OK) {
    rcl_ok(take_result, "capture_audio_take_goal_request");
    return;
  }

  rcl_action_goal_info_t goal_info =
      rcl_action_get_zero_initialized_goal_info();
  copy_goal_info_from_request(&goal_info, capture_audio_goal_request);
  if (audio_capture_session_active) {
    capture_audio_goal_response.accepted = false;
    capture_audio_goal_response.stamp = goal_info.stamp;
    rcl_ok(
        rcl_action_send_goal_response(
            &capture_audio_action_server,
            &request_header,
            &capture_audio_goal_response),
        "capture_audio_send_busy_goal_response");
    return;
  }
  rcl_action_goal_handle_t* goal_handle =
      rcl_action_accept_new_goal(&capture_audio_action_server, &goal_info);
  capture_audio_goal_response.accepted = goal_handle != nullptr;
  capture_audio_goal_response.stamp = goal_info.stamp;
  rcl_ok(
      rcl_action_send_goal_response(
          &capture_audio_action_server,
          &request_header,
          &capture_audio_goal_response),
      "capture_audio_send_goal_response");
  if (goal_handle == nullptr) {
    reset_rcl_error();
    return;
  }

  stackchan::Result validation_result;
  if (!capture_audio_goal_valid(capture_audio_goal_request.goal, &validation_result)) {
    capture_audio_active_goal_handle = goal_handle;
    copy_goal_info_from_request(&capture_audio_active_goal_info, capture_audio_goal_request);
    capture_audio_goal_active = true;
    rcl_ok(
        rcl_action_update_goal_state(capture_audio_active_goal_handle, GOAL_EVENT_EXECUTE),
        "capture_audio_update_invalid_goal_state");
    finish_capture_audio_goal(validation_result, GOAL_STATE_ABORTED);
    return;
  }
  start_capture_audio_goal(goal_handle, capture_audio_goal_request);
}

void poll_capture_audio_result_request() {
  rmw_request_id_t request_header;
  rcl_ret_t take_result = rcl_action_take_result_request(
      &capture_audio_action_server,
      &request_header,
      &capture_audio_result_request);
  if (take_result == RCL_RET_ACTION_SERVER_TAKE_FAILED) {
    reset_rcl_error();
    return;
  }
  if (take_result != RCL_RET_OK) {
    rcl_ok(take_result, "capture_audio_take_result_request");
    return;
  }
  capture_audio_result_request_header = request_header;
  capture_audio_result_request_pending = true;
  send_capture_audio_result_if_ready();
}

void poll_capture_audio_action_server() {
  if (!capture_audio_action_server_initialized) {
    return;
  }
  poll_capture_audio_goal_request();
  poll_capture_audio_result_request();
  step_capture_audio_session();
}

void reset_play_audio_speaker_buffers() {
  play_audio_buffer_index = 0;
  play_audio_buffer_fill_samples = 0;
  play_audio_last_speaker_frame_ms = 0;
  play_audio_speaker_frames_queued = 0;
  play_audio_speaker_frames_failed = 0;
  play_audio_loaded_direct_playback_ms = 0;
}

stackchan::Result prepare_play_audio_speaker() {
  if (M5.Mic.isRecording()) {
    recover_capture_mic_after_abort("playback_prepare_mic_busy");
    return stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "microphone capture did not stop before playback",
        true);
  }
  M5.Mic.end();
  if (!M5.Speaker.begin()) {
    return stackchan::Result::rejected(
        "UNSUPPORTED_FEATURE",
        "speaker begin failed",
        false);
  }
  M5.Speaker.setVolume(kAudioPlaybackSpeakerVolume);
  play_audio_speaker_session_active = true;
  return stackchan::Result::accepted("speaker ready for playback");
}

void release_play_audio_speaker(bool stop_playback) {
  if (!play_audio_speaker_session_active) {
    return;
  }
  if (stop_playback) {
    M5.Speaker.stop(0);
  }
  M5.Speaker.end();
  if (stackchan_audio_capture_initialized) {
    M5.Mic.begin();
  }
  play_audio_speaker_session_active = false;
}

bool play_audio_speaker_queue_has_room() {
  return M5.Speaker.isPlaying(0) < 2;
}

bool queue_play_audio_speaker_frame(
    const char* command_id,
    uint32_t sequence,
    bool partial_frame) {
  if (play_audio_buffer_fill_samples == 0) {
    return true;
  }
  if (!play_audio_speaker_queue_has_room()) {
    if (!play_audio_speaker_queue_full_logged) {
      log_play_audio_chunk_diagnostic(
          "speaker_queue_full",
          command_id,
          sequence,
          static_cast<uint32_t>(play_audio_buffer_fill_samples * 2),
          "OK");
      play_audio_speaker_queue_full_logged = true;
    }
    return true;
  }
  int16_t* samples = play_audio_buffers[play_audio_buffer_index];
  const size_t sample_count = play_audio_buffer_fill_samples;
  if (!M5.Speaker.playRaw(
          samples,
          sample_count,
          stackchan::kAudioSampleRate,
          false,
          1,
          0,
          false)) {
    ++play_audio_speaker_frames_failed;
    log_play_audio_chunk_diagnostic(
        "speaker_frame_failed",
        command_id,
        sequence,
        static_cast<uint32_t>(sample_count * 2),
        "AUDIO_UNDERRUN");
    return false;
  }
  ++play_audio_speaker_frames_queued;
  play_audio_last_speaker_frame_ms = millis();
  play_audio_speaker_queue_full_logged = false;
  if (play_audio_speaker_frames_queued == 1 || partial_frame) {
    log_play_audio_chunk_diagnostic(
        partial_frame ? "speaker_partial_frame_queued" : "speaker_frame_queued",
        command_id,
        sequence,
        static_cast<uint32_t>(sample_count * 2),
        "OK");
  }
  play_audio_buffer_index =
      (play_audio_buffer_index + 1) %
      (sizeof(play_audio_buffers) / sizeof(play_audio_buffers[0]));
  play_audio_buffer_fill_samples = 0;
  return true;
}

bool queue_loaded_play_audio_buffer(const char* command_id) {
  if (play_audio_loaded_total_bytes == 0 ||
      play_audio_loaded_total_bytes % 2 != 0) {
    log_play_audio_chunk_diagnostic(
        "loaded_playback_queue_failed",
        command_id,
        play_audio_next_pull_sequence,
        play_audio_loaded_total_bytes,
        "MALFORMED_AUDIO_CHUNK");
    return false;
  }
  const size_t sample_count = play_audio_loaded_total_bytes / 2;
  auto* samples = reinterpret_cast<int16_t*>(play_audio_loaded_buffer);
  if (!M5.Speaker.playRaw(
          samples,
          sample_count,
          stackchan::kAudioSampleRate,
          false,
          1,
          0,
          false)) {
    ++play_audio_speaker_frames_failed;
    log_play_audio_chunk_diagnostic(
        "loaded_playback_queue_failed",
        command_id,
        play_audio_next_pull_sequence,
        play_audio_loaded_total_bytes,
        "AUDIO_UNDERRUN");
    return false;
  }
  play_audio_speaker_frames_queued =
      (play_audio_loaded_total_bytes + kAudioPlaybackSpeakerFrameBytes - 1) /
      kAudioPlaybackSpeakerFrameBytes;
  play_audio_last_speaker_frame_ms = millis();
  play_audio_loaded_direct_playback_ms =
      static_cast<uint32_t>((sample_count * 1000ULL) / stackchan::kAudioSampleRate);
  log_play_audio_chunk_diagnostic(
      "loaded_playback_queued",
      command_id,
      play_audio_next_pull_sequence,
      play_audio_loaded_total_bytes,
      "OK");
  return true;
}

bool append_play_audio_pcm_to_speaker_frames(
    const char* command_id,
    uint32_t sequence,
    const uint8_t* pcm_data,
    size_t pcm_size) {
  size_t sample_offset = 0;
  const size_t sample_count = pcm_size / 2;
  while (sample_offset < sample_count) {
    const size_t frame_space =
        kAudioPlaybackSpeakerFrameSamples - play_audio_buffer_fill_samples;
    const size_t samples_to_copy =
        (sample_count - sample_offset) < frame_space
            ? (sample_count - sample_offset)
            : frame_space;
    int16_t* frame = play_audio_buffers[play_audio_buffer_index];
    for (size_t index = 0; index < samples_to_copy; ++index) {
      const size_t pcm_index = (sample_offset + index) * 2;
      frame[play_audio_buffer_fill_samples + index] = static_cast<int16_t>(
          static_cast<uint16_t>(pcm_data[pcm_index]) |
          (static_cast<uint16_t>(pcm_data[pcm_index + 1]) << 8));
    }
    sample_offset += samples_to_copy;
    play_audio_buffer_fill_samples += samples_to_copy;
    if (play_audio_buffer_fill_samples >= kAudioPlaybackSpeakerFrameSamples &&
        !queue_play_audio_speaker_frame(command_id, sequence, false)) {
      return false;
    }
    if (play_audio_buffer_fill_samples >= kAudioPlaybackSpeakerFrameSamples &&
        sample_offset < sample_count) {
      log_play_audio_chunk_diagnostic(
          "speaker_frame_backpressure",
          command_id,
          sequence,
          static_cast<uint32_t>(play_audio_buffer_fill_samples * 2),
          "AUDIO_UNDERRUN");
      return false;
    }
  }
  return true;
}

stackchan::Result validate_play_audio_chunk_shape(
    const stackchan::AudioPlaybackChunk& chunk,
    const uint8_t* pcm_data) {
  if (!audio_playback_guard.active()) {
    return stackchan::Result::rejected(
        "UNKNOWN_COMMAND",
        "audio playback chunk arrived without an accepted session",
        true);
  }
  if (chunk.command_id == nullptr ||
      strcmp(chunk.command_id, play_audio_diagnostic_command_id) != 0) {
    return stackchan::Result::rejected(
        "UNKNOWN_COMMAND",
        "audio playback chunk command_id does not match active session",
        true);
  }
  if (chunk.direction != stackchan::AudioDirection::Playback) {
    return stackchan::Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "audio playback chunk has wrong direction",
        true);
  }
  if (chunk.format != stackchan::AudioFormat::PcmS16Le ||
      chunk.sample_rate != stackchan::kAudioSampleRate ||
      chunk.channels != stackchan::kAudioChannels) {
    return stackchan::Result::rejected(
        "UNSUPPORTED_FEATURE",
        "audio playback chunk format is unsupported",
        false);
  }
  if (pcm_data == nullptr ||
      chunk.pcm_size == 0 ||
      chunk.pcm_size % 2 != 0 ||
      chunk.pcm_size > stackchan::kAudioMaxChunkBytes) {
    return stackchan::Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "audio playback chunk byte length is invalid",
        true);
  }
  return stackchan::Result::accepted("audio playback chunk shape accepted");
}

bool buffer_play_audio_pending_chunk(
    const char* command_id,
    uint32_t sequence,
    uint8_t format,
    uint32_t sample_rate,
    uint8_t channels,
    const uint8_t* pcm_data,
    size_t pcm_size) {
  if (find_play_audio_pending_chunk(sequence) >= 0) {
    log_play_audio_chunk_diagnostic(
        "chunk_jitter_duplicate_ignored",
        command_id,
        sequence,
        static_cast<uint32_t>(pcm_size),
        "OK");
    return true;
  }
  if (pcm_size > kAudioPlaybackPendingChunkBytes) {
    log_play_audio_chunk_diagnostic(
        "chunk_jitter_chunk_too_large",
        command_id,
        sequence,
        static_cast<uint32_t>(pcm_size),
        "AUDIO_UNDERRUN");
    return false;
  }
  if (sequence >= play_audio_next_pull_sequence + kAudioPlaybackPendingChunkSlots) {
    log_play_audio_chunk_diagnostic(
        "chunk_jitter_window_exceeded",
        command_id,
        sequence,
        static_cast<uint32_t>(pcm_size),
        "AUDIO_UNDERRUN");
    return false;
  }
  PlayAudioPendingChunk* slot = nullptr;
  for (auto& chunk : play_audio_pending_chunks) {
    if (!chunk.occupied) {
      slot = &chunk;
      break;
    }
  }
  if (slot == nullptr) {
    log_play_audio_chunk_diagnostic(
        "chunk_jitter_full",
        command_id,
        sequence,
        static_cast<uint32_t>(pcm_size),
        "AUDIO_UNDERRUN");
    return false;
  }
  slot->occupied = true;
  slot->sequence = sequence;
  slot->format = format;
  slot->sample_rate = sample_rate;
  slot->channels = channels;
  slot->pcm_size = static_cast<uint16_t>(pcm_size);
  slot->received_ms = millis();
  copy_bounded(slot->command_id, sizeof(slot->command_id), command_id);
  memcpy(slot->pcm, pcm_data, pcm_size);
  ++play_audio_pending_chunk_count;
  if (play_audio_pending_gap_started_ms == 0) {
    play_audio_pending_gap_started_ms = slot->received_ms;
  }
  play_audio_last_chunk_ms = slot->received_ms;
  log_play_audio_chunk_diagnostic(
      "chunk_buffered_out_of_order",
      command_id,
      sequence,
      static_cast<uint32_t>(pcm_size),
      "OK");
  return true;
}

bool process_play_audio_pcm_chunk_in_order(
    const char* chunk_command_id,
    uint32_t sequence,
    uint8_t format,
    uint32_t sample_rate,
    uint8_t channels,
    const uint8_t* pcm_data,
    size_t pcm_size) {
  stackchan::AudioPlaybackChunk playback_chunk{
      chunk_command_id,
      stackchan::AudioDirection::Playback,
      static_cast<stackchan::AudioFormat>(format),
      sample_rate,
      channels,
      sequence,
      static_cast<uint16_t>(pcm_size),
  };
  const stackchan::Result validation_result =
      audio_playback_guard.validate_chunk(playback_chunk);
  if (!validation_result.ok) {
    ++play_audio_chunks_rejected;
    log_play_audio_chunk_diagnostic(
        "chunk_rejected",
        chunk_command_id,
        sequence,
        static_cast<uint32_t>(pcm_size),
        validation_result.error_code);
    if (strcmp(validation_result.error_code, "AUDIO_UNDERRUN") == 0) {
      stackchan::publish_audio_underrun_event(
          event_publisher,
          millis(),
          chunk_command_id);
    }
    finish_play_audio_goal(validation_result, GOAL_STATE_ABORTED);
    return false;
  }
  if (!append_play_audio_pcm_to_speaker_frames(
          chunk_command_id,
          sequence,
          pcm_data,
          pcm_size)) {
    ++play_audio_chunks_rejected;
    log_play_audio_chunk_diagnostic(
        "speaker_frame_append_failed",
        chunk_command_id,
        sequence,
        static_cast<uint32_t>(pcm_size),
        "AUDIO_UNDERRUN");
    finish_play_audio_goal(stackchan::audio_underrun(), GOAL_STATE_ABORTED);
    return false;
  }
  ++play_audio_chunks_accepted;
  if (play_audio_chunks_accepted == 1) {
    log_play_audio_chunk_diagnostic(
        "chunk_accepted",
        chunk_command_id,
        sequence,
        static_cast<uint32_t>(pcm_size),
        "OK");
  }
  play_audio_received_chunk = true;
  play_audio_last_chunk_ms = millis();
  if (sequence >= play_audio_next_pull_sequence) {
    play_audio_next_pull_sequence = sequence + 1;
    refresh_play_audio_pending_gap_timer(millis());
  }
  return true;
}

bool drain_play_audio_pending_chunks() {
  while (play_audio_pending_chunk_count > 0) {
    const int pending_index =
        find_play_audio_pending_chunk(play_audio_next_pull_sequence);
    if (pending_index < 0) {
      return true;
    }
    PlayAudioPendingChunk& pending = play_audio_pending_chunks[pending_index];
    const uint32_t drained_sequence = pending.sequence;
    if (!process_play_audio_pcm_chunk_in_order(
            pending.command_id,
            pending.sequence,
            pending.format,
            pending.sample_rate,
            pending.channels,
            pending.pcm,
            pending.pcm_size)) {
      return false;
    }
    pending.occupied = false;
    pending.pcm_size = 0;
    pending.command_id[0] = '\0';
    --play_audio_pending_chunk_count;
    refresh_play_audio_pending_gap_timer(millis());
    log_play_audio_chunk_diagnostic(
        "chunk_jitter_drained",
        play_audio_diagnostic_command_id,
        drained_sequence,
        0,
        "OK");
  }
  return true;
}

bool play_audio_goal_valid(
    const stackchan_msgs__action__PlayAudio_Goal& goal,
    stackchan::Result* result) {
  const char* goal_device_id =
      goal.meta.device_id.data != nullptr ? goal.meta.device_id.data : "";
  const char* goal_format = goal.format.data != nullptr ? goal.format.data : "";
  if (strcmp(goal_device_id, STACKCHAN_DEVICE_ID) != 0) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "UNKNOWN_COMMAND",
          "audio playback goal device_id mismatch",
          true);
    }
    return false;
  }
  if (!stackchan_audio_playback_initialized) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "UNSUPPORTED_FEATURE",
          "speaker is not available",
          false);
    }
    return false;
  }
  if (strcmp(goal_format, "pcm_s16le") != 0 ||
      goal.sample_rate != stackchan::kAudioSampleRate ||
      goal.channels != stackchan::kAudioChannels) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "UNSUPPORTED_FEATURE",
          "audio playback goal format is unsupported",
          false);
    }
    return false;
  }
  if (goal.first_chunk_present &&
      (goal.first_chunk_sequence != 0 ||
       goal.first_chunk_pcm.size == 0 ||
       goal.first_chunk_pcm.size % 2 != 0 ||
       goal.first_chunk_pcm.size > stackchan::kAudioMaxChunkBytes)) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "MALFORMED_AUDIO_CHUNK",
          "audio playback first chunk is invalid",
          true);
    }
    return false;
  }
  if (audio_playback_guard.active()) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "FIRMWARE_BUSY",
          "audio playback already active",
          true);
    }
    return false;
  }
  if (audio_capture_session_active) {
    if (result != nullptr) {
      *result = stackchan::Result::rejected(
          "FIRMWARE_BUSY",
          "audio capture already active",
          true);
    }
    return false;
  }
  if (result != nullptr) {
    *result = stackchan::Result::accepted("audio playback goal accepted");
  }
  return true;
}

void finish_play_audio_goal(const stackchan::Result& result, int8_t action_status) {
  log_play_audio_session_diagnostic(
      result.ok ? "goal_succeeded" : "goal_failed",
      result);
  if (play_audio_goal_active && play_audio_active_goal_handle != nullptr) {
    rcl_ok(
        rcl_action_update_goal_state(
            play_audio_active_goal_handle,
            result.ok ? GOAL_EVENT_SUCCEED : GOAL_EVENT_ABORT),
        "play_audio_update_terminal_goal_state");
    rcl_ok(
        rcl_action_notify_goal_done(&play_audio_action_server),
        "play_audio_notify_goal_done");
  }
  play_audio_terminal_goal_info = play_audio_active_goal_info;
  play_audio_terminal_result = result;
  play_audio_terminal_status = action_status;
  play_audio_result_ready = true;
  log_play_audio_action_diagnostic(
      "result_ready",
      play_audio_diagnostic_command_id,
      result.ok,
      false,
      0);
  remember_play_audio_terminal_stale_suppression();
  play_audio_goal_active = false;
  play_audio_active_goal_handle = nullptr;
  play_audio_received_chunk = false;
  play_audio_end_of_stream_seen = false;
  play_audio_chunk_request_pending = false;
  play_audio_buffer_fill_samples = 0;
  release_play_audio_speaker(!result.ok || M5.Speaker.isPlaying(0) != 0);
  if (play_audio_loaded_playing) {
    reset_play_audio_loaded_buffer();
  }
  reset_play_audio_pending_chunks();
  audio_playback_guard.finish_session();
}

void send_play_audio_result_if_ready() {
  if (!play_audio_result_ready || !play_audio_result_request_pending) {
    return;
  }
  if (!goal_id_matches(
          play_audio_result_request.goal_id,
          play_audio_terminal_goal_info.goal_id)) {
    log_play_audio_action_diagnostic(
        "result_request_goal_mismatch",
        play_audio_diagnostic_command_id,
        false,
        false,
        0);
    return;
  }
  play_audio_result_response.status = play_audio_terminal_status;
  if (!convert_command_result(
          play_audio_terminal_result,
          &play_audio_result_response.result.result)) {
    stackchan_diag_println("stackchan micro_ros_step=play_audio_result_assign result=false");
    log_play_audio_action_diagnostic(
        "result_assign_failed",
        play_audio_diagnostic_command_id,
        false,
        false,
        0);
    return;
  }
  const rcl_ret_t send_result = rcl_action_send_result_response(
      &play_audio_action_server,
      &play_audio_result_request_header,
      &play_audio_result_response);
  if (rcl_ok(send_result, "play_audio_send_result_response")) {
    log_play_audio_action_diagnostic(
        "result_response_sent",
        play_audio_diagnostic_command_id,
        play_audio_terminal_result.ok,
        false,
        0);
    play_audio_result_request_pending = false;
    play_audio_result_ready = false;
  } else {
    log_play_audio_action_diagnostic(
        "result_response_failed",
        play_audio_diagnostic_command_id,
        false,
        false,
        0);
  }
}

void request_next_play_audio_chunk() {
  if (!play_audio_goal_active ||
      !play_audio_chunk_client_initialized ||
      play_audio_chunk_request_pending) {
    return;
  }
  if (play_audio_buffer_fill_samples >= kAudioPlaybackSpeakerFrameSamples) {
    if (!queue_play_audio_speaker_frame(
            play_audio_diagnostic_command_id,
            play_audio_next_pull_sequence,
            false) ||
        play_audio_buffer_fill_samples >= kAudioPlaybackSpeakerFrameSamples) {
      return;
    }
  }
  const uint32_t now_ms = millis();
  const bool waiting_for_gap = play_audio_pending_chunk_count > 0;
  publish_play_audio_ack_window(waiting_for_gap);
  if (!waiting_for_gap &&
      play_audio_received_chunk &&
      !play_audio_end_of_stream_seen &&
      now_ms - play_audio_last_chunk_ms < kAudioPlaybackPullFallbackIdleMs) {
    return;
  }
  if (play_audio_last_pull_request_ms != 0 &&
      now_ms - play_audio_last_pull_request_ms < kAudioPlaybackPullIntervalMs) {
    return;
  }
  assign_ros_string(&audio_playback_chunk_request.meta.device_id, STACKCHAN_DEVICE_ID);
  assign_ros_string(
      &audio_playback_chunk_request.meta.command_id,
      play_audio_diagnostic_command_id);
  assign_ros_string(&audio_playback_chunk_request.meta.source, "firmware");
  audio_playback_chunk_request.meta.created_at.sec = now_ms / 1000;
  audio_playback_chunk_request.meta.created_at.nanosec =
      (now_ms % 1000) * 1000000;
  audio_playback_chunk_request.meta.priority =
      static_cast<uint8_t>(stackchan::Priority::Normal);
  audio_playback_chunk_request.next_sequence = play_audio_next_pull_sequence;
  audio_playback_chunk_request.has_acknowledgement =
      play_audio_next_pull_sequence > 0;
  audio_playback_chunk_request.acknowledged_sequence =
      play_audio_next_pull_sequence > 0 ? play_audio_next_pull_sequence - 1 : 0;
  audio_playback_chunk_request.has_missing_sequence = waiting_for_gap;
  audio_playback_chunk_request.missing_sequence = play_audio_next_pull_sequence;
  audio_playback_chunk_request.free_buffer_chunks =
      play_audio_free_pending_chunk_slots();
  const rcl_ret_t send_result = rcl_send_request(
      &audio_playback_chunk_client,
      &audio_playback_chunk_request,
      &play_audio_chunk_request_sequence_number);
  if (send_result == RCL_RET_OK) {
    play_audio_chunk_request_pending = true;
    play_audio_last_pull_request_ms = now_ms;
    log_play_audio_chunk_diagnostic(
        "pull_requested",
        play_audio_diagnostic_command_id,
        play_audio_next_pull_sequence,
        0,
        "OK");
    return;
  }
  reset_rcl_error();
  log_play_audio_chunk_diagnostic(
      "pull_request_failed",
      play_audio_diagnostic_command_id,
      play_audio_next_pull_sequence,
      0,
      "TRANSPORT_DISCONNECTED");
}

void clear_stale_play_audio_chunk_request() {
  if (!play_audio_chunk_request_pending) {
    return;
  }
  const uint32_t now_ms = millis();
  if (now_ms - play_audio_last_pull_request_ms < kAudioPlaybackPullTimeoutMs) {
    return;
  }
  play_audio_chunk_request_pending = false;
  log_play_audio_chunk_diagnostic(
      "pull_response_timeout",
      play_audio_diagnostic_command_id,
      play_audio_next_pull_sequence,
      0,
      "TIMEOUT");
}

void step_loaded_play_audio_playback() {
  if (!play_audio_goal_active || !play_audio_loaded_playing) {
    return;
  }
  if (!play_audio_speaker_queue_has_room()) {
    return;
  }
  const uint32_t remaining =
      play_audio_loaded_total_bytes - play_audio_loaded_play_offset;
  if (remaining == 0) {
    play_audio_end_of_stream_seen = true;
    return;
  }
  const uint32_t bytes_to_append =
      remaining < kAudioPlaybackSpeakerFrameBytes
          ? remaining
          : kAudioPlaybackSpeakerFrameBytes;
  if (!append_play_audio_pcm_to_speaker_frames(
          play_audio_diagnostic_command_id,
          play_audio_next_pull_sequence,
          play_audio_loaded_buffer + play_audio_loaded_play_offset,
          bytes_to_append)) {
    finish_play_audio_goal(stackchan::audio_underrun(), GOAL_STATE_ABORTED);
    return;
  }
  play_audio_loaded_play_offset += bytes_to_append;
  play_audio_received_chunk = true;
  play_audio_last_chunk_ms = millis();
  ++play_audio_chunks_seen;
  ++play_audio_chunks_accepted;
  ++play_audio_next_pull_sequence;
  if (play_audio_loaded_play_offset >= play_audio_loaded_total_bytes) {
    play_audio_end_of_stream_seen = true;
    log_play_audio_chunk_diagnostic(
        "loaded_playback_drained",
        play_audio_diagnostic_command_id,
        play_audio_next_pull_sequence,
        play_audio_loaded_total_bytes,
        "OK");
  }
}

void maybe_finish_play_audio_session() {
  if (!play_audio_goal_active) {
    send_play_audio_result_if_ready();
    return;
  }
  const uint32_t now_ms = millis();
  step_loaded_play_audio_playback();
  if (!play_audio_goal_active) {
    send_play_audio_result_if_ready();
    return;
  }
  clear_stale_play_audio_chunk_request();
  if (play_audio_received_chunk &&
      !play_audio_end_of_stream_seen &&
      now_ms - play_audio_last_chunk_ms >= kAudioPlaybackInterChunkTimeoutMs) {
    log_play_audio_session_diagnostic(
        "inter_chunk_timeout",
        stackchan::audio_underrun());
    finish_play_audio_goal(stackchan::audio_underrun(), GOAL_STATE_ABORTED);
    send_play_audio_result_if_ready();
    return;
  }
  if (!play_audio_loaded_playing) {
    if (play_audio_chunk_request_pending && play_audio_pending_chunk_count > 0) {
      publish_play_audio_ack_window(true);
    }
    request_next_play_audio_chunk();
  }
  if (play_audio_pending_chunk_count > 0 &&
      play_audio_pending_gap_started_ms != 0 &&
      now_ms - play_audio_pending_gap_started_ms >=
          kAudioPlaybackPendingGapTimeoutMs) {
    log_play_audio_chunk_diagnostic(
        "chunk_jitter_gap_timeout",
        play_audio_diagnostic_command_id,
        play_audio_next_pull_sequence,
        0,
        "AUDIO_UNDERRUN");
    stackchan::publish_audio_underrun_event(
        event_publisher,
        now_ms,
        play_audio_diagnostic_command_id);
    finish_play_audio_goal(stackchan::audio_underrun(), GOAL_STATE_ABORTED);
  } else if (play_audio_pending_chunk_count > 0) {
    send_play_audio_result_if_ready();
    return;
  } else if (!play_audio_received_chunk &&
      now_ms - play_audio_started_ms >= kAudioPlaybackNoChunkTimeoutMs) {
    log_play_audio_session_diagnostic(
        "no_chunk_timeout",
        stackchan::audio_underrun());
    finish_play_audio_goal(stackchan::audio_underrun(), GOAL_STATE_ABORTED);
  } else if (play_audio_received_chunk &&
             play_audio_end_of_stream_seen &&
             play_audio_buffer_fill_samples > 0 &&
             !queue_play_audio_speaker_frame(
                 play_audio_diagnostic_command_id,
                 play_audio_next_pull_sequence,
                 true)) {
    finish_play_audio_goal(stackchan::audio_underrun(), GOAL_STATE_ABORTED);
  } else if (play_audio_received_chunk &&
             play_audio_end_of_stream_seen &&
             play_audio_buffer_fill_samples > 0) {
    send_play_audio_result_if_ready();
    return;
  } else if (play_audio_received_chunk &&
             play_audio_end_of_stream_seen &&
             now_ms - play_audio_last_chunk_ms >= kAudioPlaybackDrainTimeoutMs) {
    const bool speaker_playing = M5.Speaker.isPlaying(0) != 0;
    const uint32_t speaker_drain_budget_ms =
        kAudioPlaybackMaxSpeakerDrainMs + play_audio_loaded_direct_playback_ms;
    const bool speaker_drain_timed_out =
        speaker_playing &&
        play_audio_last_speaker_frame_ms != 0 &&
        now_ms - play_audio_last_speaker_frame_ms >= speaker_drain_budget_ms;
    if (speaker_drain_timed_out) {
      log_play_audio_chunk_diagnostic(
          "speaker_drain_fallback",
          play_audio_diagnostic_command_id,
          play_audio_next_pull_sequence,
          0,
          "OK");
    }
    if (speaker_playing && !speaker_drain_timed_out) {
      send_play_audio_result_if_ready();
      return;
    }
    finish_play_audio_goal(audio_playback_completed_result(), GOAL_STATE_SUCCEEDED);
  }
  send_play_audio_result_if_ready();
}

void start_play_audio_goal(
    rcl_action_goal_handle_t* goal_handle,
    const stackchan_msgs__action__PlayAudio_SendGoal_Request& request) {
  play_audio_active_goal_handle = goal_handle;
  copy_goal_info_from_request(&play_audio_active_goal_info, request);
  play_audio_goal_active = true;
  rcl_ok(
      rcl_action_update_goal_state(play_audio_active_goal_handle, GOAL_EVENT_EXECUTE),
      "play_audio_update_execute_goal_state");
  const char* command_id =
      request.goal.meta.command_id.data != nullptr
          ? request.goal.meta.command_id.data
          : "";
  clear_play_audio_terminal_stale_suppression();
  reset_play_audio_diagnostics(command_id);
  const stackchan::Result start_result =
      audio_playback_guard.start_session(command_id);
  if (!start_result.ok) {
    log_play_audio_session_diagnostic("goal_start_failed", start_result);
    finish_play_audio_goal(start_result, GOAL_STATE_ABORTED);
    return;
  }
  reset_play_audio_speaker_buffers();
  reset_play_audio_pending_chunks();
  const stackchan::Result speaker_result = prepare_play_audio_speaker();
  if (!speaker_result.ok) {
    log_play_audio_session_diagnostic("speaker_start_failed", speaker_result);
    finish_play_audio_goal(speaker_result, GOAL_STATE_ABORTED);
    return;
  }
  log_play_audio_session_diagnostic("goal_active", start_result);
  log_play_audio_action_diagnostic(
      "goal_execute",
      command_id,
      true,
      request.goal.first_chunk_present,
      request.goal.first_chunk_present
          ? static_cast<uint32_t>(request.goal.first_chunk_pcm.size)
          : 0);
  copy_bounded(
      last_command_id,
      sizeof(last_command_id),
      command_id);
  play_audio_received_chunk = false;
  play_audio_end_of_stream_seen = false;
  play_audio_chunk_request_pending = false;
  play_audio_chunk_request_sequence_number = 0;
  play_audio_next_pull_sequence = 0;
  play_audio_last_pull_request_ms = 0;
  play_audio_last_ack_publish_ms = 0;
  play_audio_started_ms = millis();
  play_audio_last_chunk_ms = play_audio_started_ms;
  const bool use_loaded_playback =
      !request.goal.first_chunk_present &&
      play_audio_loaded_complete &&
      strcmp(play_audio_loaded_command_id, command_id) == 0;
  if (!use_loaded_playback &&
      (play_audio_loaded_complete ||
       play_audio_loaded_expected_sequence != 0 ||
       play_audio_loaded_total_bytes != 0)) {
    reset_play_audio_loaded_buffer();
  }
  if (use_loaded_playback) {
    play_audio_loaded_playing = true;
    play_audio_loaded_play_offset = play_audio_loaded_total_bytes;
    play_audio_received_chunk = true;
    play_audio_end_of_stream_seen = true;
    play_audio_last_chunk_ms = millis();
    play_audio_chunks_seen = play_audio_loaded_total_chunks;
    play_audio_chunks_accepted = play_audio_loaded_total_chunks;
    play_audio_next_pull_sequence = play_audio_loaded_total_chunks;
    log_play_audio_chunk_diagnostic(
        "loaded_playback_started",
        command_id,
        0,
        play_audio_loaded_total_bytes,
        "OK");
    if (!queue_loaded_play_audio_buffer(command_id)) {
      finish_play_audio_goal(stackchan::audio_underrun(), GOAL_STATE_ABORTED);
      return;
    }
    log_play_audio_chunk_diagnostic(
        "loaded_playback_drained",
        command_id,
        play_audio_next_pull_sequence,
        play_audio_loaded_total_bytes,
        "OK");
  } else if (request.goal.first_chunk_present) {
    log_play_audio_action_diagnostic(
        "first_goal_chunk_dispatch",
        command_id,
        true,
        true,
        static_cast<uint32_t>(request.goal.first_chunk_pcm.size));
    accept_play_audio_pcm_chunk(
        command_id,
        request.goal.first_chunk_sequence,
        stackchan_msgs__msg__AudioChunk__PCM_S16LE,
        request.goal.sample_rate,
        request.goal.channels,
        request.goal.first_chunk_pcm.data,
        request.goal.first_chunk_pcm.size);
  }
  publish_status_heartbeat();
}

void poll_play_audio_goal_request() {
  rmw_request_id_t request_header;
  rcl_ret_t take_result = rcl_action_take_goal_request(
      &play_audio_action_server,
      &request_header,
      &play_audio_goal_request);
  if (take_result == RCL_RET_ACTION_SERVER_TAKE_FAILED) {
    reset_rcl_error();
    return;
  }
  if (take_result != RCL_RET_OK) {
    rcl_ok(take_result, "play_audio_take_goal_request");
    return;
  }

  rcl_action_goal_info_t goal_info =
      rcl_action_get_zero_initialized_goal_info();
  copy_goal_info_from_request(&goal_info, play_audio_goal_request);
  const char* command_id =
      play_audio_goal_request.goal.meta.command_id.data != nullptr
          ? play_audio_goal_request.goal.meta.command_id.data
          : "";
  log_play_audio_action_diagnostic(
      "goal_request_taken",
      command_id,
      false,
      play_audio_goal_request.goal.first_chunk_present,
      play_audio_goal_request.goal.first_chunk_present
          ? static_cast<uint32_t>(play_audio_goal_request.goal.first_chunk_pcm.size)
          : 0);
  if (audio_playback_guard.active()) {
    play_audio_goal_response.accepted = false;
    play_audio_goal_response.stamp = goal_info.stamp;
    const rcl_ret_t send_result = rcl_action_send_goal_response(
        &play_audio_action_server,
        &request_header,
        &play_audio_goal_response);
    rcl_ok(send_result, "play_audio_send_busy_goal_response");
    log_play_audio_action_diagnostic(
        "goal_response_busy",
        command_id,
        false,
        play_audio_goal_request.goal.first_chunk_present,
        play_audio_goal_request.goal.first_chunk_present
            ? static_cast<uint32_t>(play_audio_goal_request.goal.first_chunk_pcm.size)
            : 0);
    return;
  }
  rcl_action_goal_handle_t* goal_handle =
      rcl_action_accept_new_goal(&play_audio_action_server, &goal_info);
  play_audio_goal_response.accepted = goal_handle != nullptr;
  play_audio_goal_response.stamp = goal_info.stamp;
  const rcl_ret_t send_result = rcl_action_send_goal_response(
      &play_audio_action_server,
      &request_header,
      &play_audio_goal_response);
  rcl_ok(send_result, "play_audio_send_goal_response");
  log_play_audio_action_diagnostic(
      "goal_response_sent",
      command_id,
      play_audio_goal_response.accepted,
      play_audio_goal_request.goal.first_chunk_present,
      play_audio_goal_request.goal.first_chunk_present
          ? static_cast<uint32_t>(play_audio_goal_request.goal.first_chunk_pcm.size)
          : 0);
  if (goal_handle == nullptr) {
    reset_rcl_error();
    return;
  }

  stackchan::Result validation_result;
  if (!play_audio_goal_valid(play_audio_goal_request.goal, &validation_result)) {
    play_audio_active_goal_handle = goal_handle;
    copy_goal_info_from_request(&play_audio_active_goal_info, play_audio_goal_request);
    play_audio_goal_active = true;
    reset_play_audio_diagnostics(
        play_audio_goal_request.goal.meta.command_id.data != nullptr
            ? play_audio_goal_request.goal.meta.command_id.data
            : "");
    log_play_audio_session_diagnostic("invalid_goal", validation_result);
    rcl_ok(
        rcl_action_update_goal_state(play_audio_active_goal_handle, GOAL_EVENT_EXECUTE),
        "play_audio_update_invalid_goal_state");
    finish_play_audio_goal(validation_result, GOAL_STATE_ABORTED);
    return;
  }
  start_play_audio_goal(goal_handle, play_audio_goal_request);
}

void poll_play_audio_result_request() {
  rmw_request_id_t request_header;
  rcl_ret_t take_result = rcl_action_take_result_request(
      &play_audio_action_server,
      &request_header,
      &play_audio_result_request);
  if (take_result == RCL_RET_ACTION_SERVER_TAKE_FAILED) {
    reset_rcl_error();
    return;
  }
  if (take_result != RCL_RET_OK) {
    rcl_ok(take_result, "play_audio_take_result_request");
    return;
  }
  play_audio_result_request_header = request_header;
  play_audio_result_request_pending = true;
  log_play_audio_action_diagnostic(
      "result_request_taken",
      play_audio_diagnostic_command_id,
      true,
      false,
      0);
  send_play_audio_result_if_ready();
}

void poll_play_audio_action_server() {
  if (!play_audio_action_server_initialized) {
    return;
  }
  poll_play_audio_goal_request();
  poll_play_audio_result_request();
  maybe_finish_play_audio_session();
}

void accept_play_audio_pcm_chunk(
    const char* chunk_command_id,
    uint32_t sequence,
    uint8_t format,
    uint32_t sample_rate,
    uint8_t channels,
    const uint8_t* pcm_data,
    size_t pcm_size) {
  if (chunk_command_id == nullptr) {
    chunk_command_id = "";
  }
  ++play_audio_chunks_seen;
  stackchan::AudioPlaybackChunk playback_chunk{
      chunk_command_id,
      stackchan::AudioDirection::Playback,
      static_cast<stackchan::AudioFormat>(format),
      sample_rate,
      channels,
      sequence,
      static_cast<uint16_t>(pcm_size),
  };
  if (audio_playback_guard.duplicate_chunk(playback_chunk)) {
    log_play_audio_chunk_diagnostic(
        "chunk_duplicate_ignored",
        chunk_command_id,
        sequence,
        static_cast<uint32_t>(pcm_size),
        "OK");
    return;
  }
  const stackchan::Result shape_result =
      validate_play_audio_chunk_shape(playback_chunk, pcm_data);
  if (!shape_result.ok) {
    ++play_audio_chunks_rejected;
    log_play_audio_chunk_diagnostic(
        "chunk_rejected",
        chunk_command_id,
        sequence,
        static_cast<uint32_t>(pcm_size),
        shape_result.error_code);
    finish_play_audio_goal(shape_result, GOAL_STATE_ABORTED);
    return;
  }
  if (sequence > play_audio_next_pull_sequence) {
    if (!buffer_play_audio_pending_chunk(
            chunk_command_id,
            sequence,
            format,
            sample_rate,
            channels,
            pcm_data,
            pcm_size)) {
      ++play_audio_chunks_rejected;
      stackchan::publish_audio_underrun_event(
          event_publisher,
          millis(),
          chunk_command_id);
      finish_play_audio_goal(stackchan::audio_underrun(), GOAL_STATE_ABORTED);
    }
    return;
  }
  if (!process_play_audio_pcm_chunk_in_order(
          chunk_command_id,
          sequence,
          format,
          sample_rate,
          channels,
          pcm_data,
          pcm_size)) {
    return;
  }
  if (!drain_play_audio_pending_chunks()) {
    return;
  }
}

void handle_audio_chunk_subscription(const void* message) {
  if (message == nullptr) {
    return;
  }
  const auto* chunk = static_cast<const stackchan_msgs__msg__AudioChunk*>(message);
  if (chunk->direction != stackchan_msgs__msg__AudioChunk__PLAYBACK) {
    return;
  }
  if (is_loaded_audio_topic_chunk(chunk)) {
    handle_loaded_audio_topic_chunk(chunk);
    return;
  }
  const char* chunk_command_id =
      chunk->command_id.data != nullptr ? chunk->command_id.data : "";
  if (!play_audio_goal_active) {
    if (recent_terminal_play_audio_command(chunk_command_id)) {
      return;
    }
    log_play_audio_chunk_diagnostic(
        "chunk_without_active_goal",
        chunk_command_id,
        chunk->sequence,
        static_cast<uint32_t>(chunk->pcm.size),
        "UNKNOWN_COMMAND");
    return;
  }
  accept_play_audio_pcm_chunk(
      chunk_command_id,
      chunk->sequence,
      chunk->format,
      chunk->sample_rate,
      chunk->channels,
      chunk->pcm.data,
      chunk->pcm.size);
}

void handle_audio_playback_chunk_response(const void* response) {
  play_audio_chunk_request_pending = false;
  if (response == nullptr) {
    log_play_audio_chunk_diagnostic(
        "pull_response_null",
        play_audio_diagnostic_command_id,
        play_audio_next_pull_sequence,
        0,
        "TRANSPORT_DISCONNECTED");
    return;
  }
  if (!play_audio_goal_active) {
    if (recent_terminal_play_audio_command(play_audio_diagnostic_command_id)) {
      return;
    }
    log_play_audio_chunk_diagnostic(
        "pull_response_without_active_goal",
        play_audio_diagnostic_command_id,
        play_audio_next_pull_sequence,
        0,
        "UNKNOWN_COMMAND");
    return;
  }
  const auto* chunk_response =
      static_cast<const stackchan_msgs__srv__NextAudioChunk_Response*>(response);
  if (!chunk_response->result.ok) {
    const stackchan::Result result = result_from_ros(chunk_response->result);
    log_play_audio_chunk_diagnostic(
        "pull_response_rejected",
        play_audio_diagnostic_command_id,
        play_audio_next_pull_sequence,
        0,
        result.error_code);
    if (strcmp(result.error_code, "FIRMWARE_BUSY") != 0) {
      finish_play_audio_goal(result, GOAL_STATE_ABORTED);
    }
    return;
  }
  if (!chunk_response->has_chunk) {
    if (chunk_response->end_of_stream) {
      play_audio_end_of_stream_seen = true;
    }
    log_play_audio_chunk_diagnostic(
        chunk_response->end_of_stream ? "pull_end_of_stream" : "pull_empty",
        play_audio_diagnostic_command_id,
        play_audio_next_pull_sequence,
        0,
        "OK");
    return;
  }
  const auto* chunk = &chunk_response->chunk;
  accept_play_audio_pcm_chunk(
      chunk->command_id.data != nullptr ? chunk->command_id.data : "",
      chunk->sequence,
      chunk->format,
      chunk->sample_rate,
      chunk->channels,
      chunk->pcm.data,
      chunk->pcm.size);
}

bool play_audio_loaded_session_stale() {
  return !play_audio_loaded_complete &&
         !play_audio_loaded_playing &&
         play_audio_loaded_expected_sequence > 0 &&
         play_audio_loaded_last_write_ms != 0 &&
         millis() - play_audio_loaded_last_write_ms >= kAudioPlaybackInterChunkTimeoutMs;
}

stackchan::Result validate_loaded_audio_request(
    const stackchan_msgs__srv__LoadAudioChunk_Request* request) {
  if (request == nullptr) {
    return stackchan::Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "audio load request is null",
        true);
  }
  if (!request_matches_device_id(request->meta.device_id)) {
    return stackchan::Result::rejected(
        "INVALID_DEVICE_ID",
        "audio load request device_id mismatch",
        false);
  }
  if (play_audio_goal_active) {
    return stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "audio playback is already active",
        true);
  }
  const bool pcm_format =
      request->format == stackchan_msgs__msg__AudioChunk__PCM_S16LE;
  const bool adpcm_format =
      request->format == stackchan_msgs__msg__AudioChunk__IMA_ADPCM_4BIT;
  if ((!pcm_format && !adpcm_format) ||
      request->sample_rate != stackchan::kAudioSampleRate ||
      request->channels != stackchan::kAudioChannels) {
    return stackchan::Result::rejected(
        "UNSUPPORTED_FEATURE",
        "loaded audio format is unsupported",
        false);
  }
  if (request->pcm.size == 0 ||
      request->pcm.size > stackchan::kAudioMaxChunkBytes ||
      request->pcm.data == nullptr ||
      (pcm_format && request->pcm.size % 2 != 0)) {
    return stackchan::Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "loaded audio chunk byte length is invalid",
        true);
  }
  if (adpcm_format &&
      request->sequence == 0 &&
      request->pcm.size < stackchan::kImaAdpcmHeaderBytes) {
    return stackchan::Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "loaded ADPCM header is missing",
        true);
  }
  if (request->total_bytes == 0 ||
      request->total_bytes % 2 != 0 ||
      request->total_bytes > kAudioPlaybackLoadBufferBytes ||
      request->total_chunks == 0) {
    return stackchan::Result::rejected(
        "AUDIO_BUFFER_OVERFLOW",
        "loaded audio total size exceeds firmware buffer",
        false);
  }
  if ((play_audio_loaded_expected_sequence == 0 ||
       play_audio_loaded_complete ||
       play_audio_loaded_session_stale()) &&
      request->sequence == 0) {
    return stackchan::Result::accepted("loaded audio session started");
  }
  const char* command_id =
      request->meta.command_id.data != nullptr ? request->meta.command_id.data : "";
  if (!play_audio_loaded_complete &&
      strcmp(command_id, play_audio_loaded_command_id) != 0) {
    return stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "another audio load session is active",
        true);
  }
  if (request->format != play_audio_loaded_format) {
    return stackchan::Result::rejected(
        "UNSUPPORTED_FEATURE",
        "loaded audio format changed during active load",
        true);
  }
  if (request->sequence != play_audio_loaded_expected_sequence) {
    return stackchan::Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "loaded audio sequence is not contiguous",
        true);
  }
  return stackchan::Result::accepted("loaded audio chunk accepted");
}

bool is_loaded_audio_topic_chunk(const stackchan_msgs__msg__AudioChunk* chunk) {
  return chunk != nullptr &&
         chunk->direction == stackchan_msgs__msg__AudioChunk__PLAYBACK &&
         (chunk->total_chunks > 0 ||
          chunk->total_bytes > 0 ||
          chunk->end_of_stream);
}

bool is_duplicate_loaded_audio_topic_chunk(
    const stackchan_msgs__msg__AudioChunk* chunk) {
  if (chunk == nullptr || play_audio_loaded_expected_sequence == 0) {
    return false;
  }
  const char* command_id =
      chunk->command_id.data != nullptr ? chunk->command_id.data : "";
  return strcmp(command_id, play_audio_loaded_command_id) == 0 &&
         chunk->sequence < play_audio_loaded_expected_sequence;
}

stackchan::Result validate_loaded_audio_topic_chunk(
    const stackchan_msgs__msg__AudioChunk* chunk) {
  if (chunk == nullptr) {
    return stackchan::Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "loaded audio topic chunk is null",
        true);
  }
  if (!request_matches_device_id(chunk->device_id)) {
    return stackchan::Result::rejected(
        "INVALID_DEVICE_ID",
        "loaded audio topic chunk device_id mismatch",
        false);
  }
  if (play_audio_goal_active) {
    return stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "audio playback is already active",
        true);
  }
  const bool pcm_format =
      chunk->format == stackchan_msgs__msg__AudioChunk__PCM_S16LE;
  const bool adpcm_format =
      chunk->format == stackchan_msgs__msg__AudioChunk__IMA_ADPCM_4BIT;
  if ((!pcm_format && !adpcm_format) ||
      chunk->sample_rate != stackchan::kAudioSampleRate ||
      chunk->channels != stackchan::kAudioChannels) {
    return stackchan::Result::rejected(
        "UNSUPPORTED_FEATURE",
        "loaded audio topic format is unsupported",
        false);
  }
  if (chunk->pcm.size == 0 ||
      chunk->pcm.size > stackchan::kAudioMaxChunkBytes ||
      chunk->pcm.data == nullptr ||
      (pcm_format && chunk->pcm.size % 2 != 0)) {
    return stackchan::Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "loaded audio topic chunk byte length is invalid",
        true);
  }
  if (adpcm_format &&
      chunk->sequence == 0 &&
      chunk->pcm.size < stackchan::kImaAdpcmHeaderBytes) {
    return stackchan::Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "loaded audio topic ADPCM header is missing",
        true);
  }
  if (chunk->total_bytes == 0 ||
      chunk->total_bytes % 2 != 0 ||
      chunk->total_bytes > kAudioPlaybackLoadBufferBytes ||
      chunk->total_chunks == 0) {
    return stackchan::Result::rejected(
        "AUDIO_BUFFER_OVERFLOW",
        "loaded audio topic total size exceeds firmware buffer",
        false);
  }
  if ((play_audio_loaded_expected_sequence == 0 ||
       play_audio_loaded_complete ||
       play_audio_loaded_session_stale()) &&
      chunk->sequence == 0) {
    return stackchan::Result::accepted("loaded audio topic session started");
  }
  const char* command_id =
      chunk->command_id.data != nullptr ? chunk->command_id.data : "";
  if (is_duplicate_loaded_audio_topic_chunk(chunk)) {
    return stackchan::Result::accepted(
        "loaded audio topic duplicate chunk ignored");
  }
  if (!play_audio_loaded_complete &&
      strcmp(command_id, play_audio_loaded_command_id) != 0) {
    return stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "another audio topic load session is active",
        true);
  }
  if (chunk->format != play_audio_loaded_format) {
    return stackchan::Result::rejected(
        "UNSUPPORTED_FEATURE",
        "loaded audio topic format changed during active load",
        true);
  }
  if (chunk->sequence != play_audio_loaded_expected_sequence) {
    return stackchan::Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "loaded audio topic sequence is not contiguous",
        true);
  }
  return stackchan::Result::accepted("loaded audio topic chunk accepted");
}

void handle_loaded_audio_topic_chunk(
    const stackchan_msgs__msg__AudioChunk* chunk) {
  if (chunk == nullptr) {
    return;
  }
  const uint32_t received_ms = millis();
  const char* command_id =
      chunk->command_id.data != nullptr ? chunk->command_id.data : "";
  if (is_duplicate_loaded_audio_topic_chunk(chunk)) {
    const stackchan::Result result = stackchan::Result::accepted(
        "loaded audio topic duplicate chunk ignored");
    log_play_audio_load_diagnostic(
        "topic",
        command_id,
        chunk->sequence,
        chunk->pcm.size,
        chunk->total_chunks,
        play_audio_loaded_total_bytes,
        play_audio_loaded_expected_sequence,
        play_audio_loaded_complete,
        result);
    return;
  }
  stackchan::Result result = validate_loaded_audio_topic_chunk(chunk);
  if (result.ok) {
    if (chunk->sequence == 0) {
      reset_play_audio_loaded_buffer();
      copy_bounded(
          play_audio_loaded_command_id,
          sizeof(play_audio_loaded_command_id),
          command_id);
      play_audio_loaded_total_chunks = chunk->total_chunks;
      play_audio_loaded_format = chunk->format;
      play_audio_loaded_first_rx_ms = received_ms;
      play_audio_loaded_last_rx_gap_ms = 0;
    } else if (play_audio_loaded_last_rx_ms > 0 &&
               received_ms >= play_audio_loaded_last_rx_ms) {
      play_audio_loaded_last_rx_gap_ms =
          received_ms - play_audio_loaded_last_rx_ms;
    }
    play_audio_loaded_last_rx_ms = received_ms;
    const uint32_t decode_started_ms = millis();
    if (chunk->format == stackchan_msgs__msg__AudioChunk__PCM_S16LE &&
        play_audio_loaded_total_bytes + chunk->pcm.size >
            kAudioPlaybackLoadBufferBytes) {
      result = stackchan::Result::rejected(
          "AUDIO_BUFFER_OVERFLOW",
          "loaded audio topic buffer overflow",
          false);
    } else if (chunk->format == stackchan_msgs__msg__AudioChunk__PCM_S16LE) {
      memcpy(
          play_audio_loaded_buffer + play_audio_loaded_total_bytes,
          chunk->pcm.data,
          chunk->pcm.size);
      play_audio_loaded_total_bytes += chunk->pcm.size;
    } else {
      const uint32_t remaining_decoded_bytes =
          chunk->total_bytes > play_audio_loaded_total_bytes
              ? chunk->total_bytes - play_audio_loaded_total_bytes
              : 0;
      const stackchan::ImaAdpcmDecodeResult decoded =
          stackchan::decode_ima_adpcm_4bit_payload(
              chunk->pcm.data,
              chunk->pcm.size,
              chunk->sequence == 0,
              chunk->end_of_stream,
              remaining_decoded_bytes,
              play_audio_loaded_buffer + play_audio_loaded_total_bytes,
              kAudioPlaybackLoadBufferBytes - play_audio_loaded_total_bytes,
              play_audio_loaded_adpcm_state);
      result = decoded.result;
      if (result.ok) {
        play_audio_loaded_total_bytes += decoded.bytes_written;
      }
    }
    const uint32_t decode_finished_ms = millis();
    play_audio_loaded_last_decode_ms =
        decode_finished_ms >= decode_started_ms
            ? decode_finished_ms - decode_started_ms
            : 0;
    play_audio_loaded_decode_total_ms += play_audio_loaded_last_decode_ms;
    if (result.ok) {
      play_audio_loaded_expected_sequence = chunk->sequence + 1;
      play_audio_loaded_last_write_ms = millis();
      play_audio_loaded_complete = chunk->end_of_stream;
      if (play_audio_loaded_complete &&
          (play_audio_loaded_total_bytes != chunk->total_bytes ||
           play_audio_loaded_expected_sequence != chunk->total_chunks)) {
        result = stackchan::Result::rejected(
            "MALFORMED_AUDIO_CHUNK",
            "loaded audio topic final counters do not match declared totals",
            true);
        reset_play_audio_loaded_buffer();
      }
    }
  }
  log_play_audio_load_diagnostic(
      "topic",
      command_id,
      chunk->sequence,
      chunk->pcm.size,
      chunk->total_chunks,
      play_audio_loaded_total_bytes,
      play_audio_loaded_expected_sequence,
      play_audio_loaded_complete,
      result);
}

void handle_audio_playback_load_service(const void* request, void* response) {
  const auto* load_request =
      static_cast<const stackchan_msgs__srv__LoadAudioChunk_Request*>(request);
  auto* load_response =
      static_cast<stackchan_msgs__srv__LoadAudioChunk_Response*>(response);
  if (load_response == nullptr) {
    return;
  }
  stackchan::Result result = validate_loaded_audio_request(load_request);
  if (result.ok && load_request != nullptr) {
    const char* command_id =
        load_request->meta.command_id.data != nullptr
            ? load_request->meta.command_id.data
            : "";
    if (load_request->sequence == 0) {
      reset_play_audio_loaded_buffer();
      copy_bounded(
          play_audio_loaded_command_id,
          sizeof(play_audio_loaded_command_id),
          command_id);
      play_audio_loaded_total_chunks = load_request->total_chunks;
      play_audio_loaded_format = load_request->format;
    }
    if (load_request->format == stackchan_msgs__msg__AudioChunk__PCM_S16LE &&
        play_audio_loaded_total_bytes + load_request->pcm.size >
            kAudioPlaybackLoadBufferBytes) {
      result = stackchan::Result::rejected(
          "AUDIO_BUFFER_OVERFLOW",
          "loaded audio buffer overflow",
          false);
    } else if (load_request->format == stackchan_msgs__msg__AudioChunk__PCM_S16LE) {
      memcpy(
          play_audio_loaded_buffer + play_audio_loaded_total_bytes,
          load_request->pcm.data,
          load_request->pcm.size);
      play_audio_loaded_total_bytes += load_request->pcm.size;
    } else {
      const uint32_t remaining_decoded_bytes =
          load_request->total_bytes > play_audio_loaded_total_bytes
              ? load_request->total_bytes - play_audio_loaded_total_bytes
              : 0;
      const stackchan::ImaAdpcmDecodeResult decoded =
          stackchan::decode_ima_adpcm_4bit_payload(
              load_request->pcm.data,
              load_request->pcm.size,
              load_request->sequence == 0,
              load_request->end_of_stream,
              remaining_decoded_bytes,
              play_audio_loaded_buffer + play_audio_loaded_total_bytes,
              kAudioPlaybackLoadBufferBytes - play_audio_loaded_total_bytes,
              play_audio_loaded_adpcm_state);
      result = decoded.result;
      if (result.ok) {
        play_audio_loaded_total_bytes += decoded.bytes_written;
      }
    }
    if (result.ok) {
      play_audio_loaded_expected_sequence = load_request->sequence + 1;
      play_audio_loaded_last_write_ms = millis();
      play_audio_loaded_complete = load_request->end_of_stream;
      if (play_audio_loaded_complete &&
          (play_audio_loaded_total_bytes != load_request->total_bytes ||
           play_audio_loaded_expected_sequence != load_request->total_chunks)) {
        result = stackchan::Result::rejected(
            "MALFORMED_AUDIO_CHUNK",
            "loaded audio final counters do not match declared totals",
            true);
        reset_play_audio_loaded_buffer();
      }
    }
  }
  if (!convert_command_result(result, &load_response->result)) {
    stackchan_diag_println("stackchan micro_ros_step=audio_load_response_assign result=false");
  }
  load_response->accepted_sequence =
      load_request != nullptr ? load_request->sequence : 0;
  load_response->buffered_chunks = play_audio_loaded_expected_sequence;
  load_response->buffered_bytes = play_audio_loaded_total_bytes;
  load_response->complete = play_audio_loaded_complete;
  const char* command_id =
      load_request != nullptr && load_request->meta.command_id.data != nullptr
          ? load_request->meta.command_id.data
          : "";
  log_play_audio_load_diagnostic(
      "response",
      command_id,
      load_request != nullptr ? load_request->sequence : 0,
      load_request != nullptr ? load_request->pcm.size : 0,
      load_request != nullptr ? load_request->total_chunks : 0,
      load_response->buffered_bytes,
      load_response->buffered_chunks,
      load_response->complete,
      result);
}

void handle_face_set_service(const void* request, void* response) {
  const auto* face_request =
      static_cast<const stackchan_msgs__srv__SetFace_Request*>(request);
  auto* face_response =
      static_cast<stackchan_msgs__srv__SetFace_Response*>(response);
  if (face_request == nullptr || face_response == nullptr) {
    return;
  }

  stackchan::Result result =
      stackchan::Result::rejected("INVALID_DEVICE_ID", "request device_id mismatch");
  if (request_matches_device_id(face_request->meta.device_id)) {
    const stackchan::CommandMeta meta{
        STACKCHAN_DEVICE_ID,
        face_request->meta.command_id.data == nullptr
            ? ""
            : face_request->meta.command_id.data,
        face_request->meta.source.data == nullptr
            ? ""
            : face_request->meta.source.data,
        "",
        priority_from_ros(face_request->meta.priority)};
    result = handle_face_command(
        meta,
        face_request->name.data == nullptr ? "" : face_request->name.data);
  }

  if (!convert_command_result(result, &face_response->result)) {
    stackchan_diag_println("stackchan micro_ros_step=face_set_response_assign result=false");
  }
}

void led_rgb_for_pattern(const char* pattern, uint8_t* red, uint8_t* green, uint8_t* blue) {
  if (red == nullptr || green == nullptr || blue == nullptr) {
    return;
  }
  *red = 0;
  *green = 0;
  *blue = 0;
  if (strcmp(pattern, "progress") == 0) {
    *blue = 80;
  } else if (strcmp(pattern, "success") == 0) {
    *green = 80;
  } else if (strcmp(pattern, "warning") == 0) {
    *red = 80;
    *green = 48;
  } else if (strcmp(pattern, "error") == 0) {
    *red = 96;
  } else if (strcmp(pattern, "listening") == 0) {
    *green = 48;
    *blue = 80;
  }
}

stackchan::Result apply_led_pattern(const char* pattern) {
  if (!stackchan_led_initialized) {
    return stackchan::Result::rejected(
        "UNSUPPORTED_FEATURE",
        "K151 RGB LED adapter is unavailable",
        true);
  }
  uint8_t red = 0;
  uint8_t green = 0;
  uint8_t blue = 0;
  led_rgb_for_pattern(pattern, &red, &green, &blue);
  for (uint8_t index = 0; index < kRgbLedCount; ++index) {
    io_expander.setLedColor(index, red, green, blue);
  }
  io_expander.refreshLeds();
  return stackchan::Result::accepted("LED pattern accepted");
}

stackchan::Result handle_led_command(
    const stackchan::CommandMeta& meta,
    const char* pattern) {
  if (meta.priority == stackchan::Priority::Safety) {
    last_error = stackchan::Result::rejected(
        "INVALID_PRIORITY",
        "SAFETY priority is reserved for firmware-internal fault handling");
    return last_error;
  }
  if (!is_known_led_pattern(pattern)) {
    last_error = stackchan::Result::rejected("UNKNOWN_COMMAND", "unknown LED pattern");
    return last_error;
  }
  copy_bounded(last_command_id, sizeof(last_command_id), meta.command_id);
  last_error = apply_led_pattern(pattern);
  publish_status_heartbeat();
  return last_error;
}

void handle_led_set_service(const void* request, void* response) {
  const auto* led_request =
      static_cast<const stackchan_msgs__srv__SetLed_Request*>(request);
  auto* led_response =
      static_cast<stackchan_msgs__srv__SetLed_Response*>(response);
  if (led_request == nullptr || led_response == nullptr) {
    return;
  }

  stackchan::Result result =
      stackchan::Result::rejected("INVALID_DEVICE_ID", "request device_id mismatch");
  if (request_matches_device_id(led_request->meta.device_id)) {
    const stackchan::CommandMeta meta{
        STACKCHAN_DEVICE_ID,
        led_request->meta.command_id.data == nullptr
            ? ""
            : led_request->meta.command_id.data,
        led_request->meta.source.data == nullptr
            ? ""
            : led_request->meta.source.data,
        "",
        priority_from_ros(led_request->meta.priority)};
    result = handle_led_command(
        meta,
        led_request->pattern.data == nullptr ? "" : led_request->pattern.data);
  }

  if (!convert_command_result(result, &led_response->result)) {
    stackchan_diag_println("stackchan micro_ros_step=led_set_response_assign result=false");
  }
}

int rounded_degrees(float value) {
  return static_cast<int>(value >= 0.0f ? value + 0.5f : value - 0.5f);
}

stackchan::Result fill_head_pose_ros_message(
    stackchan_msgs__msg__HeadPose* destination,
    float pan_deg,
    float tilt_deg,
    bool moving) {
  if (destination == nullptr) {
    return stackchan::Result::rejected("FIRMWARE_BUSY", "head pose response storage missing", true);
  }
  destination->stamp.sec = millis() / 1000;
  destination->stamp.nanosec = (millis() % 1000) * 1000000;
  destination->pan_deg = pan_deg;
  destination->tilt_deg = tilt_deg;
  destination->moving = moving;
  if (!assign_ros_string(&destination->device_id, STACKCHAN_DEVICE_ID) ||
      !assign_ros_string(&destination->frame, "home")) {
    return stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "head pose response exceeded bounded ROS storage",
        true);
  }
  return stackchan::Result::accepted("head pose response assigned");
}

stackchan::Result publish_head_pose(float pan_deg, float tilt_deg, bool moving) {
  const stackchan::HeadPoseTelemetry telemetry{
      STACKCHAN_DEVICE_ID,
      static_cast<uint32_t>(millis()),
      pan_deg,
      tilt_deg,
      moving,
      "home"};
  return device_publishers.publish_motion_pose(telemetry);
}

stackchan::Result handle_head_pose_command(
    const stackchan::CommandMeta& meta,
    bool home,
    float pan_deg,
    float tilt_deg,
    uint16_t speed,
    uint32_t duration_ms,
    stackchan_msgs__msg__HeadPose* pose_response) {
  if (meta.priority == stackchan::Priority::Safety) {
    last_error = stackchan::Result::rejected(
        "INVALID_PRIORITY",
        "SAFETY priority is reserved for firmware-internal fault handling");
    return last_error;
  }

  if (state_machine.state() == stackchan::RuntimeState::Fault) {
    last_error = stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "firmware is in fault state; recover before accepting head pose commands",
        true);
    return last_error;
  }

  if (motion_scheduler.active || state_machine.state() == stackchan::RuntimeState::Acting) {
    last_error = stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "motion scheduler already has an active command",
        true);
    return last_error;
  }

  update_servo_health_cache(millis());
  const bool calibration_valid = firmware_calibration_valid();
  const bool servo_read_ok = calibration_valid && servo_position_read_available_cache;
  const stackchan::HeadPoseLimits limits = stackchan::kDefaultHeadPoseLimits;
  const stackchan::HeadPosePlan plan =
      home
          ? stackchan::plan_head_home(
                speed,
                duration_ms,
                true,
                limits.min_command_interval_ms,
                calibration_valid,
                servo_read_ok,
                false,
                limits)
          : stackchan::plan_head_pose(
                pan_deg,
                tilt_deg,
                speed,
                duration_ms,
                true,
                limits.min_command_interval_ms,
                calibration_valid,
                servo_read_ok,
                false,
                limits);

  copy_bounded(last_command_id, sizeof(last_command_id), meta.command_id);
  if (!plan.result.ok) {
    last_error = plan.result;
    copy_bounded(current_motion, sizeof(current_motion), "idle");
    publish_status_heartbeat();
    return plan.result;
  }

  const stackchan::ServoTarget home_target = calibrated_home_target();
  const stackchan::ServoTarget target =
      home
          ? home_target
          : stackchan::ServoTarget{
                home_target.x + rounded_degrees(plan.target.pan_deg),
                home_target.y + rounded_degrees(plan.target.tilt_deg)};

  stackchan::Result result = validate_motion_servo_target(home_target, "home");
  if (result.ok) {
    result = validate_motion_servo_target(target, "head pose", true);
  }
  if (result.ok) {
    result = move_servo_pair_to(target);
  }

  const float reported_pan = home ? 0.0f : plan.target.pan_deg;
  const float reported_tilt = home ? 0.0f : plan.target.tilt_deg;
  if (result.ok) {
    last_error = {
        true,
        stackchan::ResultState::Completed,
        "",
        home ? "head home completed" : "head pose completed",
        false};
    copy_bounded(current_motion, sizeof(current_motion), "idle");
    (void)publish_head_pose(reported_pan, reported_tilt, false);
    publish_status_heartbeat();
    if (pose_response != nullptr) {
      (void)fill_head_pose_ros_message(pose_response, reported_pan, reported_tilt, false);
    }
    return last_error;
  }

  last_error = result;
  if (is_servo_safety_fault(result) &&
      strcmp(result.error_code, "SERVO_LIMIT_EXCEEDED") != 0) {
    const stackchan::Result recovery_result = try_motion_neutral_recovery();
    if (!recovery_result.ok) {
      state_machine.fault();
    }
  }
  copy_bounded(current_motion, sizeof(current_motion), "idle");
  publish_status_heartbeat();
  return result;
}

void handle_head_pose_set_service(const void* request, void* response) {
  const auto* pose_request =
      static_cast<const stackchan_msgs__srv__SetHeadPose_Request*>(request);
  auto* pose_response =
      static_cast<stackchan_msgs__srv__SetHeadPose_Response*>(response);
  if (pose_request == nullptr || pose_response == nullptr) {
    return;
  }

  (void)fill_head_pose_ros_message(&pose_response->pose, 0.0f, 0.0f, false);
  stackchan::Result result =
      stackchan::Result::rejected("INVALID_DEVICE_ID", "request device_id mismatch");
  if (request_matches_device_id(pose_request->meta.device_id)) {
    const stackchan::CommandMeta meta{
        STACKCHAN_DEVICE_ID,
        pose_request->meta.command_id.data == nullptr
            ? ""
            : pose_request->meta.command_id.data,
        pose_request->meta.source.data == nullptr
            ? ""
            : pose_request->meta.source.data,
        "",
        priority_from_ros(pose_request->meta.priority)};
    result = handle_head_pose_command(
        meta,
        pose_request->home,
        pose_request->pan_deg,
        pose_request->tilt_deg,
        pose_request->speed,
        pose_request->duration_ms,
        &pose_response->pose);
  }

  if (!convert_command_result(result, &pose_response->result)) {
    stackchan_diag_println("stackchan micro_ros_step=head_pose_set_response_assign result=false");
  }
}

void spin_command_executor() {
  if (!microros_connected ||
      !microros_entities_initialized ||
      !microros_executor_initialized) {
    return;
  }
  const rcl_ret_t result = rclc_executor_spin_some(&microros_executor, RCL_MS_TO_NS(5));
  if (result != RCL_RET_OK && result != RCL_RET_TIMEOUT) {
    stackchan_diag_print("stackchan micro_ros_step=executor_spin result=");
    stackchan_diag_println(result);
    reset_rcl_error();
  }
}

stackchan::Result handle_motion_command(
    const stackchan::CommandMeta& meta,
    const char* name,
    float intensity,
    uint32_t duration_ms) {
  if (meta.priority == stackchan::Priority::Safety) {
    last_error = stackchan::Result::rejected(
        "INVALID_PRIORITY",
        "SAFETY priority is reserved for firmware-internal fault handling");
    return last_error;
  }

  if (state_machine.state() == stackchan::RuntimeState::Fault) {
    last_error = stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "firmware is in fault state; recover before accepting motion commands",
        true);
    return last_error;
  }

  if (motion_scheduler.active || state_machine.state() == stackchan::RuntimeState::Acting) {
    last_error = stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "motion scheduler already has an active command",
        true);
    return last_error;
  }

  const bool calibration_valid = firmware_calibration_valid();
  const bool servo_read_ok = calibration_valid && servo_position_read_available_cache;
  const stackchan::MotionPlan plan =
      stackchan::plan_motion(
          name,
          intensity,
          duration_ms,
          calibration_valid,
          servo_read_ok,
          state_machine.state() == stackchan::RuntimeState::Fault);
  copy_bounded(last_command_id, sizeof(last_command_id), meta.command_id);
  last_error = plan.result;
  if (!plan.result.ok) {
    copy_bounded(current_motion, sizeof(current_motion), "idle");
    return plan.result;
  }

  const stackchan::Result schedule_result =
      enqueue_motion_scheduler(plan, name, meta.command_id, millis());
  last_error = schedule_result;
  if (!schedule_result.ok) {
    copy_bounded(current_motion, sizeof(current_motion), "idle");
  }
  return schedule_result;
}

void handle_motion_set_service(const void* request, void* response) {
  const auto* motion_request =
      static_cast<const stackchan_msgs__srv__SetMotion_Request*>(request);
  auto* motion_response =
      static_cast<stackchan_msgs__srv__SetMotion_Response*>(response);
  if (motion_request == nullptr || motion_response == nullptr) {
    return;
  }

  stackchan::Result result =
      stackchan::Result::rejected("INVALID_DEVICE_ID", "request device_id mismatch");
  if (request_matches_device_id(motion_request->meta.device_id)) {
    const stackchan::CommandMeta meta{
        STACKCHAN_DEVICE_ID,
        motion_request->meta.command_id.data == nullptr
            ? ""
            : motion_request->meta.command_id.data,
        motion_request->meta.source.data == nullptr
            ? ""
            : motion_request->meta.source.data,
        "",
        priority_from_ros(motion_request->meta.priority)};
    result = handle_motion_command(
        meta,
        motion_request->name.data == nullptr ? "" : motion_request->name.data,
        motion_request->intensity,
        motion_request->duration_ms);
  }

  if (!convert_command_result(result, &motion_response->result)) {
    stackchan_diag_println("stackchan micro_ros_step=motion_set_response_assign result=false");
  }
}

void publish_status_heartbeat() {
  if (microros_connected) {
    const stackchan::StackChanStatusTelemetry telemetry{
        STACKCHAN_DEVICE_ID,
        true,
        runtime_state_name(state_machine.state()),
        current_face,
        current_motion,
        last_command_id,
        last_error,
        "bringup"};
    const stackchan::Result result = device_publishers.publish_status(telemetry);
    if (!result.ok && microros_publish_failures_exceeded()) {
      update_agent_connection(false);
    }
    return;
  }
  stackchan_diag_print("stackchan status device_id=");
  stackchan_diag_print(STACKCHAN_DEVICE_ID);
  stackchan_diag_print(" face=");
  stackchan_diag_print(current_face);
  stackchan_diag_print(" motion=");
  stackchan_diag_print(current_motion);
  stackchan_diag_print(" last_command_id=");
  stackchan_diag_print(last_command_id);
  stackchan_diag_print(" ok=");
  stackchan_diag_print(last_error.ok ? "true" : "false");
  stackchan_diag_print(" error_code=");
  stackchan_diag_print(last_error.error_code);
  stackchan_diag_print(" micro_ros_pub_attempts=");
  stackchan_diag_print(microros_publish_attempt_count);
  stackchan_diag_print(" micro_ros_pub_ok=");
  stackchan_diag_print(microros_publish_ok_count);
  stackchan_diag_print(" micro_ros_pub_failed=");
  stackchan_diag_print(microros_publish_failed_count);
  stackchan_diag_print(" last_rcl_publish=");
  stackchan_diag_print(last_microros_publish_result);
  stackchan_diag_print(" bringup_events_enqueued=");
  stackchan_diag_print(microros_bringup_event_enqueue_count);
  stackchan_diag_print(" bringup_events_total=");
  stackchan_diag_print(microros_bringup_event_total_enqueue_count);
  stackchan_diag_print(" audio_sample_rate=");
  stackchan_diag_print(audio_policy.sample_rate);
  stackchan_diag_print(" imu_min_hz=");
  stackchan_diag_print(stackchan::kImuMinHz);
  stackchan_diag_print(" imu_events=");
  stackchan_diag_print(stackchan_imu_initialized ? "available" : "unavailable");
  stackchan_diag_print(" nfc_events=");
  stackchan_diag_print(stackchan_nfc_initialized ? "available" : "unavailable");
  stackchan_diag_print(" nfc_bus=");
  stackchan_diag_print(stackchan_nfc_bus);
  stackchan_diag_print(" nfc_sda=");
  stackchan_diag_print(static_cast<int>(stackchan_nfc_sda_pin));
  stackchan_diag_print(" nfc_scl=");
  stackchan_diag_print(static_cast<int>(stackchan_nfc_scl_pin));
  stackchan_diag_print(" nfc_i2c_present=");
  stackchan_diag_print(stackchan_nfc_i2c_present ? "true" : "false");
  stackchan_diag_print(" nfc_detect_attempts=");
  stackchan_diag_print(stackchan_nfc_detect_attempts);
  stackchan_diag_print(" nfc_detect_hits=");
  stackchan_diag_print(stackchan_nfc_detect_hits);
  stackchan_diag_print(" nfc_identify_failures=");
  stackchan_diag_print(stackchan_nfc_identify_failures);
  stackchan_diag_print(" remote_ir=");
  stackchan_diag_print(stackchan_ir_initialized ? "available" : "unavailable");
  stackchan_diag_print(" ir_rx_pin=");
  stackchan_diag_print(kIrRecvPin);
  stackchan_diag_print(" ir_decodes=");
  stackchan_diag_print(stackchan_ir_decode_count);
  stackchan_diag_print(" ir_overflows=");
  stackchan_diag_print(stackchan_ir_overflow_count);
  stackchan_diag_print(" audio_playback=");
  stackchan_diag_print(stackchan_audio_playback_initialized ? "available" : "unavailable");
  stackchan_diag_print(" audio_capture=");
  stackchan_diag_print(stackchan_audio_capture_initialized ? "available" : "unavailable");
  stackchan_diag_print(" camera_snapshot=");
  stackchan_diag_print(stackchan_camera_snapshot_initialized ? "available" : "unavailable");
  stackchan_diag_print(" events_topic=");
  if (device_publishers.initialized()) {
    stackchan_diag_println(device_publishers.topic_name(stackchan::DevicePublisherTopic::Events));
  } else {
    stackchan_diag_println("unavailable");
  }
}

void publish_runtime_telemetry(uint32_t now_ms) {
#if STACKCHAN_MICROROS_STATUS_ONLY_BRINGUP || \
    (STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP && !STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP)
  (void)now_ms;
  return;
#endif
  if (!microros_connected || !microros_entities_initialized) {
    return;
  }

  if (telemetry_publish_scheduler.should_publish_touch(now_ms)) {
    const stackchan::TouchStateTelemetry telemetry = read_touch_state_telemetry(now_ms);
    const stackchan::Result publish_result =
        device_publishers.publish_touch_state(telemetry);
    if (!publish_result.ok) {
      last_error = publish_result;
      if (microros_publish_failures_exceeded()) {
        update_agent_connection(false);
      }
      return;
    }
    const stackchan::Result event_result =
        touch_event_estimator.update(telemetry, event_publisher);
    if (!event_result.ok && strcmp(event_result.error_code, "TRANSPORT_DISCONNECTED") != 0) {
      last_error = event_result;
    }
  }

  if (telemetry_publish_scheduler.should_publish_proximity(now_ms)) {
    const stackchan::ProximityRawTelemetry telemetry =
        read_proximity_raw_telemetry(now_ms);
    const stackchan::Result publish_result =
        device_publishers.publish_proximity_raw(telemetry);
    if (!publish_result.ok) {
      last_error = publish_result;
      if (microros_publish_failures_exceeded()) {
        update_agent_connection(false);
      }
      return;
    }
    const stackchan::Result event_result =
        proximity_event_estimator.update(telemetry, event_publisher);
    if (!event_result.ok && strcmp(event_result.error_code, "TRANSPORT_DISCONNECTED") != 0) {
      last_error = event_result;
    }
  }

  if (telemetry_publish_scheduler.should_publish_light(now_ms)) {
    const stackchan::LightRawTelemetry telemetry = read_light_raw_telemetry(now_ms);
    const stackchan::Result publish_result =
        device_publishers.publish_light_raw(telemetry);
    if (!publish_result.ok) {
      last_error = publish_result;
      if (microros_publish_failures_exceeded()) {
        update_agent_connection(false);
      }
      return;
    }
    const stackchan::Result event_result =
        light_event_estimator.update(telemetry, event_publisher);
    if (!event_result.ok && strcmp(event_result.error_code, "TRANSPORT_DISCONNECTED") != 0) {
      last_error = event_result;
    }
  }

  if (telemetry_publish_scheduler.should_publish_power(now_ms)) {
    const stackchan::PowerStatusTelemetry telemetry = read_power_status_telemetry(now_ms);
    const stackchan::Result publish_result =
        device_publishers.publish_power_status(telemetry);
    if (!publish_result.ok) {
      last_error = publish_result;
      if (microros_publish_failures_exceeded()) {
        update_agent_connection(false);
      }
      return;
    }
    const stackchan::Result event_result =
        power_event_estimator.update(telemetry, event_publisher);
    if (!event_result.ok && strcmp(event_result.error_code, "TRANSPORT_DISCONNECTED") != 0) {
      last_error = event_result;
    }
  }

  if (telemetry_publish_scheduler.should_sample_imu(now_ms)) {
    const stackchan::Result event_result = sample_imu_events(now_ms);
    if (!event_result.ok && strcmp(event_result.error_code, "TRANSPORT_DISCONNECTED") != 0) {
      last_error = event_result;
    }
  }

  const stackchan::Result button_event_result = sample_button_events(now_ms);
  if (!button_event_result.ok && strcmp(button_event_result.error_code, "TRANSPORT_DISCONNECTED") != 0) {
    last_error = button_event_result;
  }

  if (telemetry_publish_scheduler.should_sample_nfc(now_ms)) {
    const stackchan::Result event_result = sample_nfc_events(now_ms);
    if (!event_result.ok && strcmp(event_result.error_code, "TRANSPORT_DISCONNECTED") != 0) {
      last_error = event_result;
    }
  }

  const stackchan::Result ir_event_result = sample_ir_events(now_ms);
  if (!ir_event_result.ok && strcmp(ir_event_result.error_code, "TRANSPORT_DISCONNECTED") != 0) {
    last_error = ir_event_result;
  }
}

}  // namespace

void setup() {
  Serial.begin(STACKCHAN_MICROROS_SERIAL_BAUD);
#if STACKCHAN_SENSOR_INPUT_DIAGNOSTICS
  sensor_input_diag_stage_started_ms = millis();
  print_sensor_input_diag_stage("setup_enter");
  return;
#endif
#if STACKCHAN_MICROROS_MINIMAL_BRINGUP
  initialize_minimal_microros_bringup();
  return;
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_BRINGUP
  initialize_board_init_microros_bringup();
  return;
#endif
  servo_adapter_init_result = initialize_servo_adapter();
  stackchan_diag_print("stackchan servo_adapter_init ok=");
  stackchan_diag_print(servo_adapter_init_result.ok ? "true" : "false");
  stackchan_diag_print(" error_code=");
  stackchan_diag_println(servo_adapter_init_result.error_code);
  initialize_sensor_adapters();
  stackchan_diag_print("stackchan touch_sensor_init ok=");
  stackchan_diag_println(stackchan_touch_sensor_initialized ? "true" : "false");
  stackchan_diag_print("stackchan power_monitor_init ok=");
  stackchan_diag_println(stackchan_power_monitor_initialized ? "true" : "false");
  stackchan_diag_print("stackchan ltr553_sensor_init ok=");
  stackchan_diag_println(ltr553_sensor_initialized ? "true" : "false");
  stackchan_diag_print("stackchan imu_event_init ok=");
  stackchan_diag_println(stackchan_imu_initialized ? "true" : "false");
  stackchan_diag_print("stackchan nfc_event_init ok=");
  stackchan_diag_println(stackchan_nfc_initialized ? "true" : "false");
  stackchan_diag_print("stackchan nfc_event_bus=");
  stackchan_diag_print(stackchan_nfc_bus);
  stackchan_diag_print(" sda=");
  stackchan_diag_print(static_cast<int>(stackchan_nfc_sda_pin));
  stackchan_diag_print(" scl=");
  stackchan_diag_println(static_cast<int>(stackchan_nfc_scl_pin));
  stackchan_diag_print("stackchan nfc_event_i2c_present=");
  stackchan_diag_println(stackchan_nfc_i2c_present ? "true" : "false");
  stackchan_diag_print("stackchan ir_event_init ok=");
  stackchan_diag_println(stackchan_ir_initialized ? "true" : "false");
  stackchan_diag_print("stackchan ir_event_rx_pin=");
  stackchan_diag_println(kIrRecvPin);
  stackchan_diag_print("stackchan audio_playback_probe ok=");
  stackchan_diag_println(stackchan_audio_playback_initialized ? "true" : "false");
  stackchan_diag_print("stackchan audio_capture_probe ok=");
  stackchan_diag_println(stackchan_audio_capture_initialized ? "true" : "false");
  stackchan_diag_print("stackchan camera_snapshot_probe ok=");
  stackchan_diag_println(stackchan_camera_snapshot_initialized ? "true" : "false");
  calibration_maintenance_result = apply_calibration_maintenance_action();
  stackchan_diag_print("stackchan calibration_maintenance ok=");
  stackchan_diag_print(calibration_maintenance_result.ok ? "true" : "false");
  stackchan_diag_print(" error_code=");
  stackchan_diag_println(calibration_maintenance_result.error_code);
  calibration_load_result = load_calibration_from_nvs();
  stackchan_diag_print("stackchan calibration_load ok=");
  stackchan_diag_print(calibration_load_result.ok ? "true" : "false");
  stackchan_diag_print(" error_code=");
  stackchan_diag_println(calibration_load_result.error_code);
  update_servo_health_cache(millis(), true);
  stackchan::Result publisher_result = device_publishers.initialize(STACKCHAN_DEVICE_ID);
  if (!publisher_result.ok) {
    last_error = publisher_result;
  }
  device_publishers.set_publish_callback(firmware_publish_callback);
  event_publisher.set_callback(publish_device_event_ros);
  show_neutral_face();
  state_machine.booted();
}

void loop() {
  const unsigned long now = millis();
#if STACKCHAN_SENSOR_INPUT_DIAGNOSTICS
  run_sensor_input_diagnostic_loop(static_cast<uint32_t>(now));
  delay(50);
  return;
#endif
#if STACKCHAN_MICROROS_MINIMAL_BRINGUP
  if (!microros_connected && now - last_agent_attempt_ms >= 1000) {
    update_agent_connection(try_connect_microros_agent());
    last_agent_attempt_ms = now;
  }

  if (now - last_heartbeat_ms >= 1000) {
    publish_status_heartbeat();
    last_heartbeat_ms = now;
  }

  delay(10);
  return;
#endif
#if STACKCHAN_MICROROS_BOARD_INIT_BRINGUP
  if (!microros_connected && now - last_agent_attempt_ms >= 1000) {
    update_agent_connection(try_connect_microros_agent());
    last_agent_attempt_ms = now;
  }

  if (now - last_heartbeat_ms >= 1000) {
    publish_status_heartbeat();
    last_heartbeat_ms = now;
  }

  delay(10);
  return;
#endif
  M5.update();
  step_motion_scheduler(now);
  if (!motion_scheduler.active) {
    update_servo_health_cache(now);
  }

  if (!microros_connected && now - last_agent_attempt_ms >= 1000) {
    update_agent_connection(try_connect_microros_agent());
    last_agent_attempt_ms = now;
  }

  if (now - last_heartbeat_ms >= 1000) {
    publish_status_heartbeat();
    last_heartbeat_ms = now;
  }

  // Runtime order is safety/fault checks, motion-neutral work, audio media,
  // command executor, camera, event drain, then low-rate telemetry.
  // Do not publish synthetic pose/status samples as real device telemetry.
  poll_capture_audio_action_server();
  poll_play_audio_action_server();
  spin_command_executor();
  poll_capture_camera_action_server();
  queue_bringup_event_if_ready(now);
  drain_device_events();
  if (!motion_scheduler.active) {
    publish_runtime_telemetry(static_cast<uint32_t>(now));
  }
  delay(play_audio_goal_active || motion_scheduler.active ? 1 : 10);
}
