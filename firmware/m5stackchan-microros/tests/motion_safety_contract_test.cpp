#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "stackchan/motion_safety.hpp"

namespace {

void require(bool condition, const char* message) {
  if (!condition) {
    fprintf(stderr, "motion safety contract failed: %s\n", message);
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

void require_waypoint(
    const stackchan::MotionPlan& plan,
    size_t index,
    int x,
    int y) {
  require(index < plan.waypoint_count, "waypoint index exists");
  require(plan.waypoints[index].offset.x == x, "unexpected waypoint x");
  require(plan.waypoints[index].offset.y == y, "unexpected waypoint y");
}

void require_hold(
    const stackchan::MotionPlan& plan,
    size_t index,
    uint32_t hold_ms) {
  require(index < plan.waypoint_count, "hold waypoint index exists");
  require(plan.waypoints[index].hold_ms == hold_ms, "unexpected waypoint hold");
}

void require_servo_time(
    const stackchan::MotionPlan& plan,
    size_t index,
    uint16_t servo_time_ms) {
  require(index < plan.waypoint_count, "servo time waypoint index exists");
  require(plan.waypoints[index].servo_time_ms == servo_time_ms, "unexpected waypoint servo time");
}

void require_easing(
    const stackchan::MotionPlan& plan,
    size_t index,
    stackchan::MotionEasing easing) {
  require(index < plan.waypoint_count, "easing waypoint index exists");
  require(plan.waypoints[index].easing == easing, "unexpected waypoint easing");
}

}  // namespace

int main() {
  require(stackchan::kDefaultServoLimits.min_x == -128, "hard min x");
  require(stackchan::kDefaultServoLimits.max_x == 128, "hard max x");
  require(stackchan::kDefaultServoLimits.min_y == 0, "hard min y");
  require(stackchan::kDefaultServoLimits.max_y == 90, "hard max y");
  require(stackchan::kNormalServoMinY == 5, "normal min y");
  require(stackchan::kNormalServoMaxY == 85, "normal max y");

  stackchan::MotionPlan look_user =
      stackchan::plan_motion("look-user", 1.0f, 0, true, true, false);
  require(look_user.result.ok, "look-user accepted");
  require(look_user.waypoint_count == 4, "look-user waypoint count");
  require_waypoint(look_user, 0, 0, 60);
  require_waypoint(look_user, 1, 0, 15);
  require_waypoint(look_user, 2, 0, 45);
  require_waypoint(look_user, 3, 0, 0);
  require_hold(look_user, 0, 180);
  require_hold(look_user, 1, 220);
  require_hold(look_user, 2, 850);
  require_hold(look_user, 3, 650);

  stackchan::MotionPlan shake =
      stackchan::plan_motion("shake", 1.0f, 0, true, true, false);
  require(shake.result.ok, "shake accepts neutral-Y yaw movement");
  require(shake.waypoint_count == 10, "shake waypoint count");
  require(
      shake.servo_time_ms == stackchan::kShakeMotionReturnHomeServoTimeMs,
      "shake return-home servo time");
  require_waypoint(shake, 0, 88, 8);
  require_waypoint(shake, 1, -88, 11);
  require_waypoint(shake, 2, 84, 8);
  require_waypoint(shake, 3, -84, 11);
  require_waypoint(shake, 4, 78, 8);
  require_waypoint(shake, 5, -78, 10);
  require_waypoint(shake, 6, 70, 8);
  require_waypoint(shake, 7, -70, 10);
  require_waypoint(shake, 8, 58, 7);
  require_waypoint(shake, 9, -48, 7);
  for (size_t i = 0; i < shake.waypoint_count; ++i) {
    require_hold(shake, i, 0);
    require_easing(shake, i, stackchan::MotionEasing::Linear);
    const int y = shake.waypoints[i].offset.y;
    require(
        y == stackchan::kNeutralTarget.y ||
            (y >= stackchan::kNormalServoMinY && y <= stackchan::kNormalServoMaxY),
        "shake waypoint respects normal Y envelope");
  }
  require_servo_time(shake, 0, stackchan::kShakeMotionSideServoTimeMs);
  require_servo_time(shake, 5, stackchan::kShakeMotionSideServoTimeMs);
  require_servo_time(shake, 6, stackchan::kShakeMotionSmallSideServoTimeMs);
  require_servo_time(shake, 9, stackchan::kShakeMotionSmallSideServoTimeMs);

  stackchan::MotionPlan nod =
      stackchan::plan_motion("nod", 1.0f, 0, true, true, false);
  require(nod.result.ok, "nod accepted");
  require(nod.waypoint_count == 4, "nod waypoint count");
  for (size_t i = 0; i < nod.waypoint_count; ++i) {
    require_hold(nod, i, 90);
  }

  stackchan::MotionPlan cheerful =
      stackchan::plan_motion("cheerful", 1.0f, 0, true, true, false);
  require(cheerful.result.ok, "cheerful accepted");
  require(cheerful.waypoint_count == 4, "cheerful waypoint count");
  require(
      cheerful.servo_time_ms == stackchan::kCheerfulMotionReturnHomeServoTimeMs,
      "cheerful return-home servo time");
  require_waypoint(cheerful, 0, 28, 52);
  require_waypoint(cheerful, 1, 82, 82);
  require_waypoint(cheerful, 2, -64, 70);
  require_waypoint(cheerful, 3, 16, 46);
  require_hold(cheerful, 0, 0);
  require_hold(cheerful, 1, 0);
  require_hold(cheerful, 2, 20);
  require_hold(cheerful, 3, 0);
  require_servo_time(cheerful, 0, stackchan::kCheerfulMotionAnticipationServoTimeMs);
  require_servo_time(cheerful, 1, stackchan::kCheerfulMotionArcServoTimeMs);
  require_servo_time(cheerful, 2, stackchan::kCheerfulMotionReboundServoTimeMs);
  require_servo_time(cheerful, 3, stackchan::kCheerfulMotionFollowThroughServoTimeMs);
  require_easing(cheerful, 0, stackchan::MotionEasing::EaseInOutCubic);
  require_easing(cheerful, 1, stackchan::MotionEasing::EaseOutBackLike);
  require_easing(cheerful, 2, stackchan::MotionEasing::EaseInOutCubic);
  require_easing(cheerful, 3, stackchan::MotionEasing::EaseOutSine);

  stackchan::ServoLimits narrow_y{stackchan::kDefaultServoLimits.min_x,
                                  stackchan::kDefaultServoLimits.max_x,
                                  0,
                                  55};
  require_error(
      stackchan::plan_motion("look-user", 1.0f, 0, true, true, false, narrow_y).result,
      "SERVO_LIMIT_EXCEEDED");

  require_error(
      stackchan::plan_head_pose(
          0.0f,
          0.0f,
          500,
          0,
          true,
          stackchan::kDefaultHeadPoseLimits.min_command_interval_ms,
          true,
          true,
          false,
          stackchan::kDefaultHeadPoseLimits)
          .result,
      "SERVO_LIMIT_EXCEEDED");

  stackchan::HeadPosePlan home = stackchan::plan_head_home(
      500,
      0,
      true,
      stackchan::kDefaultHeadPoseLimits.min_command_interval_ms,
      true,
      true,
      false,
      stackchan::kDefaultHeadPoseLimits);
  require(home.result.ok, "home bypasses external Y endpoint envelope");
  require(home.target.tilt_deg == 0.0f, "home reports neutral tilt");

  return 0;
}
