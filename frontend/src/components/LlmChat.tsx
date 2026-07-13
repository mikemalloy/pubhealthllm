"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check, Send, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import type { PanelImperativeHandle } from "react-resizable-panels";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { cn } from "@/lib/utils";
import { askQuestion, warmupDatabase } from "@/lib/api";

// ── Content constants ────────────────────────────────────────────────────────

const WELCOME_MD = `# Welcome to the Pub Health LLM

Ask questions about U.S. public health and get evidence-backed answers grounded
in real CDC data — county health statistics (CDC PLACES), mortality (CDC WONDER),
and outbreak reports (CDC MMWR). Every answer comes with its statistics, sources,
and caveats.

**What it can do now**
- County & state health statistics (diabetes, obesity, smoking, and more)
- Compare a measure across locations
- Rank counties by a measure
- Historical outbreak & surveillance context from MMWR

**Coming soon**
- Decision modeling & cost-effectiveness analysis (the di4health decision-tree engine)
- Streaming answers and saved reports
`;

const EXAMPLE_PROMPTS = [
  "What is the diabetes rate in Travis County, TX?",
  "Compare obesity rates in Cook County, IL and Harris County, TX.",
  "Which counties have the highest adult smoking rates?",
];

// Sentinel values for the "thinking" bubble. The warming variant is used for
// the first answer requested while the database is still resuming from
// auto-pause — that response can legitimately take up to a minute.
const THINKING_SENTINEL = "__thinking__";
const THINKING_WARMING_SENTINEL = "__thinking_warming__";

// Warm-up polling: check every 5s, up to ~2 min, then give up silently.
const WARMUP_POLL_MS = 5_000;
const WARMUP_MAX_ATTEMPTS = 24;

// ── Types ────────────────────────────────────────────────────────────────────

type Role = "user" | "assistant";

type DbStatus = "warming" | "ready" | "unknown";

interface Message {
  id: number;
  role: Role;
  text: string;
}

// ── Sub-components ───────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  const isWarmingThinking = msg.text === THINKING_WARMING_SENTINEL;
  const isThinking = msg.text === THINKING_SENTINEL || isWarmingThinking;

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-sm"
            : "bg-muted text-foreground rounded-bl-sm",
          isThinking && "italic text-muted-foreground"
        )}
      >
        {isThinking
          ? isWarmingThinking
            ? "The database is still waking up, so this first answer may take up to a minute…"
            : "Thinking…"
          : msg.text}
      </div>
    </div>
  );
}

// Calm, non-modal status line shown near the chat input while the health
// database resumes from auto-pause (and a brief "ready" confirmation after).
function DbStatusIndicator({
  status,
  showReady,
}: {
  status: DbStatus;
  showReady: boolean;
}) {
  if (status === "warming") {
    return (
      <div className="flex items-start gap-2 px-1 pb-2 text-xs text-muted-foreground">
        <span className="relative mt-1 flex h-2 w-2 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
        </span>
        <span>
          Waking up the health database — this takes about 30 seconds after a
          quiet period. You can type your question now.
        </span>
      </div>
    );
  }
  if (showReady) {
    return (
      <div className="flex items-center gap-2 px-1 pb-2 text-xs text-muted-foreground">
        <span className="inline-flex h-2 w-2 shrink-0 rounded-full bg-green-500" />
        <span>Database ready.</span>
      </div>
    );
  }
  return null;
}

