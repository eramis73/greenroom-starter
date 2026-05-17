import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { notes_freetext, show_id } = body;

  if (!notes_freetext?.trim()) {
    return NextResponse.json(
      { error: "notes_freetext is required" },
      { status: 400 }
    );
  }

  try {
    const response = await fetch("http://localhost:8000/parse-deal-notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes_freetext, show_id: show_id ?? null }),
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
