import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import type { ChildProcess } from "child_process";
import path from "path";

// Module-level singleton persists across hot reloads in Next.js dev mode
declare global {
  // eslint-disable-next-line no-var
  var __backendProcess: ChildProcess | null;
  // eslint-disable-next-line no-var
  var __backendModel: string | null;
}
global.__backendProcess = global.__backendProcess ?? null;
global.__backendModel = global.__backendModel ?? null;

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch("http://localhost:8000/health", {
      signal: AbortSignal.timeout(3000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// POST /api/backend/start — spawn the Python process
export async function POST(req: NextRequest) {
  const { model, provider, apiKey } = await req.json();

  if (!apiKey?.trim()) {
    return NextResponse.json({ error: "API key is required" }, { status: 400 });
  }
  if (!model?.trim()) {
    return NextResponse.json({ error: "Model is required" }, { status: 400 });
  }

  // Kill any existing process first
  if (global.__backendProcess) {
    try {
      global.__backendProcess.kill("SIGTERM");
    } catch {}
    global.__backendProcess = null;
    await sleep(600);
  }

  const dspyModel =
    provider === "openai" && !model.startsWith("openai/")
      ? `openai/${model}`
      : model;

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    DSPY_MODEL: dspyModel,
    DSPY_API_KEY: apiKey,
    // Also set the legacy vars so any direct os.environ lookups still work
    ...(provider === "anthropic"
      ? { ANTHROPIC_API_KEY: apiKey }
      : { OPENAI_API_KEY: apiKey }),
  };

  const backendDir = path.join(process.cwd(), "backend");

  // On Windows "python" is the standard; on Unix try "python3" first
  const pythonCmd = process.platform === "win32" ? "python" : "python3";

  try {
    const proc = spawn(pythonCmd, ["api.py"], {
      cwd: backendDir,
      env,
      stdio: "pipe",
    });

    proc.on("exit", () => {
      if (global.__backendProcess === proc) {
        global.__backendProcess = null;
        global.__backendModel = null;
      }
    });

    global.__backendProcess = proc;
    global.__backendModel = dspyModel;

    // Give uvicorn time to boot
    for (let i = 0; i < 8; i++) {
      await sleep(500);
      if (await checkHealth()) {
        return NextResponse.json({ status: "running", model: dspyModel });
      }
    }

    return NextResponse.json(
      { error: "Backend started but didn't respond within 4 s" },
      { status: 500 }
    );
  } catch (err) {
    return NextResponse.json(
      { error: `Failed to spawn Python: ${err}` },
      { status: 500 }
    );
  }
}

// DELETE /api/backend/start — stop the process
export async function DELETE() {
  if (global.__backendProcess) {
    try {
      global.__backendProcess.kill("SIGTERM");
    } catch {}
    global.__backendProcess = null;
    global.__backendModel = null;
  }
  return NextResponse.json({ status: "stopped" });
}
