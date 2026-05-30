#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VeriAgent — AIエージェント/LLM 第三者品質評価ランナー
========================================================

依存ゼロ（Python 3.8+ 標準ライブラリのみ）で動く、AIの出力を採点する eval ツール。
当社ブルーオーシャン「AIエージェント/LLMの第三者品質保証」の“売り物”の中核。

使い方:
    python3 eval_runner.py <spec.json> [オプション]

オプション:
    --gate                 不合格なら終了コード1を返す（CIの品質ゲート用）
    --out <path>           評価レポート(JSON)を書き出す
    --baseline <path>      過去レポートと比較して品質回帰(リグレッション)を検出
    --save-baseline <path> 今回の結果をベースラインとして保存
    --quiet                サマリのみ表示

評価仕様(spec.json)の形:
    {
      "metadata": {"target": "...", "model": "...", "version": "...", "evaluator": "..."},
      "thresholds": {"overall_pass_rate": 0.8, "by_axis": {"安全性": 1.0}},
      "cases": [
        {
          "id": "TC-001",
          "axis": "タスク達成度",
          "input": "営業時間は？",
          "scoring": {"method": "contains", "expected": ["9:00", "18:00"]},
          "responses": ["営業時間は9:00〜18:00です。", "9:00から18:00までです。"]
        }
      ]
    }

採点メソッド(scoring.method):
    exact         expected(str)        : 完全一致(前後空白無視)
    equals_any    expected(list)       : いずれかと完全一致
    contains      expected(str|list)   : 部分文字列を含む。mode:"all"(既定)/"any", ignore_case:bool
    not_contains  forbidden(str|list)  : 禁止語を含まない（安全性向け）。ignore_case:bool
    regex         pattern(str)         : 正規表現にマッチ。ignore_case:bool

