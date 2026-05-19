"""
Baseline vs Optimized karsilastirmasi.

Calistirilma sirasi:
  1. python eval.py --mode baseline   -> API key ile raw modeli olc
  2. python optimize.py               -> BootstrapFewShot calistir
  3. python eval.py --mode optimized  -> optimize edilmis modeli olc
  4. python eval.py --mode compare    -> sonuclari karsilastir

Test seti, training setinden FARKLI ornekler kullanir (offset 20).
Bu sayede model kendi egitildigi veriler uzerinde olculmuyor.
"""

import json
import os
import sys
import argparse
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import configure_dspy
from deal_parser import DealNotesParser
import dspy


DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "greenroom.db"
)
RESULTS_DIR = os.path.dirname(os.path.abspath(__file__))
BASELINE_RESULTS  = os.path.join(RESULTS_DIR, "eval_baseline.json")
OPTIMIZED_RESULTS = os.path.join(RESULTS_DIR, "eval_optimized.json")
OPTIMIZED_MODEL   = os.path.join(RESULTS_DIR, "optimized_parser.json")


# ── Test seti: training setinden FARKLI ornekler (offset 20, limit 10) ───────

async def load_test_set(limit: int = 10) -> list[dict]:
    from libsql_client import create_client

    client = create_client(url=f"file:{DB_PATH}")
    result = await client.execute("""
        SELECT
            d.deal_notes_freetext,
            d.deal_type,
            d.guarantee_amount,
            d.percentage,
            d.expense_cap,
            d.hospitality_cap,
            ar.name AS artist
        FROM deals d
        JOIN shows      sh ON d.show_id = sh.id
        JOIN artists    ar ON sh.artist_id = ar.id
        JOIN settlements s  ON s.show_id = sh.id
        WHERE d.deal_notes_freetext IS NOT NULL
          AND length(d.deal_notes_freetext) > 20
          AND d.deal_type IN ('vs', 'percentage_of_net', 'flat')
          AND d.guarantee_amount IS NOT NULL
          AND d.percentage IS NOT NULL
          AND s.status IN ('finalized', 'paid')
          AND s.disputed_at IS NULL
        ORDER BY sh.date DESC
        LIMIT ? OFFSET 20
    """, [limit])
    await client.close()

    examples = []
    for row in result.rows:
        examples.append({
            "notes_freetext":   row[0] or "",
            "deal_type":        row[1] or "vs",
            "guarantee_amount": float(row[2] or 0),
            "percentage":       float(row[3] or 0),
            "expense_cap":      float(row[4] or 0),
            "hospitality_cap":  float(row[5] or 0),
            "artist":           row[6] or "",
        })
    return examples


# ── Metrik (optimize.py ile ayni) ─────────────────────────────────────────────

def score_prediction(example: dict, prediction) -> dict:
    """
    Her alan icin ayri skor uret. optimize.py ile ayni toleranslar:
      - deal_type    : exact match
      - guarantee    : +-5%
      - percentage   : +-0.02 (ornek: 0.80 vs 0.82)
      - expense_cap  : +-5% (0 ise atliyoruz)
    """
    scores = {}

    # Deal type
    pred_type = getattr(prediction, "deal_type", "").strip().lower()
    scores["deal_type"] = (pred_type == example["deal_type"].lower())

    # Guarantee
    try:
        pred_g = float(getattr(prediction, "guarantee_amount", 0))
        true_g = example["guarantee_amount"]
        if true_g > 0:
            scores["guarantee"] = abs(pred_g - true_g) / true_g <= 0.05
        else:
            scores["guarantee"] = pred_g == 0
    except Exception:
        scores["guarantee"] = False

    # Percentage
    try:
        pred_p = float(getattr(prediction, "percentage", 0))
        scores["percentage"] = abs(pred_p - example["percentage"]) <= 0.02
    except Exception:
        scores["percentage"] = False

    # Expense cap (sadece ground truth > 0 ise)
    if example["expense_cap"] > 0:
        try:
            pred_c = float(getattr(prediction, "expense_cap", 0))
            true_c = example["expense_cap"]
            scores["expense_cap"] = abs(pred_c - true_c) / true_c <= 0.05
        except Exception:
            scores["expense_cap"] = False

    total = sum(scores.values())
    return {"fields": scores, "score": total / len(scores), "total": total, "max": len(scores)}


# ── Degerlendirme dongusu ──────────────────────────────────────────────────────

