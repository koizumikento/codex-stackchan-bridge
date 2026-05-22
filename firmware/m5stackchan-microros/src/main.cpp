#include <Arduino.h>
#include <M5Unified.hpp>
#include <Preferences.h>
#include <drivers/FTServo_Arduino/src/SCSCL.h>
#include <drivers/PY32IOExpander/PY32IOExpander.hpp>
#include <micro_ros_platformio.h>
#include <rcl/error_handling.h>
#include <rcl/publisher.h>
#include <rcl/service.h>
#include <rcl/time.h>
#include <rclc/node.h>
#include <rclc/executor.h>
#include <rclc/publisher.h>
#include <rclc/rclc.h>
#include <rclc/service.h>
#include <rmw/qos_profiles.h>
#include <rmw_microros/ping.h>
#include <rosidl_runtime_c/string_functions.h>
#include <stackchan_msgs/msg/head_pose.h>
#include <stackchan_msgs/msg/stack_chan_event.h>
#include <stackchan_msgs/msg/stack_chan_status.h>
#include <stackchan_msgs/srv/set_face.h>
#include <stackchan_msgs/srv/set_head_pose.h>
#include <stackchan_msgs/srv/set_motion.h>
#include <string.h>

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

stackchan::StateMachine state_machine;
char current_face[16] = "neutral";
char current_motion[16] = "idle";
char last_command_id[37] = "";
stackchan::Result last_error = stackchan::Result::accepted("ok");
unsigned long last_heartbeat_ms = 0;
unsigned long last_agent_attempt_ms = 0;
unsigned long microros_connected_since_ms = 0;
unsigned long last_bringup_event_enqueue_ms = 0;
bool microros_connected = false;
uint8_t microros_bringup_event_enqueue_count = 0;
uint32_t microros_bringup_event_total_enqueue_count = 0;
uint32_t microros_publish_attempt_count = 0;
uint32_t microros_publish_ok_count = 0;
uint32_t microros_publish_failed_count = 0;
rcl_ret_t last_microros_publish_result = RCL_RET_OK;
stackchan::CalibrationStore calibration_store;
const stackchan::AudioChunkPolicy audio_policy = stackchan::baseline_audio_policy();
stackchan::EventPublisher event_publisher(STACKCHAN_DEVICE_ID);
stackchan::DevicePublisherRegistry device_publishers;
SCSCL servo_bus;
m5::PY32IOExpander_Class io_expander;
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
constexpr int kYawServoId = 1;
constexpr int kPitchServoId = 2;
constexpr int kYawDefaultZeroPos = 460;
constexpr int kPitchDefaultZeroPos = 620;
constexpr int kServoRawMin = 0;
constexpr int kServoRawMax = 1000;
constexpr int kServoTime = 20;
constexpr int kServoSpeed = 0;
constexpr int kServoUartBaud = 1000000;
constexpr int kServoTxPin = 6;
constexpr int kServoRxPin = 7;
constexpr unsigned long kIoExpanderInitTimeoutMs = 1200;
enum class MotionSchedulerPhase {
  Idle,
  MoveTarget,
  HoldTarget,
  MoveNeutral,
  HoldNeutral,
};

struct MotionSchedulerJob {
  bool active;
  MotionSchedulerPhase phase;
  stackchan::ServoTarget target;
  stackchan::ServoTarget home;
  uint32_t duration_ms;
  unsigned long phase_started_ms;
  char name[16];
  char command_id[37];
};

