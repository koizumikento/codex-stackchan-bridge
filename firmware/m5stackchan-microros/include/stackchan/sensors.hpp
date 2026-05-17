#pragma once

#include <stdint.h>
#include <string.h>

#include "stackchan/contract.hpp"
#include "stackchan/events.hpp"

namespace stackchan {

constexpr float kImuMinHz = 10.0f;
constexpr float kImuMaxHz = 30.0f;
constexpr uint16_t kCameraWidth = 320;
constexpr uint16_t kCameraHeight = 240;
constexpr uint8_t kCameraMinQuality = 1;
constexpr uint8_t kCameraMaxQuality = 95;
constexpr uint32_t kCameraMaxPayloadBytes = 98304;
constexpr uint16_t kButtonDebounceMs = 30;
constexpr uint16_t kButtonHeldMs = 700;
constexpr float kImuPlacedDownGravityMin = 7.0f;
constexpr float kImuPickedUpGravityMax = 5.0f;
constexpr float kImuTiltHorizontalMin = 6.0f;
constexpr float kImuTiltVerticalMax = 7.0f;
constexpr float kImuFaceDirectionMin = 7.0f;
constexpr float kImuShakenGyroMin = 6.0f;
constexpr uint16_t kImuShakenCooldownMs = 500;

struct ImuSample {
  float accel_x;
  float accel_y;
  float accel_z;
  float gyro_x;
  float gyro_y;
  float gyro_z;
};

inline float abs_float(float value) {
  return value < 0.0f ? -value : value;
}

inline float max_float(float left, float right) {
  return left > right ? left : right;
}

inline Result validate_camera_quality(uint8_t quality) {
  if (quality < kCameraMinQuality || quality > kCameraMaxQuality) {
    return Result::rejected(
        "CAMERA_CAPTURE_FAILED",
        "camera JPEG quality out of range",
        true);
  }
  return Result::accepted("camera capture accepted");
}

inline Result validate_imu_rate(float hz) {
  if (hz < kImuMinHz || hz > kImuMaxHz) {
    return Result::rejected(
        "UNSUPPORTED_FEATURE",
        "IMU stream rate must be between 10 and 30 Hz");
  }
  return Result::accepted("IMU stream accepted");
}

inline Result nfc_read_failed() {
  return Result::rejected("NFC_READ_FAILED", "NFC read failed", true);
}

class ButtonEventEstimator {
 public:
  Result update(
      bool pressed,
      uint32_t now_ms,
      EventPublisher& events,
      const char* button_id = "main") {
    if (pressed != raw_pressed_) {
      raw_pressed_ = pressed;
      raw_changed_ms_ = now_ms;
      return Result::accepted("button debounce pending");
    }

    if (pressed != stable_pressed_ && now_ms - raw_changed_ms_ >= kButtonDebounceMs) {
      stable_pressed_ = pressed;
      if (stable_pressed_) {
        pressed_since_ms_ = now_ms;
        held_emitted_ = false;
        return events.button_pressed(now_ms, button_id);
      }

      held_emitted_ = false;
      return events.button_released(now_ms, button_id);
    }

    if (stable_pressed_ && !held_emitted_ &&
        now_ms - pressed_since_ms_ >= kButtonHeldMs) {
      held_emitted_ = true;
      return events.button_held(now_ms, button_id);
    }

    return Result::accepted("no button event");
  }

 private:
  bool raw_pressed_ = false;
  bool stable_pressed_ = false;
  bool held_emitted_ = false;
  uint32_t raw_changed_ms_ = 0;
  uint32_t pressed_since_ms_ = 0;
};

class NfcPresenceEstimator {
 public:
  Result update(
      bool present,
      const char* tag_id,
      uint32_t now_ms,
      EventPublisher& events) {
    const char* safe_tag_id = tag_id == nullptr ? "" : tag_id;
    if (present && (!present_ || strcmp(safe_tag_id, last_tag_id_) != 0)) {
      present_ = true;
      copy_event_string(last_tag_id_, sizeof(last_tag_id_), safe_tag_id);
      return events.nfc_detected(now_ms, last_tag_id_);
    }

    if (!present && present_) {
      present_ = false;
      Result result = events.nfc_removed(now_ms, last_tag_id_);
      copy_event_string(last_tag_id_, sizeof(last_tag_id_), "");
      return result;
    }

    return Result::accepted("no NFC event");
  }

 private:
  bool present_ = false;
  char last_tag_id_[65]{};
};

class ImuEventEstimator {
 public:
  Result update(
      const ImuSample& sample,
      uint32_t now_ms,
      EventPublisher& events) {
    const float abs_accel_z = abs_float(sample.accel_z);
    const float max_horizontal =
        max_float(abs_float(sample.accel_x), abs_float(sample.accel_y));
    const float max_gyro = max_float(
        max_float(abs_float(sample.gyro_x), abs_float(sample.gyro_y)),
        abs_float(sample.gyro_z));

    if (max_gyro >= kImuShakenGyroMin &&
        (!shaken_emitted_ || now_ms - last_shaken_ms_ >= kImuShakenCooldownMs)) {
      shaken_emitted_ = true;
      last_shaken_ms_ = now_ms;
      return events.publish(DeviceEventKind::Shaken, now_ms);
    }

    if (!picked_up_ && abs_accel_z <= kImuPickedUpGravityMax) {
      picked_up_ = true;
      return events.publish(DeviceEventKind::PickedUp, now_ms);
    }

    if (picked_up_ && abs_accel_z >= kImuPlacedDownGravityMin) {
      picked_up_ = false;
      return events.publish(DeviceEventKind::PlacedDown, now_ms);
    }

    if (!tilted_ && max_horizontal >= kImuTiltHorizontalMin &&
        abs_accel_z <= kImuTiltVerticalMax) {
      tilted_ = true;
      return events.publish(DeviceEventKind::Tilted, now_ms);
    }

    if (tilted_ && max_horizontal < kImuTiltHorizontalMin) {
      tilted_ = false;
    }

    if (!face_up_ && sample.accel_z >= kImuFaceDirectionMin) {
      face_up_ = true;
      face_down_ = false;
      return events.publish(DeviceEventKind::FaceUp, now_ms);
    }

    if (!face_down_ && sample.accel_z <= -kImuFaceDirectionMin) {
      face_down_ = true;
      face_up_ = false;
      return events.publish(DeviceEventKind::FaceDown, now_ms);
    }

    return Result::accepted("no IMU event");
  }

 private:
  bool picked_up_ = false;
  bool tilted_ = false;
  bool face_up_ = false;
  bool face_down_ = false;
  bool shaken_emitted_ = false;
  uint32_t last_shaken_ms_ = 0;
};

}  // namespace stackchan