各ケースは responses(list) か response(str)。複数試行で pass率・ばらつき(一貫性)を測る。
ケースは pass_threshold(既定1.0=全試行合格)以上の試行合格率で「合格」と判定。
"""

import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone


# ----------------------------- 採点ロジック ----------------------------- #

def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def score_trial(scoring, output):
    """1試行を採点して (passed: bool, detail: str) を返す。"""
    if not isinstance(scoring, dict):
        return False, "scoring が不正（dictではない）"
    method = scoring.get("method")
    text = "" if output is None else str(output)
    ic = bool(scoring.get("ignore_case", False))
    hay = text.lower() if ic else text

    if method == "exact":
        expected = str(scoring.get("expected", ""))
        return (text.strip() == expected.strip()), "exact: 期待={!r}".format(expected)

    if method == "equals_any":
        opts = [str(e).strip() for e in _as_list(scoring.get("expected"))]
        return (text.strip() in opts), "equals_any: 候補数={}".format(len(opts))

    if method == "contains":
        terms = [str(e) for e in _as_list(scoring.get("expected"))]
        if not terms:
            return False, "contains: expected が空"
        terms_cmp = [t.lower() for t in terms] if ic else terms
        hits = [t for t in terms_cmp if t in hay]
        mode = scoring.get("mode", "all")
        ok = (len(hits) == len(terms_cmp)) if mode == "all" else (len(hits) > 0)
        missing = [terms[i] for i, t in enumerate(terms_cmp) if t not in hay]
        detail = "contains({}): 不足={}".format(mode, missing) if missing else "contains({}): OK".format(mode)
        return ok, detail

    if method == "not_contains":
        terms = [str(e) for e in _as_list(scoring.get("forbidden"))]
        terms_cmp = [t.lower() for t in terms] if ic else terms
        found = [terms[i] for i, t in enumerate(terms_cmp) if t in hay]
        detail = "not_contains: 検出={}".format(found) if found else "not_contains: 禁止語なし"
        return (len(found) == 0), detail

    if method == "regex":
        pattern = scoring.get("pattern", "")
        flags = re.IGNORECASE if ic else 0
        try:
            ok = re.search(pattern, text, flags) is not None
        except re.error as e:
            return False, "regex: 不正なパターン ({})".format(e)
        return ok, "regex: /{}/".format(pattern)

    return False, "未知の採点メソッド: {!r}".format(method)


def evaluate_case(case):
    """1ケースを全試行採点して集計結果dictを返す。"""
    trials = case.get("responses")
    if trials is None:
        single = case.get("response")
        trials = [single] if single is not None else []
    scoring = case.get("scoring", {})

    trial_results = []
    for out in trials:
        passed, detail = score_trial(scoring, out)
        trial_results.append({"passed": passed, "detail": detail})

    n = len(trial_results)
    passed_trials = sum(1 for t in trial_results if t["passed"])
    pass_rate = (passed_trials / n) if n else 0.0
    threshold = float(case.get("pass_threshold", 1.0))
    case_passed = (n > 0) and (pass_rate >= threshold)

    return {
        "id": case.get("id", "(no-id)"),
        "axis": case.get("axis", "(未分類)"),
        "input": case.get("input", ""),
        "method": scoring.get("method"),
        "n_trials": n,
        "passed_trials": passed_trials,
        "pass_rate": round(pass_rate, 4),
        "pass_threshold": threshold,
        "passed": case_passed,
        "trials": trial_results,
    }


def aggregate(case_results):
    """軸別・全体に集計。"""
    axes = {}
    for c in case_results:
        a = axes.setdefault(c["axis"], {"cases": [], "rates": []})
        a["cases"].append(c)
        a["rates"].append(c["pass_rate"])

    axis_summary = {}
    for axis, data in axes.items():
        cases = data["cases"]
        total = len(cases)
        passed = sum(1 for c in cases if c["passed"])
        total_trials = sum(c["n_trials"] for c in cases)
        passed_trials = sum(c["passed_trials"] for c in cases)
        consistency_stdev = statistics.pstdev(data["rates"]) if len(data["rates"]) > 1 else 0.0
        axis_summary[axis] = {
            "total_cases": total,
            "passed_cases": passed,
            "case_pass_rate": round(passed / total, 4) if total else 0.0,
            "total_trials": total_trials,
            "passed_trials": passed_trials,
            "trial_pass_rate": round(passed_trials / total_trials, 4) if total_trials else 0.0,
            "consistency_stdev": round(consistency_stdev, 4),
        }

    total_cases = len(case_results)
    passed_cases = sum(1 for c in case_results if c["passed"])
    overall = {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "case_pass_rate": round(passed_cases / total_cases, 4) if total_cases else 0.0,
    }
    return axis_summary, overall


def judge(axis_summary, overall, thresholds):
    """しきい値に照らして合否判定。"""
    reasons = []
    ok = True

    overall_th = thresholds.get("overall_pass_rate")
    if overall_th is not None:
        if overall["case_pass_rate"] + 1e-9 < float(overall_th):
            ok = False
            reasons.append("全体ケース合格率 {:.0%} < 基準 {:.0%}".format(
                overall["case_pass_rate"], float(overall_th)))

    by_axis = thresholds.get("by_axis", {}) or {}
    for axis, th in by_axis.items():
        cur = axis_summary.get(axis, {}).get("case_pass_rate", 0.0)
        if cur + 1e-9 < float(th):
            ok = False
            reasons.append("[{}] 合格率 {:.0%} < 基準 {:.0%}".format(axis, cur, float(th)))

    return ok, reasons


def detect_regression(axis_summary, overall, baseline, delta=0.001):
    """ベースラインと比較して品質回帰を検出。"""
    regressions = []
    base_axes = baseline.get("axes", {})
    for axis, cur in axis_summary.items():
        prev = base_axes.get(axis)
        if not prev:
            continue
        drop = prev.get("case_pass_rate", 0.0) - cur["case_pass_rate"]
        if drop > delta:
            regressions.append("[{}] 合格率が低下: {:.0%} → {:.0%}".format(
                axis, prev["case_pass_rate"], cur["case_pass_rate"]))
    base_overall = baseline.get("overall", {}).get("case_pass_rate")
    if base_overall is not None and (base_overall - overall["case_pass_rate"]) > delta:
        regressions.append("[全体] 合格率が低下: {:.0%} → {:.0%}".format(
            base_overall, overall["case_pass_rate"]))
    return regressions


# ----------------------------- 表示 ----------------------------- #

def fmt_pct(x):
    return "{:5.1f}%".format(x * 100)


def print_report(meta, axis_summary, overall, verdict_ok, reasons,
                 case_results, regressions, quiet=False):
    line = "=" * 64
    print(line)
    print("VeriAgent — AIエージェント/LLM 第三者品質検証レポート")
    print(line)
    print("対象      : {}".format(meta.get("target", "(不明)")))
    print("モデル/版 : {} / {}".format(meta.get("model", "(不明)"), meta.get("version", "(不明)")))
    print("評価者    : {}".format(meta.get("evaluator", "ai-eval-engineer")))
    print("実行日時  : {}".format(datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")))
    print()

    print("■ 評価軸別サマリ")
    header = "  {:<16}{:>12}{:>14}{:>14}{:>11}".format(
        "評価軸", "合格ケース", "ケース合格率", "試行合格率", "ばらつき")
    print(header)
    print("  " + "-" * 62)
    for axis, s in axis_summary.items():
        ratio = "{}/{}".format(s["passed_cases"], s["total_cases"])
        print("  {:<16}{:>12}{:>14}{:>14}{:>11.3f}".format(
            axis, ratio, fmt_pct(s["case_pass_rate"]),
            fmt_pct(s["trial_pass_rate"]), s["consistency_stdev"]))
    print("  " + "-" * 62)
    ratio_all = "{}/{}".format(overall["passed_cases"], overall["total_cases"])
    print("  {:<16}{:>12}{:>14}".format("全体", ratio_all, fmt_pct(overall["case_pass_rate"])))
    print()

    failed = [c for c in case_results if not c["passed"]]
    if failed and not quiet:
        print("■ 不合格ケース（要改善）")
        for c in failed:
            print("  - {} [{}] 合格率 {} (基準 {})".format(
                c["id"], c["axis"], fmt_pct(c["pass_rate"]), fmt_pct(c["pass_threshold"])))
            print("      入力: {}".format(str(c["input"])[:60]))
            ng = next((t["detail"] for t in c["trials"] if not t["passed"]), "")
            if ng:
                print("      所見: {}".format(ng))
        print()

    if regressions:
        print("■ 品質回帰（リグレッション）検出 ⚠")
        for r in regressions:
            print("  - {}".format(r))
        print()

    print(line)
    if verdict_ok and not regressions:
        print("判定: ✅ 合格（PASS）— 第三者品質基準を満たしています")
    else:
        print("判定: ❌ 不合格（FAIL）— 出荷前に改善が必要です")
        for r in reasons:
            print("  理由: {}".format(r))
        if regressions:
            print("  理由: 品質回帰を {} 件検出".format(len(regressions)))
    print(line)


# ----------------------------- main ----------------------------- #

def main(argv=None):
    p = argparse.ArgumentParser(description="VeriAgent AI品質評価ランナー")
    p.add_argument("spec", help="評価仕様 JSON のパス")
    p.add_argument("--gate", action="store_true", help="不合格なら終了コード1（CIゲート）")
    p.add_argument("--out", help="評価レポート(JSON)の出力先")
    p.add_argument("--baseline", help="比較用ベースライン(JSON)")
    p.add_argument("--save-baseline", dest="save_baseline", help="今回結果をベースライン保存")
    p.add_argument("--quiet", action="store_true", help="サマリのみ")
    args = p.parse_args(argv)

    try:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
    except FileNotFoundError:
        print("エラー: 仕様ファイルが見つかりません: {}".format(args.spec), file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print("エラー: JSON を解析できません: {}".format(e), file=sys.stderr)
        return 2

    cases = spec.get("cases", [])
    if not cases:
        print("エラー: cases が空です。評価仕様を確認してください。", file=sys.stderr)
        return 2

    case_results = [evaluate_case(c) for c in cases]
    axis_summary, overall = aggregate(case_results)
    thresholds = spec.get("thresholds", {}) or {}
    verdict_ok, reasons = judge(axis_summary, overall, thresholds)

    regressions = []
    if args.baseline:
        try:
            with open(args.baseline, encoding="utf-8") as f:
                baseline = json.load(f)
            regressions = detect_regression(axis_summary, overall, baseline)
        except FileNotFoundError:
            print("警告: ベースラインが見つかりません: {}".format(args.baseline), file=sys.stderr)

    print_report(spec.get("metadata", {}), axis_summary, overall,
                 verdict_ok, reasons, case_results, regressions, quiet=args.quiet)

    report = {
        "metadata": spec.get("metadata", {}),
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "axes": axis_summary,
        "overall": overall,
        "verdict": "PASS" if (verdict_ok and not regressions) else "FAIL",
        "reasons": reasons,
        "regressions": regressions,
        "cases": [{k: v for k, v in c.items() if k != "trials"} for c in case_results],
    }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("\nレポートを書き出しました: {}".format(args.out))
    if args.save_baseline:
        with open(args.save_baseline, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("ベースラインを保存しました: {}".format(args.save_baseline))

    if args.gate and report["verdict"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
