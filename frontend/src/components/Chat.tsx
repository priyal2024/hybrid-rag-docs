"use client";

import { useState, type FormEvent } from "react";
import { streamSSE } from "@/lib/sse";

interface Source {
  index: number;
  url: string;
  heading_path: string;
  source: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const query = input.trim();
    if (!query || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: query }, { role: "assistant", content: "" }]);
    setInput("");
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, k: 6 }),
      });

      if (!response.ok) {
        throw new Error(`backend returned ${response.status}`);
      }

      for await (const evt of streamSSE(response)) {
        setMessages((prev) => {
          const next = [...prev];
          const lastIndex = next.length - 1;
          const last = next[lastIndex];
          if (evt.event === "sources") {
            next[lastIndex] = { ...last, sources: evt.data as Source[] };
          } else if (evt.event === "token") {
            next[lastIndex] = { ...last, content: last.content + (evt.data as string) };
          }
          return next;
        });
      }
    } catch {
      setMessages((prev) => {
        const next = [...prev];
        const lastIndex = next.length - 1;
        next[lastIndex] = {
          ...next[lastIndex],
          content: "Couldn't reach the backend — is it running at " + API_URL + "?",
        };
        return next;
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto py-6">
        {messages.length === 0 && (
          <p className="text-sm text-gray-500">
            Ask anything about the React or Next.js docs — e.g. &ldquo;how do I avoid
            re-running an effect on every render?&rdquo;
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={
                "inline-block max-w-[85%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm " +
                (m.role === "user" ? "bg-blue-600 text-white" : "bg-gray-100 dark:bg-gray-800")
              }
            >
              {m.content || (loading && i === messages.length - 1 ? "…" : "")}
            </div>
            {m.sources && m.sources.length > 0 && (
              <div className="mt-1 flex flex-wrap justify-start gap-x-3 gap-y-1 text-xs text-gray-500">
                {m.sources.map((s) => (
                  <a
                    key={s.index}
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline hover:text-blue-600"
                  >
                    [{s.index}] {s.heading_path}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-gray-200 py-4 dark:border-gray-800">
        <input
          className="flex-1 rounded-md border border-gray-300 bg-transparent px-3 py-2 text-sm dark:border-gray-700"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
