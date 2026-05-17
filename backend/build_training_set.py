"""
BootstrapFewShot için training seti oluşturur.

DB'deki deals tablosundan hem prose notu hem structured field'ları
dolu olan kayıtları alır. Bunlar labeled ground truth olarak kullanılır.

DSPy'ın BootstrapFewShot'u bu örneklere bakarak prompt'u otomatik
optimize eder — elle "lütfen doğru hesapla" yazmak yerine.
"""

import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libsql_client import create_client
import asyncio
import dspy


TRAINING_EXAMPLES_PATH = os.path.join(
    os.path.dirname(__file__), "training_data.json"
)


async def extract_training_examples(db_path: str, limit: int = 20) -> list[dict]:
    """
    DB'den hem notes_freetext hem structured fields dolu olan
    deal'leri çek. Bunlar DSPy için labeled examples.
    """
    client = create_client(url=f"file:{db_path}")

    result = await client.execute("""
        SELECT
            d.deal_notes_freetext,
            d.deal_type,
            d.guarantee_amount,
            d.percentage,
            d.expense_cap,
            d.hospitality_cap,
            ar.name as artist,
            sh.date
        FROM deals d
        JOIN shows sh ON d.show_id = sh.id
        JOIN artists ar ON sh.artist_id = ar.id
        WHERE d.deal_notes_freetext IS NOT NULL
          AND length(d.deal_notes_freetext) > 20
          AND d.deal_type IN ('vs', 'percentage_of_net', 'flat')
          AND d.guarantee_amount IS NOT NULL
          AND d.percentage IS NOT NULL
        ORDER BY sh.date DESC
        LIMIT ?
    """, [limit])

    await client.close()
    return result.rows


def rows_to_dspy_examples(rows: list) -> list[dspy.Example]:
    """
    DB satırlarını DSPy Example nesnelerine çevir.
    """
    examples = []
    for row in rows:
        notes = row[0] or ""
        deal_type = row[1] or "vs"
        guarantee = float(row[2] or 0)
        percentage = float(row[3] or 0)
        expense_cap = float(row[4] or 0)
        hospitality_cap = float(row[5] or 0)

        if not notes.strip():
            continue

        example = dspy.Example(
            notes_freetext=notes,
            # Ground truth (bu değerleri DSPy parser üretmeli)
            deal_type=deal_type,
            guarantee_amount=guarantee,
            percentage=percentage,
            expense_cap=expense_cap,
            hospitality_cap=hospitality_cap,
        ).with_inputs("notes_freetext")

        examples.append(example)

    return examples


async def build_and_save(db_path: str):
    print(f"DB'den training örnekleri çekiliyor: {db_path}")
    rows = await extract_training_examples(db_path)
    print(f"{len(rows)} örnek bulundu")

    examples = rows_to_dspy_examples(rows)
    print(f"{len(examples)} geçerli training örneği oluşturuldu")

    # JSON olarak kaydet (DSPy optimize.py için)
    serialized = [
        {
            "notes_freetext": ex.notes_freetext,
            "deal_type": ex.deal_type,
            "guarantee_amount": ex.guarantee_amount,
            "percentage": ex.percentage,
            "expense_cap": ex.expense_cap,
            "hospitality_cap": ex.hospitality_cap,
        }
        for ex in examples
    ]

    with open(TRAINING_EXAMPLES_PATH, "w") as f:
        json.dump(serialized, f, indent=2)

    print(f"Training seti kaydedildi: {TRAINING_EXAMPLES_PATH}")
    return examples


if __name__ == "__main__":
    db = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "greenroom.db"
    )
    asyncio.run(build_and_save(db))
