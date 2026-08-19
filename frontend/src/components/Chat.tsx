"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
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

interface DocItem {
  source: string;
  file_path: string;
  chunk_count: number;
  created_at: string | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  // Document Management Modal & Upload State
  const [showDocsModal, setShowDocsModal] = useState(false);
  const [documents, setDocuments] = useState<DocItem[]>([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch document list
  async function fetchDocuments() {
    try {
      const res = await fetch(`${API_URL}/documents`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || []);
        setTotalChunks(data.total_chunks || 0);
      }
    } catch {
      // ignore on initial load
    }
  }

  useEffect(() => {
    fetchDocuments();
  }, []);

  async function handleFileUpload(file: File) {
    if (!file) return;
    setUploading(true);
    setUploadStatus(`Indexing ${file.name}...`);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("source", "upload");

    try {
      const res = await fetch(`${API_URL}/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }

      const data = await res.json();
      setUploadStatus(`✓ Indexed ${data.chunks_indexed} chunks from "${file.name}"`);
      await fetchDocuments();
      setTimeout(() => setUploadStatus(null), 5000);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Upload error";
      setUploadStatus(`❌ ${errorMsg}`);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDeleteDoc(filePath: string) {
    if (!confirm(`Delete "${filePath}" and all its indexed chunks?`)) return;
    try {
      const res = await fetch(`${API_URL}/documents/${encodeURIComponent(filePath)}`, {
        method: "DELETE",
      });
      if (res.ok) {
        await fetchDocuments();
      }
    } catch (e) {
      alert("Failed to delete document");
    }
  }

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
    <div className="relative mx-auto flex w-full max-w-3xl flex-1 flex-col">
      {/* Top Action Bar */}
      <div className="flex items-center justify-between border-b border-gray-100 py-3 dark:border-gray-800">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-500"></span>
          <span>
            {totalChunks > 0 ? `${totalChunks.toLocaleString()} chunks in index` : "No docs indexed yet"}
          </span>
        </div>
        <button
          onClick={() => {
            fetchDocuments();
            setShowDocsModal(true);
          }}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium shadow-sm transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:hover:bg-gray-800"
        >
          <span>📁</span>
          <span>Upload & Manage Docs</span>
        </button>
      </div>

      {/* Chat Messages */}
      <div className="flex-1 space-y-4 overflow-y-auto py-6">
        {messages.length === 0 && (
          <div className="my-auto flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-3 text-3xl">💬</div>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200">
              Hybrid-Search Documentation Assistant
            </h3>
            <p className="mt-1 max-w-md text-xs text-gray-500 dark:text-gray-400">
              Ask anything across React, Next.js, or your custom uploaded documents. Powered by
              BM25 keyword search + pgvector semantic search.
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {[
                "How do I avoid re-running an effect on every render?",
                "What is the difference between Server and Client Components?",
                "How do I configure ISR in Next.js App Router?",
              ].map((suggestion, idx) => (
                <button
                  key={idx}
                  onClick={() => setInput(suggestion)}
                  className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-600 transition hover:border-blue-500 hover:text-blue-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:border-blue-400 dark:hover:text-blue-400"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={
                "inline-block max-w-[88%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed " +
                (m.role === "user"
                  ? "bg-blue-600 text-white shadow-sm"
                  : "bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100")
              }
            >
              {m.content || (loading && i === messages.length - 1 ? "Thinking and searching..." : "")}
            </div>
            {m.sources && m.sources.length > 0 && (
              <div className="mt-2 flex flex-wrap justify-start gap-x-2 gap-y-1.5 text-xs">
                <span className="font-semibold text-gray-400">Sources:</span>
                {m.sources.map((s) => (
                  <a
                    key={s.index}
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-0.5 text-blue-600 hover:underline dark:bg-gray-800 dark:text-blue-400"
                  >
                    <span className="font-mono font-bold">[{s.index}]</span>
                    <span>{s.heading_path}</span>
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Input Form */}
      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-gray-200 py-4 dark:border-gray-800">
        <input
          className="flex-1 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about React, Next.js, or your uploaded documents…"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="inline-flex items-center justify-center rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Searching..." : "Send"}
        </button>
      </form>

      {/* Upload & Document Management Modal */}
      {showDocsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex max-h-[90vh] w-full max-w-xl flex-col rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4 dark:border-gray-800">
              <div>
                <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                  Document Knowledge Base
                </h2>
                <p className="text-xs text-gray-500">Upload and manage indexed documents</p>
              </div>
              <button
                onClick={() => setShowDocsModal(false)}
                className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
              >
                ✕
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Drag and Drop Zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragOver(true);
                }}
                onDragLeave={() => setIsDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragOver(false);
                  if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                    handleFileUpload(e.dataTransfer.files[0]);
                  }
                }}
                onClick={() => fileInputRef.current?.click()}
                className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition ${
                  isDragOver
                    ? "border-blue-500 bg-blue-50/50 dark:bg-blue-950/20"
                    : "border-gray-300 hover:border-gray-400 dark:border-gray-700 dark:hover:border-gray-600"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".md,.mdx,.txt,.pdf"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleFileUpload(e.target.files[0]);
                    }
                  }}
                />
                <div className="text-3xl mb-2">📄</div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
                  {uploading ? "Chunking & Embedding..." : "Click or drag & drop a document here"}
                </p>
                <p className="mt-1 text-xs text-gray-400">Supports .md, .mdx, .txt, .pdf</p>
              </div>

              {/* Upload Status Banner */}
              {uploadStatus && (
                <div className="rounded-lg bg-blue-50 p-3 text-xs text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">
                  {uploadStatus}
                </div>
              )}

              {/* Document List */}
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
                  Indexed Sources ({documents.length} files, {totalChunks.toLocaleString()} chunks)
                </h3>
                <div className="max-h-60 space-y-1.5 overflow-y-auto pr-1">
                  {documents.length === 0 ? (
                    <p className="py-4 text-center text-xs text-gray-500">No documents indexed yet.</p>
                  ) : (
                    documents.map((doc, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50/60 px-3 py-2 text-xs dark:border-gray-800 dark:bg-gray-800/50"
                      >
                        <div className="flex items-center gap-2 truncate">
                          <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-bold text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
                            {doc.source}
                          </span>
                          <span className="truncate font-mono text-gray-700 dark:text-gray-300">
                            {doc.file_path}
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-gray-400">{doc.chunk_count} chunks</span>
                          {doc.source === "upload" && (
                            <button
                              onClick={() => handleDeleteDoc(doc.file_path)}
                              title="Delete document"
                              className="text-gray-400 hover:text-red-500"
                            >
                              ✕
                            </button>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex justify-end border-t border-gray-100 px-6 py-3 dark:border-gray-800">
              <button
                onClick={() => setShowDocsModal(false)}
                className="rounded-lg bg-gray-100 px-4 py-2 text-xs font-medium text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
