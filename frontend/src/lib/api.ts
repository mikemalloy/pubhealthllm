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
  signal?: AbortSignal
): Promise<AskResponse> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not set");
  }
  if (!token) throw new Error("askQuestion called without an auth token");

  const timeoutSignal = AbortSignal.timeout(60_000);
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
