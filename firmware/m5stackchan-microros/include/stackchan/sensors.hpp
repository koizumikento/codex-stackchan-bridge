#pragma once

#include <stdint.h>

#include "stackchan/contract.hpp"

namespace stackchan {

constexpr float kImuMinHz = 10.0f;
constexpr float kImuMaxHz = 30.0f;
constexpr uint16_t kCameraWidth = 320;
constexpr uint16_t kCameraHeight = 240;
constexpr uint8_t kCameraMinQuality = 1;
constexpr uint8_t kCameraMaxQuality = 95;
constexpr uint32_t kCameraMaxPayloadBytes = 98304;

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

}  // namespace stackchan
