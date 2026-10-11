import { describe, expect, it } from "vitest";
import { createSseParser, type SseEvent } from "./sse";

function collect(chunks: string[]): SseEvent[] {
  const events: SseEvent[] = [];
  const feed = createSseParser((e) => events.push(e));
  chunks.forEach(feed);
  return events;
}

describe("createSseParser", () => {
  it("parses complete events", () => {
    expect(collect(['event: token\ndata: {"text":"hi"}\n\nevent: done\ndata: {}\n\n'])).toEqual([
      { event: "token", data: '{"text":"hi"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("reassembles events split across chunks at any point", () => {
    const stream = 'event: token\ndata: {"text":"a b"}\n\nevent: token\ndata: {"text":"c"}\n\n';
    for (let cut = 1; cut < stream.length; cut++) {
      const events = collect([stream.slice(0, cut), stream.slice(cut)]);
      expect(events.map((e) => e.data)).toEqual(['{"text":"a b"}', '{"text":"c"}']);
    }
  });

  it("does not emit an event until its terminating blank line arrives", () => {
    expect(collect(["event: token\ndata: {}"])).toEqual([]);
  });

  it("handles CRLF, multi-line data, comments and the default event name", () => {
    expect(collect([": keep-alive\r\n\r\ndata: one\r\ndata: two\r\n\r\n"])).toEqual([
      { event: "message", data: "one\ntwo" },
    ]);
  });
});
