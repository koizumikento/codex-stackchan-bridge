#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "stackchan/calibration.hpp"

namespace {

void require(bool condition, const char* message) {
  if (!condition) {
    fprintf(stderr, "calibration contract failed: %s\n", message);
    exit(1);
  }
  (void)message;
}

void require_error(
    const stackchan::Result& result,
    const char* code) {
  require(!result.ok, "expected rejection");
  require(strcmp(result.error_code, code) == 0, "unexpected error code");
}

}  // namespace

int main() {
  stackchan::CalibrationStore store;
  require(!store.valid(), "store defaults invalid");

  const stackchan::ServoCalibration valid_servo{
      0,
      45,
      2,
      -2,
      0,
      0,
  };
  const stackchan::CalibrationRecord valid_record =
      stackchan::make_calibration_record(valid_servo);
  stackchan::Result result = store.load_from_nvs_record(valid_record);
  require(result.ok, "valid calibration accepted");
  require(store.valid(), "store valid after valid record");

  stackchan::CalibrationRecord bad_magic = valid_record;
  bad_magic.magic = 0;
  require_error(
      stackchan::validate_calibration_record(bad_magic),
      "CALIBRATION_INVALID");
  result = store.load_from_nvs_record(bad_magic);
  require_error(result, "CALIBRATION_INVALID");
  require(!store.valid(), "invalid load resets store");

  stackchan::CalibrationRecord bad_schema = valid_record;
  bad_schema.schema_version = 99;
  require_error(
      stackchan::validate_calibration_record(bad_schema),
      "CALIBRATION_INVALID");

  stackchan::CalibrationRecord bad_size = valid_record;
  bad_size.record_size = 1;
  require_error(
      stackchan::validate_calibration_record(bad_size),
      "CALIBRATION_INVALID");

  stackchan::CalibrationRecord bad_checksum = valid_record;
  bad_checksum.checksum ^= 1;
  require_error(
      stackchan::validate_calibration_record(bad_checksum),
      "CALIBRATION_INVALID");

  stackchan::ServoCalibration unsafe_home{
      200,
      0,
      0,
      0,
      0,
      0,
  };
  require_error(
      stackchan::validate_calibration_record(
          stackchan::make_calibration_record(unsafe_home)),
      "CALIBRATION_INVALID");

  stackchan::ServoCalibration unsafe_correction{
      110,
      0,
      30,
      0,
      0,
      0,
  };
  require_error(
      stackchan::validate_calibration_record(
          stackchan::make_calibration_record(unsafe_correction)),
      "CALIBRATION_INVALID");

  store.reset();
  require(!store.valid(), "reset invalidates store");

  return 0;
}
