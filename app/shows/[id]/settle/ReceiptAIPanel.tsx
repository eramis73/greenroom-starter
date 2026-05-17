"use client";

import { useState } from "react";
import { Receipt, CheckCircle, AlertTriangle, Loader2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

interface ParsedExpense {
  amount: number;
  category: string;
  description: string;
  vendor: string;
  absorbed_by_venue: boolean;
  confidence: string;
  notes: string;
  reasoning: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  production: "Production",
  sound: "Sound",
  lights: "Lights",
  hospitality: "Hospitality",
  marketing: "Marketing",
  backline: "Backline",
  security: "Security",
  other: "Other",
};

function fmt(n: number) {
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function ReceiptAIPanel({ dealContext }: { dealContext: string }) {
  const [receiptText, setReceiptText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ParsedExpense | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function parse() {
    if (!receiptText.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setConfirmed(false);
    try {
      const res = await fetch("/api/parse-receipt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          receipt_text: receiptText,
          deal_context: dealContext,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Parse failed");
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setResult(null);
    setConfirmed(false);
    setError(null);
    setReceiptText("");
  }

  const confidenceColor =
    result?.confidence === "high"
      ? "text-emerald-700 bg-emerald-50 ring-emerald-200/60"
      : result?.confidence === "medium"
        ? "text-amber-700 bg-amber-50 ring-amber-200/60"
        : "text-rose-700 bg-rose-50 ring-rose-200/60";

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle className="flex items-center gap-2">
            <Receipt className="h-4 w-4 text-brand-700" />
            Add expense from receipt
          </CardTitle>
          <CardDescription>
            Paste a receipt, invoice, or email — DSPy extracts the amount,
            category, and whether it&apos;s passed through to the artist.
          </CardDescription>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {!confirmed ? (
          <>
            <div>
              <label className="eyebrow text-[10px] text-ink-500 mb-1.5 block">
                Receipt / invoice / email text
              </label>
              <textarea
                value={receiptText}
                onChange={(e) => setReceiptText(e.target.value)}
                placeholder={`Paste anything here — e.g.\n\nSound Tech Invoice\nDate: May 3\nPA system rental + 2 techs: $1,400\nLoad-in: 2pm, Doors: 8pm\n\nThank you,\nCrest Audio Services`}
                className="w-full h-36 rounded-lg border-0 ring-1 ring-ink-200/80 bg-canvas-soft text-[12.5px] text-ink-800 placeholder:text-ink-400 p-3.5 resize-none focus:outline-none focus:ring-2 focus:ring-brand-700/50 leading-relaxed"
                disabled={loading}
              />
            </div>

            {dealContext && (
              <div className="text-[11.5px] text-ink-400">
                <span className="font-medium text-ink-600">Deal context passed to DSPy:</span>{" "}
                {dealContext}
              </div>
            )}

            <Button
              variant="brand"
              size="sm"
              onClick={parse}
              disabled={loading || !receiptText.trim()}
            >
              {loading ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Parsing receipt…
                </>
              ) : (
                <>
                  <Receipt className="h-3.5 w-3.5" />
                  Parse with DSPy
                </>
              )}
            </Button>

            {error && (
              <div className="rounded-lg bg-rose-50 border border-rose-200/60 p-4 text-[12.5px] text-rose-800 flex gap-2">
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                <div>{error}</div>
              </div>
            )}

            {result && (
              <div className="rounded-xl ring-1 ring-ink-200/80 bg-white overflow-hidden">
                {/* Header bar */}
                <div className="flex items-center justify-between px-4 py-3 bg-canvas-soft border-b border-ink-100/80">
                  <div className="text-[12px] font-semibold text-ink-900">
                    Parsed expense
                  </div>
                  <span className={`text-[10.5px] font-medium px-2 py-0.5 rounded-full ring-1 ring-inset ${confidenceColor}`}>
                    {result.confidence} confidence
                  </span>
                </div>

                <div className="px-4 py-4 space-y-3">
                  {/* Amount — hero */}
                  <div className="flex items-baseline justify-between">
                    <span className="text-[12px] text-ink-500">Amount</span>
                    <span className="text-[22px] font-mono font-bold text-ink-900" style={{ letterSpacing: "-0.02em" }}>
                      {fmt(result.amount)}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-[12.5px]">
                    <div>
                      <div className="text-[10px] text-ink-400 mb-0.5">Category</div>
                      <div className="font-medium text-ink-900">
                        {CATEGORY_LABELS[result.category] ?? result.category}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-ink-400 mb-0.5">Vendor</div>
                      <div className="font-medium text-ink-900">{result.vendor}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-ink-400 mb-0.5">Description</div>
                      <div className="text-ink-700">{result.description}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-ink-400 mb-0.5">Artist impact</div>
                      <div className={result.absorbed_by_venue ? "text-ink-500" : "font-medium text-ink-900"}>
                        {result.absorbed_by_venue ? "Absorbed by venue" : "Passed to artist"}
                      </div>
                    </div>
                  </div>

                  {result.notes && (
                    <div className="rounded-md bg-amber-50 border border-amber-200/60 px-3 py-2 text-[12px] text-amber-800">
                      {result.notes}
                    </div>
                  )}

                  {result.confidence === "low" && (
                    <div className="rounded-md bg-rose-50 border border-rose-200/60 px-3 py-2 text-[12px] text-rose-700 flex gap-2">
                      <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                      Low confidence — verify amount manually before adding.
                    </div>
                  )}

                  {/* Action buttons */}
                  <div className="flex gap-2 pt-1">
                    <Button
                      variant="brand"
                      size="sm"
                      onClick={() => setConfirmed(true)}
                    >
                      <CheckCircle className="h-3.5 w-3.5" />
                      Confirm &amp; add to expenses
                    </Button>
                    <Button variant="ghost" size="sm" onClick={reset}>
                      <RotateCcw className="h-3.5 w-3.5" />
                      Try another
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </>
        ) : (
          /* Confirmed state */
          <div className="text-center py-8">
            <CheckCircle className="h-10 w-10 text-emerald-600 mx-auto mb-3" />
            <div className="text-[14px] font-semibold text-ink-900 mb-1">
              Expense recorded
            </div>
            <div className="text-[12.5px] text-ink-500 mb-5">
              {result && (
                <>
                  {fmt(result.amount)} · {CATEGORY_LABELS[result.category] ?? result.category} ·{" "}
                  {result.absorbed_by_venue ? "Absorbed by venue" : "Passed to artist"}
                </>
              )}
            </div>
            <Button variant="secondary" size="sm" onClick={reset}>
              <Receipt className="h-3.5 w-3.5" />
              Add another receipt
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
