# Documentation

This directory is the map for the project. Start here when you want to understand what is being built, then follow the documents that match the layer you are working on.

## Reading order

1. [architecture.md](architecture.md)
   - Overall shape of the Codex App -> CLI -> ROS 2 -> micro-ROS -> M5StackChan bridge.
2. [stackchanctl.md](stackchanctl.md)
   - Human, Codex, and MCP stdio command surface.
3. [ros-interface.md](ros-interface.md)
   - ROS 2 topics, services, actions, and shared message boundaries.
4. [firmware.md](firmware.md)
   - Device-side responsibilities, safety limits, and supported behaviors.
5. [speech-design.md](speech-design.md)
   - PC bridge VAD, echo control, local ASR, transcript privacy, and speech events.
6. [license-notes.md](license-notes.md)
   - Dependency and reference policy for StackChan-related upstream code.
7. [quality-gates.md](quality-gates.md)
   - Required validation gates for CLI, MCP stdio, ROS 2 interfaces, firmware, Codex skill, and Rust workers.
8. [ros2-container.md](ros2-container.md)
   - Docker/devcontainer setup for ROS 2 Jazzy readiness without installing ROS 2 on the host.

## Implementation areas

- [../apps/stackchanctl](../apps/stackchanctl/README.md): CLI entrypoint and backend selection.
- [../ros/stackchan_bridge](../ros/stackchan_bridge/README.md): PC-side ROS 2 bridge nodes.
- [../ros/stackchan_msgs](../ros/stackchan_msgs/README.md): ROS 2 interface definitions.
- [../firmware/m5stackchan-microros](../firmware/m5stackchan-microros/README.md): M5StackChan firmware.
- [../skills/codex-stackchan](../skills/codex-stackchan/README.md): Codex agent skill.

## Quality gates

Use [quality-gates.md](quality-gates.md) before implementation changes. The short version is: mock backend behavior must stay testable without hardware, command metadata and structured errors are contract, MCP stdio must keep JSON-RPC isolated on stdout, and safety behavior belongs at the firmware boundary.

## Document ownership

- Put design decisions and cross-layer contracts in `docs/`.
- Keep implementation-specific setup notes in each package directory.
- When a package README starts to explain another layer, move that explanation into `docs/` and link to it.
