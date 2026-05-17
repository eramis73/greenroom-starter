"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Sparkles,
  Square,
  Loader2,
  CheckCircle,
  AlertTriangle,
  Eye,
  EyeOff,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";

type Provider = "anthropic" | "openai";
type Status = "stopped" | "starting" | "running" | "error";

const MODELS: Record<Provider, { value: string; label: string; recommended?: boolean }[]> = {
  anthropic: [
    { value: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5 — fast & cheap" },
    { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", recommended: true },
    { value: "claude-opus-4-7", label: "Claude Opus 4.7 — most capable" },
  ],
  openai: [
    { value: "gpt-4o-mini", label: "GPT-4o Mini — fast & cheap" },
    { value: "gpt-4o", label: "GPT-4o", recommended: true },
    { value: "gpt-4-turbo", label: "GPT-4 Turbo" },
  ],
};

const KEY_LINKS: Record<Provider, string> = {
  anthropic: "https://console.anthropic.com/settings/keys",
  openai: "https://platform.openai.com/api-keys",
};

export default function SettingsPage() {
  const [provider, setProvider] = useState<Provider>("anthropic");
  const [model, setModel] = useState(MODELS.anthropic[1].value);
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [status, setStatus] = useState<Status>("stopped");
  const [activeModel, setActiveModel] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const pollStatus = useCallback(async () => {
    const res = await fetch("/api/backend/status").catch(() => null);
    if (!res?.ok) return;
    const data = await res.json();
    setStatus(data.running ? "running" : "stopped");
    setActiveModel(data.model ?? null);
  }, []);

  // Poll every 5 s while page is mounted
  useEffect(() => {
    pollStatus();
    const id = setInterval(pollStatus, 5000);
    return () => clearInterval(id);
  }, [pollStatus]);

  // When provider changes, reset model to recommended
  function switchProvider(p: Provider) {
    setProvider(p);
    setModel(MODELS[p].find((m) => m.recommended)?.value ?? MODELS[p][0].value);
    setApiKey("");
    setErrorMsg(null);
  }

  async function startBackend() {
    if (!apiKey.trim()) return;
    setStatus("starting");
    setErrorMsg(null);

    const res = await fetch("/api/backend/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, provider, apiKey }),
    }).catch(() => null);

    if (!res) {
      setStatus("error");
      setErrorMsg("Network error — is Next.js running?");
      return;
    }

    const data = await res.json();
    if (res.ok && data.status === "running") {
      setStatus("running");
      setActiveModel(data.model);
    } else {
      setStatus("error");
      setErrorMsg(data.error ?? "Backend failed to start");
    }
  }

  async function stopBackend() {
    await fetch("/api/backend/start", { method: "DELETE" }).catch(() => null);
    setStatus("stopped");
    setActiveModel(null);
  }

  const statusConfig = {
    stopped: { color: "text-ink-400", dot: "bg-ink-300", label: "Stopped" },
    starting: { color: "text-amber-600", dot: "bg-amber-400 animate-pulse", label: "Starting…" },
    running: { color: "text-emerald-700", dot: "bg-emerald-500", label: "Running" },
    error: { color: "text-rose-700", dot: "bg-rose-500", label: "Error" },
  }[status];

  return (
    <div className="px-12 py-10 max-w-2xl">
      <div className="mb-10">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="h-5 w-5 text-brand-700" />
          <h1
            className="font-display text-[32px] font-medium text-ink-900 leading-none"
            style={{ letterSpacing: "-0.02em" }}
          >
            AI Backend
          </h1>
          {/* Live status pill */}
          <span
            className={`ml-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium ${statusConfig.color}`}
          >
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${statusConfig.dot}`} />
            {statusConfig.label}
            {status === "running" && activeModel && (
              <span className="font-mono text-[10px] opacity-70 ml-1">{activeModel}</span>
            )}
          </span>
        </div>
        <p className="text-[13px] text-ink-500 leading-relaxed">
          Select a model and paste your API key. Greenroom will start the DSPy
          settlement agent in the background — no terminal needed.
        </p>
      </div>

      <div className="space-y-6">
        {/* Provider tabs */}
        <div>
          <label className="eyebrow text-[10px] text-ink-500 uppercase tracking-wide mb-2 block">
            Provider
          </label>
          <div className="flex gap-2">
            {(["anthropic", "openai"] as Provider[]).map((p) => (
              <button
                key={p}
                onClick={() => switchProvider(p)}
                disabled={status === "starting"}
                className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-all ring-1 ring-inset ${
                  provider === p
                    ? "bg-ink-900 text-white ring-ink-900"
                    : "bg-white text-ink-600 ring-ink-200/80 hover:bg-ink-50 hover:text-ink-900"
                }`}
              >
                {p === "anthropic" ? "Anthropic" : "OpenAI"}
              </button>
            ))}
          </div>
        </div>

        {/* Model selector */}
        <div>
          <label className="eyebrow text-[10px] text-ink-500 uppercase tracking-wide mb-2 block">
            Model
          </label>
          <div className="space-y-2">
            {MODELS[provider].map((m) => (
              <label
                key={m.value}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg ring-1 ring-inset cursor-pointer transition-all ${
                  model === m.value
                    ? "bg-brand-50 ring-brand-300/80 text-brand-900"
                    : "bg-white ring-ink-200/60 text-ink-700 hover:bg-ink-50"
                }`}
              >
                <input
                  type="radio"
                  name="model"
                  value={m.value}
                  checked={model === m.value}
                  onChange={() => setModel(m.value)}
                  className="accent-brand-700"
                  disabled={status === "starting"}
                />
                <span className="text-[13px]">{m.label}</span>
                {m.recommended && (
                  <span className="ml-auto text-[10px] font-medium px-1.5 py-0.5 rounded bg-brand-100 text-brand-700">
                    Recommended
                  </span>
                )}
              </label>
            ))}
          </div>
        </div>

        {/* API Key input */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="eyebrow text-[10px] text-ink-500 uppercase tracking-wide">
              API Key
            </label>
            <a
              href={KEY_LINKS[provider]}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-brand-700 hover:text-brand-800 hover:underline"
            >
              Get key <ExternalLink className="h-2.5 w-2.5" />
            </a>
          </div>
          <div className="relative">
            <input
              type={showKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                provider === "anthropic" ? "sk-ant-api03-…" : "sk-proj-…"
              }
              disabled={status === "starting"}
              className="w-full rounded-lg ring-1 ring-ink-200/80 bg-canvas-soft text-[13px] text-ink-800 placeholder:text-ink-400 px-4 py-3 pr-10 focus:outline-none focus:ring-2 focus:ring-brand-700/50 font-mono disabled:opacity-60"
            />
            <button
              type="button"
              onClick={() => setShowKey((s) => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-700"
            >
              {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          <p className="mt-1.5 text-[11px] text-ink-400">
            Key is used only in this session and is never stored.
          </p>
        </div>

        {/* Error banner */}
        {status === "error" && errorMsg && (
          <div className="rounded-lg bg-rose-50 border border-rose-200/60 p-4 flex gap-3">
            <AlertTriangle className="h-4 w-4 text-rose-700 mt-0.5 shrink-0" />
            <div className="text-[12.5px] text-rose-800">{errorMsg}</div>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-3 items-center">
          {status !== "running" ? (
            <Button
              variant="brand"
              onClick={startBackend}
              disabled={!apiKey.trim() || status === "starting"}
            >
              {status === "starting" ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Starting backend…
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Start AI Backend
                </>
              )}
            </Button>
          ) : (
            <>
              <div className="flex items-center gap-2 text-[13px] text-emerald-700 font-medium">
                <CheckCircle className="h-4 w-4" />
                DSPy backend running
              </div>
              <Button variant="ghost" size="sm" onClick={stopBackend}>
                <Square className="h-3.5 w-3.5" />
                Stop
              </Button>
            </>
          )}
        </div>

        {status === "running" && (
          <div className="rounded-lg bg-emerald-50 border border-emerald-200/60 p-4 text-[12.5px] text-emerald-800 leading-relaxed">
            <span className="font-semibold">AI features are live.</span> Go to any
            show&apos;s settlement page and use{" "}
            <span className="font-medium">&ldquo;Parse deal notes with DSPy AI&rdquo;</span> or{" "}
            <span className="font-medium">&ldquo;Add expense from receipt&rdquo;</span>.
          </div>
        )}

        {/* How it works */}
        <div className="pt-4 border-t border-ink-200/60">
          <div className="eyebrow text-[10px] text-ink-500 uppercase tracking-wide mb-3">
            How it works
          </div>
          <ol className="space-y-2 text-[12.5px] text-ink-600 leading-relaxed list-decimal list-inside">
            <li>Next.js spawns <span className="font-mono text-ink-800">python api.py</span> with your key as an env var</li>
            <li>DSPy configures the selected model (ChainOfThought + Assert + Suggest)</li>
            <li>Deal notes → structured financial rules with ambiguity detection</li>
            <li>Receipts/invoices → Greenroom expense entries with confidence scores</li>
            <li>All math runs in Python — no LLM for the numbers</li>
          </ol>
        </div>
      </div>
    </div>
  );
}
