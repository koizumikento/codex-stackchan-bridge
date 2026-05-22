#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "stackchan/contract.hpp"
#include "stackchan/events.hpp"
#include "stackchan/sensors.hpp"

namespace stackchan {

constexpr size_t kRosDeviceIdMaxLength = 32;
constexpr size_t kRosTopicMaxLength = 96;
constexpr size_t kRosSurfaceMaxLength = 32;
constexpr size_t kRosPowerSourceMaxLength = 32;
constexpr size_t kRosFaultCodeMaxLength = 32;
constexpr size_t kRosFrameMaxLength = 16;
constexpr size_t kRosTouchIntensityCapacity = 3;

constexpr const char* kStackchanNamespacePrefix = "/stackchan/";
constexpr const char* kDeviceStatusTopicSuffix = "/device/status";
constexpr const char* kDeviceTouchStateTopicSuffix = "/device/touch/state";
constexpr const char* kDeviceProximityRawTopicSuffix = "/device/proximity/raw";
constexpr const char* kDeviceLightRawTopicSuffix = "/device/light/raw";
constexpr const char* kDevicePowerStatusTopicSuffix = "/device/power/status";
constexpr const char* kDeviceMotionPoseTopicSuffix = "/device/motion/pose";

enum class RosReliability : uint8_t {
  BestEffort = 0,
  Reliable = 1,
};

enum class DevicePublisherTopic : uint8_t {
  Events = 0,
  Status,
  TouchState,
  ProximityRaw,
  LightRaw,
  PowerStatus,
  MotionPose,
  Count,
};

struct DevicePublisherQos {
  RosReliability reliability;
  uint8_t depth;
  bool transient_local;
};

constexpr DevicePublisherQos kDeviceEventsQos{
    RosReliability::Reliable,
    32,
    false};
constexpr DevicePublisherQos kDeviceStatusQos{
    RosReliability::Reliable,
    2,
    false};
constexpr DevicePublisherQos kDeviceTouchStateQos{
    RosReliability::Reliable,
    4,
    false};
constexpr DevicePublisherQos kDeviceProximityRawQos{
    RosReliability::BestEffort,
    10,
    false};
constexpr DevicePublisherQos kDeviceLightRawQos{
    RosReliability::BestEffort,
    5,
    false};
constexpr DevicePublisherQos kDevicePowerStatusQos{
    RosReliability::Reliable,
    2,
    false};
constexpr DevicePublisherQos kDeviceMotionPoseQos{
    RosReliability::Reliable,
    2,
    false};

struct RosTime {
  int32_t sec;
  uint32_t nanosec;
};

template <size_t Capacity>
struct BoundedString {
  char backing[Capacity + 1];
  char* data;
  size_t size;
  size_t capacity;

  BoundedString() : data(backing), size(0), capacity(Capacity) {
    backing[0] = '\0';
  }

  void clear() {
    data[0] = '\0';
    size = 0;
  }

  bool assign(const char* value) {
    const char* source = value == nullptr ? "" : value;
    const size_t length = strlen(source);
    if (length > Capacity) {
      clear();
      return false;
    }
    memcpy(data, source, length);
    data[length] = '\0';
    size = length;
    return true;
  }
};

template <typename T, size_t Capacity>
struct BoundedSequence {
  T backing[Capacity];
  T* data;
  size_t size;
  size_t capacity;

  BoundedSequence() : data(backing), size(0), capacity(Capacity) {}

  void clear() { size = 0; }

