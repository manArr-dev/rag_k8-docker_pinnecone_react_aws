import { useCallback, useEffect, useRef, useState } from "react";
import { type HistoryMessage, type Source, streamChat } from "./api";
import { Composer } from "./components/Composer";
import { Message } from "./components/Message";
import { UploadPanel } from "./components/UploadPanel";

export interface ChatTurn {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  status?: "streaming" | "done" | "error";
  notice?: string;
}

const SUGGESTIONS = [
  "Summarize the key points of the uploaded documents",
  "What does the documentation say about pricing?",
];

export default function App() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const nextId = useRef(1);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  const send = useCallback(
    async (text: string) => {
      if (busy) return;
      // Only completed exchanges go back to the server as history.
      const history: HistoryMessage[] = turns
        .filter((t) => t.content && t.status !== "error")
        .map(({ role, content }) => ({ role, content }));

      const userId = nextId.current;
      const assistantId = userId + 1;
      setTurns((prev) => [
        ...prev,
        { id: userId, role: "user", content: text },
        { id: assistantId, role: "assistant", content: "", status: "streaming" },
      ]);
      nextId.current += 2;

      const patch = (update: (turn: ChatTurn) => ChatTurn) =>
        setTurns((prev) => prev.map((t) => (t.id === assistantId ? update(t) : t)));

      const controller = new AbortController();
      abortRef.current = controller;
      setBusy(true);
      try {
        await streamChat(
          text,
          history,
          {
            onSources: (sources) => patch((t) => ({ ...t, sources })),
            onToken: (delta) => patch((t) => ({ ...t, content: t.content + delta })),
            onDone: ({ truncated }) =>
              patch((t) => ({
                ...t,
                status: "done",
                notice: truncated ? "The answer was cut off at the length limit." : undefined,
              })),
            onError: (message) => patch((t) => ({ ...t, status: "error", notice: message })),
          },
          controller.signal,
        );
      } catch (err) {
        if (controller.signal.aborted) {
          patch((t) => ({ ...t, status: "done", notice: "Stopped." }));
        } else {
          const message = err instanceof Error ? err.message : "Request failed";
          patch((t) => ({ ...t, status: "error", notice: message }));
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    [busy, turns],
  );

  return (
    <div className="app">
      <header className="header">
        <h1>Document Chat</h1>
        <div className="header-actions">
          {turns.length > 0 && (
            <button className="ghost" onClick={() => setTurns([])} disabled={busy}>
              New chat
            </button>
          )}
          <button className="ghost" onClick={() => setShowUpload((v) => !v)}>
            {showUpload ? "Close" : "Add documents"}
          </button>
        </div>
      </header>

      {showUpload && <UploadPanel />}

      <main className="messages">
        {turns.length === 0 ? (
          <div className="empty">
            <h2>Ask about your documents</h2>
            <p>Answers are grounded in the indexed documents and cite the passages they use.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="suggestion" onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          turns.map((turn) => <Message key={turn.id} turn={turn} />)
        )}
        <div ref={bottomRef} />
      </main>

      <Composer busy={busy} onSend={send} onStop={() => abortRef.current?.abort()} />
    </div>
  );
}
