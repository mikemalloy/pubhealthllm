"use client";

import { useRef, useState } from "react";
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
import { askQuestion } from "@/lib/api";

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

// Sentinel value for the "thinking" bubble
const THINKING_SENTINEL = "__thinking__";

// ── Types ────────────────────────────────────────────────────────────────────

type Role = "user" | "assistant";

interface Message {
  id: number;
  role: Role;
  text: string;
}

// ── Sub-components ───────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  const isThinking = msg.text === THINKING_SENTINEL;

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
        {isThinking ? "Thinking…" : msg.text}
      </div>
    </div>
  );
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
  const chatEndRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<PanelImperativeHandle | null>(null);
  const nextId = useRef(0);

  const scrollToBottom = () =>
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });

  const handleSubmit = async () => {
    const text = input.trim();
    if (!text || isLoading) return;

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
      return;
    }

    const userMsg: Message = { id: nextId.current++, role: "user", text };
    const thinkingMsg: Message = {
      id: nextId.current++,
      role: "assistant",
      text: THINKING_SENTINEL,
    };

    setMessages((prev) => [...prev, userMsg, thinkingMsg]);
    setInput("");
    setIsLoading(true);
    setTimeout(scrollToBottom, 50);

    try {
      const resp = await askQuestion(text, token);
      const assistantText = resp.chat_message;

      setMessages((prev) => [
        // Remove the thinking bubble (last message)
        ...prev.slice(0, -1),
        { id: nextId.current++, role: "assistant", text: assistantText },
      ]);

      if (resp.mode === "artifact" && resp.artifact?.markdown) {
        setArtifact(resp.artifact.markdown);
      }
      // if mode === "chat", leave artifact panel as-is
    } catch {
      setMessages((prev) => [
        // Remove the thinking bubble (last message)
        ...prev.slice(0, -1),
        {
          id: nextId.current++,
          role: "assistant",
          text: "Something went wrong — please try again.",
        },
      ]);
    } finally {
      setIsLoading(false);
      setTimeout(scrollToBottom, 50);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
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
              onClick={handleSubmit}
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
