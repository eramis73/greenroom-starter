"""
FastAPI — Greenroom Settlement Agent Backend

Endpoint'ler:
  POST /parse-deal-notes  → DSPy: prose notes'tan kural çıkar
  POST /parse-receipt     → DSPy: fatura/fiş metnini expense'e çevir
  POST /calculate         → Python math: settlement hesabı
  GET  /health            → Servis durumu
"""

import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from config import configure_dspy
from deal_parser import DealNotesParser, DealRules
from receipt_parser import ReceiptParser, ParsedExpense
from file_parser import parse_receipt_file
from settlement_math import (
    calculate, TicketSale, Expense, SettlementResult
)


# ── App başlatma ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # DSPy'ı yapılandır — optimize edilmiş model varsa yükle
    configure_dspy()

    optimized_path = os.path.join(os.path.dirname(__file__), "optimized_parser.json")
    app.state.deal_parser = DealNotesParser()

    if os.path.exists(optimized_path):
        try:
            app.state.deal_parser.load(optimized_path)
            print("✓ Optimize edilmiş DSPy modeli yüklendi")
        except Exception as e:
            print(f"⚠ Optimize model yüklenemedi, ham model kullanılıyor: {e}")
    else:
        print("ℹ Optimize model bulunamadı. 'python optimize.py' ile oluşturabilirsiniz.")

    app.state.receipt_parser = ReceiptParser()
    yield


app = FastAPI(
    title="Greenroom Settlement Agent",
    description="DSPy-powered settlement assistant for Greenroom venues",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ─────────────────────────────────────────────────

class ParseDealRequest(BaseModel):
    notes_freetext: str
    show_id: Optional[str] = None

class ParseReceiptRequest(BaseModel):
    receipt_text: str
    deal_context: Optional[str] = ""
    show_id: Optional[str] = None

class TicketSaleInput(BaseModel):
    qty: int
    gross: float
    fees: float

class ExpenseInput(BaseModel):
    category: str
    amount: float
    absorbed_by_venue: bool = False
    description: str = ""

class CalculateRequest(BaseModel):
    deal_type: str
    guarantee: float = 0.0
    percentage: float = 0.0
    expense_cap: float = 0.0
    hospitality_cap: float = 0.0
    marketing_recoup_amount: float = 0.0
    marketing_recoup_position: str = "in_expenses"
    hospitality_overage_treatment: str = "absorbed_by_venue"
    walkout_pot_threshold: float = 0.0
    walkout_pot_percentage: float = 1.0
    ticket_sales: list[TicketSaleInput]
    expenses: list[ExpenseInput]
    venue_capacity: Optional[int] = None

class CalculateResponse(BaseModel):
    gross_box_office: float
    net_box_office: float
    expenses_applied: float
    expense_cap_hit: bool
    marketing_recoup: float
    marketing_recoup_position: str
    hospitality_total: float
    hospitality_absorbed: float
    net_after_deductions: float
    percentage_payout: float
    guarantee: float
    winning_leg: str
    walkout_additional: float
    final_payout: float
    steps: list[dict]
    formula_summary: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "greenroom-settlement-agent"}