  bool assign(const T* values, size_t count) {
    if (count > Capacity) {
      clear();
      return false;
    }
    for (size_t index = 0; index < count; ++index) {
      data[index] = values[index];
    }
    size = count;
    return true;
  }
};

struct StackChanEventMsg {
  BoundedString<kEventIdMaxLength> event_id;
  BoundedString<kEventDeviceIdMaxLength> device_id;
  BoundedString<kEventNameMaxLength> event_name;
  BoundedString<kEventSourceMaxLength> source;
  RosTime stamp;
  BoundedString<kEventCommandIdMaxLength> command_id;
  BoundedString<kEventPayloadJsonMaxLength> payload_json;
};

struct ResultMsg {
  bool ok;
  uint8_t state;
  BoundedString<48> error_code;
  BoundedString<160> message;
  bool recoverable;
};

struct StackChanStatusMsg {
  BoundedString<kRosDeviceIdMaxLength> device_id;
  bool connected;
  BoundedString<kRosSurfaceMaxLength> state;
  BoundedString<kRosSurfaceMaxLength> face;
  BoundedString<kRosSurfaceMaxLength> motion;
  BoundedString<36> last_command_id;
  ResultMsg last_error;
  BoundedString<kRosSurfaceMaxLength> firmware_version;
};

struct StackChanStatusTelemetry {
  const char* device_id;
  bool connected;
  const char* state;
  const char* face;
  const char* motion;
  const char* last_command_id;
  Result last_error;
  const char* firmware_version;
};

struct TouchStateMsg {
  BoundedString<kRosDeviceIdMaxLength> device_id;
  RosTime stamp;
  uint8_t zone_mask;
  uint8_t zone_count;
  BoundedSequence<uint8_t, kRosTouchIntensityCapacity> intensities;
  BoundedString<kRosSurfaceMaxLength> surface;
};

struct ProximityRawMsg {
  BoundedString<kRosDeviceIdMaxLength> device_id;
  RosTime stamp;
  uint8_t sensor_index;
  float distance_m;
  float signal;
  uint16_t raw;
  bool saturated;
};

struct LightRawMsg {
  BoundedString<kRosDeviceIdMaxLength> device_id;
  RosTime stamp;
  uint8_t sensor_index;
  float illuminance_lux;
  uint16_t raw;
  bool saturated;
};

struct PowerStatusMsg {
  BoundedString<kRosDeviceIdMaxLength> device_id;
  RosTime stamp;
  float voltage_v;
  float current_ma;
  float power_mw;
  float percentage;
  uint8_t power_source;
  bool charging;
  bool powered;
  bool low_battery;
  bool brownout_risk;
  BoundedString<kRosFaultCodeMaxLength> fault_code;
};

struct HeadPoseMsg {
  BoundedString<kRosDeviceIdMaxLength> device_id;
  RosTime stamp;
  float pan_deg;
  float tilt_deg;
  bool moving;
  BoundedString<kRosFrameMaxLength> frame;
};

using FirmwarePublishFn = bool (*)(
    DevicePublisherTopic topic,
    const void* message,
    void* context);

inline bool is_valid_device_id_char(char value) {
  return (value >= 'a' && value <= 'z') ||
         (value >= 'A' && value <= 'Z') ||
         (value >= '0' && value <= '9') ||
         value == '_' ||
         value == '-';
}

inline bool is_valid_device_id(const char* device_id) {
  if (device_id == nullptr || device_id[0] == '\0') {
    return false;
  }
  size_t length = 0;
  while (device_id[length] != '\0') {
    if (length >= kRosDeviceIdMaxLength ||
        !is_valid_device_id_char(device_id[length])) {
      return false;
    }
    ++length;
  }
  return true;
}

inline const char* device_topic_suffix(DevicePublisherTopic topic) {
  switch (topic) {
    case DevicePublisherTopic::Events:
      return kDeviceEventsTopicSuffix;
    case DevicePublisherTopic::Status:
      return kDeviceStatusTopicSuffix;
    case DevicePublisherTopic::TouchState:
      return kDeviceTouchStateTopicSuffix;
    case DevicePublisherTopic::ProximityRaw:
      return kDeviceProximityRawTopicSuffix;
    case DevicePublisherTopic::LightRaw:
      return kDeviceLightRawTopicSuffix;
    case DevicePublisherTopic::PowerStatus:
      return kDevicePowerStatusTopicSuffix;
    case DevicePublisherTopic::MotionPose:
      return kDeviceMotionPoseTopicSuffix;
    case DevicePublisherTopic::Count:
      return "";
  }
  return "";
}

inline DevicePublisherQos device_topic_qos(DevicePublisherTopic topic) {
  switch (topic) {
    case DevicePublisherTopic::Events:
      return kDeviceEventsQos;
    case DevicePublisherTopic::Status:
      return kDeviceStatusQos;
    case DevicePublisherTopic::TouchState:
      return kDeviceTouchStateQos;
    case DevicePublisherTopic::ProximityRaw:
      return kDeviceProximityRawQos;
    case DevicePublisherTopic::LightRaw:
      return kDeviceLightRawQos;
    case DevicePublisherTopic::PowerStatus:
      return kDevicePowerStatusQos;
    case DevicePublisherTopic::MotionPose:
      return kDeviceMotionPoseQos;
    case DevicePublisherTopic::Count:
      return {RosReliability::BestEffort, 0, false};
  }
  return {RosReliability::BestEffort, 0, false};
}

inline bool build_device_topic_name(
    const char* device_id,
    DevicePublisherTopic topic,
    char* destination,
    size_t size) {
  if (destination == nullptr || size == 0 || !is_valid_device_id(device_id)) {
    return false;
  }

  const char* suffix = device_topic_suffix(topic);
  if (suffix[0] == '\0') {
    return false;
  }

  const size_t prefix_length = strlen(kStackchanNamespacePrefix);
  const size_t device_id_length = strlen(device_id);
  const size_t suffix_length = strlen(suffix);
  const size_t total_length = prefix_length + device_id_length + suffix_length;
  if (total_length >= size || total_length > kRosTopicMaxLength) {
    destination[0] = '\0';
    return false;
  }

  memcpy(destination, kStackchanNamespacePrefix, prefix_length);
  memcpy(destination + prefix_length, device_id, device_id_length);
  memcpy(destination + prefix_length + device_id_length, suffix, suffix_length);
  destination[total_length] = '\0';
  return true;
}

inline RosTime ros_time_from_ms(uint32_t stamp_ms) {
  return {
      static_cast<int32_t>(stamp_ms / 1000u),
      static_cast<uint32_t>((stamp_ms % 1000u) * 1000000u)};
}

inline uint8_t power_source_value(PowerSource source) {
  switch (source) {
    case PowerSource::Battery:
      return 1;
    case PowerSource::Usb:
      return 2;
    case PowerSource::External:
      return 3;
    case PowerSource::Unknown:
      return 0;
  }
  return 0;
}

inline bool telemetry_device_id_matches(
    const char* configured_device_id,
    const char* telemetry_device_id) {
  return telemetry_device_id == nullptr ||
         telemetry_device_id[0] == '\0' ||
         strcmp(configured_device_id, telemetry_device_id) == 0;
}

inline Result fill_event_message(
    const DeviceEvent& event,
    StackChanEventMsg* message) {
  if (message == nullptr) {
    return Result::rejected("FIRMWARE_BUSY", "event message storage missing", true);
  }
  if (!message->event_id.assign(event.event_id) ||
      !message->device_id.assign(event.device_id) ||
      !message->event_name.assign(event.event_name) ||
      !message->source.assign(event.source) ||
      !message->command_id.assign(event.command_id) ||
      !message->payload_json.assign(event.payload_json)) {
    return Result::rejected(
        "FIRMWARE_BUSY",
        "event message exceeded bounded ROS storage",
        true);
  }
  message->stamp = ros_time_from_ms(event.stamp_ms);
  return Result::accepted("event message converted");
}

inline Result fill_result_message(
    const Result& result,
    ResultMsg* message) {
  if (message == nullptr) {
    return Result::rejected("FIRMWARE_BUSY", "result message storage missing", true);
  }
  if (!message->error_code.assign(result.error_code) ||
      !message->message.assign(result.message)) {
    return Result::rejected(
        "FIRMWARE_BUSY",
        "result message exceeded bounded ROS storage",
        true);
  }
  message->ok = result.ok;
  message->state = static_cast<uint8_t>(result.state);
  message->recoverable = result.recoverable;
  return Result::accepted("result message converted");
}

inline Result fill_stackchan_status_message(
    const char* configured_device_id,
    const StackChanStatusTelemetry& telemetry,
    StackChanStatusMsg* message) {
  if (message == nullptr) {
    return Result::rejected("FIRMWARE_BUSY", "status message storage missing", true);
  }
  const char* status_device_id =
      telemetry.device_id == nullptr || telemetry.device_id[0] == '\0'
          ? configured_device_id
          : telemetry.device_id;
  if (!telemetry_device_id_matches(configured_device_id, status_device_id)) {
    return Result::rejected(
        "INVALID_DEVICE_ID",
        "status telemetry device_id does not match publisher namespace",
        true);
  }
  if (!message->device_id.assign(configured_device_id) ||
      !message->state.assign(telemetry.state) ||
      !message->face.assign(telemetry.face) ||
      !message->motion.assign(telemetry.motion) ||
      !message->last_command_id.assign(telemetry.last_command_id) ||
      !message->firmware_version.assign(telemetry.firmware_version)) {
    return Result::rejected(
        "FIRMWARE_BUSY",
        "status message exceeded bounded ROS storage",
        true);
  }
  Result result = fill_result_message(telemetry.last_error, &message->last_error);
  if (!result.ok) {
    return result;
  }
  message->connected = telemetry.connected;
  return Result::accepted("status message converted");
}

inline Result fill_touch_state_message(
    const char* configured_device_id,
    const TouchStateTelemetry& telemetry,
    TouchStateMsg* message) {
  if (message == nullptr) {
    return Result::rejected("FIRMWARE_BUSY", "touch message storage missing", true);
  }
  const uint8_t zone_count =
      telemetry.zone_count > kRosTouchIntensityCapacity
          ? kRosTouchIntensityCapacity
          : telemetry.zone_count;
  if (!message->device_id.assign(configured_device_id) ||
      !message->surface.assign(telemetry.surface) ||
      !message->intensities.assign(telemetry.intensities, zone_count)) {
    return Result::rejected(
        "FIRMWARE_BUSY",
        "touch message exceeded bounded ROS storage",
        true);
  }
  message->stamp = ros_time_from_ms(telemetry.stamp_ms);
  message->zone_mask = telemetry.zone_mask;
  message->zone_count = zone_count;
  return Result::accepted("touch message converted");
}

inline Result fill_proximity_raw_message(
    const char* configured_device_id,
    const ProximityRawTelemetry& telemetry,
    ProximityRawMsg* message) {
  if (message == nullptr) {
    return Result::rejected("FIRMWARE_BUSY", "proximity message storage missing", true);
  }
  if (!message->device_id.assign(configured_device_id)) {
    return Result::rejected(
        "FIRMWARE_BUSY",
        "proximity message exceeded bounded ROS storage",
        true);
  }
  message->stamp = ros_time_from_ms(telemetry.stamp_ms);
  message->sensor_index = telemetry.sensor_index;
  message->distance_m = telemetry.distance_m;
  message->signal = telemetry.signal;
  message->raw = telemetry.raw;
  message->saturated = telemetry.saturated;
  return Result::accepted("proximity message converted");
}

inline Result fill_light_raw_message(
    const char* configured_device_id,
    const LightRawTelemetry& telemetry,
    LightRawMsg* message) {
  if (message == nullptr) {
    return Result::rejected("FIRMWARE_BUSY", "light message storage missing", true);
  }
  if (!message->device_id.assign(configured_device_id)) {
    return Result::rejected(
        "FIRMWARE_BUSY",
        "light message exceeded bounded ROS storage",
        true);
  }
  message->stamp = ros_time_from_ms(telemetry.stamp_ms);
  message->sensor_index = telemetry.sensor_index;
  message->illuminance_lux = telemetry.illuminance_lux;
  message->raw = telemetry.raw;
  message->saturated = telemetry.saturated;
  return Result::accepted("light message converted");
}

inline Result fill_power_status_message(
    const char* configured_device_id,
    const PowerStatusTelemetry& telemetry,
    PowerStatusMsg* message) {
  if (message == nullptr) {
    return Result::rejected("FIRMWARE_BUSY", "power message storage missing", true);
  }
  if (!message->device_id.assign(configured_device_id) ||
      !message->fault_code.assign(telemetry.fault_code)) {
    return Result::rejected(
        "FIRMWARE_BUSY",
        "power message exceeded bounded ROS storage",
        true);
  }
  message->stamp = ros_time_from_ms(telemetry.stamp_ms);
  message->voltage_v = telemetry.voltage_v;
  message->current_ma = telemetry.current_ma;
  message->power_mw = telemetry.power_mw;
  message->percentage = telemetry.percentage;
  message->power_source = power_source_value(telemetry.power_source);
  message->charging = telemetry.charging;
  message->powered = telemetry.powered;
  message->low_battery = telemetry.low_battery;
  message->brownout_risk = telemetry.brownout_risk;
  return Result::accepted("power message converted");
}

inline Result fill_head_pose_message(
    const char* configured_device_id,
    const HeadPoseTelemetry& telemetry,
    HeadPoseMsg* message) {
  if (message == nullptr) {
    return Result::rejected("FIRMWARE_BUSY", "head pose message storage missing", true);
  }
  if (!message->device_id.assign(configured_device_id) ||
      !message->frame.assign(telemetry.frame)) {
    return Result::rejected(
        "FIRMWARE_BUSY",
        "head pose message exceeded bounded ROS storage",
        true);
  }
  message->stamp = ros_time_from_ms(telemetry.stamp_ms);
  message->pan_deg = telemetry.pan_deg;
  message->tilt_deg = telemetry.tilt_deg;
  message->moving = telemetry.moving;
  return Result::accepted("head pose message converted");
}

class DevicePublisherRegistry {
 public:
  Result initialize(const char* device_id) {
    if (!is_valid_device_id(device_id)) {
      initialized_ = false;
      return Result::rejected(
          "INVALID_DEVICE_ID",
          "configured STACKCHAN_DEVICE_ID is invalid",
          true);
    }
    copy_event_string(device_id_, sizeof(device_id_), device_id);
    for (uint8_t index = 0;
         index < static_cast<uint8_t>(DevicePublisherTopic::Count);
         ++index) {
      const DevicePublisherTopic topic =
          static_cast<DevicePublisherTopic>(index);
      if (!build_device_topic_name(
              device_id_,
              topic,
              topic_names_[index],
              sizeof(topic_names_[index]))) {
        initialized_ = false;
        return Result::rejected(
            "INVALID_DEVICE_ID",
            "device topic name could not be constructed",
            true);
      }
      qos_[index] = device_topic_qos(topic);
    }
    initialized_ = true;
    return Result::accepted("device publishers initialized");
  }

