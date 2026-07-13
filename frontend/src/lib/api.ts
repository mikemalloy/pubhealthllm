// AskResponse envelope from the Railway backend /ask endpoint

export interface ArtifactPayload {
  type: string;
  title: string;
  markdown: string | null;
  payload: unknown;
}

export interface AskResponse {
  mode: "chat" | "artifact";
  chat_message: string;
  artifact?: ArtifactPayload;
  meta: Record<string, unknown>;
}

/**
 * POST /ask to the Railway backend with a Clerk Bearer token.
 * Single-turn — no message_history sent.
 *
 * Hard timeout: 60 seconds. If the server accepts the connection but never
 * responds (cold start, hung LLM call, wrong host), the fetch rejects with a
 * DOMException(name="TimeoutError") instead of hanging forever. The caller's
 * AbortSignal (e.g. component-unmount) is composed with the timeout signal so
 * either can cancel the request independently.
 */
export async function askQuestion(
  question: string,
  token: string,
  signal?: AbortSignal,
  timeoutMs: number = 60_000
): Promise<AskResponse> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not set");
  }
  if (!token) throw new Error("askQuestion called without an auth token");

  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const composedSignal =
    signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal;

  const res = await fetch(`${apiUrl}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question }),
    signal: composedSignal,
  });
  if (!res.ok) {
    let errorDetail: string;
    try {
      const errBody = await res.json();
      errorDetail = (errBody as { detail?: string })?.detail ?? JSON.stringify(errBody);
    } catch {
      errorDetail = await res.text();
    }
    throw new Error(`/ask returned ${res.status}: ${errorDetail}`);
  }
  // Assumes the backend contract matches AskResponse — no runtime validation
  return res.json() as Promise<AskResponse>;
}

export type WarmupStatus = "ready" | "warming" | "error";

/**
 * GET /warmup — nudges Aurora Serverless v2 to resume from auto-pause.
 *
 * Best-effort and fast: a 10s timeout means a hung/cold backend never stalls
 * the caller. The endpoint itself is single-attempt and returns immediately
 * with the DB's readiness. Returns the parsed status string; on any transport
 * or HTTP error it throws, so the caller can fail silent — warm-up must never
 * break the page.
 */
export async function warmupDatabase(
  token: string,
  signal?: AbortSignal
): Promise<WarmupStatus> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) throw new Error("NEXT_PUBLIC_API_URL is not set");
  if (!token) throw new Error("warmupDatabase called without an auth token");

  const timeoutSignal = AbortSignal.timeout(10_000);
  const composedSignal =
    signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal;

  const res = await fetch(`${apiUrl}/warmup`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
    signal: composedSignal,
  });
  if (!res.ok) {
    throw new Error(`/warmup returned ${res.status}`);
  }
  const body = (await res.json()) as { database?: string };
  const status = body?.database;
  if (status === "ready" || status === "warming" || status === "error") {
    return status;
  }
  // Unknown shape — treat as ready so we never block the page on a surprise.
  return "ready";
}