def evaluate(parser: DealNotesParser, examples: list[dict], label: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  {label} ({len(examples)} test ornegi)")
    print(f"{'='*60}")

    all_scores = []
    field_hits = {"deal_type": 0, "guarantee": 0, "percentage": 0, "expense_cap": 0}
    field_counts = {"deal_type": 0, "guarantee": 0, "percentage": 0, "expense_cap": 0}

    for i, ex in enumerate(examples):
        artist = ex["artist"][:25]
        try:
            pred = parser(notes_freetext=ex["notes_freetext"])
            result = score_prediction(ex, pred)
            all_scores.append(result["score"])

            status = "PASS" if result["score"] >= 0.75 else "FAIL"
            print(f"  [{status}] {artist:<25s}  score={result['score']:.2f}  "
                  f"type={'OK' if result['fields'].get('deal_type') else 'FAIL'} "
                  f"guar={'OK' if result['fields'].get('guarantee') else 'FAIL'} "
                  f"pct={'OK' if result['fields'].get('percentage') else 'FAIL'}")

            for field, hit in result["fields"].items():
                if field in field_hits:
                    field_hits[field] += int(hit)
                    field_counts[field] += 1

        except Exception as e:
            print(f"  [ERR] {artist:<25s}  {str(e)[:60]}")
            all_scores.append(0.0)

    avg = sum(all_scores) / len(all_scores) if all_scores else 0

    field_accuracy = {
        f: field_hits[f] / field_counts[f] if field_counts[f] > 0 else None
        for f in field_hits
    }

    print(f"\n  Ortalama skor       : {avg:.1%}")
    print(f"  Deal type dogruluk  : {field_accuracy['deal_type']:.1%}" if field_accuracy['deal_type'] is not None else "  Deal type: -")
    print(f"  Guarantee dogruluk  : {field_accuracy['guarantee']:.1%}" if field_accuracy['guarantee'] is not None else "  Guarantee: -")
    print(f"  Percentage dogruluk : {field_accuracy['percentage']:.1%}" if field_accuracy['percentage'] is not None else "  Percentage: -")
    if field_accuracy['expense_cap'] is not None:
        print(f"  Expense cap         : {field_accuracy['expense_cap']:.1%}")

    return {
        "label": label,
        "avg_score": round(avg, 4),
        "field_accuracy": {k: round(v, 4) if v is not None else None for k, v in field_accuracy.items()},
        "n": len(examples),
        "per_example": all_scores,
    }


# ── Compare ───────────────────────────────────────────────────────────────────

def compare():
    if not os.path.exists(BASELINE_RESULTS):
        print("Baseline sonucu bulunamadi. Once: python eval.py --mode baseline")
        return
    if not os.path.exists(OPTIMIZED_RESULTS):
        print("Optimized sonucu bulunamadi. Once: python eval.py --mode optimized")
        return

    with open(BASELINE_RESULTS) as f:
        base = json.load(f)
    with open(OPTIMIZED_RESULTS) as f:
        opt = json.load(f)

    print("\n" + "="*60)
    print("  BASELINE vs OPTIMIZED — COMPARISON")
    print("="*60)
    print(f"  {'Metric':<25s}  {'Baseline':>10s}  {'Optimized':>10s}  {'Delta':>10s}")
    print(f"  {'-'*25}  {'-'*10}  {'-'*10}  {'-'*10}")

    def row(label, b, o):
        if b is None or o is None:
            return
        delta = o - b
        sign = "+" if delta >= 0 else ""
        print(f"  {label:<25s}  {b:>9.1%}  {o:>9.1%}  {sign}{delta:>8.1%}")

    row("Average score", base["avg_score"], opt["avg_score"])
    for field in ["deal_type", "guarantee", "percentage", "expense_cap"]:
        b_val = base["field_accuracy"].get(field)
        o_val = opt["field_accuracy"].get(field)
        if b_val is not None and o_val is not None:
            row(f"  {field}", b_val, o_val)

    delta_avg = opt["avg_score"] - base["avg_score"]
    print(f"\n  Result: BootstrapFewShot improved average score by {'+' if delta_avg >= 0 else ''}{delta_avg:.1%}.")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser_arg = argparse.ArgumentParser()
    parser_arg.add_argument("--mode", choices=["baseline", "optimized", "compare"],
                            default="baseline")
    args = parser_arg.parse_args()

    if args.mode == "compare":
        compare()
        return

    configure_dspy()
    examples = await load_test_set(limit=10)

    if not examples:
        print("Test ornegi bulunamadi. DB'yi kontrol edin.")
        return

    print(f"{len(examples)} test ornegi yuklendi (training setinden FARKLI)")

    deal_parser = DealNotesParser()

    if args.mode == "optimized":
        if not os.path.exists(OPTIMIZED_MODEL):
            print(f"Optimized model bulunamadi: {OPTIMIZED_MODEL}")
            print("Once calistirin: python optimize.py")
            return
        deal_parser.load(OPTIMIZED_MODEL)
        print("Optimize edilmis model yuklendi.")
        label = "OPTIMIZED (BootstrapFewShot)"
        out_path = OPTIMIZED_RESULTS
    else:
        print("Raw (optimize edilmemis) model kullaniliyor.")
        label = "BASELINE (Raw Model)"
        out_path = BASELINE_RESULTS

    results = evaluate(deal_parser, examples, label)

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Sonuclar kaydedildi: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
