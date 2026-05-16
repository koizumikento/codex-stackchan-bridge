#include <Arduino.h>

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
const char* current_face = "neutral";
const char* current_motion = "idle";
const char* last_command_id = "";
stackchan::Result last_error = stackchan::Result::accepted("ok");
unsigned long last_heartbeat_ms = 0;
const stackchan::AudioChunkPolicy audio_policy = stackchan::baseline_audio_policy();

void show_neutral_face() {
  current_face = "neutral";
}

stackchan::Result handle_face_command(
    const stackchan::CommandMeta& meta,
    const char* name) {
  if (meta.priority == stackchan::Priority::Safety) {
    last_error = stackchan::Result::rejected(
        "INVALID_PRIORITY",
        "SAFETY priority is reserved for firmware internals");
    return last_error;
  }

  current_face = name;
  last_command_id = meta.command_id;
  last_error = stackchan::Result::accepted("face accepted");
  return last_error;
}

stackchan::Result handle_motion_command(
    const stackchan::CommandMeta& meta,
    const char* name,
    float intensity,
    uint32_t duration_ms) {
  if (meta.priority == stackchan::Priority::Safety) {
    last_error = stackchan::Result::rejected(
        "INVALID_PRIORITY",
        "SAFETY priority is reserved for firmware internals");
    return last_error;
  }

  const stackchan::MotionPlan plan =
      stackchan::plan_motion(name, intensity, duration_ms);
  last_command_id = meta.command_id;
  last_error = plan.result;
  if (!plan.result.ok) {
    state_machine.fault();
    current_motion = "idle";
    return plan.result;
  }

  state_machine.command_started();
  current_motion = name;
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

  // TODO: initialize StackChan-BSP hardware and micro-ROS serial transport.
  // set_microros_serial_transports(Serial);
  state_machine.agent_connected();
}

void loop() {
  const unsigned long now = millis();
  if (now - last_heartbeat_ms >= 1000) {
    publish_status_heartbeat();
    last_heartbeat_ms = now;
  }

  // TODO: spin micro-ROS executor and dispatch generated stackchan_msgs handlers.
  delay(10);
}
