# codex-stackchan-bridge

Codex AppからROS 2経由でM5Stack版ｽﾀｯｸﾁｬﾝを制御するための実験リポジトリです。

目標は、ｽﾀｯｸﾁｬﾝを単なる通知端末ではなく、Codexのローカルな物理アバターとして扱えるようにすることです。CodexのエージェントスキルからローカルCLIを呼び出し、そのCLIがROS 2のtopic / service / actionへ変換し、PC側ノードとmicro-ROS経由でｽﾀｯｸﾁｬﾝ本体を動かします。

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
│   └── architecture.md        # Architecture notes
└── scripts/                   # Local helper scripts
```

## Early command sketch

```bash
stackchanctl say "テスト終わったよ"
stackchanctl face happy
stackchanctl motion nod
stackchanctl led progress
stackchanctl observe
```

These commands are expected to translate into ROS 2 operations such as publishing a face/motion command, calling a speech service, or reading a status topic.

## Status

This repository is currently a scaffold. The next useful step is to define the first narrow contract between `stackchanctl` and ROS 2, then add a PC-only mock backend so the Codex skill can be developed before the physical device firmware is ready.
