import { useEffect, useRef, useState } from "react";

// The asset shape pushed by the Python server's build_state() over SSE. The backend is
// unchanged by the frontend rewrite — this mirrors app.py's dict exactly.
export type Asset = {
  name: string;         // human-readable display label — NEVER the addressing key
  session: string;      // the opaque handle every action addresses the asset by (Phase 2, C2)
  x: number;
  y: number;
  scale: number;
  z: number;
  head: number;
  steps: number;
  w: number;
  h: number;
  op: string;
  selected: boolean;
  editing: boolean;
  intent: string;
  rev: string;
  locked: boolean;
  dots: [number, number][];
  outline: [number, number][];
  edge: boolean;          // an edge-map raster overlay (served at /mask/{name}) is present
  edge_rev: string;       // its cache-buster (PNG mtime); "" when there's no overlay
  can_undo: boolean;
  can_redo: boolean;
  timeline: string[];
};

/** POST JSON to a backend route; fire-and-forget (SSE reconciles the result). */
export function post(url: string, body: unknown): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** On-screen width of an asset before its scale (mirrors the old baseW: longest side 200). */
export function baseW(a: Pick<Asset, "w" | "h">): number {
  return a.w >= a.h ? 200 : 200 * (a.w / a.h);
}

/**
 * Konva display scale that turns image-space pixels into the on-board size. `scale`
 * defaults to the asset's server scale, but a gesture in flight (e.g. an optimistic
 * resize) can pass its own value so the view holds the new size before SSE confirms it.
 */
export function dispScale(a: Asset, scale: number = a.scale): number {
  return a.w ? (baseW(a) * scale) / a.w : scale;
}

/**
 * Subscribe to the server's single SSE state stream. Returns the latest asset array;
 * re-renders on every pushed change. Also reloads the tab when the build stamp changes
 * (server restarted with new code) — the same auto-reload the old canvas had.
 */
export function useBoard(): Asset[] {
  const [assets, setAssets] = useState<Asset[]>([]);
  const build = useRef<string | null>(null);
  useEffect(() => {
    const es = new EventSource("/api/events");
    es.addEventListener("build", (e) => {
      const stamp = (e as MessageEvent).data;
      if (build.current !== null && build.current !== stamp) location.reload();
      build.current = stamp;
    });
    es.onmessage = (e) => setAssets(JSON.parse(e.data));
    return () => es.close();
  }, []);
  return assets;
}
