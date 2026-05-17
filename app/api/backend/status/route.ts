import { NextResponse } from "next/server";

export async function GET() {
  try {
    const res = await fetch("http://localhost:8000/health", {
      signal: AbortSignal.timeout(2000),
    });
    if (res.ok) {
      const model = global.__backendModel ?? null;
      return NextResponse.json({ running: true, model });
    }
    return NextResponse.json({ running: false });
  } catch {
    return NextResponse.json({ running: false });
  }
}
