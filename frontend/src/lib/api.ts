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
  token: string
): Promise<AskResponse> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not set");
  }
  const res = await fetch(`${apiUrl}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    throw new Error(`/ask returned ${res.status}`);
  }
  return res.json() as Promise<AskResponse>;
}
