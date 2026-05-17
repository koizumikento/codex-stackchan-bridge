#pragma once

#include <stdint.h>
#include <string.h>

#include "stackchan/contract.hpp"
#include "stackchan/motion_safety.hpp"

namespace stackchan {

constexpr uint32_t kCalibrationMagic = 0x5354434Eu;
constexpr uint16_t kCalibrationSchemaVersion = 1;
constexpr const char* kCalibrationNvsNamespace = "stackchan";
constexpr const char* kCalibrationNvsKey = "calib_v1";
constexpr int16_t kMaxCalibrationCorrection = 30;

struct ServoCalibration {
  int16_t home_x;
  int16_t home_y;
  int16_t correction_x;
  int16_t correction_y;
  int16_t reserved_0;
  int16_t reserved_1;
};

struct CalibrationRecord {
  uint32_t magic;
  uint16_t schema_version;
  uint16_t record_size;
  ServoCalibration servo;
  uint32_t checksum;
};

inline uint32_t calibration_hash_step(uint32_t hash, uint32_t value) {
  hash ^= value & 0xffu;
  hash *= 16777619u;
  hash ^= (value >> 8) & 0xffu;
  hash *= 16777619u;
  hash ^= (value >> 16) & 0xffu;
  hash *= 16777619u;
  hash ^= (value >> 24) & 0xffu;
  hash *= 16777619u;
  return hash;
}

inline uint32_t calibration_checksum_without_checksum(
    const CalibrationRecord& record) {
  uint32_t hash = 2166136261u;
  hash = calibration_hash_step(hash, record.magic);
  hash = calibration_hash_step(hash, record.schema_version);
  hash = calibration_hash_step(hash, record.record_size);
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.home_x));
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.home_y));
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.correction_x));
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.correction_y));
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.reserved_0));
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.reserved_1));
  return hash;
}

inline bool servo_calibration_bounds_are_safe(const ServoCalibration& servo) {
  const int corrected_home_x = servo.home_x + servo.correction_x;
  const int corrected_home_y = servo.home_y + servo.correction_y;
  return servo.home_x >= kDefaultServoLimits.min_x &&
         servo.home_x <= kDefaultServoLimits.max_x &&
         servo.home_y >= kDefaultServoLimits.min_y &&
         servo.home_y <= kDefaultServoLimits.max_y &&
         servo.correction_x >= -kMaxCalibrationCorrection &&
         servo.correction_x <= kMaxCalibrationCorrection &&
         servo.correction_y >= -kMaxCalibrationCorrection &&
         servo.correction_y <= kMaxCalibrationCorrection &&
         corrected_home_x >= kDefaultServoLimits.min_x &&
         corrected_home_x <= kDefaultServoLimits.max_x &&
         corrected_home_y >= kDefaultServoLimits.min_y &&
         corrected_home_y <= kDefaultServoLimits.max_y;
}

inline Result validate_calibration_record(const CalibrationRecord& record) {
  if (record.magic != kCalibrationMagic ||
      record.schema_version != kCalibrationSchemaVersion ||
      record.record_size != sizeof(CalibrationRecord)) {
    return Result::rejected(
        "CALIBRATION_INVALID",
        "calibration schema is missing or unsupported",
        true);
  }
  if (!servo_calibration_bounds_are_safe(record.servo)) {
    return Result::rejected(
        "CALIBRATION_INVALID",
        "calibration servo bounds are unsafe",
        true);
  }
  if (record.checksum != calibration_checksum_without_checksum(record)) {
    return Result::rejected(
        "CALIBRATION_INVALID",
        "calibration checksum mismatch",
        true);
  }
  return Result::accepted("calibration valid");
}

inline CalibrationRecord make_calibration_record(const ServoCalibration& servo) {
  CalibrationRecord record{
      kCalibrationMagic,
      kCalibrationSchemaVersion,
      sizeof(CalibrationRecord),
      servo,
      0,
  };
  record.checksum = calibration_checksum_without_checksum(record);
  return record;
}

class CalibrationStore {
 public:
  CalibrationStore() { reset(); }

  Result load_from_nvs_record(const CalibrationRecord& record) {
    const Result result = validate_calibration_record(record);
    if (!result.ok) {
      reset();
      return result;
    }
    record_ = record;
    valid_ = true;
    return result;
  }

  void reset() {
    memset(&record_, 0, sizeof(record_));
    valid_ = false;
  }

  bool valid() const { return valid_; }

  const CalibrationRecord& record() const { return record_; }

 private:
  CalibrationRecord record_{};
  bool valid_ = false;
};

}  // namespace stackchan
