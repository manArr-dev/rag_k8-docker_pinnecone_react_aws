export interface SseEvent {
  event: string;
  data: string;
}

/**
 * Incremental Server-Sent Events parser. EventSource can't send a POST body,
 * so the chat stream is read with fetch and parsed here. Feed it decoded text
 * as it arrives; it calls `onEvent` once per complete event, however the
 * network happened to split the chunks.
 */
export function createSseParser(onEvent: (event: SseEvent) => void) {
  let buffer = "";

  return function feed(chunk: string): void {
    buffer += chunk;
    const blocks = buffer.split(/\r?\n\r?\n/);
    // The last element is an incomplete event (or "" if the chunk ended on a boundary).
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      let event = "message";
      const data: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      if (data.length > 0) onEvent({ event, data: data.join("\n") });
    }
  };
}