MotionSchedulerJob motion_scheduler{
    false,
    MotionSchedulerPhase::Idle,
    stackchan::kNeutralTarget,
    stackchan::kNeutralTarget,
    0,
    0,
    "",
    "",
};
bool microros_transport_configured = false;
bool microros_entities_initialized = false;
bool servo_position_read_available_cache = false;
bool motion_status_publish_pending = false;
unsigned long last_servo_health_check_ms = 0;
rcl_allocator_t microros_allocator;
rclc_support_t microros_support;
rcl_node_t microros_node;
rcl_publisher_t event_ros_publisher;
rcl_publisher_t motion_pose_ros_publisher;
rcl_publisher_t status_ros_publisher;
rcl_service_t face_set_service;
rcl_service_t head_pose_set_service;
rcl_service_t motion_set_service;
rclc_executor_t microros_executor;
stackchan_msgs__msg__StackChanEvent event_ros_message;
stackchan_msgs__msg__HeadPose motion_pose_ros_message;
stackchan_msgs__msg__StackChanStatus status_ros_message;
stackchan_msgs__srv__SetFace_Request face_set_request;
stackchan_msgs__srv__SetFace_Response face_set_response;
stackchan_msgs__srv__SetHeadPose_Request head_pose_set_request;
stackchan_msgs__srv__SetHeadPose_Response head_pose_set_response;
stackchan_msgs__srv__SetMotion_Request motion_set_request;
stackchan_msgs__srv__SetMotion_Response motion_set_response;
char microros_node_namespace[64] = "";
char face_set_service_name[96] = "";
char head_pose_set_service_name[96] = "";
char motion_set_service_name[96] = "";
bool microros_executor_initialized = false;

void publish_status_heartbeat();
stackchan::Result validate_motion_servo_target(
    const stackchan::ServoTarget& target,
    const char* label);

void copy_bounded(char* destination, size_t size, const char* source) {
  if (size == 0) {
    return;
  }
  strncpy(destination, source == nullptr ? "" : source, size - 1);
  destination[size - 1] = '\0';
}

