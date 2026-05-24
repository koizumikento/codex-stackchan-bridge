#include <assert.h>
#include <math.h>
#include <string.h>

#include "stackchan/ros_publishers.hpp"

namespace {

bool callback_seen = false;
stackchan::DevicePublisherTopic callback_topic =
    stackchan::DevicePublisherTopic::Count;
char callback_event_name[stackchan::kEventNameMaxLength + 1] = "";
char callback_payload_json[stackchan::kEventPayloadJsonMaxLength + 1] = "";
char callback_status_state[stackchan::kRosSurfaceMaxLength + 1] = "";
bool callback_status_connected = false;

bool capture_publish(
    stackchan::DevicePublisherTopic topic,
    const void* message,
    void*) {
  callback_seen = message != nullptr;
  callback_topic = topic;
  callback_event_name[0] = '\0';
  callback_payload_json[0] = '\0';
  callback_status_state[0] = '\0';
  callback_status_connected = false;
  if (topic == stackchan::DevicePublisherTopic::Events && message != nullptr) {
    const auto* event_message =
        static_cast<const stackchan::StackChanEventMsg*>(message);
    stackchan::copy_event_string(
        callback_event_name,
        sizeof(callback_event_name),
        event_message->event_name.data);
    stackchan::copy_event_string(
        callback_payload_json,
        sizeof(callback_payload_json),
        event_message->payload_json.data);
  } else if (topic == stackchan::DevicePublisherTopic::Status && message != nullptr) {
    const auto* status_message =
        static_cast<const stackchan::StackChanStatusMsg*>(message);
    callback_status_connected = status_message->connected;
    stackchan::copy_event_string(
        callback_status_state,
        sizeof(callback_status_state),
        status_message->state.data);
  }
  return true;
}

stackchan::Result capture_event_publish(
    const stackchan::DeviceEvent& event,
    void* context) {
  if (context == nullptr) {
    return stackchan::Result::rejected(
        "TRANSPORT_DISCONNECTED",
        "test registry unavailable",
        true);
  }
  stackchan::DevicePublisherRegistry* registry =
      static_cast<stackchan::DevicePublisherRegistry*>(context);
  return registry->publish_event(event);
}

void test_device_topic_names_and_validation() {
  char topic[stackchan::kRosTopicMaxLength + 1]{};

  assert(stackchan::is_valid_device_id("default"));
  assert(stackchan::is_valid_device_id("desk_1"));
  assert(!stackchan::is_valid_device_id("bad/id"));
  assert(!stackchan::is_valid_device_id(""));

  assert(stackchan::build_device_topic_name(
      "default",
      stackchan::DevicePublisherTopic::Events,
      topic,
      sizeof(topic)));
  assert(strcmp(topic, "/stackchan/default/device/events") == 0);

  assert(stackchan::build_device_topic_name(
      "default",
      stackchan::DevicePublisherTopic::Status,
      topic,
      sizeof(topic)));
  assert(strcmp(topic, "/stackchan/default/device/status") == 0);

  assert(stackchan::build_device_topic_name(
      "desk",
      stackchan::DevicePublisherTopic::ProximityRaw,
      topic,
      sizeof(topic)));
  assert(strcmp(topic, "/stackchan/desk/device/proximity/raw") == 0);

  assert(!stackchan::build_device_topic_name(
      "bad/id",
      stackchan::DevicePublisherTopic::Events,
      topic,
      sizeof(topic)));
}

void test_qos_contract() {
  stackchan::DevicePublisherRegistry registry;
  assert(registry.initialize("desk").ok);

  auto assert_qos = [&registry](
      stackchan::DevicePublisherTopic topic,
      stackchan::RosReliability reliability,
      uint8_t depth) {
    const stackchan::DevicePublisherQos qos = registry.qos(topic);
    assert(qos.reliability == reliability);
    assert(qos.depth == depth);
    assert(!qos.transient_local);
  };
  assert_qos(
      stackchan::DevicePublisherTopic::Events,
      stackchan::RosReliability::Reliable,
      32);
  assert_qos(
      stackchan::DevicePublisherTopic::Status,
      stackchan::RosReliability::Reliable,
      2);
  assert_qos(
      stackchan::DevicePublisherTopic::TouchState,
      stackchan::RosReliability::Reliable,
      4);
  assert_qos(
      stackchan::DevicePublisherTopic::ProximityRaw,
      stackchan::RosReliability::BestEffort,
      10);
  assert_qos(
      stackchan::DevicePublisherTopic::LightRaw,
      stackchan::RosReliability::BestEffort,
      5);
  assert_qos(
      stackchan::DevicePublisherTopic::PowerStatus,
      stackchan::RosReliability::Reliable,
      2);
  assert_qos(
      stackchan::DevicePublisherTopic::MotionPose,
      stackchan::RosReliability::Reliable,
      2);
}

void test_status_conversion_and_publish_callback() {
  stackchan::StackChanStatusTelemetry status{
      "desk",
      true,
      "ready",
      "neutral",
      "idle",
      "cmd-0001",
      stackchan::Result::accepted("ok"),
      "bringup"};
  stackchan::StackChanStatusMsg status_msg{};

  assert(stackchan::fill_stackchan_status_message("desk", status, &status_msg).ok);
  assert(strcmp(status_msg.device_id.data, "desk") == 0);
  assert(status_msg.connected);
  assert(strcmp(status_msg.state.data, "ready") == 0);
  assert(strcmp(status_msg.face.data, "neutral") == 0);
  assert(strcmp(status_msg.motion.data, "idle") == 0);
  assert(strcmp(status_msg.last_command_id.data, "cmd-0001") == 0);
  assert(status_msg.last_error.ok);
  assert(status_msg.last_error.state == 1);
  assert(strcmp(status_msg.firmware_version.data, "bringup") == 0);

  stackchan::DevicePublisherRegistry registry;
  assert(registry.initialize("desk").ok);
  registry.set_publish_callback(capture_publish);
  assert(registry.publish_status(status).ok);
  assert(callback_seen);
  assert(callback_topic == stackchan::DevicePublisherTopic::Status);
  assert(callback_status_connected);
  assert(strcmp(callback_status_state, "ready") == 0);

  status.device_id = "other";
  assert(!registry.publish_status(status).ok);
}

void test_event_conversion_and_publish_callback() {
  stackchan::DeviceEvent event{};
  stackchan::copy_event_string(event.event_id, sizeof(event.event_id), "");
  stackchan::copy_event_string(event.device_id, sizeof(event.device_id), "desk");
  stackchan::copy_event_string(
      event.event_name,
      sizeof(event.event_name),
      "button_pressed");
  stackchan::copy_event_string(event.source, sizeof(event.source), "firmware");
  stackchan::copy_event_string(event.command_id, sizeof(event.command_id), "");
  stackchan::copy_event_string(
      event.payload_json,
      sizeof(event.payload_json),
      "{\"button\":\"main\"}");
  event.stamp_ms = 1234;

  stackchan::StackChanEventMsg message{};
  assert(stackchan::fill_event_message(event, &message).ok);
  assert(strcmp(message.event_id.data, "") == 0);
  assert(strcmp(message.device_id.data, "desk") == 0);
  assert(strcmp(message.event_name.data, "button_pressed") == 0);
  assert(strcmp(message.source.data, "firmware") == 0);
  assert(strcmp(message.command_id.data, "") == 0);
  assert(strcmp(message.payload_json.data, "{\"button\":\"main\"}") == 0);
  assert(message.stamp.sec == 1);
  assert(message.stamp.nanosec == 234000000u);

  stackchan::DevicePublisherRegistry registry;
  assert(registry.initialize("desk").ok);
  registry.set_publish_callback(capture_publish);
  callback_seen = false;
  assert(registry.publish_event(event).ok);
  assert(callback_seen);
  assert(callback_topic == stackchan::DevicePublisherTopic::Events);

  stackchan::copy_event_string(event.device_id, sizeof(event.device_id), "other");
  assert(!registry.publish_event(event).ok);
}

void test_event_publisher_drain_through_registry() {
  stackchan::DevicePublisherRegistry registry;
  assert(registry.initialize("desk").ok);
  registry.set_publish_callback(capture_publish);

  stackchan::EventPublisher events("desk");
  events.set_callback(capture_event_publish, &registry);

  callback_seen = false;
  assert(events.nfc_detected(7000, "raw-nfc-id-123").ok);
  assert(events.queued_count() == 1);
  assert(events.drain(1).ok);
  assert(callback_seen);
  assert(callback_topic == stackchan::DevicePublisherTopic::Events);
  assert(events.queued_count() == 0);

  stackchan::DeviceEvent converted{};
  assert(events.nfc_removed(8000, "raw-nfc-id-456").ok);
  // Verify the queued event is redacted before it reaches registry conversion.
  struct CaptureContext {
    stackchan::DeviceEvent* event;
  } context{&converted};
  events.set_callback(
      [](const stackchan::DeviceEvent& event, void* raw_context) -> stackchan::Result {
        CaptureContext* capture = static_cast<CaptureContext*>(raw_context);
        *capture->event = event;
        return stackchan::Result::accepted("captured");
      },
      &context);
  assert(events.drain(1).ok);
  assert(strstr(converted.payload_json, "tag_ref") != nullptr);
  assert(strstr(converted.payload_json, "raw-nfc-id-456") == nullptr);

  assert(events.remote_command_received(8100, "raw-ir-code-123").ok);
  events.set_callback(
      [](const stackchan::DeviceEvent& event, void* raw_context) -> stackchan::Result {
        CaptureContext* capture = static_cast<CaptureContext*>(raw_context);
        *capture->event = event;
        return stackchan::Result::accepted("captured");
      },
      &context);
  assert(events.drain(1).ok);
  assert(strcmp(converted.event_name, "remote_command_received") == 0);
  assert(strstr(converted.payload_json, "remote_ref") != nullptr);
  assert(strstr(converted.payload_json, "raw-ir-code-123") == nullptr);

  stackchan::EventPublisher disconnected("desk");
  disconnected.set_callback(capture_event_publish, &registry);
  registry.set_publish_callback(nullptr);
  assert(disconnected.power_fault(9000, "brownout").ok);
  stackchan::Result result = disconnected.drain(1);
  assert(!result.ok);
  assert(strcmp(result.error_code, "TRANSPORT_DISCONNECTED") == 0);
  assert(disconnected.queued_count() == 1);
}

void test_firmware_ready_event_drain_through_registry() {
  stackchan::DevicePublisherRegistry registry;
  assert(registry.initialize("desk").ok);
  registry.set_publish_callback(capture_publish);

  stackchan::EventPublisher events("desk");
  events.set_callback(capture_event_publish, &registry);

  callback_seen = false;
  assert(events.publish(
      stackchan::DeviceEventKind::FirmwareReady,
      9000,
      "",
      "{\"transport\":\"serial\",\"agent\":\"micro_ros\"}").ok);
  assert(events.queued_count() == 1);
  assert(events.drain(1).ok);
  assert(callback_seen);
  assert(callback_topic == stackchan::DevicePublisherTopic::Events);
  assert(strcmp(callback_event_name, "firmware_ready") == 0);
  assert(strstr(callback_payload_json, "\"transport\":\"serial\"") != nullptr);
  assert(events.queued_count() == 0);
}

void test_touch_conversion_bounds_storage() {
  stackchan::TouchStateTelemetry telemetry{};
  telemetry.stamp_ms = 2000;
  stackchan::copy_event_string(telemetry.device_id, sizeof(telemetry.device_id), "desk");
  telemetry.zone_mask = stackchan::kTouchZone1 | stackchan::kTouchZone3;
  telemetry.zone_count = 5;
  telemetry.intensities[0] = 1;
  telemetry.intensities[1] = 2;
  telemetry.intensities[2] = 3;
  stackchan::copy_event_string(telemetry.surface, sizeof(telemetry.surface), "head");

  stackchan::TouchStateMsg message{};
  assert(stackchan::fill_touch_state_message("desk", telemetry, &message).ok);
  assert(strcmp(message.device_id.data, "desk") == 0);
  assert(message.zone_mask == 5);
  assert(message.zone_count == 3);
  assert(message.intensities.size == 3);
  assert(message.intensities.data[0] == 1);
  assert(message.intensities.data[2] == 3);
  assert(strcmp(message.surface.data, "head") == 0);
  assert(message.stamp.sec == 2);
  assert(message.stamp.nanosec == 0u);
  assert(message.device_id.capacity == stackchan::kRosDeviceIdMaxLength);
  assert(message.intensities.capacity == stackchan::kRosTouchIntensityCapacity);

  stackchan::DevicePublisherRegistry registry;
  assert(registry.initialize("desk").ok);
  registry.set_publish_callback(capture_publish);
  assert(registry.publish_touch_state(telemetry).ok);
  stackchan::copy_event_string(telemetry.device_id, sizeof(telemetry.device_id), "other");
  assert(!registry.publish_touch_state(telemetry).ok);
}

void test_sensor_and_power_conversions() {
  stackchan::ProximityRawTelemetry proximity{};
  proximity.stamp_ms = 3000;
  stackchan::copy_event_string(proximity.device_id, sizeof(proximity.device_id), "desk");
  proximity.sensor_index = 2;
  proximity.distance_m = NAN;
  proximity.signal = 0.8f;
  proximity.raw = 42;
  proximity.saturated = true;
  stackchan::ProximityRawMsg proximity_msg{};
  assert(stackchan::fill_proximity_raw_message("desk", proximity, &proximity_msg).ok);
  assert(strcmp(proximity_msg.device_id.data, "desk") == 0);
  assert(proximity_msg.sensor_index == 2);
  assert(proximity_msg.stamp.sec == 3);
  assert(proximity_msg.stamp.nanosec == 0u);
  assert(isnan(proximity_msg.distance_m));
  assert(proximity_msg.signal == 0.8f);
  assert(proximity_msg.raw == 42);
  assert(proximity_msg.saturated);

  stackchan::LightRawTelemetry light{};
  light.stamp_ms = 4000;
  stackchan::copy_event_string(light.device_id, sizeof(light.device_id), "desk");
  light.sensor_index = 1;
  light.illuminance_lux = NAN;
  light.raw = 7;
  light.saturated = false;
  stackchan::LightRawMsg light_msg{};
  assert(stackchan::fill_light_raw_message("desk", light, &light_msg).ok);
  assert(strcmp(light_msg.device_id.data, "desk") == 0);
  assert(light_msg.sensor_index == 1);
  assert(light_msg.stamp.sec == 4);
  assert(light_msg.stamp.nanosec == 0u);
  assert(isnan(light_msg.illuminance_lux));
  assert(light_msg.raw == 7);
  assert(!light_msg.saturated);

  stackchan::PowerStatusTelemetry power{};
  power.stamp_ms = 5000;
  stackchan::copy_event_string(power.device_id, sizeof(power.device_id), "desk");
  power.voltage_v = 3.7f;
  power.current_ma = 120.0f;
  power.power_mw = 444.0f;
  power.percentage = NAN;
  power.power_source = stackchan::PowerSource::Usb;
  power.charging = true;
  power.powered = true;
  power.low_battery = false;
  power.brownout_risk = false;
  stackchan::copy_event_string(power.fault_code, sizeof(power.fault_code), "ok");
  stackchan::PowerStatusMsg power_msg{};
  assert(stackchan::fill_power_status_message("desk", power, &power_msg).ok);
  assert(strcmp(power_msg.device_id.data, "desk") == 0);
  assert(power_msg.stamp.sec == 5);
  assert(power_msg.stamp.nanosec == 0u);
  assert(power_msg.voltage_v == 3.7f);
  assert(power_msg.current_ma == 120.0f);
  assert(power_msg.power_mw == 444.0f);
  assert(power_msg.power_source == 2);
  assert(isnan(power_msg.percentage));
  assert(power_msg.charging);
  assert(power_msg.powered);
  assert(!power_msg.low_battery);
  assert(!power_msg.brownout_risk);
  assert(strcmp(power_msg.fault_code.data, "ok") == 0);

  stackchan::DevicePublisherRegistry registry;
  assert(registry.initialize("desk").ok);
  registry.set_publish_callback(capture_publish);
  assert(registry.publish_proximity_raw(proximity).ok);
  assert(registry.publish_light_raw(light).ok);
  assert(registry.publish_power_status(power).ok);
  stackchan::copy_event_string(proximity.device_id, sizeof(proximity.device_id), "other");
  stackchan::copy_event_string(light.device_id, sizeof(light.device_id), "other");
  stackchan::copy_event_string(power.device_id, sizeof(power.device_id), "other");
  assert(!registry.publish_proximity_raw(proximity).ok);
  assert(!registry.publish_light_raw(light).ok);
  assert(!registry.publish_power_status(power).ok);
}

void test_head_pose_and_scheduler() {
  stackchan::HeadPoseTelemetry pose{};
  pose.stamp_ms = 6000;
  stackchan::copy_event_string(pose.device_id, sizeof(pose.device_id), "desk");
  pose.pan_deg = 10.0f;
  pose.tilt_deg = 20.0f;
  pose.moving = false;
  stackchan::copy_event_string(pose.frame, sizeof(pose.frame), "home");
  stackchan::HeadPoseMsg pose_msg{};
  assert(stackchan::fill_head_pose_message("desk", pose, &pose_msg).ok);
  assert(strcmp(pose_msg.device_id.data, "desk") == 0);
  assert(strcmp(pose_msg.frame.data, "home") == 0);
  assert(pose_msg.stamp.sec == 6);
  assert(pose_msg.stamp.nanosec == 0u);
  assert(pose_msg.pan_deg == 10.0f);
  assert(pose_msg.tilt_deg == 20.0f);
  assert(!pose_msg.moving);

  stackchan::DevicePublisherRegistry registry;
  assert(registry.initialize("desk").ok);
  registry.set_publish_callback(capture_publish);
  assert(registry.publish_motion_pose(pose).ok);
  stackchan::copy_event_string(pose.device_id, sizeof(pose.device_id), "other");
  assert(!registry.publish_motion_pose(pose).ok);

  stackchan::TelemetryPublishScheduler scheduler;
  assert(scheduler.should_publish_proximity(100));
  assert(!scheduler.should_publish_proximity(150));
  assert(scheduler.should_publish_proximity(200));
  assert(scheduler.should_publish_power(100));
  assert(!scheduler.should_publish_power(500));
  assert(scheduler.should_publish_power(1100));
}

}  // namespace

int main() {
  test_device_topic_names_and_validation();
  test_qos_contract();
  test_status_conversion_and_publish_callback();
  test_event_conversion_and_publish_callback();
  test_event_publisher_drain_through_registry();
  test_firmware_ready_event_drain_through_registry();
  test_touch_conversion_bounds_storage();
  test_sensor_and_power_conversions();
  test_head_pose_and_scheduler();
  return 0;
}
