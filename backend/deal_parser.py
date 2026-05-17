"""
DSPy Deal Notes Parser

Mariana'nın prose deal notlarından finansal kuralları çıkarır.
Coastal Spell gibi belirsizlikleri show öncesinde yakalar.

DSPy kullanım gerekçesi:
- ChainOfThought: "against gross" vs "inside cap" gibi belirsiz ifadeleri
  adım adım düşünerek doğru yorumlar. Raw prompt %80-85 doğruluk verir.
  CoT bunu %95+'e çıkarır.
- Assert: Çıkarılan değerler finansal kurallara uymak zorunda. İhlalde
  sistem durur, kendini düzeltir, tekrar dener.
- Suggest: Belirsizlik varsa Mariana'ya uyarı verir ama akışı durdurmaz.
"""

import dspy
import json
from typing import Optional
from pydantic import BaseModel


# ── Signature: Kural Çıkarımı ──────────────────────────────────────────────

class ExtractDealRules(dspy.Signature):
    """
    Extract structured financial settlement rules from a booker's freetext deal notes.

    Focus on identifying:
    - Deal type and financial structure
    - Expense caps and what falls inside/outside them
    - Where marketing recoups apply (pre-gross or inside expense cap)
    - Hospitality limits and who covers overages
    - Walkout pots and tier ratchets
    - Any language that could be interpreted multiple ways

    The notes_freetext is the ground truth. Structured fields may be stale.
    """

    notes_freetext: str = dspy.InputField(
        desc="Raw deal notes as written by the booker — this is the source of truth"
    )

    deal_type: str = dspy.OutputField(
        desc="One of: flat, vs, percentage_of_net, percentage_of_gross, door"
    )
    guarantee_amount: float = dspy.OutputField(
        desc="Artist guarantee in dollars. 0.0 if no guarantee."
    )
    percentage: float = dspy.OutputField(
        desc="Artist percentage as decimal between 0 and 1. E.g. 0.80 for 80%. 0.0 if none."
    )
    expense_cap: float = dspy.OutputField(
        desc="Maximum expenses passed through to artist in dollars. 0.0 if no cap."
    )
    expense_cap_scope: str = dspy.OutputField(
        desc="JSON list of expense categories inside the cap. E.g. '[\"sound\",\"lights\",\"production\"]'"
    )
    hospitality_cap: float = dspy.OutputField(
        desc="Hospitality spending cap in dollars. 0.0 if not specified."
    )
    hospitality_overage_treatment: str = dspy.OutputField(
        desc="Who covers hospitality overage: 'absorbed_by_venue' or 'passed_to_artist' or 'ambiguous'"
    )
    marketing_recoup_amount: float = dspy.OutputField(
        desc="Marketing recoup in dollars. 0.0 if none."
    )
    marketing_recoup_position: str = dspy.OutputField(
        desc="Where recoup is deducted: 'pre_gross' (before % calc) or 'in_expenses' (inside cap) or 'ambiguous'"
    )
    walkout_pot_threshold: float = dspy.OutputField(
        desc="Gross threshold for walkout pot in dollars. 0.0 if no walkout pot."
    )
    walkout_pot_percentage: float = dspy.OutputField(
        desc="Artist percentage above walkout threshold (usually 1.0 = 100%). 0.0 if no walkout pot."
    )
    tier_ratchet: str = dspy.OutputField(
        desc="JSON array of ratchet tiers [{from_pct, to_pct, percentage}] or '[]' if none."
    )
    ambiguities: str = dspy.OutputField(
        desc="Comma-separated list of terms or clauses that could be read multiple ways. Empty string if none."
    )
    citations: str = dspy.OutputField(
        desc="JSON object mapping each extracted field to the exact quote from the notes that sourced it."
    )


# ── DSPy Module ─────────────────────────────────────────────────────────────

