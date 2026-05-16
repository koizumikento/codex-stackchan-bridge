#include <Arduino.h>
#include <string.h>

#include "stackchan/contract.hpp"
#include "stackchan/audio.hpp"
#include "stackchan/motion_safety.hpp"
#include "stackchan/sensors.hpp"
#include "stackchan/state_machine.hpp"

#ifndef STACKCHAN_DEVICE_ID
#define STACKCHAN_DEVICE_ID "default"
#endif

#ifndef STACKCHAN_MICROROS_SERIAL_BAUD
#define STACKCHAN_MICROROS_SERIAL_BAUD 115200
#endif

namespace {

stackchan::StateMachine state_machine;
char current_face[16] = "neutral";
char current_motion[16] = "idle";
char last_command_id[37] = "";
stackchan::Result last_error = stackchan::Result::accepted("ok");
unsigned long last_heartbeat_ms = 0;
unsigned long last_agent_attempt_ms = 0;
bool microros_connected = false;
const stackchan::AudioChunkPolicy audio_policy = stackchan::baseline_audio_policy();

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

bool is_servo_safety_fault(const stackchan::Result& result) {
  return strcmp(result.error_code, "SERVO_LIMIT_EXCEEDED") == 0 ||
         strcmp(result.error_code, "MOTION_INTERRUPTED") == 0;
}

bool try_connect_microros_agent() {
  // TODO: initialize StackChan-BSP hardware and micro-ROS serial transport.
  // set_microros_serial_transports(Serial);
  // TODO: ping micro-ROS Agent, initialize support/node/executor, and create
  // stackchan_msgs publishers, services, and actions before returning true.
  return false;
}

bool check_microros_agent_connection() {
  // TODO: replace with rmw_uros_ping_agent() and executor health checks once
  // the micro-ROS support/node/executor are initialized.
  return microros_connected;
}

void update_agent_connection(bool connected) {
  microros_connected = connected;
  if (connected) {
    state_machine.agent_connected();
  } else {
    state_machine.agent_disconnected();
  }
}

void show_neutral_face() {
  copy_bounded(current_face, sizeof(current_face), "neutral");
}

stackchan::Result handle_face_command(
    const stackchan::CommandMeta& meta,
    const char* name) {
  if (state_machine.state() == stackchan::RuntimeState::Fault) {
    last_error = stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "firmware is in fault state; recover before accepting face commands",
        true);
    return last_error;
  }

  if (meta.priority == stackchan::Priority::Safety) {
    last_error = stackchan::Result::rejected(
        "INVALID_PRIORITY",
        "SAFETY priority is reserved for firmware-internal fault handling");
    return last_error;
  }

  if (!is_known_face(name)) {
    last_error = stackchan::Result::rejected("UNKNOWN_COMMAND", "unknown face name");
    return last_error;
  }

  copy_bounded(current_face, sizeof(current_face), name);
  copy_bounded(last_command_id, sizeof(last_command_id), meta.command_id);
  last_error = stackchan::Result::accepted("face accepted");
  return last_error;
}

stackchan::Result handle_motion_command(
    const stackchan::CommandMeta& meta,
    const char* name,
    float intensity,
    uint32_t duration_ms) {
  if (state_machine.state() == stackchan::RuntimeState::Fault) {
    last_error = stackchan::Result::rejected(
        "FIRMWARE_BUSY",
        "firmware is in fault state; recover before accepting motion commands",
        true);
    return last_error;
  }

  if (meta.priority == stackchan::Priority::Safety) {
    last_error = stackchan::Result::rejected(
        "INVALID_PRIORITY",
        "SAFETY priority is reserved for firmware-internal fault handling");
    return last_error;
  }

  const stackchan::MotionPlan plan =
      stackchan::plan_motion(name, intensity, duration_ms);
  copy_bounded(last_command_id, sizeof(last_command_id), meta.command_id);
  last_error = plan.result;
  if (!plan.result.ok) {
    if (is_servo_safety_fault(plan.result)) {
      state_machine.fault();
    }
    copy_bounded(current_motion, sizeof(current_motion), "idle");
    return plan.result;
  }

  state_machine.command_started();
  copy_bounded(current_motion, sizeof(current_motion), name);
  // TODO: call StackChan-BSP servo adapter with plan.target and plan.duration_ms.
  state_machine.command_finished();
  return plan.result;
}

void publish_status_heartbeat() {
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
  Serial.print(" audio_sample_rate=");
  Serial.print(audio_policy.sample_rate);
  Serial.print(" imu_min_hz=");
  Serial.println(stackchan::kImuMinHz);
}

}  // namespace

void setup() {
  Serial.begin(STACKCHAN_MICROROS_SERIAL_BAUD);
  show_neutral_face();
  state_machine.booted();
}

void loop() {
  const unsigned long now = millis();
  if (microros_connected && !check_microros_agent_connection()) {
    update_agent_connection(false);
  } else if (!microros_connected && now - last_agent_attempt_ms >= 1000) {
    update_agent_connection(try_connect_microros_agent());
    last_agent_attempt_ms = now;
  }

  if (now - last_heartbeat_ms >= 1000) {
    publish_status_heartbeat();
    last_heartbeat_ms = now;
  }

  // TODO: spin micro-ROS executor and dispatch generated stackchan_msgs handlers.
  delay(10);
}
