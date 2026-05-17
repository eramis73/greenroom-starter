"""
Vs Deal Settlement Calculator — Deterministik Python Math Engine

LLM YOK. Saf Python aritmetiği.

Neden LLM yok:
- Finansal hesaplamada %99.9 doğruluk şart
- $19,840 × 0.80 - $2,500 hesabını LLM'e yaptırırsan hata riski var
- Bu fonksiyonlar unit test edilebilir, auditable, izlenebilir
- DSPy modülleri kuralları çıkarır, bu fonksiyonlar uygular

Desteklenen deal tipleri:
  - flat
  - percentage_of_gross
  - percentage_of_net
  - vs  (guarantee vs % of net, hangisi büyükse)
  - door
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TicketSale:
    qty: int
    gross: float
    fees: float


@dataclass
class Expense:
    category: str
    amount: float
    absorbed_by_venue: bool
    description: str = ""


@dataclass
class CalculationStep:
    label: str
    value: float
    note: str = ""
    is_subtraction: bool = False


@dataclass
class SettlementResult:
    # Temel rakamlar
    gross_box_office: float
    total_fees: float
    net_box_office: float

    # Giderler
    total_expenses_raw: float          # Tüm giderler (venue absorbed dahil)
    total_expenses_passthrough: float  # Sadece artist'e geçenler
    expenses_applied: float            # Cap sonrası uygulanan
    expense_cap: float
    expense_cap_hit: bool

    # Marketing recoup
    marketing_recoup: float
    marketing_recoup_position: str     # pre_gross / in_expenses

    # Hospitality
    hospitality_total: float
    hospitality_cap: float
    hospitality_overage: float
    hospitality_absorbed: float

    # Hesaplama
    net_after_deductions: float
    percentage_payout: float
    guarantee: float
    winning_leg: str                   # "guarantee" veya "percentage"
    final_payout: float

    # Walkout pot
    walkout_threshold: float
    walkout_additional: float

    # Adımlar (UI'da gösterilecek)
    steps: list[CalculationStep]

    # Formül özeti
    formula_summary: str


def calculate(
    deal_type: str,
    guarantee: float,
    percentage: float,
    expense_cap: float,
    hospitality_cap: float,
    marketing_recoup_amount: float,
    marketing_recoup_position: str,   # "pre_gross" | "in_expenses" | "ambiguous"
    hospitality_overage_treatment: str, # "absorbed_by_venue" | "passed_to_artist"
    walkout_threshold: float,
    walkout_percentage: float,
    ticket_sales: list[TicketSale],
    expenses: list[Expense],
    venue_capacity: Optional[int] = None,
) -> SettlementResult:
    """
    Ana settlement hesaplama fonksiyonu.
    DSPy'dan gelen kuralları + DB'den gelen giderleri alır, matematik yapar.
    """

    steps: list[CalculationStep] = []

    # ── 1. Bilet Gelirleri ─────────────────────────────────────────────────
    gross = sum(t.gross for t in ticket_sales)
    fees = sum(t.fees for t in ticket_sales)
    net = gross - fees

    steps.append(CalculationStep("Gross box office", gross))
    steps.append(CalculationStep("Ticket platform fees", -fees, is_subtraction=True,
                                  note=f"{(fees/gross*100):.1f}% of gross" if gross > 0 else ""))
    steps.append(CalculationStep("Net box office", net))

    # ── 2. Marketing Recoup (pre_gross konumu) ────────────────────────────
    pre_gross_deductions = 0.0
    if marketing_recoup_amount > 0 and marketing_recoup_position == "pre_gross":
        pre_gross_deductions = marketing_recoup_amount
        steps.append(CalculationStep(
            "Marketing recoup (pre-gross)",
            -marketing_recoup_amount,
            is_subtraction=True,
            note="Deducted from net before percentage calculation"
        ))

    net_after_recoup = net - pre_gross_deductions

    # ── 3. Giderleri Sınıflandır ───────────────────────────────────────────
    hospitality_expenses = [e for e in expenses if e.category == "hospitality"]
    marketing_expenses = [e for e in expenses if e.category == "marketing"]
    other_expenses = [e for e in expenses
                      if not e.absorbed_by_venue
                      and e.category not in ("hospitality", "marketing")]

    # Hospitality cap hesabı
    hospitality_total = sum(e.amount for e in hospitality_expenses)
    hosp_cap = hospitality_cap if hospitality_cap > 0 else float("inf")
    hospitality_passthrough = min(hospitality_total, hosp_cap)
    hospitality_overage = max(0.0, hospitality_total - hosp_cap)
    hospitality_absorbed = (
        hospitality_overage
        if hospitality_overage_treatment == "absorbed_by_venue"
        else 0.0
    )

    # Diğer giderler (absorbed olmayanlar)
    other_total = sum(e.amount for e in other_expenses)

    # Marketing giderleri (eğer in_expenses konumundaysa cap'e dahil)
    marketing_in_expenses = 0.0
    if marketing_recoup_amount > 0 and marketing_recoup_position == "in_expenses":
        marketing_in_expenses = marketing_recoup_amount

    # Cap uygulanacak toplam
    cappable = other_total + hospitality_passthrough + marketing_in_expenses
    applied_cap = expense_cap if expense_cap > 0 else float("inf")
    expenses_applied = min(cappable, applied_cap)
    cap_hit = expense_cap > 0 and cappable > expense_cap

    if hospitality_total > 0:
        if hospitality_overage > 0 and hospitality_overage_treatment == "absorbed_by_venue":
            steps.append(CalculationStep(
                f"Hospitality (cap ${hospitality_cap:,.0f}, venue absorbs ${hospitality_absorbed:,.2f} overage)",
                -hospitality_passthrough,
                is_subtraction=True,
                note=f"Total ${hospitality_total:,.2f} → ${hospitality_passthrough:,.2f} passed through"
            ))
        else:
            steps.append(CalculationStep(
                "Hospitality expenses",
                -hospitality_passthrough,
                is_subtraction=True
            ))

    if other_total > 0:
        steps.append(CalculationStep(
            "Production / Sound / Lights / Other",
            -other_total,
            is_subtraction=True
        ))

    if marketing_in_expenses > 0:
        steps.append(CalculationStep(
            "Marketing recoup (inside expense cap)",
            -marketing_in_expenses,
            is_subtraction=True,
            note="Counted toward expense cap"
        ))

    if cap_hit:
        steps.append(CalculationStep(
            f"Expense cap applied (${expense_cap:,.0f} limit)",
            -expenses_applied,
            is_subtraction=True,
            note=f"Raw total ${cappable:,.2f} → capped at ${expense_cap:,.0f}"
        ))

    net_after_expenses = net_after_recoup - expenses_applied
    steps.append(CalculationStep("Net after all deductions", net_after_expenses))

    # ── 4. Deal Tipi Hesabı ───────────────────────────────────────────────
    pct_payout = 0.0
    winning_leg = "guarantee"
    final_payout = guarantee

    if deal_type == "flat":
        final_payout = guarantee
        winning_leg = "flat"
        steps.append(CalculationStep("Flat guarantee", guarantee,
                                      note="No percentage calculation for flat deals"))

    elif deal_type == "percentage_of_gross":
        pct_payout = gross * percentage
        final_payout = pct_payout
        winning_leg = "percentage"
        steps.append(CalculationStep(
            f"× {percentage*100:.0f}% of gross",
            pct_payout,
            note="Percentage of gross — no expense deductions"
        ))

    elif deal_type == "percentage_of_net":
        pct_payout = net_after_expenses * percentage
        final_payout = pct_payout
        winning_leg = "percentage"
        steps.append(CalculationStep(
            f"× {percentage*100:.0f}% of net after deductions",
            pct_payout
        ))

    elif deal_type == "vs":
        pct_payout = net_after_expenses * percentage
        steps.append(CalculationStep(
            f"× {percentage*100:.0f}% of net",
            pct_payout
        ))
        steps.append(CalculationStep("Guarantee", guarantee))

        if guarantee >= pct_payout:
            final_payout = guarantee
            winning_leg = "guarantee"
            steps.append(CalculationStep(
                "→ Guarantee wins",
                guarantee,
                note=f"Guarantee ${guarantee:,.2f} > Percentage ${pct_payout:,.2f}"
            ))
        else:
            final_payout = pct_payout
            winning_leg = "percentage"
            steps.append(CalculationStep(
                "→ Percentage wins",
                pct_payout,
                note=f"Percentage ${pct_payout:,.2f} > Guarantee ${guarantee:,.2f}"
            ))

    elif deal_type == "door":
        # Door: artist gets all or agreed % of gross at door
        door_pct = percentage if percentage > 0 else 1.0
        final_payout = gross * door_pct
        winning_leg = "door"
        steps.append(CalculationStep(
            f"Door deal — {door_pct*100:.0f}% of gross",
            final_payout
        ))

    # ── 5. Walkout Pot ────────────────────────────────────────────────────
    walkout_additional = 0.0
    if walkout_threshold > 0 and gross > walkout_threshold:
        walkout_additional = (gross - walkout_threshold) * walkout_percentage
        steps.append(CalculationStep(
            f"Walkout pot (gross > ${walkout_threshold:,.0f})",
            walkout_additional,
            note=f"(${gross:,.2f} - ${walkout_threshold:,.2f}) × {walkout_percentage*100:.0f}%"
        ))
        final_payout += walkout_additional

    # ── Formula Summary ───────────────────────────────────────────────────
    formula_summary = _build_formula(
        deal_type, guarantee, percentage, expense_cap,
        marketing_recoup_position, winning_leg, final_payout
    )

    return SettlementResult(
        gross_box_office=gross,
        total_fees=fees,
        net_box_office=net,
        total_expenses_raw=sum(e.amount for e in expenses),
        total_expenses_passthrough=expenses_applied,
        expenses_applied=expenses_applied,
        expense_cap=expense_cap,
        expense_cap_hit=cap_hit,
        marketing_recoup=marketing_recoup_amount,
        marketing_recoup_position=marketing_recoup_position,
        hospitality_total=hospitality_total,
        hospitality_cap=hospitality_cap,
        hospitality_overage=hospitality_overage,
        hospitality_absorbed=hospitality_absorbed,
        net_after_deductions=net_after_expenses,
        percentage_payout=pct_payout,
        guarantee=guarantee,
        winning_leg=winning_leg,
        final_payout=round(final_payout, 2),
        walkout_threshold=walkout_threshold,
        walkout_additional=walkout_additional,
        steps=steps,
        formula_summary=formula_summary,
    )


def _build_formula(deal_type, guarantee, percentage, expense_cap,
                   recoup_pos, winning_leg, final_payout) -> str:
    if deal_type == "flat":
        return f"Flat guarantee = ${guarantee:,.2f}"
    elif deal_type == "percentage_of_gross":
        return f"Gross × {percentage*100:.0f}% = ${final_payout:,.2f}"
    elif deal_type == "percentage_of_net":
        cap_str = f", exp cap ${expense_cap:,.0f}" if expense_cap > 0 else ""
        return f"Net after expenses{cap_str} × {percentage*100:.0f}% = ${final_payout:,.2f}"
    elif deal_type == "vs":
        cap_str = f", cap ${expense_cap:,.0f}" if expense_cap > 0 else ""
        return (
            f"max(${guarantee:,.0f} guarantee, "
            f"{percentage*100:.0f}% of net{cap_str}) "
            f"→ {winning_leg} wins = ${final_payout:,.2f}"
        )
    elif deal_type == "door":
        return f"Door: {percentage*100:.0f}% of gross = ${final_payout:,.2f}"
    return f"${final_payout:,.2f}"
