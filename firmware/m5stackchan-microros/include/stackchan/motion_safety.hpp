#pragma once

#include <stddef.h>
#include <stdint.h>
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

enum class MotionEasing : uint8_t {
  Linear,
  EaseInOutCubic,
  EaseOutSine,
  EaseOutBackLike,
};

struct MotionWaypoint {
  ServoTarget offset;
  uint32_t hold_ms;
  uint16_t servo_time_ms;
  MotionEasing easing;
};

constexpr size_t kMaxMotionWaypoints = 24;
constexpr uint16_t kDefaultNamedMotionServoTimeMs = 105;
constexpr uint16_t kShakeMotionSideServoTimeMs = 180;
constexpr uint16_t kShakeMotionSmallSideServoTimeMs = 165;
constexpr uint16_t kShakeMotionReturnHomeServoTimeMs = 270;
constexpr uint16_t kCheerfulMotionReturnHomeServoTimeMs = 700;
constexpr uint16_t kCheerfulMotionAnticipationServoTimeMs = 320;
constexpr uint16_t kCheerfulMotionArcServoTimeMs = 700;
constexpr uint16_t kCheerfulMotionReboundServoTimeMs = 620;
constexpr uint16_t kCheerfulMotionFollowThroughServoTimeMs = 500;

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
  MotionWaypoint waypoints[kMaxMotionWaypoints];
  size_t waypoint_count;
  uint16_t servo_time_ms = kDefaultNamedMotionServoTimeMs;
};

constexpr ServoLimits kDefaultServoLimits{-128, 128, 0, 90};
constexpr ServoTarget kNeutralTarget{0, 0};
constexpr int kNormalServoMinY = 5;
constexpr int kNormalServoMaxY = 85;
constexpr HeadPoseLimits kDefaultHeadPoseLimits{
    -128.0f,
    128.0f,
    5.0f,
    85.0f,
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
  return strcmp(name, "nod") == 0 ||
         strcmp(name, "shake") == 0 ||
         strcmp(name, "cheerful") == 0 ||
         strcmp(name, "idle") == 0 ||
         strcmp(name, "look-left") == 0 ||
         strcmp(name, "look-right") == 0 ||
         strcmp(name, "look-user") == 0;
}

inline bool is_invalid_float(float value) {
  return value != value;
}

inline Result validate_head_pose_motion_parameters(
    uint16_t speed,
    uint32_t duration_ms,
    HeadPoseLimits limits = kDefaultHeadPoseLimits) {
  if (speed < limits.min_speed || speed > limits.max_speed) {
    return Result::rejected("SERVO_LIMIT_EXCEEDED", "head pose speed out of range", true);
  }
  if (duration_ms != 0 &&
      (duration_ms < limits.min_nonzero_duration_ms || duration_ms > limits.max_duration_ms)) {
    return Result::rejected("MOTION_INTERRUPTED", "head pose duration out of safe range", true);
  }
  return Result::accepted("head pose accepted");
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
  return validate_head_pose_motion_parameters(speed, duration_ms, limits);
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

  Result result = validate_head_pose_motion_parameters(speed, duration_ms, limits);
  return {result, kHomeHeadPose};
}

inline int scaled_motion_degrees(int degrees, float intensity) {
  return static_cast<int>(static_cast<float>(degrees) * intensity);
}

inline bool motion_target_within_limits(const ServoTarget& target, ServoLimits limits) {
  return target.x >= limits.min_x &&
         target.x <= limits.max_x &&
         target.y >= limits.min_y &&
         target.y <= limits.max_y;
}

inline bool motion_target_within_normal_limits(const ServoTarget& target, ServoLimits limits) {
  return motion_target_within_limits(target, limits) &&
         (target.y == kNeutralTarget.y ||
          (target.y >= kNormalServoMinY && target.y <= kNormalServoMaxY));
}