@app.post("/parse-deal-notes", response_model=DealRules)
def parse_deal_notes(req: ParseDealRequest):
    """
    Mariana'nın prose deal notlarından finansal kuralları çıkarır.

    DSPy ChainOfThought + Assert + Suggest kullanır.
    Ambiguous language tespiti Coastal Spell benzeri disputeları önler.
    """
    if not req.notes_freetext.strip():
        raise HTTPException(status_code=400, detail="notes_freetext cannot be empty")

    try:
        result = app.state.deal_parser(notes_freetext=req.notes_freetext)
        return DealRules.from_dspy(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DSPy parse error: {str(e)}")


@app.post("/parse-receipt", response_model=ParsedExpense)
def parse_receipt(req: ParseReceiptRequest):
    """
    Fatura, fiş veya email metnini Greenroom expense satırına çevirir.

    DSPy ChainOfThought + Assert ile kategori ve tutar çıkarır.
    Onaylayınca Greenroom expenses tablosuna eklenebilir.
    """
    if not req.receipt_text.strip():
        raise HTTPException(status_code=400, detail="receipt_text cannot be empty")

    try:
        result = app.state.receipt_parser(
            receipt_text=req.receipt_text,
            deal_context=req.deal_context or ""
        )
        return ParsedExpense.from_dspy(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DSPy parse error: {str(e)}")


@app.post("/parse-receipt-file", response_model=ParsedExpense)
async def parse_receipt_file_endpoint(
    file: UploadFile = File(...),
    deal_context: str = Form(""),
    show_id: Optional[str] = Form(None),
):
    """
    PDF, JPG, PNG veya WEBP dosyasından gider bilgisi çıkarır.

    Pipeline:
      - Metin PDF   → pdfplumber → DSPy ReceiptParser
      - Taranmış PDF → PyMuPDF → PNG → vision OCR → DSPy ReceiptParser
      - Görsel       → vision OCR → DSPy ReceiptParser
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Dosya adı eksik.")

    max_size = 10 * 1024 * 1024  # 10 MB
    file_data = await file.read()
    if len(file_data) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"Dosya çok büyük ({len(file_data)//1024} KB). Max 10 MB."
        )

    try:
        expense = parse_receipt_file(
            file_data=file_data,
            filename=file.filename,
            media_type=file.content_type or "",
            deal_context=deal_context,
        )
        return expense
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dosya parse hatası: {str(e)}")


@app.post("/calculate", response_model=CalculateResponse)
def calculate_settlement(req: CalculateRequest):
    """
    Deterministik Python math engine. LLM yok.
    DSPy'dan gelen kuralları + DB'den gelen giderleri alır, hesabı yapar.
    """
    ticket_sales = [
        TicketSale(qty=t.qty, gross=t.gross, fees=t.fees)
        for t in req.ticket_sales
    ]
    expenses = [
        Expense(
            category=e.category,
            amount=e.amount,
            absorbed_by_venue=e.absorbed_by_venue,
            description=e.description
        )
        for e in req.expenses
    ]

    result = calculate(
        deal_type=req.deal_type,
        guarantee=req.guarantee,
        percentage=req.percentage,
        expense_cap=req.expense_cap,
        hospitality_cap=req.hospitality_cap,
        marketing_recoup_amount=req.marketing_recoup_amount,
        marketing_recoup_position=req.marketing_recoup_position,
        hospitality_overage_treatment=req.hospitality_overage_treatment,
        walkout_threshold=req.walkout_pot_threshold,
        walkout_percentage=req.walkout_pot_percentage,
        ticket_sales=ticket_sales,
        expenses=expenses,
        venue_capacity=req.venue_capacity,
    )

    return CalculateResponse(
        gross_box_office=result.gross_box_office,
        net_box_office=result.net_box_office,
        expenses_applied=result.expenses_applied,
        expense_cap_hit=result.expense_cap_hit,
        marketing_recoup=result.marketing_recoup,
        marketing_recoup_position=result.marketing_recoup_position,
        hospitality_total=result.hospitality_total,
        hospitality_absorbed=result.hospitality_absorbed,
        net_after_deductions=result.net_after_deductions,
        percentage_payout=result.percentage_payout,
        guarantee=result.guarantee,
        winning_leg=result.winning_leg,
        walkout_additional=result.walkout_additional,
        final_payout=result.final_payout,
        steps=[
            {"label": s.label, "value": s.value, "note": s.note,
             "is_subtraction": s.is_subtraction}
            for s in result.steps
        ],
        formula_summary=result.formula_summary,
    )


if __name__ == "__main__":
    import uvicorn
    import sys
    sys.exit(uvicorn.run("api:app", host="0.0.0.0", port=8000))