  void set_publish_callback(FirmwarePublishFn callback, void* context = nullptr) {
    callback_ = callback;
    context_ = context;
  }

  bool initialized() const { return initialized_; }

  const char* device_id() const { return device_id_; }

  const char* topic_name(DevicePublisherTopic topic) const {
    return topic_names_[static_cast<uint8_t>(topic)];
  }

  DevicePublisherQos qos(DevicePublisherTopic topic) const {
    return qos_[static_cast<uint8_t>(topic)];
  }

  Result publish_event(const DeviceEvent& event) {
    if (strcmp(event.device_id, device_id_) != 0) {
      return Result::rejected(
          "INVALID_DEVICE_ID",
          "event device_id does not match publisher namespace",
          true);
    }
    Result result = fill_event_message(event, &event_message_);
    if (!result.ok) {
      return result;
    }
    return publish(DevicePublisherTopic::Events, &event_message_);
  }

  Result publish_status(const StackChanStatusTelemetry& telemetry) {
    Result result =
        fill_stackchan_status_message(device_id_, telemetry, &status_message_);
    if (!result.ok) {
      return result;
    }
    return publish(DevicePublisherTopic::Status, &status_message_);
  }

  Result publish_touch_state(const TouchStateTelemetry& telemetry) {
    if (!telemetry_device_id_matches(device_id_, telemetry.device_id)) {
      return Result::rejected(
          "INVALID_DEVICE_ID",
          "touch telemetry device_id does not match publisher namespace",
          true);
    }
    Result result =
        fill_touch_state_message(device_id_, telemetry, &touch_state_message_);
    if (!result.ok) {
      return result;
    }
    return publish(DevicePublisherTopic::TouchState, &touch_state_message_);
  }