inline Result add_motion_waypoint(
    MotionPlan* plan,
    int x,
    int y,
    uint32_t hold_ms,
    float intensity,
    ServoLimits limits,
    uint16_t servo_time_ms = kDefaultNamedMotionServoTimeMs,
    MotionEasing easing = MotionEasing::EaseInOutCubic) {
  if (plan == nullptr || plan->waypoint_count >= kMaxMotionWaypoints) {
    return Result::rejected("MOTION_INTERRUPTED", "motion preset has too many waypoints", true);
  }
  const ServoTarget target{
      scaled_motion_degrees(x, intensity),
      scaled_motion_degrees(y, intensity),
  };
  if (!motion_target_within_normal_limits(target, limits)) {
    return Result::rejected("SERVO_LIMIT_EXCEEDED", "motion waypoint out of range", true);
  }
  plan->waypoints[plan->waypoint_count] = {target, hold_ms, servo_time_ms, easing};
  plan->waypoint_count += 1;
  return Result::accepted("motion waypoint accepted");
}

inline Result add_motion_return_home(MotionPlan* plan, uint32_t hold_ms, ServoLimits limits) {
  if (plan == nullptr || plan->waypoint_count >= kMaxMotionWaypoints) {
    return Result::rejected("MOTION_INTERRUPTED", "motion preset has too many waypoints", true);
  }
  if (!motion_target_within_limits(kNeutralTarget, limits)) {
    return Result::rejected("SERVO_LIMIT_EXCEEDED", "motion home offset out of range", true);
  }
  plan->waypoints[plan->waypoint_count] =
      {kNeutralTarget, hold_ms, kDefaultNamedMotionServoTimeMs, MotionEasing::EaseInOutCubic};
  plan->waypoint_count += 1;
  return Result::accepted("motion waypoint accepted");
}

