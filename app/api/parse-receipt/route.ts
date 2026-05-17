import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { receipt_text, deal_context, show_id } = body;

  if (!receipt_text?.trim()) {
    return NextResponse.json(
      { error: "receipt_text is required" },
      { status: 400 }
    );
  }

  try {
    const response = await fetch("http://localhost:8000/parse-receipt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        receipt_text,
        deal_context: deal_context ?? "",
        show_id: show_id ?? null,
      }),
      signal: AbortSignal.timeout(60_000),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json({ error: errorText }, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      {
        error:
          "DSPy backend unavailable. Start it with: cd backend && python api.py",
      },
      { status: 503 }
    );
  }
}
