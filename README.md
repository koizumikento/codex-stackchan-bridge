# codex-stackchan-bridge

Codex AppからROS 2経由でM5Stack版ｽﾀｯｸﾁｬﾝを制御するための実験リポジトリです。

目標は、ｽﾀｯｸﾁｬﾝを単なる通知端末ではなく、Codexのローカルな物理アバターとして扱えるようにすることです。CodexのエージェントスキルからローカルCLIを呼び出し、そのCLIがPC側のROS 2 bridge facadeへ命令を送り、bridgeがmicro-ROS経由でｽﾀｯｸﾁｬﾝ本体へ転送します。

```text
Codex App
  -> Agent Skill
  -> stackchanctl
  -> ROS 2 nodes
  -> micro-ROS Agent
  -> M5StackChan firmware
```

## What this project is trying to build

- `stackchanctl`: Codexにも人間にも扱いやすいローカルCLI
- ROS 2 bridge nodes: 表情、発話、首振り、LED、センサー入力をROSの語彙にのせるPC側ノード
- micro-ROS firmware: ｽﾀｯｸﾁｬﾝ本体でROS 2からの指示を受けて、表情・サーボ・LEDなどを制御するファームウェア
- Codex agent skill: 作業開始、テスト成功/失敗、ユーザー待ち、完了などの場面で自然にｽﾀｯｸﾁｬﾝへ振る舞いを送るスキル
- Shared message definitions: CLI、ROSノード、ファームウェア間で共有する命令や状態の型

## Direction

通信基盤はROS 2に寄せます。MQTTや独自WebSocketではなく、最初からｽﾀｯｸﾁｬﾝを「ロボット」として扱うためです。必要になった場合、ZenohなどはROS 2の通信層として検討しますが、プロジェクトの中心はROS 2のtopic / service / actionに置きます。

外部認証やクラウド連携はできるだけ避け、ローカルPC上で完結する構成を優先します。Codex Appはローカルコマンドを呼び、ROS 2がデバイスとの接続面を担当します。

## Repository layout

```text
.
├── apps/
│   └── stackchanctl/          # Local CLI entrypoint
├── firmware/
│   └── m5stackchan-microros/  # M5StackChan firmware
├── ros/
│   ├── stackchan_bridge/      # PC-side ROS 2 nodes
│   └── stackchan_msgs/        # ROS 2 message/service/action definitions
├── skills/
│   └── codex-stackchan/       # Codex agent skill draft
├── docs/
│   ├── README.md              # Documentation map
│   ├── architecture.md        # Architecture notes
│   ├── stackchanctl.md        # CLI design
│   ├── firmware.md            # Firmware design
│   ├── ros-interface.md       # ROS 2 interface design
│   ├── quality-gates.md       # Validation gates
│   └── license-notes.md       # Dependency and license notes
└── scripts/                   # Local helper scripts
```

## Documentation

Start from [docs/README.md](docs/README.md) for the reading order and cross-references.

## Early command sketch

```bash
stackchanctl say "テスト終わったよ"
stackchanctl face happy
stackchanctl motion nod
stackchanctl led progress
stackchanctl observe
```

These commands use the stable `stackchan_bridge` facade under `/stackchan/<device_id>/cmd/...`. The CLI should not publish command topics or call device-side resources directly during normal operation.

## Status

This repository currently contains the first MVP scaffold:

- ROS 2 interface definitions in `ros/stackchan_msgs`.
- A Python `stackchanctl` CLI with mock backend and bridge backend skeleton.
- A hardware-free `stackchan_bridge` facade core with a lazy ROS node adapter.
- A PlatformIO firmware scaffold with safety, audio, and sensor policy headers.
- A Codex skill draft that calls `stackchanctl`.

ROS 2 Jazzy `colcon` builds, micro-ROS firmware build/flash, and hardware behavior validation still need to run in the prepared ROS/PlatformIO environment.

## License

MIT. See [LICENSE](LICENSE).
