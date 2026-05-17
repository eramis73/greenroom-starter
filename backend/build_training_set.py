"""
BootstrapFewShot için Gold Standard training seti oluşturur.

Sadece şu kriterleri karşılayan deal'leri alır:
  1. deal_notes_freetext dolu ve 20+ karakter
  2. Structured fields (guarantee, percentage) dolu
  3. Settlement status = 'finalized' veya 'paid'
     → her iki tarafın onayladığı, para transferi gerçekleşmiş deal'ler
  4. disputed_at IS NULL
     → dispute yaşanmış kayıtlar gürültü getirir; structured field'lar
        dispute sürecinde değişmiş olabilir, freetext ile çelişir

Neden bu filtre kritik:
  - Dispute'lu deal'lerde freetext ile structured field arasındaki uyumsuzluk
    kasıtlıdır (zaten ihtilaf konusu bu). Bu kayıtları LLM'e öğretmek
    modeli yanlış yönde optimize eder.
  - 'finalized'/'paid' = ground truth doğrulanmış demek. İki taraf da
    rakamları kabul etmiş, structured field güvenilir.

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
    Gold Standard filtresi:
      - deal_notes_freetext dolu (> 20 karakter)
      - guarantee_amount ve percentage structured olarak girilmiş
      - Settlement finalized veya paid (iki taraf onaylamış)
      - disputed_at IS NULL (hiç dispute yaşanmamış)

    Bu filtre BootstrapFewShot için en güvenilir labeled set'i üretir.
    Dispute'lu örnekleri dışarıda bırakmak modelin doğruluğunu artırır
    çünkü dispute = structured field ile freetext'in birbiriyle çeliştiği
    kayıt demektir.
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
            ar.name  AS artist,
            sh.date,
            s.status AS settlement_status
        FROM deals d
        JOIN shows      sh ON d.show_id = sh.id
        JOIN artists    ar ON sh.artist_id = ar.id
        JOIN settlements s ON s.show_id = sh.id
        WHERE d.deal_notes_freetext IS NOT NULL
          AND length(d.deal_notes_freetext) > 20
          AND d.deal_type IN ('vs', 'percentage_of_net', 'flat')
          AND d.guarantee_amount IS NOT NULL
          AND d.percentage IS NOT NULL
          AND s.status IN ('finalized', 'paid')
          AND s.disputed_at IS NULL
        ORDER BY sh.date DESC
        LIMIT ?
    """, [limit])

    await client.close()
    return result.rows


def rows_to_dspy_examples(rows: list) -> list[dspy.Example]:
    """
    DB satırlarını DSPy Example nesnelerine çevir.
    Sütun sırası: notes, deal_type, guarantee, percentage,
                  expense_cap, hospitality_cap, artist, date, settlement_status
    """
    examples = []
    for row in rows:
        notes            = row[0] or ""
        deal_type        = row[1] or "vs"
        guarantee        = float(row[2] or 0)
        percentage       = float(row[3] or 0)
        expense_cap      = float(row[4] or 0)
        hospitality_cap  = float(row[5] or 0)
        artist           = row[6] or "Unknown"
        date             = row[7] or ""
        settlement_status = row[8] or ""

        if not notes.strip():
            continue

        print(f"  ✓ [{settlement_status:10s}] {artist[:30]:<30s} {date}  "
              f"{deal_type}, ${guarantee:,.0f}, {percentage*100:.0f}%")

        example = dspy.Example(
            notes_freetext=notes,
            deal_type=deal_type,
            guarantee_amount=guarantee,
            percentage=percentage,
            expense_cap=expense_cap,
            hospitality_cap=hospitality_cap,
        ).with_inputs("notes_freetext")

        examples.append(example)

    return examples


async def build_and_save(db_path: str):
    print(f"DB'den Gold Standard training örnekleri çekiliyor: {db_path}")
    print("Filtre: finalized/paid settlement + disputed_at IS NULL\n")
    rows = await extract_training_examples(db_path)
    print(f"\n{len(rows)} Gold Standard örnek bulundu")

    examples = rows_to_dspy_examples(rows)
    print(f"{len(examples)} geçerli DSPy Example oluşturuldu")

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
