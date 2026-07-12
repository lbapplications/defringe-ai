import { useCallback, useEffect, useMemo, useState } from "react";
import Canvas from "./Canvas";
import Toolbox from "./Toolbox";
import { post, useBoard } from "./state";

// Thin shell: owns the client-only UI state (active tool + view toggles), subscribes to
// the board over SSE, and composes the toolbox (controls) with the canvas (view). All
// board/edit state lives on the server; this component holds none of it.
export default function App() {
  const board = useBoard();
  const [tool, setTool] = useState<"move" | "dot">("move");
  const [showImg, setShowImg] = useState(true);
  const [showMask, setShowMask] = useState(true);

  // Optimistic selection: a click must feel instant, but `selected` only lands when the
  // server echoes state back over SSE (~0.15s+). So we override it locally the moment the
  // user clicks and defer to the server again once its push agrees — the same reconcile the
  // resize gesture uses for optScale. null = no override (trust the server); a session id
  // (or "" for a background deselect) = show this as selected until the stream confirms it.
  const [optSel, setOptSel] = useState<string | null>(null);
  const assets = useMemo(
    () => (optSel === null ? board : board.map((a) => ({ ...a, selected: a.session === optSel }))),
    [board, optSel],
  );
  useEffect(() => {
    if (optSel === null) return;
    const serverSel = board.find((a) => a.selected)?.session ?? "";
    if (serverSel === optSel) setOptSel(null);          // server caught up → drop the override
  }, [board, optSel]);

  const select = useCallback((session: string) => {
    setOptSel(session);                                 // highlight now
    post("/api/select", { session });                  // …tell the server, SSE reconciles
  }, []);

  // keyboard undo/redo on the selected asset (Ctrl/Cmd+Z, +Shift for redo)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      const a = assets.find((x) => x.selected);
      if (!a) return;
      if (e.shiftKey && a.can_redo) post("/api/redo", { session: a.session });
      else if (!e.shiftKey && a.can_undo) post("/api/undo", { session: a.session });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [assets]);

  return (
    <>
      <header>
        <b>defringe-ai</b> · edit screen
        <a href="/chains">edit chains →</a>
        <span className="hint">drag to move · corner handles to resize · Dot tool to seed · pushed live</span>
      </header>
      <Toolbox
        assets={assets}
        tool={tool}
        setTool={setTool}
        showImg={showImg}
        setShowImg={setShowImg}
        showMask={showMask}
        setShowMask={setShowMask}
      />
      <main className={"stage-wrap" + (tool === "dot" ? " tool-dot" : "")}>
        <Canvas assets={assets} select={select} tool={tool} showImg={showImg} showMask={showMask} />
      </main>
    </>
  );
}
