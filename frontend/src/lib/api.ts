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
  const res = await fetch(`${apiUrl}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question }),
    signal,
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