  Result publish_proximity_raw(const ProximityRawTelemetry& telemetry) {
    if (!telemetry_device_id_matches(device_id_, telemetry.device_id)) {
      return Result::rejected(
          "INVALID_DEVICE_ID",
          "proximity telemetry device_id does not match publisher namespace",
          true);
    }
    Result result =
        fill_proximity_raw_message(device_id_, telemetry, &proximity_raw_message_);
    if (!result.ok) {
      return result;
    }
    return publish(DevicePublisherTopic::ProximityRaw, &proximity_raw_message_);
  }

  Result publish_light_raw(const LightRawTelemetry& telemetry) {
    if (!telemetry_device_id_matches(device_id_, telemetry.device_id)) {
      return Result::rejected(
          "INVALID_DEVICE_ID",
          "light telemetry device_id does not match publisher namespace",
          true);
    }
    Result result =
        fill_light_raw_message(device_id_, telemetry, &light_raw_message_);
    if (!result.ok) {
      return result;
    }
    return publish(DevicePublisherTopic::LightRaw, &light_raw_message_);
  }

  Result publish_power_status(const PowerStatusTelemetry& telemetry) {
    if (!telemetry_device_id_matches(device_id_, telemetry.device_id)) {
      return Result::rejected(
          "INVALID_DEVICE_ID",
          "power telemetry device_id does not match publisher namespace",
          true);
    }
    Result result =
        fill_power_status_message(device_id_, telemetry, &power_status_message_);
    if (!result.ok) {
      return result;
    }
    return publish(DevicePublisherTopic::PowerStatus, &power_status_message_);
  }

