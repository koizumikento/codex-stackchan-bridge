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

struct MotionPlan {
  Result result;
  ServoTarget target;
  uint32_t duration_ms;
};

constexpr ServoLimits kDefaultServoLimits{-45, 45, -30, 30};
constexpr ServoTarget kNeutralTarget{0, 0};
constexpr uint32_t kMinMotionDurationMs = 100;
constexpr uint32_t kMaxMotionDurationMs = 2000;
constexpr uint32_t kDefaultMotionDurationMs = 500;

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

inline MotionPlan plan_motion(
    const char* name,
    float intensity,
    uint32_t duration_ms,
    ServoLimits limits = kDefaultServoLimits) {
  if (!is_known_motion(name)) {
    return {
        Result::rejected("UNKNOWN_COMMAND", "unknown motion name"),
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
    target.y = static_cast<int>(20.0f * intensity);
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
