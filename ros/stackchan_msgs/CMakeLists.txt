cmake_minimum_required(VERSION 3.8)
project(stackchan_msgs)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/AudioChunk.msg"
  "msg/CommandMeta.msg"
  "msg/CompressedImagePayload.msg"
  "msg/ImuRaw.msg"
  "msg/Result.msg"
  "msg/StackChanEvent.msg"
  "msg/StackChanStatus.msg"
  "srv/GetStatus.srv"
  "srv/SetFace.srv"
  "srv/SetLed.srv"
  "action/CaptureAudio.action"
  "action/CaptureCamera.action"
  "action/PlayAudio.action"
  "action/RunMotion.action"
  "action/Say.action"
  DEPENDENCIES builtin_interfaces geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