  Result publish_motion_pose(const HeadPoseTelemetry& telemetry) {
    if (!telemetry_device_id_matches(device_id_, telemetry.device_id)) {
      return Result::rejected(
          "INVALID_DEVICE_ID",
          "head pose telemetry device_id does not match publisher namespace",
          true);
    }
    Result result =
        fill_head_pose_message(device_id_, telemetry, &head_pose_message_);
    if (!result.ok) {
      return result;
    }
    return publish(DevicePublisherTopic::MotionPose, &head_pose_message_);
  }

 private:
  char device_id_[kRosDeviceIdMaxLength + 1]{};
  char topic_names_[static_cast<uint8_t>(DevicePublisherTopic::Count)]
                   [kRosTopicMaxLength + 1]{};
  DevicePublisherQos qos_[static_cast<uint8_t>(DevicePublisherTopic::Count)]{};
  bool initialized_ = false;
  FirmwarePublishFn callback_ = nullptr;
  void* context_ = nullptr;
  StackChanEventMsg event_message_{};
  StackChanStatusMsg status_message_{};
  TouchStateMsg touch_state_message_{};
  ProximityRawMsg proximity_raw_message_{};
  LightRawMsg light_raw_message_{};
  PowerStatusMsg power_status_message_{};
  HeadPoseMsg head_pose_message_{};

