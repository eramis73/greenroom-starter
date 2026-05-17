"""
DSPy BootstrapFewShot Optimizer

DB'deki labeled örneklerle DealNotesParser'ı optimize eder.
Optimize edilmiş model backend/optimized_parser.json'a kaydedilir.

Neden BootstrapFewShot:
- Raw prompt her seferinde aynı sonucu vermeyebilir
- BootstrapFewShot 15-20 labeled örnek kullanarak en iyi
  few-shot prompt kombinasyonunu otomatik bulur
- Manuel prompt mühendisliği yerine veri ile optimize

Çalıştırmak için:
  cd backend
  python optimize.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import json
import os
import dspy
from dspy.teleprompt import BootstrapFewShot

from config import configure_dspy
from deal_parser import DealNotesParser


TRAINING_PATH = os.path.join(os.path.dirname(__file__), "training_data.json")
OPTIMIZED_PATH = os.path.join(os.path.dirname(__file__), "optimized_parser.json")


def load_training_examples() -> list[dspy.Example]:
    if not os.path.exists(TRAINING_PATH):
        raise FileNotFoundError(
            f"Training seti bulunamadı: {TRAINING_PATH}\n"
            "Önce: python build_training_set.py"
        )

    with open(TRAINING_PATH) as f:
        data = json.load(f)

    examples = []
    for item in data:
        ex = dspy.Example(
            notes_freetext=item["notes_freetext"],
            deal_type=item["deal_type"],
            guarantee_amount=item["guarantee_amount"],
            percentage=item["percentage"],
            expense_cap=item["expense_cap"],
            hospitality_cap=item["hospitality_cap"],
        ).with_inputs("notes_freetext")
        examples.append(ex)

    return examples


def metric(example: dspy.Example, prediction, trace=None) -> float:
    """
    DSPy'ın optimizer'ına her tahmin için ne kadar doğru olduğunu söyler.
    Sayısal alanlarda toleranslı karşılaştırma yapılır (±5% kabul).
    """
    score = 0.0
    total = 0.0

    # Deal type eşleşmesi
    total += 1
    if hasattr(prediction, "deal_type") and prediction.deal_type == example.deal_type:
        score += 1

    # Guarantee (±5% tolerans)
    if example.guarantee_amount > 0:
        total += 1
        try:
            pred_g = float(prediction.guarantee_amount)
            if abs(pred_g - example.guarantee_amount) / example.guarantee_amount <= 0.05:
                score += 1
        except Exception:
            pass

    # Percentage (±0.02 tolerans, örn. 0.80 vs 0.82)
    if example.percentage > 0:
        total += 1
        try:
            pred_p = float(prediction.percentage)
            if abs(pred_p - example.percentage) <= 0.02:
                score += 1
        except Exception:
            pass

    # Expense cap (±5% tolerans)
    if example.expense_cap > 0:
        total += 1
        try:
            pred_c = float(prediction.expense_cap)
            if abs(pred_c - example.expense_cap) / example.expense_cap <= 0.05:
                score += 1
        except Exception:
            pass

    return score / total if total > 0 else 0.0


def optimize():
    print("DSPy BootstrapFewShot optimizasyonu basliyor...")
    configure_dspy()

    examples = load_training_examples()
    print(f"{len(examples)} training örneği yüklendi")

    # Train/val split
    train = examples[:int(len(examples) * 0.8)]
    val = examples[int(len(examples) * 0.8):]
    print(f"Train: {len(train)}, Val: {len(val)}")

    # BootstrapFewShot: max 4 örnek otomatik seçer
    teleprompter = BootstrapFewShot(
        metric=metric,
        max_bootstrapped_demos=4,
        max_labeled_demos=4,
    )

    parser = DealNotesParser()
    optimized = teleprompter.compile(parser, trainset=train)

    # Kaydet
    optimized.save(OPTIMIZED_PATH)
    print(f"Optimize edilmiş model kaydedildi: {OPTIMIZED_PATH}")

    # Val seti üzerinde değerlendirme
    if val:
        print("\nValidation seti değerlendirmesi:")
        scores = []
        for ex in val:
            try:
                pred = optimized(notes_freetext=ex.notes_freetext)
                s = metric(ex, pred)
                scores.append(s)
                print(f"  {ex.notes_freetext[:50]}... → {s:.2f}")
            except Exception as e:
                print(f"  HATA: {e}")
                scores.append(0.0)

        avg = sum(scores) / len(scores) if scores else 0
        print(f"\nOrtalama doğruluk: {avg:.2%}")


if __name__ == "__main__":
    optimize()
