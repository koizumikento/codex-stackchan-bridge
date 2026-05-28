#include <assert.h>
#include <string.h>

#include "stackchan/sensors.hpp"

namespace {

struct EventCapture {
  int count = 0;
  char last_event_name[stackchan::kEventNameMaxLength + 1] = "";
  char last_payload_json[stackchan::kEventPayloadJsonMaxLength + 1] = "";
};

stackchan::Result capture_event(const stackchan::DeviceEvent& event, void* context) {
  auto* capture = static_cast<EventCapture*>(context);
  assert(capture != nullptr);
  ++capture->count;
  stackchan::copy_event_string(
      capture->last_event_name,
      sizeof(capture->last_event_name),
      event.event_name);
  stackchan::copy_event_string(
      capture->last_payload_json,
      sizeof(capture->last_payload_json),
      event.payload_json);
  return stackchan::Result::accepted("captured");
}

stackchan::ProximityRawTelemetry proximity(float signal, uint16_t raw, uint32_t stamp_ms) {
  stackchan::ProximityRawTelemetry telemetry{};
  stackchan::copy_event_string(telemetry.device_id, sizeof(telemetry.device_id), "default");
  telemetry.stamp_ms = stamp_ms;
  telemetry.sensor_index = 0;
  telemetry.signal = signal;
  telemetry.raw = raw;
  telemetry.saturated = false;
  return telemetry;
}

}  // namespace

int main() {
  EventCapture capture{};
  stackchan::EventPublisher events("default");
  events.set_callback(capture_event, &capture);
  stackchan::ProximityEventEstimator estimator;

  assert(stackchan::kProximityNearSignal == 0.0010f);
  assert(stackchan::kProximityClearSignal == 0.0005f);

  assert(estimator.update(proximity(0.0009f, 2, 1000), events).ok);
  assert(events.queued_count() == 0);

  assert(estimator.update(proximity(0.001465f, 3, 1100), events).ok);
  assert(events.queued_count() == 1);
  assert(events.drain().ok);
  assert(capture.count == 1);
  assert(strcmp(capture.last_event_name, "proximity_near") == 0);
  assert(strcmp(capture.last_payload_json, "{}") == 0);

  assert(estimator.update(proximity(0.0008f, 2, 1200), events).ok);
  assert(events.queued_count() == 0);

  assert(estimator.update(proximity(0.0f, 0, 1300), events).ok);
  assert(events.queued_count() == 1);
  assert(events.drain().ok);
  assert(capture.count == 2);
  assert(strcmp(capture.last_event_name, "proximity_clear") == 0);
  assert(strcmp(capture.last_payload_json, "{}") == 0);

  return 0;
}
