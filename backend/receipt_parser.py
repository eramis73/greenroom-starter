"""
DSPy Receipt / Invoice Parser

Mariana'nın masasındaki fiziksel fişleri, PDF faturaları ve email içeriklerini
okuyup Greenroom'un expenses tablosuna girecek yapılandırılmış veriye çevirir.

Bu modül neden şart:
- Mariana her Çarşamba saatlerce gider topluyor
- Hospitality fişi masada, sound faturası PDF'te, güvenlik emailde
- Bunları elle Google Sheets'e yazıyor
- Bu modül o adımı ortadan kaldırıyor
"""

import dspy
import json
from typing import Optional
from pydantic import BaseModel


VALID_CATEGORIES = [
    "production", "sound", "lights", "hospitality",
    "marketing", "backline", "security", "other"
]


# ── Signature ────────────────────────────────────────────────────────────────

class ExtractExpenseData(dspy.Signature):
    """
    Extract structured expense information from a receipt, invoice, or email.

    The input can be:
    - A scanned/pasted receipt text
    - A vendor invoice
    - An email with expense details
    - A production manager's message with costs

    Output must map to Greenroom's expense categories:
    production, sound, lights, hospitality, marketing, backline, security, other

    Also determine whether this expense is passed through to the artist
    (deducted from their payout) or absorbed by the venue.
    """

    receipt_text: str = dspy.InputField(
        desc="Raw text from a receipt, invoice, or expense-related email"
    )
    deal_context: str = dspy.InputField(
        desc="Brief deal context to help classify the expense correctly. E.g. 'vs deal, expense cap $2500, hospitality cap $400'"
    )

    amount: float = dspy.OutputField(
        desc="Total expense amount in dollars as a number. E.g. 800.0"
    )
    category: str = dspy.OutputField(
        desc="One of: production, sound, lights, hospitality, marketing, backline, security, other"
    )
    description: str = dspy.OutputField(
        desc="Clear, concise description of what this expense is for. Max 100 chars."
    )
    vendor: str = dspy.OutputField(
        desc="Vendor or supplier name. 'Unknown' if not mentioned."
    )
    absorbed_by_venue: bool = dspy.OutputField(
        desc="True if venue absorbs this cost (not deducted from artist). False if passed through to artist."
    )
    confidence: str = dspy.OutputField(
        desc="'high' if amount is clearly stated, 'medium' if inferred, 'low' if uncertain"
    )
    notes: str = dspy.OutputField(
        desc="Any relevant notes about this expense (e.g. 'over hospitality cap by $87'). Empty string if none."
    )


# ── DSPy Module ──────────────────────────────────────────────────────────────

class ReceiptParser(dspy.Module):
    """
    Fatura/fiş/email metnini Greenroom expense satırına çevirir.

    ChainOfThought: Kategori sınıflandırması ve absorbed_by_venue kararı
    bağlama göre değişiyor (deal context'e bakıyor). Adım adım düşünmek
    doğru kategoriyi seçmek için kritik.
    """

    def __init__(self):
        super().__init__()
        self.extractor = dspy.ChainOfThought(ExtractExpenseData)

    def forward(self, receipt_text: str, deal_context: str = "") -> dspy.Prediction:

        result = self.extractor(
            receipt_text=receipt_text,
            deal_context=deal_context
        )

        # ── Hard guardrails (DSPy 3.x: inline validation) ──
        amount = float(result.amount)
        if amount <= 0:
            raise ValueError("Expense amount must be positive.")
        if amount >= 50_000:
            raise ValueError(f"Amount ${amount:,.0f} is likely a parsing error. Check the receipt.")
        if result.category not in VALID_CATEGORIES:
            result.category = "other"
        if result.confidence not in ["high", "medium", "low"]:
            result.confidence = "low"

        return result


# ── Pydantic Output Model ────────────────────────────────────────────────────

class ParsedExpense(BaseModel):
    amount: float
    category: str
    description: str
    vendor: str
    absorbed_by_venue: bool
    confidence: str
    notes: str
    reasoning: str

    @classmethod
    def from_dspy(cls, result: dspy.Prediction) -> "ParsedExpense":
        absorbed = result.absorbed_by_venue
        if isinstance(absorbed, str):
            absorbed = absorbed.lower() in ("true", "yes", "1")

        return cls(
            amount=float(result.amount),
            category=result.category,
            description=result.description,
            vendor=result.vendor,
            absorbed_by_venue=bool(absorbed),
            confidence=result.confidence,
            notes=result.notes or "",
            reasoning=getattr(result, "reasoning", ""),
        )