  Result publish(DevicePublisherTopic topic, const void* message) {
    if (!initialized_ || callback_ == nullptr) {
      return Result::rejected(
          "TRANSPORT_DISCONNECTED",
          "device publisher is unavailable",
          true);
    }
    if (!callback_(topic, message, context_)) {
      return Result::rejected(
          "FIRMWARE_BUSY",
          "device publisher rejected the message",
          true);
    }
    return Result::accepted("device message published");
  }
};

class TelemetryPublishScheduler {
 public:
  bool should_publish_touch(uint32_t now_ms) {
    return should_publish(now_ms, kTouchMinIntervalMs, &last_touch_ms_);
  }

  bool should_publish_proximity(uint32_t now_ms) {
    return should_publish(now_ms, kProximityMinIntervalMs, &last_proximity_ms_);
  }

  bool should_publish_light(uint32_t now_ms) {
    return should_publish(now_ms, kLightMinIntervalMs, &last_light_ms_);
  }

  bool should_publish_power(uint32_t now_ms) {
    return should_publish(now_ms, kPowerMinIntervalMs, &last_power_ms_);
  }

  bool should_publish_motion_pose(uint32_t now_ms) {
    return should_publish(
        now_ms,
        kMotionPoseMinIntervalMs,
        &last_motion_pose_ms_);
  }

 private:
  static constexpr uint32_t kTouchMinIntervalMs = 100;
  static constexpr uint32_t kProximityMinIntervalMs = 100;
  static constexpr uint32_t kLightMinIntervalMs = 200;
  static constexpr uint32_t kPowerMinIntervalMs = 1000;
  static constexpr uint32_t kMotionPoseMinIntervalMs = 100;

  uint32_t last_touch_ms_ = 0;
  uint32_t last_proximity_ms_ = 0;
  uint32_t last_light_ms_ = 0;
  uint32_t last_power_ms_ = 0;
  uint32_t last_motion_pose_ms_ = 0;

  bool should_publish(
      uint32_t now_ms,
      uint32_t min_interval_ms,
      uint32_t* last_ms) {
    if (*last_ms == 0 || now_ms - *last_ms >= min_interval_ms) {
      *last_ms = now_ms;
      return true;
    }
    return false;
  }
};

}  // namespace stackchan
