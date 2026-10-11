import { useState } from "react";
import Markdown from "react-markdown";
import type { ChatTurn } from "../App";
import type { Source } from "../api";

function SourceList({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const active = sources.find((s) => s.index === open);

  return (
    <div className="sources">
      <div className="source-chips">
        {sources.map((s) => (
          <button
            key={s.index}
            className={`chip${open === s.index ? " active" : ""}`}
            aria-expanded={open === s.index}
            onClick={() => setOpen(open === s.index ? null : s.index)}
          >
            <span className="chip-index">{s.index}</span>
            {s.source}
            {s.page !== null && ` · p.${s.page}`}
          </button>
        ))}
      </div>
      {active && <blockquote className="source-text">{active.text}</blockquote>}
    </div>
  );
}

export function Message({ turn }: { turn: ChatTurn }) {
  if (turn.role === "user") {
    return (
      <div className="message user">
        <div className="bubble">{turn.content}</div>
      </div>
    );
  }

  const waiting = turn.status === "streaming" && turn.content === "";
  return (
    <div className="message assistant">
      <div className="bubble">
        {waiting ? (
          <span className="thinking" role="status">
            {turn.sources ? "Reading sources…" : "Searching documents…"}
          </span>
        ) : (
          <Markdown>{turn.content}</Markdown>
        )}
        {turn.notice && (
          <p className={turn.status === "error" ? "notice error" : "notice"} role="alert">
            {turn.notice}
          </p>
        )}
      </div>
      {turn.sources && turn.sources.length > 0 && <SourceList sources={turn.sources} />}
    </div>
  );
}