bool is_known_face(const char* name) {
  return strcmp(name, "neutral") == 0 ||
         strcmp(name, "happy") == 0 ||
         strcmp(name, "thinking") == 0 ||
         strcmp(name, "surprised") == 0 ||
         strcmp(name, "sleepy") == 0 ||
         strcmp(name, "error") == 0;
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

int servo_degrees_to_raw(int default_zero_pos, int degrees) {
  const int deci_degrees = degrees * 10;
  return default_zero_pos + deci_degrees * 16 / 50;
}

stackchan::Result initialize_servo_adapter() {
  M5.begin();

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
  delay(200);

  if (!servo_bus.begin(UART_NUM_1, kServoUartBaud, kServoTxPin, kServoRxPin)) {
    return stackchan::Result::rejected(
        "SERVO_READ_FAILED",
        "StackChan servo UART initialization failed",
        true);
  }

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

stackchan::Result move_servo_pair_to(int target_x_deg, int target_y_deg) {
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

  if (servo_bus.EnableTorque(kYawServoId, 1) != 1 ||
      servo_bus.EnableTorque(kPitchServoId, 1) != 1 ||
      servo_bus.WritePos(kYawServoId, yaw_raw, kServoTime, kServoSpeed) != 1 ||
      servo_bus.WritePos(kPitchServoId, pitch_raw, kServoTime, kServoSpeed) != 1) {
    return stackchan::Result::rejected(
        "MOTION_INTERRUPTED",
        "servo write failed",
        true);
  }
  return stackchan::Result::accepted("servo move accepted");
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

stackchan::Result move_servo_pair_to(const stackchan::ServoTarget& target) {
  return move_servo_pair_to(target.x, target.y);
}

uint32_t motion_half_duration(uint32_t duration_ms) {
  return duration_ms / 2;
}

void reset_motion_scheduler() {
  motion_scheduler.active = false;
  motion_status_publish_pending = false;
  motion_scheduler.phase = MotionSchedulerPhase::Idle;
  motion_scheduler.target = stackchan::kNeutralTarget;
  motion_scheduler.home = stackchan::kNeutralTarget;
  motion_scheduler.duration_ms = 0;
  motion_scheduler.phase_started_ms = 0;
  copy_bounded(motion_scheduler.name, sizeof(motion_scheduler.name), "");
  copy_bounded(motion_scheduler.command_id, sizeof(motion_scheduler.command_id), "");
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
  last_error = result;
  copy_bounded(current_motion, sizeof(current_motion), "idle");
  if (state_machine.state() == stackchan::RuntimeState::Acting) {
    state_machine.command_finished();
  }
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

  const stackchan::ServoTarget home = calibrated_home_target();
  const stackchan::ServoTarget target = apply_motion_offset(home, plan.target);
  stackchan::Result target_result = validate_motion_servo_target(home, "home");
  if (!target_result.ok) {
    return target_result;
  }
  target_result = validate_motion_servo_target(target, "motion");
  if (!target_result.ok) {
    return target_result;
  }

  motion_scheduler.active = true;
  motion_scheduler.phase = MotionSchedulerPhase::MoveTarget;
  motion_scheduler.home = home;
  motion_scheduler.target = target;
  motion_scheduler.duration_ms = plan.duration_ms;
  motion_scheduler.phase_started_ms = now;
  copy_bounded(motion_scheduler.name, sizeof(motion_scheduler.name), name);
  copy_bounded(motion_scheduler.command_id, sizeof(motion_scheduler.command_id), command_id);
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

  if (motion_scheduler.phase == MotionSchedulerPhase::MoveTarget) {
    const stackchan::Result result = move_servo_pair_to(motion_scheduler.target);
    if (!result.ok) {
      fail_motion_scheduler(result);
      return;
    }
    motion_scheduler.phase = MotionSchedulerPhase::HoldTarget;
    motion_scheduler.phase_started_ms = now;
    return;
  }

  if (motion_scheduler.phase == MotionSchedulerPhase::HoldTarget) {
    if (now - motion_scheduler.phase_started_ms < motion_half_duration(motion_scheduler.duration_ms)) {
      return;
    }
    motion_scheduler.phase = MotionSchedulerPhase::MoveNeutral;
  }

  if (motion_scheduler.phase == MotionSchedulerPhase::MoveNeutral) {
    const stackchan::Result result = move_servo_pair_to(motion_scheduler.home);
    if (!result.ok) {
      fail_motion_scheduler(result);
      return;
    }
    motion_scheduler.phase = MotionSchedulerPhase::HoldNeutral;
    motion_scheduler.phase_started_ms = now;
    return;
  }

  if (motion_scheduler.phase == MotionSchedulerPhase::HoldNeutral &&
      now - motion_scheduler.phase_started_ms >= motion_half_duration(motion_scheduler.duration_ms)) {
    finish_motion_scheduler(stackchan::Result::accepted("motion completed"));
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
    const char* label) {
  if (servo_target_within_limits(target)) {
    return stackchan::Result::accepted("servo target accepted");
  }
  char message[96] = "";
  snprintf(
      message,
      sizeof(message),
      "%s servo target exceeds firmware degree limits",
      label == nullptr ? "motion" : label);
  return stackchan::Result::rejected("SERVO_LIMIT_EXCEEDED", message, true);
}

void reset_rcl_error() {
  if (rcl_error_is_set()) {
    rcl_reset_error();
  }
}

bool rcl_ok(rcl_ret_t result, const char* step) {
  if (result == RCL_RET_OK) {
    return true;
  }
  Serial.print("stackchan micro_ros_step=");
  Serial.print(step);
  Serial.print(" result=");
  Serial.println(result);
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

bool assign_ros_string(rosidl_runtime_c__String* destination, const char* value) {
  return rosidl_runtime_c__String__assign(destination, value == nullptr ? "" : value);
}

bool reserve_ros_string(rosidl_runtime_c__String* destination, size_t capacity) {
  static const char kReserve36[] = "....................................";
  if (destination == nullptr || capacity > 36) {
    return false;
  }
  if (!rosidl_runtime_c__String__assignn(destination, kReserve36, capacity)) {
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

bool convert_status_message(
    const stackchan::StackChanStatusMsg& source,
    stackchan_msgs__msg__StackChanStatus* destination) {
  if (destination == nullptr) {
    return false;
  }
  destination->connected = source.connected;
  destination->capabilities.size = 0;
  return assign_ros_string(&destination->device_id, source.device_id.data) &&
         assign_ros_string(&destination->state, source.state.data) &&
         assign_ros_string(&destination->face, source.face.data) &&
         assign_ros_string(&destination->motion, source.motion.data) &&
         assign_ros_string(&destination->last_command_id, source.last_command_id.data) &&
         convert_result_message(source.last_error, &destination->last_error) &&
         assign_ros_string(&destination->firmware_version, source.firmware_version.data);
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

void build_motion_set_service_name() {
  snprintf(
      motion_set_service_name,
      sizeof(motion_set_service_name),
      "/stackchan/%s/device/motion/run",
      STACKCHAN_DEVICE_ID);
  motion_set_service_name[sizeof(motion_set_service_name) - 1] = '\0';
}

void handle_face_set_service(const void* request, void* response);
void handle_head_pose_set_service(const void* request, void* response);
void handle_motion_set_service(const void* request, void* response);
void publish_status_heartbeat();

bool initialize_microros_entities() {
  microros_allocator = rcl_get_default_allocator();
  memset(&microros_support, 0, sizeof(microros_support));
  microros_node = rcl_get_zero_initialized_node();
  event_ros_publisher = rcl_get_zero_initialized_publisher();
  motion_pose_ros_publisher = rcl_get_zero_initialized_publisher();
  status_ros_publisher = rcl_get_zero_initialized_publisher();
  face_set_service = rcl_get_zero_initialized_service();
  head_pose_set_service = rcl_get_zero_initialized_service();
  motion_set_service = rcl_get_zero_initialized_service();
  microros_executor = rclc_executor_get_zero_initialized_executor();
  memset(&event_ros_message, 0, sizeof(event_ros_message));
  memset(&motion_pose_ros_message, 0, sizeof(motion_pose_ros_message));
  memset(&status_ros_message, 0, sizeof(status_ros_message));
  memset(&face_set_request, 0, sizeof(face_set_request));
  memset(&face_set_response, 0, sizeof(face_set_response));
  memset(&head_pose_set_request, 0, sizeof(head_pose_set_request));
  memset(&head_pose_set_response, 0, sizeof(head_pose_set_response));
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
    Serial.println("stackchan micro_ros_step=event_message_init result=false");
    return false;
  }
  if (!stackchan_msgs__msg__HeadPose__init(&motion_pose_ros_message)) {
    Serial.println("stackchan micro_ros_step=motion_pose_message_init result=false");
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__msg__StackChanStatus__init(&status_ros_message)) {
    Serial.println("stackchan micro_ros_step=status_message_init result=false");
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetFace_Request__init(&face_set_request)) {
    Serial.println("stackchan micro_ros_step=face_set_request_init result=false");
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!reserve_face_set_request_strings()) {
    Serial.println("stackchan micro_ros_step=face_set_request_reserve result=false");
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetFace_Response__init(&face_set_response)) {
    Serial.println("stackchan micro_ros_step=face_set_response_init result=false");
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetHeadPose_Request__init(&head_pose_set_request)) {
    Serial.println("stackchan micro_ros_step=head_pose_set_request_init result=false");
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!reserve_head_pose_set_request_strings()) {
    Serial.println("stackchan micro_ros_step=head_pose_set_request_reserve result=false");
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetHeadPose_Response__init(&head_pose_set_response)) {
    Serial.println("stackchan micro_ros_step=head_pose_set_response_init result=false");
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    return false;
  }
  if (!stackchan_msgs__srv__SetMotion_Request__init(&motion_set_request)) {
    Serial.println("stackchan micro_ros_step=motion_set_request_init result=false");
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
    Serial.println("stackchan micro_ros_step=motion_set_request_reserve result=false");
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
    Serial.println("stackchan micro_ros_step=motion_set_response_init result=false");
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
                  3,
                  &microros_allocator),
              "executor_init")) {
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
  return true;
}

void destroy_microros_entities() {
  if (microros_entities_initialized) {
    if (microros_executor_initialized) {
      rcl_ret_t fini_result = rclc_executor_fini(&microros_executor);
      (void)fini_result;
      microros_executor_initialized = false;
    }
    stackchan_msgs__srv__SetMotion_Response__fini(&motion_set_response);
    stackchan_msgs__srv__SetMotion_Request__fini(&motion_set_request);
    stackchan_msgs__srv__SetHeadPose_Response__fini(&head_pose_set_response);
    stackchan_msgs__srv__SetHeadPose_Request__fini(&head_pose_set_request);
    stackchan_msgs__srv__SetFace_Response__fini(&face_set_response);
    stackchan_msgs__srv__SetFace_Request__fini(&face_set_request);
    stackchan_msgs__msg__StackChanStatus__fini(&status_ros_message);
    stackchan_msgs__msg__HeadPose__fini(&motion_pose_ros_message);
    stackchan_msgs__msg__StackChanEvent__fini(&event_ros_message);
    rcl_ret_t fini_result = rcl_publisher_fini(&event_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&motion_pose_ros_publisher, &microros_node);
    fini_result = rcl_publisher_fini(&status_ros_publisher, &microros_node);
    fini_result = rcl_service_fini(&face_set_service, &microros_node);
    fini_result = rcl_service_fini(&head_pose_set_service, &microros_node);
    fini_result = rcl_service_fini(&motion_set_service, &microros_node);
    fini_result = rcl_node_fini(&microros_node);
    fini_result = rclc_support_fini(&microros_support);
    (void)fini_result;
    microros_entities_initialized = false;
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

  if (message == nullptr) {
    Serial.print("stackchan firmware_publish topic=");
    Serial.print(device_publishers.topic_name(topic));
    Serial.print(" qos_depth=");
    Serial.println(device_publishers.qos(topic).depth);
    return false;
  }

  const void* ros_message = nullptr;
  rcl_publisher_t* publisher = nullptr;
  if (topic == stackchan::DevicePublisherTopic::Events) {
    const auto* event_message =
        static_cast<const stackchan::StackChanEventMsg*>(message);
    if (!convert_event_message(*event_message, &event_ros_message)) {
      ++microros_publish_failed_count;
      return false;
    }
    ros_message = &event_ros_message;
    publisher = &event_ros_publisher;
  } else if (topic == stackchan::DevicePublisherTopic::Status) {
    const auto* status_message =
        static_cast<const stackchan::StackChanStatusMsg*>(message);
    if (!convert_status_message(*status_message, &status_ros_message)) {
      ++microros_publish_failed_count;
      return false;
    }
    ros_message = &status_ros_message;
    publisher = &status_ros_publisher;
  } else if (topic == stackchan::DevicePublisherTopic::MotionPose) {
    const auto* pose_message =
        static_cast<const stackchan::HeadPoseMsg*>(message);
    if (!convert_head_pose_message(*pose_message, &motion_pose_ros_message)) {
      ++microros_publish_failed_count;
      return false;
    }
    ros_message = &motion_pose_ros_message;
    publisher = &motion_pose_ros_publisher;
  } else {
    Serial.print("stackchan firmware_publish topic=");
    Serial.print(device_publishers.topic_name(topic));
    Serial.print(" qos_depth=");
    Serial.println(device_publishers.qos(topic).depth);
    return false;
  }
  ++microros_publish_attempt_count;
  const rcl_ret_t result = rcl_publish(publisher, ros_message, nullptr);
  last_microros_publish_result = result;
  if (result != RCL_RET_OK) {
    ++microros_publish_failed_count;
    reset_rcl_error();
    return false;
  }
  ++microros_publish_ok_count;
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
    state_machine.agent_connected();
    microros_connected_since_ms = millis();
    last_bringup_event_enqueue_ms = 0;
    microros_bringup_event_enqueue_count = 0;
  } else {
    microros_connected_since_ms = 0;
    last_bringup_event_enqueue_ms = 0;
    microros_bringup_event_enqueue_count = 0;
    state_machine.agent_disconnected();
  }
}

void queue_bringup_event_if_ready(unsigned long now) {
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
    Serial.println("stackchan micro_ros_step=face_set_response_assign result=false");
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
    result = validate_motion_servo_target(target, "head pose");
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
    Serial.println("stackchan micro_ros_step=head_pose_set_response_assign result=false");
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
    Serial.print("stackchan micro_ros_step=executor_spin result=");
    Serial.println(result);
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
    if (is_servo_safety_fault(plan.result)) {
      state_machine.fault();
    }
    copy_bounded(current_motion, sizeof(current_motion), "idle");
    return plan.result;
  }

  const stackchan::Result schedule_result =
      enqueue_motion_scheduler(plan, name, meta.command_id, millis());
  last_error = schedule_result;
  if (!schedule_result.ok) {
    if (is_servo_safety_fault(schedule_result)) {
      state_machine.fault();
    }
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
    Serial.println("stackchan micro_ros_step=motion_set_response_assign result=false");
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
    if (!result.ok) {
      update_agent_connection(false);
    }
    return;
  }
  Serial.print("stackchan status device_id=");
  Serial.print(STACKCHAN_DEVICE_ID);
  Serial.print(" face=");
  Serial.print(current_face);
  Serial.print(" motion=");
  Serial.print(current_motion);
  Serial.print(" last_command_id=");
  Serial.print(last_command_id);
  Serial.print(" ok=");
  Serial.print(last_error.ok ? "true" : "false");
  Serial.print(" error_code=");
  Serial.print(last_error.error_code);
  Serial.print(" micro_ros_pub_attempts=");
  Serial.print(microros_publish_attempt_count);
  Serial.print(" micro_ros_pub_ok=");
  Serial.print(microros_publish_ok_count);
  Serial.print(" micro_ros_pub_failed=");
  Serial.print(microros_publish_failed_count);
  Serial.print(" last_rcl_publish=");
  Serial.print(last_microros_publish_result);
  Serial.print(" bringup_events_enqueued=");
  Serial.print(microros_bringup_event_enqueue_count);
  Serial.print(" bringup_events_total=");
  Serial.print(microros_bringup_event_total_enqueue_count);
  Serial.print(" audio_sample_rate=");
  Serial.print(audio_policy.sample_rate);
  Serial.print(" imu_min_hz=");
  Serial.print(stackchan::kImuMinHz);
  Serial.print(" events_topic=");
  if (device_publishers.initialized()) {
    Serial.println(device_publishers.topic_name(stackchan::DevicePublisherTopic::Events));
  } else {
    Serial.println("unavailable");
  }
}

}  // namespace

void setup() {
  Serial.begin(STACKCHAN_MICROROS_SERIAL_BAUD);
  servo_adapter_init_result = initialize_servo_adapter();
  Serial.print("stackchan servo_adapter_init ok=");
  Serial.print(servo_adapter_init_result.ok ? "true" : "false");
  Serial.print(" error_code=");
  Serial.println(servo_adapter_init_result.error_code);
  calibration_maintenance_result = apply_calibration_maintenance_action();
  Serial.print("stackchan calibration_maintenance ok=");
  Serial.print(calibration_maintenance_result.ok ? "true" : "false");
  Serial.print(" error_code=");
  Serial.println(calibration_maintenance_result.error_code);
  calibration_load_result = load_calibration_from_nvs();
  Serial.print("stackchan calibration_load ok=");
  Serial.print(calibration_load_result.ok ? "true" : "false");
  Serial.print(" error_code=");
  Serial.println(calibration_load_result.error_code);
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
  step_motion_scheduler(now);
  update_servo_health_cache(now);

  if (!microros_connected && now - last_agent_attempt_ms >= 1000) {
    update_agent_connection(try_connect_microros_agent());
    last_agent_attempt_ms = now;
  }

  if (now - last_heartbeat_ms >= 1000) {
    publish_status_heartbeat();
    last_heartbeat_ms = now;
  }

  // Runtime order is safety/fault checks, motion-neutral work, command executor,
  // high-priority event drain, then low-rate telemetry once real adapters exist.
  // Do not publish synthetic pose/status samples as real device telemetry.
  spin_command_executor();
  queue_bringup_event_if_ready(now);
  drain_device_events();
  delay(10);
}
