#pragma once

#include <stdint.h>
#include <string.h>

#include "stackchan/contract.hpp"

namespace stackchan {

constexpr uint32_t kCalibrationMagic = 0x5354434Eu;
constexpr uint16_t kCalibrationSchemaVersion = 1;
constexpr const char* kCalibrationNvsNamespace = "stackchan";
constexpr const char* kCalibrationNvsKey = "calib_v1";

struct ServoCalibration {
  int16_t min_x;
  int16_t max_x;
  int16_t home_x;
  int16_t min_y;
  int16_t max_y;
  int16_t home_y;
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
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.min_x));
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.max_x));
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.home_x));
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.min_y));
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.max_y));
  hash = calibration_hash_step(hash, static_cast<uint16_t>(record.servo.home_y));
  return hash;
}

inline bool servo_calibration_bounds_are_safe(const ServoCalibration& servo) {
  return servo.min_x < servo.home_x &&
         servo.home_x < servo.max_x &&
         servo.min_y < servo.home_y &&
         servo.home_y < servo.max_y &&
         servo.min_x >= -180 &&
         servo.max_x <= 180 &&
         servo.min_y >= -180 &&
         servo.max_y <= 180;
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
