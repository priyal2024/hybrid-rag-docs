import { extractSSEEvents } from "./sse";

describe("extractSSEEvents", () => {
  it("parses a single complete event", () => {
    const { events, remainder } = extractSSEEvents('event: token\ndata: "hello"\n\n');
    expect(events).toEqual([{ event: "token", data: "hello" }]);
    expect(remainder).toBe("");
  });

  it("parses multiple events in one buffer", () => {
    const buffer =
      'event: sources\ndata: [{"url":"https://react.dev/x"}]\n\n' +
      'event: token\ndata: "hi"\n\n' +
      "event: done\ndata: {}\n\n";
    const { events, remainder } = extractSSEEvents(buffer);
    expect(events).toHaveLength(3);
    expect(events[0]).toEqual({ event: "sources", data: [{ url: "https://react.dev/x" }] });
    expect(events[1]).toEqual({ event: "token", data: "hi" });
    expect(events[2]).toEqual({ event: "done", data: {} });
    expect(remainder).toBe("");
  });

  it("leaves an incomplete event (no trailing blank line) in the remainder", () => {
    const { events, remainder } = extractSSEEvents('event: token\ndata: "partial');
    expect(events).toEqual([]);
    expect(remainder).toBe('event: token\ndata: "partial');
  });

  it("handles an event split across two chunks (the actual streaming case)", () => {
    const firstChunk = 'event: token\ndata: "hel';
    const { events: eventsA, remainder } = extractSSEEvents(firstChunk);
    expect(eventsA).toEqual([]);

    const secondChunk = remainder + 'lo"\n\n';
    const { events: eventsB, remainder: remainderB } = extractSSEEvents(secondChunk);
    expect(eventsB).toEqual([{ event: "token", data: "hello" }]);
    expect(remainderB).toBe("");
  });

  it("recovers the buffer correctly when a full event is followed by a partial one", () => {
    const buffer = 'event: token\ndata: "a"\n\nevent: token\ndata: "b';
    const { events, remainder } = extractSSEEvents(buffer);
    expect(events).toEqual([{ event: "token", data: "a" }]);
    expect(remainder).toBe('event: token\ndata: "b');
  });

  it("falls back to the raw string for non-JSON data instead of throwing", () => {
    const { events } = extractSSEEvents("event: token\ndata: not-json\n\n");
    expect(events).toEqual([{ event: "token", data: "not-json" }]);
  });

  it("returns nothing for an empty buffer", () => {
    const { events, remainder } = extractSSEEvents("");
    expect(events).toEqual([]);
    expect(remainder).toBe("");
  });
});
