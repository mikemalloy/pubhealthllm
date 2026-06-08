import LlmChat from "@/components/LlmChat";

// Auth is enforced by clerkMiddleware() in middleware.ts (auth.protect() on /llm).
// No redundant auth() call here — Clerk v7 re-throws all errors from buildRequestLike(),
// causing a 500 if called outside a fully-resolved middleware request context.
export default function LlmPage() {
  return <LlmChat />;
}
