/**
 * Parses the backend's Server-Sent Event format:
 *   event: <name>\n
 *   data: <json>\n
 *   \n
 *
 * Deliberately stateful/incremental rather than a one-shot parser: a fetch
 * stream delivers chunks at arbitrary byte boundaries, so a single event
 * block can arrive split across two `read()` calls. Callers accumulate into
 * a buffer and call `extractSSEEvents` after each read; only complete
 * (`\n\n`-terminated) blocks are consumed, and whatever's left over is
 * returned as `remainder` to prepend to the next chunk.
 */
export interface SSEEvent {
  event: string;
  data: unknown;
}

export function extractSSEEvents(buffer: string): { events: SSEEvent[]; remainder: string } {
  const events: SSEEvent[] = [];
  let rest = buffer;
  let boundary: number;

  while ((boundary = rest.indexOf("\n\n")) !== -1) {
    const block = rest.slice(0, boundary);
    rest = rest.slice(boundary + 2);

    if (!block.trim()) continue;

    const lines = block.split("\n");
    const eventLine = lines.find((l) => l.startsWith("event: "));
    const dataLine = lines.find((l) => l.startsWith("data: "));
    if (!eventLine || !dataLine) continue;

    const event = eventLine.slice("event: ".length);
    const rawData = dataLine.slice("data: ".length);
    let data: unknown;
    try {
      data = JSON.parse(rawData);
    } catch {
      data = rawData; // defensive fallback — the backend always sends valid JSON
    }
    events.push({ event, data });
  }

  return { events, remainder: rest };
}

/** Consumes a fetch Response's streaming body, yielding parsed SSE events as they arrive. */
export async function* streamSSE(response: Response): AsyncGenerator<SSEEvent> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, remainder } = extractSSEEvents(buffer);
    buffer = remainder;
    for (const event of events) yield event;
  }
}