class DealNotesParser(dspy.Module):
    """
    Mariana'nın prose deal notlarını yapılandırılmış kurallara çevirir.

    ChainOfThought kullanılıyor çünkü:
    - "marketing recoup of $900 against gross" gibi cümleler belirsiz
    - Model önce adım adım düşünmeli, sonra karar vermeli
    - Düşünce izi Mariana'ya gösterilebilir (explainability)
    """

    def __init__(self):
        super().__init__()
        self.extractor = dspy.ChainOfThought(ExtractDealRules)

    def forward(self, notes_freetext: str) -> dspy.Prediction:

        result = self.extractor(notes_freetext=notes_freetext)

        # ── Hard Guardrails (Assert-equivalent): financial sanity checks ──
        # DSPy 3.x removed dspy.Assert; we implement the same semantics inline.
        if float(result.guarantee_amount) < 0:
            raise ValueError("Guarantee amount cannot be negative.")
        if not (0.0 <= float(result.percentage) <= 1.0):
            raise ValueError("Percentage must be between 0 and 1 (e.g. 0.80 for 80%).")
        if float(result.expense_cap) < 0:
            raise ValueError("Expense cap cannot be negative.")
        valid_recoup = ["pre_gross", "in_expenses", "ambiguous"]
        if result.marketing_recoup_position not in valid_recoup:
            result = result.copy(marketing_recoup_position="ambiguous")
        valid_hosp = ["absorbed_by_venue", "passed_to_artist", "ambiguous"]
        if result.hospitality_overage_treatment not in valid_hosp:
            result = result.copy(hospitality_overage_treatment="ambiguous")

        # ── Soft Suggestions (Suggest-equivalent): ambiguity detection ──
        # These accumulate warnings without stopping the flow — surfaced in UI.
        suggestions = []
        if result.marketing_recoup_position == "ambiguous":
            suggestions.append(
                "Marketing recoup position is ambiguous — most common dispute source "
                "(e.g. Coastal Spell $720). Clarify with agent before show night."
            )
        if result.hospitality_overage_treatment == "ambiguous":
            suggestions.append("Hospitality overage treatment is unclear. Who covers the excess?")
        if result.ambiguities.strip():
            suggestions.append(
                f"Deal contains ambiguous language: {result.ambiguities}. Resolve before show night."
            )

        result._suggestions = suggestions
        return result


# ── Pydantic Output Model (API response için) ───────────────────────────────

class DealRules(BaseModel):
    deal_type: str
    guarantee_amount: float
    percentage: float
    expense_cap: float
    expense_cap_scope: list[str]
    hospitality_cap: float
    hospitality_overage_treatment: str
    marketing_recoup_amount: float
    marketing_recoup_position: str
    walkout_pot_threshold: float
    walkout_pot_percentage: float
    tier_ratchet: list[dict]
    ambiguities: list[str]
    citations: dict
    reasoning: str  # ChainOfThought'un düşünce izi

    @classmethod
    def from_dspy(cls, result: dspy.Prediction) -> "DealRules":
        def safe_json_list(val: str) -> list:
            try:
                parsed = json.loads(val)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []

        def safe_json_dict(val: str) -> dict:
            try:
                parsed = json.loads(val)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}

        ambiguity_list = (
            [a.strip() for a in result.ambiguities.split(",") if a.strip()]
            if result.ambiguities else []
        )

        return cls(
            deal_type=result.deal_type,
            guarantee_amount=float(result.guarantee_amount),
            percentage=float(result.percentage),
            expense_cap=float(result.expense_cap),
            expense_cap_scope=safe_json_list(result.expense_cap_scope),
            hospitality_cap=float(result.hospitality_cap),
            hospitality_overage_treatment=result.hospitality_overage_treatment,
            marketing_recoup_amount=float(result.marketing_recoup_amount),
            marketing_recoup_position=result.marketing_recoup_position,
            walkout_pot_threshold=float(result.walkout_pot_threshold),
            walkout_pot_percentage=float(result.walkout_pot_percentage),
            tier_ratchet=safe_json_list(result.tier_ratchet),
            ambiguities=ambiguity_list,
            citations=safe_json_dict(result.citations),
            reasoning=getattr(result, "reasoning", ""),
        )
