"""
File-based receipt parser — PDF ve görsel dosyaları işler.

Üç senaryo:
  1. Metin tabanlı PDF  → pdfplumber ile text çıkar → ReceiptParser'a gönder
  2. Taranmış PDF       → PyMuPDF ile ilk sayfayı görsel yap → vision OCR
  3. Görsel (jpg/png)   → doğrudan vision OCR

Vision OCR için DSPy ChainOfThought kullanır — ayarlı olan model ne ise
(Claude veya GPT-4o) onun vision yeteneğini otomatik devreye sokar.
"""

import base64
import io
import os
from typing import Optional

import dspy

from receipt_parser import ReceiptParser, ParsedExpense


# ── Vision OCR Signature ──────────────────────────────────────────────────────

class ExtractTextFromReceiptImage(dspy.Signature):
    """
    Extract all visible text from a receipt, invoice, or financial document image.
    Return the complete text verbatim — numbers, vendor name, dates, line items,
    totals. Preserve line breaks and structure. Do not interpret or summarize.
    """

    image: dspy.Image = dspy.InputField(
        desc="Receipt, invoice, or scanned document image"
    )
    extracted_text: str = dspy.OutputField(
        desc="Complete verbatim text from the image with line breaks preserved"
    )


class VisionOCR(dspy.Module):
    """DSPy modülü: görsel → ham metin."""

    def __init__(self):
        super().__init__()
        self.extractor = dspy.Predict(ExtractTextFromReceiptImage)

    def forward(self, image_data: bytes, media_type: str) -> str:
        b64 = base64.b64encode(image_data).decode()
        image = dspy.Image(url=f"data:{media_type};base64,{b64}")
        result = self.extractor(image=image)
        return result.extracted_text


# ── PDF helpers ───────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_data: bytes) -> Optional[str]:
    """
    pdfplumber ile metin tabanlı PDF'ten text çıkar.
    Metin bulunamazsa (taranmış PDF) None döner.
    """
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            combined = "\n".join(pages_text).strip()
            return combined if combined else None
    except Exception as e:
        print(f"pdfplumber hatası: {e}")
        return None


def pdf_first_page_to_image(pdf_data: bytes) -> Optional[tuple[bytes, str]]:
    """
    PyMuPDF ile taranmış PDF'in ilk sayfasını PNG görsel'e çevirir.
    Vision OCR için 2x zoom ile yüksek kaliteli render.
    Döndürür: (png_bytes, "image/png") ya da hata durumunda None.
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_data, filetype="pdf")
        page = doc[0]
        # 2x zoom → vision model için daha net metin
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        doc.close()
        return png_bytes, "image/png"
    except Exception as e:
        print(f"PyMuPDF hatası: {e}")
        return None


# ── Ana parse fonksiyonu ──────────────────────────────────────────────────────

def parse_receipt_file(
    file_data: bytes,
    filename: str,
    media_type: str,
    deal_context: str = "",
) -> ParsedExpense:
    """
    Dosya tipine göre doğru pipeline'ı seçer:
      PDF (metin) → pdfplumber → text → ReceiptParser
      PDF (taranmış) → PyMuPDF → PNG → VisionOCR → text → ReceiptParser
      Görsel → VisionOCR → text → ReceiptParser
    """
    ocr = VisionOCR()
    parser = ReceiptParser()
    lower = filename.lower()

    # ── PDF ──────────────────────────────────────────────────────────────────
    if lower.endswith(".pdf") or media_type == "application/pdf":
        # Önce metin tabanlı PDF dene
        text = extract_text_from_pdf(file_data)

        if text:
            print(f"PDF metin çıkarıldı ({len(text)} karakter)")
            source = "PDF (text layer)"
        else:
            # Taranmış PDF — görsel OCR gerekiyor
            print("Metin bulunamadı, görsel OCR'a geçiliyor…")
            page_img = pdf_first_page_to_image(file_data)
            if page_img is None:
                raise ValueError(
                    "PDF'ten ne metin ne de görsel alınamadı. "
                    "Dosya bozuk olabilir."
                )
            img_bytes, img_mime = page_img
            text = ocr(image_data=img_bytes, media_type=img_mime)
            source = "PDF (scanned → vision OCR)"

    # ── Görsel (jpg / png / webp / gif) ──────────────────────────────────────
    elif any(lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
        # media_type'ı normalize et
        if lower.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif lower.endswith(".png"):
            mime = "image/png"
        elif lower.endswith(".webp"):
            mime = "image/webp"
        else:
            mime = media_type or "image/jpeg"

        print(f"Görsel vision OCR ({mime})…")
        text = ocr(image_data=file_data, media_type=mime)
        source = "Image (vision OCR)"

    else:
        raise ValueError(
            f"Desteklenmeyen dosya tipi: {filename}. "
            "PDF, JPG, PNG veya WEBP yükleyiniz."
        )

    print(f"OCR tamamlandı [{source}] — {len(text)} karakter")
    print(f"Metin önizleme: {text[:200]!r}…")

    # OCR metnini mevcut DSPy ReceiptParser'a gönder
    result = parser(receipt_text=text, deal_context=deal_context)

    expense = ParsedExpense.from_dspy(result)
    # Dosyadan geldiğini not et
    if expense.notes:
        expense.notes = f"[{source}] {expense.notes}"
    else:
        expense.notes = f"Parsed from {source}"

    return expense
