#pragma once

#include <stdint.h>

namespace stackchan {

enum class Priority : uint8_t {
  Low = 0,
  Normal = 1,
  High = 2,
  Safety = 3,
};

enum class ResultState : uint8_t {
  Accepted = 1,
  Completed = 2,
  Rejected = 3,
  Timeout = 4,
};

struct CommandMeta {
  const char* device_id;
  const char* command_id;
  const char* source;
  const char* created_at;
  Priority priority;
};

struct Result {
  bool ok;
  ResultState state;
  const char* error_code;
  const char* message;
  bool recoverable;

  static Result accepted(const char* message = "accepted") {
    return {true, ResultState::Accepted, "", message, false};
  }

  static Result rejected(
      const char* error_code,
      const char* message,
      bool recoverable = false) {
    return {false, ResultState::Rejected, error_code, message, recoverable};
  }
};

}  // namespace stackchan
