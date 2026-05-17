#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "stackchan/contract.hpp"

namespace stackchan {

constexpr size_t kEventDeviceIdMaxLength = 32;
constexpr size_t kEventIdMaxLength = 36;
constexpr size_t kEventNameMaxLength = 32;
constexpr size_t kEventSourceMaxLength = 32;
constexpr size_t kEventCommandIdMaxLength = 36;
constexpr size_t kEventPayloadJsonMaxLength = 256;
constexpr size_t kEventQueueCapacity = 8;
constexpr const char* kDeviceEventsTopicSuffix = "/device/events";
constexpr const char* kFirmwareEventSource = "firmware";

enum class DeviceEventKind : uint8_t {
  ButtonPressed,
  ButtonReleased,
  ButtonHeld,
  PickedUp,
  PlacedDown,
  Shaken,
  Tilted,
  FaceUp,
  FaceDown,
  NfcDetected,
  NfcRemoved,
  NfcReadFailed,
  MicOverrun,
  AudioPlaybackUnderrun,
  AudioCaptureStarted,
  AudioCaptureFinished,
  AudioCaptureFailed,
  CameraCaptureFailed,
  BatteryLow,
  BatteryRecovered,
  ChargingStarted,
  ChargingStopped,
  PowerSourceChanged,
  BrownoutRisk,
  PowerFault,
  Touched,
  TouchReleased,
  TouchHeld,
  ProximityNear,
  ProximityClear,
  LightChanged,
  DarkDetected,
  BrightDetected,
  RemoteButtonPressed,
  RemoteButtonReleased,
  RemoteButtonHeld,
  RemoteCommandReceived,
  IrTransmitStarted,
  IrTransmitFinished,
  IrTransmitFailed,
  TransportUnstable,
};

struct DeviceEvent {
  char event_id[kEventIdMaxLength + 1];
  char device_id[kEventDeviceIdMaxLength + 1];
  char event_name[kEventNameMaxLength + 1];
  char source[kEventSourceMaxLength + 1];
  uint32_t stamp_ms;
  char command_id[kEventCommandIdMaxLength + 1];
  char payload_json[kEventPayloadJsonMaxLength + 1];
};

using EventPublishFn = bool (*)(const DeviceEvent& event, void* context);

inline const char* device_event_name(DeviceEventKind kind) {
  switch (kind) {
    case DeviceEventKind::ButtonPressed:
      return "button_pressed";
    case DeviceEventKind::ButtonReleased:
      return "button_released";
    case DeviceEventKind::ButtonHeld:
      return "button_held";
    case DeviceEventKind::PickedUp:
      return "picked_up";
    case DeviceEventKind::PlacedDown:
      return "placed_down";
    case DeviceEventKind::Shaken:
      return "shaken";
    case DeviceEventKind::Tilted:
      return "tilted";
    case DeviceEventKind::FaceUp:
      return "face_up";
    case DeviceEventKind::FaceDown:
      return "face_down";
    case DeviceEventKind::NfcDetected:
      return "nfc_detected";
    case DeviceEventKind::NfcRemoved:
      return "nfc_removed";
    case DeviceEventKind::NfcReadFailed:
      return "nfc_read_failed";
    case DeviceEventKind::MicOverrun:
      return "mic_overrun";
    case DeviceEventKind::AudioPlaybackUnderrun:
      return "audio_playback_underrun";
    case DeviceEventKind::AudioCaptureStarted:
      return "audio_capture_started";
    case DeviceEventKind::AudioCaptureFinished:
      return "audio_capture_finished";
    case DeviceEventKind::AudioCaptureFailed:
      return "audio_capture_failed";
    case DeviceEventKind::CameraCaptureFailed:
      return "camera_capture_failed";
    case DeviceEventKind::BatteryLow:
      return "battery_low";
    case DeviceEventKind::BatteryRecovered:
      return "battery_recovered";
    case DeviceEventKind::ChargingStarted:
      return "charging_started";
    case DeviceEventKind::ChargingStopped:
      return "charging_stopped";
    case DeviceEventKind::PowerSourceChanged:
      return "power_source_changed";
    case DeviceEventKind::BrownoutRisk:
      return "brownout_risk";
    case DeviceEventKind::PowerFault:
      return "power_fault";
    case DeviceEventKind::Touched:
      return "touched";
    case DeviceEventKind::TouchReleased:
      return "touch_released";
    case DeviceEventKind::TouchHeld:
      return "touch_held";
    case DeviceEventKind::ProximityNear:
      return "proximity_near";
    case DeviceEventKind::ProximityClear:
      return "proximity_clear";
    case DeviceEventKind::LightChanged:
      return "light_changed";
    case DeviceEventKind::DarkDetected:
      return "dark_detected";
    case DeviceEventKind::BrightDetected:
      return "bright_detected";
    case DeviceEventKind::RemoteButtonPressed:
      return "remote_button_pressed";
    case DeviceEventKind::RemoteButtonReleased:
      return "remote_button_released";
    case DeviceEventKind::RemoteButtonHeld:
      return "remote_button_held";
    case DeviceEventKind::RemoteCommandReceived:
      return "remote_command_received";
    case DeviceEventKind::IrTransmitStarted:
      return "ir_transmit_started";
    case DeviceEventKind::IrTransmitFinished:
      return "ir_transmit_finished";
    case DeviceEventKind::IrTransmitFailed:
      return "ir_transmit_failed";
    case DeviceEventKind::TransportUnstable:
      return "transport_unstable";
  }
  return "";
}

inline bool is_firmware_device_event_name(const char* name) {
  if (name == nullptr) {
    return false;
  }
  return strcmp(name, "button_pressed") == 0 ||
         strcmp(name, "button_released") == 0 ||
         strcmp(name, "button_held") == 0 ||
         strcmp(name, "picked_up") == 0 ||
         strcmp(name, "placed_down") == 0 ||
         strcmp(name, "shaken") == 0 ||
         strcmp(name, "tilted") == 0 ||
         strcmp(name, "face_up") == 0 ||
         strcmp(name, "face_down") == 0 ||
         strcmp(name, "nfc_detected") == 0 ||
         strcmp(name, "nfc_removed") == 0 ||
         strcmp(name, "nfc_read_failed") == 0 ||
         strcmp(name, "mic_overrun") == 0 ||
         strcmp(name, "audio_playback_underrun") == 0 ||
         strcmp(name, "audio_capture_started") == 0 ||
         strcmp(name, "audio_capture_finished") == 0 ||
         strcmp(name, "audio_capture_failed") == 0 ||
         strcmp(name, "camera_capture_failed") == 0 ||
         strcmp(name, "battery_low") == 0 ||
         strcmp(name, "battery_recovered") == 0 ||
         strcmp(name, "charging_started") == 0 ||
         strcmp(name, "charging_stopped") == 0 ||
         strcmp(name, "power_source_changed") == 0 ||
         strcmp(name, "brownout_risk") == 0 ||
         strcmp(name, "power_fault") == 0 ||
         strcmp(name, "touched") == 0 ||
         strcmp(name, "touch_released") == 0 ||
         strcmp(name, "touch_held") == 0 ||
         strcmp(name, "proximity_near") == 0 ||
         strcmp(name, "proximity_clear") == 0 ||
         strcmp(name, "light_changed") == 0 ||
         strcmp(name, "dark_detected") == 0 ||
         strcmp(name, "bright_detected") == 0 ||
         strcmp(name, "remote_button_pressed") == 0 ||
         strcmp(name, "remote_button_released") == 0 ||
         strcmp(name, "remote_button_held") == 0 ||
         strcmp(name, "remote_command_received") == 0 ||
         strcmp(name, "ir_transmit_started") == 0 ||
         strcmp(name, "ir_transmit_finished") == 0 ||
         strcmp(name, "ir_transmit_failed") == 0 ||
         strcmp(name, "transport_unstable") == 0;
}

inline void copy_event_string(char* destination, size_t size, const char* source) {
  if (size == 0) {
    return;
  }
  strncpy(destination, source == nullptr ? "" : source, size - 1);
  destination[size - 1] = '\0';
}

inline bool event_payload_json_fits(const char* payload_json) {
  return payload_json == nullptr ||
         strlen(payload_json) <= kEventPayloadJsonMaxLength;
}

inline bool is_priority_device_event_name(const char* name) {
  if (name == nullptr) {
    return false;
  }
  return strcmp(name, "mic_overrun") == 0 ||
         strcmp(name, "audio_playback_underrun") == 0 ||
         strcmp(name, "audio_capture_failed") == 0 ||
         strcmp(name, "camera_capture_failed") == 0 ||
         strcmp(name, "battery_low") == 0 ||
         strcmp(name, "brownout_risk") == 0 ||
         strcmp(name, "power_fault") == 0 ||
         strcmp(name, "transport_unstable") == 0;
}

inline char safe_json_char(char value) {
  const unsigned char byte = static_cast<unsigned char>(value);
  if (byte < 0x20 || byte > 0x7e || value == '"' || value == '\\') {
    return '_';
  }
  return value;
}

inline void sanitize_json_value(
    char* destination,
    size_t size,
    const char* value) {
  if (size == 0) {
    return;
  }

  const char* source = value == nullptr ? "" : value;
  size_t index = 0;
  while (source[index] != '\0' && index < size - 1) {
    destination[index] = safe_json_char(source[index]);
    ++index;
  }
  destination[index] = '\0';
}

inline void make_string_payload(
    char* destination,
    size_t size,
    const char* key,
    const char* value) {
  if (size == 0) {
    return;
  }

  char safe_value[kEventPayloadJsonMaxLength + 1];
  const char* safe_key = key == nullptr ? "value" : key;
  const size_t key_length = strlen(safe_key);
  const size_t max_payload_length = size - 1;
  if (key_length + 7 >= max_payload_length) {
    copy_event_string(
        destination,
        size,
        "{\"truncated\":true,\"reason\":\"payload_json_key_too_long\"}");
    return;
  }
  const size_t max_value_length = max_payload_length - key_length - 7;
  sanitize_json_value(safe_value, max_value_length + 1, value);
  snprintf(
      destination,
      size,
      "{\"%s\":\"%s\"}",
      safe_key,
      safe_value);
  destination[size - 1] = '\0';
}

class EventPublisher {
 public:
  explicit EventPublisher(const char* device_id) { set_device_id(device_id); }

