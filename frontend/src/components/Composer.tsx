import { type KeyboardEvent, useRef, useState } from "react";

interface Props {
  busy: boolean;
  onSend(text: string): void;
  onStop(): void;
}

export function Composer({ busy, onSend, onStop }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    onSend(trimmed);
    setText("");
    if (ref.current) ref.current.style.height = "auto";
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends, Shift+Enter adds a line. Ignore Enter while an IME is composing.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <textarea
        ref={ref}
        value={text}
        rows={1}
        maxLength={4000}
        placeholder="Ask a question about your documents"
        aria-label="Message"
        autoFocus
        onChange={(e) => {
          setText(e.target.value);
          e.target.style.height = "auto";
          e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
        }}
        onKeyDown={onKeyDown}
      />
      {busy ? (
        <button type="button" className="primary" onClick={onStop}>
          Stop
        </button>
      ) : (
        <button type="submit" className="primary" disabled={!text.trim()}>
          Send
        </button>
      )}
    </form>
  );
}
