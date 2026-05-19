"use client";

import { useState } from "react";
import { Sparkles, AlertTriangle, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

interface DealRules {
  deal_type: string;
  guarantee_amount: number;
  percentage: number;
  expense_cap: number;
  expense_cap_scope: string[];
  hospitality_cap: number;
  hospitality_overage_treatment: string;
  marketing_recoup_amount: number;
  marketing_recoup_position: string;
  walkout_pot_threshold: number;
  walkout_pot_percentage: number;
  tier_ratchet: object[];
  ambiguities: string[];
  citations: Record<string, string>;
  reasoning: string;
}

function fmt(n: number) {
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export function DealNotesAIPanel({
  dealNotesFreetext,
  showId,
}: {
  dealNotesFreetext: string;
  showId: string;
}) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DealRules | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showReasoning, setShowReasoning] = useState(false);
  const [showCitations, setShowCitations] = useState(false);

  async function parse() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/parse-deal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes_freetext: dealNotesFreetext, show_id: showId }),
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

  const realAmbiguities = result
    ? result.ambiguities.filter((a) => a.trim().toLowerCase() !== "none" && a.trim() !== "")
    : [];
  const hasAmbiguities = realAmbiguities.length > 0;
  const citationEntries = result ? Object.entries(result.citations) : [];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand-700" />
            Parse deal notes with DSPy AI
          </CardTitle>
          <CardDescription>
            Extracts financial rules from Mariana&apos;s freetext notes using
            ChainOfThought reasoning. Catches ambiguities before show night.
          </CardDescription>
        </div>
        <Button
          variant="brand"
          size="sm"
          onClick={parse}
          disabled={loading || !dealNotesFreetext}
        >
          {loading ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Parsing…
            </>
          ) : (
            <>
              <Sparkles className="h-3.5 w-3.5" />
              Parse with AI
            </>
          )}
        </Button>
      </CardHeader>

      <CardContent>
        {/* Notes preview */}
        <div className="mb-4">
          <div className="eyebrow text-[10px] text-ink-500 mb-1.5">
            Deal notes (source of truth)
          </div>
          <div className="text-[12.5px] text-ink-700 bg-canvas-soft rounded-lg p-4 ring-1 ring-ink-200/60 leading-relaxed max-h-32 overflow-y-auto">
            {dealNotesFreetext || <span className="text-ink-400 italic">No deal notes on file</span>}
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-rose-50 border border-rose-200/60 p-4 text-[12.5px] text-rose-800 flex gap-2">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <div>{error}</div>
          </div>
        )}

        {result && (
          <div className="space-y-4">
            {/* Ambiguity alert */}
            {hasAmbiguities && (
              <div className="rounded-lg bg-amber-50 border border-amber-200/60 p-4 flex gap-3">
                <AlertTriangle className="h-4 w-4 text-amber-700 mt-0.5 shrink-0" />
                <div>
                  <div className="text-[12.5px] font-semibold text-amber-800 mb-1">
                    {result.ambiguities.length} ambiguit{result.ambiguities.length === 1 ? "y" : "ies"} detected — resolve before show night
                  </div>
                  <ul className="space-y-0.5">
                    {realAmbiguities.map((a, i) => (
                      <li key={i} className="text-[12px] text-amber-700">
                        · {a}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {/* Marketing recoup position warning — only when a recoup actually exists */}
            {result.marketing_recoup_position === "ambiguous" && result.marketing_recoup_amount > 0 && (
              <div className="rounded-lg bg-rose-50 border border-rose-200/60 p-4 text-[12.5px] text-rose-800">
                <span className="font-semibold">Marketing recoup position is ambiguous.</span>{" "}
                "Against gross" vs "inside cap" — this is the Coastal Spell dispute pattern.
                Clarify with the agent now.
              </div>
            )}

            {/* Extracted rules grid */}
            <div>
              <div className="eyebrow text-[10px] text-ink-500 mb-2">
                Extracted deal structure
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <RuleField label="Deal type" value={result.deal_type} />
                {result.guarantee_amount > 0 && (
                  <RuleField label="Guarantee" value={fmt(result.guarantee_amount)} />
                )}
                {result.percentage > 0 && (
                  <RuleField
                    label="Percentage"
                    value={`${(result.percentage * 100).toFixed(0)}%`}
                  />
                )}
                {result.expense_cap > 0 && (
                  <RuleField
                    label="Expense cap"
                    value={fmt(result.expense_cap)}
                    sub={result.expense_cap_scope.join(", ") || undefined}
                  />
                )}
                {result.hospitality_cap > 0 && (
                  <RuleField
                    label="Hospitality cap"
                    value={fmt(result.hospitality_cap)}
                    sub={result.hospitality_overage_treatment.replace(/_/g, " ")}
                  />
                )}
                {result.marketing_recoup_amount > 0 && (
                  <RuleField
                    label="Marketing recoup"
                    value={fmt(result.marketing_recoup_amount)}
                    sub={result.marketing_recoup_position.replace(/_/g, " ")}
                    highlight={result.marketing_recoup_position === "ambiguous"}
                  />
                )}
                {result.walkout_pot_threshold > 0 && (
                  <RuleField
                    label="Walkout pot"
                    value={`>${fmt(result.walkout_pot_threshold)}`}
                    sub={`${(result.walkout_pot_percentage * 100).toFixed(0)}% of overage`}
                  />
                )}
              </div>
            </div>

            {/* Citations toggle */}
            {citationEntries.length > 0 && (
              <div>
                <button
                  onClick={() => setShowCitations(!showCitations)}
                  className="flex items-center gap-1.5 text-[12px] text-brand-700 hover:text-brand-800 font-medium"
                >
                  {showCitations ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                  {showCitations ? "Hide" : "Show"} source citations
                </button>
                {showCitations && (
                  <div className="mt-2 space-y-2">
                    {citationEntries.map(([field, quote]) => (
                      <div key={field} className="flex gap-2 text-[12px]">
                        <span className="text-ink-400 font-mono min-w-[140px] shrink-0">{field}</span>
                        <span className="text-ink-700 italic">&ldquo;{quote}&rdquo;</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Reasoning trace toggle */}
            {result.reasoning && (
              <div>
                <button
                  onClick={() => setShowReasoning(!showReasoning)}
                  className="flex items-center gap-1.5 text-[12px] text-ink-500 hover:text-ink-700 font-medium"
                >
                  {showReasoning ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                  {showReasoning ? "Hide" : "Show"} DSPy reasoning trace
                </button>
                {showReasoning && (
                  <div className="mt-2 text-[12px] text-ink-600 bg-canvas-soft rounded-lg p-4 ring-1 ring-ink-200/60 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
                    {result.reasoning}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RuleField({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className={`rounded-lg p-3 ring-1 ring-inset ${highlight ? "bg-amber-50 ring-amber-200/80" : "bg-canvas-soft ring-ink-200/60"}`}>
      <div className="text-[10px] text-ink-400 uppercase tracking-wide mb-1">{label}</div>
      <div className={`text-[13px] font-mono font-medium break-all ${highlight ? "text-amber-800" : "text-ink-900"}`}>
        {value}
      </div>
      {sub && (
        <div className={`text-[11px] mt-0.5 ${highlight ? "text-amber-600" : "text-ink-400"}`}>{sub}</div>
      )}
    </div>
  );
}
