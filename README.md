# codex-stackchan-bridge

Codex App から ROS 2 経由で M5Stack 版ｽﾀｯｸﾁｬﾝを制御するための実験リポジトリです。

目標は、ｽﾀｯｸﾁｬﾝを単なる通知端末ではなく、Codex のローカルな物理アバターとして扱えるようにすることです。Codex 向け product skill からローカル CLI を呼び出し、その CLI が PC 側の ROS 2 bridge facade へ命令を送り、bridge が micro-ROS 経由でｽﾀｯｸﾁｬﾝ本体へ転送します。

```text
Codex App
  -> Product Skill
  -> stackchanctl
  -> ROS 2 nodes
  -> micro-ROS Agent
  -> M5StackChan firmware
```

MCP host は、ローカル stdio adapter として `stackchanctl mcp serve` を起動できます。この経路も同じ `stackchanctl` command contract を使い、mock backend または bridge backend を通ります。

## 作るもの

- `stackchanctl`: Codex にも人間にも扱いやすいローカル CLI
- `stackchanctl mcp serve`: MCP host 向けのローカル stdio adapter
- ROS 2 bridge nodes: 表情、発話、首振り、LED、センサー入力を ROS の語彙にのせる PC 側ノード
- micro-ROS firmware: ｽﾀｯｸﾁｬﾝ本体で ROS 2 からの指示を受けて、表情・サーボ・LED などを制御するファームウェア
- Codex product skill: 作業開始、テスト成功/失敗、ユーザー待ち、完了などの場面で控えめな振る舞いを送り、StackChan 由来イベントを観測として扱うスキル
- Shared message definitions: CLI、ROS ノード、ファームウェア間で共有する命令や状態の型

## 方針

通信基盤は ROS 2 に寄せます。MQTT や独自 WebSocket ではなく、最初からｽﾀｯｸﾁｬﾝを「ロボット」として扱うためです。必要になった場合、Zenoh などは ROS 2 の通信層として検討しますが、プロジェクトの中心は ROS 2 の topic / service / action に置きます。

外部認証やクラウド連携はできるだけ避け、ローカル PC 上で完結する構成を優先します。Codex App はローカルコマンドを呼び、ROS 2 がデバイスとの接続面を担当します。MCP を使う場合も、Codex / MCP host がローカルの `stackchanctl mcp serve` を stdio で起動するだけで、独自ネットワーク API は増やしません。

## リポジトリ構成

```text
.
├── apps/
│   └── stackchanctl/          # ローカル CLI の入口
├── firmware/
│   └── m5stackchan-microros/  # M5StackChan ファームウェア
├── ros/
│   ├── stackchan_bridge/      # PC 側 ROS 2 ノード
│   └── stackchan_msgs/        # ROS 2 message/service/action 定義
├── skills/
│   └── codex-stackchan/       # Codex product skill
├── docs/
│   ├── README.md              # ドキュメントの入口
│   ├── architecture.md        # アーキテクチャ
│   ├── stackchanctl.md        # CLI 設計
│   ├── firmware.md            # ファームウェア設計
│   ├── ros-interface.md       # ROS 2 インターフェース設計
│   ├── quality-gates.md       # 検証ゲート
│   └── license-notes.md       # 依存関係とライセンス
└── scripts/                   # ローカル補助スクリプト
```

## ドキュメント

読む順番と参照先は [docs/README.md](docs/README.md) にまとめています。

ホスト環境に ROS 2 を直接入れずに検証する場合は、[docs/ros2-container.md](docs/ros2-container.md) のコンテナ化された Jazzy 環境を使います。

## コマンド例

```bash
stackchanctl say "テスト終わったよ"
stackchanctl face happy
stackchanctl motion nod
stackchanctl led progress
stackchanctl observe
stackchanctl mcp serve --transport stdio --backend mock
```

シェルコマンドと MCP tool call は同じ command contract を共有します。bridge backend を使う場合は `/stackchan/<device_id>/cmd/...` 以下の安定した `stackchan_bridge` facade を通り、mock backend を使う場合は実機なしで完結します。

## 現在の状態

このリポジトリには現在、MVP の最初の足場が入っています。

- `ros/stackchan_msgs` の ROS 2 interface 定義
- mock backend と bridge backend skeleton を持つ Python 製 `stackchanctl` CLI
- 実機なしで検証できる `stackchan_bridge` facade core と lazy ROS node adapter
- safety、audio、sensor policy headers を持つ PlatformIO firmware scaffold
- `stackchanctl` を呼び、routine cue を控えめに保ち、StackChan 由来イベントを direct command ではなく観測として扱う Codex-facing product skill

ROS 2 Jazzy の `colcon` build、micro-ROS firmware の build / flash、実機挙動の検証は、準備済みの ROS / PlatformIO 環境で実施します。

## ライセンス

MIT です。詳細は [LICENSE](LICENSE) を参照してください。
