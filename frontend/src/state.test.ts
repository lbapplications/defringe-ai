import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

import { baseW, dispScale, post, useBoard, type Asset } from "./state";

function asset(over: Partial<Asset> = {}): Asset {
  return {
    name: "a", session: "s-a", x: 0, y: 0, scale: 1, z: 0, head: 0, steps: 1, w: 100, h: 50,
    op: "open", selected: false, editing: false, intent: "", rev: "0-1",
    locked: false, dots: [], outline: [], edge: false, edge_rev: "",
    can_undo: false, can_redo: false, timeline: [], ...over,
  };
}

describe("baseW", () => {
  it("landscape → fixed 200 on the long side", () => {
    expect(baseW({ w: 400, h: 200 })).toBe(200);
  });
  it("portrait → scales the short side down", () => {
    expect(baseW({ w: 100, h: 200 })).toBe(100);
  });
});

describe("dispScale", () => {
  it("maps image pixels to the on-board size", () => {
    // landscape 100x50, scale 1 → baseW 200 → dispScale 2
    expect(dispScale(asset({ w: 100, h: 50, scale: 1 }))).toBe(2);
  });
  it("falls back to raw scale when width is 0", () => {
    expect(dispScale(asset({ w: 0, scale: 1.5 }))).toBe(1.5);
  });
  it("honors an optimistic scale override over a.scale", () => {
    // same asset, but a resize gesture is holding scale 2 → doubled on-board size
    expect(dispScale(asset({ w: 100, h: 50, scale: 1 }), 2)).toBe(4);
  });
});

describe("post", () => {
  afterEach(() => vi.restoreAllMocks());
  it("POSTs JSON with the right headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    await post("/api/move", { session: "s-a", x: 1 });
    expect(fetchMock).toHaveBeenCalledWith("/api/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: "s-a", x: 1 }),
    });
    vi.unstubAllGlobals();
  });
});

// A minimal EventSource stand-in so useBoard's SSE subscription is testable in jsdom.
class FakeES {
  static last: FakeES | null = null;
  url: string;
  onmessage: ((e: MessageEvent) => void) | null = null;
  listeners: Record<string, (e: MessageEvent) => void> = {};
  closed = false;
  constructor(url: string) {
    this.url = url;
    FakeES.last = this;
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    this.listeners[type] = fn;
  }
  emit(data: string) {
    this.onmessage?.({ data } as MessageEvent);
  }
  emitBuild(data: string) {
    this.listeners["build"]?.({ data } as MessageEvent);
  }
  close() {
    this.closed = true;
  }
}

describe("useBoard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("subscribes to /api/events and returns pushed state", async () => {
    vi.stubGlobal("EventSource", FakeES as unknown as typeof EventSource);
    const { result, unmount } = renderHook(() => useBoard());
    expect(FakeES.last?.url).toBe("/api/events");
    act(() => FakeES.last!.emit(JSON.stringify([asset({ name: "shark" })])));
    await waitFor(() => expect(result.current[0]?.name).toBe("shark"));
    unmount();
    expect(FakeES.last?.closed).toBe(true);   // cleanup closes the stream
  });

  it("reloads the tab only when the build stamp changes", async () => {
    vi.stubGlobal("EventSource", FakeES as unknown as typeof EventSource);
    const reload = vi.fn();
    vi.stubGlobal("location", { reload } as unknown as Location);
    renderHook(() => useBoard());
    act(() => FakeES.last!.emitBuild("100"));   // first stamp → remembered, no reload
    expect(reload).not.toHaveBeenCalled();
    act(() => FakeES.last!.emitBuild("100"));   // same stamp → no reload
    expect(reload).not.toHaveBeenCalled();
    act(() => FakeES.last!.emitBuild("200"));   // changed → reload
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
