# AIエージェント/LLM 第三者品質保証サービス（売り物）

> 当社ブルーオーシャンの中核オファリング。AIエージェント/LLMアプリを、開発元から独立した第三者の立場で評価し、**そのまま経営・監査・調達に提出できる検証エビデンス**を提供します。

## 提供価値（なぜ買うのか）
- **独立性**：開発元の自己評価ではない、第三者の客観評価。
- **再現可能性**：モデル/プロンプト/seed/版を固定し、誰でも追試できる。
- **説明責任**：スコアの裏に必ず生ログ・サンプル。監査・規制対応のエビデンスになる。
- **回帰検出**：モデル/プロンプト更新時の品質劣化を自動で発見。

## サービスライン（収益モデル）
| メニュー | 内容 | 課金 |
|---|---|---|
| スポット検証 | 評価設計→実行→検証レポート納品 | 案件一括（例 ~240万円/件） |
| 継続モニタリング | 回帰検出を定期実行（ストック収益） | 月額 |
| AI品質体制構築/研修 | 顧客のAI-QA内製化支援 | コンサル/研修 |
| 評価フレーム提供 | 評価軸・ツール・テンプレの提供 | ライセンス |

> 価格は仮説。実際の見積は `/win-deal` で `qa-architect`→`finance` が算定します。

## 中身（このフォルダの構成）
| ファイル | 役割 |
|---|---|
| `methodology.md` | AI品質評価の方法論（8つの評価軸と測定法）。`ai-quality-researcher` の頭脳 |
| `eval_runner.py` | 依存ゼロで動く評価ランナー（採点・合否・回帰検出・レポート出力） |
| `eval_spec.example.json` | 評価仕様のサンプル（社内FAQボットを評価） |
| `templates/test-plan.md` | テスト計画書テンプレ（提案・受注用） |
| `templates/qa-report.md` | 検証報告書テンプレ（納品物） |

## クイックスタート

```bash
# 1) サンプルを評価（標準出力にレポート）
python3 products/ai-agent-qa/eval_runner.py products/ai-agent-qa/eval_spec.example.json

# 2) レポートをJSONで保存し、ベースライン化
python3 products/ai-agent-qa/eval_runner.py products/ai-agent-qa/eval_spec.example.json \
  --out report.json --save-baseline baseline.json

# 3) 回帰検出（更新後のモデルを過去ベースラインと比較）
python3 products/ai-agent-qa/eval_runner.py new_spec.json --baseline baseline.json

# 4) CIの品質ゲート（不合格なら終了コード1）
python3 products/ai-agent-qa/eval_runner.py products/ai-agent-qa/eval_spec.example.json --gate
```

> **サンプルは意図的に「安全性」の欠陥を1つ含めています**（プロンプトインジェクションで管理者パスワードを漏らす応答）。
> そのため判定は **不合格（FAIL）** になります。これは「総合89%でも、安全性ゲート未達なら出荷不可」という、
> AIの安全性を妥協なく検出するツールの価値を示すためのデモです。

## 評価仕様(JSON)の書き方
`eval_spec.example.json` を雛形に、対象AIの応答を `responses`（複数試行）として記録し、`scoring` で採点方法を指定します。

採点メソッド:
| method | 用途 |
|---|---|
| `exact` / `equals_any` | 完全一致 / いずれかと一致 |
| `contains`（mode: all/any） | 必須語の包含（タスク達成度・事実性） |
| `not_contains` | 禁止語の不在（安全性・情報漏えい） |
| `regex` | 正規表現（フォーマット検証など） |

各軸の合格基準は `thresholds.by_axis` で設定（例：安全性は 1.0＝1件も許容しない）。

## ライブ評価への拡張
本ランナーは「記録済み応答(responses)」を採点するオフライン設計です（ネットワーク不要・再現性重視）。
実運用では `ai-eval-engineer` が、対象AIのAPIを叩いて応答を収集→この形式に整形→採点、というパイプラインに拡張します。
（Claude API を使う場合のプロンプトキャッシュ等の実装方針は `cto` / `ai-eval-engineer` が設計）
