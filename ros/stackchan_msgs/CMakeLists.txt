cmake_minimum_required(VERSION 3.8)
project(stackchan_msgs)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/AudioChunk.msg"
  "msg/CapabilityStatus.msg"
  "msg/CommandMeta.msg"
  "msg/CompressedImagePayload.msg"
  "msg/HeadPose.msg"
  "msg/ImuRaw.msg"
  "msg/LightRaw.msg"
  "msg/PowerStatus.msg"
  "msg/ProximityRaw.msg"
  "msg/Result.msg"
  "msg/StackChanEvent.msg"
  "msg/StackChanStatus.msg"
  "msg/TouchState.msg"
  "srv/ClearEventCursor.srv"
  "srv/GetPowerStatus.srv"
  "srv/GetHeadPose.srv"
  "srv/GetTranscript.srv"
  "srv/GetStatus.srv"
  "srv/ListEvents.srv"
  "srv/NextAudioChunk.srv"
  "srv/NextEvent.srv"
  "srv/SetFace.srv"
  "srv/SetHeadPose.srv"
  "srv/SetLed.srv"
  "srv/SetMotion.srv"
  "action/CaptureAudio.action"
  "action/CaptureCamera.action"
  "action/PlayAudio.action"
  "action/MoveHeadPose.action"
  "action/RunMotion.action"
  "action/Say.action"
  DEPENDENCIES builtin_interfaces geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