  void set_device_id(const char* device_id) {
    copy_event_string(device_id_, sizeof(device_id_), device_id);
  }

  void set_callback(EventPublishFn callback, void* context = nullptr) {
    callback_ = callback;
    context_ = context;
  }

  size_t queued_count() const { return count_; }
  size_t dropped_low_priority_count() const {
    return dropped_low_priority_count_;
  }

  Result drain(size_t max_events = kEventQueueCapacity) {
    if (callback_ == nullptr) {
      return Result::rejected(
          "TRANSPORT_DISCONNECTED",
          "device event publisher callback is not configured",
          true);
    }

    size_t drained = 0;
    while (count_ > 0 && drained < max_events) {
      if (!callback_(queue_[head_], context_)) {
        return Result::rejected(
            "FIRMWARE_BUSY",
            "event publisher callback rejected the event",
            true);
      }
      head_ = (head_ + 1) % kEventQueueCapacity;
      --count_;
      ++drained;
    }
    return Result::accepted("events drained");
  }

  Result publish(
      DeviceEventKind kind,
      uint32_t stamp_ms,
      const char* command_id = "",
      const char* payload_json = "{}") {
    return publish_name(device_event_name(kind), stamp_ms, command_id, payload_json);
  }

  Result publish_name(
      const char* event_name,
      uint32_t stamp_ms,
      const char* command_id = "",
      const char* payload_json = "{}") {
    if (!is_firmware_device_event_name(event_name)) {
      return Result::rejected("UNKNOWN_COMMAND", "unknown firmware event name");
    }
    if (!event_payload_json_fits(payload_json)) {
      return Result::rejected(
          "UNSUPPORTED_FEATURE",
          "event payload_json exceeds 256 bytes",
          true);
    }

    DeviceEvent event{};
    copy_event_string(event.event_id, sizeof(event.event_id), "");
    copy_event_string(event.device_id, sizeof(event.device_id), device_id_);
    copy_event_string(event.event_name, sizeof(event.event_name), event_name);
    copy_event_string(event.source, sizeof(event.source), kFirmwareEventSource);
    event.stamp_ms = stamp_ms;
    copy_event_string(event.command_id, sizeof(event.command_id), command_id);
    copy_event_string(
        event.payload_json,
        sizeof(event.payload_json),
        payload_json == nullptr ? "{}" : payload_json);

    if (count_ >= kEventQueueCapacity &&
        (!is_priority_device_event_name(event_name) ||
         !drop_oldest_low_priority_event())) {
      return Result::rejected(
          "FIRMWARE_BUSY",
          "device event queue is full",
          true);
    }
    const size_t tail = (head_ + count_) % kEventQueueCapacity;
    queue_[tail] = event;
    ++count_;
    return Result::accepted("event accepted");
  }