function ArtifactPanel({ markdown }: { markdown: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b shrink-0">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Report
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={handleCopy}
          title="Copy markdown"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-green-500" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>

      {/* Markdown body */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {markdown}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export default function LlmChat() {
  const { getToken } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [artifact, setArtifact] = useState(WELCOME_MD);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [dbStatus, setDbStatus] = useState<DbStatus>("unknown");
  const [showReady, setShowReady] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<PanelImperativeHandle | null>(null);
  const nextId = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const prevDbStatus = useRef<DbStatus>("unknown");

  // Fix I1: scroll to bottom whenever messages change
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Fix I3: abort any in-flight request on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // Warm up Aurora on mount: it auto-pauses after idle, so the first /ask after
  // a quiet period otherwise eats a ~30s cold resume. Ping /warmup immediately;
  // if the DB is resuming, poll until it's ready. Best-effort — any failure
  // fails silent (per-request retries still cover a cold DB) and never breaks
  // the page.
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    const sleep = (ms: number) =>
      new Promise<void>((resolve, reject) => {
        const t = setTimeout(resolve, ms);
        controller.signal.addEventListener("abort", () => {
          clearTimeout(t);
          reject(new DOMException("aborted", "AbortError"));
        });
      });

    const runWarmup = async () => {
      try {
        const token = await getToken();
        if (!token || cancelled) return;

        let status = await warmupDatabase(token, controller.signal);
        if (cancelled) return;
        if (status !== "warming") {
          setDbStatus("ready");
          return;
        }

        // Cluster is resuming — show the indicator and poll until ready.
        setDbStatus("warming");
        for (let attempt = 0; attempt < WARMUP_MAX_ATTEMPTS && !cancelled; attempt++) {
          await sleep(WARMUP_POLL_MS);
          if (cancelled) return;
          try {
            status = await warmupDatabase(token, controller.signal);
          } catch {
            continue; // transient — keep polling
          }
          if (status === "ready") {
            setDbStatus("ready");
            return;
          }
        }
        // Gave up after ~2 min — treat as ready; the per-request retry logic
        // still covers a slow resume.
        if (!cancelled) setDbStatus("ready");
      } catch {
        // Fail silent — warm-up must never break the page.
        if (!cancelled) setDbStatus("ready");
      }
    };

    void runWarmup();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [getToken]);

  // Briefly confirm "Database ready" when the resume completes, then hide.
  useEffect(() => {
    if (prevDbStatus.current === "warming" && dbStatus === "ready") {
      setShowReady(true);
      const t = setTimeout(() => setShowReady(false), 2500);
      prevDbStatus.current = dbStatus;
      return () => clearTimeout(t);
    }
    prevDbStatus.current = dbStatus;
  }, [dbStatus]);

  const handleSubmit = async () => {
    const text = input.trim();
    // Fix C2: guard first, then set loading state immediately before any await
    if (!text || isLoading) return;
    setIsLoading(true);
    setInput("");

    const token = await getToken();
    if (token === null) {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId.current++,
          role: "assistant",
          text: "Authentication error — please sign in again.",
        },
      ]);
      setIsLoading(false);
      return;
    }

    // If the database is still resuming, acknowledge it in the thinking bubble
    // and give this first request a longer timeout — a cold-resume answer can
    // take up to a minute.
    const warming = dbStatus === "warming";
    const thinkingText = warming ? THINKING_WARMING_SENTINEL : THINKING_SENTINEL;

    // Fix C1: store thinkingId so we can remove by ID (not slice)
    const thinkingId = nextId.current++;
    const userMsg: Message = { id: nextId.current++, role: "user", text };
    const thinkingMsg: Message = { id: thinkingId, role: "assistant", text: thinkingText };
    setMessages((prev) => [...prev, userMsg, thinkingMsg]);

    // Fix I3: abort any previous in-flight request, set up new controller
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const resp = await askQuestion(
        text,
        token,
        controller.signal,
        warming ? 120_000 : 60_000
      );
      // Fix I4: null-coalesce chat_message
      const assistantText = resp.chat_message ?? "No response received.";

      // Fix C1: remove thinking bubble by ID
      setMessages((prev) =>
        prev
          .filter((m) => m.id !== thinkingId)
          .concat({ id: nextId.current++, role: "assistant", text: assistantText })
      );

      if (resp.mode === "artifact" && resp.artifact?.markdown) {
        setArtifact(resp.artifact.markdown);
      }
      // if mode === "chat", leave artifact panel as-is
    } catch (err) {
      // Fix I3: skip error bubble if request was aborted (component unmount)
      if (err instanceof Error && err.name === "AbortError") return;
      // Fix m1: log the caught error
      console.error("[LlmChat] askQuestion failed:", err);
      // Surface timeout clearly; fall back to generic message for other errors
      const errText =
        err instanceof Error && err.name === "TimeoutError"
          ? "Request timed out — the backend may be cold-starting. Please try again."
          : "Something went wrong — please try again.";
      // Fix C1: remove thinking bubble by ID
      setMessages((prev) =>
        prev
          .filter((m) => m.id !== thinkingId)
          .concat({ id: nextId.current++, role: "assistant", text: errText })
      );
    } finally {
      setIsLoading(false);
    }
  };

  // Fix m2: void handleSubmit() to silence floating-promise lint warning
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  const toggleChat = () => {
    if (chatCollapsed) {
      panelRef.current?.expand();
      setChatCollapsed(false);
    } else {
      panelRef.current?.collapse();
      setChatCollapsed(true);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] w-full">
      {/* Collapse/expand toggle */}
      <div className="flex items-center gap-2 mb-2 shrink-0">
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleChat}
          className="h-7 gap-1.5 text-xs text-muted-foreground"
        >
          {chatCollapsed ? (
            <>
              <PanelLeftOpen className="h-3.5 w-3.5" /> Show chat
            </>
          ) : (
            <>
              <PanelLeftClose className="h-3.5 w-3.5" /> Hide chat
            </>
          )}
        </Button>
      </div>

      {/* Resizable panels */}
      <ResizablePanelGroup
        orientation="horizontal"
        className="flex-1 rounded-lg border overflow-hidden"
      >
        {/* ── LEFT: Chat ── */}
        <ResizablePanel
          panelRef={panelRef}
          defaultSize={33}
          minSize={20}
          collapsible
          collapsedSize={0}
          onResize={(size) => setChatCollapsed(size.asPercentage === 0)}
          className="flex flex-col"
        >
          {/* Message thread */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 && (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground">
                  Try one of these examples:
                </p>
                {EXAMPLE_PROMPTS.map((p) => (
                  <button
                    key={p}
                    onClick={() => setInput(p)}
                    className="block w-full text-left text-xs px-3 py-2 rounded-lg border border-dashed hover:bg-accent hover:text-accent-foreground transition-colors"
                  >
                    {p}
                  </button>
                ))}
              </div>
            )}
            {messages.map((msg) => (
              <MessageBubble key={msg.id} msg={msg} />
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* DB warm-up status (calm, non-modal) */}
          <div className="shrink-0 px-3 pt-2">
            <DbStatusIndicator status={dbStatus} showReady={showReady} />
          </div>

          {/* Pinned input */}
          <div className="shrink-0 border-t p-3 flex gap-2 items-end">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about public health data…"
              rows={2}
              className="resize-none text-sm flex-1"
              disabled={isLoading}
            />
            <Button
              size="icon"
              onClick={() => void handleSubmit()}
              disabled={isLoading || !input.trim()}
              className="shrink-0"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* ── RIGHT: Artifact ── */}
        <ResizablePanel defaultSize={67} minSize={30}>
          <ArtifactPanel markdown={artifact} />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
