# 協働モデル（オペレーティングモデル）

「実際に協働して稼ぐ」ための、部門間の連携ルールです。

## 大原則：オーケストレーションは本体が行う
Claude Code のサブエージェントは**他のサブエージェントを直接起動できません**（無限再帰防止のため Agent/Task ツールを持たない）。
そのため部門間の協働は次の形を取ります。

```
ユーザー / Claude本体（オーケストレーター）
   ├─(1)→ sales を起動 → 案件カルテ
   ├─(2)→ qa-architect を起動（案件カルテを入力）→ 見積根拠
   ├─(3)→ finance を起動（見積根拠を入力）→ 採算
   └─(4)→ ... と成果物をバケツリレーで引き継ぐ
```

この「台本」を再利用可能にしたのが `.claude/commands/` のワークフローです。各エージェントは自分の前工程・後工程を system prompt に明記しているため、誰に渡すべきかが自律的に分かります。

## 主要バリューストリーム（価値の流れ）

### A. 受注 → デリバリー（既存事業 / `/win-deal` → 個別実行）
```
sales(要件) → qa-architect(計画・見積根拠) → finance(採算) → legal(契約)
            → 受注 → test-engineer / test-automation-engineer / security-tester(実施)
            → qa-architect(品質ゲート) → 納品レポート → sales(顧客へ)
```

### B. AI第三者検証（ブルーオーシャン / `/ai-qa`）
```
ai-quality-researcher(評価設計) → ai-eval-engineer(eval実装・実行)
            → security-tester(安全性) → qa-architect(レビュー)
            → ai-eval-engineer(検証レポート) → 納品
```

### C. 経営意思決定（`/board-meeting`）
```
corp-strategy(戦略案) + cto(技術) + finance(採算) → ceo(意思決定) → 各部門へKPI展開
```

### D. 新規事業創出（`/new-service`）
```
corp-strategy(市場機会) → ai-quality-researcher/cto(中身・技術) → marketing(GTM)
            → finance(収益モデル) → hr(体制) → 企画書 → /board-meeting(投資判断)
```

## RACI（主要プロセス）

| プロセス | Responsible（実行） | Accountable（最終責任） | Consulted（相談） | Informed（共有） |
|---|---|---|---|---|
| 受注提案 | sales | ceo | qa-architect, finance, legal | corp-strategy |
| テスト計画 | qa-architect | cto | test-engineer | sales |
| 検証実施 | test-engineer 他 | qa-architect | security-tester | sales |
| AI評価設計 | ai-quality-researcher | cto | security-tester | qa-architect |
| AI評価実施 | ai-eval-engineer | qa-architect | ai-quality-researcher | sales |
| 見積採算 | finance | ceo | qa-architect, hr | sales |
| 契約 | legal | ceo | qa-architect | finance |
| 全社戦略 | corp-strategy | ceo | cto, finance, marketing | 全部門 |

## 会議体（コマンド）
| 会議体 | コマンド | 目的 | 出席（起動）エージェント |
|---|---|---|---|
| 受注会議 | `/win-deal` | 提案・受注の意思決定 | sales, qa-architect, finance, legal |
| AI検証PJ | `/ai-qa` | ブルーオーシャンの実行 | ai-quality-researcher, ai-eval-engineer, security-tester, qa-architect |
| 経営会議 | `/board-meeting` | 戦略・投資の意思決定 | corp-strategy, cto, finance, (marketing/hr/legal), ceo |
| 新規事業会議 | `/new-service` | 新サービス企画 | corp-strategy, ai-quality-researcher, cto, marketing, finance, hr |

## 品質ゲート
- 顧客に出るすべての検証成果物は **`qa-architect` のレビュー（承認/条件付き/差し戻し）** を通す。
- 顧客に出るすべての見積は **`finance` の採算判定** を通す（粗利率しきい値）。
- 対外発信は **`pr-ir` ＋ `legal`（開示適正性）** を通す。

## 行動原則（全社共通バリュー）
1. **独立性・公正性**：第三者検証会社の生命線。顧客に忖度して品質判断を曲げない。
2. **エビデンス第一**：すべての判定は再現可能な証跡で裏付ける。
3. **稼ぐ規律**：採算の合わない仕事は受けない／代替案を出す。
4. **二兎を追う**：本業の安定収益（7）とブルーオーシャン投資（3）を両立。
