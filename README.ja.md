# flow5ctl

**[flow5](https://flow5.tech) を使った、AI駆動の機体設計。**

`flow5ctl` は、Claude Desktop / Claude Code / Codex などの AI エージェントが
flow5 のヘッドレス解析エンジンを操作して、低レイノルズ数領域の機体を設計・解析
できるようにするツールです。

1つの Python パッケージに、2つのフロントエンドが載っています。

| フロントエンド | コマンド | 対象 |
|---|---|---|
| **MCPサーバー** | `flow5ctl mcp` | Claude Desktop、その他のMCPクライアント |
| **CLI** | `flow5ctl <verb>` | Claude Code、Codex、人間、CI |

> **ステータス: コアは動作します。MCPサーバーはまだありません。**
>
> `flow5ctl analyze` は既に実解析を実行します — 幾何計算、flow5のXML生成と検証、
> 2D翼型ポーラーの自動計算とキャッシュ、flow5が要求する2パス実行、結果の要約まで。
> テスト131本（うち8本は実機 flow5 7.57 に対して実行）。
> [ロードマップ](docs/ROADMAP.md) の Phase 1 と Phase 2 の大部分が完了、MCP は Phase 3 です。
>
> 検証は **macOS のみ**、**flow5 7.57** に対して。
> 途中で見つかったこと（再現可能な flow5 のクラッシュと、出力が素朴な読み手を誤らせる
> 7つの罠）は [検証ログ](docs/log/2026-09-03-poc-verification.md) にあり、
> [`poc/`](poc) から全て再実行できます。

英語版 README: [README.md](README.md)

---

## なぜ作るのか

flow5 は優れたポテンシャル流ソルバーですが、機体設計は手作業のループです。
平面形を描き、翼型を選び、極線を設定し、走らせ、グラフを読み、直し、また走らせる。
このループはまさに AI エージェントが得意とするもの — **ソルバーを確実に操作できるなら。**

操作はできます。flow5 には `flow5 -s script.xml` というヘッドレス実行モードがあり、
機体1機の解析が1秒未満で終わります。足りないのは、エージェントが実際に使える
インターフェースの方です。XMLスキーマは巨大で、省略すると静かに致命的になる項目があり、
結果は Unicode 混じりの横長 CSV で返ってきます。

`flow5ctl` はその欠けている層です。flow5 バイナリの薄いラッパー **ではありません** —
それではシェルコマンドと変わりません。以下を行うドメイン層です。

- 生の XML ではなく、**高レベルな設計記述**（スパン、テーパー、翼型、質量、重心）を受け取る
- flow5 が必要とするのにバッチモードでは導出してくれない幾何量（基準面積・スパン・MAC）を計算する
- すべての XML を生成・検証する
- ソルバーを実行し、失敗を平易な言葉で診断する
- 生データではなく、**エージェントが推論できる要約**（CL傾斜、最良L/Dとその迎角、Cm_α、静安定余裕、中立点）を返す
- 設計全体を **git で扱えるプロジェクトディレクトリ** に保持し、人間が確認・差分比較・レビューできるようにする

これが単なる配管作業ではない理由：flow5 は1つのスクリプトで2Dと3Dの両方を要求すると
**セグメンテーション違反で落ち**、ポーラーの `.csv` にはカンマが1つも無く、データの
1行目がヘッダ行に改行なしで連結され、`Static margin` は分数に見えて実はパーセント、
運用点ファイルは全ポーラーのディレクトリに**別ポーラーの中身のまま**複製され、
安定性を間違った極線タイプに要求すると `5.995e+51` という固有値を平然と返します。
そのすべてを検証し、文書化し、対処済みです。

## 誰のためのものか

flow5 / XFLR5 を使っている低レイノルズ数コミュニティ全体を対象にしています。

- **人力飛行機**（鳥人間コンテスト、Daedalus級）: スパン30m超、AR約30、
  Re 5×10⁵〜1×10⁶、地面効果、スパン方向荷重分布、構造重量配分
- **RCグライダー**（F3B / F3F / F5J、DLG）: スパン1.5〜4m、Re 5×10⁴〜3×10⁵、
  キャンバー変更フラップ、バラスト、広い速度域
- 同じ領域の**小型UAV・模型航空機**

プリセットがそれぞれに必要なデフォルト値を持ち、下地のモデル自体は汎用です。

## クイックスタート

先に flow5 を [flow5.tech](https://flow5.tech) からインストールしてください。

```bash
git clone https://github.com/97kuek/flow5ctl && cd flow5ctl
uv sync                          # または: pip install -e .
uv run flow5ctl doctor           # flow5 のインストールを確認
```

機体を記述して解析します：

```yaml
# glider.yaml
preset: rc-glider
requirements: {cruise_speed: 12.0, objective: min_sink}
mass:
  components:
    - {tag: fuselage,   mass: 0.40, at: [ 0.12,  0.00, 0.00]}
    - {tag: wing_left,  mass: 0.10, at: [ 0.05, -0.75, 0.02]}
    - {tag: wing_right, mass: 0.10, at: [ 0.05,  0.75, 0.02]}
airfoils:
  - {name: AG35, source: 'naca:2409'}
wing:
  airfoil: AG35
  planform: {span: 3.0, root_chord: 0.24, taper: 0.55, dihedral: 3.0, washout: -1.5}
```

```bash
flow5ctl init Glider --file glider.yaml
flow5ctl analyze Glider --type T1 --speed 12 --alpha=-2,8,2
```

必要な2D翼型ポーラーは初回に自動計算されキャッシュされるので、初回は約12秒、
以降は1秒未満です。

> `pipx install flow5ctl` と PyPI リリースは 0.1.0 で提供予定です。

Claude Desktop の MCP 設定に追加：

```json
{
  "mcpServers": {
    "flow5": { "command": "flow5ctl", "args": ["mcp"] }
  }
}
```

あとはこう聞くだけです —
*「最小沈下率を狙った3mのF5Jグライダーを設計して。重心を MAC の30%から40%に
動かしたときの影響も見せて」*

## 仕組み

```
                design.yaml  ← 信頼できる唯一の情報源。人にもLLMにも読める。gitに入る
                     │
        flow5ctl     │  幾何計算 → XML生成 → 検証
                     ▼
            plane.xml + polar.xml + script.xml   ← ビルド成果物。使い捨て
                     │
                     ▼
            flow5 -s script.xml                  ← ヘッドレス、1スイープ約0.5秒
                     │
                     ▼
            polars.csv + oppoints/ + project.fl5
                     │
        flow5ctl     │  パース → 正規化 → 要約
                     ▼
            構造化された結果と警告 → エージェントへ
                                  → `flow5ctl open` で .fl5 をGUIに渡して人間が確認
```

YAML がソース、XML はビルド成果物です。
詳細は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | レイヤ構成、データフロー、なぜ1コア2フロントエンドなのか |
| [docs/DOMAIN-MODEL.md](docs/DOMAIN-MODEL.md) | 用語と `design.yaml` スキーマ |
| [docs/MCP-TOOLS.md](docs/MCP-TOOLS.md) | エージェントに公開するツール群 |
| [docs/FLOW5-INTERFACE.md](docs/FLOW5-INTERFACE.md) | flow5 バッチ/XML インターフェースの検証済みリファレンス |
| [docs/DESIGN-GUIDE.md](docs/DESIGN-GUIDE.md) | エージェントが守るべき空力上のガードレール |
| [docs/ROADMAP.md](docs/ROADMAP.md) | フェーズとマイルストーン |
| [docs/adr/](docs/adr/) | アーキテクチャ決定記録 |
| [docs/log/](docs/log/) | 調査・検証ログ |
| [poc/](poc/) | 検証ハーネス — 記載の全数値を再現できます |

コントリビュート: [CONTRIBUTING.md](CONTRIBUTING.md) ·
このリポジトリでのAIエージェント運用: [AGENTS.md](AGENTS.md)

## 既知の制限

- **フラップ・制御面は非対応で、原理的に対応できません。** flow5 の機体XMLには
  フラップ/ヒンジの要素が存在せず、フラップは Foil オブジェクトの属性で `.dat`
  ファイルには載りません。GUIで作った `.fl5` を読み込む逃げ道も、プロジェクト由来の
  機体が新規解析とペアリングされないため使えません。したがって T6 制御極線は
  このインターフェースでは到達不能です。キャンバー変更翼のRCグライダーには影響します
  — [検証ログ](docs/log/2026-09-03-poc-verification.md) の findings 9, 10 を参照。
- **検証は macOS のみ。** Linux と Windows は動作見込みですが未検証です。報告歓迎。
- **flow5 自体の不具合は引き継ぎます。** 7.57 ではダッチロール周波数と短周期
  モードの出力が信頼できないため、意図的に報告しません。

## 安全に関する注意

flow5 はポテンシャル流ソルバーです。失速後の挙動、剥離、構造変形は扱えません。
**人が乗る機体を、ポテンシャル流解析だけを根拠に製作決定してはいけません。**
詳しくは [docs/DESIGN-GUIDE.md](docs/DESIGN-GUIDE.md) を読んでください。

## flow5 との関係

flow5 は André Deperrois 氏による独立したプロジェクトで、GPL-3.0 のもと
[techwinder/flow5](https://github.com/techwinder/flow5) で公開されています。
`flow5ctl` は flow5 の実行ファイルをサブプロセスとして呼び出す独立したツールであり、
flow5 のコードをリンクせず、再配布もしません（flow5 はご自身でインストールしてください）。
[ADR-0006](docs/adr/0006-licensing-and-the-gpl-boundary.md) を参照。

`flow5ctl` は flow5 プロジェクトとは無関係であり、その承認を受けたものでもありません。

## ライセンス

Apache-2.0（提案中 — [ADR-0006](docs/adr/0006-licensing-and-the-gpl-boundary.md)）
