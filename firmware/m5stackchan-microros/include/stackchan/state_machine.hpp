#pragma once

namespace stackchan {

enum class RuntimeState {
  Booting,
  WaitingForAgent,
  Idle,
  Acting,
  Degraded,
  Fault,
};

class StateMachine {
 public:
  RuntimeState state() const { return state_; }

  void booted() { state_ = RuntimeState::WaitingForAgent; }

  void agent_connected() {
    if (state_ != RuntimeState::Fault) {
      state_ = RuntimeState::Idle;
    }
  }

  void command_started() {
    if (state_ == RuntimeState::Idle) {
      state_ = RuntimeState::Acting;
    }
  }

  void command_finished() {
    if (state_ == RuntimeState::Acting) {
      state_ = RuntimeState::Idle;
    }
  }

  void agent_disconnected() {
    if (state_ != RuntimeState::Fault) {
      state_ = RuntimeState::Degraded;
    }
  }

  void recovered() {
    if (state_ == RuntimeState::Degraded || state_ == RuntimeState::Fault) {
      state_ = RuntimeState::Idle;
    }
  }

  void fault() { state_ = RuntimeState::Fault; }

 private:
  RuntimeState state_ = RuntimeState::Booting;
};

}  // namespace stackchan
