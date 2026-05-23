#pragma once

#include <string.h>

#include "stackchan/contract.hpp"

namespace stackchan {

struct ServoLimits {
  int min_x;
  int max_x;
  int min_y;
  int max_y;
};

struct ServoTarget {
  int x;
  int y;
};

struct HeadPoseLimits {
  float min_pan_deg;
  float max_pan_deg;
  float min_tilt_deg;
  float max_tilt_deg;
  uint16_t min_speed;
  uint16_t max_speed;
  uint32_t min_nonzero_duration_ms;
  uint32_t max_duration_ms;
  uint32_t min_command_interval_ms;
};

struct HeadPoseTarget {
  float pan_deg;
  float tilt_deg;
  uint16_t speed;
  uint32_t duration_ms;
};

struct HeadPosePlan {
  Result result;
  HeadPoseTarget target;
};

struct MotionPlan {
  Result result;
  ServoTarget target;
  uint32_t duration_ms;
};

constexpr ServoLimits kDefaultServoLimits{-45, 45, -30, 30};
constexpr ServoTarget kNeutralTarget{0, 0};
constexpr HeadPoseLimits kDefaultHeadPoseLimits{
    -128.0f,
    128.0f,
    0.0f,
    90.0f,
    0,
    1000,
    100,
    2000,
    50,
};
constexpr HeadPoseTarget kHomeHeadPose{0.0f, 0.0f, 0, 0};
constexpr uint32_t kMinMotionDurationMs = 100;
constexpr uint32_t kMaxMotionDurationMs = 2000;
constexpr uint32_t kDefaultMotionDurationMs = 900;

inline int clamp_int(int value, int min_value, int max_value) {
  if (value < min_value) {
    return min_value;
  }
  if (value > max_value) {
    return max_value;
  }
  return value;
}

inline bool is_known_motion(const char* name) {
  return strcmp(name, "nod") == 0 || strcmp(name, "idle") == 0;
}

inline bool is_invalid_float(float value) {
  return value != value;
}

inline Result validate_head_pose_target(
    float pan_deg,
    float tilt_deg,
    uint16_t speed,
    uint32_t duration_ms,
    HeadPoseLimits limits = kDefaultHeadPoseLimits) {
  if (is_invalid_float(pan_deg) || is_invalid_float(tilt_deg)) {
    return Result::rejected("SERVO_LIMIT_EXCEEDED", "head pose angles must be finite", true);
  }
  if (pan_deg < limits.min_pan_deg || pan_deg > limits.max_pan_deg) {
    return Result::rejected("SERVO_LIMIT_EXCEEDED", "head pose pan_deg out of range", true);
  }
  if (tilt_deg < limits.min_tilt_deg || tilt_deg > limits.max_tilt_deg) {
    return Result::rejected("SERVO_LIMIT_EXCEEDED", "head pose tilt_deg out of range", true);
  }
  if (speed < limits.min_speed || speed > limits.max_speed) {
    return Result::rejected("SERVO_LIMIT_EXCEEDED", "head pose speed out of range", true);
  }
  if (duration_ms != 0 &&
      (duration_ms < limits.min_nonzero_duration_ms || duration_ms > limits.max_duration_ms)) {
    return Result::rejected("MOTION_INTERRUPTED", "head pose duration out of safe range", true);
  }
  return Result::accepted("head pose accepted");
}

inline HeadPosePlan plan_head_pose(
    float pan_deg,
    float tilt_deg,
    uint16_t speed,
    uint32_t duration_ms,
    bool pose_slot_available,
    uint32_t elapsed_since_last_command_ms,
    bool calibration_valid,
    bool servo_read_ok,
    bool fault_state,
    HeadPoseLimits limits) {
  if (!pose_slot_available ||
      elapsed_since_last_command_ms < limits.min_command_interval_ms) {
    return {
        Result::rejected("FIRMWARE_BUSY", "head pose command rate limited", true),
        kHomeHeadPose,
    };
  }
  if (!calibration_valid) {
    return {
        Result::rejected("CALIBRATION_INVALID", "head pose calibration is invalid", true),
        kHomeHeadPose,
    };
  }
  if (!servo_read_ok) {
    return {
        Result::rejected("SERVO_READ_FAILED", "servo current position read failed", true),
        kHomeHeadPose,
    };
  }
  if (fault_state) {
    return {
        Result::rejected("MOTION_INTERRUPTED", "firmware is in fault state", true),
        kHomeHeadPose,
    };
  }

  Result result = validate_head_pose_target(pan_deg, tilt_deg, speed, duration_ms, limits);
  if (!result.ok) {
    return {result, kHomeHeadPose};
  }
  return {result, {pan_deg, tilt_deg, speed, duration_ms}};
}

inline HeadPosePlan plan_head_home(
    uint16_t speed,
    uint32_t duration_ms,
    bool pose_slot_available,
    uint32_t elapsed_since_last_command_ms,
    bool calibration_valid,
    bool servo_read_ok,
    bool fault_state,
    HeadPoseLimits limits) {
  return plan_head_pose(
      kHomeHeadPose.pan_deg,
      kHomeHeadPose.tilt_deg,
      speed,
      duration_ms,
      pose_slot_available,
      elapsed_since_last_command_ms,
      calibration_valid,
      servo_read_ok,
      fault_state,
      limits);
}

inline MotionPlan plan_motion(
    const char* name,
    float intensity,
    uint32_t duration_ms,
    bool calibration_valid,
    bool servo_read_ok,
    bool fault_state,
    ServoLimits limits = kDefaultServoLimits) {
  if (!is_known_motion(name)) {
    return {
        Result::rejected("UNKNOWN_COMMAND", "unknown motion name"),
        kNeutralTarget,
        0,
    };
  }

  if (!calibration_valid) {
    return {
        Result::rejected("CALIBRATION_INVALID", "motion calibration is invalid", true),
        kNeutralTarget,
        0,
    };
  }

  if (!servo_read_ok) {
    return {
        Result::rejected("SERVO_READ_FAILED", "servo current position read failed", true),
        kNeutralTarget,
        0,
    };
  }

  if (fault_state) {
    return {
        Result::rejected("MOTION_INTERRUPTED", "firmware is in fault state", true),
        kNeutralTarget,
        0,
    };
  }

  if (intensity < 0.0f || intensity > 1.0f) {
    return {
        Result::rejected("SERVO_LIMIT_EXCEEDED", "motion intensity out of range", true),
        kNeutralTarget,
        0,
    };
  }

  if (duration_ms != 0 &&
      (duration_ms < kMinMotionDurationMs || duration_ms > kMaxMotionDurationMs)) {
    return {
        Result::rejected("MOTION_INTERRUPTED", "motion duration out of safe range", true),
        kNeutralTarget,
        0,
    };
  }

  ServoTarget target = kNeutralTarget;
  if (strcmp(name, "nod") == 0) {
    target.y = static_cast<int>(28.0f * intensity);
  }

  target.x = clamp_int(target.x, limits.min_x, limits.max_x);
  target.y = clamp_int(target.y, limits.min_y, limits.max_y);

  return {
      Result::accepted("motion accepted"),
      target,
      duration_ms == 0 ? kDefaultMotionDurationMs : duration_ms,
  };
}

}  // namespace stackchan