inline uint32_t scaled_motion_hold(uint32_t hold_ms, uint32_t duration_ms, uint32_t default_ms) {
  if (hold_ms == 0) {
    return 0;
  }
  if (duration_ms == 0 || default_ms == 0) {
    return hold_ms;
  }
  uint32_t scaled = (hold_ms * duration_ms) / default_ms;
  if (scaled < kMinMotionDurationMs / 2) {
    return kMinMotionDurationMs / 2;
  }
  return scaled;
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
        {},
        0,
    };
  }

  if (is_invalid_float(intensity) || intensity < 0.0f || intensity > 1.0f) {
    return {
        Result::rejected("SERVO_LIMIT_EXCEEDED", "motion intensity out of range", true),
        {},
        0,
    };
  }

  if (duration_ms != 0 &&
      (duration_ms < kMinMotionDurationMs || duration_ms > kMaxMotionDurationMs)) {
    return {
        Result::rejected("MOTION_INTERRUPTED", "motion duration out of safe range", true),
        {},
        0,
    };
  }

  MotionPlan plan{
      Result::accepted("motion accepted"),
      {},
      0,
  };
  if (strcmp(name, "idle") == 0) {
    return plan;
  }

  if (!calibration_valid) {
    return {
        Result::rejected("CALIBRATION_INVALID", "motion calibration is invalid", true),
        {},
        0,
    };
  }

  if (!servo_read_ok) {
    return {
        Result::rejected("SERVO_READ_FAILED", "servo current position read failed", true),
        {},
        0,
    };
  }

  if (fault_state) {
    return {
        Result::rejected("MOTION_INTERRUPTED", "firmware is in fault state", true),
        {},
        0,
    };
  }

  Result result = Result::accepted("motion accepted");
  if (strcmp(name, "nod") == 0) {
    const uint32_t hold = scaled_motion_hold(90, duration_ms, 360);
    result = add_motion_waypoint(&plan, 0, 18, hold, intensity, limits);
    if (result.ok) result = add_motion_return_home(&plan, hold, limits);
    if (result.ok) result = add_motion_waypoint(&plan, 0, 18, hold, intensity, limits);
    if (result.ok) result = add_motion_return_home(&plan, hold, limits);
  } else if (strcmp(name, "shake") == 0) {
    plan.servo_time_ms = kShakeMotionReturnHomeServoTimeMs;
    result = add_motion_waypoint(
        &plan,
        88,
        8,
        0,
        intensity,
        limits,
        kShakeMotionSideServoTimeMs,
        MotionEasing::Linear);
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          -88,
          11,
          0,
          intensity,
          limits,
          kShakeMotionSideServoTimeMs,
          MotionEasing::Linear);
    }
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          84,
          8,
          0,
          intensity,
          limits,
          kShakeMotionSideServoTimeMs,
          MotionEasing::Linear);
    }
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          -84,
          11,
          0,
          intensity,
          limits,
          kShakeMotionSideServoTimeMs,
          MotionEasing::Linear);
    }
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          78,
          8,
          0,
          intensity,
          limits,
          kShakeMotionSideServoTimeMs,
          MotionEasing::Linear);
    }
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          -78,
          10,
          0,
          intensity,
          limits,
          kShakeMotionSideServoTimeMs,
          MotionEasing::Linear);
    }
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          70,
          8,
          0,
          intensity,
          limits,
          kShakeMotionSmallSideServoTimeMs,
          MotionEasing::Linear);
    }
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          -70,
          10,
          0,
          intensity,
          limits,
          kShakeMotionSmallSideServoTimeMs,
          MotionEasing::Linear);
    }
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          58,
          7,
          0,
          intensity,
          limits,
          kShakeMotionSmallSideServoTimeMs,
          MotionEasing::Linear);
    }
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          -48,
          7,
          0,
          intensity,
          limits,
          kShakeMotionSmallSideServoTimeMs,
          MotionEasing::Linear);
    }
  } else if (strcmp(name, "cheerful") == 0) {
    plan.servo_time_ms = kCheerfulMotionReturnHomeServoTimeMs;
    constexpr uint32_t kCheerfulDefaultMs = 1820;
    const uint32_t anticipate_hold = scaled_motion_hold(0, duration_ms, kCheerfulDefaultMs);
    const uint32_t arc_hold = scaled_motion_hold(0, duration_ms, kCheerfulDefaultMs);
    const uint32_t rebound_hold = scaled_motion_hold(20, duration_ms, kCheerfulDefaultMs);
    const uint32_t follow_hold = scaled_motion_hold(0, duration_ms, kCheerfulDefaultMs);
    result = add_motion_waypoint(
        &plan,
        28,
        52,
        anticipate_hold,
        intensity,
        limits,
        kCheerfulMotionAnticipationServoTimeMs,
        MotionEasing::EaseInOutCubic);
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          82,
          82,
          arc_hold,
          intensity,
          limits,
          kCheerfulMotionArcServoTimeMs,
          MotionEasing::EaseOutBackLike);
    }
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          -64,
          70,
          rebound_hold,
          intensity,
          limits,
          kCheerfulMotionReboundServoTimeMs,
          MotionEasing::EaseInOutCubic);
    }
    if (result.ok) {
      result = add_motion_waypoint(
          &plan,
          16,
          46,
          follow_hold,
          intensity,
          limits,
          kCheerfulMotionFollowThroughServoTimeMs,
          MotionEasing::EaseOutSine);
    }
  } else if (strcmp(name, "look-left") == 0) {
    const uint32_t hold = scaled_motion_hold(750, duration_ms, 1500);
    result = add_motion_waypoint(&plan, 22, 6, hold, intensity, limits);
    if (result.ok) result = add_motion_return_home(&plan, hold, limits);
  } else if (strcmp(name, "look-right") == 0) {
    const uint32_t hold = scaled_motion_hold(750, duration_ms, 1500);
    result = add_motion_waypoint(&plan, -22, 6, hold, intensity, limits);
    if (result.ok) result = add_motion_return_home(&plan, hold, limits);
  } else if (strcmp(name, "look-user") == 0) {
    constexpr uint32_t kLookUserDefaultMs = 1900;
    const uint32_t upper_hold = scaled_motion_hold(180, duration_ms, kLookUserDefaultMs);
    const uint32_t lower_hold = scaled_motion_hold(220, duration_ms, kLookUserDefaultMs);
    const uint32_t gaze_hold = scaled_motion_hold(850, duration_ms, kLookUserDefaultMs);
    const uint32_t return_hold = scaled_motion_hold(650, duration_ms, kLookUserDefaultMs);
    result = add_motion_waypoint(&plan, 0, 60, upper_hold, intensity, limits);
    if (result.ok) result = add_motion_waypoint(&plan, 0, 15, lower_hold, intensity, limits);
    if (result.ok) result = add_motion_waypoint(&plan, 0, 45, gaze_hold, intensity, limits);
    if (result.ok) result = add_motion_return_home(&plan, return_hold, limits);
  }

  if (!result.ok) {
    return {result, {}, 0};
  }

  return plan;
}

}  // namespace stackchan