  Result button_pressed(
      uint32_t stamp_ms,
      const char* button_id = "main") {
    char payload[kEventPayloadJsonMaxLength + 1];
    make_string_payload(payload, sizeof(payload), "button", button_id);
    return publish(DeviceEventKind::ButtonPressed, stamp_ms, "", payload);
  }

  Result button_released(
      uint32_t stamp_ms,
      const char* button_id = "main") {
    char payload[kEventPayloadJsonMaxLength + 1];
    make_string_payload(payload, sizeof(payload), "button", button_id);
    return publish(DeviceEventKind::ButtonReleased, stamp_ms, "", payload);
  }

  Result button_held(uint32_t stamp_ms, const char* button_id = "main") {
    char payload[kEventPayloadJsonMaxLength + 1];
    make_string_payload(payload, sizeof(payload), "button", button_id);
    return publish(DeviceEventKind::ButtonHeld, stamp_ms, "", payload);
  }

  Result nfc_detected(uint32_t stamp_ms, const char* tag_id) {
    char payload[kEventPayloadJsonMaxLength + 1];
    make_string_payload(payload, sizeof(payload), "tag_id", tag_id);
    return publish(DeviceEventKind::NfcDetected, stamp_ms, "", payload);
  }

  Result nfc_removed(uint32_t stamp_ms, const char* tag_id) {
    char payload[kEventPayloadJsonMaxLength + 1];
    make_string_payload(payload, sizeof(payload), "tag_id", tag_id);
    return publish(DeviceEventKind::NfcRemoved, stamp_ms, "", payload);
  }

