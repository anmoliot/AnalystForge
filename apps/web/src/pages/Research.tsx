import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Sparkles,
  Send,
  Plus,
  BookOpen,
  ExternalLink,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";

export interface CitationItem {
  source_type: string;
  title: string;
  accession?: string;
  url?: string;
  period?: string;
  fact_concept?: string;
  fact_value?: number;
  snippet?: string;
}

export interface MessageItem {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: CitationItem[];
  created_at: string;
}

export interface ResearchSessionItem {
  id: string;
  title: string;
  ticker?: string;
  created_at: string;
  updated_at: string;
}

const SAMPLE_QUESTIONS = [
  "What are the primary revenue drivers and margin expectations?",
  "What are the major risk factors highlighted in recent filings?",
  "How did free cash flow and capital expenditure trend over the past year?",
  "Summarize key updates from recent regulatory filings and news.",
];

export default function Research() {
  const queryClient = useQueryClient();
  const [ticker, setTicker] = useState("NVDA");
  const [queryInput, setQueryInput] = useState("");
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([
    {
      id: "initial-welcome",
      role: "assistant",
      content:
        "Welcome to the Grounded Research Assistant. I retrieve official SEC filings, XBRL facts, and vetted financial news to answer your investment questions with strict citation provenance.",
      created_at: new Date().toISOString(),
    },
  ]);

  // Load sessions
  const { data: sessions = [] } = useQuery<ResearchSessionItem[]>({
    queryKey: ["research-sessions"],
    queryFn: async () => {
      try {
        return await api.get<ResearchSessionItem[]>("/api/v1/research/sessions");
      } catch {
        return [];
      }
    },
  });

  // Query mutation
  const queryMutation = useMutation({
    mutationFn: async ({ q, t, sId }: { q: string; t: string; sId: string | null }) => {
      return await api.post<{
        answer: string;
        citations: CitationItem[];
        session_id?: string;
        ticker?: string;
      }>("/api/v1/research/query", {
        query: q,
        ticker: t.toUpperCase().trim() || undefined,
        session_id: sId || undefined,
      });
    },
    onSuccess: (data, variables) => {
      const userMsg: MessageItem = {
        id: `user-${Date.now()}`,
        role: "user",
        content: variables.q,
        created_at: new Date().toISOString(),
      };
      const assistantMsg: MessageItem = {
        id: `asst-${Date.now()}`,
        role: "assistant",
        content: data.answer,
        citations: data.citations,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setQueryInput("");
      if (data.session_id) {
        queryClient.invalidateQueries({ queryKey: ["research-sessions"] });
      }
    },
  });

  // Create session mutation
  const createSessionMutation = useMutation({
    mutationFn: async () => {
      return await api.post<{ id: string; title: string }>("/api/v1/research/sessions", {
        title: `${ticker} Investment Memo ${new Date().toISOString().slice(0, 10)}`,
        ticker: ticker.toUpperCase().trim(),
      });
    },
    onSuccess: (data) => {
      setCurrentSessionId(data.id);
      queryClient.invalidateQueries({ queryKey: ["research-sessions"] });
      setMessages([
        {
          id: `welcome-${data.id}`,
          role: "assistant",
          content: `New research workspace created for ${ticker}. Ask any grounded question over indexed filings, XBRL facts, or disclosures.`,
          created_at: new Date().toISOString(),
        },
      ]);
    },
  });

  const handleSelectSession = async (sId: string) => {
    setCurrentSessionId(sId);
    try {
      const res = await api.get<{
        id: string;
        title: string;
        messages: MessageItem[];
      }>(`/api/v1/research/sessions/${sId}`);
      if (res.messages && res.messages.length > 0) {
        setMessages(res.messages);
      }
    } catch {
      // Keep existing messages on error
    }
  };

  const handleSend = () => {
    if (!queryInput.trim() || queryMutation.isPending) return;
    queryMutation.mutate({
      q: queryInput.trim(),
      t: ticker,
      sId: currentSessionId,
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-accent" />
            <h1 className="text-2xl font-semibold tracking-tight text-ink">Grounded Research Assistant</h1>
          </div>
          <p className="mt-1 text-sm text-muted">
            SEC EDGAR filings, XBRL disclosures, and market news indexed with strict passage citation provenance.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="TICKER"
            className="w-24 rounded-md border border-neutral-700 bg-elevated px-3 py-1.5 text-center font-mono text-sm font-semibold text-accent uppercase focus:border-brand-500 focus:outline-none"
            data-testid="research-ticker-input"
          />
          <Button
            size="sm"
            onClick={() => createSessionMutation.mutate()}
            disabled={createSessionMutation.isPending}
            data-testid="new-session-button"
          >
            <Plus className="mr-1.5 h-4 w-4" />
            New Workspace
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        {/* Sidebar Sessions */}
        <div className="space-y-4">
          <Panel className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted">
                Workspaces ({sessions.length})
              </span>
            </div>
            {sessions.length === 0 ? (
              <p className="text-xs text-muted">
                No saved workspaces. Click &quot;New Workspace&quot; to persist your research history.
              </p>
            ) : (
              <div className="space-y-1">
                {sessions.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => handleSelectSession(s.id)}
                    className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-xs transition ${
                      currentSessionId === s.id
                        ? "bg-brand-500/10 text-accent border border-brand-500/30"
                        : "text-ink hover:bg-elevated"
                    }`}
                  >
                    <span className="truncate">{s.title}</span>
                    {s.ticker && (
                      <span className="ml-1 rounded bg-elevated px-1 py-0.5 font-mono text-[10px]">
                        {s.ticker}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </Panel>

          {/* Quick Prompts */}
          <Panel className="p-4">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              Suggested Questions
            </span>
            <div className="mt-3 space-y-2">
              {SAMPLE_QUESTIONS.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => setQueryInput(q)}
                  className="block w-full rounded border border-neutral-800 bg-elevated/60 p-2 text-left text-xs text-ink transition hover:border-neutral-700 hover:text-ink"
                >
                  {q}
                </button>
              ))}
            </div>
          </Panel>
        </div>

        {/* Chat / Assistant Panel */}
        <Panel className="flex flex-col lg:col-span-3 min-h-[550px]">
          <div className="flex-1 space-y-4 overflow-y-auto p-5" data-testid="research-conversation">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex flex-col ${
                  m.role === "user" ? "items-end" : "items-start"
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-lg p-4 text-sm leading-relaxed ${
                    m.role === "user"
                      ? "bg-brand-600 text-ink"
                      : "border border-neutral-800 bg-elevated/90 text-ink"
                  }`}
                >
                  <div className="whitespace-pre-wrap">{m.content}</div>

                  {/* Citations Card */}
                  {m.citations && m.citations.length > 0 && (
                    <div className="mt-4 border-t border-neutral-800 pt-3">
                      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-accent mb-2">
                        <BookOpen className="h-3.5 w-3.5" />
                        Grounded Citations & Provenance ({m.citations.length})
                      </div>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {m.citations.map((c, i) => (
                          <div
                            key={i}
                            className="rounded border border-neutral-800 bg-panel/70 p-2 text-xs"
                          >
                            <div className="flex items-center justify-between">
                              <Badge tone="neutral" className="text-[10px]">
                                {c.source_type}
                              </Badge>
                              {c.period && (
                                <span className="text-[10px] text-muted">{c.period}</span>
                              )}
                            </div>
                            <p className="mt-1 font-medium text-ink line-clamp-1">{c.title}</p>
                            {c.snippet && (
                              <p className="mt-1 text-muted line-clamp-2">{c.snippet}</p>
                            )}
                            {c.url && (
                              <a
                                href={c.url}
                                target="_blank"
                                rel="noreferrer"
                                className="mt-1.5 inline-flex items-center gap-1 text-[10px] text-accent hover:underline"
                              >
                                View Source <ExternalLink className="h-2.5 w-2.5" />
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {queryMutation.isPending && (
              <div className="flex items-center gap-2 text-xs text-muted">
                <Sparkles className="h-4 w-4 animate-spin text-accent" />
                Synthesizing grounded analysis from indexed filings and disclosures...
              </div>
            )}
          </div>

          {/* Input Box */}
          <div className="border-t border-neutral-800 p-4">
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder={`Ask a grounded investment question regarding ${ticker}...`}
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                className="flex-1 rounded-md border border-neutral-700 bg-elevated px-4 py-2.5 text-sm text-ink placeholder-neutral-500 focus:border-brand-500 focus:outline-none"
                data-testid="research-query-input"
              />
              <Button
                onClick={handleSend}
                disabled={!queryInput.trim() || queryMutation.isPending}
                data-testid="send-research-query-button"
              >
                <Send className="mr-1.5 h-4 w-4" />
                Ask Assistant
              </Button>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
