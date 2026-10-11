import { createSseParser } from "./sse";

const API_BASE: string = import.meta.env.VITE_API_BASE ?? "";

export interface Source {
  index: number;
  source: string;
  page: number | null;
  score: number;
  text: string;
}

export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatHandlers {
  onSources(sources: Source[]): void;
  onToken(text: string): void;
  onDone(info: { truncated: boolean }): void;
  onError(message: string): void;
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Not JSON (e.g. a proxy error page); fall through to the status line.
  }
  return `Request failed (${res.status})`;
}

/** POST a question and dispatch the streamed reply. Resolves when the stream ends. */
export async function streamChat(
  message: string,
  history: HistoryMessage[],
  handlers: ChatHandlers,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message, history }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(await errorMessage(res));

  let finished = false;
  const feed = createSseParser(({ event, data }) => {
    const payload = JSON.parse(data);
    if (event === "sources") handlers.onSources(payload.sources);
    else if (event === "token") handlers.onToken(payload.text);
    else if (event === "done") {
      finished = true;
      handlers.onDone(payload);
    } else if (event === "error") {
      finished = true;
      handlers.onError(payload.message);
    }
  });

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    feed(value);
  }
  if (!finished) handlers.onError("The connection closed before the answer finished.");
}

export interface UploadResult {
  doc_id: string;
  filename: string;
  chunks: number;
}

export async function uploadDocument(file: File, adminKey: string): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/documents`, {
    method: "POST",
    headers: adminKey ? { "X-API-Key": adminKey } : {},
    body: form,
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}
