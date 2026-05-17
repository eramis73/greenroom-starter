import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  // Forward the multipart form data directly to the Python backend
  const formData = await req.formData();

  const file = formData.get("file");
  if (!file || !(file instanceof File)) {
    return NextResponse.json({ error: "file is required" }, { status: 400 });
  }

  // Build a fresh FormData for the Python backend
  const backendForm = new FormData();
  backendForm.append("file", file, file.name);

  const dealContext = formData.get("deal_context");
  if (dealContext) backendForm.append("deal_context", dealContext as string);

  const showId = formData.get("show_id");
  if (showId) backendForm.append("show_id", showId as string);

  try {
    const response = await fetch("http://localhost:8000/parse-receipt-file", {
      method: "POST",
      body: backendForm,
      signal: AbortSignal.timeout(90_000), // vision OCR can be slow
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