  Result nfc_read_failed(uint32_t stamp_ms, const char* reason = "") {
    char payload[kEventPayloadJsonMaxLength + 1];
    make_string_payload(payload, sizeof(payload), "reason", reason);
    return publish(DeviceEventKind::NfcReadFailed, stamp_ms, "", payload);
  }

  Result mic_overrun(uint32_t stamp_ms, const char* command_id = "") {
    return publish(DeviceEventKind::MicOverrun, stamp_ms, command_id);
  }

  Result audio_playback_underrun(
      uint32_t stamp_ms,
      const char* command_id = "") {
    return publish(DeviceEventKind::AudioPlaybackUnderrun, stamp_ms, command_id);
  }

  Result audio_capture_started(
      uint32_t stamp_ms,
      const char* command_id = "") {
    return publish(DeviceEventKind::AudioCaptureStarted, stamp_ms, command_id);
  }

  Result audio_capture_finished(
      uint32_t stamp_ms,
      const char* command_id = "") {
    return publish(DeviceEventKind::AudioCaptureFinished, stamp_ms, command_id);
  }

  Result audio_capture_failed(uint32_t stamp_ms, const char* command_id = "") {
    return publish(DeviceEventKind::AudioCaptureFailed, stamp_ms, command_id);
  }

  Result power_fault(uint32_t stamp_ms, const char* fault_code) {
    char payload[kEventPayloadJsonMaxLength + 1];
    make_string_payload(payload, sizeof(payload), "fault_code", fault_code);
    return publish(DeviceEventKind::PowerFault, stamp_ms, "", payload);
  }

  Result remote_command_received(uint32_t stamp_ms, const char* command) {
    char payload[kEventPayloadJsonMaxLength + 1];
    make_string_payload(payload, sizeof(payload), "command", command);
    return publish(DeviceEventKind::RemoteCommandReceived, stamp_ms, "", payload);
  }

 private:
  char device_id_[kEventDeviceIdMaxLength + 1]{};
  DeviceEvent queue_[kEventQueueCapacity]{};
  size_t head_ = 0;
  size_t count_ = 0;
  size_t dropped_low_priority_count_ = 0;
  EventPublishFn callback_ = nullptr;
  void* context_ = nullptr;

  bool drop_oldest_low_priority_event() {
    for (size_t offset = 0; offset < count_; ++offset) {
      const size_t index = (head_ + offset) % kEventQueueCapacity;
      if (is_priority_device_event_name(queue_[index].event_name)) {
        continue;
      }
      for (size_t shift = offset; shift + 1 < count_; ++shift) {
        const size_t current = (head_ + shift) % kEventQueueCapacity;
        const size_t next = (head_ + shift + 1) % kEventQueueCapacity;
        queue_[current] = queue_[next];
      }
      --count_;
      ++dropped_low_priority_count_;
      return true;
    }
    return false;
  }
};

}  // namespace stackchan
